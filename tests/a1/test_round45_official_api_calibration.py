from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SUMMARY = ROOT / "docs" / "a1" / "evidence" / "official_api_round45_public_summary.json"
FIELD_MAP = ROOT / "docs" / "a1" / "api_calibration" / "round45_official_api_frontend_field_map.json"
READINESS = ROOT / "docs" / "a1" / "api_calibration" / "official_api_readiness_packet.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_round45_public_summary_is_read_only_and_redacted():
    summary = _load(PUBLIC_SUMMARY)

    assert summary["schema_version"] == "releasefoundry.public_official_api_manifest_summary.v1"
    assert summary["source_private_manifest"] == "docs/evidence/private_refs/a1_readonly_api_round45_20260710.json"
    assert summary["source_private_manifest_present"] is True
    assert summary["status"] == "ok"
    assert summary["summary"]["total_steps"] == 5
    assert summary["summary"]["read_steps"] == 5
    assert summary["summary"]["mutating_steps"] == 0
    assert summary["summary"]["error_steps"] == 0
    assert summary["summary"]["quota_block_count"] == 0
    assert summary["public_safety"]["raw_payload_values_included"] is False
    assert summary["public_safety"]["header_values_included"] is False
    assert summary["public_safety"]["raw_key_material_present"] is False
    assert summary["public_safety"]["private_payload_contents_present"] is False

    assert [step["function"] for step in summary["step_summaries"]] == [
        "init",
        "keep_alive",
        "list_agents",
        "list_datasets",
        "list_requests",
    ]
    assert all(step["kind"] == "read" for step in summary["step_summaries"])
    assert all(step["status_code"] == 200 for step in summary["step_summaries"])


def test_round45_field_map_separates_official_observation_from_frontend_static_evidence():
    summary = _load(PUBLIC_SUMMARY)
    field_map = _load(FIELD_MAP)

    observed = field_map["official_api_observed"]
    mirror = field_map["frontend_mirror_static"]
    summary_keys = {step["function"]: step["response_keys"] for step in summary["step_summaries"]}

    assert field_map["schema_version"] == "releasefoundry.a1.official_api_frontend_field_map.v1"
    assert observed["mode"] == "read-only small batch"
    assert observed["usage_or_quota_fields_observed"] == []
    assert observed["media_fields_observed"] == []
    assert {name: value["response_keys"] for name, value in observed["functions"].items()} == summary_keys

    assert mirror["source_sha256"] == "1d12159feb2e1133941bba05d46f24a0e38002dabdfaa29c9cadc7a63d056793"
    assert mirror["inspection_mode"] == "read-only ZIP entry inspection"
    assert {"get_usage", "billing_get_status", "create_request"}.issubset(mirror["api_functions"])
    assert {"videos", "images", "simulations", "audios", "files", "graded_scenarios", "observations", "voice_minutes"} == set(
        mirror["usage_fields"]
    )
    assert {"generate_audio", "generate_files", "generate_simulations", "generation_options"}.issubset(
        mirror["media_and_generation_fields"]
    )
    assert {"Queued", "Processing", "Failed", "Completed", "Retry", "Retrying"} == set(mirror["request_lifecycle_labels"])
    assert "not proof" in mirror["interpretation"]


def test_round45_mutation_is_fail_closed_by_existing_readiness_gate():
    field_map = _load(FIELD_MAP)
    readiness = _load(READINESS)
    decision = field_map["mutation_decision"]

    assert readiness["readiness"]["read_only_small_batch_ready"] is True
    assert readiness["readiness"]["mutating_small_batch_ready"] is False
    assert decision["performed"] is False
    assert decision["decision"] == "fail-closed"
    assert decision["mutating_small_batch_ready"] is False
    assert decision["fresh_target_bound_quota_gate_present"] is False


def test_round45_field_map_contains_only_public_safe_names_and_references():
    field_map = _load(FIELD_MAP)
    serialized = json.dumps(field_map, sort_keys=True).lower()

    assert field_map["public_safety"] == {
        "raw_archive_committed": False,
        "raw_mirrored_source_committed": False,
        "raw_api_payload_values_included": False,
        "raw_header_values_included": False,
        "secret_values_included": False,
        "private_evidence_contents_included": False,
        "private_evidence_paths_only": True,
    }
    forbidden_fragments = (
        "bearer" + " ",
        "sk" + "-",
        "set-cookie" + ":",
        "authorization" + ":",
        "releasefoundry_api_key" + "=",
    )
    for forbidden in forbidden_fragments:
        assert forbidden not in serialized
