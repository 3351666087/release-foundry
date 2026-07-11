use std::cell::RefCell;
use std::fs;
use std::process::Command;

use ashr_runtime_verify::{
    canonical_json, sha256_hex, AuthenticatedEnvelope, HmacSha256Verifier, ReplayDecision,
    ReplayGuard, ReplayGuardInput, VerificationPolicy, VerifyError,
};
use serde::Deserialize;

const VECTOR_PATH: &str = "test-vectors/identity_verification_hmac_sha256_v1.json";

#[derive(Deserialize)]
struct Vector {
    key_utf8: String,
    now_unix_ms: u64,
    canonical_signing_json: String,
    canonical_signing_sha256: String,
    envelope: AuthenticatedEnvelope,
}

fn vector() -> Vector {
    serde_json::from_str(&fs::read_to_string(VECTOR_PATH).unwrap()).unwrap()
}

struct RecordingGuard {
    decision: ReplayDecision,
    seen: RefCell<Vec<ReplayGuardInput>>,
}

impl ReplayGuard for RecordingGuard {
    fn inspect(&self, input: &ReplayGuardInput) -> Result<ReplayDecision, VerifyError> {
        self.seen.borrow_mut().push(input.clone());
        Ok(self.decision)
    }
}

#[test]
fn cross_language_vector_verifies_and_exposes_guard_inputs() {
    let vector = vector();
    assert_eq!(
        String::from_utf8(vector.envelope.canonical_signing_bytes().unwrap()).unwrap(),
        vector.canonical_signing_json
    );
    let verifier =
        HmacSha256Verifier::new(&vector.envelope.key_id, vector.key_utf8.as_bytes()).unwrap();
    let guard = RecordingGuard {
        decision: ReplayDecision::Fresh,
        seen: RefCell::new(Vec::new()),
    };
    let verified = vector
        .envelope
        .verify(
            &verifier,
            &guard,
            &VerificationPolicy::at(vector.now_unix_ms),
        )
        .unwrap();
    assert_eq!(guard.seen.borrow().len(), 1);
    assert_eq!(
        verified.replay_guard.request_digest,
        vector.envelope.request_digest
    );
    assert_eq!(verified.envelope_digest, vector.canonical_signing_sha256);
    assert_eq!(
        verified.envelope_digest,
        sha256_hex(vector.canonical_signing_json.as_bytes())
    );
}

#[test]
fn tampering_fails_before_replay_guard() {
    let mut vector = vector();
    vector.envelope.payload_digest = "f".repeat(64);
    let verifier =
        HmacSha256Verifier::new(&vector.envelope.key_id, vector.key_utf8.as_bytes()).unwrap();
    let guard = RecordingGuard {
        decision: ReplayDecision::Fresh,
        seen: RefCell::new(Vec::new()),
    };
    assert_eq!(
        vector
            .envelope
            .verify(
                &verifier,
                &guard,
                &VerificationPolicy::at(vector.now_unix_ms)
            )
            .unwrap_err(),
        VerifyError::SignatureMismatch
    );
    assert!(guard.seen.borrow().is_empty());
}

#[test]
fn replay_conflict_and_nonce_replay_fail_closed() {
    let vector = vector();
    let verifier =
        HmacSha256Verifier::new(&vector.envelope.key_id, vector.key_utf8.as_bytes()).unwrap();
    for (decision, expected) in [
        (ReplayDecision::Conflict, VerifyError::ReplayConflict),
        (ReplayDecision::ReplayedNonce, VerifyError::ReplayedNonce),
    ] {
        let guard = RecordingGuard {
            decision,
            seen: RefCell::new(Vec::new()),
        };
        assert_eq!(
            vector
                .envelope
                .verify(
                    &verifier,
                    &guard,
                    &VerificationPolicy::at(vector.now_unix_ms)
                )
                .unwrap_err(),
            expected
        );
    }
}

#[test]
fn idempotent_same_request_replay_is_explicitly_accepted() {
    let vector = vector();
    let verifier =
        HmacSha256Verifier::new(&vector.envelope.key_id, vector.key_utf8.as_bytes()).unwrap();
    let guard = RecordingGuard {
        decision: ReplayDecision::IdempotentReplay,
        seen: RefCell::new(Vec::new()),
    };
    vector
        .envelope
        .verify(
            &verifier,
            &guard,
            &VerificationPolicy::at(vector.now_unix_ms),
        )
        .unwrap();
}

#[test]
fn rejects_expired_wrong_scope_and_excessive_lifetime() {
    let vector = vector();
    let verifier =
        HmacSha256Verifier::new(&vector.envelope.key_id, vector.key_utf8.as_bytes()).unwrap();
    let guard = RecordingGuard {
        decision: ReplayDecision::Fresh,
        seen: RefCell::new(Vec::new()),
    };
    assert_eq!(
        vector
            .envelope
            .verify(
                &verifier,
                &guard,
                &VerificationPolicy::at(vector.envelope.expires_at_unix_ms)
            )
            .unwrap_err(),
        VerifyError::Expired
    );
    let mut wrong_scope = VerificationPolicy::at(vector.now_unix_ms);
    wrong_scope.expected_tenant_digest = Some("f".repeat(64));
    assert_eq!(
        vector
            .envelope
            .verify(&verifier, &guard, &wrong_scope)
            .unwrap_err(),
        VerifyError::ScopeMismatch("tenant_digest")
    );
    let mut short_lifetime = VerificationPolicy::at(vector.now_unix_ms);
    short_lifetime.max_lifetime_ms = 1;
    assert_eq!(
        vector
            .envelope
            .verify(&verifier, &guard, &short_lifetime)
            .unwrap_err(),
        VerifyError::LifetimeExceeded
    );
}

#[test]
fn strict_schema_rejects_unknown_raw_or_duplicate_fields() {
    let vector = vector();
    let raw = serde_json::to_string(&vector.envelope).unwrap();
    let with_raw_otp = raw.replacen('{', r#"{"otp":"123456","#, 1);
    assert!(AuthenticatedEnvelope::parse_strict(&with_raw_otp)
        .unwrap_err()
        .to_string()
        .contains("unknown field"));

    let duplicate = raw.replacen(
        r#""schema_version":"#,
        r#""schema_version":"ashr.identity_verification.authenticated_envelope.v1","schema_version":"#,
        1,
    );
    assert!(AuthenticatedEnvelope::parse_strict(&duplicate)
        .unwrap_err()
        .to_string()
        .contains("duplicate JSON object key"));
}

#[test]
fn canonical_json_sorts_recursively_and_rejects_floats() {
    assert_eq!(
        canonical_json(r#"{"z":{"b":2,"a":1},"a":["x",true,null]}"#).unwrap(),
        r#"{"a":["x",true,null],"z":{"a":1,"b":2}}"#
    );
    assert!(canonical_json(r#"{"unsafe":1.25}"#)
        .unwrap_err()
        .to_string()
        .contains("floating-point"));
}

#[test]
fn key_id_and_signature_comparisons_fail_closed() {
    let vector = vector();
    let wrong_key_id =
        HmacSha256Verifier::new("round52:key:other", vector.key_utf8.as_bytes()).unwrap();
    let guard = RecordingGuard {
        decision: ReplayDecision::Fresh,
        seen: RefCell::new(Vec::new()),
    };
    assert_eq!(
        vector
            .envelope
            .verify(
                &wrong_key_id,
                &guard,
                &VerificationPolicy::at(vector.now_unix_ms)
            )
            .unwrap_err(),
        VerifyError::UnknownKey
    );
}

#[test]
fn cli_reads_key_only_from_named_environment_variable() {
    let vector = vector();
    let temp = tempfile::NamedTempFile::new().unwrap();
    fs::write(temp.path(), serde_json::to_vec(&vector.envelope).unwrap()).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_ashr-runtime-verify"))
        .args([
            "verify-envelope",
            temp.path().to_str().unwrap(),
            "--key-env",
            "ASHR_TEST_VECTOR_HMAC_KEY",
            "--now-ms",
            &vector.now_unix_ms.to_string(),
        ])
        .env("ASHR_TEST_VECTOR_HMAC_KEY", &vector.key_utf8)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["status"], "ok");
    assert_eq!(
        result["idempotency_key_digest"],
        vector.envelope.idempotency_key_digest
    );
    assert!(!String::from_utf8_lossy(&output.stdout).contains(&vector.key_utf8));
}

#[test]
fn legacy_commands_remain_available() {
    let temp = tempfile::NamedTempFile::new().unwrap();
    fs::write(
        temp.path(),
        r#"{"kind":"local_cloud_state","runs":[{"status":"queued"}]}"#,
    )
    .unwrap();
    for command in ["verify", "replay-plan"] {
        assert!(Command::new(env!("CARGO_BIN_EXE_ashr-runtime-verify"))
            .args([command, temp.path().to_str().unwrap()])
            .status()
            .unwrap()
            .success());
    }
}
