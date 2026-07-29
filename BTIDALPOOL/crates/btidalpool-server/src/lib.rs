//! BTIDALPOOL server library.
//!
//! See `main.rs` for the binary entry point. This crate exposes the
//! internal modules as `pub` so the integration test in
//! `tests/loopback.rs` can drive the server in-process with mocked
//! dependencies — no real OAuth / MySQL / Tell_Me_Everything required.

pub mod handlers;
pub mod http;
pub mod ingest;
pub mod native_query;
pub mod oauth;
pub mod query;
pub mod rate_limit;
pub mod resumable;
pub mod session;
pub mod state;
