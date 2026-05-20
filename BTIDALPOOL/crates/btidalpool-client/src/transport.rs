//! Synchronous HTTPS transport for the BTIDALPOOL client.
//!
//! Uses `ureq` (sync, blocking) instead of `reqwest` (async, tokio) because
//! the client's control flow is one-shot per invocation — the binary either
//! runs an upload or a query, then exits. No event loop justified.
//!
//! Server certificate trust (default mirrors the old Python client):
//!   * Default ([`CertTrust::BundledPin`]) pins to the BTIDALPOOL server's
//!     self-signed certificate, which is compiled into this binary via
//!     `include_bytes!`. This reproduces the Python client's
//!     `verify='./btidalpool.ddns.net.crt'` behavior so `btidalpool-client`
//!     talks to the production server out of the box with no flags — but
//!     without depending on the current working directory the way the
//!     relative-path Python version did.
//!   * `--system-roots` ([`CertTrust::System`]) uses the OS trust store,
//!     for the day the server moves to a publicly-trusted (e.g. LetsEncrypt)
//!     certificate.
//!   * `--insecure` ([`CertTrust::Insecure`]) accepts any cert. Local
//!     end-to-end testing only.
//!   * [`CertTrust::Pinned`] pins a caller-supplied PEM file. There is no
//!     CLI flag for it (the bundled default covers production); it exists
//!     only as a Rust API for the loopback QA test, which needs to pin the
//!     self-signed cert it mints per-run — analogous to `--insecure` being
//!     retained for QA.

use std::io::Read;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use btidalpool_proto::{codec, Envelope, Response, CONTENT_TYPE};
use rustls::{ClientConfig, RootCertStore};

/// The BTIDALPOOL production server's self-signed TLS certificate, compiled
/// into the binary. This is the same `Analysis/btidalpool.ddns.net.crt` the
/// Python client pinned against; it is a *public* certificate (no private
/// key), so embedding it is safe. Pinned by default — see [`CertTrust`].
///
/// Path is relative to this source file:
/// `BTIDALPOOL/crates/btidalpool-client/src/` → up four → repo root →
/// `Analysis/btidalpool.ddns.net.crt`.
const BUNDLED_CA_PEM: &[u8] = include_bytes!("../../../../Analysis/btidalpool.ddns.net.crt");

pub struct Transport {
    agent: ureq::Agent,
    url: String,
}

/// How the client should trust the server's TLS certificate.
pub enum CertTrust {
    /// Default: pin to the BTIDALPOOL server cert compiled into this binary
    /// ([`BUNDLED_CA_PEM`]). Mirrors the Python client's default of
    /// `verify=./btidalpool.ddns.net.crt`.
    BundledPin,
    /// Use the OS trust roots (for a server with a publicly-trusted cert).
    System,
    /// Pin a single PEM-encoded certificate (or chain) from a file. No CLI
    /// flag exposes this — it is a Rust API for the loopback QA test, which
    /// pins the self-signed cert it generates per run.
    Pinned { ca_pem_path: std::path::PathBuf },
    /// Accept any cert. Local tests only — never the default.
    Insecure,
}

impl Transport {
    /// Build a transport pinned to `url` with the given cert trust policy.
    pub fn new(url: impl Into<String>, trust: CertTrust) -> Result<Self> {
        ensure_crypto_provider_installed();
        let builder = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_secs(10))
            .timeout(Duration::from_secs(120));
        let builder = match trust {
            CertTrust::BundledPin => {
                let roots = roots_from_pem(BUNDLED_CA_PEM)
                    .context("loading the bundled BTIDALPOOL server certificate")?;
                let cfg = ClientConfig::builder()
                    .with_root_certificates(roots)
                    .with_no_client_auth();
                builder.tls_config(Arc::new(cfg))
            }
            CertTrust::System => builder,
            CertTrust::Pinned { ca_pem_path } => {
                let bytes = std::fs::read(&ca_pem_path)
                    .with_context(|| format!("reading CA pem {ca_pem_path:?}"))?;
                let roots = roots_from_pem(&bytes)
                    .with_context(|| format!("parsing CA pem {ca_pem_path:?}"))?;
                let cfg = ClientConfig::builder()
                    .with_root_certificates(roots)
                    .with_no_client_auth();
                builder.tls_config(Arc::new(cfg))
            }
            CertTrust::Insecure => {
                let cfg = insecure_client_config();
                builder.tls_config(Arc::new(cfg))
            }
        };
        Ok(Self {
            agent: builder.build(),
            url: url.into(),
        })
    }

    /// POST one [`Envelope`] and return the decoded [`Response`].
    pub fn round_trip(&self, env: &Envelope) -> Result<Response> {
        let body = codec::encode(env).context("encoding envelope")?;
        let resp = self
            .agent
            .post(&self.url)
            .set("Content-Type", CONTENT_TYPE)
            .send_bytes(&body);

        // For HTTP-level errors (4xx/5xx) we still want to look at the
        // body — the server returns a structured Response::Err inside the
        // codec frame for most error categories, with the matching HTTP
        // status. ureq raises Status(...) on 4xx/5xx by default, so handle
        // that as a "still parse the body" case.
        let resp = match resp {
            Ok(r) => r,
            Err(ureq::Error::Status(_code, r)) => r,
            Err(ureq::Error::Transport(t)) => {
                anyhow::bail!("transport error talking to {}: {t}", self.url)
            }
        };

        // Pull the body bytes regardless of the content type — we want a
        // clean error message if the server returned text/plain instead of
        // our codec format (e.g. an HTTP 415 because the URL is wrong).
        let ct = resp.header("Content-Type").unwrap_or("").to_string();
        let mut buf = Vec::new();
        resp.into_reader().read_to_end(&mut buf)?;

        if ct.contains(CONTENT_TYPE) {
            let decoded: Response = codec::decode(&buf).context("decoding response envelope")?;
            Ok(decoded)
        } else {
            let txt = String::from_utf8_lossy(&buf);
            anyhow::bail!(
                "server returned non-codec Content-Type {:?} (body: {})",
                ct,
                txt
            );
        }
    }
}

/// Build a [`RootCertStore`] from a PEM blob (one or more certificates).
/// Shared by the bundled-cert path and the QA-only `Pinned` path so the
/// two can't drift apart. Errors if the PEM parses to zero certs.
fn roots_from_pem(pem: &[u8]) -> Result<RootCertStore> {
    let mut roots = RootCertStore::empty();
    let mut cursor = std::io::Cursor::new(pem);
    for cert in rustls_pemfile::certs(&mut cursor) {
        let cert = cert.context("parsing CA certificate")?;
        roots.add(cert).context("registering CA certificate")?;
    }
    if roots.is_empty() {
        anyhow::bail!("PEM contained no certificates");
    }
    Ok(roots)
}

/// Idempotently install rustls's default `ring` crypto provider. Safe to
/// call from any thread, any number of times — `install_default` returns
/// `Err` if a provider is already installed, which we ignore.
fn ensure_crypto_provider_installed() {
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let _ = rustls::crypto::ring::default_provider().install_default();
    });
}

/// Build a rustls ClientConfig that accepts any server certificate. Behind
/// `--insecure` for local loopback testing only.
fn insecure_client_config() -> ClientConfig {
    use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
    use rustls::pki_types::{CertificateDer, ServerName, UnixTime};
    use rustls::{DigitallySignedStruct, SignatureScheme};

    #[derive(Debug)]
    struct AcceptAll;
    impl ServerCertVerifier for AcceptAll {
        fn verify_server_cert(
            &self,
            _: &CertificateDer<'_>,
            _: &[CertificateDer<'_>],
            _: &ServerName<'_>,
            _: &[u8],
            _: UnixTime,
        ) -> std::result::Result<ServerCertVerified, rustls::Error> {
            Ok(ServerCertVerified::assertion())
        }
        fn verify_tls12_signature(
            &self,
            _: &[u8],
            _: &CertificateDer<'_>,
            _: &DigitallySignedStruct,
        ) -> std::result::Result<HandshakeSignatureValid, rustls::Error> {
            Ok(HandshakeSignatureValid::assertion())
        }
        fn verify_tls13_signature(
            &self,
            _: &[u8],
            _: &CertificateDer<'_>,
            _: &DigitallySignedStruct,
        ) -> std::result::Result<HandshakeSignatureValid, rustls::Error> {
            Ok(HandshakeSignatureValid::assertion())
        }
        fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
            vec![
                SignatureScheme::RSA_PKCS1_SHA256,
                SignatureScheme::RSA_PKCS1_SHA384,
                SignatureScheme::RSA_PKCS1_SHA512,
                SignatureScheme::ECDSA_NISTP256_SHA256,
                SignatureScheme::ECDSA_NISTP384_SHA384,
                SignatureScheme::ED25519,
                SignatureScheme::RSA_PSS_SHA256,
                SignatureScheme::RSA_PSS_SHA384,
                SignatureScheme::RSA_PSS_SHA512,
            ]
        }
    }
    ClientConfig::builder()
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(AcceptAll))
        .with_no_client_auth()
    }

#[cfg(test)]
mod tests {
    use super::*;
    use rustls::client::danger::ServerCertVerifier;
    use rustls::client::WebPkiServerVerifier;
    use rustls::pki_types::{CertificateDer, ServerName, UnixTime};

    fn bundled_end_entity() -> CertificateDer<'static> {
        let mut cursor = std::io::Cursor::new(BUNDLED_CA_PEM);
        let certs: Vec<CertificateDer<'static>> = rustls_pemfile::certs(&mut cursor)
            .collect::<std::result::Result<_, _>>()
            .expect("parse bundled cert");
        assert_eq!(certs.len(), 1, "bundled file should hold exactly one cert");
        certs.into_iter().next().unwrap()
    }

    /// The bundled cert must parse into a non-empty RootCertStore. Cheap
    /// guard that catches an accidentally-truncated or wrong-format file
    /// getting embedded.
    #[test]
    fn bundled_cert_loads_into_root_store() {
        let roots = roots_from_pem(BUNDLED_CA_PEM).expect("bundled cert should load");
        assert_eq!(roots.len(), 1);
    }

    /// The marquee test: run the bundled cert through rustls's *real*
    /// WebPki server-cert verifier, pinned to itself, for the hostname the
    /// default server URL uses. If this passes we know that pointing the
    /// client at https://btidalpool.ddns.net:3567 with the default
    /// `BundledPin` trust will complete the TLS handshake — without needing
    /// a live server in the test. Exercises the same trust-anchor + SAN +
    /// validity-window checks the real handshake performs.
    #[test]
    fn bundled_cert_validates_as_its_own_server_cert() {
        ensure_crypto_provider_installed();
        let roots = roots_from_pem(BUNDLED_CA_PEM).unwrap();
        let verifier = WebPkiServerVerifier::builder(Arc::new(roots))
            .build()
            .expect("build verifier");
        let ee = bundled_end_entity();
        let name = ServerName::try_from("btidalpool.ddns.net").unwrap();
        let res = verifier.verify_server_cert(&ee, &[], &name, &[], UnixTime::now());
        assert!(
            res.is_ok(),
            "bundled cert must validate as its own server cert for \
             btidalpool.ddns.net (else the default --BundledPin trust would \
             fail the real handshake): {res:?}"
        );
    }

    /// Pinning is hostname-scoped: the bundled cert must be *rejected* for a
    /// hostname it isn't issued for. Confirms we didn't accidentally end up
    /// with name-checking disabled.
    #[test]
    fn bundled_cert_rejected_for_wrong_hostname() {
        ensure_crypto_provider_installed();
        let roots = roots_from_pem(BUNDLED_CA_PEM).unwrap();
        let verifier = WebPkiServerVerifier::builder(Arc::new(roots))
            .build()
            .unwrap();
        let ee = bundled_end_entity();
        let name = ServerName::try_from("example.com").unwrap();
        let res = verifier.verify_server_cert(&ee, &[], &name, &[], UnixTime::now());
        assert!(res.is_err(), "wrong hostname must be rejected");
    }

    #[test]
    fn empty_pem_is_rejected() {
        let err = roots_from_pem(b"not a cert").unwrap_err();
        assert!(err.to_string().contains("no certificates"));
    }
}
