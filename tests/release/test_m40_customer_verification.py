from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = (
    ROOT
    / "fixtures"
    / "releases"
    / "m40-06"
    / "agent-release-demo-a3-golden-agent-0.2.0-rc.3"
)
RECEIPT = ROOT / "fixtures" / "releases" / "m40-06" / "customer-verification-receipt.json"
EXPECTED_PACKAGE_COMMIT = "718f9b0512138382d8562737ecf4e99e72a998e1"
EXPECTED_BLOCKERS = {
    "a2_release_blocked",
    "a2_release_not_ready",
    "a3_ci_tested_sha_missing",
    "a3_delivery_not_ready",
    "a3_gate_blocked",
    "human_approval_missing",
    "product_release_not_approved",
}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m40_06_committed_customer_packet_recomputes_without_identity_mismatch() -> None:
    completed = subprocess.run(
        ["python", "scripts/build_m40_rc3_customer_verification.py", "--check", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert completed.stderr == ""
    assert result["status"] == "passed"
    assert result["release_package_commit"] == EXPECTED_PACKAGE_COMMIT
    assert result["candidate_id"] == "a3-golden-agent@0.2.0-rc.3"
    assert result["run_id"] == "a3-golden-20260720-003"
    assert result["release_version"] == "0.2.0-rc.3"
    assert result["identity_alignment"] == "passed"
    assert result["identity_mismatch_reasons"] == []
    assert result["customer_decision"] == "block_customer_agent_release"
    assert result["product_decision"] == "block_product_release"
    assert result["a2_decision"] == "block"
    assert set(result["blocking_reasons"]) == EXPECTED_BLOCKERS
    assert result["safety"] == {
        "a2_decision_recomputed": False,
        "human_approval_invented": False,
        "no_go_relabelled_as_go": False,
        "production_authority_claimed": False,
        "secrets_included": False,
    }


def test_m40_06_manifest_separates_package_and_lane_commits() -> None:
    manifest = load_json(PACKET_ROOT / "manifest.json")
    verification = load_json(PACKET_ROOT / "verification.json")
    receipt = load_json(RECEIPT)

    assert manifest["source"]["commit_sha"] == EXPECTED_PACKAGE_COMMIT
    assert manifest["source"]["dirty"] is False
    assert manifest["candidate"] == {
        "agent_id": "a3-golden-agent",
        "candidate_id": "a3-golden-agent@0.2.0-rc.3",
        "evidence_release_version": "0.2.0-rc.3",
        "run_id": "a3-golden-20260720-003",
        "source_commit": "1d292047e991995fdf52f0545ffff410ee19a171",
        "version": "0.2.0-rc.3",
    }
    assert manifest["lane_bindings"] == {
        "release_package_commit": EXPECTED_PACKAGE_COMMIT,
        "a1_candidate_source_commit": "1d292047e991995fdf52f0545ffff410ee19a171",
        "a1_evidence_bundle_hash": "sha256:0b4fb982ccc5a25a54c8c8ea8744285296502bb6be3113d5220af7f3340e3d6b",
        "a2_authority_commit": "d3529c356e49ce8502c050f0dad44020031ee0dd",
        "a2_decision_ledger_head_hash": "sha256:af84d7e9e3143f4da06341f2e20f3402c8f44ed5efc8221b18c8ef2869747a4e",
        "a2_grades_hash": "sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304",
        "a3_implementation_commit": "a0b427257c5cd80fbe3394b4a406fa21f50bae37",
    }
    assert verification["identity_alignment"]["status"] == "passed"
    assert verification["identity_alignment"]["mismatch_reasons"] == []
    assert receipt["customer_release"]["manifest_sha256"] == sha256_file(PACKET_ROOT / "manifest.json")
    assert receipt["customer_release"]["verification_sha256"] == sha256_file(PACKET_ROOT / "verification.json")
    assert re.fullmatch(r"[0-9a-f]{40}", EXPECTED_PACKAGE_COMMIT)

    commit_lookup = subprocess.run(
        ["git", "cat-file", "-e", f"{EXPECTED_PACKAGE_COMMIT}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if commit_lookup.returncode == 0:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", EXPECTED_PACKAGE_COMMIT, "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
