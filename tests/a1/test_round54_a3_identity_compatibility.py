from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT
    / "docs"
    / "a1"
    / "evidence"
    / "round54_a3_identity_verification_compatibility.json"
)
SCHEMA = (
    ROOT
    / "docs"
    / "a1"
    / "schemas"
    / "a3_identity_verification_compatibility.schema.json"
)
SERVER = ROOT / "packages" / "go" / "releasefoundry" / "server.go"
VERIFICATION_HTTP = ROOT / "packages" / "go" / "releasefoundry" / "identity_verification_http.go"
VERIFICATION_SECURITY = (
    ROOT / "packages" / "go" / "releasefoundry" / "identity_verification_security.go"
)
VERIFICATION_SERVICE = ROOT / "packages" / "go" / "releasefoundry" / "identity_verification.go"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_a1_owned_a3_compatibility_snapshot_matches_schema_and_latest_request_ref() -> None:
    fixture = _load(FIXTURE)
    schema = _load(SCHEMA)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(fixture)
    assert fixture["latest_change_request"] == {
        "ref": "origin/agent/a3-commercial-growth-round4",
        "commit_sha": "2250254bfeeb8d9c24008c997296bf62b2e846a3",
        "document_path": "docs/a3/a1_identity_verification_contract_change_request_2026_07_11.md",
        "document_blob_sha": "1e552e0ed4db405451e3e9838cc00c855ca94989",
        "a3_code_imported": False,
    }
    assert fixture["a1_baseline"]["commit_sha"] == "c784163588e9e0839fe17c604f3285c42efe3661"


def test_snapshot_uses_only_a1_source_evidence_and_imports_no_a3_runtime_or_judge_code() -> None:
    fixture = _load(FIXTURE)

    for capability in fixture["capabilities"]:
        assert capability["source_evidence"]
        assert all(
            source.startswith(("packages/go/releasefoundry/", "tests/a1/"))
            for source in capability["source_evidence"]
        )
        assert all("apps/webapp" not in source for source in capability["source_evidence"])
        assert all("services/judge" not in source for source in capability["source_evidence"])
    assert fixture["safety"]["a3_runtime_imported"] is False
    assert fixture["safety"]["a2_judge_imported"] is False
    assert fixture["authority_boundary"]["judge_semantics_changed"] is False
    assert fixture["authority_boundary"]["dashboard_business_changed"] is False


def test_route_snapshot_claims_only_current_a1_dispatch_and_manifest_facts() -> None:
    fixture = _load(FIXTURE)
    routes = {(item["method"], item["path"]): item for item in fixture["route_compatibility"]}
    server = SERVER.read_text(encoding="utf-8")
    verification_http = VERIFICATION_HTTP.read_text(encoding="utf-8")

    assert set(routes) == {
        ("POST", "/v1/identity-verification/challenges"),
        ("POST", "/v1/identity-verification/verify"),
        (
            "POST",
            "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh",
        ),
    }
    assert 'parts[1] == "identity-verification"' in server
    assert 'case "challenges":' in verification_http
    assert 'case "verify":' in verification_http
    assert (
        'goScopedRoute("POST", "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh"'
        in server
    )
    assert routes[("POST", "/v1/identity-verification/challenges")][
        "public_manifest_advertised"
    ] is False
    assert routes[("POST", "/v1/identity-verification/verify")][
        "public_manifest_advertised"
    ] is False
    assert routes[
        (
            "POST",
            "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh",
        )
    ]["public_manifest_advertised"] is True
    assert fixture["disposition"]["unsupported_routes_claimed"] is False


def test_supported_and_blocked_capabilities_follow_current_a1_source_behavior() -> None:
    fixture = _load(FIXTURE)
    capabilities = {item["id"]: item for item in fixture["capabilities"]}
    verification_http = VERIFICATION_HTTP.read_text(encoding="utf-8")
    verification_security = VERIFICATION_SECURITY.read_text(encoding="utf-8")
    verification_service = VERIFICATION_SERVICE.read_text(encoding="utf-8")

    assert len(capabilities) == len(fixture["capabilities"])
    assert capabilities["uniform_challenge_start_response"]["status"] == "supported"
    assert 'Status:        "accepted"' in verification_security
    public_response = verification_security[
        verification_security.index("type IdentityVerificationPublicResponse struct") :
        verification_security.index("type IdentityVerificationResponsePolicyOptions struct")
    ]
    assert "ChallengeID" not in public_response
    assert "VerificationToken" not in public_response

    assert capabilities["browser_safe_verification_context"]["status"] == "blocked"
    assert capabilities["server_owned_verification_scope"]["status"] == "blocked"
    assert 'ChallengeID: stringValue(body, "challenge_id")' in verification_http
    assert 'Identifier: stringValue(body, "identifier")' in verification_http
    assert "verification_token" not in verification_http
    assert "verification_token" not in verification_service

    assert capabilities["secure_session_after_login_or_recovery_verify"]["status"] == "supported"
    assert "CompleteAndIssueSession" in verification_http
    assert "WriteIdentitySessionReceipt" in verification_http
    assert capabilities["same_origin_refresh_rotation"]["status"] == "supported"
    assert "validateIdentitySessionRefreshBrowserRequest" in verification_http
    assert "identitySessionRefreshIdempotencyKey" in verification_http

    assert capabilities["allowlisted_post_verify_redirect"]["status"] == "blocked"
    verify_case = verification_http[verification_http.index('case "verify":') :]
    assert "http.StatusSeeOther" not in verify_case
    assert "writeJSON(writer, http.StatusOK" in verify_case


def test_disposition_preserves_fail_closed_a3_behavior_until_all_blockers_are_resolved() -> None:
    fixture = _load(FIXTURE)
    capabilities = {item["id"]: item for item in fixture["capabilities"]}
    blocked = sorted(
        item["id"] for item in fixture["capabilities"] if item["status"] == "blocked"
    )

    assert fixture["disposition"]["change_request_resolved"] is False
    assert fixture["disposition"]["a3_should_fail_closed"] is True
    assert fixture["disposition"]["blocking_capability_ids"] == blocked
    assert set(fixture["disposition"]["newly_supported_since_request"]) == {
        "same_origin_refresh_rotation",
        "secure_session_after_login_or_recovery_verify",
    }
    assert all(capabilities[item]["status"] == "supported" for item in fixture["disposition"]["newly_supported_since_request"])


def test_compatibility_snapshot_is_public_safe_and_contains_no_secret_values() -> None:
    fixture = _load(FIXTURE)
    serialized = json.dumps(fixture, sort_keys=True)

    assert fixture["safety"] == {
        "public_safe": True,
        "secret_values_included": False,
        "raw_identifiers_included": False,
        "tokens_or_codes_included": False,
        "a3_runtime_imported": False,
        "a2_judge_imported": False,
    }
    forbidden = (
        re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}", re.IGNORECASE),
        re.compile(r"releasefoundry_(?:live|test)_[A-Za-z0-9_-]+"),
        re.compile(r"sk-[A-Za-z0-9]{8,}"),
        re.compile(r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    )
    assert all(pattern.search(serialized) is None for pattern in forbidden)
