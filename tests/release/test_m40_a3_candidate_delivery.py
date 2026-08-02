from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RC3 = ROOT / "fixtures" / "a3" / "golden-path" / "rc3"
EXPECTED_CANDIDATE = "a3-golden-agent@0.2.0-rc.3"
EXPECTED_RUN = "a3-golden-20260720-003"
EXPECTED_VERSION = "0.2.0-rc.3"
EXPECTED_A1_SHA = "1d292047e991995fdf52f0545ffff410ee19a171"
EXPECTED_DECISION_HEAD = (
    "sha256:bc608df9825ea316b374797ef76b4921bff4f6cee1943600d0297783e6be6303"
)
EXPECTED_GRADES_HASH = (
    "sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304"
)


def load_json(name: str) -> dict:
    return json.loads((RC3 / name).read_text(encoding="utf-8"))


def test_m40_05_rc3_delivery_check_recomputes_all_local_integrity() -> None:
    completed = subprocess.run(
        ["node", "scripts/a3_build_m40_rc3_delivery.mjs", "--check", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(completed.stdout)
    assert completed.stderr == ""
    assert receipt["status"] == "passed"
    assert receipt["candidate_id"] == EXPECTED_CANDIDATE
    assert receipt["run_id"] == EXPECTED_RUN
    assert receipt["release_version"] == EXPECTED_VERSION
    assert receipt["a2_decision"] == "block"
    assert receipt["a2_decision_ledger_head_hash"] == EXPECTED_DECISION_HEAD
    assert receipt["a2_grades_hash"] == EXPECTED_GRADES_HASH
    assert receipt["candidate_binding_verified"] is True
    assert receipt["audit_bundle_verified"] is True
    assert receipt["audit_archive_verified"] is True
    assert receipt["release_artifact_verified"] is True
    assert receipt["production_ready"] is False
    assert receipt["safety"] == {
        "a2_decision_recomputed": False,
        "human_approval_claimed": False,
        "production_authority_claimed": False,
        "live_github_readback_reused": False,
        "secrets_included": False,
    }


def test_m40_05_a3_identity_consumes_exact_a2_hashes() -> None:
    source_identity = load_json("a2_shared_candidate_identity.json")
    identity = load_json("a3_shared_candidate_identity.json")
    binding = load_json("a3_candidate_delivery_binding.json")
    implementation_commit = identity["a3"]["git_sha"]

    assert identity["candidate_id"] == EXPECTED_CANDIDATE
    assert identity["a1"] == source_identity["a1"]
    assert identity["a2"] == source_identity["a2"]
    assert identity["a3"]["consumed_decision_hash"] == EXPECTED_DECISION_HEAD
    assert identity["a3"]["consumed_grades_hash"] == EXPECTED_GRADES_HASH
    assert identity["binding_state"] == "exact"
    assert identity["blockers"] == []
    assert identity["release_authority"] is False
    assert re.fullmatch(r"[0-9a-f]{40}", implementation_commit)

    assert binding["candidate"] == {
        "candidate_id": EXPECTED_CANDIDATE,
        "run_id": EXPECTED_RUN,
        "release_version": EXPECTED_VERSION,
    }
    assert binding["upstream"]["a1_source_commit"] == EXPECTED_A1_SHA
    assert binding["upstream"]["a2_decision_ledger_head_hash"] == EXPECTED_DECISION_HEAD
    assert binding["upstream"]["a2_grades_hash"] == EXPECTED_GRADES_HASH
    assert binding["upstream"]["a2_upstream_decision"] == "block"
    assert binding["upstream"]["a2_release_ready"] is False
    assert binding["a3"]["implementation_commit"] == implementation_commit
    assert binding["a3"]["delivery_status"] == "blocked_by_a2"
    assert binding["a3"]["production_ready"] is False
    assert binding["a3"]["a2_decision_recomputed"] is False

    commit_lookup = subprocess.run(
        ["git", "cat-file", "-e", f"{implementation_commit}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    # actions/checkout uses a depth-one clone. Verify ancestry when the preserved
    # implementation object is available; exact artifact hashes remain mandatory
    # in both full and shallow repositories.
    if commit_lookup.returncode == 0:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", implementation_commit, "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )


def test_m40_05_delivery_stays_blocked_and_does_not_reuse_rc2_live_readbacks() -> None:
    gate = load_json("gate-report.json")
    bundle = load_json("audit-bundle-index.json")
    index = load_json("release-delivery-index.json")
    acceptance = load_json("deployment-acceptance.json")
    golden_path = load_json("golden-path-status.json")

    assert gate["candidate_binding_verification"]["verified"] is True
    assert gate["trusted_release_authority"]["integrity_verified"] is True
    assert gate["trusted_release_authority"]["upstream_decision"] == "block"
    assert gate["release_gate"]["decision"] == "block_release"
    assert gate["github_check_run"]["conclusion"] == "failure"

    artifact_ids = {artifact["id"] for artifact in bundle["bundle_artifacts"]}
    assert {
        "a2_shared_candidate_identity",
        "a2_trusted_spine",
        "a3_shared_candidate_identity",
        "a3_candidate_delivery_binding",
        "runs",
        "grades",
    }.issubset(artifact_ids)
    assert artifact_ids.isdisjoint(
        {
            "github_check_readback",
            "github_pr_comment_readback",
            "github_required_check_proof",
            "github_actions_artifact_readback",
        }
    )
    assert bundle["release"]["candidate_binding_verified"] is True
    assert bundle["release"]["a2_upstream_decision"] == "block"

    assert index["candidate_id"] == EXPECTED_CANDIDATE
    assert index["run_id"] == EXPECTED_RUN
    assert index["release_version"] == EXPECTED_VERSION
    assert index["candidate_binding"]["verified"] is True
    assert index["authority"]["a2_upstream_decision"] == "block"
    assert index["authority"]["a3_recomputed_decision"] is False
    assert index["production_ready"] is False
    assert acceptance["production_accepted"] is False
    assert "a2_release_authority" in acceptance["blocking_check_ids"]
    assert "github_app_installation" in acceptance["blocking_check_ids"]
    assert "required_check_enforcement" in acceptance["blocking_check_ids"]
    assert golden_path["status"] == "blocked_by_a2"
    assert golden_path["production_ready"] is False
