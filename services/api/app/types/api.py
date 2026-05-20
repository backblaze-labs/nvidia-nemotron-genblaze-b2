"""Inbound request DTOs and the briefing response schema.

Outbound run payloads are Genblaze types directly. The schema below
(`BriefingSpec`) doubles as the chat step's `response_format=` value, so
upstream JSON-schema enforcement keeps the model on contract.
"""

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Result of POST /uploads — gives the client what it needs to run."""

    durable_url: str = Field(..., description="Credential-free B2 URL of the staged asset.")
    sha256: str = Field(..., description="SHA-256 of the bytes; required for stable cache keys.")
    media_type: str = Field(..., description="Sniffed or client-supplied MIME type.")
    size_bytes: int = Field(..., ge=0)


class Takeaway(BaseModel):
    """One of three structured takeaways the chat step emits."""

    headline: str = Field(..., min_length=1, max_length=140)
    illustration_prompt: str = Field(..., min_length=4, max_length=400)
    narration: str = Field(..., min_length=10, max_length=1500)


class BriefingSpec(BaseModel):
    """The chat step's structured output. Drives the media fan-out.

    Used as the `response_format=` argument on `Pipeline.step(...)`; Genblaze's
    `coerce_response_format` auto-derives the JSON schema and NIM enforces it,
    so the downstream pipeline never sees free-form prose.
    """

    title: str = Field(..., min_length=1, max_length=140)
    summary: str = Field(..., min_length=10, max_length=1200)
    takeaways: list[Takeaway] = Field(..., min_length=3, max_length=3)
    music_prompt: str = Field(..., min_length=4, max_length=400)
    recommended_video_prompt: str | None = Field(default=None, max_length=400)


class BriefingRequest(BaseModel):
    """A single 'perceive this asset, generate a briefing' request."""

    input_asset_url: str = Field(
        ...,
        description="Durable HTTPS URL of the asset to perceive — typically from POST /uploads.",
    )
    input_asset_sha256: str | None = Field(
        default=None,
        description=(
            "SHA-256 of the input bytes. Recommended: pass the value returned by "
            "POST /uploads so step.cache and the manifest canonical hash stay stable "
            "across reruns. If omitted the chat step still works; cache misses every run."
        ),
    )
    input_asset_media_type: str | None = Field(
        default=None,
        description=(
            "MIME type of the input asset (e.g. 'image/png', 'audio/wav', 'video/mp4'). "
            "Required for NvidiaChatProvider to dispatch to the right OpenAI-vision "
            "content block."
        ),
    )
    instruction: str | None = Field(
        default=None,
        max_length=600,
        description="Optional override for the default 'summarize into 3 takeaways' prompt.",
    )
    chat_model: str | None = Field(
        default=None,
        description="Override the default Nemotron 3 Nano Omni — any NIM chat model id.",
    )
    image_model: str | None = Field(
        default=None,
        description="Override the default image model (FLUX.1 Schnell by default).",
    )
    include_video: bool = Field(
        default=False,
        description=(
            "Best-effort Cosmos video tail. Free-tier NVIDIA keys often lack"
            " Cosmos access; if the step fails with AUTH_FAILURE the run is"
            " re-issued without video and `video_skipped` is set on the response."
        ),
    )
    video_model: str | None = Field(
        default=None,
        description="Override the default video model. Ignored when include_video=False.",
    )
