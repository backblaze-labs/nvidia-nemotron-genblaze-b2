# AGENTS.md — instructions for AI assistants editing this repo

Read this before touching anything. The whole point of the sample is
that **storage and orchestration are delegated to Genblaze**; if you
break that delegation, you defeat the demo.

## Hard rules

1. **No `import boto3`, no `import botocore`.** Anywhere. The
   `tests/test_structure.py` AST walk will fail your PR. Storage goes
   through `genblaze-s3` exclusively. If you need a pre-signed URL,
   call `S3StorageBackend.get_url(key, expires_in=...)` from inside
   `app/repo/`.
2. **All `genblaze_*` imports live in `services/api/app/repo/`.**
   Handlers see Genblaze types only via the Pydantic models returned
   from the repo layer. The allowlisted exceptions in `app/main.py`
   are `genblaze_core.exceptions` (PipelineError, ProviderError,
   StorageError, GenblazeError — surfaced to clients via the typed
   error envelope), `genblaze_core.models.enums` (ProviderErrorCode
   for the AUTH_FAILURE catch), and `genblaze_core.models.asset`
   (Asset reconstructed from `BriefingRequest` for the
   `external_inputs=` argument).
3. **Don't wrap Genblaze types in custom DTOs.** `Run`, `Step`,
   `Asset`, `Manifest` already are Pydantic models. Mirroring them
   doubles maintenance and breaks the "Genblaze is the contract"
   ethos. The only custom DTOs in the sample are the inbound
   `BriefingRequest` / `UploadResponse`, and the structured chat
   output `BriefingSpec` — which doubles as the chat step's
   `response_format=`.
4. **Pipeline slug = provenance.** Always
   `Pipeline("nvidia-nemotron-genblaze-b2", ...)`. The slug is what
   NVIDIA audit logs and B2 manifests carry forward; renaming it
   breaks the trail.
5. **`.env.example` uses the parent-standard names.** Don't introduce
   `B2_S3_*` or `AWS_*` aliases. `S3StorageBackend.for_backblaze()` is
   invoked with explicit `key_id=` and `app_key=` kwargs so the
   library's `B2_APP_KEY` env fallback can never fire — keep it that
   way.

## Where to make changes

- **Want a new model knob?** Add it to `Settings` in `app/config.py`
  and pipe it through `_resolve_models()` in `app/main.py`. Don't
  hard-code model ids in `repo/pipelines.py`.
- **Want a new pipeline shape?** Edit `repo/pipelines.py`. A
  structural test caps the file size — keep it readable in one
  sitting.
- **Want a new modality?** Add a new `.step(NvidiaXProvider, ...)`
  call. Don't hand-roll a provider unless you have a non-NVIDIA
  reason — `NvidiaChatProvider`, `NvidiaImageProvider`,
  `NvidiaAudioProvider`, `NvidiaVideoProvider` cover the four free
  surfaces.
- **Want to attach a user-uploaded asset to the chat step?** That's
  what `external_inputs=[asset]` on `Pipeline.step()` is for. The
  reserved kwarg is **`external_inputs=`**, not `inputs=` / `input=`
  (the latter raise loudly to prevent silent canonical-hash drift).
  Always populate `Asset.sha256` — without it the cache falls back
  to URL, which rotates for presigned URLs and breaks dedup +
  drifts the manifest hash.
- **Want to change the UI?** Stay inside `apps/web/src/`. The visual
  tokens (`globals.css`, `lib/utils.ts`, `components/ui/*`) were
  copied from `vibe-coding-starter-kit`; don't reach back into that
  kit at runtime.

## How to run the tests

```
cd services/api && uv run pytest && uv run ruff check app/ tests/
cd apps/web && pnpm lint
```

If a structural guard fails it's because new code reached for `boto3`
or imported `genblaze_*` outside `repo/`. Move the offending code into
`repo/` instead of relaxing the guard.
