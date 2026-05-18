//! Google OAuth validation behind a trait.
//!
//! Production code uses [`GoogleOAuthValidator`], which calls
//! `https://www.googleapis.com/oauth2/v2/userinfo` with `Authorization:
//! Bearer <token>` and pulls the `email` field out of the response — the
//! same call the Python server makes via the `googleapiclient` library.
//!
//! Tests use [`MockOAuthValidator`], which just returns a canned email and
//! never touches the network. This keeps the test suite from needing a
//! real Google account or internet access.

use std::time::Duration;

use serde::Deserialize;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AuthError {
    #[error("invalid or expired OAuth token (Google returned status {0})")]
    InvalidToken(u16),
    #[error("could not contact Google: {0}")]
    Transport(String),
    #[error("malformed Google userinfo response: {0}")]
    Parse(String),
}

/// What every OAuth validator must do: given a token (and a refresh token,
/// which the server only uses for diagnostics — refresh is the client's job),
/// either return the authenticated user's email address or fail.
///
/// Implementations must be `Send + Sync` so the server can stash one inside
/// an `Arc` and share it across request-handling threads.
pub trait OAuthValidator: Send + Sync {
    fn validate(&self, token: &str, refresh_token: &str) -> Result<String, AuthError>;
}

/// Google userinfo endpoint URL. Pulled out as a const so [`GoogleOAuthValidator`]
/// can be unit-tested against a stub URL if we ever need to (currently we just
/// use [`MockOAuthValidator`] in tests, which short-circuits the HTTP layer
/// entirely).
const USERINFO_URL: &str = "https://www.googleapis.com/oauth2/v2/userinfo";

/// Real Google validator. Single HTTP round trip per request, with a short
/// connect/read timeout so a slow Google response can't tie up a server
/// thread for long.
pub struct GoogleOAuthValidator {
    agent: ureq::Agent,
}

impl Default for GoogleOAuthValidator {
    fn default() -> Self {
        Self::new()
    }
}

impl GoogleOAuthValidator {
    pub fn new() -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout(Duration::from_secs(8))
            .build();
        Self { agent }
    }
}

#[derive(Debug, Deserialize)]
struct UserInfo {
    email: Option<String>,
}

impl OAuthValidator for GoogleOAuthValidator {
    fn validate(&self, token: &str, _refresh_token: &str) -> Result<String, AuthError> {
        let resp = self
            .agent
            .get(USERINFO_URL)
            .set("Authorization", &format!("Bearer {token}"))
            .call();
        let resp = match resp {
            Ok(r) => r,
            Err(ureq::Error::Status(code, _)) => {
                // 401/403 means the token is bad. Anything else is unexpected
                // but still "invalid token" from the server's perspective —
                // we don't want to leak Google's internal status codes to the
                // client; the Python server collapsed all of these to 400.
                return Err(AuthError::InvalidToken(code));
            }
            Err(e) => return Err(AuthError::Transport(e.to_string())),
        };
        let info: UserInfo = resp
            .into_json()
            .map_err(|e| AuthError::Parse(e.to_string()))?;
        match info.email {
            Some(e) => Ok(e),
            None => Err(AuthError::Parse(
                "userinfo response did not include 'email'".into(),
            )),
        }
    }
}

/// Test-only validator that returns a preconfigured email if the token
/// matches the preconfigured "good" token, and an `InvalidToken` otherwise.
/// Lets unit and integration tests cover both happy-path and 401 branches
/// without standing up a Google account.
pub struct MockOAuthValidator {
    pub good_token: String,
    pub email: String,
}

impl OAuthValidator for MockOAuthValidator {
    fn validate(&self, token: &str, _refresh_token: &str) -> Result<String, AuthError> {
        if token == self.good_token {
            Ok(self.email.clone())
        } else {
            Err(AuthError::InvalidToken(401))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mock_validator_returns_email_for_good_token() {
        let v = MockOAuthValidator {
            good_token: "tok".into(),
            email: "u@example.com".into(),
        };
        assert_eq!(v.validate("tok", "rt").unwrap(), "u@example.com");
    }

    #[test]
    fn mock_validator_rejects_bad_token() {
        let v = MockOAuthValidator {
            good_token: "tok".into(),
            email: "u@example.com".into(),
        };
        let err = v.validate("nope", "rt").unwrap_err();
        assert!(matches!(err, AuthError::InvalidToken(401)));
    }
}
