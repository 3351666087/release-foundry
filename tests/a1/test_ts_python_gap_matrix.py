from __future__ import annotations

import json
import re
from pathlib import Path

from tests.a1.ts_python_parity_matrix import ARTIFACT, MEDIA_MODALITIES, REQUIRED_HOSTED_ROUTE_LITERALS, generate_matrix


def _matrix_by_area(matrix: dict) -> dict[str, dict]:
    return {entry["area"]: entry for entry in matrix["gap_matrix"]}


def test_ts_python_gap_matrix_is_generated_public_safe_and_current():
    matrix = json.loads(ARTIFACT.read_text(encoding="utf-8-sig"))
    assert matrix == generate_matrix()

    assert matrix["schema_version"] == "ashr.clone.a1_ts_python_gap_matrix.v2"
    assert matrix["public_safe"] is True
    assert matrix["secret_policy"] == {
        "private_evidence_read": False,
        "tokens_included": False,
        "raw_private_payloads_included": False,
        "input_sources": [
            "packages/sdk/ashr_clone public module source",
            "packages/ts/ashr-clone public package metadata and src source",
            "tests/a1 generated public parity generator",
        ],
    }

    text = ARTIFACT.read_text(encoding="utf-8-sig")
    for forbidden in ("private_refs", "sk-", "Bearer ", "ashr_live_"):
        assert forbidden not in text
    assert re.search(r"(?<![a-z])tp_", text, re.IGNORECASE) is None

    by_area = _matrix_by_area(matrix)
    assert set(by_area) == {
        "exported Python functions/classes/types vs TS exports",
        "CLI commands",
        "SaaS route literals",
        "media text/audio/file/image/video parity",
        "official API calibration SDK import surface",
        "Python/TypeScript identity delivery protocol",
        "Python/TypeScript unified identity contract",
        "Python/TypeScript session lifecycle contract",
    }
    assert by_area["CLI commands"]["status"] in {"parity", "typescript_leads"}
    assert by_area["media text/audio/file/image/video parity"]["status"] == "parity"
    assert by_area["official API calibration SDK import surface"]["status"] == "parity"

    symbols = matrix["generated_contract"]["symbols"]
    assert "SaaSIngestionClient" in symbols["shared_export_names"]
    assert "CloudApiService" in symbols["typescript_only_export_names"]
    assert "capability_matrix" not in symbols["typescript_effective_export_names"]
    assert symbols["python_only_export_names"] == []

    cli = matrix["generated_contract"]["cli"]
    assert "bootstrap" in cli["python_commands"]["ashr_clone.saas_cli"]
    assert "release-gate" in cli["typescript_commands"]["saas"]
    assert cli["python_only_saas_command_names"] == []
    assert "job-lease" in cli["typescript_only_saas_command_names"]

    routes = matrix["generated_contract"]["routes"]
    assert "/v1/bootstrap" in routes["shared_route_literals"]
    assert routes["python_saas_route_literals"]
    assert routes["typescript_saas_route_literals"]
    assert routes["required_hosted_route_literals"] == REQUIRED_HOSTED_ROUTE_LITERALS
    assert routes["missing_required_python_hosted_routes"] == []
    assert routes["missing_required_typescript_hosted_routes"] == []

    media = matrix["generated_contract"]["media"]
    assert media["required_modalities"] == MEDIA_MODALITIES
    assert media["python"]["agent_input_part_types"] == MEDIA_MODALITIES
    assert media["typescript"]["agent_input_part_types"] == MEDIA_MODALITIES
    assert media["typescript"]["safe_media_envelope_exported"] is True

    calibration = matrix["generated_contract"]["calibration"]
    assert calibration["typescript"]["barrel_module_exported"] is True
    assert calibration["typescript"]["missing_required_exports"] == []
    assert calibration["typescript"]["sdk_import_surface"] == "public"

    identity = matrix["generated_contract"]["unified_identity"]
    assert identity["differing_fields"] == []
    assert identity["matching_fields"] == [
        "account_statuses",
        "credential_statuses",
        "forbidden_key_suffixes",
        "forbidden_public_keys",
        "invariants",
        "membership_roles",
        "membership_statuses",
        "providers",
        "public_safety",
        "recovery_providers",
        "routes",
        "schema_version",
        "stable_error_codes",
        "subject_model",
        "verification",
        "verification_audit_event_types",
        "verification_audit_outcome_codes",
        "verification_challenge_statuses",
        "verification_providers",
        "verification_public_surface",
        "verification_purposes",
        "verification_receipt_statuses",
    ]
    assert identity["requirements"] == {
        "memberships_independent": True,
        "no_email_automerge": True,
        "public_safe": True,
        "seven_credential_kinds": True,
        "stable_account_principal": True,
    }
    assert identity["python"]["providers"] == [
        "alipay",
        "email",
        "github",
        "google",
        "phone",
        "qq",
        "wechat",
    ]
    assert len(identity["python"]["stable_error_codes"]) == 28
    assert len(identity["python"]["routes"]) == 12
    assert len(identity["python"]["verification_public_surface"]) == 10
    assert identity["python"]["verification"]["digest_only_envelopes"] is True
    assert identity["typescript"]["verification"]["atomic_receipt_consumption"] is True
    assert by_area["Python/TypeScript unified identity contract"]["status"] == "parity"

    session = matrix["generated_contract"]["session_lifecycle"]
    assert session["differing_fields"] == []
    assert session["matching_fields"] == [
        "digest_only",
        "invariants",
        "recent_auth",
        "recovery",
        "reuse_detection",
        "revocation",
        "rotation",
        "routes",
        "schema_version",
        "stable_error_codes",
        "statuses",
    ]
    assert len(session["python"]["routes"]) == 9
    assert len(session["python"]["stable_error_codes"]) == 9
    assert all(session["python"][key] is True for key in (
        "digest_only", "rotation", "reuse_detection", "revocation", "recent_auth", "recovery"
    ))
    assert by_area["Python/TypeScript session lifecycle contract"]["status"] == "parity"

    delivery = matrix["generated_contract"]["identity_delivery_protocol"]
    assert delivery["differing_fields"] == []
    assert delivery["matching_fields"] == [
        "acceptance_statuses",
        "dto_kinds",
        "failure_codes",
        "invariants",
        "routes",
        "schema_version",
        "stable_error_codes",
        "statuses",
    ]
    assert len(delivery["python"]["dto_kinds"]) == 4
    assert len(delivery["python"]["routes"]) == 5
    assert len(delivery["python"]["statuses"]) == 7
    assert len(delivery["python"]["stable_error_codes"]) == 11
    assert delivery["python"]["invariants"][
        "provider_idempotency_stable_on_retry"
    ] is True
    assert delivery["python"]["invariants"][
        "provider_idempotency_rotates_only_on_audited_redrive"
    ] is True
    assert delivery["python"]["invariants"][
        "ambiguous_provider_outcome_fails_closed"
    ] is True
    assert by_area["Python/TypeScript identity delivery protocol"]["status"] == "parity"

    for entry in matrix["gap_matrix"]:
        assert entry["status"] in {"parity", "partial", "python_leads", "typescript_leads"}
        assert entry["evidence"]
        for path in entry["evidence"]:
            assert not Path(path).is_absolute()
            assert "private" not in path.lower()
            assert "secret" not in path.lower()
