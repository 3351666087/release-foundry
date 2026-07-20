from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import jsonschema

from scripts.a2_build_m40_rc3_authority import (
    A2_AUTHORITY_GIT_SHA,
    GRADE_RESULTS_PATH,
    SHARED_IDENTITY_PATH,
    TRUSTED_SPINE_PATH,
    build_outputs,
)
from scripts.a2_verify_shared_candidate_identity import (
    verify_shared_candidate_identity,
)
from services.judge.result_persistence import stable_hash
from services.judge.trusted_spine import build_decision_ledger


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "docs/a2/schemas"
SECRET_PATTERNS = [
    re.compile(r"ashr_live_[A-Za-z0-9_-]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"Bearer\s+", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
]


def load_json(path: str | Path) -> dict:
    value = Path(path)
    if not value.is_absolute():
        value = ROOT / value
    return json.loads(value.read_text(encoding="utf-8"))


def test_m40_rc3_a2_authority_is_recomputable_and_fail_closed() -> None:
    committed = {
        "grade_results": load_json(GRADE_RESULTS_PATH),
        "shared_candidate_identity": load_json(SHARED_IDENTITY_PATH),
        "trusted_spine": load_json(TRUSTED_SPINE_PATH),
    }
    assert build_outputs() == committed

    grades = committed["grade_results"]
    identity = committed["shared_candidate_identity"]
    spine = committed["trusted_spine"]
    assert grades["total_cases"] == grades["passed"] == 3
    assert grades["failed"] == 0
    assert {item["score"] for item in grades["grade_results"]} == {100.0}
    assert {item["primary_failure_class"] for item in grades["grade_results"]} == {
        "none"
    }

    binding = spine["candidate_binding"]
    assert binding == {
        "candidate_id": "a3-golden-agent@0.2.0-rc.3",
        "run_id": "a3-golden-20260720-003",
        "evidence_release_version": "0.2.0-rc.3",
        "a1_source_commit": "1d292047e991995fdf52f0545ffff410ee19a171",
        "a2_authority_commit": A2_AUTHORITY_GIT_SHA,
        "a1_evidence_bundle_hash": (
            "sha256:0b4fb982ccc5a25a54c8c8ea8744285296502bb6be3113d5220af7f3340e3d6b"
        ),
    }
    snapshots = {item["case_id"]: item for item in spine["evidence_snapshots"]}
    assert set(snapshots) == {
        "a3-gp2-direct-answer",
        "a3-gp2-required-web-tool",
        "a3-gp2-media-pipeline",
    }
    assert snapshots["a3-gp2-direct-answer"]["completeness"] == "complete"
    assert snapshots["a3-gp2-required-web-tool"]["completeness"] == "complete"
    media = snapshots["a3-gp2-media-pipeline"]
    assert media["artifact_modalities"] == ["image"]
    assert media["observed_modalities"] == ["text"]
    assert media["missing_modalities"] == ["image"]
    assert media["completeness"] == "evidence_missing"

    ledger = spine["decision_ledger"]
    assert ledger["record_count"] == 3
    assert {record["run_id"] for record in ledger["records"]} == {
        "a3-golden-20260720-003"
    }
    assert {record["decision"] for record in ledger["records"]} == {"block"}
    assert ledger["head_hash"] == ledger["records"][-1]["record_hash"]
    assert spine["decision_summary"]["decision"] == "block"
    assert "latest_multimodal_control_quality_blocked" in spine[
        "decision_summary"
    ]["blockers"]
    assert "latest_multimodal_repeat_promotion_blocked" in spine[
        "decision_summary"
    ]["blockers"]
    assert "latest_cloud_multimodal_qualification_blocked" in spine[
        "decision_summary"
    ]["blockers"]
    assert "latest_local_multimodal_runtime_blocked" in spine[
        "decision_summary"
    ]["blockers"]
    assert "pending_multimodal_human_review" in spine["decision_summary"][
        "blockers"
    ]
    assert "same_round_real_postgresql_unverified" not in spine[
        "decision_summary"
    ]["blockers"]
    assert spine["decision_summary"]["same_round_postgresql_verified"] is True
    assert "evidence_snapshot_incomplete:a3-gp2-media-pipeline" in spine[
        "decision_summary"
    ]["blockers"]
    assert spine["a3_consumption"]["release_ready"] is False
    assert spine["a3_consumption"]["may_recompute_grade"] is False
    assert spine["metadata"]["production_authority"] is False

    expected_identity_blockers = [
        "a3_consumed_decision_hash_mismatch",
        "a3_consumed_grades_hash_mismatch",
        "a3_rc3_delivery_not_generated",
    ]
    assert identity["a2"]["decision_hash"] == ledger["head_hash"]
    assert identity["a2"]["grades_hash"] == stable_hash(grades)
    assert identity["binding_state"] == "blocked"
    assert identity["blockers"] == expected_identity_blockers
    assert verify_shared_candidate_identity(identity) == expected_identity_blockers


def test_m40_rc3_a2_contracts_hash_chain_and_public_safety() -> None:
    grades = load_json(GRADE_RESULTS_PATH)
    identity = load_json(SHARED_IDENTITY_PATH)
    spine = load_json(TRUSTED_SPINE_PATH)
    _validate_schema("grade_results.schema.json", grades)
    _validate_schema("shared_candidate_identity_v2.schema.json", identity)
    _validate_spine_schema(spine)

    rebuilt_ledger = build_decision_ledger(
        deepcopy(spine["decision_ledger"]["records"]),
        ledger_id=spine["decision_ledger"]["ledger_id"],
        organization_id=spine["decision_ledger"]["organization_id"],
        tenant_id=spine["decision_ledger"]["tenant_id"],
        workspace_id=spine["decision_ledger"]["workspace_id"],
        project_id=spine["decision_ledger"]["project_id"],
        environment_id=spine["decision_ledger"]["environment_id"],
        created_at=spine["decision_ledger"]["created_at"],
    )
    assert rebuilt_ledger == spine["decision_ledger"]
    assert spine["bundle_hash"] == stable_hash(
        {key: value for key, value in spine.items() if key != "bundle_hash"}
    )

    public_text = "\n".join(
        json.dumps(value, sort_keys=True)
        for value in (grades, identity, spine)
    )
    for pattern in SECRET_PATTERNS:
        assert pattern.search(public_text) is None


def _validate_schema(name: str, value: dict) -> None:
    schema = load_json(SCHEMAS / name)
    jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(value)


def _validate_spine_schema(value: dict) -> None:
    schema_path = SCHEMAS / "candidate_trusted_spine.schema.json"
    schema = load_json(schema_path)
    evidence_schema = load_json(SCHEMAS / "evidence_snapshot.schema.json")
    ledger_schema = load_json(SCHEMAS / "decision_ledger.schema.json")
    derived_schema = load_json(SCHEMAS / "derived_evidence.schema.json")
    resolver = jsonschema.RefResolver(
        schema_path.as_uri(),
        schema,
        store={
            "https://ashr.io/schemas/a2/evidence_snapshot.schema.json": evidence_schema,
            "https://ashr.io/schemas/a2/decision_ledger.schema.json": ledger_schema,
            "https://ashr.io/schemas/a2/derived_evidence.schema.json": derived_schema,
        },
    )
    jsonschema.validate(
        value,
        schema,
        resolver=resolver,
        format_checker=jsonschema.FormatChecker(),
    )
