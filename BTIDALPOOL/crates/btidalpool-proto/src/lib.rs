//! BTIDALPOOL wire protocol.
//!
//! This crate is the *only* place that defines the on-the-wire encoding for
//! BTIDALPOOL requests and responses. Both the Rust server
//! (`btidalpool-server`) and the Rust client (`btidalpool-client`) depend on
//! it; if a wire-format change is needed, it happens here once and propagates
//! everywhere.
//!
//! The protocol is intentionally minimal:
//!
//!   * Transport: HTTPS POST. (The HTTP/TLS layer is the server's concern,
//!     not this crate's.)
//!   * Body: a single CBOR-encoded [`wire::Envelope`] (request) or
//!     [`wire::Response`] (response), wrapped in the framing format defined
//!     in [`codec`] (4-byte magic + 1-byte version + 4-byte declared length
//!     + zstd-compressed CBOR).
//!   * Safety: the codec enforces hard caps on both compressed input size
//!     and decompressed output size, and the decompressor aborts the moment
//!     the running output exceeds the cap — so a malicious sender cannot
//!     consume hundreds of MB of server memory by sending a few KB of
//!     compressed data.
//!
//! Versioning: bump [`codec::WIRE_VERSION`] on any breaking change. The
//! decoder rejects frames with any unknown version, so a server / client
//! mismatch produces a clean error instead of silent corruption.

pub mod codec;
pub mod hash;
pub mod wire;

pub use codec::{decode, decode_with_caps, encode, encode_with_caps, CodecError};
pub use hash::canonical_sha1;
pub use wire::{AuthFields, Envelope, ErrorKind, Payload, QueryParams, Response};

/// HTTP Content-Type used for all BTIDALPOOL request and response bodies.
/// Servers and clients check this so a stray `application/json` POST to the
/// new endpoint (e.g. an old Python client hitting a new Rust server) is
/// rejected cleanly with a clear error instead of being mis-parsed.
pub const CONTENT_TYPE: &str = "application/x-btidalpool-cbor-zstd";
