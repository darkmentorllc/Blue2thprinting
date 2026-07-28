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
//!   3. Broad pre-authentication abuse check (per-client-IP).
//!   4. Read body (capped at the wire codec's max compressed size — extra
//!      bytes are discarded and the request is rejected).
//!   5. Decode the codec frame into an [`Envelope`].
//!   6. Authenticate Google credentials (v1/session exchange) or validate a
//!      short-lived v2 session.
//!   7. Apply the primary authenticated-identity rate limit.
//!   8. Dispatch to the typed handler and encode the matching response.
//!
//! Per-request threading: we accept connections on the main loop and spawn
//! a short-lived `std::thread` per request. The rate limiter bounds the
//! number of in-flight requests per identity and per IP, so the worker-thread
//! count is self-limiting in steady state.

use std::io::{self, Read, Write};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use btidalpool_proto::{
    codec, AuthFields, Envelope, ErrorKind, Payload, Response, V2Auth, V2Envelope, V2ErrorKind,
    V2Payload, V2Response, V3Envelope, V3Payload, V3Response, CONTENT_TYPE,
};
use tiny_http::{Header, Method, Request, Response as TinyResp, Server, StatusCode};

use crate::handlers::{dispatch, dispatch_v2, dispatch_v3, Deps};
use crate::oauth::{AuthError, OAuthValidator};
use crate::rate_limit::{ConcurrencyGuard, ConcurrencyLimiter, Decision, Guard, Limiter};
use crate::session::{SessionError, SessionTokens};

/// Server configuration. Built by `main.rs` from CLI flags and handed to
/// [`run`].
pub struct Config {
    pub bind: SocketAddr,
    pub tls: Option<TlsConfig>,
    pub ip_limiter: Limiter,
    pub identity_limiter: Limiter,
    pub overload: OverloadConfig,
    pub validator: Arc<dyn OAuthValidator>,
    pub sessions: SessionTokens,
    pub deps: Deps,
}

/// Process-wide admission control for memory/CPU-heavy work. Identity and IP
/// limiters answer "is this caller within quota?"; these limits answer "does
/// this small host have capacity right now?".
#[derive(Clone)]
pub struct OverloadConfig {
    /// Shared weighted budget. Legacy queries reserve all four default
    /// units; whole-file uploads/finalizes reserve two; native queries
    /// reserve one. This preserves isolation for the memory-heavy Python
    /// path while allowing four lightweight native queries in parallel.
    pub expensive_work: ConcurrencyLimiter,
    pub v1_uploads: ConcurrencyLimiter,
    pub queries: ConcurrencyLimiter,
    pub native_queries: ConcurrencyLimiter,
    pub chunk_puts: ConcurrencyLimiter,
    pub finalizes: ConcurrencyLimiter,
    pub retry_after: std::time::Duration,
}

impl Default for OverloadConfig {
    fn default() -> Self {
        Self {
            expensive_work: ConcurrencyLimiter::new(4),
            v1_uploads: ConcurrencyLimiter::new(2),
            queries: ConcurrencyLimiter::new(1),
            native_queries: ConcurrencyLimiter::new(4),
            chunk_puts: ConcurrencyLimiter::new(4),
            finalizes: ConcurrencyLimiter::new(2),
            retry_after: std::time::Duration::from_secs(2),
        }
    }
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
        ip_limiter: cfg.ip_limiter,
        identity_limiter: cfg.identity_limiter,
        overload: cfg.overload,
        validator: cfg.validator,
        sessions: cfg.sessions,
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
        None => Server::http(cfg.bind).map_err(|e| anyhow::anyhow!("tiny_http::http: {e}")),
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
    ip_limiter: Limiter,
    identity_limiter: Limiter,
    overload: OverloadConfig,
    validator: Arc<dyn OAuthValidator>,
    sessions: SessionTokens,
    deps: Deps,
}

fn handle(mut request: Request, cfg: &SharedCfg) -> io::Result<()> {
    let client_ip = request.remote_addr().map(|a| a.ip()).unwrap_or_else(|| {
        // Falls back to a sentinel address rather than failing the request,
        // which matches `tiny_http`'s own pattern of always producing a peer.
        std::net::IpAddr::from([127, 0, 0, 1])
    });

    let path = request.url().split('?').next().unwrap_or("/").to_string();
    if request.method() == &Method::Get && path == "/healthz" {
        return reply_plain(request, 200, "ok");
    }

    // Method gate — v1 retains the old Python server's POST-only behavior.
    if request.method() != &Method::Post {
        return reply_plain(request, 405, "Method Not Allowed");
    }
    if path != "/" && path != "/v2" && path != "/v3" {
        return reply_plain(request, 404, "Not Found");
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

    // Broad pre-authentication IP gate. Authenticated identity limits below
    // are the primary quota; this only bounds abusive unauthenticated traffic.
    let _ip_guard = match cfg.ip_limiter.try_acquire(format!("ip:{client_ip}")) {
        Decision::Allowed(g) => g,
        Decision::TooManyDaily { retry_after } | Decision::TooManyConcurrent { retry_after } => {
            return reply_plain_retry(request, "Too Many Requests", retry_after);
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
    let mut take = request
        .as_reader()
        .take(codec::DEFAULT_MAX_COMPRESSED as u64 + 1);
    take.read_to_end(&mut body)?;
    if body.len() > codec::DEFAULT_MAX_COMPRESSED {
        return reply_plain(request, 413, "Payload Too Large");
    }

    match path.as_str() {
        "/v2" => handle_v2(request, body, client_ip, cfg),
        "/v3" => handle_v3(request, body, client_ip, cfg),
        _ => handle_v1(request, body, client_ip, cfg),
    }
}

fn handle_v1(
    request: Request,
    body: Vec<u8>,
    client_ip: std::net::IpAddr,
    cfg: &SharedCfg,
) -> io::Result<()> {
    let env: Envelope = match codec::decode(&body) {
        Ok(e) => e,
        Err(e) => {
            return reply_plain(request, 400, &format!("Bad request body: {e}"));
        }
    };

    let email = match cfg
        .validator
        .validate(&env.auth.token, &env.auth.refresh_token)
    {
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

    let _identity_guard = match acquire_identity(cfg, &email) {
        Ok(guard) => guard,
        Err(retry_after) => {
            return reply_codec_retry(
                request,
                Response::Err {
                    kind: ErrorKind::RateLimited,
                    message: "Authenticated identity rate limit exceeded.".into(),
                },
                retry_after,
            )
        }
    };

    let _capacity_guards = match acquire_v1_capacity(cfg, &env.payload) {
        Ok(guards) => guards,
        Err(()) => {
            return reply_codec_retry_status(
                request,
                Response::Err {
                    // Keep the existing v1 enum tag so deployed v1 clients
                    // can decode the body; HTTP 503 distinguishes capacity
                    // overload from the caller-quota HTTP 429.
                    kind: ErrorKind::RateLimited,
                    message: "Server capacity is temporarily exhausted; retry later.".into(),
                },
                cfg.overload.retry_after,
                503,
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

fn handle_v2(
    request: Request,
    body: Vec<u8>,
    client_ip: std::net::IpAddr,
    cfg: &SharedCfg,
) -> io::Result<()> {
    let env: V2Envelope = match codec::decode_v2(&body) {
        Ok(envelope) => envelope,
        Err(error) => {
            return reply_plain(request, 400, &format!("Bad v2 request body: {error}"));
        }
    };

    if matches!(env.payload, V2Payload::CreateSession) {
        let access_token = match env.auth {
            V2Auth::Google { access_token } => access_token,
            V2Auth::Session { .. } => {
                return reply_v2(
                    request,
                    v2_error(
                        V2ErrorKind::Unauthorized,
                        "create_session requires a Google access token",
                    ),
                )
            }
        };
        let email = match cfg.validator.validate(&access_token, "") {
            Ok(email) => email,
            Err(AuthError::InvalidToken(_)) => {
                return reply_v2(
                    request,
                    v2_error(V2ErrorKind::Unauthorized, "Invalid Google access token."),
                )
            }
            Err(error) => {
                log::error!("Google validation failed during v2 session exchange: {error}");
                return reply_v2(
                    request,
                    v2_error(
                        V2ErrorKind::Internal,
                        "Authentication service temporarily unavailable.",
                    ),
                );
            }
        };
        let _identity_guard = match acquire_identity(cfg, &email) {
            Ok(guard) => guard,
            Err(retry_after) => {
                return reply_v2_retry(
                    request,
                    v2_error(
                        V2ErrorKind::RateLimited,
                        "Authenticated identity rate limit exceeded.",
                    ),
                    retry_after,
                )
            }
        };
        let issued = cfg.sessions.issue(&email);
        let _ = cfg.deps.state.append_access_log(format!(
            "{ts} - {email},{client_ip},v2 create_session",
            ts = chrono_ish_now(),
        ));
        return reply_v2(
            request,
            V2Response::Session {
                token: issued.token,
                expires_at_unix: issued.expires_at_unix,
            },
        );
    }

    let session_token = match env.auth {
        V2Auth::Session { token } => token,
        V2Auth::Google { .. } => {
            return reply_v2(
                request,
                v2_error(
                    V2ErrorKind::Unauthorized,
                    "v2 upload operations require a BTIDALPOOL session token",
                ),
            )
        }
    };
    let identity = match cfg.sessions.verify(&session_token) {
        Ok(identity) => identity,
        Err(SessionError::Expired) => {
            return reply_v2(
                request,
                v2_error(V2ErrorKind::SessionExpired, "BTIDALPOOL session expired."),
            )
        }
        Err(_) => {
            return reply_v2(
                request,
                v2_error(V2ErrorKind::Unauthorized, "Invalid BTIDALPOOL session."),
            )
        }
    };
    let _identity_guard = match acquire_identity(cfg, &identity.email) {
        Ok(guard) => guard,
        Err(retry_after) => {
            return reply_v2_retry(
                request,
                v2_error(
                    V2ErrorKind::RateLimited,
                    "Authenticated identity rate limit exceeded.",
                ),
                retry_after,
            )
        }
    };

    let _capacity_guards = match acquire_v2_capacity(cfg, &env.payload) {
        Ok(guards) => guards,
        Err(()) => {
            return reply_v2_retry(
                request,
                v2_error(
                    V2ErrorKind::ServerBusy,
                    "Server capacity is temporarily exhausted; retry later.",
                ),
                cfg.overload.retry_after,
            )
        }
    };

    let summary = summarize_v2_payload(&env.payload);
    let _ = cfg.deps.state.append_access_log(format!(
        "{ts} - {email},{client_ip},{summary}",
        ts = chrono_ish_now(),
        email = identity.email,
    ));
    let response = dispatch_v2(&identity.email, env.payload, &cfg.deps);
    reply_v2(request, response)
}

fn handle_v3(
    request: Request,
    body: Vec<u8>,
    client_ip: std::net::IpAddr,
    cfg: &SharedCfg,
) -> io::Result<()> {
    let env: V3Envelope = match codec::decode_v3(&body) {
        Ok(envelope) => envelope,
        Err(error) => {
            return reply_plain(request, 400, &format!("Bad v3 request body: {error}"));
        }
    };
    let session_token = match env.auth {
        V2Auth::Session { token } => token,
        V2Auth::Google { .. } => {
            return reply_v3(
                request,
                v3_error(
                    V2ErrorKind::Unauthorized,
                    "v3 queries require a BTIDALPOOL session token",
                ),
            )
        }
    };
    let identity = match cfg.sessions.verify(&session_token) {
        Ok(identity) => identity,
        Err(SessionError::Expired) => {
            return reply_v3(
                request,
                v3_error(V2ErrorKind::SessionExpired, "BTIDALPOOL session expired."),
            )
        }
        Err(_) => {
            return reply_v3(
                request,
                v3_error(V2ErrorKind::Unauthorized, "Invalid BTIDALPOOL session."),
            )
        }
    };
    let _identity_guard = match acquire_identity(cfg, &identity.email) {
        Ok(guard) => guard,
        Err(retry_after) => {
            return reply_v3_retry(
                request,
                v3_error(
                    V2ErrorKind::RateLimited,
                    "Authenticated identity rate limit exceeded.",
                ),
                retry_after,
            )
        }
    };
    let _capacity_guards = match acquire_v3_capacity(cfg, &env.payload) {
        Ok(guards) => guards,
        Err(()) => {
            return reply_v3_retry(
                request,
                v3_error(
                    V2ErrorKind::ServerBusy,
                    "Server capacity is temporarily exhausted; retry later.",
                ),
                cfg.overload.retry_after,
            )
        }
    };
    let summary = summarize_v3_payload(&env.payload);
    let response = dispatch_v3(env.payload, &cfg.deps);
    let outcome = match &response {
        V3Response::QueryResult { query } => format!(
            "devices={}, rows={}, truncated={}",
            query.devices.len(),
            query.total_rows,
            query.truncated
        ),
        V3Response::Err { kind, .. } => format!("error={kind:?}"),
    };
    let _ = cfg.deps.state.append_access_log(format!(
        "{ts} - {email},{client_ip},{summary}, {outcome}",
        ts = chrono_ish_now(),
        email = identity.email,
    ));
    log::info!("v3 query completed for {}: {outcome}", identity.email);
    reply_v3(request, response)
}

fn acquire_identity(cfg: &SharedCfg, email: &str) -> Result<Guard, std::time::Duration> {
    match cfg
        .identity_limiter
        .try_acquire(format!("identity:{}", email.to_ascii_lowercase()))
    {
        Decision::Allowed(guard) => Ok(guard),
        Decision::TooManyDaily { retry_after } | Decision::TooManyConcurrent { retry_after } => {
            Err(retry_after)
        }
    }
}

type CapacityGuards = Option<(Option<ConcurrencyGuard>, ConcurrencyGuard)>;

fn acquire_v1_capacity(cfg: &SharedCfg, payload: &Payload) -> Result<CapacityGuards, ()> {
    let (operation_limiter, expensive_permits) = match payload {
        Payload::Upload { .. } => (&cfg.overload.v1_uploads, 2),
        Payload::Query { .. } => (&cfg.overload.queries, 4),
        Payload::CheckHash { .. } => return Ok(None),
    };
    acquire_capacity(cfg, operation_limiter, expensive_permits)
}

fn acquire_v2_capacity(cfg: &SharedCfg, payload: &V2Payload) -> Result<CapacityGuards, ()> {
    match payload {
        V2Payload::PutChunk { .. } => {
            let operation = cfg.overload.chunk_puts.try_acquire(1).ok_or(())?;
            Ok(Some((None, operation)))
        }
        V2Payload::Finalize { .. } => acquire_capacity(cfg, &cfg.overload.finalizes, 2),
        V2Payload::CreateSession | V2Payload::Manifest { .. } | V2Payload::Status { .. } => {
            Ok(None)
        }
    }
}

fn acquire_v3_capacity(cfg: &SharedCfg, payload: &V3Payload) -> Result<CapacityGuards, ()> {
    match payload {
        V3Payload::Query { .. } => acquire_capacity(cfg, &cfg.overload.native_queries, 1),
    }
}

fn acquire_capacity(
    cfg: &SharedCfg,
    operation_limiter: &ConcurrencyLimiter,
    expensive_permits: u32,
) -> Result<CapacityGuards, ()> {
    let operation = operation_limiter.try_acquire(1).ok_or(())?;
    let expensive = cfg
        .overload
        .expensive_work
        .try_acquire(expensive_permits)
        .ok_or(())?;
    Ok(Some((Some(expensive), operation)))
}

fn v2_error(kind: V2ErrorKind, message: impl Into<String>) -> V2Response {
    V2Response::Err {
        kind,
        message: message.into(),
        missing_chunks: Vec::new(),
    }
}

fn v3_error(kind: V2ErrorKind, message: impl Into<String>) -> V3Response {
    V3Response::Err {
        kind,
        message: message.into(),
    }
}

/// Send a tiny plain-text response. Used for HTTP-level errors (bad
/// content type, method not allowed, rate limited, etc.) where we don't
/// even have a codec envelope to encode into.
fn reply_plain(req: Request, status: u16, msg: &str) -> io::Result<()> {
    let resp = TinyResp::from_string(msg.to_string())
        .with_status_code(StatusCode(status))
        .with_header(
            "Content-Type: text/plain; charset=utf-8"
                .parse::<Header>()
                .unwrap(),
        );
    req.respond(resp)
}

fn reply_plain_retry(req: Request, msg: &str, retry_after: std::time::Duration) -> io::Result<()> {
    let resp = TinyResp::from_string(msg.to_string())
        .with_status_code(StatusCode(429))
        .with_header(
            "Content-Type: text/plain; charset=utf-8"
                .parse::<Header>()
                .unwrap(),
        )
        .with_header(retry_after_header(retry_after));
    req.respond(resp)
}

/// Send a typed [`Response`] back through the codec, with the matching HTTP
/// status. Errors that occur during encoding fall back to plain text.
fn reply_codec(req: Request, resp: Response) -> io::Result<()> {
    reply_codec_inner(req, resp, None, None)
}

fn reply_codec_retry(
    req: Request,
    resp: Response,
    retry_after: std::time::Duration,
) -> io::Result<()> {
    reply_codec_inner(req, resp, Some(retry_after), None)
}

fn reply_codec_retry_status(
    req: Request,
    resp: Response,
    retry_after: std::time::Duration,
    status: u16,
) -> io::Result<()> {
    reply_codec_inner(req, resp, Some(retry_after), Some(status))
}

fn reply_codec_inner(
    req: Request,
    resp: Response,
    retry_after: Option<std::time::Duration>,
    status_override: Option<u16>,
) -> io::Result<()> {
    let status = status_override.unwrap_or_else(|| match &resp {
        Response::Ok { .. } | Response::QueryResult { .. } => 200,
        Response::Err { kind, .. } => kind.http_status(),
    });
    let bytes = match codec::encode(&resp) {
        Ok(b) => b,
        Err(e) => {
            log::error!("response encode error: {e}");
            return reply_plain(req, 500, "internal encode error");
        }
    };
    let mut tr = TinyResp::from_data(bytes)
        .with_status_code(StatusCode(status))
        .with_header(
            format!("Content-Type: {CONTENT_TYPE}")
                .parse::<Header>()
                .unwrap(),
        );
    if let Some(duration) = retry_after {
        tr.add_header(retry_after_header(duration));
    }
    req.respond(tr)
}

fn reply_v2(req: Request, resp: V2Response) -> io::Result<()> {
    reply_v2_inner(req, resp, None)
}

fn reply_v2_retry(
    req: Request,
    resp: V2Response,
    retry_after: std::time::Duration,
) -> io::Result<()> {
    reply_v2_inner(req, resp, Some(retry_after))
}

fn reply_v2_inner(
    req: Request,
    resp: V2Response,
    retry_after: Option<std::time::Duration>,
) -> io::Result<()> {
    let status = match &resp {
        V2Response::Err { kind, .. } => kind.http_status(),
        _ => 200,
    };
    let bytes = match codec::encode_v2(&resp) {
        Ok(bytes) => bytes,
        Err(error) => {
            log::error!("v2 response encode error: {error}");
            return reply_plain(req, 500, "internal encode error");
        }
    };
    let mut response = TinyResp::from_data(bytes)
        .with_status_code(StatusCode(status))
        .with_header(
            format!("Content-Type: {CONTENT_TYPE}; version=2")
                .parse::<Header>()
                .unwrap(),
        );
    if let Some(duration) = retry_after {
        response.add_header(retry_after_header(duration));
    }
    req.respond(response)
}

fn reply_v3(req: Request, resp: V3Response) -> io::Result<()> {
    reply_v3_inner(req, resp, None)
}

fn reply_v3_retry(
    req: Request,
    resp: V3Response,
    retry_after: std::time::Duration,
) -> io::Result<()> {
    reply_v3_inner(req, resp, Some(retry_after))
}

fn reply_v3_inner(
    req: Request,
    resp: V3Response,
    retry_after: Option<std::time::Duration>,
) -> io::Result<()> {
    let status = match &resp {
        V3Response::Err { kind, .. } => kind.http_status(),
        V3Response::QueryResult { .. } => 200,
    };
    let bytes = match codec::encode_v3(&resp) {
        Ok(bytes) => bytes,
        Err(error) => {
            log::error!("v3 response encode error: {error}");
            return reply_plain(req, 500, "internal encode error");
        }
    };
    let mut response = TinyResp::from_data(bytes)
        .with_status_code(StatusCode(status))
        .with_header(
            format!("Content-Type: {CONTENT_TYPE}; version=3")
                .parse::<Header>()
                .unwrap(),
        );
    if let Some(duration) = retry_after {
        response.add_header(retry_after_header(duration));
    }
    req.respond(response)
}

fn retry_after_header(duration: std::time::Duration) -> Header {
    let seconds = duration
        .as_secs()
        .saturating_add(u64::from(duration.subsec_nanos() > 0))
        .max(1);
    format!("Retry-After: {seconds}").parse::<Header>().unwrap()
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

fn summarize_v2_payload(payload: &V2Payload) -> String {
    match payload {
        V2Payload::CreateSession => "v2 create_session".into(),
        V2Payload::Manifest {
            content_sha256,
            total_size,
            chunk_sha256,
            use_test_db,
        } => format!(
            "v2 manifest (hash={content_sha256}, size={total_size}, chunks={}, test_db={use_test_db})",
            chunk_sha256.len()
        ),
        V2Payload::PutChunk {
            upload_id,
            index,
            data,
        } => format!(
            "v2 put_chunk (upload_id={upload_id}, index={index}, bytes={})",
            data.len()
        ),
        V2Payload::Status { upload_id } => {
            format!("v2 status (upload_id={upload_id})")
        }
        V2Payload::Finalize { upload_id } => {
            format!("v2 finalize (upload_id={upload_id})")
        }
    }
}

fn summarize_v3_payload(payload: &V3Payload) -> String {
    match payload {
        V3Payload::Query {
            params,
            use_test_db,
        } => format!("v3 native query ({params:?}, test_db={use_test_db})"),
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
