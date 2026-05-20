# Audio — narration (Riva TTS)

Three narration tracks, one per takeaway, fanned out in parallel via
`NvidiaAudioProvider` against `nvidia/riva-tts`.

## The shape

Identical to the image fan-out: three `.step()` calls in
`build_media_pipeline()`, each with the takeaway's narration text as
its `prompt`. `Pipeline(max_concurrency=3)` lets all three run in
parallel with the three illustrations.

```python
for ch in spec.takeaways:
    p = p.step(
        NvidiaAudioProvider(api_key=api_key),
        model=tts_model,                 # nvidia/riva-tts by default
        modality=Modality.AUDIO,
        prompt=ch.narration,
    )
```

## Voice selection

Riva ships a default English voice. To pick another, pass `voice`
through the kwargs — `NvidiaAudioProvider.normalize_params()` forwards
unknown kwargs into the NVIDIA payload. Example:

```python
p = p.step(
    NvidiaAudioProvider(api_key=api_key),
    model="nvidia/riva-tts",
    modality=Modality.AUDIO,
    prompt=ch.narration,
    voice="English-US.Female-1",
)
```

The full voice list lives in NVIDIA's NIM model card for Riva.

## Where the assets land

Each WAV / MP3 lands at
`nemotron/<run-id>/<step-id>/audio.wav` (or `.mp3` depending on the
model's output format). The asset's `media_type` field tells the
browser which `<audio>` element to use.

## Why three separate steps instead of batch_run?

`Pipeline.batch_run([prompt1, prompt2, prompt3])` would run the *whole*
pipeline once per prompt, generating 9 images and 9 narrations and 3
music tracks — the wrong shape. We want one run with three parallel
narration steps inside it, which is what siblings + `max_concurrency`
gives us.
