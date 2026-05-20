"""Settings loader. All env names match the parent-repo B2 standard."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide config. Env-driven; never hold raw secrets in code."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Backblaze B2 (parent standard names — must not be renamed)
    b2_endpoint: str = Field(..., alias="B2_ENDPOINT")
    b2_region: str = Field(..., alias="B2_REGION")
    b2_key_id: str = Field(..., alias="B2_KEY_ID")
    b2_application_key: str = Field(..., alias="B2_APPLICATION_KEY")
    b2_bucket_name: str = Field(..., alias="B2_BUCKET_NAME")

    # NVIDIA NIM — one key covers all four modalities
    nvidia_api_key: str = Field(..., alias="NVIDIA_API_KEY")

    # Observability + dev
    otel_endpoint: str | None = Field(default=None, alias="OTEL_ENDPOINT")
    step_cache_dir: Path = Field(default=Path(".cache/nemotron"), alias="STEP_CACHE_DIR")

    # Model defaults. Chat model defaults to Nemotron 3 Nano Omni — the
    # multimodal perception sub-agent the sample is built around. The
    # `-reasoning` slug enables thinking-mode by default; flip via
    # `nemotron_reasoning=False` if you want to skip the reasoning trace.
    nemotron_chat_model: str = Field(
        default="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        alias="NEMOTRON_CHAT_MODEL",
    )
    nemotron_reasoning: bool = Field(default=True, alias="NEMOTRON_REASONING")
    nemotron_image_model: str = Field(
        default="black-forest-labs/flux.1-schnell", alias="NEMOTRON_IMAGE_MODEL"
    )
    nemotron_tts_model: str = Field(default="nvidia/riva-tts", alias="NEMOTRON_TTS_MODEL")
    nemotron_music_model: str = Field(default="nvidia/fugatto", alias="NEMOTRON_MUSIC_MODEL")
    nemotron_video_model: str = Field(
        default="nvidia/cosmos-2.0-diffusion-text2world", alias="NEMOTRON_VIDEO_MODEL"
    )
    # Upload guardrail. ≤25 MB v1 because uploads stream synchronously through
    # FastAPI; see docs/features/uploads.md for the production-hardening note.
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")


settings = Settings()  # imported once at process start
