# Uploads

The sample's entry point. Users drop an asset into the `<UploadForm>`;
`POST /uploads` stages it to B2, content-addresses it by SHA-256, and
returns the durable URL plus the hash for the run request to round-trip.

## Wire shape

```
POST /uploads
Content-Type: multipart/form-data; boundary=...

file=<binary>
media_type=<optional MIME override>
```

Response:

```json
{
  "durable_url": "https://<b2-host>/<bucket>/nemotron/uploads/<sha256>/<filename>",
  "sha256": "<sha256>",
  "media_type": "image/png",
  "size_bytes": 142_341
}
```

## Why content-addressed keys

Storage key is `nemotron/uploads/<sha256>/<filename>`. Two consequences:

1. **Dedup for free.** Re-uploading the same file from a different
   user / browser / day lands on the same key, so B2 stores one copy.
2. **Stable cache key.** `step_cache_key` in `genblaze-core` keys on
   `Asset.sha256 or Asset.url`. Because the URL embeds the same hash
   we computed, the cache hits whether the caller sends the URL or
   the explicit `sha256` field. Robust against future presigned-URL
   migrations.

## What's accepted

`image/* | audio/* | video/*`. PDFs return 415 because
`NvidiaChatProvider` explicitly raises `INVALID_INPUT` on
`application/pdf` — Nemotron 3 Nano Omni processes documents as
multi-page image sequences upstream.

## What's rejected

| Status | Reason                                                          |
| ------ | --------------------------------------------------------------- |
| 413    | Body exceeded `MAX_UPLOAD_BYTES` (default 25 MiB).              |
| 415    | Unsupported MIME — caller saw the supported-prefixes hint.      |
| 502    | B2 backend rejected the put (rare; surfaces via `genblaze-s3`). |

## Production hardening (deliberately out of scope here)

The sample uploads stream synchronously through FastAPI. For a real
deployment:

- Use a presigned-PUT-from-browser flow so the API service never sees
  the bytes. `S3StorageBackend.get_url(key, expires_in=...)` already
  exists in `genblaze-s3`; the API just needs an endpoint that
  reserves a key and returns the presigned URL plus the eventual
  durable URL.
- Bump or remove the size cap; deal with multi-GB videos via
  `S3StorageBackend.create_multipart_upload()`.
- Run a virus / malware scanner before allowing the briefing run.
- Authenticate the upload route (the sample doesn't auth anything).
