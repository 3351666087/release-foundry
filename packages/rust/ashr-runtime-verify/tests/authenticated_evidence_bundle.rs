use std::fs;
use std::process::Command;

use ashr_runtime_verify::{
    sha256_hex, AuthenticatedEvidenceBundle, EvidenceArtifact, HmacSha256Verifier,
    VerificationPolicy, VerifyError, AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION,
    HMAC_SHA256_ALGORITHM,
};

const KEY_ID: &str = "round52:evidence:key:v2";
const KEY: &[u8] = b"round52-evidence-test-key-material-0000000001";
const NOW_UNIX_MS: u64 = 1_750_000_000_000;

fn digest(label: &str) -> String {
    sha256_hex(label.as_bytes())
}

fn unsigned_bundle() -> AuthenticatedEvidenceBundle {
    AuthenticatedEvidenceBundle {
        schema_version: AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION.to_string(),
        algorithm: HMAC_SHA256_ALGORITHM.to_string(),
        key_id: KEY_ID.to_string(),
        bundle_id_digest: digest("bundle-001"),
        tenant_digest: digest("tenant-001"),
        project_digest: digest("project-001"),
        evidence: vec![
            EvidenceArtifact {
                artifact_path: "reports/run-001.json".to_string(),
                sha256: digest("report bytes"),
                size_bytes: 12_345,
                media_type: "application/json".to_string(),
            },
            EvidenceArtifact {
                artifact_path: "traces/run-001.ndjson".to_string(),
                sha256: digest("trace bytes"),
                size_bytes: 67_890,
                media_type: "application/x-ndjson".to_string(),
            },
        ],
        evidence_digest: String::new(),
        issued_at_unix_ms: NOW_UNIX_MS - 1_000,
        expires_at_unix_ms: NOW_UNIX_MS + 60_000,
        signature: String::new(),
    }
}

fn signed_bundle() -> AuthenticatedEvidenceBundle {
    let mut bundle = unsigned_bundle();
    bundle.sign_hmac_sha256(KEY).unwrap();
    bundle
}

fn verifier() -> HmacSha256Verifier<'static> {
    HmacSha256Verifier::new(KEY_ID, KEY).unwrap()
}

#[test]
fn authenticates_manifest_scope_window_and_evidence() {
    let bundle = signed_bundle();
    let mut policy = VerificationPolicy::at(NOW_UNIX_MS);
    policy.expected_tenant_digest = Some(bundle.tenant_digest.clone());
    policy.expected_project_digest = Some(bundle.project_digest.clone());
    policy.expected_bundle_id_digest = Some(bundle.bundle_id_digest.clone());

    let verified = bundle.verify(&verifier(), &policy).unwrap();

    assert_eq!(verified.bundle.evidence.len(), 2);
    assert_eq!(
        verified.bundle.evidence_digest,
        sha256_hex(&bundle.canonical_evidence_bytes().unwrap())
    );
    assert_eq!(
        verified.authenticated_bundle_digest,
        sha256_hex(&verified.canonical_signing_bytes)
    );
}

#[test]
fn rejects_attacker_rewriting_evidence_and_self_hash() {
    let mut bundle = signed_bundle();
    bundle.evidence[0].sha256 = digest("attacker replacement");
    bundle.refresh_evidence_digest().unwrap();

    assert_eq!(
        bundle
            .verify(&verifier(), &VerificationPolicy::at(NOW_UNIX_MS))
            .unwrap_err(),
        VerifyError::SignatureMismatch
    );
}

#[test]
fn rejects_digest_tamper_before_signature_and_wrong_scope() {
    let mut bundle = signed_bundle();
    bundle.evidence[0].size_bytes += 1;
    assert_eq!(
        bundle
            .verify(&verifier(), &VerificationPolicy::at(NOW_UNIX_MS))
            .unwrap_err(),
        VerifyError::EvidenceDigestMismatch
    );

    let bundle = signed_bundle();
    let mut wrong_scope = VerificationPolicy::at(NOW_UNIX_MS);
    wrong_scope.expected_tenant_digest = Some(digest("other tenant"));
    assert_eq!(
        bundle.verify(&verifier(), &wrong_scope).unwrap_err(),
        VerifyError::ScopeMismatch("tenant_digest")
    );

    let mut wrong_run = VerificationPolicy::at(NOW_UNIX_MS);
    wrong_run.expected_bundle_id_digest = Some(digest("other run"));
    assert_eq!(
        bundle.verify(&verifier(), &wrong_run).unwrap_err(),
        VerifyError::ScopeMismatch("bundle_id_digest")
    );
}

#[test]
fn rejects_path_escape_and_duplicate_extraction_targets() {
    for unsafe_path in [
        "../secret",
        "reports/../secret",
        "/etc/passwd",
        r"C:\Windows\system.ini",
        "reports/file.json:stream",
        "reports//run.json",
        "./run.json",
        "reports/run.json.",
        "reports/run report.json",
        "reports/\u{212b}.json",
    ] {
        let mut bundle = unsigned_bundle();
        bundle.evidence[0].artifact_path = unsafe_path.to_string();
        assert_eq!(
            bundle.sign_hmac_sha256(KEY).unwrap_err(),
            VerifyError::UnsafeArtifactPath,
            "{unsafe_path}"
        );
    }

    let mut duplicate = unsigned_bundle();
    duplicate.evidence[1].artifact_path = duplicate.evidence[0].artifact_path.clone();
    assert_eq!(
        duplicate.sign_hmac_sha256(KEY).unwrap_err(),
        VerifyError::DuplicateArtifactPath
    );
}

#[test]
fn strict_parser_rejects_unknown_and_duplicate_security_fields() {
    let bundle = signed_bundle();
    let raw = serde_json::to_string(&bundle).unwrap();
    let unknown = raw.replacen('{', r#"{"archive_root":"C:/unsafe","#, 1);
    assert!(AuthenticatedEvidenceBundle::parse_strict(&unknown)
        .unwrap_err()
        .to_string()
        .contains("unknown field"));

    let duplicate = raw.replacen(
        r#""schema_version":"#,
        &format!(
            r#""schema_version":"{AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION}","schema_version":"#
        ),
        1,
    );
    assert!(AuthenticatedEvidenceBundle::parse_strict(&duplicate)
        .unwrap_err()
        .to_string()
        .contains("duplicate JSON object key"));
}

#[test]
fn cli_verifies_signed_bundle_without_exposing_key() {
    let bundle = signed_bundle();
    let temp = tempfile::NamedTempFile::new().unwrap();
    fs::write(temp.path(), serde_json::to_vec(&bundle).unwrap()).unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_ashr-runtime-verify"))
        .args([
            "verify-signed-bundle",
            temp.path().to_str().unwrap(),
            "--key-env",
            "ASHR_TEST_BUNDLE_HMAC_KEY",
            "--now-ms",
            &NOW_UNIX_MS.to_string(),
        ])
        .env(
            "ASHR_TEST_BUNDLE_HMAC_KEY",
            std::str::from_utf8(KEY).unwrap(),
        )
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["status"], "ok");
    assert_eq!(result["verification_level"], "manifest_authenticated");
    assert_eq!(result["manifest_authenticated"], true);
    assert_eq!(result["object_verification_performed"], false);
    assert_eq!(result["objects_verified"], 0);
    assert_eq!(result["evidence_items"], 2);
    assert!(!String::from_utf8_lossy(&output.stdout).contains(std::str::from_utf8(KEY).unwrap()));
}
