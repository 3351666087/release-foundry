use std::collections::{BTreeMap, HashSet};
#[cfg(unix)]
use std::ffi::CString;
use std::fmt::Write;
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{self, Read};
#[cfg(unix)]
use std::os::fd::{AsRawFd, FromRawFd};
use std::path::{Path, PathBuf};

#[cfg(unix)]
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
#[cfg(windows)]
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
#[cfg(windows)]
use std::os::windows::io::AsRawHandle;

use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

#[cfg(windows)]
use windows_sys::Win32::Foundation::HANDLE;
#[cfg(windows)]
use windows_sys::Win32::Storage::FileSystem::{
    GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION, FILE_ATTRIBUTE_REPARSE_POINT,
    FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT,
};

pub const AUTHENTICATED_ENVELOPE_SCHEMA_VERSION: &str =
    "releasefoundry.identity_verification.authenticated_envelope.v1";
pub const AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION: &str =
    "releasefoundry.a1.authenticated_evidence_bundle.v2";
pub const HMAC_SHA256_ALGORITHM: &str = "hmac-sha256";
pub const SHA256_ALGORITHM: &str = "sha256";
pub const MIN_HMAC_KEY_BYTES: usize = 32;
pub const SHA256_HEX_LENGTH: usize = 64;
pub const MAX_EVIDENCE_ITEMS: usize = 10_000;
pub const MAX_ARTIFACT_PATH_BYTES: usize = 1_024;
pub const DEFAULT_MAX_ARTIFACT_BYTES: u64 = 1024 * 1024 * 1024;
pub const DEFAULT_MAX_TOTAL_ARTIFACT_BYTES: u64 = 4 * DEFAULT_MAX_ARTIFACT_BYTES;
const STREAM_BUFFER_BYTES: usize = 64 * 1024;

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AuthenticatedEnvelope {
    pub schema_version: String,
    pub algorithm: String,
    pub key_id: String,
    pub purpose: VerificationPurpose,
    pub tenant_digest: String,
    pub project_digest: String,
    pub principal_digest: String,
    pub event_id_digest: String,
    pub idempotency_key_digest: String,
    pub request_digest: String,
    pub nonce_digest: String,
    pub payload_digest: String,
    pub evidence_digest: String,
    pub issued_at_unix_ms: u64,
    pub expires_at_unix_ms: u64,
    pub signature: String,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum VerificationPurpose {
    CredentialBinding,
    Login,
    AccountRecovery,
    EvidenceAttestation,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct SigningPayload<'a> {
    schema_version: &'a str,
    algorithm: &'a str,
    key_id: &'a str,
    purpose: VerificationPurpose,
    tenant_digest: &'a str,
    project_digest: &'a str,
    principal_digest: &'a str,
    event_id_digest: &'a str,
    idempotency_key_digest: &'a str,
    request_digest: &'a str,
    nonce_digest: &'a str,
    payload_digest: &'a str,
    evidence_digest: &'a str,
    issued_at_unix_ms: u64,
    expires_at_unix_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EvidenceArtifact {
    pub artifact_path: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub media_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AuthenticatedEvidenceBundle {
    pub schema_version: String,
    pub algorithm: String,
    pub key_id: String,
    pub bundle_id_digest: String,
    pub tenant_digest: String,
    pub project_digest: String,
    pub evidence: Vec<EvidenceArtifact>,
    pub evidence_digest: String,
    pub issued_at_unix_ms: u64,
    pub expires_at_unix_ms: u64,
    pub signature: String,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct EvidenceBundleSigningPayload<'a> {
    schema_version: &'a str,
    algorithm: &'a str,
    key_id: &'a str,
    bundle_id_digest: &'a str,
    tenant_digest: &'a str,
    project_digest: &'a str,
    evidence_digest: &'a str,
    issued_at_unix_ms: u64,
    expires_at_unix_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
#[non_exhaustive]
pub struct VerifiedEvidenceBundle {
    pub bundle: AuthenticatedEvidenceBundle,
    pub canonical_signing_bytes: Vec<u8>,
    pub authenticated_bundle_digest: String,
    // Anchors the public snapshot fields against coherent post-verification mutation.
    authentication_binding: [u8; 32],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedEvidenceObject {
    pub artifact_path: String,
    pub size_bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedEvidenceObjects {
    pub objects: Vec<VerifiedEvidenceObject>,
    pub total_size_bytes: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EvidenceObjectVerificationPolicy {
    pub max_object_bytes: u64,
    pub max_total_bytes: u64,
}

impl Default for EvidenceObjectVerificationPolicy {
    fn default() -> Self {
        Self {
            max_object_bytes: DEFAULT_MAX_ARTIFACT_BYTES,
            max_total_bytes: DEFAULT_MAX_TOTAL_ARTIFACT_BYTES,
        }
    }
}

#[derive(Debug)]
pub struct LocalEvidenceObjectRoot {
    canonical_root: PathBuf,
    root_handle: File,
    root_identity: FileIdentity,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplayGuardInput {
    pub tenant_digest: String,
    pub project_digest: String,
    pub event_id_digest: String,
    pub idempotency_key_digest: String,
    pub request_digest: String,
    pub nonce_digest: String,
    pub expires_at_unix_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedEnvelope {
    pub envelope: AuthenticatedEnvelope,
    pub canonical_signing_bytes: Vec<u8>,
    pub envelope_digest: String,
    pub replay_guard: ReplayGuardInput,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerificationPolicy {
    pub now_unix_ms: u64,
    pub max_lifetime_ms: u64,
    pub expected_tenant_digest: Option<String>,
    pub expected_project_digest: Option<String>,
    pub expected_bundle_id_digest: Option<String>,
}

impl VerificationPolicy {
    pub fn at(now_unix_ms: u64) -> Self {
        Self {
            now_unix_ms,
            max_lifetime_ms: 15 * 60 * 1000,
            expected_tenant_digest: None,
            expected_project_digest: None,
            expected_bundle_id_digest: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReplayDecision {
    Fresh,
    IdempotentReplay,
    Conflict,
    ReplayedNonce,
}

pub trait ReplayGuard {
    fn inspect(&self, input: &ReplayGuardInput) -> Result<ReplayDecision, VerifyError>;
}

pub trait SignatureVerifier {
    fn verify(
        &self,
        key_id: &str,
        canonical_signing_bytes: &[u8],
        signature: &[u8],
    ) -> Result<(), VerifyError>;
}

pub struct HmacSha256Verifier<'a> {
    key_id: &'a str,
    key: &'a [u8],
}

impl<'a> HmacSha256Verifier<'a> {
    pub fn new(key_id: &'a str, key: &'a [u8]) -> Result<Self, VerifyError> {
        validate_key_id(key_id)?;
        if key.len() < MIN_HMAC_KEY_BYTES {
            return Err(VerifyError::InvalidKey);
        }
        Ok(Self { key_id, key })
    }
}

impl SignatureVerifier for HmacSha256Verifier<'_> {
    fn verify(
        &self,
        key_id: &str,
        canonical_signing_bytes: &[u8],
        signature: &[u8],
    ) -> Result<(), VerifyError> {
        if self.key_id.as_bytes().ct_eq(key_id.as_bytes()).unwrap_u8() != 1 {
            return Err(VerifyError::UnknownKey);
        }
        let mut mac = HmacSha256::new_from_slice(self.key).map_err(|_| VerifyError::InvalidKey)?;
        mac.update(canonical_signing_bytes);
        mac.verify_slice(signature)
            .map_err(|_| VerifyError::SignatureMismatch)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerifyError {
    InvalidJson(String),
    InvalidSchema(&'static str),
    InvalidField(&'static str),
    InvalidDigest(&'static str),
    InvalidSignatureEncoding,
    InvalidKey,
    UnknownKey,
    SignatureMismatch,
    NotYetValid,
    Expired,
    LifetimeExceeded,
    ScopeMismatch(&'static str),
    ReplayConflict,
    ReplayedNonce,
    ReplayStoreUnavailable,
    EvidenceLimitExceeded,
    UnsafeArtifactPath,
    DuplicateArtifactPath,
    EvidenceDigestMismatch,
    ArtifactSizeLimitExceeded,
    ArtifactTotalSizeLimitExceeded,
    ArtifactOpenFailed,
    ArtifactReadFailed,
    ArtifactUndersize,
    ArtifactOversize,
    ArtifactDigestMismatch,
    ArtifactNotRegularFile,
    ArtifactSymlinkRejected,
    ArtifactRootEscape,
    ArtifactRootNotDirectory,
    ArtifactIdentityUnavailable,
    ArtifactChangedDuringVerification,
    DuplicateArtifactReference,
}

impl std::fmt::Display for VerifyError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidJson(message) => write!(formatter, "invalid JSON: {message}"),
            Self::InvalidSchema(message) => write!(formatter, "invalid schema: {message}"),
            Self::InvalidField(field) => write!(formatter, "invalid field: {field}"),
            Self::InvalidDigest(field) => write!(formatter, "invalid SHA-256 digest: {field}"),
            Self::InvalidSignatureEncoding => {
                formatter.write_str("signature must be 64 lowercase hexadecimal characters")
            }
            Self::InvalidKey => formatter.write_str("verification key is invalid"),
            Self::UnknownKey => formatter.write_str("verification key id is not available"),
            Self::SignatureMismatch => {
                formatter.write_str("authenticated envelope signature mismatch")
            }
            Self::NotYetValid => formatter.write_str("authenticated envelope is not yet valid"),
            Self::Expired => formatter.write_str("authenticated envelope has expired"),
            Self::LifetimeExceeded => {
                formatter.write_str("authenticated envelope lifetime exceeds policy")
            }
            Self::ScopeMismatch(field) => {
                write!(formatter, "authenticated envelope {field} mismatch")
            }
            Self::ReplayConflict => {
                formatter.write_str("idempotency key was reused with a different request")
            }
            Self::ReplayedNonce => formatter.write_str("authenticated envelope nonce was replayed"),
            Self::ReplayStoreUnavailable => formatter.write_str("replay guard is unavailable"),
            Self::EvidenceLimitExceeded => {
                formatter.write_str("authenticated evidence bundle item limit exceeded")
            }
            Self::UnsafeArtifactPath => {
                formatter.write_str("artifact path must be a confined relative POSIX path")
            }
            Self::DuplicateArtifactPath => {
                formatter.write_str("authenticated evidence bundle contains a duplicate path")
            }
            Self::EvidenceDigestMismatch => {
                formatter.write_str("authenticated evidence bundle digest mismatch")
            }
            Self::ArtifactSizeLimitExceeded => {
                formatter.write_str("artifact declared size exceeds verification policy")
            }
            Self::ArtifactTotalSizeLimitExceeded => {
                formatter.write_str("artifact declared total size exceeds verification policy")
            }
            Self::ArtifactOpenFailed => formatter.write_str("artifact could not be opened"),
            Self::ArtifactReadFailed => {
                formatter.write_str("artifact stream ended with an I/O failure")
            }
            Self::ArtifactUndersize => {
                formatter.write_str("artifact stream ended before its declared length")
            }
            Self::ArtifactOversize => {
                formatter.write_str("artifact stream exceeded its declared length")
            }
            Self::ArtifactDigestMismatch => {
                formatter.write_str("artifact SHA-256 does not match its declaration")
            }
            Self::ArtifactNotRegularFile => {
                formatter.write_str("artifact path is not a regular file")
            }
            Self::ArtifactSymlinkRejected => {
                formatter.write_str("artifact path contains a symlink or reparse point")
            }
            Self::ArtifactRootEscape => {
                formatter.write_str("artifact path escaped the configured object root")
            }
            Self::ArtifactRootNotDirectory => {
                formatter.write_str("configured artifact object root is not a directory")
            }
            Self::ArtifactIdentityUnavailable => {
                formatter.write_str("artifact file identity could not be established")
            }
            Self::ArtifactChangedDuringVerification => {
                formatter.write_str("artifact changed while it was being verified")
            }
            Self::DuplicateArtifactReference => {
                formatter.write_str("multiple artifact paths reference the same local object")
            }
        }
    }
}

impl std::error::Error for VerifyError {}

impl AuthenticatedEnvelope {
    pub fn parse_strict(input: &str) -> Result<Self, VerifyError> {
        reject_duplicate_object_keys(input)?;
        let envelope: Self = serde_json::from_str(input)
            .map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
        envelope.validate_schema()?;
        Ok(envelope)
    }

    pub fn canonical_signing_bytes(&self) -> Result<Vec<u8>, VerifyError> {
        let payload = SigningPayload {
            schema_version: &self.schema_version,
            algorithm: &self.algorithm,
            key_id: &self.key_id,
            purpose: self.purpose,
            tenant_digest: &self.tenant_digest,
            project_digest: &self.project_digest,
            principal_digest: &self.principal_digest,
            event_id_digest: &self.event_id_digest,
            idempotency_key_digest: &self.idempotency_key_digest,
            request_digest: &self.request_digest,
            nonce_digest: &self.nonce_digest,
            payload_digest: &self.payload_digest,
            evidence_digest: &self.evidence_digest,
            issued_at_unix_ms: self.issued_at_unix_ms,
            expires_at_unix_ms: self.expires_at_unix_ms,
        };
        let value = serde_json::to_value(payload)
            .map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
        canonical_json_bytes(&value)
    }

    pub fn sign_hmac_sha256(&mut self, key: &[u8]) -> Result<(), VerifyError> {
        if key.len() < MIN_HMAC_KEY_BYTES {
            return Err(VerifyError::InvalidKey);
        }
        self.validate_schema_without_signature()?;
        let mut mac = HmacSha256::new_from_slice(key).map_err(|_| VerifyError::InvalidKey)?;
        mac.update(&self.canonical_signing_bytes()?);
        self.signature = hex::encode(mac.finalize().into_bytes());
        Ok(())
    }

    pub fn verify(
        &self,
        verifier: &dyn SignatureVerifier,
        replay_guard: &dyn ReplayGuard,
        policy: &VerificationPolicy,
    ) -> Result<VerifiedEnvelope, VerifyError> {
        self.validate_schema()?;
        validate_policy(self, policy)?;
        let canonical_signing_bytes = self.canonical_signing_bytes()?;
        let signature =
            hex::decode(&self.signature).map_err(|_| VerifyError::InvalidSignatureEncoding)?;
        verifier.verify(&self.key_id, &canonical_signing_bytes, &signature)?;

        let replay_guard_input = ReplayGuardInput {
            tenant_digest: self.tenant_digest.clone(),
            project_digest: self.project_digest.clone(),
            event_id_digest: self.event_id_digest.clone(),
            idempotency_key_digest: self.idempotency_key_digest.clone(),
            request_digest: self.request_digest.clone(),
            nonce_digest: self.nonce_digest.clone(),
            expires_at_unix_ms: self.expires_at_unix_ms,
        };
        match replay_guard.inspect(&replay_guard_input)? {
            ReplayDecision::Fresh | ReplayDecision::IdempotentReplay => {}
            ReplayDecision::Conflict => return Err(VerifyError::ReplayConflict),
            ReplayDecision::ReplayedNonce => return Err(VerifyError::ReplayedNonce),
        }

        Ok(VerifiedEnvelope {
            envelope: self.clone(),
            envelope_digest: sha256_hex(&canonical_signing_bytes),
            canonical_signing_bytes,
            replay_guard: replay_guard_input,
        })
    }

    fn validate_schema(&self) -> Result<(), VerifyError> {
        self.validate_schema_without_signature()?;
        if !is_lower_hex_sha256(&self.signature) {
            return Err(VerifyError::InvalidSignatureEncoding);
        }
        Ok(())
    }

    fn validate_schema_without_signature(&self) -> Result<(), VerifyError> {
        if self.schema_version != AUTHENTICATED_ENVELOPE_SCHEMA_VERSION {
            return Err(VerifyError::InvalidSchema("unsupported schema_version"));
        }
        if self.algorithm != HMAC_SHA256_ALGORITHM {
            return Err(VerifyError::InvalidSchema("unsupported algorithm"));
        }
        validate_key_id(&self.key_id)?;
        for (field, digest) in [
            ("tenant_digest", &self.tenant_digest),
            ("project_digest", &self.project_digest),
            ("principal_digest", &self.principal_digest),
            ("event_id_digest", &self.event_id_digest),
            ("idempotency_key_digest", &self.idempotency_key_digest),
            ("request_digest", &self.request_digest),
            ("nonce_digest", &self.nonce_digest),
            ("payload_digest", &self.payload_digest),
            ("evidence_digest", &self.evidence_digest),
        ] {
            if !is_lower_hex_sha256(digest) {
                return Err(VerifyError::InvalidDigest(field));
            }
        }
        if self.issued_at_unix_ms == 0 || self.expires_at_unix_ms <= self.issued_at_unix_ms {
            return Err(VerifyError::InvalidField(
                "issued_at_unix_ms/expires_at_unix_ms",
            ));
        }
        Ok(())
    }
}

impl AuthenticatedEvidenceBundle {
    pub fn parse_strict(input: &str) -> Result<Self, VerifyError> {
        reject_duplicate_object_keys(input)?;
        let bundle: Self = serde_json::from_str(input)
            .map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
        bundle.validate_schema()?;
        Ok(bundle)
    }

    pub fn canonical_evidence_bytes(&self) -> Result<Vec<u8>, VerifyError> {
        let value = serde_json::to_value(&self.evidence)
            .map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
        canonical_json_bytes(&value)
    }

    pub fn canonical_signing_bytes(&self) -> Result<Vec<u8>, VerifyError> {
        let payload = EvidenceBundleSigningPayload {
            schema_version: &self.schema_version,
            algorithm: &self.algorithm,
            key_id: &self.key_id,
            bundle_id_digest: &self.bundle_id_digest,
            tenant_digest: &self.tenant_digest,
            project_digest: &self.project_digest,
            evidence_digest: &self.evidence_digest,
            issued_at_unix_ms: self.issued_at_unix_ms,
            expires_at_unix_ms: self.expires_at_unix_ms,
        };
        let value = serde_json::to_value(payload)
            .map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
        canonical_json_bytes(&value)
    }

    pub fn refresh_evidence_digest(&mut self) -> Result<(), VerifyError> {
        self.evidence_digest = sha256_hex(&self.canonical_evidence_bytes()?);
        Ok(())
    }

    pub fn sign_hmac_sha256(&mut self, key: &[u8]) -> Result<(), VerifyError> {
        if key.len() < MIN_HMAC_KEY_BYTES {
            return Err(VerifyError::InvalidKey);
        }
        self.validate_schema_without_signature_and_digest()?;
        self.refresh_evidence_digest()?;
        let mut mac = HmacSha256::new_from_slice(key).map_err(|_| VerifyError::InvalidKey)?;
        mac.update(&self.canonical_signing_bytes()?);
        self.signature = hex::encode(mac.finalize().into_bytes());
        Ok(())
    }

    pub fn verify(
        &self,
        verifier: &dyn SignatureVerifier,
        policy: &VerificationPolicy,
    ) -> Result<VerifiedEvidenceBundle, VerifyError> {
        self.validate_schema()?;
        validate_bundle_policy(self, policy)?;
        let actual_evidence_digest = sha256_hex(&self.canonical_evidence_bytes()?);
        if actual_evidence_digest
            .as_bytes()
            .ct_eq(self.evidence_digest.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(VerifyError::EvidenceDigestMismatch);
        }
        let canonical_signing_bytes = self.canonical_signing_bytes()?;
        let signature =
            hex::decode(&self.signature).map_err(|_| VerifyError::InvalidSignatureEncoding)?;
        verifier.verify(&self.key_id, &canonical_signing_bytes, &signature)?;
        let authentication_binding = Sha256::digest(&canonical_signing_bytes).into();

        Ok(VerifiedEvidenceBundle {
            bundle: self.clone(),
            authenticated_bundle_digest: sha256_hex(&canonical_signing_bytes),
            canonical_signing_bytes,
            authentication_binding,
        })
    }

    fn validate_schema(&self) -> Result<(), VerifyError> {
        self.validate_schema_without_signature_and_digest()?;
        if !is_lower_hex_sha256(&self.evidence_digest) {
            return Err(VerifyError::InvalidDigest("evidence_digest"));
        }
        if !is_lower_hex_sha256(&self.signature) {
            return Err(VerifyError::InvalidSignatureEncoding);
        }
        Ok(())
    }

    fn validate_schema_without_signature_and_digest(&self) -> Result<(), VerifyError> {
        if self.schema_version != AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION {
            return Err(VerifyError::InvalidSchema("unsupported schema_version"));
        }
        if self.algorithm != HMAC_SHA256_ALGORITHM {
            return Err(VerifyError::InvalidSchema("unsupported algorithm"));
        }
        validate_key_id(&self.key_id)?;
        for (field, digest) in [
            ("bundle_id_digest", &self.bundle_id_digest),
            ("tenant_digest", &self.tenant_digest),
            ("project_digest", &self.project_digest),
        ] {
            if !is_lower_hex_sha256(digest) {
                return Err(VerifyError::InvalidDigest(field));
            }
        }
        if self.evidence.is_empty() {
            return Err(VerifyError::InvalidField("evidence"));
        }
        if self.evidence.len() > MAX_EVIDENCE_ITEMS {
            return Err(VerifyError::EvidenceLimitExceeded);
        }
        let mut artifact_paths = std::collections::HashSet::with_capacity(self.evidence.len());
        for artifact in &self.evidence {
            validate_artifact_path(&artifact.artifact_path)?;
            if !artifact_paths.insert(artifact.artifact_path.as_str()) {
                return Err(VerifyError::DuplicateArtifactPath);
            }
            if !is_lower_hex_sha256(&artifact.sha256) {
                return Err(VerifyError::InvalidDigest("evidence[].sha256"));
            }
            validate_media_type(&artifact.media_type)?;
        }
        if self.issued_at_unix_ms == 0 || self.expires_at_unix_ms <= self.issued_at_unix_ms {
            return Err(VerifyError::InvalidField(
                "issued_at_unix_ms/expires_at_unix_ms",
            ));
        }
        Ok(())
    }
}

impl VerifiedEvidenceBundle {
    pub fn verify_objects<F, R>(
        &self,
        policy: &EvidenceObjectVerificationPolicy,
        mut open: F,
    ) -> Result<VerifiedEvidenceObjects, VerifyError>
    where
        F: FnMut(&EvidenceArtifact) -> Result<R, VerifyError>,
        R: Read,
    {
        let total_size_bytes = self.validate_object_manifest_binding(policy)?;
        let mut objects = Vec::with_capacity(self.bundle.evidence.len());
        for artifact in &self.bundle.evidence {
            let mut reader = open(artifact)?;
            objects.push(verify_artifact_stream(artifact, &mut reader)?);
        }
        Ok(VerifiedEvidenceObjects {
            objects,
            total_size_bytes,
        })
    }

    pub fn verify_local_objects(
        &self,
        object_root: impl AsRef<Path>,
        policy: &EvidenceObjectVerificationPolicy,
    ) -> Result<VerifiedEvidenceObjects, VerifyError> {
        LocalEvidenceObjectRoot::new(object_root)?.verify(self, policy)
    }

    fn validate_object_manifest_binding(
        &self,
        policy: &EvidenceObjectVerificationPolicy,
    ) -> Result<u64, VerifyError> {
        self.bundle.validate_schema()?;
        let actual_evidence_digest = sha256_hex(&self.bundle.canonical_evidence_bytes()?);
        if actual_evidence_digest
            .as_bytes()
            .ct_eq(self.bundle.evidence_digest.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(VerifyError::EvidenceDigestMismatch);
        }

        let current_signing_bytes = self.bundle.canonical_signing_bytes()?;
        let current_authentication_binding: [u8; 32] =
            Sha256::digest(&current_signing_bytes).into();
        if current_signing_bytes
            .as_slice()
            .ct_eq(self.canonical_signing_bytes.as_slice())
            .unwrap_u8()
            != 1
            || current_authentication_binding
                .ct_eq(&self.authentication_binding)
                .unwrap_u8()
                != 1
            || sha256_hex(&current_signing_bytes)
                .as_bytes()
                .ct_eq(self.authenticated_bundle_digest.as_bytes())
                .unwrap_u8()
                != 1
        {
            return Err(VerifyError::EvidenceDigestMismatch);
        }

        let mut total_size_bytes = 0_u64;
        let mut artifact_paths = HashSet::with_capacity(self.bundle.evidence.len());
        for artifact in &self.bundle.evidence {
            validate_artifact_path(&artifact.artifact_path)?;
            if !artifact_paths.insert(artifact.artifact_path.as_str()) {
                return Err(VerifyError::DuplicateArtifactPath);
            }
            if artifact.size_bytes > policy.max_object_bytes {
                return Err(VerifyError::ArtifactSizeLimitExceeded);
            }
            total_size_bytes = total_size_bytes
                .checked_add(artifact.size_bytes)
                .ok_or(VerifyError::ArtifactTotalSizeLimitExceeded)?;
            if total_size_bytes > policy.max_total_bytes {
                return Err(VerifyError::ArtifactTotalSizeLimitExceeded);
            }
        }
        Ok(total_size_bytes)
    }
}

impl LocalEvidenceObjectRoot {
    pub fn new(root: impl AsRef<Path>) -> Result<Self, VerifyError> {
        let root = root.as_ref();
        let supplied_metadata =
            fs::symlink_metadata(root).map_err(|_| VerifyError::ArtifactOpenFailed)?;
        reject_link_or_reparse(&supplied_metadata)?;
        if !supplied_metadata.is_dir() {
            return Err(VerifyError::ArtifactRootNotDirectory);
        }

        let canonical_root = fs::canonicalize(root).map_err(|_| VerifyError::ArtifactOpenFailed)?;
        let canonical_metadata =
            fs::symlink_metadata(&canonical_root).map_err(|_| VerifyError::ArtifactOpenFailed)?;
        reject_link_or_reparse(&canonical_metadata)?;
        if !canonical_metadata.is_dir() {
            return Err(VerifyError::ArtifactRootNotDirectory);
        }

        let root_handle = open_directory_no_follow(&canonical_root)
            .map_err(|_| VerifyError::ArtifactOpenFailed)?;
        let handle_metadata = root_handle
            .metadata()
            .map_err(|_| VerifyError::ArtifactIdentityUnavailable)?;
        reject_link_or_reparse(&handle_metadata)?;
        if !handle_metadata.is_dir() {
            return Err(VerifyError::ArtifactRootNotDirectory);
        }
        let root_identity = file_identity(&root_handle)?;

        Ok(Self {
            canonical_root,
            root_handle,
            root_identity,
        })
    }

    pub fn canonical_path(&self) -> &Path {
        &self.canonical_root
    }

    pub fn verify(
        &self,
        verified_bundle: &VerifiedEvidenceBundle,
        policy: &EvidenceObjectVerificationPolicy,
    ) -> Result<VerifiedEvidenceObjects, VerifyError> {
        let total_size_bytes = verified_bundle.validate_object_manifest_binding(policy)?;
        let mut objects = Vec::with_capacity(verified_bundle.bundle.evidence.len());
        let mut seen_objects = HashSet::with_capacity(verified_bundle.bundle.evidence.len());

        for artifact in &verified_bundle.bundle.evidence {
            self.ensure_root_stable()?;
            let canonical_before = self.inspect_artifact_path(&artifact.artifact_path)?;
            let mut file = self.open_artifact_file(&artifact.artifact_path)?;
            let metadata_before = regular_file_metadata(&file)?;
            let identity = file_identity(&file)?;
            self.confirm_path_binding(&artifact.artifact_path, &canonical_before, identity)?;

            if !seen_objects.insert(identity) {
                return Err(VerifyError::DuplicateArtifactReference);
            }
            match metadata_before.len().cmp(&artifact.size_bytes) {
                std::cmp::Ordering::Less => return Err(VerifyError::ArtifactUndersize),
                std::cmp::Ordering::Greater => return Err(VerifyError::ArtifactOversize),
                std::cmp::Ordering::Equal => {}
            }

            let stamp_before = metadata_stamp(&metadata_before);
            let verified_object = verify_artifact_stream(artifact, &mut file)?;
            let metadata_after = regular_file_metadata(&file)?;
            if stamp_before != metadata_stamp(&metadata_after) {
                return Err(VerifyError::ArtifactChangedDuringVerification);
            }
            self.confirm_path_binding(&artifact.artifact_path, &canonical_before, identity)?;
            objects.push(verified_object);
        }

        Ok(VerifiedEvidenceObjects {
            objects,
            total_size_bytes,
        })
    }

    #[cfg(not(unix))]
    fn candidate_path(&self, artifact_path: &str) -> PathBuf {
        let mut candidate = self.canonical_root.clone();
        for component in artifact_path.split('/') {
            candidate.push(component);
        }
        candidate
    }

    #[cfg(unix)]
    fn open_artifact_file(&self, artifact_path: &str) -> Result<File, VerifyError> {
        open_unix_artifact_beneath(&self.root_handle, artifact_path)
    }

    #[cfg(not(unix))]
    fn open_artifact_file(&self, artifact_path: &str) -> Result<File, VerifyError> {
        open_file_no_follow(&self.candidate_path(artifact_path))
            .map_err(|_| VerifyError::ArtifactOpenFailed)
    }

    fn ensure_root_stable(&self) -> Result<(), VerifyError> {
        if file_identity(&self.root_handle)? != self.root_identity {
            return Err(VerifyError::ArtifactChangedDuringVerification);
        }
        let metadata = fs::symlink_metadata(&self.canonical_root)
            .map_err(|_| VerifyError::ArtifactChangedDuringVerification)?;
        reject_link_or_reparse(&metadata)?;
        if !metadata.is_dir() {
            return Err(VerifyError::ArtifactChangedDuringVerification);
        }
        let current = open_directory_no_follow(&self.canonical_root)
            .map_err(|_| VerifyError::ArtifactChangedDuringVerification)?;
        if file_identity(&current)? != self.root_identity {
            return Err(VerifyError::ArtifactChangedDuringVerification);
        }
        Ok(())
    }

    fn inspect_artifact_path(&self, artifact_path: &str) -> Result<PathBuf, VerifyError> {
        validate_artifact_path(artifact_path)?;
        let mut candidate = self.canonical_root.clone();
        let mut components = artifact_path.split('/').peekable();
        while let Some(component) = components.next() {
            candidate.push(component);
            let metadata =
                fs::symlink_metadata(&candidate).map_err(|_| VerifyError::ArtifactOpenFailed)?;
            reject_link_or_reparse(&metadata)?;
            if components.peek().is_some() {
                if !metadata.is_dir() {
                    return Err(VerifyError::ArtifactNotRegularFile);
                }
            } else if !metadata.is_file() {
                return Err(VerifyError::ArtifactNotRegularFile);
            }
        }

        let canonical =
            fs::canonicalize(&candidate).map_err(|_| VerifyError::ArtifactOpenFailed)?;
        if canonical.strip_prefix(&self.canonical_root).is_err() {
            return Err(VerifyError::ArtifactRootEscape);
        }
        Ok(canonical)
    }

    fn confirm_path_binding(
        &self,
        artifact_path: &str,
        expected_canonical: &Path,
        expected_identity: FileIdentity,
    ) -> Result<(), VerifyError> {
        self.ensure_root_stable()?;
        let canonical = self.inspect_artifact_path(artifact_path)?;
        if canonical != expected_canonical {
            return Err(VerifyError::ArtifactChangedDuringVerification);
        }
        let current = self.open_artifact_file(artifact_path)?;
        regular_file_metadata(&current)?;
        if file_identity(&current)? != expected_identity {
            return Err(VerifyError::ArtifactChangedDuringVerification);
        }
        Ok(())
    }
}

fn verify_artifact_stream<R: Read>(
    artifact: &EvidenceArtifact,
    reader: &mut R,
) -> Result<VerifiedEvidenceObject, VerifyError> {
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; STREAM_BUFFER_BYTES];
    {
        let mut bounded = reader.by_ref().take(artifact.size_bytes);
        while bounded.limit() != 0 {
            let requested = if bounded.limit() < buffer.len() as u64 {
                bounded.limit() as usize
            } else {
                buffer.len()
            };
            let read = read_retry(&mut bounded, &mut buffer[..requested])?;
            if read == 0 {
                return Err(VerifyError::ArtifactUndersize);
            }
            hasher.update(&buffer[..read]);
        }
    }

    let mut extra = [0_u8; 1];
    if read_retry(reader, &mut extra)? != 0 {
        return Err(VerifyError::ArtifactOversize);
    }

    let sha256 = hex::encode(hasher.finalize());
    if sha256
        .as_bytes()
        .ct_eq(artifact.sha256.as_bytes())
        .unwrap_u8()
        != 1
    {
        return Err(VerifyError::ArtifactDigestMismatch);
    }

    Ok(VerifiedEvidenceObject {
        artifact_path: artifact.artifact_path.clone(),
        size_bytes: artifact.size_bytes,
        sha256,
    })
}

fn read_retry(reader: &mut impl Read, buffer: &mut [u8]) -> Result<usize, VerifyError> {
    loop {
        match reader.read(buffer) {
            Ok(read) => return Ok(read),
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(_) => return Err(VerifyError::ArtifactReadFailed),
        }
    }
}

pub struct AllowFreshReplayGuard;

impl ReplayGuard for AllowFreshReplayGuard {
    fn inspect(&self, _input: &ReplayGuardInput) -> Result<ReplayDecision, VerifyError> {
        Ok(ReplayDecision::Fresh)
    }
}

pub fn canonical_json(input: &str) -> Result<String, VerifyError> {
    reject_duplicate_object_keys(input)?;
    let value: Value =
        serde_json::from_str(input).map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
    String::from_utf8(canonical_json_bytes(&value)?)
        .map_err(|error| VerifyError::InvalidJson(error.to_string()))
}

pub fn canonical_json_bytes(value: &Value) -> Result<Vec<u8>, VerifyError> {
    let mut output = String::new();
    write_canonical_json(value, &mut output)?;
    Ok(output.into_bytes())
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

pub fn is_lower_hex_sha256(candidate: &str) -> bool {
    candidate.len() == SHA256_HEX_LENGTH
        && candidate
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_key_id(key_id: &str) -> Result<(), VerifyError> {
    if !(8..=128).contains(&key_id.len())
        || !key_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.' | b':'))
    {
        return Err(VerifyError::InvalidField("key_id"));
    }
    Ok(())
}

fn validate_policy(
    envelope: &AuthenticatedEnvelope,
    policy: &VerificationPolicy,
) -> Result<(), VerifyError> {
    if policy.now_unix_ms < envelope.issued_at_unix_ms {
        return Err(VerifyError::NotYetValid);
    }
    if policy.now_unix_ms >= envelope.expires_at_unix_ms {
        return Err(VerifyError::Expired);
    }
    if envelope.expires_at_unix_ms - envelope.issued_at_unix_ms > policy.max_lifetime_ms {
        return Err(VerifyError::LifetimeExceeded);
    }
    if let Some(expected) = policy.expected_tenant_digest.as_deref() {
        if expected
            .as_bytes()
            .ct_eq(envelope.tenant_digest.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(VerifyError::ScopeMismatch("tenant_digest"));
        }
    }
    if let Some(expected) = policy.expected_project_digest.as_deref() {
        if expected
            .as_bytes()
            .ct_eq(envelope.project_digest.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(VerifyError::ScopeMismatch("project_digest"));
        }
    }
    Ok(())
}

fn validate_bundle_policy(
    bundle: &AuthenticatedEvidenceBundle,
    policy: &VerificationPolicy,
) -> Result<(), VerifyError> {
    if policy.now_unix_ms < bundle.issued_at_unix_ms {
        return Err(VerifyError::NotYetValid);
    }
    if policy.now_unix_ms >= bundle.expires_at_unix_ms {
        return Err(VerifyError::Expired);
    }
    if bundle.expires_at_unix_ms - bundle.issued_at_unix_ms > policy.max_lifetime_ms {
        return Err(VerifyError::LifetimeExceeded);
    }
    if let Some(expected) = policy.expected_tenant_digest.as_deref() {
        if expected
            .as_bytes()
            .ct_eq(bundle.tenant_digest.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(VerifyError::ScopeMismatch("tenant_digest"));
        }
    }
    if let Some(expected) = policy.expected_project_digest.as_deref() {
        if expected
            .as_bytes()
            .ct_eq(bundle.project_digest.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(VerifyError::ScopeMismatch("project_digest"));
        }
    }
    if let Some(expected) = policy.expected_bundle_id_digest.as_deref() {
        if expected
            .as_bytes()
            .ct_eq(bundle.bundle_id_digest.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(VerifyError::ScopeMismatch("bundle_id_digest"));
        }
    }
    Ok(())
}

fn validate_artifact_path(path: &str) -> Result<(), VerifyError> {
    if path.is_empty()
        || path.len() > MAX_ARTIFACT_PATH_BYTES
        || path.starts_with('/')
        || path.contains('\\')
        || path.split('/').any(|component| {
            component.is_empty()
                || matches!(component, "." | "..")
                || component.ends_with('.')
                || !component
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
        })
    {
        return Err(VerifyError::UnsafeArtifactPath);
    }
    Ok(())
}

fn validate_media_type(media_type: &str) -> Result<(), VerifyError> {
    if media_type.is_empty()
        || media_type.len() > 255
        || !media_type.contains('/')
        || media_type
            .bytes()
            .any(|byte| byte.is_ascii_control() || byte.is_ascii_whitespace() || !byte.is_ascii())
    {
        return Err(VerifyError::InvalidField("evidence[].media_type"));
    }
    Ok(())
}

fn reject_link_or_reparse(metadata: &Metadata) -> Result<(), VerifyError> {
    if metadata.file_type().is_symlink() || metadata_is_reparse(metadata) {
        return Err(VerifyError::ArtifactSymlinkRejected);
    }
    Ok(())
}

fn regular_file_metadata(file: &File) -> Result<Metadata, VerifyError> {
    let metadata = file
        .metadata()
        .map_err(|_| VerifyError::ArtifactIdentityUnavailable)?;
    reject_link_or_reparse(&metadata)?;
    if !metadata.is_file() {
        return Err(VerifyError::ArtifactNotRegularFile);
    }
    Ok(metadata)
}

#[cfg(unix)]
fn open_unix_artifact_beneath(
    root_handle: &File,
    artifact_path: &str,
) -> Result<File, VerifyError> {
    open_unix_artifact_beneath_with_hook(root_handle, artifact_path, |_| {})
}

#[cfg(unix)]
fn open_unix_artifact_beneath_with_hook<F>(
    root_handle: &File,
    artifact_path: &str,
    mut after_directory_opened: F,
) -> Result<File, VerifyError>
where
    F: FnMut(usize),
{
    validate_artifact_path(artifact_path)?;
    let mut opened_directory: Option<File> = None;
    let mut components = artifact_path.split('/').enumerate().peekable();

    while let Some((index, component)) = components.next() {
        let is_leaf = components.peek().is_none();
        let parent = opened_directory.as_ref().unwrap_or(root_handle);
        let component = CString::new(component).map_err(|_| VerifyError::UnsafeArtifactPath)?;
        let flags = if is_leaf {
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK
        } else {
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_DIRECTORY
        };

        // SAFETY: `parent` remains alive for the call, `component` is NUL-terminated,
        // and a successful descriptor is immediately transferred into `File`.
        let descriptor = unsafe { libc::openat(parent.as_raw_fd(), component.as_ptr(), flags) };
        if descriptor < 0 {
            return Err(map_unix_open_error(io::Error::last_os_error()));
        }
        // SAFETY: `openat` returned a new owned descriptor that has not been wrapped.
        let opened = unsafe { File::from_raw_fd(descriptor) };
        let metadata = opened
            .metadata()
            .map_err(|_| VerifyError::ArtifactIdentityUnavailable)?;
        reject_link_or_reparse(&metadata)?;

        if is_leaf {
            if !metadata.is_file() {
                return Err(VerifyError::ArtifactNotRegularFile);
            }
            return Ok(opened);
        }
        if !metadata.is_dir() {
            return Err(VerifyError::ArtifactNotRegularFile);
        }
        opened_directory = Some(opened);
        after_directory_opened(index);
    }

    Err(VerifyError::UnsafeArtifactPath)
}

#[cfg(unix)]
fn map_unix_open_error(error: io::Error) -> VerifyError {
    match error.raw_os_error() {
        Some(libc::ELOOP) => VerifyError::ArtifactSymlinkRejected,
        Some(libc::ENOTDIR) => VerifyError::ArtifactNotRegularFile,
        _ => VerifyError::ArtifactOpenFailed,
    }
}

#[cfg(windows)]
fn metadata_is_reparse(metadata: &Metadata) -> bool {
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn metadata_is_reparse(_metadata: &Metadata) -> bool {
    false
}

#[cfg(windows)]
fn open_file_no_follow(path: &Path) -> io::Result<File> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
}

#[cfg(not(any(unix, windows)))]
fn open_file_no_follow(path: &Path) -> io::Result<File> {
    File::open(path)
}

#[cfg(unix)]
fn open_directory_no_follow(path: &Path) -> io::Result<File> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
        .open(path)
}

#[cfg(windows)]
fn open_directory_no_follow(path: &Path) -> io::Result<File> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
}

#[cfg(not(any(unix, windows)))]
fn open_directory_no_follow(path: &Path) -> io::Result<File> {
    File::open(path)
}

#[cfg(unix)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct FileIdentity {
    device: u64,
    inode: u64,
}

#[cfg(unix)]
fn file_identity(file: &File) -> Result<FileIdentity, VerifyError> {
    let metadata = file
        .metadata()
        .map_err(|_| VerifyError::ArtifactIdentityUnavailable)?;
    Ok(FileIdentity {
        device: metadata.dev(),
        inode: metadata.ino(),
    })
}

#[cfg(windows)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct FileIdentity {
    volume: u32,
    index: u64,
}

#[cfg(windows)]
fn file_identity(file: &File) -> Result<FileIdentity, VerifyError> {
    let information = windows_file_information(file)?;
    Ok(FileIdentity {
        volume: information.dwVolumeSerialNumber,
        index: u64::from(information.nFileIndexHigh) << 32 | u64::from(information.nFileIndexLow),
    })
}

#[cfg(windows)]
fn windows_file_information(file: &File) -> Result<BY_HANDLE_FILE_INFORMATION, VerifyError> {
    let mut information = std::mem::MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    // SAFETY: `file` owns a valid handle for the duration of the call and the
    // output points to writable, correctly sized storage.
    let succeeded = unsafe {
        GetFileInformationByHandle(file.as_raw_handle() as HANDLE, information.as_mut_ptr())
    };
    if succeeded == 0 {
        return Err(VerifyError::ArtifactIdentityUnavailable);
    }
    // SAFETY: a successful `GetFileInformationByHandle` initializes the full
    // `BY_HANDLE_FILE_INFORMATION` value.
    Ok(unsafe { information.assume_init() })
}

#[cfg(not(any(unix, windows)))]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct FileIdentity;

#[cfg(not(any(unix, windows)))]
fn file_identity(_file: &File) -> Result<FileIdentity, VerifyError> {
    Err(VerifyError::ArtifactIdentityUnavailable)
}

#[cfg(unix)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct MetadataStamp {
    length: u64,
    device: u64,
    inode: u64,
    mode: u32,
    owner: u32,
    group: u32,
    link_count: u64,
    modified_seconds: i64,
    modified_nanoseconds: i64,
    changed_seconds: i64,
    changed_nanoseconds: i64,
}

#[cfg(unix)]
fn metadata_stamp(metadata: &Metadata) -> MetadataStamp {
    MetadataStamp {
        length: metadata.len(),
        device: metadata.dev(),
        inode: metadata.ino(),
        mode: metadata.mode(),
        owner: metadata.uid(),
        group: metadata.gid(),
        link_count: metadata.nlink(),
        modified_seconds: metadata.mtime(),
        modified_nanoseconds: metadata.mtime_nsec(),
        changed_seconds: metadata.ctime(),
        changed_nanoseconds: metadata.ctime_nsec(),
    }
}

#[cfg(windows)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct MetadataStamp {
    length: u64,
    file_attributes: u32,
    creation_time: u64,
    last_write_time: u64,
}

#[cfg(windows)]
fn metadata_stamp(metadata: &Metadata) -> MetadataStamp {
    MetadataStamp {
        length: metadata.file_size(),
        file_attributes: metadata.file_attributes(),
        creation_time: metadata.creation_time(),
        last_write_time: metadata.last_write_time(),
    }
}

#[cfg(not(any(unix, windows)))]
#[derive(Debug, Clone, PartialEq, Eq)]
struct MetadataStamp {
    length: u64,
    modified: Option<std::time::SystemTime>,
    readonly: bool,
}

#[cfg(not(any(unix, windows)))]
fn metadata_stamp(metadata: &Metadata) -> MetadataStamp {
    MetadataStamp {
        length: metadata.len(),
        modified: metadata.modified().ok(),
        readonly: metadata.permissions().readonly(),
    }
}

fn write_canonical_json(value: &Value, output: &mut String) -> Result<(), VerifyError> {
    match value {
        Value::Null => output.push_str("null"),
        Value::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
        Value::Number(number) => {
            if let Some(value) = number.as_i64() {
                write!(output, "{value}").expect("writing to String cannot fail");
            } else if let Some(value) = number.as_u64() {
                write!(output, "{value}").expect("writing to String cannot fail");
            } else {
                return Err(VerifyError::InvalidSchema(
                    "floating-point numbers are forbidden in canonical security envelopes",
                ));
            }
        }
        Value::String(value) => output.push_str(
            &serde_json::to_string(value)
                .map_err(|error| VerifyError::InvalidJson(error.to_string()))?,
        ),
        Value::Array(values) => {
            output.push('[');
            for (index, value) in values.iter().enumerate() {
                if index != 0 {
                    output.push(',');
                }
                write_canonical_json(value, output)?;
            }
            output.push(']');
        }
        Value::Object(values) => {
            output.push('{');
            let sorted: BTreeMap<&str, &Value> = values
                .iter()
                .map(|(key, value)| (key.as_str(), value))
                .collect();
            for (index, (key, value)) in sorted.into_iter().enumerate() {
                if index != 0 {
                    output.push(',');
                }
                output.push_str(
                    &serde_json::to_string(key)
                        .map_err(|error| VerifyError::InvalidJson(error.to_string()))?,
                );
                output.push(':');
                write_canonical_json(value, output)?;
            }
            output.push('}');
        }
    }
    Ok(())
}

fn reject_duplicate_object_keys(input: &str) -> Result<(), VerifyError> {
    let mut deserializer = serde_json::Deserializer::from_str(input);
    DuplicateRejectingValue::deserialize(&mut deserializer)
        .map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
    deserializer
        .end()
        .map_err(|error| VerifyError::InvalidJson(error.to_string()))
}

struct DuplicateRejectingValue;

impl<'de> Deserialize<'de> for DuplicateRejectingValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(DuplicateRejectingVisitor)
    }
}

struct DuplicateRejectingVisitor;

impl<'de> serde::de::Visitor<'de> for DuplicateRejectingVisitor {
    type Value = DuplicateRejectingValue;

    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("a JSON value without duplicate object keys")
    }

    fn visit_bool<E>(self, _value: bool) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_i64<E>(self, _value: i64) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_u64<E>(self, _value: u64) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_f64<E>(self, _value: f64) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_str<E>(self, _value: &str) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_string<E>(self, _value: String) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(DuplicateRejectingValue)
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        DuplicateRejectingValue::deserialize(deserializer)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: serde::de::SeqAccess<'de>,
    {
        while sequence
            .next_element::<DuplicateRejectingValue>()?
            .is_some()
        {}
        Ok(DuplicateRejectingValue)
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: serde::de::MapAccess<'de>,
    {
        let mut keys = std::collections::HashSet::new();
        while let Some(key) = map.next_key::<String>()? {
            if !keys.insert(key.clone()) {
                return Err(serde::de::Error::custom(format!(
                    "duplicate JSON object key: {key}"
                )));
            }
            map.next_value::<DuplicateRejectingValue>()?;
        }
        Ok(DuplicateRejectingValue)
    }
}

pub fn object_without_signature(
    envelope: &AuthenticatedEnvelope,
) -> Result<Map<String, Value>, VerifyError> {
    let payload = serde_json::to_value(SigningPayload {
        schema_version: &envelope.schema_version,
        algorithm: &envelope.algorithm,
        key_id: &envelope.key_id,
        purpose: envelope.purpose,
        tenant_digest: &envelope.tenant_digest,
        project_digest: &envelope.project_digest,
        principal_digest: &envelope.principal_digest,
        event_id_digest: &envelope.event_id_digest,
        idempotency_key_digest: &envelope.idempotency_key_digest,
        request_digest: &envelope.request_digest,
        nonce_digest: &envelope.nonce_digest,
        payload_digest: &envelope.payload_digest,
        evidence_digest: &envelope.evidence_digest,
        issued_at_unix_ms: envelope.issued_at_unix_ms,
        expires_at_unix_ms: envelope.expires_at_unix_ms,
    })
    .map_err(|error| VerifyError::InvalidJson(error.to_string()))?;
    payload
        .as_object()
        .cloned()
        .ok_or(VerifyError::InvalidSchema(
            "signing payload must be an object",
        ))
}

#[cfg(all(test, unix))]
mod unix_path_security_tests {
    use super::*;
    use std::os::unix::ffi::OsStrExt;
    use std::os::unix::fs::{symlink, PermissionsExt};

    #[test]
    fn descriptor_walk_stays_on_opened_directory_and_rebinding_fails_closed() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("root");
        let nested = root.join("nested");
        let detached = root.join("detached");
        let outside = temp.path().join("outside");
        fs::create_dir_all(&nested).unwrap();
        fs::create_dir_all(&outside).unwrap();
        fs::write(nested.join("object.bin"), b"inside-root").unwrap();
        fs::write(outside.join("object.bin"), b"outside-root").unwrap();

        let anchored = LocalEvidenceObjectRoot::new(&root).unwrap();
        let canonical_before = anchored.inspect_artifact_path("nested/object.bin").unwrap();
        let mut swapped = false;
        let mut opened = open_unix_artifact_beneath_with_hook(
            &anchored.root_handle,
            "nested/object.bin",
            |index| {
                if index == 0 {
                    fs::rename(&nested, &detached).unwrap();
                    symlink(&outside, &nested).unwrap();
                    swapped = true;
                }
            },
        )
        .unwrap();
        assert!(swapped);

        let opened_identity = file_identity(&opened).unwrap();
        let mut bytes = Vec::new();
        opened.read_to_end(&mut bytes).unwrap();
        assert_eq!(bytes, b"inside-root");
        assert_eq!(
            anchored
                .confirm_path_binding("nested/object.bin", &canonical_before, opened_identity,)
                .unwrap_err(),
            VerifyError::ArtifactSymlinkRejected
        );
    }

    #[test]
    fn descriptor_walk_rejects_fifo_without_waiting_for_a_writer() {
        let temp = tempfile::tempdir().unwrap();
        let fifo = temp.path().join("stream.pipe");
        let fifo_path = CString::new(fifo.as_os_str().as_bytes()).unwrap();
        // SAFETY: `fifo_path` is a valid NUL-terminated path and no pointer is retained.
        assert_eq!(unsafe { libc::mkfifo(fifo_path.as_ptr(), 0o600) }, 0);
        let root = open_directory_no_follow(temp.path()).unwrap();

        assert_eq!(
            open_unix_artifact_beneath(&root, "stream.pipe").unwrap_err(),
            VerifyError::ArtifactNotRegularFile
        );
    }

    #[test]
    fn metadata_stamp_covers_permission_and_link_count_changes() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("object.bin");
        fs::write(&path, b"stable bytes").unwrap();
        let file = File::open(&path).unwrap();
        let before = metadata_stamp(&file.metadata().unwrap());

        let changed_mode = before.mode ^ 0o100;
        fs::set_permissions(&path, fs::Permissions::from_mode(changed_mode)).unwrap();
        let after_permissions = metadata_stamp(&file.metadata().unwrap());
        assert_ne!(before.mode, after_permissions.mode);
        assert_ne!(before, after_permissions);

        fs::hard_link(&path, temp.path().join("object-alias.bin")).unwrap();
        let after_link = metadata_stamp(&file.metadata().unwrap());
        assert_eq!(after_link.link_count, after_permissions.link_count + 1);
        assert_ne!(after_permissions, after_link);
    }
}
