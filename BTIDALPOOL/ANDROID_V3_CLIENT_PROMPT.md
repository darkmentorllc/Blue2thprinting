# Prompt for the parallel Android worker

```text
Implement the Android client side of the deployed BTIDALPOOL overload/backoff
and native-query upgrade. Work only in Android/client code; do not modify the
Rust server.

Authoritative contracts:
- BTIDALPOOL/V2_PROTOCOL.md
- BTIDALPOOL/V3_PROTOCOL.md
- shared Rust wire types in
  BTIDALPOOL/crates/btidalpool-proto/src/{codec.rs,wire.rs}

Requirements:

1. Add BTPL v3 query support at POST /v3:
   - same BTPL magic, zstd(CBOR), header version byte 3
   - Content-Type application/x-btidalpool-cbor-zstd; version=3
   - authenticate with the short-lived signed BTIDALPOOL session obtained
     from v2 create_session; never send Google credentials to /v3
   - encode V3Envelope/V3Payload::Query and decode V3Response exactly
   - decode every DbValue variant losslessly, especially CBOR byte strings
   - preserve exact table/column names and surface total_rows, row_limit,
     table/global truncation to the caller
   - keep existing v1 query support as a compatibility fallback for
     company_regex and GPS exclusion-box queries, which v3 rejects explicitly

2. Add one centralized retry policy for v1/v2/v3:
   - HTTP 429 means caller quota; HTTP 503 plus v2/v3 server_busy means global
     capacity
   - parse Retry-After as either integer delta-seconds or an HTTP date; never
     retry before it
   - add randomized jitter and capped exponential growth for repeated
     overloads (for example base=max(Retry-After, 2s), multiplier 2, full
     jitter, cap 30s)
   - use a bounded attempt/time budget and make waits coroutine-cancellable
   - safely replay read-only queries, manifests, status, chunk puts, and
     finalize; preserve upload/chunk state
   - on session_expired, exchange a fresh session and replay once; do not
     treat 401 as overload
   - do not retry unchanged 400/413/422 requests
   - do not log OAuth tokens, session tokens, BTIDES contents, or secrets
   - retain v1 compatibility: its overload body uses the legacy rate_limited
     tag, so distinguish quota vs overload by HTTP 429 vs 503

3. UX:
   - represent overload as a normal queued/retrying state, including the next
     retry time and a Cancel action
   - do not ask the user to sign in again for 429/503
   - only surface a final error after the bounded retry budget is exhausted

4. Tests (use the project’s existing HTTP test framework/MockWebServer):
   - 503 with Retry-After then 200
   - repeated 503 demonstrates bounded exponential jitter
   - 429 is retried no earlier than Retry-After
   - HTTP-date Retry-After
   - malformed/missing Retry-After uses the safe default
   - coroutine cancellation stops the wait/request
   - v1 503 legacy body remains decodable
   - v2 put/finalize replay keeps the same upload/chunk identifiers
   - session expiry refreshes once, whereas overload never triggers sign-in
   - v3 100-device response, binary DbValue, and truncation flags round-trip
   - unsupported v3 company/GPS filters route to v1

Run the relevant Android unit/instrumentation tests, report exact changed
files and results, and do not perform interactive Google sign-in.
```

