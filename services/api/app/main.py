"""FastAPI surface — handlers return Genblaze Pydantic models directly.

Genblaze imports are confined to `app.repo.*`. This module is allowed to
reference `genblaze_core.exceptions` because the exception types ARE the
contract we surface to the client (and to discriminate AUTH_FAILURE from
other failures via `exc.result.run.steps[i].error_code`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from genblaze_core.exceptions import GenblazeError, PipelineError, ProviderError, StorageError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.providers import DiscoveryStatus, DiscoverySupport

from app.config import settings
from app.repo.pipelines import (
    PREFIX,
    backend,
    build_briefing_spec_pipeline,
    build_media_pipeline,
    nvidia_providers,
    sink,
)
from app.types.api import BriefingRequest, BriefingSpec, UploadResponse

log = logging.getLogger("nemotron")

# Whitelist of input modalities NvidiaChatProvider accepts. PDFs are
# explicitly rejected by the provider (must be rasterized to images first
# upstream — see docs/features/uploads.md). Server-side guard here gives
# a friendlier error than the upstream provider's INVALID_INPUT.
SUPPORTED_INPUT_MIME_PREFIXES = ("image/", "audio/", "video/")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Surface bad credentials at boot, not on the first 30s-timeout request.

    Both NVIDIA and B2 preflights are warn-not-fatal: a missing key is more
    useful as a runtime error than a crashed process, and CI / local-dev
    placeholders ("test"/"nvapi-test") will fail preflight without blocking
    iteration on the unrelated parts of the app.
    """
    for modality, provider in nvidia_providers().items():
        try:
            provider.preflight_auth(timeout=5.0)
            log.info("preflight ok: nvidia-%s", modality)
        except ProviderError as exc:
            log.warning("preflight auth failure: nvidia-%s — %s", modality, exc)
        except Exception as exc:  # noqa: BLE001 — keep the API up on transport hiccups
            log.warning("preflight transport error: nvidia-%s — %s", modality, exc)
    # Realize the B2 backend singleton once. genblaze-s3 0.3.0
    # `for_backblaze(preflight=True)` (default) does HeadBucket eagerly,
    # so this call is the boot preflight — a misconfigured key/bucket
    # surfaces here, not on the first user upload.
    try:
        backend()
        log.info("preflight ok: b2-bucket=%s", settings.b2_bucket_name)
    except StorageError as exc:
        log.warning("preflight storage failure: %s", exc)
    except Exception as exc:  # noqa: BLE001 — keep the API up on transport hiccups
        log.warning("preflight storage transport error: %s", exc)
    yield


app = FastAPI(title="nvidia-nemotron-genblaze-b2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3737"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(GenblazeError)
async def _genblaze_error_handler(_: Request, exc: GenblazeError) -> JSONResponse:
    """Return a typed 502 envelope for any GenblazeError that escapes a route.

    The route bodies in `run_briefing` already catch `PipelineError` and
    `ProviderError` to express AUTH_FAILURE retry logic; that inner handling
    takes precedence (the `except` blocks run before this handler ever sees
    the exception). What reaches here is the long tail: `StorageError` from
    a B2 misconfig surfacing on `/uploads`, `SinkError` from a manifest
    write, etc. Without this handler those bubble up as bare 500s with
    "Internal Server Error" — opaque to API consumers.

    `StorageError` carries typed fields (genblaze-s3 0.3.x):
    `error_code`, `status_code`, `is_retriable`, `operation`, `request_id`.
    We surface them when present so observability tools can classify
    upstream failures without parsing the message string.
    """
    body: dict[str, Any] = {"code": type(exc).__name__, "msg": str(exc)}
    if isinstance(exc, StorageError):
        # Storage classification fields are populated by the
        # `classify_botocore_error` wrapper in genblaze-s3 0.3.0; emit only
        # the ones the caller set so older error sites don't leak null fields.
        if exc.error_code is not None:
            body["error_code"] = (
                exc.error_code.value if hasattr(exc.error_code, "value") else str(exc.error_code)
            )
        for field in ("status_code", "operation", "request_id", "is_retriable"):
            value = getattr(exc, field, None)
            if value is not None:
                body[field] = value
    return JSONResponse(status_code=502, content=body)


def _resolve_models(req: BriefingRequest) -> dict[str, str]:
    """Apply per-request overrides on top of the env-configured defaults."""
    return {
        "chat_model": req.chat_model or settings.nemotron_chat_model,
        "image_model": req.image_model or settings.nemotron_image_model,
        "tts_model": settings.nemotron_tts_model,
        "music_model": settings.nemotron_music_model,
        "video_model": req.video_model or settings.nemotron_video_model,
    }


def _serialize_cost(cost: Decimal | None) -> str | None:
    """Pipeline.estimated_cost() returns Decimal | None. JSON-safe stringify."""
    return str(cost) if cost is not None else None


def _input_asset(req: BriefingRequest) -> Asset:
    """Reconstruct the Asset for the chat step's `external_inputs=`.

    `media_type` is required (NvidiaChatProvider dispatches on it). `sha256`
    is strongly recommended — without it `step_cache_key` falls back to the
    URL, which rotates for presigned URLs and silently breaks cache + drifts
    the manifest canonical hash. `Pipeline.step(external_inputs=...)` warns
    loudly when sha256 is missing.
    """
    if not req.input_asset_media_type:
        raise HTTPException(
            status_code=400,
            detail="input_asset_media_type is required (NvidiaChatProvider dispatches on it)",
        )
    return Asset(
        url=req.input_asset_url,
        media_type=req.input_asset_media_type,
        sha256=req.input_asset_sha256,
    )


def _run_briefing(req: BriefingRequest, *, allow_video: bool) -> dict[str, Any]:
    """Execute Stage A then Stage B and return a JSON-ready response payload.

    `raise_on_failure=True` on Stage A turns any step failure into a
    `PipelineError` carrying the partial `PipelineResult`, so we don't have
    to inspect `run.status` ourselves. Stage B uses `raise_on_failure=False`
    + `Pipeline(preflight=False)` so individual step drift surfaces inline.
    """
    models = _resolve_models(req)
    spec_pipe = build_briefing_spec_pipeline(
        input_asset=_input_asset(req),
        instruction=req.instruction,
        chat_model=models["chat_model"],
    )
    spec_result = spec_pipe.run(sink=sink(), timeout=300, raise_on_failure=True)
    spec_step = spec_result.run.steps[0]
    # NvidiaChatProvider stashes the raw text in step.assets[0].metadata['text'].
    # response_format=BriefingSpec enforced JSON schema upstream, so parsing is
    # guaranteed to succeed for any model/spec combination NIM accepts.
    raw_text = spec_step.assets[0].metadata.get("text", "{}") if spec_step.assets else "{}"
    spec = BriefingSpec.model_validate_json(raw_text)

    media_pipe = build_media_pipeline(
        spec,
        image_model=models["image_model"],
        tts_model=models["tts_model"],
        music_model=models["music_model"],
        include_video=req.include_video and allow_video,
        video_model=models["video_model"],
    )
    # Stage B is intentionally non-fatal at the pipeline level: NIM model ids
    # drift (e.g., a TTS endpoint going 404) shouldn't sink the whole briefing
    # when image + music succeeded. Each step's status lives on the returned
    # Run; the UI surfaces failures inline. Stage A still uses
    # raise_on_failure=True because there's nothing to fan out from without
    # the parsed BriefingSpec.
    media_result = media_pipe.run(sink=sink(), timeout=600, raise_on_failure=False)
    return {
        "briefing": spec.model_dump(mode="json"),
        "spec_run": spec_result.run.model_dump(mode="json"),
        "media_run": media_result.run.model_dump(mode="json"),
        # The AUTH_FAILURE branch in `run_briefing` overwrites this to
        # "auth_required"; the happy path leaves it None.
        "video_skipped": None,
        # `Pipeline.estimated_cost()` returns None for slugs without a
        # registered pricing strategy (the NVIDIA free tier case). The field
        # is always present so the UI can render "varies" without a key check.
        "estimated_cost_usd": {
            "spec": _serialize_cost(spec_pipe.estimated_cost()),
            "media": _serialize_cost(media_pipe.estimated_cost()),
        },
    }


def _pipeline_error_code(exc: PipelineError) -> ProviderErrorCode | None:
    """Reach into `exc.result.run.steps[failed_index].error_code` if available.

    `PipelineError.failed_step_error` is the message string; the typed
    `error_code` we need to discriminate `AUTH_FAILURE` lives on the
    underlying Step.
    """
    if exc.result is None or exc.failed_step_index is None:
        return None
    steps = exc.result.run.steps
    if 0 <= exc.failed_step_index < len(steps):
        return steps[exc.failed_step_index].error_code
    return None


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "pipeline": "nvidia-nemotron-genblaze-b2"}


@app.get("/models")
def models() -> dict[str, list[dict[str, Any]]]:
    """Per-modality model catalog — drives the UI model picker.

    genblaze-core 0.3.0 stopped shipping per-slug spec dictionaries, so
    `provider.list_models()` returns only user-registered specs (empty here).
    The two new surfaces:
      - NATIVE providers (chat): `discover_models()` queries the upstream
        `/v1/models` endpoint. Result is cached single-flight, 1-hour TTL.
      - PARTIAL/NONE providers (image/audio/video): each `ModelFamily`
        carries an `example_slugs` tuple — the curated short-list the
        connector ships for that modality.

    Discovery is best-effort: on transport failure or unsupported tier we
    fall back to family `example_slugs` so the picker is never empty.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for modality, provider in nvidia_providers().items():
        slugs: set[str] = set()
        if provider.discovery_support is DiscoverySupport.NATIVE:
            try:
                result = provider.discover_models()
                if result.status is DiscoveryStatus.OK:
                    slugs = set(result.slugs)
            except ProviderError as exc:
                # Auth / config — operator-actionable. WARN so a misprovisioned
                # NVIDIA_API_KEY doesn't masquerade as a healthy (empty) picker.
                log.warning("discover_models(%s) provider error: %s", modality, exc)
            except Exception as exc:  # noqa: BLE001 — transient transport: degrade to families
                log.debug("discover_models(%s) transport error: %s", modality, exc)
        if not slugs:
            # PARTIAL/NONE providers (and NATIVE fallback on discovery failure)
            # surface the curated short-list each ModelFamily ships.
            for family in provider.models.families:
                slugs.update(family.example_slugs)
        out[modality] = [{"id": s, "modality": modality} for s in sorted(slugs)]
    return out


@app.post("/uploads", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    media_type: str | None = Form(default=None),
) -> UploadResponse:
    """Stage a user-supplied asset to B2 and return durable URL + sha256.

    The returned sha256 is the load-bearing field for run-side caching and
    manifest canonical hashing. Callers MUST round-trip it via
    `BriefingRequest.input_asset_sha256` so `step_cache_key`'s
    `a.sha256 or a.url` branch picks the stable hash, not the rotating
    presigned URL — otherwise every retry is a cache miss.
    """
    body = await file.read()
    if len(body) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds limit ({len(body)} > {settings.max_upload_bytes} bytes)",
        )

    mt = (media_type or file.content_type
          or mimetypes.guess_type(file.filename or "")[0]
          or "application/octet-stream")
    if not any(mt.startswith(p) for p in SUPPORTED_INPUT_MIME_PREFIXES):
        raise HTTPException(
            status_code=415,
            detail=(
                f"unsupported media type {mt!r}. NvidiaChatProvider accepts "
                "image/*, audio/*, video/*. PDFs must be rasterized to images "
                "first — see docs/features/uploads.md."
            ),
        )

    digest = hashlib.sha256(body).hexdigest()
    # Content-addressed key — same upload from a different user dedupes for free.
    safe_name = (file.filename or "asset").replace("/", "_")
    key = f"{PREFIX}/uploads/{digest}/{safe_name}"
    backend().put(key, body, content_type=mt)
    return UploadResponse(
        durable_url=backend().get_durable_url(key),
        sha256=digest,
        media_type=mt,
        size_bytes=len(body),
    )


@app.post("/runs")
def run_briefing(req: BriefingRequest) -> dict[str, Any]:
    """One-shot run. Returns when both pipelines finish.

    AUTH_FAILURE handling reads through `PipelineError` — the contract
    carries the partial `PipelineResult` so we still recover the failed
    step's typed `error_code`. The `ProviderError` catch is the defensive
    fallback for paths where the failure surfaces directly (e.g., Stage A
    preflight `MODEL_ERROR` from genblaze-core 0.3.0's auto-validation).
    """
    try:
        return _run_briefing(req, allow_video=True)
    except PipelineError as e:
        code = _pipeline_error_code(e)
        if code == ProviderErrorCode.AUTH_FAILURE and req.include_video:
            payload = _run_briefing(req, allow_video=False)
            payload["video_skipped"] = "auth_required"
            return payload
        raise HTTPException(status_code=502, detail={
            "code": code.value if code else "PIPELINE_FAILURE",
            "msg": e.failed_step_error or str(e),
            "failed_step_index": e.failed_step_index,
        }) from e
    except ProviderError as e:  # legacy fallback — kept defensively
        if e.error_code == ProviderErrorCode.AUTH_FAILURE and req.include_video:
            payload = _run_briefing(req, allow_video=False)
            payload["video_skipped"] = "auth_required"
            return payload
        raise HTTPException(
            status_code=502,
            detail={"code": e.error_code.value if e.error_code else "PROVIDER_ERROR", "msg": str(e)},
        ) from e


def _to_sse(events: Iterator[Any]) -> Iterator[bytes]:
    """Wrap Genblaze stream events in the text/event-stream wire format."""
    for ev in events:
        body = ev.model_dump(mode="json") if hasattr(ev, "model_dump") else ev
        yield f"event: {type(ev).__name__}\ndata: {json.dumps(body)}\n\n".encode("utf-8")


def _sse_event(name: str, payload: dict[str, Any]) -> bytes:
    """Emit a custom SSE event with a JSON-serializable payload."""
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


@app.post("/runs/stream")
def stream_briefing(req: BriefingRequest) -> StreamingResponse:
    """SSE: live-stream Stage A then Stage B events, then a terminal `result`.

    Wire shape (consumed by the UI's RunTimeline + final-result handler):
      - Per-step: `event: <PipelineStartedEvent|StepStartedEvent|...>` with the
        Genblaze event class name, and `data: {type:"step.started",...}`. The
        type discriminator on `data` is the source of truth for the consumer;
        the `event:` line is a convenience for EventSource users.
      - On Stage-A failure: `event: error` with `{code,msg}` and the stream
        ends. Consumer renders the failure inline.
      - On success: `event: result` with the same payload `/runs` returns
        (briefing, spec_run, media_run, video_skipped, estimated_cost_usd).
        Lets the UI render the final BriefingSpec without a follow-up fetch.

    Stage A still uses `raise_on_failure=True` (no fan-out without spec).
    Stage B uses `raise_on_failure=False` so a single bad model id (e.g., a
    drifted TTS slug) doesn't blank the image and music output.
    """
    models = _resolve_models(req)

    def gen() -> Iterator[bytes]:
        # Wrap the whole body: once StreamingResponse starts writing, any
        # uncaught exception aborts the connection mid-flight (no `event:
        # error` reaches the client, and the @app.exception_handler can't
        # rewrite a response whose headers are already on the wire). Catch
        # GenblazeError here so transient infra failures (StorageError on
        # bucket misconfig, SinkError on manifest write, etc.) surface as a
        # typed terminal event the UI can render.
        try:
            spec_pipe = build_briefing_spec_pipeline(
                input_asset=_input_asset(req),
                instruction=req.instruction,
                chat_model=models["chat_model"],
            )
            spec_result = None
            try:
                for ev in spec_pipe.stream(sink=sink(), timeout=300, raise_on_failure=True):
                    yield from _to_sse([ev])
                    if hasattr(ev, "result"):
                        spec_result = ev.result
            except PipelineError as e:
                code = _pipeline_error_code(e)
                yield _sse_event("error", {
                    "code": code.value if code else "BRIEFING_STAGE_FAILED",
                    "msg": e.failed_step_error or str(e),
                })
                return
            if spec_result is None:
                yield _sse_event("error", {
                    "code": "BRIEFING_STAGE_EMPTY",
                    "msg": "chat-stage produced no result",
                })
                return
            # PipelineResult.run.steps — same shape the non-streaming path
            # consumes at `_run_briefing` above. Going through `.steps` directly
            # raises AttributeError because PipelineResult holds the RunRecord
            # under `.run`.
            raw_text = spec_result.run.steps[0].assets[0].metadata.get("text", "{}")
            spec = BriefingSpec.model_validate_json(raw_text)

            media_pipe = build_media_pipeline(
                spec,
                image_model=models["image_model"],
                tts_model=models["tts_model"],
                music_model=models["music_model"],
                include_video=req.include_video,
                video_model=models["video_model"],
            )
            media_result = None
            for ev in media_pipe.stream(sink=sink(), timeout=600, raise_on_failure=False):
                yield from _to_sse([ev])
                if hasattr(ev, "result"):
                    media_result = ev.result

            # Terminal result event — same shape as POST /runs response so
            # the UI can flip from "live progress" view to "final briefing"
            # without a follow-up fetch. Mirror the non-streaming path:
            # serialize `result.run`, not the PipelineResult wrapper.
            yield _sse_event("result", {
                "briefing": spec.model_dump(mode="json"),
                "spec_run": spec_result.run.model_dump(mode="json"),
                "media_run": media_result.run.model_dump(mode="json") if media_result else None,
                "video_skipped": None,
                "estimated_cost_usd": {
                    "spec": _serialize_cost(spec_pipe.estimated_cost()),
                    "media": _serialize_cost(media_pipe.estimated_cost()),
                },
            })
        except GenblazeError as exc:
            yield _sse_event("error", {
                "code": type(exc).__name__,
                "msg": str(exc),
            })

    return StreamingResponse(gen(), media_type="text/event-stream")
