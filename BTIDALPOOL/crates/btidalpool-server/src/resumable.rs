//! Durable, idempotent storage for BTPL v2 resumable uploads.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use btidalpool_proto::{canonical_sha1, exact_sha256, UploadReceipt, V2ErrorKind};
use parking_lot::Mutex;
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use thiserror::Error;

use crate::handlers::MAX_UPLOAD_BYTES;
use crate::ingest::IngestSink;
use crate::state::{PublishOutcome, ServerState};

pub const MAX_CHUNK_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_CHUNKS: usize = 1024;
const LOCK_SHARDS: usize = 32;

#[derive(Clone)]
pub struct ResumableStore {
    inner: Arc<Inner>,
}

struct Inner {
    root: PathBuf,
    locks: Vec<Mutex<()>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UploadStatus {
    pub upload_id: String,
    pub missing_chunks: Vec<u32>,
    pub receipt: Option<UploadReceipt>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PutChunkResult {
    pub upload_id: String,
    pub index: u32,
    pub already_present: bool,
}

#[derive(Debug, Error)]
pub enum ResumableError {
    #[error("{0}")]
    BadRequest(String),
    #[error("{0}")]
    NotFound(String),
    #[error("{0}")]
    Conflict(String),
    #[error("{0}")]
    PayloadTooLarge(String),
    #[error("{0}")]
    HashMismatch(String),
    #[error("finalize requires missing chunks: {0:?}")]
    MissingChunks(Vec<u32>),
    #[error("upload ingest failed: {0}")]
    Ingest(String),
    #[error("storage error: {0}")]
    Io(#[from] std::io::Error),
    #[error("stored state is invalid: {0}")]
    State(String),
}

impl ResumableError {
    pub fn kind(&self) -> V2ErrorKind {
        match self {
            Self::BadRequest(_) => V2ErrorKind::BadRequest,
            Self::NotFound(_) => V2ErrorKind::NotFound,
            Self::Conflict(_) | Self::MissingChunks(_) => V2ErrorKind::Conflict,
            Self::PayloadTooLarge(_) => V2ErrorKind::PayloadTooLarge,
            Self::HashMismatch(_) => V2ErrorKind::HashMismatch,
            Self::Ingest(_) | Self::Io(_) | Self::State(_) => V2ErrorKind::Internal,
        }
    }

    pub fn missing_chunks(&self) -> Vec<u32> {
        match self {
            Self::MissingChunks(missing) => missing.clone(),
            _ => Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct StoredManifest {
    protocol_version: u8,
    owner_email: String,
    content_sha256: String,
    total_size: u64,
    chunk_sha256: Vec<String>,
    use_test_db: bool,
    created_at_unix: u64,
}

impl ResumableStore {
    pub fn initialize(root: impl Into<PathBuf>) -> std::io::Result<Self> {
        let root = root.into();
        fs::create_dir_all(&root)?;
        sync_directory(&root)?;
        Ok(Self {
            inner: Arc::new(Inner {
                root,
                locks: (0..LOCK_SHARDS).map(|_| Mutex::new(())).collect(),
            }),
        })
    }

    pub fn submit_manifest(
        &self,
        email: &str,
        content_sha256: String,
        total_size: u64,
        chunk_sha256: Vec<String>,
        use_test_db: bool,
    ) -> Result<UploadStatus, ResumableError> {
        validate_manifest(&content_sha256, total_size, &chunk_sha256)?;
        let owner_email = email.to_ascii_lowercase();
        let upload_id = manifest_id(
            &owner_email,
            &content_sha256,
            total_size,
            &chunk_sha256,
            use_test_db,
        );
        let _guard = self.shard(&upload_id).lock();
        let upload_dir = self.upload_dir(&upload_id);
        fs::create_dir_all(upload_dir.join("chunks"))?;
        sync_directory(&self.inner.root)?;

        let manifest_path = upload_dir.join("manifest.json");
        if manifest_path.exists() {
            let stored: StoredManifest = read_json(&manifest_path)?;
            if stored.owner_email != owner_email
                || stored.content_sha256 != content_sha256
                || stored.total_size != total_size
                || stored.chunk_sha256 != chunk_sha256
                || stored.use_test_db != use_test_db
            {
                return Err(ResumableError::Conflict(
                    "upload id already exists with a different manifest".into(),
                ));
            }
        } else {
            let manifest = StoredManifest {
                protocol_version: 2,
                owner_email,
                content_sha256,
                total_size,
                chunk_sha256,
                use_test_db,
                created_at_unix: unix_now(),
            };
            atomic_write_json(&manifest_path, &manifest)?;
            sync_directory(&upload_dir)?;
        }
        self.status_locked(email, &upload_id)
    }

    pub fn status(&self, email: &str, upload_id: &str) -> Result<UploadStatus, ResumableError> {
        validate_upload_id(upload_id)?;
        let _guard = self.shard(upload_id).lock();
        self.status_locked(email, upload_id)
    }

    pub fn put_chunk(
        &self,
        email: &str,
        upload_id: &str,
        index: u32,
        data: &[u8],
    ) -> Result<PutChunkResult, ResumableError> {
        validate_upload_id(upload_id)?;
        let _guard = self.shard(upload_id).lock();
        let manifest = self.load_owned_manifest(email, upload_id)?;
        let expected = manifest.chunk_sha256.get(index as usize).ok_or_else(|| {
            ResumableError::BadRequest(format!("chunk index {index} is out of range"))
        })?;
        if data.is_empty() {
            return Err(ResumableError::BadRequest(
                "chunks must contain at least one byte".into(),
            ));
        }
        if data.len() > MAX_CHUNK_BYTES {
            return Err(ResumableError::PayloadTooLarge(format!(
                "chunk is {} bytes; maximum is {MAX_CHUNK_BYTES}",
                data.len()
            )));
        }
        let actual = exact_sha256(data);
        if &actual != expected {
            return Err(ResumableError::HashMismatch(format!(
                "chunk {index} SHA-256 does not match the manifest"
            )));
        }

        let chunk_path = self.chunk_path(upload_id, index);
        if chunk_path.exists() {
            let existing = fs::read(&chunk_path)?;
            if exact_sha256(&existing) == *expected {
                return Ok(PutChunkResult {
                    upload_id: upload_id.into(),
                    index,
                    already_present: true,
                });
            }
        }

        let mut stored_bytes = data.len() as u64;
        for other_index in 0..manifest.chunk_sha256.len() as u32 {
            if other_index == index {
                continue;
            }
            let path = self.chunk_path(upload_id, other_index);
            if let Ok(metadata) = fs::metadata(path) {
                stored_bytes = stored_bytes.saturating_add(metadata.len());
            }
        }
        if stored_bytes > manifest.total_size {
            return Err(ResumableError::PayloadTooLarge(
                "stored chunk bytes would exceed manifest total_size".into(),
            ));
        }

        atomic_write(&chunk_path, data)?;
        Ok(PutChunkResult {
            upload_id: upload_id.into(),
            index,
            already_present: false,
        })
    }

    pub fn finalize(
        &self,
        email: &str,
        upload_id: &str,
        state: &ServerState,
        ingest: &dyn IngestSink,
    ) -> Result<UploadReceipt, ResumableError> {
        validate_upload_id(upload_id)?;
        let _guard = self.shard(upload_id).lock();
        let manifest = self.load_owned_manifest(email, upload_id)?;
        let receipt_path = self.upload_dir(upload_id).join("receipt.json");
        if receipt_path.exists() {
            return read_json(&receipt_path);
        }

        let missing = self.missing_chunks(upload_id, &manifest)?;
        if !missing.is_empty() {
            return Err(ResumableError::MissingChunks(missing));
        }

        let mut assembled = Vec::with_capacity(manifest.total_size as usize);
        for index in 0..manifest.chunk_sha256.len() as u32 {
            let bytes = fs::read(self.chunk_path(upload_id, index))?;
            if exact_sha256(&bytes) != manifest.chunk_sha256[index as usize] {
                return Err(ResumableError::HashMismatch(format!(
                    "stored chunk {index} is corrupt"
                )));
            }
            assembled.extend_from_slice(&bytes);
            if assembled.len() > MAX_UPLOAD_BYTES {
                return Err(ResumableError::PayloadTooLarge(
                    "assembled upload exceeds server maximum".into(),
                ));
            }
        }
        if assembled.len() as u64 != manifest.total_size {
            return Err(ResumableError::HashMismatch(format!(
                "assembled size {} does not match manifest total_size {}",
                assembled.len(),
                manifest.total_size
            )));
        }
        if exact_sha256(&assembled) != manifest.content_sha256 {
            return Err(ResumableError::HashMismatch(
                "assembled content SHA-256 does not match manifest".into(),
            ));
        }
        let canonical_sha1 = canonical_sha1(&assembled).map_err(|error| {
            ResumableError::BadRequest(format!("assembled upload is not valid JSON: {error}"))
        })?;

        let staged_path = self.upload_dir(upload_id).join("assembled.json");
        atomic_write(&staged_path, &assembled)?;
        ingest
            .ingest_file(&staged_path, manifest.use_test_db)
            .map_err(|error| ResumableError::Ingest(error.to_string()))?;
        let publish = state.publish_staged_upload(
            &staged_path,
            &canonical_sha1,
            &manifest.owner_email,
            &timestamp_for_filename(),
        )?;
        let deduplicated = matches!(publish, PublishOutcome::AlreadyExists);

        let completed_at_unix = unix_now();
        let receipt_id = exact_sha256(
            format!(
                "btidalpool-v2-receipt\0{upload_id}\0{}\0{canonical_sha1}\0{}\0{completed_at_unix}\0{}",
                manifest.content_sha256, manifest.total_size, manifest.use_test_db
            )
            .as_bytes(),
        );
        let receipt = UploadReceipt {
            receipt_id,
            upload_id: upload_id.into(),
            content_sha256: manifest.content_sha256,
            canonical_sha1,
            total_size: manifest.total_size,
            completed_at_unix,
            use_test_db: manifest.use_test_db,
            deduplicated,
        };
        atomic_write_json(&receipt_path, &receipt)?;
        Ok(receipt)
    }

    pub fn root(&self) -> &Path {
        &self.inner.root
    }

    fn status_locked(&self, email: &str, upload_id: &str) -> Result<UploadStatus, ResumableError> {
        let manifest = self.load_owned_manifest(email, upload_id)?;
        let receipt_path = self.upload_dir(upload_id).join("receipt.json");
        let receipt = if receipt_path.exists() {
            Some(read_json(&receipt_path)?)
        } else {
            None
        };
        let missing_chunks = if receipt.is_some() {
            Vec::new()
        } else {
            self.missing_chunks(upload_id, &manifest)?
        };
        Ok(UploadStatus {
            upload_id: upload_id.into(),
            missing_chunks,
            receipt,
        })
    }

    fn missing_chunks(
        &self,
        upload_id: &str,
        manifest: &StoredManifest,
    ) -> Result<Vec<u32>, ResumableError> {
        let mut missing = Vec::new();
        for (index, expected) in manifest.chunk_sha256.iter().enumerate() {
            let path = self.chunk_path(upload_id, index as u32);
            match fs::read(path) {
                Ok(bytes) if exact_sha256(&bytes) == *expected => {}
                Ok(_) => missing.push(index as u32),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    missing.push(index as u32)
                }
                Err(error) => return Err(error.into()),
            }
        }
        Ok(missing)
    }

    fn load_owned_manifest(
        &self,
        email: &str,
        upload_id: &str,
    ) -> Result<StoredManifest, ResumableError> {
        let path = self.upload_dir(upload_id).join("manifest.json");
        if !path.exists() {
            return Err(ResumableError::NotFound("upload manifest not found".into()));
        }
        let manifest: StoredManifest = read_json(&path)?;
        if manifest.protocol_version != 2 {
            return Err(ResumableError::State(
                "unsupported stored manifest version".into(),
            ));
        }
        if manifest.owner_email != email.to_ascii_lowercase() {
            // Do not reveal whether another identity owns the upload.
            return Err(ResumableError::NotFound("upload manifest not found".into()));
        }
        Ok(manifest)
    }

    fn upload_dir(&self, upload_id: &str) -> PathBuf {
        self.inner.root.join(upload_id)
    }

    fn chunk_path(&self, upload_id: &str, index: u32) -> PathBuf {
        self.upload_dir(upload_id)
            .join("chunks")
            .join(format!("{index:08}.chunk"))
    }

    fn shard(&self, upload_id: &str) -> &Mutex<()> {
        let prefix = upload_id.get(..8).unwrap_or("0");
        let value = u32::from_str_radix(prefix, 16).unwrap_or(0) as usize;
        &self.inner.locks[value % self.inner.locks.len()]
    }
}

fn validate_manifest(
    content_sha256: &str,
    total_size: u64,
    chunk_sha256: &[String],
) -> Result<(), ResumableError> {
    if !is_sha256(content_sha256) {
        return Err(ResumableError::BadRequest(
            "content_sha256 must be 64 lowercase hexadecimal characters".into(),
        ));
    }
    if total_size == 0 {
        return Err(ResumableError::BadRequest(
            "total_size must be greater than zero".into(),
        ));
    }
    if total_size > MAX_UPLOAD_BYTES as u64 {
        return Err(ResumableError::PayloadTooLarge(format!(
            "total_size exceeds maximum of {MAX_UPLOAD_BYTES} bytes"
        )));
    }
    if chunk_sha256.is_empty() || chunk_sha256.len() > MAX_CHUNKS {
        return Err(ResumableError::BadRequest(format!(
            "chunk_sha256 must contain between 1 and {MAX_CHUNKS} hashes"
        )));
    }
    if chunk_sha256.iter().any(|hash| !is_sha256(hash)) {
        return Err(ResumableError::BadRequest(
            "every chunk SHA-256 must be 64 lowercase hexadecimal characters".into(),
        ));
    }
    Ok(())
}

fn validate_upload_id(upload_id: &str) -> Result<(), ResumableError> {
    if is_sha256(upload_id) {
        Ok(())
    } else {
        Err(ResumableError::BadRequest(
            "upload_id must be 64 lowercase hexadecimal characters".into(),
        ))
    }
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn manifest_id(
    owner_email: &str,
    content_sha256: &str,
    total_size: u64,
    chunk_sha256: &[String],
    use_test_db: bool,
) -> String {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"btidalpool-v2-manifest\0");
    bytes.extend_from_slice(owner_email.as_bytes());
    bytes.push(0);
    bytes.extend_from_slice(content_sha256.as_bytes());
    bytes.extend_from_slice(&total_size.to_be_bytes());
    bytes.push(use_test_db as u8);
    for hash in chunk_sha256 {
        bytes.extend_from_slice(hash.as_bytes());
    }
    exact_sha256(&bytes)
}

fn atomic_write_json<T: Serialize>(path: &Path, value: &T) -> Result<(), ResumableError> {
    let bytes = serde_json::to_vec_pretty(value)
        .map_err(|error| ResumableError::State(error.to_string()))?;
    atomic_write(path, &bytes)?;
    Ok(())
}

fn atomic_write(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    let parent = path.parent().ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::InvalidInput, "path has no parent")
    })?;
    fs::create_dir_all(parent)?;
    let temp_path = path.with_extension("tmp");
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&temp_path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);
    fs::rename(&temp_path, path)?;
    sync_directory(parent)
}

fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T, ResumableError> {
    let bytes = fs::read(path)?;
    serde_json::from_slice(&bytes)
        .map_err(|error| ResumableError::State(format!("{}: {error}", path.display())))
}

fn sync_directory(path: &Path) -> std::io::Result<()> {
    File::open(path)?.sync_all()
}

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

fn timestamp_for_filename() -> String {
    let (year, month, day, hour, minute, second) =
        crate::handlers::ymd_hms_from_unix(unix_now() as i64);
    format!("{year:04}-{month:02}-{day:02}-{hour:02}-{minute:02}-{second:02}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ingest::{IngestError, NoopIngestSink};
    use tempfile::tempdir;

    fn chunks() -> (Vec<u8>, Vec<Vec<u8>>, Vec<String>) {
        let parts = vec![b"[{\"a\":".to_vec(), b"1}]".to_vec()];
        let all = parts.concat();
        let hashes = parts.iter().map(|part| exact_sha256(part)).collect();
        (all, parts, hashes)
    }

    fn state(td: &tempfile::TempDir) -> ServerState {
        ServerState::initialize(
            td.path().join("pool"),
            td.path().join("logs"),
            td.path().join("access.log"),
        )
        .unwrap()
    }

    #[test]
    fn resume_survives_store_restart() {
        let td = tempdir().unwrap();
        let (all, parts, hashes) = chunks();
        let store = ResumableStore::initialize(td.path().join("v2")).unwrap();
        let first = store
            .submit_manifest(
                "u@example.com",
                exact_sha256(&all),
                all.len() as u64,
                hashes.clone(),
                false,
            )
            .unwrap();
        store
            .put_chunk("u@example.com", &first.upload_id, 0, &parts[0])
            .unwrap();
        drop(store);

        let restarted = ResumableStore::initialize(td.path().join("v2")).unwrap();
        let resumed = restarted
            .submit_manifest(
                "u@example.com",
                exact_sha256(&all),
                all.len() as u64,
                hashes,
                false,
            )
            .unwrap();
        assert_eq!(resumed.upload_id, first.upload_id);
        assert_eq!(resumed.missing_chunks, vec![1]);
    }

    #[test]
    fn out_of_order_corrupt_and_missing_chunks_are_reported() {
        let td = tempdir().unwrap();
        let (all, parts, hashes) = chunks();
        let store = ResumableStore::initialize(td.path().join("v2")).unwrap();
        let status = store
            .submit_manifest(
                "u@example.com",
                exact_sha256(&all),
                all.len() as u64,
                hashes,
                false,
            )
            .unwrap();
        store
            .put_chunk("u@example.com", &status.upload_id, 1, &parts[1])
            .unwrap();
        assert_eq!(
            store
                .status("u@example.com", &status.upload_id)
                .unwrap()
                .missing_chunks,
            vec![0]
        );

        fs::write(store.chunk_path(&status.upload_id, 1), b"corrupt").unwrap();
        assert_eq!(
            store
                .status("u@example.com", &status.upload_id)
                .unwrap()
                .missing_chunks,
            vec![0, 1]
        );
        assert!(matches!(
            store.finalize(
                "u@example.com",
                &status.upload_id,
                &state(&td),
                &NoopIngestSink
            ),
            Err(ResumableError::MissingChunks(missing)) if missing == vec![0, 1]
        ));
    }

    #[test]
    fn manifest_chunk_and_finalize_replays_are_idempotent() {
        let td = tempdir().unwrap();
        let pool_state = state(&td);
        let (all, parts, hashes) = chunks();
        let store = ResumableStore::initialize(td.path().join("v2")).unwrap();
        let first = store
            .submit_manifest(
                "u@example.com",
                exact_sha256(&all),
                all.len() as u64,
                hashes.clone(),
                false,
            )
            .unwrap();
        let replay = store
            .submit_manifest(
                "u@example.com",
                exact_sha256(&all),
                all.len() as u64,
                hashes,
                false,
            )
            .unwrap();
        assert_eq!(replay.upload_id, first.upload_id);
        for (index, part) in parts.iter().enumerate() {
            let put = store
                .put_chunk("u@example.com", &first.upload_id, index as u32, part)
                .unwrap();
            assert!(!put.already_present);
            let replay_put = store
                .put_chunk("u@example.com", &first.upload_id, index as u32, part)
                .unwrap();
            assert!(replay_put.already_present);
        }
        let receipt = store
            .finalize(
                "u@example.com",
                &first.upload_id,
                &pool_state,
                &NoopIngestSink,
            )
            .unwrap();
        let replay_receipt = store
            .finalize(
                "u@example.com",
                &first.upload_id,
                &pool_state,
                &NoopIngestSink,
            )
            .unwrap();
        assert_eq!(receipt, replay_receipt);
        assert_eq!(fs::read_dir(pool_state.pool_dir()).unwrap().count(), 1);
    }

    struct FailingIngest;

    impl IngestSink for FailingIngest {
        fn ingest_file(&self, _path: &Path, _use_test_db: bool) -> Result<(), IngestError> {
            Err(IngestError::Backend("test failure".into()))
        }
    }

    #[test]
    fn failed_finalize_never_publishes_partial_file_or_receipt() {
        let td = tempdir().unwrap();
        let pool_state = state(&td);
        let (all, parts, hashes) = chunks();
        let store = ResumableStore::initialize(td.path().join("v2")).unwrap();
        let status = store
            .submit_manifest(
                "u@example.com",
                exact_sha256(&all),
                all.len() as u64,
                hashes,
                false,
            )
            .unwrap();
        for (index, part) in parts.iter().enumerate() {
            store
                .put_chunk("u@example.com", &status.upload_id, index as u32, part)
                .unwrap();
        }
        assert!(matches!(
            store.finalize(
                "u@example.com",
                &status.upload_id,
                &pool_state,
                &FailingIngest
            ),
            Err(ResumableError::Ingest(_))
        ));
        assert_eq!(fs::read_dir(pool_state.pool_dir()).unwrap().count(), 0);
        assert!(!store
            .upload_dir(&status.upload_id)
            .join("receipt.json")
            .exists());
    }

    #[test]
    fn corrupt_upload_never_finalizes() {
        let td = tempdir().unwrap();
        let pool_state = state(&td);
        let (all, parts, hashes) = chunks();
        let store = ResumableStore::initialize(td.path().join("v2")).unwrap();
        let status = store
            .submit_manifest(
                "u@example.com",
                exact_sha256(b"different"),
                all.len() as u64,
                hashes,
                false,
            )
            .unwrap();
        for (index, part) in parts.iter().enumerate() {
            store
                .put_chunk("u@example.com", &status.upload_id, index as u32, part)
                .unwrap();
        }
        assert!(matches!(
            store.finalize(
                "u@example.com",
                &status.upload_id,
                &pool_state,
                &NoopIngestSink
            ),
            Err(ResumableError::HashMismatch(_))
        ));
        assert_eq!(fs::read_dir(pool_state.pool_dir()).unwrap().count(), 0);
    }
}
