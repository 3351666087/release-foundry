from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RC3 = ROOT / "fixtures" / "a3" / "golden-path" / "rc3"
RECEIPT = RC3 / "a1_candidate_run_receipt.json"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(payload)


def test_m40_rc3_a1_candidate_run_is_recomputable_and_public_safe() -> None:
    receipt = load_json(RECEIPT)
    run_path = ROOT / receipt["evidence"]["run_result"]["path"]
    fixture_path = ROOT / receipt["evidence"]["run_fixture"]["path"]
    archived_cases_path = ROOT / receipt["case_set"]["archived_path"]
    source_cases_path = ROOT / receipt["case_set"]["source_path"]
    run = load_json(run_path)
    archived_cases = load_json(archived_cases_path)["cases"]
    source_cases = load_json(source_cases_path)["cases"]

    assert receipt["schema_version"] == "ashr.clone.a1_candidate_run_receipt.v1"
    assert run["schema_version"] == "ashr.clone.run_result.v1"
    assert sha256_bytes(run_path.read_bytes()) == receipt["evidence"]["run_result"]["sha256"]
    assert sha256_bytes(fixture_path.read_bytes()) == receipt["evidence"]["run_fixture"]["sha256"]
    assert archived_cases == source_cases
    assert stable_hash(archived_cases) == receipt["case_set"]["sha256"]

    binding = receipt["candidate_binding"]
    assert run["metadata"]["candidate_binding"] == binding
    assert binding["candidate_id"] == "a3-golden-agent@0.2.0-rc.3"
    assert binding["git_sha"] == "1d292047e991995fdf52f0545ffff410ee19a171"
    assert binding["candidate_source_commit"] == binding["git_sha"]
    assert binding["source_tree_clean"] is True
    assert binding["case_set_sha256"] == receipt["case_set"]["sha256"]

    summary = receipt["run"]
    for field in (
        "run_id",
        "dataset_id",
        "runner_id",
        "status",
        "total_cases",
        "passed",
        "failed",
        "errored",
        "timed_out",
        "trace_completeness",
    ):
        assert run[field] == summary[field]
    assert summary["status"] == "passed"
    assert summary["passed"] == summary["total_cases"] == 3
    assert summary["failed"] == summary["errored"] == summary["timed_out"] == 0
    assert summary["trace_completeness"] == 1

    tool_names = [
        call["name"]
        for case in run["cases"]
        for call in case["agent_output"]["tool_calls"]
    ]
    assert tool_names == ["web.search", "media.fetch", "image.view", "media.classify"]
    assert summary["total_tool_calls"] == len(tool_names) == 4
    assert all(case["status"] == "passed" for case in run["cases"])
    assert all(len(case["observations"]) == 2 for case in run["cases"])

    expected_hash_payload = {
        "schema_version": "ashr.clone.a1_candidate_evidence_payload.v1",
        "candidate_id": binding["candidate_id"],
        "git_sha": binding["git_sha"],
        "run_id": run["run_id"],
        "run_result_sha256": receipt["evidence"]["run_result"]["sha256"],
        "run_fixture_sha256": receipt["evidence"]["run_fixture"]["sha256"],
        "case_set_sha256": receipt["case_set"]["sha256"],
    }
    assert receipt["hash_payload"] == expected_hash_payload
    assert receipt["evidence_bundle_hash"] == stable_hash(expected_hash_payload)

    assert receipt["authority"] == {
        "release_authority": False,
        "a2_decision_generated": False,
        "a3_delivery_generated": False,
        "next_owner": "A2",
        "next_action": "Generate a Trusted Spine and Decision Ledger for this exact candidate, run, source commit, and evidence bundle hash.",
    }
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (RECEIPT, run_path, fixture_path, archived_cases_path)
    )
    assert re.search(r"sk-[A-Za-z0-9_-]{8,}", public_text) is None
    assert re.search(r"Bearer\s+[A-Za-z0-9._-]+", public_text, re.IGNORECASE) is None
    assert "ASHR_API_KEY=" not in public_text
