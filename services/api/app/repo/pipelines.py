"""Genblaze pipeline factories — the only file that imports `genblaze_*`.

Two pipelines, both under the same `Pipeline.name` slug for provenance:

  Stage A `build_briefing_spec_pipeline` -> NvidiaChatProvider perceives the
          uploaded asset (image/audio/video) and returns a JSON-schema-
          enforced `BriefingSpec`.
  Stage B `build_media_pipeline` -> 3x image + 3x narration + 1x music + opt video.

Stage A is a single `.step(NvidiaChatProvider, response_format=BriefingSpec,
external_inputs=[asset])` call. The provider builds OpenAI-vision-shape
content blocks from the Asset's media_type; NIM enforces the JSON schema
upstream so downstream parsing is `BriefingSpec.model_validate_json(...)`.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from genblaze_core import (
    KeyStrategy,
    Modality,
    ObjectStorageSink,
    Pipeline,
    StepCache,
)
from genblaze_core.models.asset import Asset
from genblaze_core.models.chat import coerce_response_format
from genblaze_core.observability import CompositeTracer, LoggingTracer, OTelTracer
from genblaze_core.providers.base import SyncProvider
from genblaze_nvidia import (
    NvidiaAudioProvider,
    NvidiaChatProvider,
    NvidiaImageProvider,
    NvidiaVideoProvider,
)
from genblaze_s3 import S3StorageBackend

from app.config import settings
from app.types.api import BriefingSpec

PIPELINE_NAME = "nvidia-nemotron-genblaze-b2"
PREFIX = "nemotron"

DEFAULT_INSTRUCTION = (
    "Inspect the attached media. Produce a JSON briefing matching the schema: "
    "a concise title, a 1-2 sentence summary, exactly three takeaways "
    "(headline + an illustration_prompt suitable for a text-to-image model "
    "+ a 2-3 sentence narration script), a music_prompt describing an "
    "ambient soundtrack that matches the mood, and an optional "
    "recommended_video_prompt for a short text-to-video establishing shot."
)


@lru_cache(maxsize=1)
def _artifact_dir() -> Path:
    """Stage base64 NIM outputs under the OS temp root, not CWD.

    NvidiaImage/Audio/VideoProvider default `output_dir=None`, which writes to
    CWD. Genblaze's AssetTransfer guard then rejects the resulting file://
    URLs as "outside allowed directories" — the allowlist is the temp roots.
    """
    d = Path(tempfile.gettempdir()) / "nemotron-artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


@lru_cache(maxsize=1)
def backend() -> S3StorageBackend:
    """B2 backend singleton. Explicit kwargs bypass the B2_APP_KEY env fallback.

    `for_backblaze(preflight=True)` verifies bucket/region eagerly and raises
    `StorageError` on auth/region failure — first call here is the boot
    preflight. Lifespan treats failures as warn-not-fatal. genblaze-s3 0.3.2+
    names the correct region on `B2_REGION` mismatch via a cross-region probe.
    """
    return S3StorageBackend.for_backblaze(
        settings.b2_bucket_name,
        region=settings.b2_region,
        key_id=settings.b2_key_id,
        app_key=settings.b2_application_key,
        auto_lifecycle=True,
    )


def sink() -> ObjectStorageSink:
    """Per-run sink. HIERARCHICAL keys yield clean nemotron/<run-id>/... layout.

    Default `URLPolicy.AUTO` (0.3.2+) logs a one-time benign WARN when
    `backend.public_url_base` is unset, as it is here.
    """
    return ObjectStorageSink(
        backend(), prefix=PREFIX, key_strategy=KeyStrategy.HIERARCHICAL
    )


def _tracer() -> CompositeTracer:
    tracers = [LoggingTracer()]
    if settings.otel_endpoint:
        tracers.append(OTelTracer(endpoint=settings.otel_endpoint))
    return CompositeTracer(tracers)


def _attach_observability(p: Pipeline) -> Pipeline:
    return p.tracer(_tracer()).cache(StepCache(settings.step_cache_dir))


def nvidia_providers() -> dict[str, SyncProvider]:
    """One of each NVIDIA provider, for `app.main` startup preflight + /models.

    Construction is cheap; providers are stateless apart from their poll cache,
    so making fresh instances at boot is fine — these are not the same
    instances the pipeline steps construct, but `preflight_auth` validates the
    nvapi- key, which IS shared.
    """
    api_key = settings.nvidia_api_key
    return {
        "chat": NvidiaChatProvider(api_key=api_key, reasoning=settings.nemotron_reasoning),
        "image": NvidiaImageProvider(api_key=api_key),
        "audio": NvidiaAudioProvider(api_key=api_key),
        "video": NvidiaVideoProvider(api_key=api_key),
    }


def build_briefing_spec_pipeline(
    *, input_asset: Asset, instruction: str | None, chat_model: str
) -> Pipeline:
    """Stage A: Nemotron 3 Nano Omni perceives the input asset → BriefingSpec JSON.

    The chat step takes the input via `external_inputs=[input_asset]`; the
    provider auto-builds the OpenAI-vision-shape content blocks based on the
    Asset's `media_type`. `response_format=BriefingSpec` enforces the JSON
    schema upstream, so the downstream parsing in `app.main` is just
    `BriefingSpec.model_validate_json(...)`.
    """
    chat = NvidiaChatProvider(
        api_key=settings.nvidia_api_key,
        reasoning=settings.nemotron_reasoning,
    )
    # Pre-coerce the Pydantic class to the OpenAI wire-shape JSON-schema
    # dict so the cache-key serializer sees plain data. The provider's
    # internal coercion in `_build_payload` is idempotent on dicts.
    return _attach_observability(Pipeline(PIPELINE_NAME, max_concurrency=1)).step(
        chat,
        model=chat_model,
        modality=Modality.TEXT,
        prompt=instruction or DEFAULT_INSTRUCTION,
        response_format=coerce_response_format(BriefingSpec),
        external_inputs=[input_asset],
    )


def build_media_pipeline(
    spec: BriefingSpec,
    *,
    image_model: str,
    tts_model: str,
    music_model: str,
    include_video: bool,
    video_model: str | None,
) -> Pipeline:
    """Stage B: 3x image + 3x narration (max_concurrency=3) + 1x music + opt video.

    `preflight=False` is deliberate: genblaze-core 0.3.0 turned preflight on
    by default, and a single retired slug would block the whole fan-out —
    see docs/features/video-best-effort.md for the rationale.
    """
    api_key = settings.nvidia_api_key
    out_dir = _artifact_dir()
    p = _attach_observability(Pipeline(PIPELINE_NAME, max_concurrency=3, preflight=False))
    for ch in spec.takeaways:  # 3x illustration
        # FLUX.1 Schnell on NIM is guidance-distilled (must run at cfg_scale=0)
        # and rejects `aspect_ratio` outright — it produces 1024×1024 only. We
        # rely on the model's defaults; the UI crops via `aspect-video object-
        # cover`. Override `image_model` to flux.1-dev or sd-3.5-* if you need
        # cfg_scale / aspect_ratio knobs.
        p = p.step(
            NvidiaImageProvider(api_key=api_key, output_dir=out_dir),
            model=image_model, modality=Modality.IMAGE,
            prompt=ch.illustration_prompt,
        )
    for ch in spec.takeaways:  # 3x narration
        p = p.step(
            NvidiaAudioProvider(api_key=api_key, output_dir=out_dir),
            model=tts_model, modality=Modality.AUDIO,
            prompt=ch.narration,
        )
    p = p.step(  # 1x mood music
        NvidiaAudioProvider(api_key=api_key, output_dir=out_dir),
        model=music_model, modality=Modality.AUDIO,
        prompt=spec.music_prompt,
    )
    if include_video and video_model:  # opt-in Cosmos tail
        # Cosmos accepts a fixed aspect/duration on its NIM endpoint — we don't
        # pass `aspect_ratio` here either, mirroring the image step.
        p = p.step(
            NvidiaVideoProvider(api_key=api_key, output_dir=out_dir),
            model=video_model, modality=Modality.VIDEO,
            prompt=spec.recommended_video_prompt or spec.takeaways[0].illustration_prompt,
        )
    return p
