//! Short-lived, stateless BTIDALPOOL session tokens for v4.
//!
//! A Google access token is validated once, then exchanged for an HMAC-SHA256
//! signed token containing only the authenticated email and expiry. OAuth
//! access/refresh tokens are never persisted. An operator-provided signing
//! key keeps sessions valid across restarts; otherwise a cryptographically
//! random in-memory key is generated and sessions safely expire on restart.

use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use hmac::{Hmac, Mac};
use rand::rngs::OsRng;
use rand::RngCore;
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use thiserror::Error;

type HmacSha256 = Hmac<Sha256>;

#[derive(Clone)]
pub struct SessionTokens {
    key: Arc<[u8]>,
    ttl: Duration,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IssuedSession {
    pub token: String,
    pub expires_at_unix: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SessionIdentity {
    pub email: String,
    pub expires_at_unix: u64,
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum SessionError {
    #[error("session token is malformed or has an invalid signature")]
    Invalid,
    #[error("session token has expired")]
    Expired,
    #[error("session signing key must contain at least 32 bytes")]
    WeakKey,
}

#[derive(Serialize, Deserialize)]
struct Claims {
    version: u8,
    subject: String,
    issued_at_unix: u64,
    expires_at_unix: u64,
}

impl SessionTokens {
    pub fn random(ttl: Duration) -> Self {
        let mut key = [0u8; 32];
        OsRng.fill_bytes(&mut key);
        Self {
            key: Arc::from(key),
            ttl,
        }
    }

    pub fn from_key(key: Vec<u8>, ttl: Duration) -> Result<Self, SessionError> {
        if key.len() < 32 {
            return Err(SessionError::WeakKey);
        }
        Ok(Self {
            key: Arc::from(key),
            ttl,
        })
    }

    pub fn issue(&self, email: &str) -> IssuedSession {
        self.issue_at(email, unix_now())
    }

    fn issue_at(&self, email: &str, now: u64) -> IssuedSession {
        let expires_at_unix = now.saturating_add(self.ttl.as_secs());
        let claims = Claims {
            version: 1,
            subject: email.to_ascii_lowercase(),
            issued_at_unix: now,
            expires_at_unix,
        };
        let payload = serde_json::to_vec(&claims).expect("session claims are serializable");
        let payload_b64 = URL_SAFE_NO_PAD.encode(payload);
        let signature = self.sign(payload_b64.as_bytes());
        IssuedSession {
            token: format!("{payload_b64}.{}", URL_SAFE_NO_PAD.encode(signature)),
            expires_at_unix,
        }
    }

    pub fn verify(&self, token: &str) -> Result<SessionIdentity, SessionError> {
        self.verify_at(token, unix_now())
    }

    fn verify_at(&self, token: &str, now: u64) -> Result<SessionIdentity, SessionError> {
        let (payload_b64, signature_b64) = token.split_once('.').ok_or(SessionError::Invalid)?;
        if payload_b64.is_empty() || signature_b64.is_empty() {
            return Err(SessionError::Invalid);
        }
        let signature = URL_SAFE_NO_PAD
            .decode(signature_b64)
            .map_err(|_| SessionError::Invalid)?;
        let mut mac = HmacSha256::new_from_slice(&self.key).map_err(|_| SessionError::Invalid)?;
        mac.update(payload_b64.as_bytes());
        mac.verify_slice(&signature)
            .map_err(|_| SessionError::Invalid)?;

        let payload = URL_SAFE_NO_PAD
            .decode(payload_b64)
            .map_err(|_| SessionError::Invalid)?;
        let claims: Claims = serde_json::from_slice(&payload).map_err(|_| SessionError::Invalid)?;
        if claims.version != 1
            || claims.subject.is_empty()
            || claims.expires_at_unix < claims.issued_at_unix
        {
            return Err(SessionError::Invalid);
        }
        if now >= claims.expires_at_unix {
            return Err(SessionError::Expired);
        }
        Ok(SessionIdentity {
            email: claims.subject,
            expires_at_unix: claims.expires_at_unix,
        })
    }

    fn sign(&self, payload: &[u8]) -> Vec<u8> {
        let mut mac = HmacSha256::new_from_slice(&self.key)
            .expect("HMAC accepts keys of any nonzero practical size");
        mac.update(payload);
        mac.finalize().into_bytes().to_vec()
    }
}

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sessions() -> SessionTokens {
        SessionTokens::from_key(vec![0x42; 32], Duration::from_secs(60)).unwrap()
    }

    #[test]
    fn issue_verify_and_expiry() {
        let sessions = sessions();
        let issued = sessions.issue_at("User@Example.COM", 100);
        let identity = sessions.verify_at(&issued.token, 159).unwrap();
        assert_eq!(identity.email, "user@example.com");
        assert_eq!(identity.expires_at_unix, 160);
        assert_eq!(
            sessions.verify_at(&issued.token, 160),
            Err(SessionError::Expired)
        );
    }

    #[test]
    fn tamper_is_rejected() {
        let sessions = sessions();
        let issued = sessions.issue_at("u@example.com", 100);
        let mut token = issued.token;
        token.replace_range(0..1, "X");
        assert_eq!(sessions.verify_at(&token, 101), Err(SessionError::Invalid));
    }

    #[test]
    fn weak_operator_key_is_rejected() {
        assert!(matches!(
            SessionTokens::from_key(vec![1; 31], Duration::from_secs(60)),
            Err(SessionError::WeakKey)
        ));
    }
}
