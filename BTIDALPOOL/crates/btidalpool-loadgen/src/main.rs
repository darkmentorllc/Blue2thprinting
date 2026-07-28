//! Protocol-aware load generator for the BTIDALPOOL v1/v2/v3 server.
//!
//! This is deliberately a standalone client. Run it from a machine other
//! than the server so client-side TLS, compression, and response validation
//! do not consume the server resources being measured.

use std::collections::BTreeMap;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Barrier};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{bail, Context, Result};
use btidalpool_proto::{
    codec, exact_sha256, AuthFields, Envelope, ErrorKind, Payload, QueryParams, Response, V2Auth,
    V2Envelope, V2Payload, V2Response, V3Envelope, V3Payload, V3Response, CONTENT_TYPE,
};
use clap::{Parser, ValueEnum};
use rustls::{ClientConfig, RootCertStore};
use serde::Serialize;

const CHUNK_BYTES: usize = 1024 * 1024;

#[derive(Debug, Parser)]
#[command(
    name = "btidalpool-loadgen",
    about = "Protocol-aware BTIDALPOOL v1/v2/v3 load generator"
)]
struct Cli {
    #[arg(long, default_value = "https://btidalpool.ddns.net:3568")]
    server_url: String,
    /// PEM certificate used to authenticate the benchmark server.
    #[arg(long)]
    ca_cert: PathBuf,
    /// Mock OAuth token configured on the isolated benchmark server.
    #[arg(long, default_value = "btidalpool-load-test")]
    mock_token: String,
    /// Existing signed session token. Useful for read-only production v3
    /// benchmarks where no Google credential should be supplied to loadgen.
    #[arg(long)]
    session_token: Option<String>,
    /// Read an existing signed session token from a protected file. Prefer
    /// this over --session-token for production probes so the token never
    /// appears in the process list or shell history.
    #[arg(long, conflicts_with = "session_token")]
    session_token_file: Option<PathBuf>,
    #[arg(long, value_enum)]
    workload: Workload,
    #[arg(long, default_value_t = 1)]
    concurrency: usize,
    #[arg(long, default_value_t = 10)]
    duration_seconds: u64,
    /// Run exactly this many requests per worker instead of a timed loop.
    /// Useful for one-shot concurrency bursts of expensive queries.
    #[arg(long)]
    iterations_per_worker: Option<usize>,
    /// Real BTIDES JSON used by upload/chunk/finalize workloads.
    #[arg(long)]
    input: Option<PathBuf>,
    /// Pad a valid JSON input with trailing JSON whitespace to this exact
    /// byte length. This exercises a protocol size boundary without
    /// fabricating or duplicating BTIDES records.
    #[arg(long)]
    pad_input_to_bytes: Option<usize>,
    /// Request `Connection: close` to measure cold-connection overhead.
    #[arg(long)]
    close_connection: bool,
    /// Starting array rotation for unique finalize-burst payloads.
    #[arg(long, default_value_t = 0)]
    variant_offset: usize,
    /// Route v1-query to the production read-only dataset instead of bttest.
    /// This flag is rejected for writing workloads.
    #[arg(long)]
    query_use_production_db: bool,
    /// Require every successful query response to contain at least this many
    /// records. Used to prove the server's configured response cap was hit.
    #[arg(long, default_value_t = 0)]
    expected_query_records: u64,
    /// Optional broad or specific BDADDR regex for v1-query.
    #[arg(long)]
    query_bdaddr_regex: Option<String>,
    /// Optional device-name regex for v1-query.
    #[arg(long)]
    query_name_regex: Option<String>,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum Workload {
    Health,
    V1Check,
    V1Query,
    V3Query,
    V1UploadReplay,
    V2Manifest,
    V2Status,
    V2PutReplay,
    V2FinalizeReplay,
    V2FinalizeBurst,
}

#[derive(Clone)]
struct Client {
    agent: ureq::Agent,
    base_url: String,
    close_connection: bool,
}

#[derive(Clone)]
enum RequestSpec {
    Health,
    V1 {
        body: Arc<Vec<u8>>,
        expected: ExpectedV1,
    },
    V2 {
        body: Arc<Vec<u8>>,
        expected: ExpectedV2,
    },
    V3 {
        body: Arc<Vec<u8>>,
        expected: ExpectedV3,
    },
}

#[derive(Clone, Copy)]
enum ExpectedV1 {
    Check,
    Query { minimum_records: u64 },
    UploadReplay,
}

#[derive(Clone, Copy)]
enum ExpectedV2 {
    Manifest,
    Status,
    Chunk,
    Finalize,
}

#[derive(Clone, Copy)]
enum ExpectedV3 {
    Query { minimum_devices: u64 },
}

struct Sample {
    micros: u64,
    status: u16,
    ok: bool,
    error: Option<String>,
}

#[derive(Serialize)]
struct Summary {
    workload: String,
    concurrency: usize,
    requested_duration_seconds: u64,
    elapsed_seconds: f64,
    requests: usize,
    successful: usize,
    errors: usize,
    requests_per_second: f64,
    latency_ms_p50: f64,
    latency_ms_p95: f64,
    latency_ms_p99: f64,
    latency_ms_max: f64,
    http_statuses: BTreeMap<u16, usize>,
    error_kinds: BTreeMap<String, usize>,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    if cli.concurrency == 0 {
        bail!("--concurrency must be at least 1");
    }
    let tls = load_tls(&cli.ca_cert)?;
    let client = Client::new(
        cli.server_url.trim_end_matches('/').to_owned(),
        tls,
        cli.close_connection,
    );

    let mut input = match &cli.input {
        Some(path) => {
            Some(std::fs::read(path).with_context(|| format!("reading BTIDES input {path:?}"))?)
        }
        None => None,
    };
    if let Some(target) = cli.pad_input_to_bytes {
        let bytes = input
            .as_mut()
            .context("--pad-input-to-bytes requires --input")?;
        serde_json::from_slice::<serde_json::Value>(bytes)
            .context("input must be valid JSON before boundary padding")?;
        if bytes.len() > target {
            bail!(
                "input is already {} bytes, larger than requested padded size {target}",
                bytes.len()
            );
        }
        bytes.resize(target, b' ');
    }

    if matches!(cli.workload, Workload::V2FinalizeBurst) {
        let input = input
            .as_deref()
            .context("--input is required for v2-finalize-burst")?;
        let summary = run_finalize_burst(&cli, &client, input)?;
        println!("{}", serde_json::to_string(&summary)?);
        return Ok(());
    }

    let spec = prepare_request(&cli, &client, input.as_deref())?;
    let summary = run_steady(&cli, &client, spec);
    println!("{}", serde_json::to_string(&summary)?);
    Ok(())
}

impl Client {
    fn new(base_url: String, tls: Arc<ClientConfig>, close_connection: bool) -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_secs(10))
            .timeout(Duration::from_secs(30))
            .tls_config(tls)
            .build();
        Self {
            agent,
            base_url,
            close_connection,
        }
    }

    fn request(&self, spec: &RequestSpec) -> Sample {
        let started = Instant::now();
        let result = match spec {
            RequestSpec::Health => self.health(),
            RequestSpec::V1 { body, expected } => self.v1(body, *expected),
            RequestSpec::V2 { body, expected } => self.v2(body, *expected),
            RequestSpec::V3 { body, expected } => self.v3(body, *expected),
        };
        let micros = started.elapsed().as_micros().min(u64::MAX as u128) as u64;
        match result {
            Ok(status) => Sample {
                micros,
                status,
                ok: true,
                error: None,
            },
            Err((status, error)) => Sample {
                micros,
                status,
                ok: false,
                error: Some(error),
            },
        }
    }

    fn health(&self) -> std::result::Result<u16, (u16, String)> {
        let mut req = self.agent.get(&format!("{}/healthz", self.base_url));
        if self.close_connection {
            req = req.set("Connection", "close");
        }
        let response = match req.call() {
            Ok(response) => response,
            Err(ureq::Error::Status(_, response)) => response,
            Err(error) => return Err((0, transport_kind(&error))),
        };
        let status = response.status();
        if status == 200 {
            Ok(status)
        } else {
            Err((status, format!("http_{status}")))
        }
    }

    fn v1(&self, body: &[u8], expected: ExpectedV1) -> std::result::Result<u16, (u16, String)> {
        let (status, bytes) = self.post(&self.base_url, CONTENT_TYPE, body)?;
        let response: Response =
            codec::decode(&bytes).map_err(|_| (status, "v1_decode".to_owned()))?;
        let accepted = match (expected, response) {
            (ExpectedV1::Check, Response::Ok { .. })
            | (
                ExpectedV1::Check,
                Response::Err {
                    kind: ErrorKind::DuplicateUpload,
                    ..
                },
            )
            | (ExpectedV1::Query { minimum_records: 0 }, Response::QueryResult { .. })
            | (
                ExpectedV1::UploadReplay,
                Response::Err {
                    kind: ErrorKind::DuplicateUpload,
                    ..
                },
            ) => true,
            (ExpectedV1::Query { minimum_records }, Response::QueryResult { records, .. })
                if records >= minimum_records =>
            {
                true
            }
            (
                ExpectedV1::Query { minimum_records: 0 },
                Response::Err {
                    kind: ErrorKind::EmptyResult,
                    ..
                },
            ) => true,
            (ExpectedV1::Query { .. }, Response::QueryResult { .. }) => {
                return Err((status, "v1_query_too_few_records".to_owned()))
            }
            (_, Response::Err { kind, .. }) => {
                return Err((status, format!("v1_{kind:?}").to_ascii_lowercase()))
            }
            _ => false,
        };
        if accepted {
            Ok(status)
        } else {
            Err((status, "v1_unexpected_response".to_owned()))
        }
    }

    fn v2(&self, body: &[u8], expected: ExpectedV2) -> std::result::Result<u16, (u16, String)> {
        let url = format!("{}/v2", self.base_url);
        let (status, bytes) = self.post(&url, &format!("{CONTENT_TYPE}; version=2"), body)?;
        let response: V2Response =
            codec::decode_v2(&bytes).map_err(|_| (status, "v2_decode".to_owned()))?;
        let accepted = matches!(
            (expected, response),
            (ExpectedV2::Manifest, V2Response::Manifest { .. })
                | (ExpectedV2::Status, V2Response::Status { .. })
                | (ExpectedV2::Chunk, V2Response::Chunk { .. })
                | (ExpectedV2::Finalize, V2Response::Finalized { .. })
        );
        if accepted {
            Ok(status)
        } else {
            Err((status, "v2_unexpected_response".to_owned()))
        }
    }

    fn v3(&self, body: &[u8], expected: ExpectedV3) -> std::result::Result<u16, (u16, String)> {
        let url = format!("{}/v3", self.base_url);
        let (status, bytes) = self.post(&url, &format!("{CONTENT_TYPE}; version=3"), body)?;
        let response: V3Response =
            codec::decode_v3(&bytes).map_err(|_| (status, "v3_decode".to_owned()))?;
        match (expected, response) {
            (ExpectedV3::Query { minimum_devices }, V3Response::QueryResult { query })
                if query.devices.len() as u64 >= minimum_devices =>
            {
                Ok(status)
            }
            (ExpectedV3::Query { .. }, V3Response::QueryResult { .. }) => {
                Err((status, "v3_query_too_few_devices".to_owned()))
            }
            (_, V3Response::Err { kind, .. }) => {
                Err((status, format!("v3_{kind:?}").to_ascii_lowercase()))
            }
        }
    }

    fn post(
        &self,
        url: &str,
        content_type: &str,
        body: &[u8],
    ) -> std::result::Result<(u16, Vec<u8>), (u16, String)> {
        let mut req = self.agent.post(url).set("Content-Type", content_type);
        if self.close_connection {
            req = req.set("Connection", "close");
        }
        let response = match req.send_bytes(body) {
            Ok(response) => response,
            Err(ureq::Error::Status(_, response)) => response,
            Err(error) => return Err((0, transport_kind(&error))),
        };
        let status = response.status();
        let mut bytes = Vec::new();
        response
            .into_reader()
            .read_to_end(&mut bytes)
            .map_err(|_| (status, "response_read".to_owned()))?;
        Ok((status, bytes))
    }
}

fn transport_kind(error: &ureq::Error) -> String {
    match error {
        ureq::Error::Status(code, _) => format!("http_{code}"),
        ureq::Error::Transport(_) => "transport".to_owned(),
    }
}

fn prepare_request(cli: &Cli, client: &Client, input: Option<&[u8]>) -> Result<RequestSpec> {
    if cli.query_use_production_db && !matches!(cli.workload, Workload::V1Query | Workload::V3Query)
    {
        bail!("--query-use-production-db is valid only with a query workload");
    }
    let auth = AuthFields {
        token: cli.mock_token.clone(),
        refresh_token: String::new(),
        use_test_db: !cli.query_use_production_db,
    };
    match cli.workload {
        Workload::Health => Ok(RequestSpec::Health),
        Workload::V1Check => {
            let envelope = Envelope {
                auth,
                payload: Payload::CheckHash {
                    hash: "0000000000000000000000000000000000000000".to_owned(),
                },
            };
            Ok(v1_spec(envelope, ExpectedV1::Check)?)
        }
        Workload::V1Query => {
            let mut params = QueryParams::default();
            if let Some(regex) = &cli.query_bdaddr_regex {
                params.bdaddr_regex = Some(vec![regex.clone()]);
            }
            if let Some(regex) = &cli.query_name_regex {
                params.name_regex = Some(vec![regex.clone()]);
            }
            let envelope = Envelope {
                auth,
                payload: Payload::Query { params },
            };
            Ok(v1_spec(
                envelope,
                ExpectedV1::Query {
                    minimum_records: cli.expected_query_records,
                },
            )?)
        }
        Workload::V3Query => {
            let session = existing_session(cli)?
                .map(Ok)
                .unwrap_or_else(|| create_session(client, &cli.mock_token))?;
            let mut params = QueryParams::default();
            if let Some(regex) = &cli.query_bdaddr_regex {
                params.bdaddr_regex = Some(vec![regex.clone()]);
            }
            if let Some(regex) = &cli.query_name_regex {
                params.name_regex = Some(vec![regex.clone()]);
            }
            let envelope = V3Envelope {
                auth: V2Auth::Session { token: session },
                payload: V3Payload::Query {
                    params,
                    use_test_db: !cli.query_use_production_db,
                },
            };
            Ok(RequestSpec::V3 {
                body: Arc::new(codec::encode_v3(&envelope)?),
                expected: ExpectedV3::Query {
                    minimum_devices: cli.expected_query_records,
                },
            })
        }
        Workload::V1UploadReplay => {
            let input = input.context("--input is required for v1-upload-replay")?;
            let envelope = Envelope {
                auth,
                payload: Payload::Upload {
                    btides_json: input.to_vec(),
                },
            };
            let body = Arc::new(codec::encode(&envelope)?);
            let first = client.request(&RequestSpec::V1 {
                body: body.clone(),
                expected: ExpectedV1::UploadReplay,
            });
            // The preparation request is expected to succeed as a new upload,
            // which intentionally differs from steady-state replay semantics.
            if !first.ok && first.error.as_deref() != Some("v1_unexpected_response") {
                bail!("could not prepare v1 upload replay: {:?}", first.error);
            }
            Ok(RequestSpec::V1 {
                body,
                expected: ExpectedV1::UploadReplay,
            })
        }
        Workload::V2Manifest
        | Workload::V2Status
        | Workload::V2PutReplay
        | Workload::V2FinalizeReplay => prepare_v2(cli, client, input),
        Workload::V2FinalizeBurst => unreachable!(),
    }
}

fn existing_session(cli: &Cli) -> Result<Option<String>> {
    if let Some(token) = &cli.session_token {
        return Ok(Some(token.clone()));
    }
    if let Some(path) = &cli.session_token_file {
        let token = std::fs::read_to_string(path)
            .with_context(|| format!("reading signed session token {path:?}"))?
            .trim()
            .to_owned();
        if token.is_empty() {
            bail!("session token file is empty");
        }
        return Ok(Some(token));
    }
    Ok(None)
}

fn v1_spec(envelope: Envelope, expected: ExpectedV1) -> Result<RequestSpec> {
    Ok(RequestSpec::V1 {
        body: Arc::new(codec::encode(&envelope)?),
        expected,
    })
}

fn prepare_v2(cli: &Cli, client: &Client, input: Option<&[u8]>) -> Result<RequestSpec> {
    let session = create_session(client, &cli.mock_token)?;
    let data = input.unwrap_or(b"[]");
    let hashes: Vec<String> = data.chunks(CHUNK_BYTES).map(exact_sha256).collect();
    let manifest = V2Envelope {
        auth: V2Auth::Session {
            token: session.clone(),
        },
        payload: V2Payload::Manifest {
            content_sha256: exact_sha256(data),
            total_size: data.len() as u64,
            chunk_sha256: hashes,
            use_test_db: true,
        },
    };
    let manifest_body = Arc::new(codec::encode_v2(&manifest)?);
    let manifest_response = client.request(&RequestSpec::V2 {
        body: manifest_body.clone(),
        expected: ExpectedV2::Manifest,
    });
    if !manifest_response.ok {
        bail!("manifest preparation failed: {:?}", manifest_response.error);
    }
    let upload_id = manifest_upload_id(client, &manifest_body)?;

    match cli.workload {
        Workload::V2Manifest => Ok(RequestSpec::V2 {
            body: manifest_body,
            expected: ExpectedV2::Manifest,
        }),
        Workload::V2Status => v2_spec(session, V2Payload::Status { upload_id }, ExpectedV2::Status),
        Workload::V2PutReplay => {
            let chunk = data
                .chunks(CHUNK_BYTES)
                .next()
                .context("input must not be empty")?
                .to_vec();
            let spec = v2_spec(
                session,
                V2Payload::PutChunk {
                    upload_id,
                    index: 0,
                    data: chunk,
                },
                ExpectedV2::Chunk,
            )?;
            let first = client.request(&spec);
            if !first.ok {
                bail!("chunk preparation failed: {:?}", first.error);
            }
            Ok(spec)
        }
        Workload::V2FinalizeReplay => {
            for (index, chunk) in data.chunks(CHUNK_BYTES).enumerate() {
                let spec = v2_spec(
                    session.clone(),
                    V2Payload::PutChunk {
                        upload_id: upload_id.clone(),
                        index: index as u32,
                        data: chunk.to_vec(),
                    },
                    ExpectedV2::Chunk,
                )?;
                let sample = client.request(&spec);
                if !sample.ok {
                    bail!("chunk {index} preparation failed: {:?}", sample.error);
                }
            }
            let spec = v2_spec(
                session,
                V2Payload::Finalize { upload_id },
                ExpectedV2::Finalize,
            )?;
            let first = client.request(&spec);
            if !first.ok {
                bail!("finalize preparation failed: {:?}", first.error);
            }
            Ok(spec)
        }
        _ => unreachable!(),
    }
}

fn v2_spec(session: String, payload: V2Payload, expected: ExpectedV2) -> Result<RequestSpec> {
    let envelope = V2Envelope {
        auth: V2Auth::Session { token: session },
        payload,
    };
    Ok(RequestSpec::V2 {
        body: Arc::new(codec::encode_v2(&envelope)?),
        expected,
    })
}

fn create_session(client: &Client, mock_token: &str) -> Result<String> {
    let envelope = V2Envelope {
        auth: V2Auth::Google {
            access_token: mock_token.to_owned(),
        },
        payload: V2Payload::CreateSession,
    };
    let body = codec::encode_v2(&envelope)?;
    let url = format!("{}/v2", client.base_url);
    let (status, bytes) = client
        .post(&url, &format!("{CONTENT_TYPE}; version=2"), &body)
        .map_err(|(_, kind)| anyhow::anyhow!("session transport failed: {kind}"))?;
    let response: V2Response = codec::decode_v2(&bytes)?;
    match response {
        V2Response::Session { token, .. } => Ok(token),
        V2Response::Err { kind, .. } => bail!("session failed with {kind:?} (HTTP {status})"),
        _ => bail!("session returned an unexpected response (HTTP {status})"),
    }
}

fn manifest_upload_id(client: &Client, body: &[u8]) -> Result<String> {
    let url = format!("{}/v2", client.base_url);
    let (_, bytes) = client
        .post(&url, &format!("{CONTENT_TYPE}; version=2"), body)
        .map_err(|(_, kind)| anyhow::anyhow!("manifest transport failed: {kind}"))?;
    match codec::decode_v2(&bytes)? {
        V2Response::Manifest { upload_id, .. } => Ok(upload_id),
        V2Response::Err { kind, .. } => bail!("manifest failed with {kind:?}"),
        _ => bail!("manifest returned an unexpected response"),
    }
}

fn run_steady(cli: &Cli, client: &Client, spec: RequestSpec) -> Summary {
    let barrier = Arc::new(Barrier::new(cli.concurrency + 1));
    let deadline_duration = Duration::from_secs(cli.duration_seconds);
    let iterations_per_worker = cli.iterations_per_worker;
    let mut workers = Vec::with_capacity(cli.concurrency);
    for _ in 0..cli.concurrency {
        let worker_client = client.clone();
        let worker_spec = spec.clone();
        let worker_barrier = barrier.clone();
        workers.push(thread::spawn(move || {
            worker_barrier.wait();
            let deadline = Instant::now() + deadline_duration;
            let mut samples = Vec::new();
            if let Some(iterations) = iterations_per_worker {
                for _ in 0..iterations {
                    samples.push(worker_client.request(&worker_spec));
                }
            } else {
                while Instant::now() < deadline {
                    samples.push(worker_client.request(&worker_spec));
                }
            }
            samples
        }));
    }
    let started = Instant::now();
    barrier.wait();
    let mut samples = Vec::new();
    for worker in workers {
        samples.extend(worker.join().expect("load worker panicked"));
    }
    summarize(
        format!("{:?}", cli.workload),
        cli.concurrency,
        cli.duration_seconds,
        started.elapsed(),
        samples,
    )
}

fn run_finalize_burst(cli: &Cli, client: &Client, input: &[u8]) -> Result<Summary> {
    let records = if cli.pad_input_to_bytes.is_some() {
        // The boundary-padding path must preserve the exact requested byte
        // length. Distinguish concurrent manifests by changing only trailing
        // JSON whitespace, which preserves both validity and real BTIDES
        // records while producing unique exact-byte content hashes.
        serde_json::from_slice::<serde_json::Value>(input)
            .context("finalize-burst input is not valid JSON")?;
        None
    } else {
        let value: serde_json::Value =
            serde_json::from_slice(input).context("finalize-burst input is not valid JSON")?;
        let records = value
            .as_array()
            .context("finalize-burst input must be a top-level JSON array")?;
        if records.is_empty() {
            bail!("finalize-burst input array must not be empty");
        }
        Some(records.clone())
    };
    let session = create_session(client, &cli.mock_token)?;
    let mut specs = Vec::with_capacity(cli.concurrency);
    for worker_index in 0..cli.concurrency {
        let bytes = if let Some(records) = &records {
            let mut variant = records.clone();
            let rotation = (cli.variant_offset + worker_index) % variant.len();
            variant.rotate_left(rotation);
            serde_json::to_vec(&variant)?
        } else {
            let mut variant = input.to_vec();
            if variant.len() < 64
                || !variant[variant.len() - 64..]
                    .iter()
                    .all(|byte| byte.is_ascii_whitespace())
            {
                bail!(
                    "exact-size finalize variants require at least 64 bytes of trailing JSON whitespace"
                );
            }
            let marker = (cli.variant_offset + worker_index) as u64;
            let start = variant.len() - 64;
            for bit in 0..64 {
                variant[start + bit] = if marker & (1_u64 << bit) == 0 {
                    b' '
                } else {
                    b'\t'
                };
            }
            variant
        };
        if bytes.len() > 10 * 1024 * 1024 {
            bail!("compact finalize-burst variant exceeds the 10 MiB server limit");
        }
        let chunk_hashes = bytes.chunks(CHUNK_BYTES).map(exact_sha256).collect();
        let manifest = V2Envelope {
            auth: V2Auth::Session {
                token: session.clone(),
            },
            payload: V2Payload::Manifest {
                content_sha256: exact_sha256(&bytes),
                total_size: bytes.len() as u64,
                chunk_sha256: chunk_hashes,
                use_test_db: true,
            },
        };
        let manifest_body = codec::encode_v2(&manifest)?;
        let upload_id = manifest_upload_id(client, &manifest_body)?;
        for (index, chunk) in bytes.chunks(CHUNK_BYTES).enumerate() {
            let spec = v2_spec(
                session.clone(),
                V2Payload::PutChunk {
                    upload_id: upload_id.clone(),
                    index: index as u32,
                    data: chunk.to_vec(),
                },
                ExpectedV2::Chunk,
            )?;
            let sample = client.request(&spec);
            if !sample.ok {
                bail!("finalize-burst chunk setup failed: {:?}", sample.error);
            }
        }
        specs.push(v2_spec(
            session.clone(),
            V2Payload::Finalize { upload_id },
            ExpectedV2::Finalize,
        )?);
    }

    let barrier = Arc::new(Barrier::new(cli.concurrency + 1));
    let mut workers = Vec::with_capacity(cli.concurrency);
    for spec in specs {
        let worker_client = client.clone();
        let worker_barrier = barrier.clone();
        workers.push(thread::spawn(move || {
            worker_barrier.wait();
            worker_client.request(&spec)
        }));
    }
    let started = Instant::now();
    barrier.wait();
    let samples: Vec<Sample> = workers
        .into_iter()
        .map(|worker| worker.join().expect("finalize worker panicked"))
        .collect();
    let elapsed = started.elapsed();
    Ok(summarize(
        format!("{:?}", cli.workload),
        cli.concurrency,
        0,
        elapsed,
        samples,
    ))
}

fn summarize(
    workload: String,
    concurrency: usize,
    requested_duration_seconds: u64,
    elapsed: Duration,
    samples: Vec<Sample>,
) -> Summary {
    let mut latencies: Vec<u64> = samples.iter().map(|sample| sample.micros).collect();
    latencies.sort_unstable();
    let successful = samples.iter().filter(|sample| sample.ok).count();
    let mut statuses = BTreeMap::new();
    let mut errors = BTreeMap::new();
    for sample in &samples {
        *statuses.entry(sample.status).or_insert(0) += 1;
        if let Some(error) = &sample.error {
            *errors.entry(error.clone()).or_insert(0) += 1;
        }
    }
    let seconds = elapsed.as_secs_f64().max(f64::EPSILON);
    Summary {
        workload,
        concurrency,
        requested_duration_seconds,
        elapsed_seconds: seconds,
        requests: samples.len(),
        successful,
        errors: samples.len() - successful,
        requests_per_second: samples.len() as f64 / seconds,
        latency_ms_p50: percentile_ms(&latencies, 0.50),
        latency_ms_p95: percentile_ms(&latencies, 0.95),
        latency_ms_p99: percentile_ms(&latencies, 0.99),
        latency_ms_max: latencies.last().copied().unwrap_or(0) as f64 / 1000.0,
        http_statuses: statuses,
        error_kinds: errors,
    }
}

fn percentile_ms(sorted: &[u64], quantile: f64) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    let index = ((sorted.len() - 1) as f64 * quantile).round() as usize;
    sorted[index] as f64 / 1000.0
}

fn load_tls(path: &Path) -> Result<Arc<ClientConfig>> {
    let _ = rustls::crypto::ring::default_provider().install_default();
    let bytes = std::fs::read(path).with_context(|| format!("reading CA certificate {path:?}"))?;
    let mut roots = RootCertStore::empty();
    let mut reader = std::io::Cursor::new(bytes);
    for certificate in rustls_pemfile::certs(&mut reader) {
        roots.add(certificate?)?;
    }
    if roots.is_empty() {
        bail!("CA file contained no certificates");
    }
    Ok(Arc::new(
        ClientConfig::builder()
            .with_root_certificates(roots)
            .with_no_client_auth(),
    ))
}
