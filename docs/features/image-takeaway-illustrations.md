# Image — takeaway illustrations

Three illustrations, one per takeaway, fanned out in parallel.

## The fan-out idiom

`Pipeline.step()` is called three times in `build_media_pipeline()`,
each with its own statically rendered prompt:

```python
for ch in spec.takeaways:
    p = p.step(
        NvidiaImageProvider(api_key=api_key),
        model=image_model,
        modality=Modality.IMAGE,
        prompt=ch.illustration_prompt,
        aspect_ratio="16:9",
        cfg_scale=4.5,
    )
```

`Pipeline(name=..., max_concurrency=3)` lets the three image steps
execute concurrently. Genblaze's per-step retry / backoff logic
handles transient NVIDIA failures; sibling steps don't block each
other.

## Why FLUX.1 Schnell by default?

Schnell is the cheapest free path on `build.nvidia.com`: 4-step
diffusion, sub-3-second wall-clock per image at 1024x1024. Override
to `stabilityai/stable-diffusion-3.5-large` or
`stabilityai/sdxl-turbo` via `NEMOTRON_IMAGE_MODEL` or per-request
`image_model` field.

## Aspect ratio

Hard-coded to `16:9` so the illustrations slot cleanly into the
takeaway cards' `aspect-video` containers. Adjust in
`repo/pipelines.py` if you want a different layout — the
`aspect_ratio` kwarg is forwarded into the NVIDIA payload by
`NvidiaImageProvider.normalize_params()`.

## Where the assets land

Each step's PNG is uploaded by `ObjectStorageSink` under
`nemotron/<run-id>/<step-id>/image.png`. The asset's `url` field
on the returned `Step` is rewritten to the durable B2 URL — the UI
just renders it via `<img src={asset.url} />`. No presigning is
needed for public buckets; for private ones, expose a thin
`/assets/sign` endpoint that calls `S3StorageBackend.get_url(key,
expires_in=...)` from inside `app/repo/`.
