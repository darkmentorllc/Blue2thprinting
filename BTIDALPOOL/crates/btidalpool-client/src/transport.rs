//! Synchronous HTTPS transport for the BTIDALPOOL client.
//!
//! Uses `ureq` (sync, blocking) instead of `reqwest` (async, tokio) because
//! the client's control flow is one-shot per invocation — the binary either
//! runs an upload or a query, then exits. No event loop justified.
//!
//! Server certificate trust:
//!   * If the caller passes `--ca <path>`, we load that PEM file as the
//!     *only* trusted root for the request. Matches the Python client's
//!     `verify='./btidalpool.ddns.net.crt'` pinning.
//!   * If the caller passes `--insecure`, all certs are accepted. For
//!     local end-to-end tests only.
//!   * Otherwise the system roots are used (the AWS server has a real
//!     LetsEncrypt cert on its OAuth port, but the BTIDALPOOL endpoint
//!     historically uses a self-signed cert pinned by file).

use std::io::Read;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use btidalpool_proto::{codec, Envelope, Response, CONTENT_TYPE};
use rustls::{ClientConfig, RootCertStore};

pub struct Transport {
    agent: ureq::Agent,
    url: String,
}

/// How the client should trust the server's TLS certificate.
pub enum CertTrust {
    /// Default: use the system trust roots.
    System,
    /// Pin a single PEM-encoded certificate (or chain). Matches the Python
    /// client's behavior when given `verify=./btidalpool.ddns.net.crt`.
    Pinned { ca_pem_path: std::path::PathBuf },
    /// Accept any cert. Local tests only — refuses to be the default.
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
            CertTrust::System => builder,
            CertTrust::Pinned { ca_pem_path } => {
                let mut roots = RootCertStore::empty();
                let bytes = std::fs::read(&ca_pem_path)
                    .with_context(|| format!("reading CA pem {ca_pem_path:?}"))?;
                let mut cursor = std::io::Cursor::new(bytes);
                for cert in rustls_pemfile::certs(&mut cursor) {
                    let cert = cert.with_context(|| "parsing pinned CA certificate")?;
                    roots
                        .add(cert)
                        .with_context(|| "registering pinned CA certificate")?;
                }
                if roots.is_empty() {
                    anyhow::bail!("--ca file contained no certificates");
                }
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
