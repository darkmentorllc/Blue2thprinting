# BTIDALPOOL Rust Server — Client Protocol Spec (for the Android uploader)

**Purpose.** This document fully specifies the wire protocol and server interface of the
**Rust** BTIDALPOOL server so an Android application can be updated to connect to it and
upload (and optionally query) BTIDES data. It is self-contained: an implementer needs no
other source.

**What changed.** The legacy Python server (`btidalpool.ddns.net:3567`) accepts **raw JSON**
POSTs. The new Rust server (`btidalpool.ddns.net:3568`) accepts the **same logical
requests** but in a compact binary framing: **CBOR, zstd-compressed, inside a 9-byte
frame**. Authentication (Google OAuth `token` + `refresh_token`) is **unchanged** — only the
transport encoding and the field layout differ. The two servers run in parallel; moving the
Android app to `:3568` is the goal.

> Quick efficiency note: a 127,600-byte BTIDES JSON upload goes out as ~12,900 bytes on the
> wire (~10×). That compression is the whole reason for the new format.

---

## Table of contents
1. [Endpoint & transport](#1-endpoint--transport)
2. [Frame format (the "codec")](#2-frame-format-the-codec)
3. [Request: the Envelope](#3-request-the-envelope)
4. [Response](#4-response)
5. [Authentication & token refresh](#5-authentication--token-refresh)
6. [The upload flow (primary)](#6-the-upload-flow-primary)
7. [The query flow (optional)](#7-the-query-flow-optional)
8. [Limits, validation, dedup](#8-limits-validation-dedup)
9. [TLS / certificate pinning](#9-tls--certificate-pinning)
10. [Legacy (Python :3567) → new (Rust :3568) mapping](#10-legacy-python-3567--new-rust-3568-mapping)
11. [Android implementation notes](#11-android-implementation-notes)
12. [Worked example](#12-worked-example)
13. [Appendix A — CDDL schema](#appendix-a--cddl-schema)
14. [Appendix B — exact Rust wire types](#appendix-b--exact-rust-wire-types)

---

## 1. Endpoint & transport

| Property | Value |
| --- | --- |
| URL | `https://btidalpool.ddns.net:3568/` (path is ignored; POST to `/`) |
| Method | **POST only** (any other method → `405` plain text) |
| Request `Content-Type` | **`application/x-btidalpool-cbor-zstd`** (anything else → `415` plain text) |
| Request body | one [frame](#2-frame-format-the-codec) wrapping one [`Envelope`](#3-request-the-envelope) |
| Response `Content-Type` | `application/x-btidalpool-cbor-zstd` for application responses; `text/plain` for transport errors |
| Response body | one frame wrapping one [`Response`](#4-response) (except transport errors, which are plain text) |
| TLS | self-signed cert, **must be pinned/trusted** — see [§9](#9-tls--certificate-pinning) |

There is exactly **one request and one response per HTTP POST**. No keep-alive semantics are
required; one POST == one operation (upload, query, or check-hash).

---

## 2. Frame format (the "codec")

Every request and response body is a single **frame**:

```
 offset  size  field
 ------  ----  ---------------------------------------------------------
   0      4    MAGIC            = ASCII "BTPL"  (0x42 0x54 0x50 0x4C)
   4      1    VERSION          = 0x01
   5      4    declared_len     = uint32, BIG-ENDIAN, = length of the
                                  *uncompressed* CBOR in bytes
   9      N    payload          = zstd-compressed CBOR (a standard zstd frame)
```

**To build a request body:**
1. Serialize the `Envelope` to **CBOR** → call it `cbor` (remember `cbor.len()`).
2. **zstd-compress** `cbor` (level 3 is what the reference client uses; any level the
   decoder can read is fine — it's a standard zstd frame) → `compressed`.
3. Emit: `b"BTPL"` + `0x01` + `uint32_be(cbor.len())` + `compressed`.

**To read a response body:** verify magic `BTPL` + version `1`, read `declared_len`, then
`zstd-decompress` bytes `[9..]` and CBOR-decode the result into a `Response`.

**Hard caps (server-enforced; mirror these client-side):**
- Compressed frame ≤ **20 MiB** (a larger `Content-Length` is rejected with `413`).
- Decompressed CBOR ≤ 200 MiB (zip-bomb guard; you will never hit this).
- The decoder is strict: wrong magic, unknown version, or a declared-length/actual-length
  mismatch is rejected. Keep `declared_len` exactly equal to the uncompressed CBOR length.

---

## 3. Request: the Envelope

The CBOR value is a **map** (the field names below are the literal CBOR map keys):

```
Envelope = {
  "auth":    AuthFields,
  "payload": Payload
}

AuthFields = {
  "token":         <text>,    // Google OAuth2 ACCESS token (see §5)
  "refresh_token": <text>,    // Google refresh token (see §5)
  "use_test_db":   <bool>     // false = production DB (bt2); true = test DB (bttest)
}
```

`Payload` is an **internally-tagged** enum: it is a map whose `"cmd"` key selects the
command, with the command's own fields in the **same** map (not nested under the command
name). The three commands:

```
// Upload a BTIDES file:
Payload = { "cmd": "upload", "btides_json": <byte string> }

// Ask if the server already has this content (optional pre-flight):
Payload = { "cmd": "check_hash", "hash": <text> }

// Run a query:
Payload = { "cmd": "query", "params": QueryParams }
```

### ⚠️ Critical encoding details
- **`btides_json` is a CBOR *byte string* (major type 2)** containing the **raw UTF-8 bytes
  of the BTIDES JSON file** — *not* a nested CBOR object and *not* a CBOR text string. Take
  the JSON document as a `byte[]` and put it in as a byte string. (Rust type: `Vec<u8>` via
  `serde_bytes`.)
- **Internally-tagged:** for `upload`, the map is `{"cmd":"upload","btides_json":h'...'}` —
  two keys at the same level. Do **not** nest as `{"upload":{...}}`.
- **`use_test_db`** is optional on decode (missing ⇒ `false`) but you should send it
  explicitly. Set `false` for real data; `true` only for testing.
- **CBOR map key order does not matter** — the server decodes by key name. You do not need
  canonical/deterministic CBOR.

---

## 4. Response

The response body (when present as a frame) is a **map**, internally-tagged on `"result"`:

```
// Success (e.g. upload accepted):  HTTP 200
Response = { "result": "ok", "message": <text> }

// Application error:               HTTP status depends on "kind" (table below)
Response = { "result": "err", "kind": <ErrorKind>, "message": <text> }

// Query result:                    HTTP 200
Response = { "result": "query_result", "records": <uint>, "btides_json": <byte string> }
```

`ErrorKind` is a lowercase snake_case string. Branch on it; the `message` is human-readable
only.

| `kind` | HTTP | Meaning | Client action |
| --- | --- | --- | --- |
| `unauthorized` | 401 | OAuth token invalid/expired | **Refresh token, retry once** (§5) |
| `duplicate_upload` | 400 | Server already has this exact content | **Treat as success** (no-op) |
| `bad_request` | 400 | Malformed request / file too big / not valid JSON | Fix input; don't blind-retry |
| `schema_invalid` | 400 | BTIDES failed schema validation | Fix input |
| `empty_result` | 400 | Query matched zero records | Normal "no results" for queries |
| `internal` | 500 | Server-side failure (disk, SQL ingest, etc.) | Retry later |
| `rate_limited` | 429 | (defined, but see note) | Back off |

### Two response classes — read the `Content-Type`
1. **Application responses** (`Content-Type: application/x-btidalpool-cbor-zstd`): a frame
   wrapping a `Response`. **This includes `401 unauthorized`** — decode the body to detect
   it and trigger refresh.
2. **Transport errors** (`Content-Type: text/plain; charset=utf-8`): a short plain-text
   message, **not** a frame. These are returned *before* the application layer:
   - `405` Method Not Allowed (you didn't POST)
   - `415` Unsupported Media Type (wrong/missing request `Content-Type`)
   - `413` Payload Too Large (frame > 20 MiB)
   - `400 Bad request body` (frame failed to decode — bad magic/version/zstd/CBOR)
   - `429 Too Many Requests` (rate limit; **plain text**, not a codec `err`)

> **Read the body even on 4xx/5xx.** Many HTTP clients throw on non-2xx; you must still pull
> the body bytes and (if the content-type is the codec type) decode them, because
> `unauthorized` / `duplicate_upload` arrive with 401 / 400 status.

---

## 5. Authentication & token refresh

**Unchanged from the current Python flow** — same credentials, same Google client, same
refresh endpoint. The app already obtains a `token` + `refresh_token` to upload to `:3567`;
reuse that exact credential acquisition.

- **`token`** must be a **Google OAuth2 access token** carrying the email scope
  (`https://www.googleapis.com/auth/userinfo.email`, i.e. `openid email`). The server
  validates every request by calling `https://www.googleapis.com/oauth2/v2/userinfo` with
  `Authorization: Bearer <token>` and reading the `email` field. Any Google access token
  with that scope works; the server does not care which OAuth client minted it.
- **`refresh_token`** is sent inline but the **server ignores it for validation** (refresh is
  the client's responsibility). It only matters for the refresh step below.
- **BTIDALPOOL Google client ID** (used by the refresh endpoint):
  `6849068466-1sone95u0ihio99646tn60s234d88hge.apps.googleusercontent.com`

### Refresh-and-retry (handle `401 unauthorized`)
Access tokens expire ~hourly. The reference client does this:

1. Send the request. If the decoded response is `{"result":"err","kind":"unauthorized"}`
   (HTTP 401):
2. `POST https://btidalpool.ddns.net:7653/refresh` with a **plain JSON** body (this endpoint
   is ordinary JSON, *not* the codec):
   ```json
   { "refresh_token": "<refresh_token>",
     "client_id": "6849068466-1sone95u0ihio99646tn60s234d88hge.apps.googleusercontent.com" }
   ```
   - On success it returns JSON `{ "token": "<new access>", "refresh_token": "<new refresh>" }`.
   - **This server uses a normal (Let's Encrypt) certificate** — validate it against the
     system trust store. **Do NOT pin the self-signed data-server cert here** (it would, and
     should, fail). Port `:7653` ≠ port `:3568` trust.
3. Update your stored `token`/`refresh_token`, **retry the original request exactly once**.
4. If refresh is declined (4xx/5xx or missing fields), surface the original `unauthorized`.

> **Android-idiomatic alternative.** If on Android you mint access tokens directly from the
> account (e.g. Credential Manager / `AuthorizationClient`, or `GoogleAuthUtil.getToken` with
> scope `oauth2:https://www.googleapis.com/auth/userinfo.email`), you can skip the `:7653`
> endpoint entirely: on a `401`, invalidate the cached token, fetch a fresh access token from
> Google, and retry. In that mode `refresh_token` can be any placeholder (e.g. `""`) since the
> server ignores it. Pick whichever matches what the app already does for `:3567`.

---

## 6. The upload flow (primary)

**Recommended (simplest, and what the server is built for): skip the pre-flight, just
upload.** The server deduplicates on its own.

```
1. Read the BTIDES JSON file as bytes -> btidesBytes (must be < 10 MiB, valid JSON).
2. Build Envelope:
     auth = { token, refresh_token, use_test_db=false }
     payload = { cmd:"upload", btides_json: <byte string = btidesBytes> }
3. frame = BTPL header + zstd(CBOR(envelope))
4. POST frame to https://btidalpool.ddns.net:3568/
     Content-Type: application/x-btidalpool-cbor-zstd
5. Read response:
     - text/plain  -> transport error (see §4); handle by status.
     - codec frame -> decode Response:
         result=="ok"                          -> SUCCESS ("File saved successfully.")
         result=="err" && kind=="duplicate_upload" -> SUCCESS (already on server; no-op)
         result=="err" && kind=="unauthorized" -> refresh token (§5), retry ONCE
         result=="err" (other)                 -> failure; show message, do not loop
```

- A successful new upload returns `ok` with `message = "File saved successfully."`
- A duplicate returns `err`/`duplicate_upload` (HTTP 400) — **treat as success**: the content
  is already stored. (Dedup is by a canonical SHA1 of the JSON, computed server-side.)
- The optional `check_hash` pre-flight only exists to avoid sending bytes you know are
  duplicates. It is **not** required and is easy to get subtly wrong (see [Appendix C note on
  hashing](#appendix-a--cddl-schema)); prefer skipping it.

---

## 7. The query flow (optional)

Only needed if the Android app reads data back (most uploaders don't). Build
`payload = { cmd:"query", params: QueryParams }`. All `QueryParams` fields are optional;
omit or set to null/false to not apply a filter. The server returns at most **100 records**.

Common fields (full list in [Appendix B](#appendix-b--exact-rust-wire-types)):

| Field | CBOR type | Meaning |
| --- | --- | --- |
| `bdaddr` | text or null | exact BDADDR, e.g. `"92:70:29:e9:f0:78"` |
| `bdaddr_regex` | array of text or null | match BDADDRs by regex |
| `name_regex` | array of text or null | match advertised names |
| `company_regex` | array of text or null | match company IDs |
| `UUID_regex` | array of text or null | match service UUIDs |
| `require_GPS`, `require_GATT_any`, … | bool | boolean filters (default false) |

Response is `query_result` with `records` (count) and `btides_json` (a **byte string** of the
result BTIDES JSON). An empty match returns `err`/`empty_result` (not an exception).

Field names are **case-sensitive** and some are intentionally upper-case (`NOT_bdaddr`,
`UUID_regex`, `LL_VERSION_IND`, `require_SMP`, …) — copy them verbatim from Appendix B.

---

## 8. Limits, validation, dedup

- **Upload size:** the decoded BTIDES JSON must be **< 10 MiB** (else `bad_request` "File
  size too big"). The compressed frame must be **≤ 20 MiB** (else `413`).
- **JSON validity:** the upload bytes must parse as JSON, and should be a valid **BTIDES**
  document (a JSON array of device records). The repo's BTIDES schema lives under
  `Analysis/BTIDES_Schema/` (`BTIDES_base.json` + the per-layer `BTIDES_*.json`). The current
  Android/Python uploader already validates against this before sending — keep doing so.
- **Dedup:** server-side, by a canonical (sorted-keys) SHA1 of the JSON. Duplicate content ⇒
  `duplicate_upload`. You do not need to compute this hash if you skip the pre-flight.
- **Rate limits (per client IP):** **10** concurrent requests, **100** requests/day. Exceeding
  → `429 Too Many Requests` (plain text). Back off and retry later.

---

## 9. TLS / certificate pinning

The data server (`:3568`, same cert as `:3567`) presents a **self-signed** certificate. You
must explicitly trust/pin it; the system trust store will reject it.

- **Subject/Issuer:** `CN=btidalpool.ddns.net` (self-signed), **SAN** `DNS:btidalpool.ddns.net`
- **Validity:** 2025-03-15 → **2035-03-13** (long-lived; rotation is rare but will require an
  app update when it happens)
- **SPKI SHA-256 pin** (OkHttp `CertificatePinner` format):
  ```
  sha256/W50B6HRWnILf3AZ4hVFIBeo63ccaEvIMtzgFtMP2Gmg=
  ```
- **Refresh endpoint `:7653`** uses a **normal Let's Encrypt** cert → validate with the
  **system** trust store; do **not** apply the pin above to it.

The full PEM (public cert, safe to embed in the app as a raw resource):

```
-----BEGIN CERTIFICATE-----
MIIGIzCCBAugAwIBAgIUKu5XJInkKLXCJ8K8cydH78LvFB0wDQYJKoZIhvcNAQEL
BQAwgZ0xCzAJBgNVBAYTAlVTMQswCQYDVQQIDAJCVDEUMBIGA1UEBwwLQmx1ZUNy
ZXdCYXkxETAPBgNVBAoMCEJsdWVDcmV3MRgwFgYDVQQLDA9CVElERS1vLW1hbmNl
cnMxHDAaBgNVBAMME2J0aWRhbHBvb2wuZGRucy5uZXQxIDAeBgkqhkiG9w0BCQEW
EWJsdWVjcmV3QG9zdDIuZnlpMB4XDTI1MDMxNTExMjMyOVoXDTM1MDMxMzExMjMy
OVowgZ0xCzAJBgNVBAYTAlVTMQswCQYDVQQIDAJCVDEUMBIGA1UEBwwLQmx1ZUNy
ZXdCYXkxETAPBgNVBAoMCEJsdWVDcmV3MRgwFgYDVQQLDA9CVElERS1vLW1hbmNl
cnMxHDAaBgNVBAMME2J0aWRhbHBvb2wuZGRucy5uZXQxIDAeBgkqhkiG9w0BCQEW
EWJsdWVjcmV3QG9zdDIuZnlpMIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKC
AgEArGLxr2A8ilhGU2M8KKUAWkLg5H0DilDoYdVtwKK2xo3dhyiiYZx2kbVzkjXC
9BAvdDKBBkSZsAg+ndTv9qrtYhMWac22VMK9LimSH5SMomMlbiKdFRu7mLKh6Ysb
oeFaON1T2o88hF7ikmNNBTPrngy/vvRABABUwO4qVjdRQtILVqfcjvSeo9Pe+JOO
yyoBq9l4Pm0R2xwcyWk5EHgw220hprE8WPsLfWmNJWy+oN192mf1Lj1EJes0Tcqq
Yx7k5Y9ceL5ReS02F41r9Ir/qRx/rKKDZTWpmqoq2BsdWEitaDnqGtYsvLpcrigF
onMz1b0D7lkOFLICWJRb8s01t4/3oEpLQVEZqZRJnhpUhDskNH+D8E+6rm1BjUWc
dS7tuCORrarf5L/OVBp+L5kKMXIBRy0be/iHDLIcHhG6L3cJ85EXbubJfUTJZ1kw
KenpdJLJ/MTZApB+YLItItMu2v2A5Z9EzVIhSu3UKK4ZAmrX/IKdbKFtL74LEzxG
XuYQFGPhAQolTFWY8te7FPLv5yPSrRG1GcvKRYOKa39wQFV85B2efL+2a7nY1sbJ
rKjiJio6TvmYljv7yWxmaSoXcnK9SuzbShzkwQ/AYF+7Q4FodPkcoNzur2boI1do
FnQdDAPf3MWWGhxBJSpTKMz+GGas6aHEdIR9ywlJlKoqBmkCAwEAAaNZMFcwCQYD
VR0TBAIwADALBgNVHQ8EBAMCBaAwHgYDVR0RBBcwFYITYnRpZGFscG9vbC5kZG5z
Lm5ldDAdBgNVHQ4EFgQUAZ1Nszbd2Ocf3ZFpS6PMDFpWKUUwDQYJKoZIhvcNAQEL
BQADggIBAFZ2fi/eiKgLOSq1vFSuzgFQGa2odXnp9EJuQAkDew0JCbAN7LD6Sl7/
JSMcBZdTHishavU3nG+TND4V9gUY7JdPBA4v1ZF1+uim+c2du7vq6pn8wW0UKj/u
rZkLimDXEPDVeg28c+oWmG4j4W6gEr9tMkt6T684xjXpvEOckVyaYxNCqOmX3Agq
iSP23HpfjVggmFtmDQO3+xfUC6jwhENrITA5gf+DMoG4PsnAO/KhGXPqzk7sqOrX
9a89Nsaz6R4tPs+5SFYwbKPR7/gZmcdrFLPO/Gn3Fihdif5/znjPraekiYsyhfua
BDgCysww/hfju6z6xVLdB+Enub73c2zJqNlK/u25N4jUJG72XnOB/yrWcMXvvr5f
13r3VKn9B8KGbNxL2OiMli9NYuIyyzwH64NEy4Ry2O88V4lUIt+kAzHKQ5aSPzgp
mahGY8dI1bzNLcpXLEn/VnE1QPDji51DXhx1Dhq7xw3hJ9u9Wryqqnl3Y61JYf6A
/uJEOzRrFp+CurWYzUq6EOYBgyG0fvaseF8O6+yw7A+P/oirH1jTWkDvUk3jbwGk
VF9Dg5Yo1J39AW2BDPDmB5NKKKN1iPbmvF0Ec9bLpIuAaUxymMlQo+eD4Xd2NWKU
mheLd5T+Edy7l9Xdfa51gBT6gS1r0aMc7Q6NDvITbRqiAArlNTfA
-----END CERTIFICATE-----
```

---

## 10. Legacy (Python `:3567`) → new (Rust `:3568`) mapping

| Aspect | Legacy (Python, `:3567`) | New (Rust, `:3568`) |
| --- | --- | --- |
| Body | raw JSON (`application/json`) | `BTPL` frame: zstd(CBOR), `application/x-btidalpool-cbor-zstd` |
| Auth fields | top-level keys `token`, `refresh_token`, `use_test_db` | nested under `auth` map |
| Command selector | `"command": "upload"/"check_hash"/"query"` | `"cmd": "upload"/"check_hash"/"query"` inside `payload` |
| Upload payload | `"btides_content": <parsed JSON object>` | `"btides_json": <byte string of the raw JSON text>` |
| Hash check | `"hash": <sha1>` | `"hash": <sha1>` (same; pre-flight still optional) |
| Success response | `200 text/plain` "File saved successfully." | frame `{"result":"ok","message":"File saved successfully."}` |
| Error response | `4xx text/plain` | frame `{"result":"err","kind":...,"message":...}` (except transport errors) |
| Endpoint host:port | `btidalpool.ddns.net:3567` | `btidalpool.ddns.net:3568` |
| TLS | same self-signed cert | **same self-signed cert** (reuse the pin/PEM) |

Net change for the app: **(a)** point at port `3568`, **(b)** wrap the request in CBOR→zstd→BTPL
instead of sending JSON, **(c)** nest auth under `auth` and rename `command`→`cmd` /
`btides_content`(object)→`btides_json`(bytes), **(d)** decode the framed response instead of
reading `text/plain`. Auth acquisition and the cert are unchanged.

---

## 11. Android implementation notes

**Suggested libraries**
- HTTP: **OkHttp**.
- zstd: **`com.github.luben:zstd-jni`** (`Zstd.compress(bytes, 3)` / `Zstd.decompress(...)`).
- CBOR: **Jackson** `com.fasterxml.jackson.dataformat:jackson-dataformat-cbor`
  (`CBORMapper`), or `com.upokecenter:cbor`, or kotlinx-serialization-cbor. Any of them can
  emit a map with a byte-string value.

**Building the frame (Kotlin-ish pseudocode)**
```kotlin
// 1) CBOR envelope. btidesBytes is the raw JSON file as ByteArray.
val env = mapOf(
    "auth" to mapOf(
        "token" to accessToken,
        "refresh_token" to refreshToken,   // or "" if you re-mint via Google on 401
        "use_test_db" to false
    ),
    "payload" to mapOf(
        "cmd" to "upload",
        "btides_json" to btidesBytes        // MUST encode as a CBOR byte string
    )
)
val cbor = CBORMapper().writeValueAsBytes(env)   // ensure ByteArray -> CBOR byte string

// 2) zstd compress
val compressed = Zstd.compress(cbor, 3)

// 3) BTPL frame
val frame = ByteBuffer.allocate(9 + compressed.size).order(ByteOrder.BIG_ENDIAN)
    .put('B'.code.toByte()).put('T'.code.toByte()).put('P'.code.toByte()).put('L'.code.toByte())
    .put(1)                       // version
    .putInt(cbor.size)            // declared uncompressed length, big-endian
    .put(compressed)
    .array()

// 4) POST
val req = Request.Builder()
    .url("https://btidalpool.ddns.net:3568/")
    .post(frame.toRequestBody("application/x-btidalpool-cbor-zstd".toMediaType()))
    .build()
```
> With Jackson, make sure the BTIDES file is passed as a `ByteArray` (→ CBOR major type 2),
> **not** as a `String` (→ text string) and **not** as a parsed `JsonNode` (→ nested map).

**Parsing the response**
```kotlin
val body = response.body!!.bytes()                 // read even on 4xx/5xx
if (response.header("Content-Type")?.startsWith("application/x-btidalpool-cbor-zstd") == true) {
    require(body.copyOfRange(0,4).contentEquals("BTPL".toByteArray()) && body[4].toInt() == 1)
    val declared = ByteBuffer.wrap(body,5,4).order(ByteOrder.BIG_ENDIAN).int
    val cbor = Zstd.decompress(body.copyOfRange(9, body.size), declared)
    val resp = CBORMapper().readValue(cbor, Map::class.java)
    when (resp["result"]) {
        "ok" -> { /* success */ }
        "query_result" -> { /* resp["records"], resp["btides_json"] (ByteArray) */ }
        "err" -> when (resp["kind"]) {
            "duplicate_upload" -> { /* treat as success */ }
            "unauthorized"     -> { /* refresh token (§5), retry once */ }
            else               -> { /* show resp["message"] */ }
        }
    }
} else {
    // text/plain transport error (405/415/413/429/400-bad-body): handle by status code
}
```

**TLS** — cleanest is an Android **Network Security Config** that trusts *both* the bundled
self-signed cert (for `:3568`) *and* the system roots (for `:7653`):
```xml
<!-- res/xml/network_security_config.xml -->
<network-security-config>
  <domain-config>
    <domain includeSubdomains="false">btidalpool.ddns.net</domain>
    <trust-anchors>
      <certificates src="@raw/btidalpool_selfsigned"/>  <!-- the PEM from §9 -->
      <certificates src="system"/>                      <!-- keeps :7653 LE cert working -->
    </trust-anchors>
  </domain-config>
</network-security-config>
```
Or use OkHttp `CertificatePinner` with the SPKI pin from §9 for `:3568`, and a separate plain
OkHttp client (system trust) for the `:7653` refresh call.

**Auth** — reuse whatever the app already does to get the `token`/`refresh_token` it currently
sends to `:3567`. The new server validates the access token the same way (Google userinfo →
email). Implement the `401 unauthorized` → refresh → retry-once loop (§5).

---

## 12. Worked example

A real captured upload of a 127,600-byte BTIDES JSON produced this on-wire frame:

```
first bytes (hex):  42 54 50 4c 01 00 01 f4 29 28 b5 2f fd ...
                    └─ "BTPL" ─┘ │  └ declared ┘ └ zstd magic ┘
                     magic       v1   0x0001f429    28 b5 2f fd
                                      = 128041 B
raw JSON size            : 127,600 bytes
CBOR envelope (declared) : 128,041 bytes   (JSON-as-byte-string + auth, ~441 B overhead)
on-wire frame            :  12,933 bytes   (~9.9x smaller than the JSON)
```

The decompressed CBOR begins with `0xA2` = a 2-entry map (`auth`, `payload`) — confirming the
structure in [§3](#3-request-the-envelope).

Decoded-CBOR (diagnostic) view of an upload envelope:
```
{
  "auth": { "token": "ya29.A0AR...", "refresh_token": "1//09...", "use_test_db": false },
  "payload": { "cmd": "upload", "btides_json": h'5b7b2262646164...' }   // bytes of "[{"bdaddr...
}
```

A successful response decodes to:
```
{ "result": "ok", "message": "File saved successfully." }     // HTTP 200
```

---

## Appendix A — CDDL schema

A precise, language-agnostic [CDDL](https://www.rfc-editor.org/rfc/rfc8610) description of the
CBOR (before zstd/framing):

```cddl
envelope = {
  auth:    auth-fields,
  payload: payload,
}

auth-fields = {
  token:          tstr,
  refresh_token:  tstr,
  ? use_test_db:  bool,        ; default false if omitted
}

payload = upload-cmd / checkhash-cmd / query-cmd
upload-cmd    = { cmd: "upload",     btides_json: bstr }   ; bstr = raw JSON file bytes
checkhash-cmd = { cmd: "check_hash", hash: tstr }          ; 40-char lowercase hex SHA1
query-cmd     = { cmd: "query",      params: query-params }

query-params = {
  ? bdaddr: tstr / null,
  ? NOT_bdaddr: [* tstr] / null,
  ? bdaddr_regex: [* tstr] / null,
  ? NOT_bdaddr_regex: [* tstr] / null,
  ? name_regex: [* tstr] / null,
  ? NOT_name_regex: [* tstr] / null,
  ? company_regex: [* tstr] / null,
  ? NOT_company_regex: [* tstr] / null,
  ? UUID_regex: [* tstr] / null,
  ? NOT_UUID_regex: [* tstr] / null,
  ? MSD_regex: [* tstr] / null,
  ? LL_VERSION_IND: tstr / null,
  ? LMP_VERSION_RES: tstr / null,
  ? GPS_exclude_upper_left: tstr / null,
  ? GPS_exclude_lower_right: tstr / null,
  ? require_GPS: bool, ? require_GATT_any: bool, ? require_GATT_values: bool,
  ? require_SMP: bool, ? require_SMP_legacy_pairing: bool, ? require_SDP: bool,
  ? require_LL_VERSION_IND: bool, ? require_LMP_VERSION_RES: bool,
}

response = ok-resp / err-resp / query-result
ok-resp      = { result: "ok",           message: tstr }
err-resp     = { result: "err",          kind: error-kind, message: tstr }
query-result = { result: "query_result", records: uint, btides_json: bstr }

error-kind = "bad_request" / "unauthorized" / "rate_limited" /
             "schema_invalid" / "duplicate_upload" / "empty_result" / "internal"
```

> **Hashing note (only if you implement `check_hash`).** The server's dedup hash is
> `SHA1( serialize(sort_object_keys_recursively(parse(json))) )`, hex-lowercase, where
> `serialize` is **compact** (no inter-token spaces). Replicate that exactly or your
> pre-flight hashes won't match. This is fiddly and unnecessary — **prefer skipping the
> pre-flight** and letting the server dedup the upload.

---

## Appendix B — exact Rust wire types

Authoritative source (`btidalpool-proto`). Field names = CBOR keys; enum representations are
serde-internally-tagged.

```rust
pub const CONTENT_TYPE: &str = "application/x-btidalpool-cbor-zstd";

#[derive(Serialize, Deserialize)]
pub struct AuthFields {
    pub token: String,
    pub refresh_token: String,
    #[serde(default)] pub use_test_db: bool,
}

#[derive(Serialize, Deserialize)]
pub struct Envelope { pub auth: AuthFields, pub payload: Payload }

#[derive(Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]   // -> "upload" / "check_hash" / "query"
pub enum Payload {
    Upload { #[serde(with = "serde_bytes")] btides_json: Vec<u8> }, // CBOR byte string
    CheckHash { hash: String },
    Query { params: QueryParams },
}

#[derive(Default, Serialize, Deserialize)]
#[allow(non_snake_case)]
pub struct QueryParams {
    pub bdaddr: Option<String>,
    pub NOT_bdaddr: Option<Vec<String>>,
    pub bdaddr_regex: Option<Vec<String>>,
    pub NOT_bdaddr_regex: Option<Vec<String>>,
    pub name_regex: Option<Vec<String>>,
    pub NOT_name_regex: Option<Vec<String>>,
    pub company_regex: Option<Vec<String>>,
    pub NOT_company_regex: Option<Vec<String>>,
    pub UUID_regex: Option<Vec<String>>,
    pub NOT_UUID_regex: Option<Vec<String>>,
    pub MSD_regex: Option<Vec<String>>,
    pub LL_VERSION_IND: Option<String>,
    pub LMP_VERSION_RES: Option<String>,
    pub GPS_exclude_upper_left: Option<String>,
    pub GPS_exclude_lower_right: Option<String>,
    #[serde(default)] pub require_GPS: bool,
    #[serde(default)] pub require_GATT_any: bool,
    #[serde(default)] pub require_GATT_values: bool,
    #[serde(default)] pub require_SMP: bool,
    #[serde(default)] pub require_SMP_legacy_pairing: bool,
    #[serde(default)] pub require_SDP: bool,
    #[serde(default)] pub require_LL_VERSION_IND: bool,
    #[serde(default)] pub require_LMP_VERSION_RES: bool,
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "result", rename_all = "snake_case")]  // "ok" / "err" / "query_result"
pub enum Response {
    Ok { message: String },
    Err { kind: ErrorKind, message: String },
    QueryResult { records: u64, #[serde(with = "serde_bytes")] btides_json: Vec<u8> },
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorKind {           // http_status():
    BadRequest,                // 400
    Unauthorized,              // 401
    RateLimited,               // 429
    SchemaInvalid,             // 400
    DuplicateUpload,           // 400
    EmptyResult,               // 400
    Internal,                  // 500
}
```

Frame codec constants: `MAGIC = b"BTPL"`, `WIRE_VERSION = 1`, header = 9 bytes
(`4 magic + 1 version + 4 big-endian uncompressed-length`), payload = zstd (`level 3`),
`DEFAULT_MAX_COMPRESSED = 20 MiB`, `DEFAULT_MAX_UNCOMPRESSED = 200 MiB`, upload JSON cap
`MAX_UPLOAD_BYTES = 10 MiB`, `MAX_RECORDS_PER_QUERY = 100`.
