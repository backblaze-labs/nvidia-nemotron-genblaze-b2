# Infra notes

The sample needs one B2 bucket. `genblaze-s3` handles lifecycle and
manifest writing; the only manual setup is creating the bucket and an
Application Key scoped to it.

## 1. Create the bucket

In the B2 web UI:

- **Bucket name**: anything globally unique (e.g. `nemotron-<your-handle>`).
- **Files in bucket are**: `Private` (recommended). Public buckets
  also work but expose every generated asset URL on the open
  internet.
- **Default encryption**: SSE-B2 (free).
- **Object lock**: optional. `ObjectStorageSink` supports a
  `manifest_lock=` config if you want immutable manifests.

The bucket region (`us-west-004`, `eu-central-003`, `us-east-005`,
etc.) is what goes into `B2_REGION`. The matching endpoint goes into
`B2_ENDPOINT` — `https://s3.<region>.backblazeb2.com`.

## 2. Create the Application Key

- Scope: bucket above only.
- Capabilities: `listFiles`, `readFiles`, `writeFiles`, `listBuckets`,
  `readBucketEncryption`, plus `writeBucketLifecycle` so
  `auto_lifecycle=True` can call `put_bucket_lifecycle_configuration`.
  `deleteFiles` is **not** needed for the default sink configuration —
  `genblaze-s3`'s pipelined-CAS code path is the only one that calls
  `delete_object`, and we don't enable it. B2's lifecycle rules expire
  versions on their own without per-object delete calls.
- Save the `keyID` into `B2_KEY_ID` and the `applicationKey` into
  `B2_APPLICATION_KEY` (parent-standard names — do not rename).

## 3. Lifecycle (auto)

`S3StorageBackend.for_backblaze(..., auto_lifecycle=True)` (the
sample's default) sets up B2's "keep only last version, delete after
7 days" lifecycle rule on first write. Tweak by passing a different
lifecycle config or by setting it manually in the B2 UI.

## 4. CORS (only if you serve assets directly to the browser)

The sample's UI loads chapter assets from B2 via `<img src={url}>` /
`<audio src={url}>`. For a private bucket served via presigned URLs,
no CORS rules are needed. For a public bucket, add a CORS rule that
allows `GET` from your dev origin (`http://localhost:3000`) and your
production origin.

`b2-doctor` flags `allowedOrigins: ["*"]` as a warning — use specific
origins.

## 5. Optional: OpenTelemetry

Set `OTEL_ENDPOINT=http://localhost:4318` (or any OTLP-compatible
collector) to ship pipeline traces. The sample wires
`OTelTracer(endpoint=...)` only when this env var is set, so leaving
it empty in dev costs nothing.
