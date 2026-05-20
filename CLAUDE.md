# CLAUDE.md — sample-local instructions

This file is the source of truth for AI assistants working inside
`nvidia-nemotron-genblaze-b2`. The parent repo's `CLAUDE.md` covers
B2-wide standards; this file restates the Genblaze ethos that's
specific to this sample.

## Read these in order

1. [AGENTS.md](AGENTS.md) — the hard rules
2. [ARCHITECTURE.md](ARCHITECTURE.md) — layer diagram and rationale
3. [docs/app-workflows.md](docs/app-workflows.md) — request lifecycle
4. The relevant `docs/features/<feature>.md` if you're touching one
   modality

## Reflexes

- A new modality? `app/repo/pipelines.py`, one `.step()` call.
- A new model knob? `Settings` in `app/config.py`, then surface it
  through `_resolve_models()` in `app/main.py`.
- A new endpoint? `app/main.py`. Returns Genblaze types directly.
- Reaching for `boto3`? Stop. Use `S3StorageBackend.get_url()` from
  inside `app/repo/`.
- Wiring a user-uploaded asset to the chat step? Use
  `external_inputs=[asset]` on `Pipeline.step()` (NOT `inputs=` —
  0.2.7 raises loudly). Always populate `Asset.sha256`.

## Tests

```
cd services/api && uv run pytest
```

Pre-PR sanity:

```
cd services/api && uv run pytest && uv run ruff check app/
cd apps/web && pnpm lint
```
