# Chat — multimodal perception (Nemotron 3 Nano Omni)

The pipeline's entry point. Stage A is one chat step that takes the
user-uploaded asset and emits a JSON-schema-enforced `BriefingSpec`.

## Provider

`NvidiaChatProvider` from `genblaze-nvidia` 0.3. First-class —
`Pipeline.step()` plays it the same as image / audio / video providers.
The shim that used to live in this sample (`NvidiaChatStepProvider`) is
gone.

## Default model

`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`. Multimodal in
(image / audio / video / text), text out. 256K context, configurable
reasoning trace, free-tier endpoint on `build.nvidia.com`. Override via
`NEMOTRON_CHAT_MODEL` env or `BriefingRequest.chat_model`.

## How the asset reaches the model

The uploaded asset arrives as a `BriefingRequest.input_asset_url` plus
`input_asset_sha256` and `input_asset_media_type`. `app.main._input_asset`
reconstructs an `Asset` and `app.repo.pipelines.build_briefing_spec_pipeline`
attaches it via `external_inputs=[asset]`.

`NvidiaChatProvider.generate()` then dispatches by `media_type`:

| Asset media_type | Wire shape                                     |
| ---------------- | ---------------------------------------------- |
| `image/*`        | `{"type":"image_url","image_url":{"url":...}}` |
| `audio/*`        | `{"type":"audio_url","audio_url":{"url":...}}` |
| `video/*`        | `{"type":"video_url","video_url":{"url":...}}` |
| `application/pdf`| `INVALID_INPUT` — rasterize first              |

The provider builds a single `user` message whose content is the text
prompt followed by the appropriate content block.

## Structured output

`Pipeline.step(response_format=BriefingSpec)` passes the Pydantic class
through `coerce_response_format`, which derives the JSON schema and
sends it as `{"type":"json_schema","json_schema":{...}}` per the
OpenAI / NIM wire. NIM enforces server-side — the model returns valid
`BriefingSpec` JSON or no response at all.

Downstream parsing in `app.main` is therefore the one-liner
`BriefingSpec.model_validate_json(asset.metadata["text"])`. No
try/except, no JSON-from-prose fallback, no system-prompt prayer.

## Reasoning trace

`NvidiaChatProvider(reasoning=True)` toggles the chat-template
`enable_thinking` flag. Default is `True` (matches the
`-reasoning`-suffixed slug). The reasoning trace is consumed
server-side; only the final response reaches us. To disable, set
`NEMOTRON_REASONING=false` — saves tokens and latency at the cost of
weaker reasoning on harder instructions.

## What lands in B2

`NvidiaChatProvider` writes one Asset per step carrying the chat text.
The Asset's url is currently a synthetic `text:<sha256>` placeholder
(`Asset.text(content=..., media_type=...)` is "active plan Wave 4" per
the provider's docstring); the actual text lives on
`asset.metadata["text"]`. `ObjectStorageSink` still records the asset
on the run's `manifest.json` so provenance is intact.
