# BTIDALPOOL v4 unified client contract

BTPL v4 is the only protocol exposed by the Rust listener. It provides
whole-file/check/query, resumable-upload, and normalized-query capabilities
through one endpoint.

## Transport and authentication

- Endpoint: `POST https://btidalpool.ddns.net:3568/v4`
- Content-Type: `application/x-btidalpool-cbor-zstd; version=4`
- Framing: the existing 9-byte `BTPL` header with byte 4 set to `0x04`,
  followed by zstd-compressed CBOR.
- TLS: pin the production Rust listener certificate.

Exchange a Google access token for a short-lived session:

```text
{
  "auth": {"scheme":"google", "access_token":"..."},
  "payload": {"cmd":"create_session"}
}
```

Every other command uses
`{"scheme":"session","token":"..."}`. Google access tokens and BTIDALPOOL
session tokens must remain separate from persisted upload state.

## Unified command set

V4 accepts these internally-tagged payloads:

| Command | Capability | Important fields |
| --- | --- | --- |
| `create_session` | session exchange | none |
| `upload` | whole-file upload | `btides_json` byte string, `use_test_db` |
| `check_hash` | canonical-hash check | `hash` |
| `legacy_query` | reconstructed-BTIDES query | `params`, `use_test_db` |
| `manifest` | resumable start/resume | `content_sha256`, `total_size`, `chunk_sha256`, `use_test_db` |
| `put_chunk` | resumable chunk | `upload_id`, `index`, `data` byte string |
| `status` | missing-chunk/receipt status | `upload_id` |
| `finalize` | atomic ingest/publish | `upload_id` |
| `native_query` | normalized query | `params`, `use_test_db` |

V4 uses distinct `legacy_query` and `native_query` names so response shape
and performance are explicit.

All resumable operations are idempotent. The server reuses existing durable
state written before the v4-only upgrade, deterministic upload IDs, chunk
acknowledgements, and receipts. A client upgrading during an upload can replay
the same manifest through v4 and continue from the server's current
`missing_chunks`. Never resend a chunk the server no longer reports missing.
Finalize is safe to replay if its response was lost.

## Responses

V4's `result` variants are:

- `session`
- `ok`
- `manifest`
- `chunk`
- `status`
- `finalized`
- `query_result` for legacy reconstructed BTIDES
- `native_query_result` for normalized database rows
- `err`

The v4 native-query response uses stable fields for lossless MySQL types:

```text
{
  "kind": "bytes",
  "bytes": "<CBOR byte string>",
  "signed": null,
  "unsigned": null,
  "float": null,
  "date": null,
  "time": null
}
```

Exactly the field named by `kind` is populated. Unsigned integers are decimal
text, preserving the complete MySQL `u64` range in signed-integer clients such
as Kotlin/JVM. Date and time use explicit component fields.
Table names, column names, row ordering, byte strings, row limits, and
truncation flags remain lossless.

## Errors, overload, and replay

V4 unifies the typed error space:

| Kind | HTTP | Replay behavior |
| --- | ---: | --- |
| `bad_request`, `schema_invalid` | 400 | Fix the request. |
| `unauthorized`, `session_expired` | 401 | Reacquire authentication/session separately. |
| `not_found` | 404 | Resubmit the persisted manifest for resumable uploads. |
| `conflict` | 409 | Upload the returned `missing_chunks` or reconcile the manifest. |
| `payload_too_large` | 413 | Reduce the logical upload size. |
| `hash_mismatch` | 422 | Re-read and re-hash local bytes. |
| `duplicate_upload`, `empty_result` | 400 | Terminal, command-specific result. |
| `rate_limited` | 429 | Wait for `Retry-After` plus positive jitter, then replay. |
| `server_busy` | 503 | Preserve state, wait for `Retry-After` plus positive jitter, then replay. |
| `internal` | 500 | Use bounded backoff where the operation is replay-safe. |

HTTP 429 and 503 include `Retry-After`. Clients should accept both positive
delta-seconds and HTTP-date, fall back to bounded exponential backoff when the
header is absent or malformed, and bound retries by attempt count and elapsed
time. Cancellation and app shutdown must stop the wait and request. A 401 is
never an overload retry.

## Limits

V4 uses operation-specific limits and admission-control weights:

- whole upload: weight 2
- legacy query: weight 4
- manifest/status: no expensive-work permit; chunk puts have their own cap
- finalize: weight 2
- native query: weight 1

The current resumable limit remains 10 MiB per logical upload and 2 MiB per
chunk. Send a larger collection as multiple resumable logical uploads.
