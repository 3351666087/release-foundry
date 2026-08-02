"""Candidate-bound A2 authority evidence for cross-lane releases."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .result_persistence import stable_hash
from .runner import grade_runs
from .trusted_spine import (
    GENESIS_HASH,
    build_decision_ledger,
    build_decision_record,
    build_evidence_snapshot,
)


CANDIDATE_TRUSTED_SPINE_SCHEMA_VERSION = "a2.candidate_trusted_spine.v1"
SHARED_CANDIDATE_IDENTITY_SCHEMA_VERSION = "a2.shared_candidate_identity.v2"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ZERO_HASH = GENESIS_HASH

SCOPE = {
    "organization_id": "org_local_demo",
    "tenant_id": "tenant_local_demo",
    "workspace_id": "workspace_local_demo",
    "project_id": "releasefoundry_plus_plus_golden_path",
    "environment_id": "staging",
}


def build_candidate_authority(
    *,
    run_result: dict[str, Any],
    a1_receipt: dict[str, Any],
    source_release_gate: dict[str, Any],
    multimodal_control: dict[str, Any],
    multimodal_repeat: dict[str, Any],
    cloud_control: dict[str, Any],
    local_runtime: dict[str, Any],
    postgresql_qualification: dict[str, Any],
    review_collection: dict[str, Any],
    review_conservation: dict[str, Any],
    run_result_file_hash: str,
    a1_receipt_file_hash: str,
    a2_git_sha: str,
    a3_baseline_git_sha: str,
    created_at: str,
    source_paths: dict[str, str],
    grade_results_path: str,
    shared_identity_path: str,
) -> dict[str, dict[str, Any]]:
    """Regrade one A1 run and bind A2's unchanged release policy to it."""
    identity = _validate_inputs(
        run_result=run_result,
        a1_receipt=a1_receipt,
        run_result_file_hash=run_result_file_hash,
        a2_git_sha=a2_git_sha,
        a3_baseline_git_sha=a3_baseline_git_sha,
    )
    candidate_id = identity["candidate_id"]
    run_id = identity["run_id"]

    grade_results = grade_runs(
        run_result["cases"],
        report_id=f"a2-{run_id}-grade-results",
        dataset_id=str(run_result["dataset_id"]),
    )
    grades_hash = stable_hash(grade_results)

    snapshots = _build_snapshots(run_result, created_at=created_at)
    source_hashes = {
        "release_gate": stable_hash(source_release_gate),
        "multimodal_control": stable_hash(multimodal_control),
        "multimodal_repeat": stable_hash(multimodal_repeat),
        "cloud_control": stable_hash(cloud_control),
        "local_runtime": stable_hash(local_runtime),
        "postgresql_qualification": stable_hash(postgresql_qualification),
        "review_collection": stable_hash(review_collection),
        "review_conservation": stable_hash(review_conservation),
    }
    blockers = _authority_blockers(
        grade_results=grade_results,
        snapshots=snapshots,
        source_release_gate=source_release_gate,
        multimodal_control=multimodal_control,
        multimodal_repeat=multimodal_repeat,
        cloud_control=cloud_control,
        local_runtime=local_runtime,
        postgresql_qualification=postgresql_qualification,
        review_collection=review_collection,
        review_conservation=review_conservation,
    )
    decision = "block" if blockers else "allow"
    candidate_gate = {
        "schema_version": "a2.candidate_release_gate.v1",
        "candidate_id": candidate_id,
        "run_id": run_id,
        "decision": decision,
        "blocking_reasons": [
            {"reason_id": blocker, "release_authority": False}
            for blocker in blockers
        ],
        "source_release_gate_hash": source_hashes["release_gate"],
        "multimodal_control_hash": source_hashes["multimodal_control"],
        "multimodal_repeat_hash": source_hashes["multimodal_repeat"],
        "cloud_control_hash": source_hashes["cloud_control"],
        "local_runtime_hash": source_hashes["local_runtime"],
        "postgresql_qualification_hash": source_hashes[
            "postgresql_qualification"
        ],
        "review_collection_hash": source_hashes["review_collection"],
        "review_conservation_hash": source_hashes["review_conservation"],
        "local_grade_summary": {
            "total_cases": grade_results["total_cases"],
            "passed": grade_results["passed"],
            "failed": grade_results["failed"],
        },
        "release_authority": True,
        "public_safe": True,
    }
    policy_version = "a2.candidate_release_policy.v1"
    policy_hash = stable_hash(
        {
            "policy_version": policy_version,
            "candidate_id": candidate_id,
            "a2_git_sha": a2_git_sha,
            **source_hashes,
        }
    )
    ledger = _build_ledger(
        snapshots=snapshots,
        grade_results=grade_results,
        candidate_gate=candidate_gate,
        decision=decision,
        policy_version=policy_version,
        policy_hash=policy_hash,
        run_id=run_id,
        created_at=created_at,
    )

    shared_identity = _build_shared_identity(
        candidate_id=candidate_id,
        a1_git_sha=identity["a1_git_sha"],
        a1_evidence_bundle_hash=identity["a1_evidence_bundle_hash"],
        a2_git_sha=a2_git_sha,
        a3_baseline_git_sha=a3_baseline_git_sha,
        decision_hash=str(ledger["head_hash"]),
        grades_hash=grades_hash,
        review_collection_hash=source_hashes["review_collection"],
        review_conservation_hash=source_hashes["review_conservation"],
    )
    source_evidence = {
        "a1_receipt": _source_ref(
            source_paths["a1_receipt"], a1_receipt_file_hash
        ),
        "a1_run_result": _source_ref(
            source_paths["a1_run_result"], run_result_file_hash
        ),
        "a2_release_gate": _source_ref(
            source_paths["a2_release_gate"], source_hashes["release_gate"]
        ),
        "a2_multimodal_control": _source_ref(
            source_paths["a2_multimodal_control"],
            source_hashes["multimodal_control"],
        ),
        "a2_multimodal_repeat": _source_ref(
            source_paths["a2_multimodal_repeat"],
            source_hashes["multimodal_repeat"],
        ),
        "a2_cloud_control": _source_ref(
            source_paths["a2_cloud_control"],
            source_hashes["cloud_control"],
        ),
        "a2_local_runtime": _source_ref(
            source_paths["a2_local_runtime"],
            source_hashes["local_runtime"],
        ),
        "a2_postgresql_qualification": _source_ref(
            source_paths["a2_postgresql_qualification"],
            source_hashes["postgresql_qualification"],
        ),
        "a2_review_collection": _source_ref(
            source_paths["a2_review_collection"],
            source_hashes["review_collection"],
        ),
        "a2_review_conservation": _source_ref(
            source_paths["a2_review_conservation"],
            source_hashes["review_conservation"],
        ),
    }
    spine_core = {
        "schema_version": CANDIDATE_TRUSTED_SPINE_SCHEMA_VERSION,
        "candidate_binding": {
            "candidate_id": candidate_id,
            "run_id": run_id,
            "evidence_release_version": identity["evidence_release_version"],
            "a1_source_commit": identity["a1_git_sha"],
            "a2_authority_commit": a2_git_sha,
            "a1_evidence_bundle_hash": identity["a1_evidence_bundle_hash"],
        },
        "source_evidence": source_evidence,
        "grade_results": {
            "path": grade_results_path,
            "hash": grades_hash,
            "total_cases": grade_results["total_cases"],
            "passed": grade_results["passed"],
            "failed": grade_results["failed"],
        },
        "evidence_snapshots": snapshots,
        "decision_ledger": ledger,
        "shared_candidate_identity": {
            "path": shared_identity_path,
            "hash": stable_hash(shared_identity),
            "binding_state": shared_identity["binding_state"],
            "blockers": shared_identity["blockers"],
        },
        "decision_summary": {
            "decision": decision,
            "blockers": blockers,
            "local_cases_passed": grade_results["passed"],
            "local_cases_total": grade_results["total_cases"],
            "source_release_gate_decision": source_release_gate.get("decision"),
            "multimodal_control_quality_state": multimodal_control.get(
                "quality_state"
            ),
            "multimodal_repeat_promotion_eligible": bool(
                multimodal_repeat.get("promotion_eligible", False)
            ),
            "cloud_control_qualification_state": cloud_control.get(
                "qualification_state"
            ),
            "local_runtime_promotion_state": local_runtime.get(
                "runtime_promotion_state"
            ),
            "same_round_postgresql_verified": bool(
                postgresql_qualification.get("claims", {}).get(
                    "same_round_real_postgresql_verified", False
                )
            ),
            "source_quality_blockers": _source_quality_blockers(
                multimodal_control=multimodal_control,
                multimodal_repeat=multimodal_repeat,
                cloud_control=cloud_control,
                local_runtime=local_runtime,
            ),
            "human_review_state": review_collection.get("collection_state"),
            "review_conservation_verified": (
                review_conservation.get("verification_state") == "verified"
                and review_conservation.get("conservation_holds") is True
            ),
            "release_authority": True,
        },
        "a3_consumption": {
            "release_ready": decision == "allow",
            "decision_record_required": True,
            "may_recompute_grade": False,
            "may_override_decision": False,
            "review_queue_status": (
                "blocked" if decision == "block" else "not_required"
            ),
            "display_decision": decision,
            "display_provenance_hash": ledger["head_hash"],
            "delivery_generated": False,
        },
        "metadata": {
            "created_at": created_at,
            "public_safe": True,
            "raw_evidence_included": False,
            "secrets_included": False,
            "requires_network": False,
            "a1_release_authority": False,
            "a2_decision_authority": True,
            "a3_delivery_generated": False,
            "production_authority": False,
        },
    }
    trusted_spine = {
        **spine_core,
        "bundle_hash": stable_hash(spine_core),
    }
    return {
        "grade_results": grade_results,
        "shared_candidate_identity": shared_identity,
        "trusted_spine": trusted_spine,
    }


def _validate_inputs(
    *,
    run_result: dict[str, Any],
    a1_receipt: dict[str, Any],
    run_result_file_hash: str,
    a2_git_sha: str,
    a3_baseline_git_sha: str,
) -> dict[str, str]:
    for name, value in {
        "a2_git_sha": a2_git_sha,
        "a3_baseline_git_sha": a3_baseline_git_sha,
    }.items():
        if not GIT_SHA_RE.fullmatch(value):
            raise ValueError(f"{name} must be a lowercase 40-character git SHA")
    binding = a1_receipt.get("candidate_binding")
    receipt_run = a1_receipt.get("run")
    run_binding = run_result.get("metadata", {}).get("candidate_binding")
    if not all(isinstance(item, dict) for item in (binding, receipt_run, run_binding)):
        raise ValueError("candidate-bound A1 receipt and RunResult are required")
    if binding.get("source_tree_clean") is not True:
        raise ValueError("A1 candidate source tree was not clean")
    if run_result_file_hash != a1_receipt.get("evidence", {}).get(
        "run_result", {}
    ).get("sha256"):
        raise ValueError("A1 RunResult file hash does not match its receipt")

    expected = {
        "candidate_id": str(binding.get("candidate_id") or ""),
        "a1_git_sha": str(binding.get("candidate_source_commit") or ""),
        "evidence_release_version": str(
            binding.get("evidence_release_version") or ""
        ),
        "run_id": str(receipt_run.get("run_id") or ""),
        "a1_evidence_bundle_hash": str(
            a1_receipt.get("evidence_bundle_hash") or ""
        ),
    }
    if not expected["candidate_id"] or not GIT_SHA_RE.fullmatch(
        expected["a1_git_sha"]
    ):
        raise ValueError("A1 candidate identity is incomplete")
    if run_result.get("run_id") != expected["run_id"]:
        raise ValueError("A1 run id mismatch")
    if run_binding.get("candidate_id") != expected["candidate_id"]:
        raise ValueError("A1 RunResult candidate id mismatch")
    if run_binding.get("candidate_source_commit") != expected["a1_git_sha"]:
        raise ValueError("A1 RunResult source commit mismatch")
    if int(run_result.get("total_cases", -1)) != len(run_result.get("cases", [])):
        raise ValueError("A1 RunResult case count mismatch")
    if not expected["a1_evidence_bundle_hash"].startswith("sha256:"):
        raise ValueError("A1 evidence bundle hash is missing")
    return expected


def _build_snapshots(
    run_result: dict[str, Any], *, created_at: str
) -> list[dict[str, Any]]:
    snapshots = []
    for case in run_result["cases"]:
        case_id = str(case["case_id"])
        scenario_id = str(case["scenario_id"])
        first = build_evidence_snapshot(
            run_result,
            **SCOPE,
            run_id=str(run_result["run_id"]),
            case_id=case_id,
            scenario_id=scenario_id,
            created_at=created_at,
            required_modalities=["text"],
            source_schema_version=str(run_result.get("schema_version") or "unknown"),
        )
        required_modalities = sorted(
            set(first["required_modalities"]) | set(first["artifact_modalities"])
        )
        snapshot = (
            first
            if required_modalities == first["required_modalities"]
            else build_evidence_snapshot(
                run_result,
                **SCOPE,
                run_id=str(run_result["run_id"]),
                case_id=case_id,
                scenario_id=scenario_id,
                created_at=created_at,
                required_modalities=required_modalities,
                source_schema_version=str(
                    run_result.get("schema_version") or "unknown"
                ),
            )
        )
        snapshots.append(snapshot)
    return snapshots


def _authority_blockers(
    *,
    grade_results: dict[str, Any],
    snapshots: list[dict[str, Any]],
    source_release_gate: dict[str, Any],
    multimodal_control: dict[str, Any],
    multimodal_repeat: dict[str, Any],
    cloud_control: dict[str, Any],
    local_runtime: dict[str, Any],
    postgresql_qualification: dict[str, Any],
    review_collection: dict[str, Any],
    review_conservation: dict[str, Any],
) -> list[str]:
    blockers = []
    if grade_results["failed"]:
        blockers.append("candidate_local_grade_failed")
    blockers.extend(
        f"evidence_snapshot_incomplete:{snapshot['case_id']}"
        for snapshot in snapshots
        if snapshot.get("completeness") != "complete"
    )
    if source_release_gate.get("decision") != "allow":
        blockers.append("source_a2_release_gate_blocked")
    if multimodal_control.get("quality_state") != "qualified":
        blockers.append("latest_multimodal_control_quality_blocked")
    if multimodal_repeat.get("promotion_eligible") is not True:
        blockers.append("latest_multimodal_repeat_promotion_blocked")
    if cloud_control.get("qualification_state") != "qualified":
        blockers.append("latest_cloud_multimodal_qualification_blocked")
    if local_runtime.get("runtime_promotion_state") != "qualified":
        blockers.append("latest_local_multimodal_runtime_blocked")
    if review_collection.get("collection_state") != "complete":
        blockers.append("pending_multimodal_human_review")
    if not (
        review_conservation.get("verification_state") == "verified"
        and review_conservation.get("conservation_holds") is True
    ):
        blockers.append("multimodal_review_conservation_invalid")
    if not postgresql_qualification.get("claims", {}).get(
        "same_round_real_postgresql_verified", False
    ):
        blockers.append("same_round_real_postgresql_unverified")
    return sorted(set(blockers))


def _source_quality_blockers(
    *,
    multimodal_control: dict[str, Any],
    multimodal_repeat: dict[str, Any],
    cloud_control: dict[str, Any],
    local_runtime: dict[str, Any],
) -> list[str]:
    blockers = []
    for source in (
        multimodal_control,
        multimodal_repeat,
        cloud_control,
        local_runtime,
    ):
        for field in ("blockers", "quality_blockers"):
            blockers.extend(
                str(item)
                for item in source.get(field, [])
                if isinstance(item, str) and item
            )
    return sorted(set(blockers))


def _build_ledger(
    *,
    snapshots: list[dict[str, Any]],
    grade_results: dict[str, Any],
    candidate_gate: dict[str, Any],
    decision: str,
    policy_version: str,
    policy_hash: str,
    run_id: str,
    created_at: str,
) -> dict[str, Any]:
    grades_by_case = {
        str(item["case_id"]): item for item in grade_results["grade_results"]
    }
    records = []
    previous_hash = GENESIS_HASH
    for snapshot in snapshots:
        grade = grades_by_case[str(snapshot["case_id"])]
        record = build_decision_record(
            snapshot,
            decision=decision,
            release_gate_report=candidate_gate,
            judge_results=deepcopy(grade["judge_results"]),
            policy_version=policy_version,
            policy_hash=policy_hash,
            model_versions=["deterministic:a2-local-judges"],
            created_at=created_at,
            previous_record_hash=previous_hash,
        )
        records.append(record)
        previous_hash = str(record["record_hash"])
    return build_decision_ledger(
        records,
        ledger_id=f"a2-{run_id}-ledger",
        **SCOPE,
        created_at=created_at,
    )


def _build_shared_identity(
    *,
    candidate_id: str,
    a1_git_sha: str,
    a1_evidence_bundle_hash: str,
    a2_git_sha: str,
    a3_baseline_git_sha: str,
    decision_hash: str,
    grades_hash: str,
    review_collection_hash: str,
    review_conservation_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": SHARED_CANDIDATE_IDENTITY_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "a1": {
            "candidate_id": candidate_id,
            "git_sha": a1_git_sha,
            "evidence_bundle_hash": a1_evidence_bundle_hash,
        },
        "a2": {
            "candidate_id": candidate_id,
            "git_sha": a2_git_sha,
            "decision_hash": decision_hash,
            "grades_hash": grades_hash,
            "review_collection_hash": review_collection_hash,
            "review_conservation_hash": review_conservation_hash,
        },
        "a3": {
            "candidate_id": candidate_id,
            "git_sha": a3_baseline_git_sha,
            "consumed_decision_hash": ZERO_HASH,
            "consumed_grades_hash": ZERO_HASH,
        },
        "binding_state": "blocked",
        "blockers": [
            "a3_consumed_decision_hash_mismatch",
            "a3_consumed_grades_hash_mismatch",
            "a3_rc3_delivery_not_generated",
        ],
        "release_authority": False,
        "public_safe": True,
    }


def _source_ref(path: str, digest: str) -> dict[str, str]:
    return {"path": path, "hash": digest}
