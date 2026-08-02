from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CRATE = ROOT / "packages" / "rust" / "releasefoundry-runtime-verify"
VECTOR = CRATE / "test-vectors" / "identity_verification_hmac_sha256_v1.json"


def _canonical(value: object) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_canonical(value[key])}"
            for key in sorted(value)
        ) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, float):
        raise AssertionError("security vector must not contain floating-point values")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def test_cross_language_vector_recomputes_with_python_stdlib() -> None:
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    envelope = dict(vector["envelope"])
    signature = envelope.pop("signature")
    canonical = _canonical(envelope)

    assert canonical == vector["canonical_signing_json"]
    assert hashlib.sha256(canonical.encode()).hexdigest() == vector["canonical_signing_sha256"]
    assert hmac.new(
        vector["key_utf8"].encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest() == signature


def test_envelope_is_digest_only_and_replay_guard_complete() -> None:
    envelope = json.loads(VECTOR.read_text(encoding="utf-8"))["envelope"]
    expected_digest_fields = {
        "tenant_digest",
        "project_digest",
        "principal_digest",
        "event_id_digest",
        "idempotency_key_digest",
        "request_digest",
        "nonce_digest",
        "payload_digest",
        "evidence_digest",
    }
    assert expected_digest_fields <= envelope.keys()
    for field in expected_digest_fields:
        assert len(envelope[field]) == 64
        assert envelope[field] == envelope[field].lower()
        int(envelope[field], 16)

    forbidden = {
        "otp",
        "code",
        "email",
        "phone",
        "token",
        "authorization",
        "cookie",
        "provider_subject",
        "raw_payload",
    }
    assert forbidden.isdisjoint(envelope)


def test_cli_preserves_legacy_commands_and_never_accepts_inline_key() -> None:
    main_source = (CRATE / "src" / "main.rs").read_text(encoding="utf-8")
    readme = (CRATE / "README.md").read_text(encoding="utf-8")
    for command in ("verify", "replay-plan", "verify-bundle"):
        assert f'"{command}"' in main_source
        assert command in readme
    assert "--key-env" in main_source
    assert "--key " not in main_source
    assert "key_utf8" not in main_source


def test_library_requires_strict_schema_and_constant_time_primitives() -> None:
    library = (CRATE / "src" / "lib.rs").read_text(encoding="utf-8")
    cargo = (CRATE / "Cargo.toml").read_text(encoding="utf-8")
    assert "#[serde(deny_unknown_fields)]" in library
    assert "reject_duplicate_object_keys" in library
    assert "floating-point numbers are forbidden" in library
    assert ".ct_eq(" in library
    assert "verify_slice(signature)" in library
    assert "pub trait ReplayGuard" in library
    assert "IdempotentReplay" in library
    assert "subtle" in cargo
    assert "hmac" in cargo


def test_authenticated_bundle_closes_self_hash_and_path_escape_gaps() -> None:
    library = (CRATE / "src" / "lib.rs").read_text(encoding="utf-8")
    main_source = (CRATE / "src" / "main.rs").read_text(encoding="utf-8")
    readme = (CRATE / "README.md").read_text(encoding="utf-8")

    assert "releasefoundry.a1.authenticated_evidence_bundle.v2" in library
    assert "pub struct AuthenticatedEvidenceBundle" in library
    assert "pub struct EvidenceArtifact" in library
    assert "EvidenceDigestMismatch" in library
    assert "UnsafeArtifactPath" in library
    assert "DuplicateArtifactPath" in library
    assert "MAX_EVIDENCE_ITEMS" in library
    assert "path.contains('\\\\')" in library
    assert 'matches!(component, "." | "..")' in library
    assert '"verify-signed-bundle"' in main_source
    assert "--key-env" in main_source
    assert "integrity-only" in readme
