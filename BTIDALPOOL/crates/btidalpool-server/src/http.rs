//! HTTP/HTTPS request loop. Uses `tiny_http` with its `ssl-rustls` feature
//! so we don't pull in OpenSSL.
//!
//! Every POST goes through the same pipeline:
//!
//!   1. Route and method check (`POST /v4` is the only protocol endpoint).
//!   2. Content-Type check — POSTs must explicitly select wire version 4.
//!   3. Broad pre-authentication abuse check (per-client-IP).
//!   4. Read body (capped at the wire codec's max compressed size — extra
//!      bytes are discarded and the request is rejected).
//!   5. Decode the codec frame into a [`V4Envelope`].
//!   6. Authenticate Google credentials (session exchange) or validate a
//!      short-lived BTIDALPOOL session.
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
    codec, V4Auth, V4Envelope, V4ErrorKind, V4Payload, V4Response, CONTENT_TYPE,
};
use tiny_http::{Header, Method, Request, Response as TinyResp, Server, StatusCode};

use crate::handlers::{dispatch_v4, Deps};
use crate::oauth::{AuthError, OAuthValidator};
use crate::rate_limit::{ConcurrencyGuard, ConcurrencyLimiter, Decision, Guard, Limiter};
use crate::session::{SessionError, SessionTokens};

/// Server configuration. Built by `main.rs` from CLI flags and handed to
/// [`run`].
pub struct Config {
    pub bind: SocketAddr,
    pub tls: Option<TlsConfig>,
    /// Whether the unauthenticated GET /healthz route is exposed. Production
    /// defaults this off and enables it only for controlled test windows.
    pub enable_healthz: bool,
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
    pub whole_uploads: ConcurrencyLimiter,
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
            whole_uploads: ConcurrencyLimiter::new(2),
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
        enable_healthz: cfg.enable_healthz,
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
    enable_healthz: bool,
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
        return if cfg.enable_healthz {
            reply_plain(request, 200, "ok")
        } else {
            reply_plain(request, 404, "Not Found")
        };
    }

    // The Rust service exposes one protocol route. The original non-Rust
    // service is separate and is intentionally unaffected by this listener.
    if request.method() != &Method::Post {
        return reply_plain(request, 405, "Method Not Allowed");
    }
    if path != "/v4" {
        return reply_plain(request, 404, "Not Found");
    }

    // Content-Type gate.
    let ct = request
        .headers()
        .iter()
        .find(|h| h.field.equiv("Content-Type"))
        .map(|h| h.value.as_str().to_string())
        .unwrap_or_default();
    let expected_content_type = format!("{CONTENT_TYPE}; version=4");
    if !ct
        .split(';')
        .map(str::trim)
        .collect::<Vec<_>>()
        .windows(2)
        .any(|parts| parts[0] == CONTENT_TYPE && parts[1].eq_ignore_ascii_case("version=4"))
    {
        return reply_plain(
            request,
            415,
            &format!(
                "Unsupported Media Type: expected {}, got {:?}",
                expected_content_type, ct
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

    handle_v4(request, body, client_ip, cfg)
}

fn handle_v4(
    request: Request,
    body: Vec<u8>,
    client_ip: std::net::IpAddr,
    cfg: &SharedCfg,
) -> io::Result<()> {
    let env: V4Envelope = match codec::decode_v4(&body) {
        Ok(envelope) => envelope,
        Err(error) => {
            return reply_plain(request, 400, &format!("Bad v4 request body: {error}"));
        }
    };

    if matches!(env.payload, V4Payload::CreateSession) {
        let access_token = match env.auth {
            V4Auth::Google { access_token } => access_token,
            V4Auth::Session { .. } => {
                return reply_v4(
                    request,
                    v4_error(
                        V4ErrorKind::Unauthorized,
                        "create_session requires a Google access token",
                    ),
                )
            }
        };
        let email = match cfg.validator.validate(&access_token, "") {
            Ok(email) => email,
            Err(AuthError::InvalidToken(_)) => {
                return reply_v4(
                    request,
                    v4_error(V4ErrorKind::Unauthorized, "Invalid Google access token."),
                )
            }
            Err(error) => {
                log::error!("Google validation failed during v4 session exchange: {error}");
                return reply_v4(
                    request,
                    v4_error(
                        V4ErrorKind::Internal,
                        "Authentication service temporarily unavailable.",
                    ),
                );
            }
        };
        let _identity_guard = match acquire_identity(cfg, &email) {
            Ok(guard) => guard,
            Err(retry_after) => {
                return reply_v4_retry(
                    request,
                    v4_error(
                        V4ErrorKind::RateLimited,
                        "Authenticated identity rate limit exceeded.",
                    ),
                    retry_after,
                )
            }
        };
        let issued = cfg.sessions.issue(&email);
        let _ = cfg.deps.state.append_access_log(format!(
            "{ts} - {email},{client_ip},v4 create_session",
            ts = chrono_ish_now(),
        ));
        return reply_v4(
            request,
            V4Response::Session {
                token: issued.token,
                expires_at_unix: issued.expires_at_unix,
            },
        );
    }

    let session_token = match env.auth {
        V4Auth::Session { token } => token,
        V4Auth::Google { .. } => {
            return reply_v4(
                request,
                v4_error(
                    V4ErrorKind::Unauthorized,
                    "v4 operations require a BTIDALPOOL session token",
                ),
            )
        }
    };
    let identity = match cfg.sessions.verify(&session_token) {
        Ok(identity) => identity,
        Err(SessionError::Expired) => {
            return reply_v4(
                request,
                v4_error(V4ErrorKind::SessionExpired, "BTIDALPOOL session expired."),
            )
        }
        Err(_) => {
            return reply_v4(
                request,
                v4_error(V4ErrorKind::Unauthorized, "Invalid BTIDALPOOL session."),
            )
        }
    };
    let _identity_guard = match acquire_identity(cfg, &identity.email) {
        Ok(guard) => guard,
        Err(retry_after) => {
            return reply_v4_retry(
                request,
                v4_error(
                    V4ErrorKind::RateLimited,
                    "Authenticated identity rate limit exceeded.",
                ),
                retry_after,
            )
        }
    };
    let _capacity_guards = match acquire_v4_capacity(cfg, &env.payload) {
        Ok(guards) => guards,
        Err(()) => {
            return reply_v4_retry(
                request,
                v4_error(
                    V4ErrorKind::ServerBusy,
                    "Server capacity is temporarily exhausted; retry later.",
                ),
                cfg.overload.retry_after,
            )
        }
    };

    let summary = summarize_v4_payload(&env.payload);
    let response = dispatch_v4(&identity.email, env.payload, &cfg.deps);
    let _ = cfg.deps.state.append_access_log(format!(
        "{ts} - {email},{client_ip},{summary}",
        ts = chrono_ish_now(),
        email = identity.email,
    ));
    reply_v4(request, response)
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

fn acquire_v4_capacity(cfg: &SharedCfg, payload: &V4Payload) -> Result<CapacityGuards, ()> {
    match payload {
        V4Payload::Upload { .. } => acquire_capacity(cfg, &cfg.overload.whole_uploads, 2),
        V4Payload::LegacyQuery { .. } => acquire_capacity(cfg, &cfg.overload.queries, 4),
        V4Payload::NativeQuery { .. } => acquire_capacity(cfg, &cfg.overload.native_queries, 1),
        V4Payload::PutChunk { .. } => {
            let operation = cfg.overload.chunk_puts.try_acquire(1).ok_or(())?;
            Ok(Some((None, operation)))
        }
        V4Payload::Finalize { .. } => acquire_capacity(cfg, &cfg.overload.finalizes, 2),
        V4Payload::CreateSession
        | V4Payload::CheckHash { .. }
        | V4Payload::Manifest { .. }
        | V4Payload::Status { .. } => Ok(None),
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

fn v4_error(kind: V4ErrorKind, message: impl Into<String>) -> V4Response {
    V4Response::Err {
        kind,
        message: message.into(),
        missing_chunks: Vec::new(),
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

fn reply_v4(req: Request, resp: V4Response) -> io::Result<()> {
    reply_v4_inner(req, resp, None)
}

fn reply_v4_retry(
    req: Request,
    resp: V4Response,
    retry_after: std::time::Duration,
) -> io::Result<()> {
    reply_v4_inner(req, resp, Some(retry_after))
}

fn reply_v4_inner(
    req: Request,
    resp: V4Response,
    retry_after: Option<std::time::Duration>,
) -> io::Result<()> {
    let status = match &resp {
        V4Response::Err { kind, .. } => kind.http_status(),
        _ => 200,
    };
    let bytes = match codec::encode_v4(&resp) {
        Ok(bytes) => bytes,
        Err(error) => {
            log::error!("v4 response encode error: {error}");
            return reply_plain(req, 500, "internal encode error");
        }
    };
    let mut response = TinyResp::from_data(bytes)
        .with_status_code(StatusCode(status))
        .with_header(
            format!("Content-Type: {CONTENT_TYPE}; version=4")
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

/// Summary of an inbound payload for the access log. Deliberately
/// does NOT include the BTIDES content or the OAuth tokens — only enough to
/// reconstruct what the client asked us to do.
fn summarize_v4_payload(payload: &V4Payload) -> String {
    match payload {
        V4Payload::CreateSession => "v4 create_session".into(),
        V4Payload::Upload {
            btides_json,
            use_test_db,
        } => format!(
            "v4 upload ({} bytes, test_db={use_test_db})",
            btides_json.len()
        ),
        V4Payload::CheckHash { hash } => format!("v4 check_hash ({hash})"),
        V4Payload::LegacyQuery {
            params,
            use_test_db,
        } => format!("v4 legacy query ({params:?}, test_db={use_test_db})"),
        V4Payload::Manifest {
            content_sha256,
            total_size,
            chunk_sha256,
            use_test_db,
        } => format!(
            "v4 manifest (hash={content_sha256}, size={total_size}, chunks={}, test_db={use_test_db})",
            chunk_sha256.len()
        ),
        V4Payload::PutChunk {
            upload_id,
            index,
            data,
        } => format!(
            "v4 put_chunk (upload_id={upload_id}, index={index}, bytes={})",
            data.len()
        ),
        V4Payload::Status { upload_id } => format!("v4 status (upload_id={upload_id})"),
        V4Payload::Finalize { upload_id } => format!("v4 finalize (upload_id={upload_id})"),
        V4Payload::NativeQuery {
            params,
            use_test_db,
        } => format!("v4 native query ({params:?}, test_db={use_test_db})"),
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
