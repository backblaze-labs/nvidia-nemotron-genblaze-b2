# Video — best-effort Cosmos tail

Cosmos `nvidia/cosmos-1.0-7b` access on `build.nvidia.com` is gated
behind a separate request flow, distinct from the `nvapi-` key that
unlocks chat / image / TTS / music. Free-tier accounts often don't
have it. Rather than refuse to run the rest of the pipeline, this
sample treats the video step as **best-effort**: it runs when the
client opts in via `include_video: true`, and it's transparently
skipped when the key lacks access.

## How it's wired

In `repo/pipelines.py::build_media_pipeline`:

```python
if include_video and video_model:
    p = p.step(
        NvidiaVideoProvider(api_key=settings.nvidia_api_key),
        model=video_model,
        modality=Modality.VIDEO,
        prompt=chapters[0].get("image_prompt", "") if chapters else "",
        aspect_ratio="16:9",
    )
```

The video step is appended only when the request asks for it — there
is no built-in fallback model rotation, by design (the alternative
free video models are also gated).

## How AUTH_FAILURE is surfaced

When NVIDIA returns 401/403, `NvidiaVideoProvider.generate()` raises
`ProviderError(error_code=ProviderErrorCode.AUTH_FAILURE)`.

For the **non-streaming** endpoint (`POST /runs`), as of `genblaze-core`
0.2.5 the pipeline raises `PipelineError` when any step fails (we pass
`raise_on_failure=True` to opt in early; default flips in 0.4.0). The
exception carries the partial `PipelineResult`, so we discriminate
`AUTH_FAILURE` via the failed step's typed `error_code`:

```python
try:
    return _run_story(req, allow_video=True)
except PipelineError as e:
    if _pipeline_error_code(e) == ProviderErrorCode.AUTH_FAILURE and req.include_video:
        payload = _run_story(req, allow_video=False)
        payload["video_skipped"] = "auth_required"
        return payload
    raise HTTPException(...)
```

`_pipeline_error_code` reads
`exc.result.run.steps[exc.failed_step_index].error_code` — `PipelineError`
itself flattens the failed step into a string message, but the typed code
is still on the underlying Step. The handler re-issues the media stage
(only Stage B — the chat result is reused) without the video tail and
stamps `video_skipped: "auth_required"` on the response.

For the **SSE** endpoint (`POST /runs/stream`):

There is no mid-stream auto-retry, but the failure IS surfaced as a typed
terminal event. `Pipeline.stream(raise_on_failure=True)` in
`genblaze-core` 0.2.5 re-raises after the worker thread finishes (the
event stream forwards into `Pipeline.run()` and propagates via an
exception box), so `services/api/app/main.py::stream_story` catches
`PipelineError` and emits:

```
event: error
data: {"code": "AUTH_FAILURE", "msg": "Cosmos returned 401"}
```

The lack of mid-stream retry is intentional: by the time we know the
video step failed, Stage A's events are already on the wire, and
re-running would replay them. SSE consumers that want a clean run on a
key without Cosmos access should set `include_video: false` upfront, or
fall back to the synchronous `/runs` endpoint which DOES auto-retry
(no streamed state to roll back).

## How to enable when access lands

When NVIDIA grants Cosmos access to your `nvapi-` key, no code change
is needed. The same `include_video: true` request now succeeds; the
video step's asset URL appears in `media_run.steps` and the UI
renders a `<video>` element below the chapters.

## Why not auto-detect Cosmos access at startup?

It would mean a synthetic Cosmos call on boot — costly, slow, and
opaque (some keys have access for one model id but not another).
Best-effort-with-graceful-fallback is the lower-friction shape and
matches how access actually evolves on `build.nvidia.com`.
