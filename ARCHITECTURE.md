# Architecture

```
+--------------------------------------------------------------+
|  apps/web (Next.js, App Router)                              |
|    page.tsx + components/*  +  /api/proxy/[...path]          |
|        |               (HTTP / SSE)                          |
+--------|----------------------------------------------------+
         v
+--------------------------------------------------------------+
|  services/api (FastAPI)                                      |
|    app/main.py        -- handlers, returns Genblaze types    |
|    app/types/api.py   -- BriefingRequest + BriefingSpec      |
|    app/config.py      -- env settings (B2_*, NVIDIA_API_KEY) |
|    app/repo/pipelines.py  --  ONLY file that imports         |
|                              genblaze_* (the layer boundary) |
+--------|----------------------------------------------------+
         v
+--------------------------------------------------------------+
|  genblaze-core 0.2.8  +  genblaze-nvidia 0.2.1  +            |
|  genblaze-s3 0.3.0                                           |
|    Pipeline + Steps + Tracers                                |
|    NvidiaChatProvider (multimodal)                           |
|    NvidiaImage/Audio/VideoProvider                           |
|    S3StorageBackend.for_backblaze(...)                       |
|    ObjectStorageSink (manifest.json, lifecycle, hashes)      |
+--------|---------------------|------------------------------+
         v                     v
   build.nvidia.com      Backblaze B2
   (NIM endpoints)       (S3-compatible)
```

## Layer rules (enforced by `tests/test_structure.py`)

- **No direct `boto3`/`botocore` imports** anywhere under
  `services/api/app/`. Storage is delegated to `genblaze-s3`, which
  owns the boto3 client and sets a `b2ai-genblaze/<version>` user
  agent on it. The sample's per-app identity is carried in the
  `Pipeline(name="nvidia-nemotron-genblaze-b2")` slug, which
  `genblaze-s3` writes into every B2 manifest.
- **`genblaze_*` imports only from `app/repo/`**, with allowlisted
  exceptions in `app/main.py`: `genblaze_core.exceptions`
  (PipelineError + ProviderError ARE the contract surfaced to
  clients), `genblaze_core.models.enums` (ProviderErrorCode for the
  AUTH_FAILURE catch), and `genblaze_core.models.asset` (Asset
  reconstructed from `BriefingRequest` for the `external_inputs=`
  argument on the chat step).
- **`repo/pipelines.py` stays compact.** A structural test caps the
  file size so you can read the entire pipeline definition in one
  sitting.

## Why two pipelines instead of one chained run?

`Pipeline.step()` prompts are rendered at construction time, so Stage
B's per-takeaway prompts can't derive from Stage A's output inside a
single pipeline. The sample runs in two stages, both under the same
Pipeline slug:

1. **Stage A** — one chat step (`NvidiaChatProvider`). The uploaded
   asset is attached via `external_inputs=[asset]`; the provider
   builds the OpenAI-vision-shape `messages[].content[]` array
   automatically. `response_format=BriefingSpec` enforces the JSON
   schema upstream, so the parsed output is guaranteed valid.
2. **Stage B** — fan-out images + narrations + music (+ optional
   video). Each step's prompt is statically rendered from Stage A's
   parsed `BriefingSpec`.

Both pipelines write through the same `ObjectStorageSink`, so all run
artifacts land at `nemotron/<run-id>/...` with a `manifest.json` per
stage that carries the same Pipeline name.

## SSE wire format

`/runs/stream` returns `text/event-stream`. Each Genblaze pipeline
event becomes one SSE event:

```
event: PipelineStartedEvent
data: {"pipeline_name":"nvidia-nemotron-genblaze-b2","run_id":"..."}

event: StepStartedEvent
data: {"step_id":"...","provider":"nvidia-chat","model":"..."}

event: StepCompletedEvent
data: {"step_id":"...","status":"succeeded","assets":[{...}]}

event: PipelineCompletedEvent
data: {...}
```

Stage A streams first, then Stage B. On any failure, the handler
emits a typed terminal event:

```
event: error
data: {"code":"AUTH_FAILURE","msg":"..."}
```

`Pipeline.stream(raise_on_failure=True)` re-raises after the worker
thread finishes; we catch `PipelineError` and emit the structured
error event so consumers don't have to parse `StepFailedEvent`
payloads.

The SSE endpoint does NOT auto-retry on Cosmos `AUTH_FAILURE` — by
the time we know the video step failed, Stage A's events are already
on the wire and re-running would replay them. Consumers that want a
clean run on a key without Cosmos access should set
`include_video: false` upfront, or use the synchronous `/runs`
endpoint (which DOES handle the retry).

## Failure modes

| What fails                  | What the sample does                                                        |
| --------------------------- | --------------------------------------------------------------------------- |
| Asset upload too large      | `POST /uploads` returns 413 (`MAX_UPLOAD_BYTES`).                           |
| Asset MIME unsupported      | `POST /uploads` returns 415 with the supported-prefixes hint (PDFs link).   |
| Chat returns invalid JSON   | `response_format=BriefingSpec` enforces upstream — happens at NIM, not us.  |
| One image step fails        | `Pipeline.run(raise_on_failure=True)` raises `PipelineError`; sibling step assets up to that point are still on `exc.result`. |
| Cosmos video AUTH_FAILURE   | `/runs` re-issues the media stage without the video step (typed catch).     |
| B2 upload fails             | Reported on `manifest.transfer_failures`; `error_summary()` surfaces it.    |
| NVIDIA rate limit           | `genblaze-nvidia` raises `ProviderError(RATE_LIMIT)`; flows up to handler.  |
