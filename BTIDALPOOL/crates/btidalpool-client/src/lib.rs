//! BTIDALPOOL client library.
//!
//! Phase 1 helpers (envelope builders + transport) so the binary in
//! `main.rs` stays small and the integration test in
//! `btidalpool-server/tests/loopback.rs` can drive the client logic
//! without spawning a subprocess.

pub mod refresh;
pub mod transport;

use btidalpool_proto::{AuthFields, Envelope, Payload, QueryParams};

/// Build an `upload` request envelope around a BTIDES JSON blob (raw bytes).
pub fn build_upload(auth: AuthFields, btides_json: Vec<u8>) -> Envelope {
    Envelope {
        auth,
        payload: Payload::Upload { btides_json },
    }
}

/// Build a `check_hash` request envelope. The hash is the same canonical
/// SHA1 the server computes — see [`btidalpool_proto::canonical_sha1`].
pub fn build_check_hash(auth: AuthFields, hash: String) -> Envelope {
    Envelope {
        auth,
        payload: Payload::CheckHash { hash },
    }
}

/// Build a `query` request envelope around a [`QueryParams`].
pub fn build_query(auth: AuthFields, params: QueryParams) -> Envelope {
    Envelope {
        auth,
        payload: Payload::Query { params },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use btidalpool_proto::{codec, AuthFields, Envelope, Payload};

    fn auth() -> AuthFields {
        AuthFields {
            token: "t".into(),
            refresh_token: "rt".into(),
            use_test_db: false,
        }
    }

    #[test]
    fn upload_envelope_round_trips_through_codec() {
        let env = build_upload(auth(), b"[]".to_vec());
        let frame = codec::encode(&env).expect("encode");
        let back: Envelope = codec::decode(&frame).expect("decode");
        match back.payload {
            Payload::Upload { btides_json } => assert_eq!(btides_json, b"[]"),
            _ => panic!("wrong payload variant"),
        }
    }

    #[test]
    fn check_hash_envelope_round_trips_through_codec() {
        let env = build_check_hash(auth(), "deadbeef".into());
        let frame = codec::encode(&env).expect("encode");
        let back: Envelope = codec::decode(&frame).expect("decode");
        match back.payload {
            Payload::CheckHash { hash } => assert_eq!(hash, "deadbeef"),
            _ => panic!("wrong payload variant"),
        }
    }

    #[test]
    fn query_envelope_round_trips_through_codec() {
        let mut q = QueryParams::default();
        q.bdaddr = Some("AA:BB:CC:DD:EE:FF".into());
        q.require_GPS = true;
        let env = build_query(auth(), q);
        let frame = codec::encode(&env).expect("encode");
        let back: Envelope = codec::decode(&frame).expect("decode");
        match back.payload {
            Payload::Query { params } => {
                assert_eq!(params.bdaddr.as_deref(), Some("AA:BB:CC:DD:EE:FF"));
                assert!(params.require_GPS);
            }
            _ => panic!("wrong payload variant"),
        }
    }
}
