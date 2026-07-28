# BTIDALPOOL v3 native-query client contract

BTPL v3 replaces the Python/Tell_Me_Everything query hot path with batched
Rust/MySQL reads. It does not change the MariaDB schema and is additive:
whole-file BTPL v1 remains at `POST /`, and resumable uploads remain at
`POST /v2`.

## Transport and authentication

- Endpoint: `POST https://btidalpool.ddns.net:3568/v3`
- TLS: use the same pinned server certificate as v1/v2.
- Content-Type: `application/x-btidalpool-cbor-zstd; version=3`
- Framing: the existing `BTPL` 9-byte header, with byte 4 set to `0x03`,
  followed by zstd-compressed CBOR.
- Authentication: `{"scheme":"session","token":"..."}` using the same
  short-lived signed session obtained from v2 `create_session`.
- Google credentials are never accepted at `/v3`; exchange them at `/v2`
  and keep the returned session token in memory.

## Query

The request payload is:

```text
{
  "auth": {"scheme": "session", "token": "..."},
  "payload": {
    "cmd": "query",
    "params": {
      "name_regex": ["Samsung"]
    },
    "use_test_db": false
  }
}
```

`params` uses the existing typed `QueryParams` fields. V3 supports exact
BDADDR, BDADDR/name/UUID/MSD regexes, LL/LMP version triples, corresponding
NOT filters, and the GPS/GATT/SMP/SDP/LL/LMP presence requirements. Positive
selectors are unioned, then NOT and requirement filters are applied.

Two TME metadata-dependent features intentionally remain v1-only for now:

- `company_regex` / `NOT_company_regex`, which depend on external assigned
  number and CLUES datasets rather than only the production database
- GPS exclusion boxes

V3 returns a typed `bad_request` instead of silently returning incomplete
matches when either is requested.

The server currently returns at most 100 devices and 50,000 total normalized
rows. The independent row limit prevents a single heavily observed device
from creating an unbounded response. A response says explicitly whether the
row limit truncated it.

## Response

V3 returns a lossless normalized view of the unchanged MySQL schema:

```text
{
  "result": "query_result",
  "query": {
    "devices": [{
      "bdaddr": "aa:bb:cc:dd:ee:ff",
      "tables": {
        "LE_bdaddr_to_name": {
          "columns": [
            "bdaddr", "bdaddr_random", "le_evt_type",
            "device_name_type", "name_hex_str"
          ],
          "rows": [[
            {"type":"bytes", "value":"<CBOR byte string>"},
            {"type":"signed", "value":1},
            {"type":"signed", "value":0},
            {"type":"signed", "value":9},
            {"type":"bytes", "value":"<CBOR byte string>"}
          ]],
          "truncated": false
        }
      }
    }],
    "total_rows": 944,
    "row_limit": 50000,
    "truncated": false
  }
}
```

Table and column names are the exact existing MariaDB names. Each row has the
same number and ordering of cells as `columns`. MySQL byte strings remain CBOR
byte strings; clients must not assume UTF-8.

Cell variants are:

- `null`
- `bytes`
- `signed`
- `unsigned`
- `float`
- `date` (`year`, `month`, `day`, `hour`, `minute`, `second`, `micros`)
- `time` (`negative`, `days`, `hours`, `minutes`, `seconds`, `micros`)

This representation is intentionally normalized rather than reconstructed
BTIDES JSON. It avoids thousands of per-device SQL calls and repeated metadata
loading. Clients that require legacy reconstructed BTIDES may continue using
v1 while a client-side normalized-row adapter is developed.

## Backoff

Errors use the v2 typed error kinds. In particular:

- HTTP 429 / `rate_limited`: authenticated identity or IP quota
- HTTP 503 / `server_busy`: global server capacity is occupied
- HTTP 401 / `session_expired`: exchange a new session and replay once

Every 429 and 503 carries integer delta-seconds `Retry-After`. On 503, keep the
logical query unchanged, wait at least that duration plus randomized jitter,
and retry. Use capped exponential backoff and honor cancellation. A query is
read-only, so replay is safe.

