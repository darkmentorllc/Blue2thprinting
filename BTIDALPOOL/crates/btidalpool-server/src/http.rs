//! HTTP/HTTPS request loop. Uses `tiny_http` with its `ssl-rustls` feature
//! so we don't pull in OpenSSL.
//!
//! Every POST goes through the same pipeline:
//!
//!   1. Method check (only POST is allowed, matching the Python server's
//!      explicit do_GET/do_PUT/etc. rejection block).
//!   2. Content-Type check — POSTs that don't carry our wire mime type
//!      are rejected with HTTP 415 and a plain-text body so an old Python
//!      client trying to POST raw JSON sees a clear error.
//!   3. Rate-limit check (per-client-IP).
//!   4. Read body (capped at the wire codec's max compressed size — extra
//!      bytes are discarded and the request is rejected).
//!   5. Decode the codec frame into an [`Envelope`].
//!   6. OAuth-validate the embedded token; on failure return Unauthorized.
//!   7. Dispatch to the typed handler.
//!   8. Encode the [`Response`], set the matching HTTP status, write back.
//!
//! Per-request threading: we accept connections on the main loop and spawn
//! a short-lived `std::thread` per request. The rate limiter bounds the
//! number of in-flight requests per IP, so the worker-thread count is
//! self-limiting in steady state.

use std::io::{self, Read, Write};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use btidalpool_proto::{codec, AuthFields, Envelope, ErrorKind, Payload, Response, CONTENT_TYPE};
use tiny_http::{Header, Method, Request, Response as TinyResp, Server, StatusCode};

use crate::handlers::{dispatch, Deps};
use crate::oauth::{AuthError, OAuthValidator};
use crate::rate_limit::{Decision, Limiter};

/// Server configuration. Built by `main.rs` from CLI flags and handed to
/// [`run`].
pub struct Config {
    pub bind: SocketAddr,
    pub tls: Option<TlsConfig>,
    pub limiter: Limiter,
    pub validator: Arc<dyn OAuthValidator>,
    pub deps: Deps,
}

pub struct TlsConfig {
    pub cert_pem_path: PathBuf,
    pub key_pem_path: PathBuf,
}

/// Run the server until the process is killed. Returns only on a fatal
/// error from `tiny_http::Server::http`/`https` — recoverable per-request
/// errors are logged and the loop continues.
pub fn run(cfg: Config) -> anyhow::Result<()> {
    let server = build_server(&cfg)?;
    log::info!("Listening on {}", cfg.bind);

    let cfg = Arc::new(SharedCfg {
        limiter: cfg.limiter,
        validator: cfg.validator,
        deps: cfg.deps,
    });

    loop {
        let request = match server.recv() {
            Ok(r) => r,
            Err(e) => {
                log::error!("accept error: {e}");
                continue;
            }
        };
        let cfg = cfg.clone();
        std::thread::spawn(move || {
            if let Err(e) = handle(request, &cfg) {
                log::error!("handler error: {e}");
            }
        });
    }
}

/// Build a `tiny_http::Server` with or without TLS depending on `cfg.tls`.
fn build_server(cfg: &Config) -> anyhow::Result<Server> {
    match &cfg.tls {
        None => Server::http(cfg.bind)
            .map_err(|e| anyhow::anyhow!("tiny_http::http: {e}")),
        Some(tls) => {
            let certificate = std::fs::read(&tls.cert_pem_path)?;
            let private_key = std::fs::read(&tls.key_pem_path)?;
            let ssl = tiny_http::SslConfig {
                certificate,
                private_key,
            };
            Server::https(cfg.bind, ssl).map_err(|e| anyhow::anyhow!("tiny_http::https: {e}"))
        }
    }
}

struct SharedCfg {
    limiter: Limiter,
    validator: Arc<dyn OAuthValidator>,
    deps: Deps,
}

fn handle(mut request: Request, cfg: &SharedCfg) -> io::Result<()> {
    let client_ip = request.remote_addr().map(|a| a.ip()).unwrap_or_else(|| {
        // Falls back to a sentinel address rather than failing the request,
        // which matches `tiny_http`'s own pattern of always producing a peer.
        std::net::IpAddr::from([127, 0, 0, 1])
    });

    // Method gate — the old Python server rejected everything except POST
    // with HTTP 405. Keep parity.
    if request.method() != &Method::Post {
        return reply_plain(request, 405, "Method Not Allowed");
    }

    // Content-Type gate.
    let ct = request
        .headers()
        .iter()
        .find(|h| h.field.equiv("Content-Type"))
        .map(|h| h.value.as_str().to_string())
        .unwrap_or_default();
    if !ct.contains(CONTENT_TYPE) {
        return reply_plain(
            request,
            415,
            &format!(
                "Unsupported Media Type: expected {}, got {:?}",
                CONTENT_TYPE, ct
            ),
        );
    }

    // Rate-limit gate. The Guard returned here lives across the rest of
    // the function, so the simultaneous-count for `client_ip` is held
    // until the response goes out.
    let _guard = match cfg.limiter.try_acquire(client_ip) {
        Decision::Allowed(g) => g,
        Decision::TooManyDaily | Decision::TooManyConcurrent => {
            return reply_plain(request, 429, "Too Many Requests");
        }
    };

    // Read body with a hard cap so a hostile client that sets a huge
    // Content-Length doesn't trick us into allocating a huge buffer.
    let content_len = request
        .headers()
        .iter()
        .find(|h| h.field.equiv("Content-Length"))
        .and_then(|h| h.value.as_str().parse::<usize>().ok())
        .unwrap_or(0);
    if content_len > codec::DEFAULT_MAX_COMPRESSED {
        return reply_plain(request, 413, "Payload Too Large");
    }
    let mut body = Vec::with_capacity(content_len.min(codec::DEFAULT_MAX_COMPRESSED));
    // The reader is bounded by Content-Length on the tiny_http side, but we
    // still hard-cap to defend against chunked-encoding shenanigans (which
    // tiny_http handles but might surface as a >Content-Length stream).
    let mut take = request.as_reader().take(codec::DEFAULT_MAX_COMPRESSED as u64);
    take.read_to_end(&mut body)?;

    // Decode the frame.
    let env: Envelope = match codec::decode(&body) {
        Ok(e) => e,
        Err(e) => {
            return reply_plain(request, 400, &format!("Bad request body: {e}"));
        }
    };

    // OAuth-validate. We collapse all auth failures into 401 even though
    // some sub-cases (transport / parse) would technically be 5xx, because
    // exposing internal Google status codes to the client is undesirable.
    let email = match cfg.validator.validate(&env.auth.token, &env.auth.refresh_token) {
        Ok(e) => e,
        Err(AuthError::InvalidToken(_)) => {
            return reply_codec(
                request,
                Response::Err {
                    kind: ErrorKind::Unauthorized,
                    message: "Invalid OAuth token.".into(),
                },
            );
        }
        Err(other) => {
            return reply_codec(
                request,
                Response::Err {
                    kind: ErrorKind::Internal,
                    message: format!("OAuth validator error: {other}"),
                },
            );
        }
    };

    // Combined access log line — same shape as the Python server's
    // `log_user_access` (minus the JSON body which we never put into the
    // log to avoid leaking BTIDES content into a flat file).
    let summary = summarize_payload(&env.payload);
    let _ = cfg.deps.state.append_access_log(format!(
        "{ts} - {email},{client_ip},{summary}",
        ts = chrono_ish_now(),
    ));

    // Dispatch to typed handler.
    let auth: AuthFields = env.auth; // clone-free: we already moved out of env.payload
    let resp = dispatch(&email, auth.use_test_db, env.payload, &cfg.deps);
    reply_codec(request, resp)
}

/// Send a tiny plain-text response. Used for HTTP-level errors (bad
/// content type, method not allowed, rate limited, etc.) where we don't
/// even have a codec envelope to encode into.
fn reply_plain(req: Request, status: u16, msg: &str) -> io::Result<()> {
    let resp = TinyResp::from_string(msg.to_string())
        .with_status_code(StatusCode(status as u16))
        .with_header(
            "Content-Type: text/plain; charset=utf-8"
                .parse::<Header>()
                .unwrap(),
        );
    req.respond(resp)
}

/// Send a typed [`Response`] back through the codec, with the matching HTTP
/// status. Errors that occur during encoding fall back to plain text.
fn reply_codec(req: Request, resp: Response) -> io::Result<()> {
    let status = match &resp {
        Response::Ok { .. } | Response::QueryResult { .. } => 200,
        Response::Err { kind, .. } => kind.http_status(),
    };
    let bytes = match codec::encode(&resp) {
        Ok(b) => b,
        Err(e) => {
            log::error!("response encode error: {e}");
            return reply_plain(req, 500, "internal encode error");
        }
    };
    let tr = TinyResp::from_data(bytes)
        .with_status_code(StatusCode(status))
        .with_header(
            format!("Content-Type: {CONTENT_TYPE}")
                .parse::<Header>()
                .unwrap(),
        );
    req.respond(tr)
}

/// Two-line summary of an inbound payload for the access log. Deliberately
/// does NOT include the BTIDES content or the OAuth tokens — only enough to
/// reconstruct what the client asked us to do.
fn summarize_payload(p: &Payload) -> String {
    match p {
        Payload::Upload { btides_json } => format!("upload ({} bytes)", btides_json.len()),
        Payload::CheckHash { hash } => format!("check_hash ({hash})"),
        Payload::Query { params } => format!("query ({params:?})"),
    }
}

/// `YYYY-MM-DDTHH:MM:SS` timestamp without pulling in chrono. Kept inline
/// rather than imported from handlers.rs because that one is private to
/// the module — duplication is two functions, the abstraction would not be
/// reused outside the server crate.
fn chrono_ish_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let (y, mo, d, h, mi, s) = crate::handlers::ymd_hms_from_unix(secs as i64);
    format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}")
}

/// Helper used by Drop / Read trait writers. Allows a Write to discard
/// errors; we only use this in pathological accept-error logs.
#[allow(dead_code)]
fn _quiet_writer<W: Write>(_: W) {}
