# App workflows

End-to-end lifecycle of a single briefing request. Read this alongside
[`ARCHITECTURE.md`](../ARCHITECTURE.md) for the layer diagram.

## 1. The user uploads an asset

The frontend's `<UploadForm>` collects a single file (image / audio /
video, ≤25 MB by default) plus an optional instruction. On submit it
issues a multipart `POST /api/proxy/uploads`; the Next.js proxy
forwards to FastAPI's `POST /uploads`.

The handler in `app/main.py::upload`:

1. Reads the body, enforces `MAX_UPLOAD_BYTES`.
2. Sniffs the MIME type (client-supplied `media_type` form field >
   `UploadFile.content_type` > `mimetypes.guess_type`).
3. Rejects anything outside `image/* | audio/* | video/*` with a
   415 (PDFs are explicitly redirected at the user via the response
   detail — see `docs/features/uploads.md`).
4. Computes SHA-256 over the bytes and stages to B2 at
   `nemotron/uploads/<sha256>/<filename>` (content-addressed —
   identical uploads dedupe automatically).
5. Returns `{durable_url, sha256, media_type, size_bytes}`.

The frontend round-trips `sha256` into the next request — that's what
makes the run cacheable. Without it, `step_cache_key` falls back to
the URL, which would break dedup across reruns.

## 2. The user triggers a briefing

`POST /api/proxy/runs` → FastAPI `POST /runs` with a `BriefingRequest`:

```json
{
  "input_asset_url": "https://<b2-host>/<bucket>/nemotron/uploads/<sha>/cat.png",
  "input_asset_sha256": "<sha>",
  "input_asset_media_type": "image/png",
  "instruction": null,
  "include_video": false
}
```

`app.main._run_briefing` reconstructs an `Asset` from those fields and
runs Stage A.

## 3. Stage A — Nemotron 3 Nano Omni perceives

`build_briefing_spec_pipeline()` returns a
`Pipeline("nvidia-nemotron-genblaze-b2", max_concurrency=1)` with a
single `NvidiaChatProvider` step. The step:

- Receives the upload via `external_inputs=[asset]`. The provider
  inspects `asset.media_type` and builds the right OpenAI-vision
  content block (`image_url` / `audio_url` / `video_url`) inside the
  user message.
- Sends `response_format=BriefingSpec`. `genblaze-core` derives the
  JSON schema from the Pydantic class and NIM enforces it server-side
  — the response is guaranteed to validate.
- Has reasoning-mode on by default (`NEMOTRON_REASONING=true`,
  matching the `-reasoning`-suffixed slug). The reasoning trace is
  consumed and discarded by NIM; only the final structured response
  reaches us.

The completed step's asset carries the JSON text in
`asset.metadata["text"]`. `app.main` parses it via
`BriefingSpec.model_validate_json(text)`.

## 4. Stage B — Genblaze fans out media generation

`build_media_pipeline(spec, ...)` returns a second
`Pipeline("nvidia-nemotron-genblaze-b2", max_concurrency=3)` with
statically rendered prompts:

| step idx | provider              | model                                  | prompt source                      |
| -------- | --------------------- | -------------------------------------- | ---------------------------------- |
| 0..2     | `NvidiaImageProvider` | `black-forest-labs/flux.1-schnell`     | `takeaways[i].illustration_prompt` |
| 3..5     | `NvidiaAudioProvider` | `nvidia/riva-tts`                      | `takeaways[i].narration`           |
| 6        | `NvidiaAudioProvider` | `nvidia/fugatto`                       | `music_prompt`                     |
| 7?       | `NvidiaVideoProvider` | `nvidia/cosmos-2.0-diffusion-text2world` | `recommended_video_prompt` (best-effort) |

Both pipelines write through the same `ObjectStorageSink`, so all
artifacts land at `nemotron/<run-id>/...` with a `manifest.json` per
stage that carries the same Pipeline name.

## 5. The handler returns

```json
{
  "briefing": { "title": "...", "summary": "...", "takeaways": [...], "music_prompt": "..." },
  "spec_run":  { ... full Genblaze Run ... },
  "media_run": { ... full Genblaze Run ... },
  "video_skipped": null,
  "estimated_cost_usd": { "spec": null, "media": null }
}
```

`estimated_cost_usd` returns `null` for the free tier (no published
per-request pricing). The wiring uses `Pipeline.estimated_cost()`;
the same field populates automatically when paid providers are added.

## 6. Streaming variant — `/runs/stream`

Same flow, wrapped in `text/event-stream`. Each `Pipeline.stream(...)`
event becomes an SSE event whose `event:` line is the Pydantic class
name and whose `data:` line is the model_dump JSON.

SSE is offered as an advanced endpoint and is **not wired into the
default UI** — `apps/web/src/app/page.tsx` uses the synchronous
`/runs` path. SSE failures DO surface as a typed terminal event
(`event: error`, `code` is the `ProviderErrorCode` value). The handler
passes `raise_on_failure=True` to `Pipeline.stream()` and catches
`PipelineError` after the inner event loop drains. There is no
mid-stream auto-retry though, so consumers that don't want the
best-effort video tail to surface as an error should still set
`include_video=false` upfront.

## 7. The UI renders the result

`page.tsx` slices `media_run.steps` by modality:

- First three image steps → takeaway illustrations
- First three audio steps → takeaway narrations
- Fourth audio step → mood music in `<MusicPlayer>`
- Optional video step → standalone `<video>` below the takeaways

If `video_skipped === "auth_required"`, a `<Badge>` surfaces the
explanation. If the chat provider returned an unexpected JSON shape
(shouldn't happen with `response_format=BriefingSpec` enforcement,
but defensive), Pydantic validation in `app.main` raises 502 before
the UI sees a half-baked spec.
