//! Google OAuth access-token refresh, mirroring
//! `oauth_helper.AuthClient.refresh_access_token` from the Python tools.
//!
//! Access tokens expire after ~1 hour. The Python client refreshes them
//! transparently before/while talking to the BTIDALPOOL server; this module
//! gives the Rust client the same ability so a slightly-stale token file
//! (e.g. `Analysis/tf`) keeps working without a fresh interactive SSO login.
//!
//! The refresh itself is delegated to the BTIDALPOOL OAuth helper server
//! (`btidalpool.ddns.net:7653/refresh`), which holds the Google
//! `client_secret` and performs the actual token exchange. That endpoint
//! uses a real (LetsEncrypt) certificate, so — unlike the data server on
//! :3567/:3568 with its bundled self-signed cert — this request validates
//! against the normal webpki/system trust roots (ureq's default agent).

use std::path::Path;
use std::time::Duration;

use anyhow::{Context, Result};

/// BTIDALPOOL's Google OAuth2 client ID — identical to the value in
/// `oauth_helper.py` and the SSO redirect server.
pub const CLIENT_ID: &str =
    "934838710114-hrn5hafisthr3eqh7gnr1jka5c5hmjli.apps.googleusercontent.com";

/// The BTIDALPOOL OAuth helper server's refresh endpoint.
pub const DEFAULT_REFRESH_URL: &str = "https://btidalpool.ddns.net:7653/refresh";

/// Refresh against the default endpoint. Returns `Some((access, refresh))`
/// on success, `None` if the endpoint declined (e.g. the refresh token is
/// itself invalid/revoked), or an `Err` only for transport-level failures.
pub fn refresh(refresh_token: &str) -> Result<Option<(String, String)>> {
    refresh_via(DEFAULT_REFRESH_URL, refresh_token)
}

/// Refresh against an explicit URL (the test suite points this at a stub).
pub fn refresh_via(url: &str, refresh_token: &str) -> Result<Option<(String, String)>> {
    // Plain ureq agent → ureq's default rustls config + webpki-roots, which
    // validates the real cert on the OAuth helper server. We do NOT reuse
    // the data-server transport here because that one pins the self-signed
    // data-server cert, which would (correctly) reject :7653's real cert.
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(15))
        .build();
    let resp = agent.post(url).send_json(serde_json::json!({
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }));
    match resp {
        Ok(r) => {
            // The OAuth helper server is Python's http.server, which sends
            // the body and then closes the TCP socket WITHOUT a TLS
            // close_notify. rustls (correctly, per spec) flags that as an
            // "unexpected EOF" when we read past the body. The body itself
            // arrived intact, so read tolerantly: if the only failure is
            // that missing close_notify and we already have bytes, parse
            // them. This mirrors the leniency of Python's urllib, which
            // talks to this same server without complaint.
            let mut reader = r.into_reader();
            let mut buf = Vec::new();
            match std::io::Read::read_to_end(&mut reader, &mut buf) {
                Ok(_) => {}
                Err(e) if !buf.is_empty() && is_unexpected_eof(&e) => {
                    // Tolerated — full body already in `buf`.
                }
                Err(e) => {
                    return Err(anyhow::anyhow!("reading /refresh response: {e}"));
                }
            }
            let v: serde_json::Value =
                serde_json::from_slice(&buf).context("parsing /refresh response JSON")?;
            let token = v.get("token").and_then(|x| x.as_str());
            let new_refresh = v.get("refresh_token").and_then(|x| x.as_str());
            match (token, new_refresh) {
                (Some(t), Some(rt)) => Ok(Some((t.to_string(), rt.to_string()))),
                // 200 but missing fields → treat as a declined refresh.
                _ => Ok(None),
            }
        }
        // 4xx/5xx from the refresh endpoint → refresh declined, not a hard
        // error: the caller falls back to reporting the original Unauthorized.
        Err(ureq::Error::Status(_, _)) => Ok(None),
        Err(ureq::Error::Transport(e)) => {
            Err(anyhow::anyhow!("could not reach refresh endpoint {url}: {e}"))
        }
    }
}

/// True if `e` is the benign "peer closed without TLS close_notify" /
/// unexpected-EOF condition that Python's `http.server` triggers. We only
/// tolerate this when a body has already been read.
fn is_unexpected_eof(e: &std::io::Error) -> bool {
    if e.kind() == std::io::ErrorKind::UnexpectedEof {
        return true;
    }
    // rustls surfaces it with a descriptive message rather than a dedicated
    // ErrorKind in some ureq/rustls versions, so match on the text too.
    let msg = e.to_string();
    msg.contains("close_notify") || msg.contains("unexpected EOF")
}

/// Persist refreshed credentials back to the token file, in the same JSON
/// shape the Python tools read/write (`{"token": ..., "refresh_token": ...}`),
/// so the next invocation starts from the fresh token. Mirrors
/// `oauth_helper`'s write-back behavior.
pub fn persist_token_file(path: &Path, token: &str, refresh_token: &str) -> Result<()> {
    let body = serde_json::json!({ "token": token, "refresh_token": refresh_token });
    let bytes = serde_json::to_vec_pretty(&body)?;
    std::fs::write(path, bytes)
        .with_context(|| format!("writing refreshed token file {path:?}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn persist_round_trips_through_token_file() {
        let td = tempdir().unwrap();
        let p = td.path().join("tf");
        persist_token_file(&p, "ACCESS", "REFRESH").unwrap();
        let v: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&p).unwrap()).unwrap();
        assert_eq!(v["token"], "ACCESS");
        assert_eq!(v["refresh_token"], "REFRESH");
    }
}
