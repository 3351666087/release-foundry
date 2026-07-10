use std::collections::BTreeMap;
use std::fmt::Write;

use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

pub const AUTHENTICATED_ENVELOPE_SCHEMA_VERSION: &str =
    "ashr.identity_verification.authenticated_envelope.v1";
pub const AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION: &str =
    "ashr.a1.authenticated_evidence_bundle.v2";
pub const HMAC_SHA256_ALGORITHM: &str = "hmac-sha256";
pub const SHA256_ALGORITHM: &str = "sha256";
pub const MIN_HMAC_KEY_BYTES: usize = 32;
pub const SHA256_HEX_LENGTH: usize = 64;
pub const MAX_EVIDENCE_ITEMS: usize = 10_000;
pub const MAX_ARTIFACT_PATH_BYTES: usize = 1_024;

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
pub struct VerifiedEvidenceBundle {
    pub bundle: AuthenticatedEvidenceBundle,
    pub canonical_signing_bytes: Vec<u8>,
    pub authenticated_bundle_digest: String,
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
}

impl VerificationPolicy {
    pub fn at(now_unix_ms: u64) -> Self {
        Self {
            now_unix_ms,
            max_lifetime_ms: 15 * 60 * 1000,
            expected_tenant_digest: None,
            expected_project_digest: None,
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

        Ok(VerifiedEvidenceBundle {
            bundle: self.clone(),
            authenticated_bundle_digest: sha256_hex(&canonical_signing_bytes),
            canonical_signing_bytes,
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
