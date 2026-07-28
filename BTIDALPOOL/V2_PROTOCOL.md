# BTIDALPOOL v2 resumable-upload client contract

This is the implementation contract for Android and other BTIDALPOOL v2
clients. V2 is additive: the deployed whole-file BTPL v1 protocol remains at
`POST https://btidalpool.ddns.net:3568/`.

## Transport and framing

- Endpoint: `POST https://btidalpool.ddns.net:3568/v2`
- TLS: use the same pinned server certificate as v1.
- Content-Type: `application/x-btidalpool-cbor-zstd; version=2`
- Body: one CBOR value, zstd-compressed, inside the existing 9-byte BTPL
  header.
- BTPL header byte 4 is `0x02` for v2. Bytes 5-8 are the big-endian
  uncompressed CBOR length. Magic remains ASCII `BTPL`.
- Integer chunk indexes are zero-based.
- Hashes are lowercase hexadecimal SHA-256 of the exact bytes.

The CBOR data model below is shown in JSON-like notation for readability. The
actual encoding is CBOR, and chunk `data` is a CBOR byte string.

## Authentication

Exchange a valid Google access token once:

```text
{
  "auth": {"scheme": "google", "access_token": "<Google access token>"},
  "payload": {"cmd": "create_session"}
}
```

Success:

```text
{
  "result": "session",
  "token": "<signed BTIDALPOOL session token>",
  "expires_at_unix": 1785270000
}
```

The default session lifetime is 15 minutes. A client should keep the token
only in memory, proactively exchange again near expiry, and retry an operation
once after a `session_expired` response. V2 never sends or stores a Google
refresh token. All other operations require:

```text
{"scheme": "session", "token": "<BTIDALPOOL session token>"}
```

## Upload sequence

Choose a fixed chunking for one logical upload. One MiB chunks are recommended;
the final chunk may be shorter. Current server limits are:

- 10 MiB maximum logical upload
- 2 MiB maximum individual chunk
- 1,024 maximum chunks
- no empty chunks

Compute:

- `content_sha256`: SHA-256 of the exact complete file bytes
- `total_size`: complete file byte length
- `chunk_sha256`: ordered SHA-256 list, one element per chunk

Submit or replay the manifest:

```text
{
  "auth": {"scheme": "session", "token": "..."},
  "payload": {
    "cmd": "manifest",
    "content_sha256": "<64 lowercase hex>",
    "total_size": 1234567,
    "chunk_sha256": ["<chunk 0 hash>", "<chunk 1 hash>"],
    "use_test_db": false
  }
}
```

Response:

```text
{
  "result": "manifest",
  "upload_id": "<64 lowercase hex>",
  "missing_chunks": [0, 1],
  "receipt": null
}
```

`upload_id` is deterministic for the authenticated identity, database choice,
logical hash, size, and ordered chunk hashes. Replaying the identical manifest
returns the same ID and current missing list. If already finalized, `receipt`
is populated and `missing_chunks` is empty.

Upload missing chunks in any order and, if useful, concurrently:

```text
{
  "auth": {"scheme": "session", "token": "..."},
  "payload": {
    "cmd": "put_chunk",
    "upload_id": "...",
    "index": 1,
    "data": "<CBOR byte string>"
  }
}
```

Success:

```text
{
  "result": "chunk",
  "upload_id": "...",
  "index": 1,
  "already_present": false
}
```

The server hashes each chunk before storing it. Replaying the same valid chunk
returns `already_present: true`. A corrupt chunk is rejected and never replaces
a valid stored chunk.

Status is optional because manifest replay also supplies the missing list:

```text
{
  "auth": {"scheme": "session", "token": "..."},
  "payload": {"cmd": "status", "upload_id": "..."}
}
```

Finalize only after all missing chunks have been acknowledged:

```text
{
  "auth": {"scheme": "session", "token": "..."},
  "payload": {"cmd": "finalize", "upload_id": "..."}
}
```

The server re-reads every chunk in manifest order and validates every chunk
hash, exact total size, exact complete-file SHA-256, and JSON parseability. It
then ingests and atomically publishes the complete file into the legacy pool.
No partial final file is visible. Success returns:

```text
{
  "result": "finalized",
  "receipt": {
    "receipt_id": "<64 lowercase hex>",
    "upload_id": "...",
    "content_sha256": "...",
    "canonical_sha1": "<legacy canonical JSON SHA-1>",
    "total_size": 1234567,
    "completed_at_unix": 1785270000,
    "use_test_db": false,
    "deduplicated": false
  }
}
```

The receipt is durably stored before success is returned. Replaying finalize
returns the exact same receipt. `deduplicated: true` means equivalent JSON was
already present according to the legacy canonical SHA-1 index.

## Errors and retries

V2 typed errors have:

```text
{
  "result": "err",
  "kind": "<error kind>",
  "message": "...",
  "missing_chunks": []
}
```

Kinds and HTTP status:

| Kind | HTTP | Client behavior |
| --- | ---: | --- |
| `bad_request` | 400 | Fix the request; do not replay unchanged. |
| `unauthorized` | 401 | Exchange a new Google credential/session. |
| `session_expired` | 401 | Exchange a new session and replay once. |
| `not_found` | 404 | Replay the manifest; ownership is intentionally not disclosed. |
| `conflict` | 409 | For finalize, upload `missing_chunks`; otherwise inspect manifest. |
| `payload_too_large` | 413 | Re-chunk or reduce the logical upload. |
| `hash_mismatch` | 422 | Re-read/re-hash local bytes; replay the affected chunk/manifest. |
| `rate_limited` | 429 | Wait for the HTTP `Retry-After` delta-seconds value. |
| `internal` | 500 | Back off and safely replay the same idempotent operation. |

Every 429 response includes a standards-compatible `Retry-After` header. The
primary quota is keyed by authenticated Google identity. A broader public-IP
gate remains for unauthenticated abuse protection.

## Client persistence

To resume after app/process/device interruption, persist only:

- the source-file identity/path needed to re-read bytes
- `content_sha256`, `total_size`, ordered `chunk_sha256`
- returned `upload_id`
- acknowledged/final receipt

Do not persist Google or BTIDALPOOL session tokens as part of the upload record.
After restart, exchange a fresh session and replay the manifest. The server is
the authority for `missing_chunks`.
