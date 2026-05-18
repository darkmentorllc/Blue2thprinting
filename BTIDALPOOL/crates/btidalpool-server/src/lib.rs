//! BTIDALPOOL server library.
//!
//! See `main.rs` for the binary entry point. This crate exposes the
//! internal modules as `pub` so the integration test in
//! `tests/loopback.rs` can drive the server in-process with mocked
//! dependencies — no real OAuth / MySQL / Tell_Me_Everything required.

pub mod handlers;
pub mod http;
pub mod ingest;
pub mod oauth;
pub mod query;
pub mod rate_limit;
pub mod state;

use btidalpool_proto::{ErrorKind, Response};

/// Wrap an error category + human-readable message into a [`Response::Err`]
/// suitable for sending straight back to the client. Centralized here so
/// the server never accidentally invents a fresh format string for the
/// same condition in two different request handlers.
pub fn err_response(kind: ErrorKind, message: impl Into<String>) -> Response {
    Response::Err {
        kind,
        message: message.into(),
    }
}

/// Build a plain-text "ok" response. Used for the upload + check_hash code
/// paths where there's no structured payload to return — just a confirmation
/// message that the old Python clients used to render verbatim.
pub fn ok_response(message: impl Into<String>) -> Response {
    Response::Ok {
        message: message.into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn err_response_carries_kind_and_message() {
        let r = err_response(ErrorKind::RateLimited, "slow down");
        match r {
            Response::Err { kind, message } => {
                assert_eq!(kind, ErrorKind::RateLimited);
                assert_eq!(message, "slow down");
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn ok_response_carries_message() {
        let r = ok_response("done");
        match r {
            Response::Ok { message } => assert_eq!(message, "done"),
            _ => panic!("wrong variant"),
        }
    }
}
