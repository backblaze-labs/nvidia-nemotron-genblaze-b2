# Audio — mood music (Fugatto)

One ambient soundtrack per run, prompted by Nemotron Omni's
`music_prompt` field.

## The shape

A single trailing `NvidiaAudioProvider` step against `nvidia/fugatto`:

```python
p = p.step(
    NvidiaAudioProvider(api_key=api_key),
    model=music_model,                # nvidia/fugatto by default
    modality=Modality.AUDIO,
    prompt=spec.music_prompt,
)
```

`response_format=BriefingSpec` enforces `music_prompt` as a required
non-empty string, so there's no fallback to worry about.

## Prompt-shaping tips

Fugatto responds best to:

- **Mood adjectives first**: "Wistful, gentle, twilight…" not "A song
  that is wistful and gentle."
- **Instrumentation hints**: "…with soft piano and brushed drums."
- **Tempo cues**: "Slow, rubato" or "Steady 90 BPM."
- **Length cues**: Fugatto picks length based on the prompt's
  implication; we don't pin a duration.

The default Nemotron instruction nudges the model toward this shape;
override `BriefingRequest.instruction` if you want a different bias.

## Stereo

Fugatto returns stereo by default. The frontend's `MusicPlayer`
renders a sticky `<audio>` element at the bottom of the page so the
soundtrack keeps playing while the user scrolls through the takeaways.

## Where the asset lands

`nemotron/<run-id>/<step-id>/audio.wav` (or `.mp3`). The
`MusicPlayer` reads `assets[0].url` and `assets[0].media_type`
directly from the Genblaze `Step` model — no DTO hop.
