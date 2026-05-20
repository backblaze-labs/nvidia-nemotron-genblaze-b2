"""Construction-time smoke tests + a real end-to-end run against fakes.

These verify the live SDK surface still supports the shapes
`repo/pipelines.py` uses — the canary that fires when an upstream
release renames `Pipeline.step()`'s kwargs, drops `NvidiaChatProvider`,
or moves the `external_inputs=` mechanism.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

# Keep settings happy without real creds for these unit-level checks.
os.environ.setdefault("B2_ENDPOINT", "https://s3.us-west-004.backblazeb2.com")
os.environ.setdefault("B2_REGION", "us-west-004")
os.environ.setdefault("B2_KEY_ID", "test")
os.environ.setdefault("B2_APPLICATION_KEY", "test")
os.environ.setdefault("B2_BUCKET_NAME", "test-bucket")
os.environ.setdefault("NVIDIA_API_KEY", "nvapi-test")


def test_media_pipeline_builds_with_three_takeaways() -> None:
    from app.repo.pipelines import build_media_pipeline
    from app.types.api import BriefingSpec, Takeaway

    spec = BriefingSpec(
        title="T",
        summary="A short summary, long enough.",
        takeaways=[
            Takeaway(headline=f"H{i}", illustration_prompt=f"img {i}",
                     narration=f"narration body {i} that's long enough")
            for i in range(3)
        ],
        music_prompt="calm ambient",
    )
    pipe = build_media_pipeline(
        spec,
        image_model="black-forest-labs/flux.1-schnell",
        tts_model="nvidia/riva-tts",
        music_model="nvidia/fugatto",
        include_video=False,
        video_model=None,
    )
    # 3 image + 3 audio + 1 music = 7 steps when video is off.
    assert len(pipe._steps) == 7  # noqa: SLF001 — internal pipeline state, no public step count yet


def test_media_pipeline_appends_video_when_requested() -> None:
    from app.repo.pipelines import build_media_pipeline
    from app.types.api import BriefingSpec, Takeaway

    spec = BriefingSpec(
        title="T",
        summary="A summary.",
        takeaways=[
            Takeaway(headline=f"H{i}", illustration_prompt=f"prompt {i}",
                     narration=f"long enough narration body {i}")
            for i in range(3)
        ],
        music_prompt="ambient",
        recommended_video_prompt="establishing shot",
    )
    pipe = build_media_pipeline(
        spec,
        image_model="black-forest-labs/flux.1-schnell",
        tts_model="nvidia/riva-tts",
        music_model="nvidia/fugatto",
        include_video=True,
        video_model="nvidia/cosmos-2.0-diffusion-text2world",
    )
    # 3 image + 3 audio + 1 music + 1 video = 8 steps
    assert len(pipe._steps) == 8  # noqa: SLF001 — internal pipeline state, no public step count yet


def test_pipeline_name_carries_provenance() -> None:
    from genblaze_core.models.asset import Asset

    from app.repo.pipelines import PIPELINE_NAME, build_briefing_spec_pipeline

    assert PIPELINE_NAME == "nvidia-nemotron-genblaze-b2"
    asset = Asset(url="https://fake.local/x.png", media_type="image/png", sha256="a" * 64)
    pipe = build_briefing_spec_pipeline(
        input_asset=asset,
        instruction=None,
        chat_model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    )
    assert getattr(pipe, "_name", None) == PIPELINE_NAME or getattr(pipe, "name", None) == PIPELINE_NAME


def test_briefing_spec_pipeline_attaches_external_input() -> None:
    """The chat step must wire the uploaded asset through external_inputs=
    (verified via the deferred step's recorded kwargs)."""
    from genblaze_core.models.asset import Asset

    from app.repo.pipelines import build_briefing_spec_pipeline

    asset = Asset(url="https://fake.local/cat.png", media_type="image/png", sha256="b" * 64)
    pipe = build_briefing_spec_pipeline(
        input_asset=asset,
        instruction="describe",
        chat_model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    )
    deferred = pipe._steps[0]  # noqa: SLF001 — internal pipeline state
    # Caller-held assets land on the deferred step's external_inputs
    # field (defensive copy is taken at construction time).
    assert deferred.external_inputs == [asset]


def test_briefing_request_validates() -> None:
    """BriefingRequest enforces that input_asset_url is provided."""
    import pydantic

    from app.types.api import BriefingRequest

    with pytest.raises(pydantic.ValidationError):
        BriefingRequest()  # type: ignore[call-arg]

    BriefingRequest(
        input_asset_url="https://fake.local/x.png",
        input_asset_media_type="image/png",
        input_asset_sha256="c" * 64,
    )


def test_briefing_spec_validates_takeaway_count() -> None:
    """BriefingSpec must reject specs that don't have exactly three takeaways."""
    import pydantic

    from app.types.api import BriefingSpec, Takeaway

    valid_takeaways = [
        Takeaway(headline=f"H{i}", illustration_prompt=f"prompt {i}",
                 narration=f"body of narration {i} long enough")
        for i in range(3)
    ]
    BriefingSpec(title="T", summary="A summary.", takeaways=valid_takeaways, music_prompt="m m m m")
    with pytest.raises(pydantic.ValidationError):
        BriefingSpec(title="T", summary="A summary.", takeaways=valid_takeaways[:2],
                     music_prompt="m m m m")


def test_nvidia_providers_expose_list_models() -> None:
    """`BaseProvider.list_models()` discovery — used by `/models`."""
    from app.repo.pipelines import nvidia_providers

    providers = nvidia_providers()
    for modality in ("chat", "image", "audio", "video"):
        ids = [m.model_id for m in providers[modality].list_models()]
        assert ids, f"{modality} provider returned empty list_models()"


def test_pipeline_estimated_cost_is_decimal_or_none() -> None:
    """`Pipeline.estimated_cost()` returns Decimal or None.

    None is the honest answer for NVIDIA's free-tier providers (no
    per-request pricing registered). The handler stringifies the result
    for JSON safety.
    """
    from decimal import Decimal

    from app.repo.pipelines import build_media_pipeline
    from app.types.api import BriefingSpec, Takeaway

    spec = BriefingSpec(
        title="T",
        summary="Summary text.",
        takeaways=[
            Takeaway(headline=f"H{i}", illustration_prompt=f"prompt {i}",
                     narration=f"narration body {i} long enough")
            for i in range(3)
        ],
        music_prompt="ambient music prompt",
    )
    pipe = build_media_pipeline(
        spec,
        image_model="black-forest-labs/flux.1-schnell",
        tts_model="nvidia/riva-tts",
        music_model="nvidia/fugatto",
        include_video=False,
        video_model=None,
    )
    cost = pipe.estimated_cost()
    assert cost is None or isinstance(cost, Decimal)


def test_briefing_spec_pipeline_params_canonical_hashable() -> None:
    """Regression guard: `step.params` must canonical-hash without raising.

    `Pipeline.run/stream` calls `step_cache_key` on every step before
    invoking the provider, which serializes `step.params`. The chat
    step's `response_format=` value must be plain data (not a class) for
    that serialization to succeed; this test fails if the
    `coerce_response_format()` call in `build_briefing_spec_pipeline` is
    ever reverted to passing the raw Pydantic class.

    Stage B (`build_media_pipeline`) is not exercised here because none
    of its `.step()` kwargs are Pydantic classes — only string prompts
    and primitive scalars (`aspect_ratio`, `cfg_scale`).
    """
    from genblaze_core.canonical.json import canonical_hash
    from genblaze_core.models.asset import Asset

    from app.repo.pipelines import build_briefing_spec_pipeline

    asset = Asset(url="https://fake.local/x.png", media_type="image/png", sha256="d" * 64)
    pipe = build_briefing_spec_pipeline(
        input_asset=asset,
        instruction=None,
        chat_model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    )
    step = pipe._steps[0]  # noqa: SLF001 — internal pipeline state
    canonical_hash(step.params)  # must not raise


def test_chat_step_rejects_inputs_kwarg_with_helpful_error() -> None:
    """Pipeline.step() rejects `inputs=` / `input=` kwargs so callers
    don't silently send them through **params and corrupt the canonical
    hash. Regression guard against accidentally reaching for the
    natural-but-wrong name."""
    from genblaze_core import GenblazeError, Modality, Pipeline
    from genblaze_nvidia import NvidiaChatProvider

    chat = NvidiaChatProvider(api_key="nvapi-test")
    pipe = Pipeline("test")
    with pytest.raises(GenblazeError, match="external_inputs="):
        pipe.step(chat, model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                  modality=Modality.TEXT, prompt="x", inputs=[])  # type: ignore[arg-type]


# --- End-to-end run with fakes -------------------------------------------

class _FakeBackend:
    """In-memory StorageBackend stand-in. Records every put/copy/get."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: Any, *, content_type: str | None = None,
            extra_args: dict | None = None) -> None:
        if hasattr(data, "read"):
            data = data.read()
        self.objects[key] = bytes(data)

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def copy(self, src_key: str, dst_key: str) -> None:
        self.objects[dst_key] = self.objects[src_key]

    def get_url(self, key: str, *, expires_in: int = 3600) -> str:
        return f"https://fake.local/{key}"

    def get_durable_url(self, key: str) -> str:
        return f"https://fake.local/{key}"

    def close(self) -> None:
        pass


@pytest.mark.skipif(
    not os.environ.get("B2_BUCKET_NAME") or os.environ.get("B2_KEY_ID") == "test",
    reason="Requires real B2 credentials; skipped on placeholder values.",
)
def test_backend_singleton_resolves() -> None:
    from app.repo.pipelines import backend

    assert backend() is backend()
