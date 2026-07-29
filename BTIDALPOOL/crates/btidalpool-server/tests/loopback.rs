//! End-to-end loopback tests for the v4-only Rust listener.

use std::collections::BTreeMap;
use std::io::Read;
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use btidalpool_proto::{
    canonical_sha1, exact_sha256, DbValue, NativeDevice, NativeQueryResult, NativeTable,
    QueryParams, V4Auth, V4DbValueKind, V4Envelope, V4ErrorKind, V4Payload, V4Response,
    CONTENT_TYPE,
};
use btidalpool_server::handlers::Deps;
use btidalpool_server::http::{self, Config as ServerConfig, OverloadConfig, TlsConfig};
use btidalpool_server::ingest::NoopIngestSink;
use btidalpool_server::native_query::{NativeQueryEngine, StubNativeQueryEngine};
use btidalpool_server::oauth::{MockOAuthValidator, OAuthValidator};
use btidalpool_server::query::{QueryEngine, StubQueryEngine};
use btidalpool_server::rate_limit::{Limiter, Limits};
use btidalpool_server::resumable::ResumableStore;
use btidalpool_server::session::SessionTokens;
use btidalpool_server::state::ServerState;

struct Harness {
    _td: tempfile::TempDir,
    server_url: String,
}

impl Harness {
    fn boot(
        query: Arc<dyn QueryEngine>,
        native_query: Arc<dyn NativeQueryEngine>,
        good_token: &str,
        email: &str,
    ) -> Self {
        Self::boot_with(
            query,
            native_query,
            good_token,
            email,
            OverloadConfig::default(),
            Limits::default(),
        )
    }

    fn boot_with(
        query: Arc<dyn QueryEngine>,
        native_query: Arc<dyn NativeQueryEngine>,
        good_token: &str,
        email: &str,
        overload: OverloadConfig,
        identity_limits: Limits,
    ) -> Self {
        Self::boot_configured(
            query,
            native_query,
            good_token,
            email,
            overload,
            identity_limits,
            false,
        )
    }

    fn boot_configured(
        query: Arc<dyn QueryEngine>,
        native_query: Arc<dyn NativeQueryEngine>,
        good_token: &str,
        email: &str,
        overload: OverloadConfig,
        identity_limits: Limits,
        enable_healthz: bool,
    ) -> Self {
        let td = tempfile::tempdir().unwrap();
        let mut params = rcgen::CertificateParams::new(vec!["localhost".to_string()]).unwrap();
        params
            .subject_alt_names
            .push(rcgen::SanType::IpAddress(IpAddr::V4(Ipv4Addr::LOCALHOST)));
        let key_pair = rcgen::KeyPair::generate().unwrap();
        let cert = params.self_signed(&key_pair).unwrap();
        let cert_path = td.path().join("cert.pem");
        let key_path = td.path().join("key.pem");
        std::fs::write(&cert_path, cert.pem()).unwrap();
        std::fs::write(&key_path, key_pair.serialize_pem()).unwrap();

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        let bind = SocketAddr::from(([127, 0, 0, 1], port));

        let state = ServerState::initialize(
            td.path().join("pool"),
            td.path().join("users"),
            td.path().join("access.log"),
        )
        .unwrap();
        let validator: Arc<dyn OAuthValidator> = Arc::new(MockOAuthValidator {
            good_token: good_token.into(),
            email: email.into(),
        });
        let cfg = ServerConfig {
            bind,
            tls: Some(TlsConfig {
                cert_pem_path: cert_path,
                key_pem_path: key_path,
            }),
            enable_healthz,
            ip_limiter: Limiter::new(Limits {
                max_simultaneous: 50,
                max_per_day: 1_000,
                ..Limits::default()
            }),
            identity_limiter: Limiter::new(identity_limits),
            overload,
            validator,
            sessions: SessionTokens::from_key(vec![0x42; 32], Duration::from_secs(900)).unwrap(),
            deps: Deps {
                state,
                // The path name is intentionally neutral in new deployments.
                resumable: ResumableStore::initialize(td.path().join("resumable")).unwrap(),
                ingest: Arc::new(NoopIngestSink),
                query,
                native_query,
                max_query_records: 100,
                max_native_rows: 1_000,
            },
        };
        thread::spawn(move || {
            if let Err(error) = http::run(cfg) {
                eprintln!("server thread exited: {error}");
            }
        });

        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        loop {
            if std::net::TcpStream::connect_timeout(&bind, Duration::from_millis(200)).is_ok() {
                break;
            }
            assert!(
                std::time::Instant::now() <= deadline,
                "server did not start listening within 5s"
            );
            thread::sleep(Duration::from_millis(50));
        }
        Self {
            _td: td,
            server_url: format!("https://localhost:{port}"),
        }
    }
}

#[test]
fn v4_unifies_all_capabilities_and_replays_resumable_finalize() {
    let mut tables = BTreeMap::new();
    tables.insert(
        "LE_bdaddr_to_name".to_owned(),
        NativeTable {
            columns: vec!["payload".into(), "name".into(), "large_unsigned".into()],
            rows: vec![vec![
                DbValue::Bytes(vec![0xaa, 0xbb]),
                DbValue::Bytes(b"sensor".to_vec()),
                DbValue::Unsigned(u64::MAX),
            ]],
            truncated: false,
        },
    );
    let harness = Harness::boot(
        Arc::new(StubQueryEngine::ok(b"[{\"legacy\":true}]".to_vec(), 1)),
        Arc::new(StubNativeQueryEngine::ok(NativeQueryResult {
            devices: vec![NativeDevice {
                bdaddr: "aa:bb:cc:dd:ee:ff".into(),
                tables,
            }],
            total_rows: 1,
            row_limit: 1_000,
            truncated: false,
        })),
        "good-token",
        "tester@example.com",
    );

    let session = v4_round_trip(
        &harness,
        &V4Envelope {
            auth: V4Auth::Google {
                access_token: "good-token".into(),
            },
            payload: V4Payload::CreateSession,
        },
    );
    let token = match session {
        V4Response::Session { token, .. } => token,
        other => panic!("expected session, got {other:?}"),
    };
    let auth = || V4Auth::Session {
        token: token.clone(),
    };

    let whole = br#"[{"bdaddr":"10:20:30:40:50:60","bdaddr_rand":0}]"#.to_vec();
    let hash = canonical_sha1(&whole).unwrap();
    assert!(matches!(
        v4_round_trip(
            &harness,
            &V4Envelope {
                auth: auth(),
                payload: V4Payload::CheckHash { hash: hash.clone() },
            },
        ),
        V4Response::Ok { .. }
    ));
    assert!(matches!(
        v4_round_trip(
            &harness,
            &V4Envelope {
                auth: auth(),
                payload: V4Payload::Upload {
                    btides_json: whole,
                    use_test_db: true,
                },
            },
        ),
        V4Response::Ok { .. }
    ));
    assert!(matches!(
        v4_round_trip(
            &harness,
            &V4Envelope {
                auth: auth(),
                payload: V4Payload::CheckHash { hash },
            },
        ),
        V4Response::Err {
            kind: V4ErrorKind::DuplicateUpload,
            ..
        }
    ));

    assert!(matches!(
        v4_round_trip(
            &harness,
            &V4Envelope {
                auth: auth(),
                payload: V4Payload::LegacyQuery {
                    params: QueryParams::default(),
                    use_test_db: true,
                },
            },
        ),
        V4Response::QueryResult {
            records: 1,
            ref btides_json
        } if btides_json == b"[{\"legacy\":true}]"
    ));
    match v4_round_trip(
        &harness,
        &V4Envelope {
            auth: auth(),
            payload: V4Payload::NativeQuery {
                params: QueryParams::default(),
                use_test_db: true,
            },
        },
    ) {
        V4Response::NativeQueryResult { query } => {
            let row = &query.devices[0].tables["LE_bdaddr_to_name"].rows[0];
            assert_eq!(row[0].kind, V4DbValueKind::Bytes);
            assert_eq!(
                row[0].bytes.as_ref().map(|bytes| bytes.as_slice()),
                Some(&[0xaa, 0xbb][..])
            );
            assert_eq!(row[2].kind, V4DbValueKind::Unsigned);
            assert_eq!(row[2].unsigned.as_deref(), Some("18446744073709551615"));
        }
        other => panic!("expected native result, got {other:?}"),
    }

    let chunks = [
        b"[{\"bdaddr\":\"70:80:".to_vec(),
        b"90:A0:B0:C0\",\"bdaddr_rand\":0}]".to_vec(),
    ];
    let all = chunks.concat();
    let manifest_payload = V4Payload::Manifest {
        content_sha256: exact_sha256(&all),
        total_size: all.len() as u64,
        chunk_sha256: chunks.iter().map(|chunk| exact_sha256(chunk)).collect(),
        use_test_db: true,
    };
    let upload_id = match v4_round_trip(
        &harness,
        &V4Envelope {
            auth: auth(),
            payload: manifest_payload.clone(),
        },
    ) {
        V4Response::Manifest {
            upload_id,
            missing_chunks,
            ..
        } => {
            assert_eq!(missing_chunks, vec![0, 1]);
            upload_id
        }
        other => panic!("expected manifest, got {other:?}"),
    };
    let _ = v4_round_trip(
        &harness,
        &V4Envelope {
            auth: auth(),
            payload: V4Payload::PutChunk {
                upload_id: upload_id.clone(),
                index: 0,
                data: chunks[0].clone(),
            },
        },
    );
    assert!(matches!(
        v4_round_trip(
            &harness,
            &V4Envelope {
                auth: auth(),
                payload: V4Payload::Status {
                    upload_id: upload_id.clone(),
                },
            },
        ),
        V4Response::Status {
            ref missing_chunks,
            ..
        } if missing_chunks == &[1]
    ));
    assert!(matches!(
        v4_round_trip(
            &harness,
            &V4Envelope {
                auth: auth(),
                payload: manifest_payload,
            },
        ),
        V4Response::Manifest {
            ref missing_chunks,
            ..
        } if missing_chunks == &[1]
    ));
    let _ = v4_round_trip(
        &harness,
        &V4Envelope {
            auth: auth(),
            payload: V4Payload::PutChunk {
                upload_id: upload_id.clone(),
                index: 1,
                data: chunks[1].clone(),
            },
        },
    );
    let receipt = match v4_round_trip(
        &harness,
        &V4Envelope {
            auth: auth(),
            payload: V4Payload::Finalize {
                upload_id: upload_id.clone(),
            },
        },
    ) {
        V4Response::Finalized { receipt } => receipt,
        other => panic!("expected receipt, got {other:?}"),
    };
    assert_eq!(
        v4_round_trip(
            &harness,
            &V4Envelope {
                auth: auth(),
                payload: V4Payload::Finalize { upload_id },
            },
        ),
        V4Response::Finalized { receipt }
    );
}

#[test]
fn overloaded_v4_native_query_returns_typed_503_with_retry_after() {
    let harness = Harness::boot_with(
        Arc::new(StubQueryEngine::empty()),
        Arc::new(StubNativeQueryEngine::empty()),
        "good-token",
        "tester@example.com",
        OverloadConfig {
            native_queries: btidalpool_server::rate_limit::ConcurrencyLimiter::new(0),
            retry_after: Duration::from_secs(9),
            ..OverloadConfig::default()
        },
        Limits::default(),
    );
    let token = create_session(&harness, "good-token");
    let envelope = V4Envelope {
        auth: V4Auth::Session { token },
        payload: V4Payload::NativeQuery {
            params: QueryParams::default(),
            use_test_db: false,
        },
    };
    let response = post_v4_raw(&harness, &envelope);
    assert_eq!(response.status(), 503);
    assert_eq!(response.header("Retry-After"), Some("9"));
    let decoded = decode_v4_response(response);
    assert!(matches!(
        decoded,
        V4Response::Err {
            kind: V4ErrorKind::ServerBusy,
            ..
        }
    ));
}

#[test]
fn authenticated_quota_returns_typed_v4_429_with_retry_after() {
    let harness = Harness::boot_with(
        Arc::new(StubQueryEngine::empty()),
        Arc::new(StubNativeQueryEngine::empty()),
        "good-token",
        "tester@example.com",
        OverloadConfig::default(),
        Limits {
            max_simultaneous: 10,
            max_per_day: 1,
            window: Duration::from_secs(3_600),
        },
    );
    let _ = create_session(&harness, "good-token");
    let response = post_v4_raw(
        &harness,
        &V4Envelope {
            auth: V4Auth::Google {
                access_token: "good-token".into(),
            },
            payload: V4Payload::CreateSession,
        },
    );
    assert_eq!(response.status(), 429);
    assert!(
        response
            .header("Retry-After")
            .unwrap()
            .parse::<u64>()
            .unwrap()
            >= 1
    );
    assert!(matches!(
        decode_v4_response(response),
        V4Response::Err {
            kind: V4ErrorKind::RateLimited,
            ..
        }
    ));
}

#[test]
fn rust_listener_rejects_removed_protocol_routes() {
    let harness = Harness::boot(
        Arc::new(StubQueryEngine::empty()),
        Arc::new(StubNativeQueryEngine::empty()),
        "good-token",
        "tester@example.com",
    );
    let agent = build_insecure_agent();
    for path in ["/", "/v2", "/v3"] {
        let response = agent
            .post(&format!("{}{path}", harness.server_url))
            .set("Content-Type", &format!("{CONTENT_TYPE}; version=4"))
            .send_bytes(b"ignored");
        match response {
            Err(ureq::Error::Status(404, _)) => {}
            Ok(response) => panic!("{path} unexpectedly returned {}", response.status()),
            Err(error) => panic!("{path} expected 404, got {error}"),
        }
    }
}

#[test]
fn v4_requires_explicit_version_four_content_type() {
    let harness = Harness::boot(
        Arc::new(StubQueryEngine::empty()),
        Arc::new(StubNativeQueryEngine::empty()),
        "good-token",
        "tester@example.com",
    );
    let body = btidalpool_proto::codec::encode_v4(&V4Envelope {
        auth: V4Auth::Google {
            access_token: "good-token".into(),
        },
        payload: V4Payload::CreateSession,
    })
    .unwrap();
    for content_type in [
        CONTENT_TYPE.to_string(),
        format!("{CONTENT_TYPE}; version=1"),
        format!("{CONTENT_TYPE}; version=2"),
        format!("{CONTENT_TYPE}; version=3"),
    ] {
        let response = build_insecure_agent()
            .post(&format!("{}/v4", harness.server_url))
            .set("Content-Type", &content_type)
            .send_bytes(&body);
        match response {
            Err(ureq::Error::Status(415, _)) => {}
            Ok(response) => panic!("{content_type} unexpectedly returned {}", response.status()),
            Err(error) => panic!("{content_type} expected 415, got {error}"),
        }
    }
}

#[test]
fn health_is_hidden_by_default_and_other_methods_are_rejected() {
    let harness = Harness::boot(
        Arc::new(StubQueryEngine::empty()),
        Arc::new(StubNativeQueryEngine::empty()),
        "good-token",
        "tester@example.com",
    );
    match build_insecure_agent()
        .get(&format!("{}/healthz", harness.server_url))
        .call()
    {
        Err(ureq::Error::Status(404, _)) => {}
        other => panic!("GET /healthz expected 404, got {other:?}"),
    }
    match build_insecure_agent()
        .get(&format!("{}/v4", harness.server_url))
        .call()
    {
        Err(ureq::Error::Status(405, _)) => {}
        other => panic!("GET /v4 expected 405, got {other:?}"),
    }
}

#[test]
fn health_can_be_enabled_for_a_controlled_test_window() {
    let harness = Harness::boot_configured(
        Arc::new(StubQueryEngine::empty()),
        Arc::new(StubNativeQueryEngine::empty()),
        "good-token",
        "tester@example.com",
        OverloadConfig::default(),
        Limits::default(),
        true,
    );
    assert_eq!(
        build_insecure_agent()
            .get(&format!("{}/healthz", harness.server_url))
            .call()
            .unwrap()
            .status(),
        200
    );
}

fn create_session(harness: &Harness, google_token: &str) -> String {
    match v4_round_trip(
        harness,
        &V4Envelope {
            auth: V4Auth::Google {
                access_token: google_token.into(),
            },
            payload: V4Payload::CreateSession,
        },
    ) {
        V4Response::Session { token, .. } => token,
        other => panic!("expected session, got {other:?}"),
    }
}

fn v4_round_trip(harness: &Harness, envelope: &V4Envelope) -> V4Response {
    decode_v4_response(post_v4_raw(harness, envelope))
}

fn post_v4_raw(harness: &Harness, envelope: &V4Envelope) -> ureq::Response {
    let body = btidalpool_proto::codec::encode_v4(envelope).unwrap();
    match build_insecure_agent()
        .post(&format!("{}/v4", harness.server_url))
        .set("Content-Type", &format!("{CONTENT_TYPE}; version=4"))
        .send_bytes(&body)
    {
        Ok(response) => response,
        Err(ureq::Error::Status(_, response)) => response,
        Err(error) => panic!("v4 transport error: {error}"),
    }
}

fn decode_v4_response(response: ureq::Response) -> V4Response {
    assert!(response
        .header("Content-Type")
        .unwrap_or_default()
        .contains("version=4"));
    let mut bytes = Vec::new();
    response.into_reader().read_to_end(&mut bytes).unwrap();
    btidalpool_proto::codec::decode_v4(&bytes).unwrap()
}

fn ensure_crypto_provider_installed() {
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let _ = rustls::crypto::ring::default_provider().install_default();
    });
}

fn build_insecure_agent() -> ureq::Agent {
    ensure_crypto_provider_installed();
    use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
    use rustls::pki_types::{CertificateDer, ServerName, UnixTime};
    use rustls::{ClientConfig, DigitallySignedStruct, SignatureScheme};

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
        ) -> Result<ServerCertVerified, rustls::Error> {
            Ok(ServerCertVerified::assertion())
        }

        fn verify_tls12_signature(
            &self,
            _: &[u8],
            _: &CertificateDer<'_>,
            _: &DigitallySignedStruct,
        ) -> Result<HandshakeSignatureValid, rustls::Error> {
            Ok(HandshakeSignatureValid::assertion())
        }

        fn verify_tls13_signature(
            &self,
            _: &[u8],
            _: &CertificateDer<'_>,
            _: &DigitallySignedStruct,
        ) -> Result<HandshakeSignatureValid, rustls::Error> {
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
    let cfg = ClientConfig::builder()
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(AcceptAll))
        .with_no_client_auth();
    ureq::AgentBuilder::new().tls_config(Arc::new(cfg)).build()
}
