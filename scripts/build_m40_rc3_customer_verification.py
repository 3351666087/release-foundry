#!/usr/bin/env python3
"""Build or verify the M40-06 rc.3 Customer Agent Release packet."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUTPUT_ROOT = ROOT / "fixtures" / "releases" / "m40-06"
CUSTOMER_NAME = "agent-release-demo-a3-golden-agent-0.2.0-rc.3"
CUSTOMER_ROOT = OUTPUT_ROOT / CUSTOMER_NAME
RECEIPT_PATH = OUTPUT_ROOT / "customer-verification-receipt.json"
EXPECTED = {
    "candidate_id": "a3-golden-agent@0.2.0-rc.3",
    "run_id": "a3-golden-20260720-003",
    "release_version": "0.2.0-rc.3",
    "a1_source_commit": "1d292047e991995fdf52f0545ffff410ee19a171",
    "a2_authority_commit": "d3529c356e49ce8502c050f0dad44020031ee0dd",
    "a3_implementation_commit": "a0b427257c5cd80fbe3394b4a406fa21f50bae37",
    "a2_decision_head": "sha256:af84d7e9e3143f4da06341f2e20f3402c8f44ed5efc8221b18c8ef2869747a4e",
    "a2_grades_hash": "sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304",
}
REQUIRED_BLOCKERS = {
    "product_release_not_approved",
    "a2_release_blocked",
    "a2_release_not_ready",
    "a3_gate_blocked",
    "a3_delivery_not_ready",
    "a3_ci_tested_sha_missing",
    "human_approval_missing",
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}", re.IGNORECASE),
)


def build(*, generated_at: str, source_commit: str) -> dict[str, Any]:
    from services.release_distribution import build_dual_release_candidates

    if source_commit != git("rev-parse", "HEAD"):
        raise ValueError("source commit must match HEAD")
    if git("status", "--porcelain"):
        raise ValueError("M40-06 evidence must be generated from a clean worktree")
    with tempfile.TemporaryDirectory(prefix="ashr-m40-06-") as temporary:
        temporary_root = Path(temporary)
        index = build_dual_release_candidates(
            ROOT,
            temporary_root,
            product_version="1.0.0-rc.1",
            agent_version="0.2.0-rc.3",
            agent_org="demo",
            agent_name="a3-golden-agent",
            source_commit=source_commit,
            generated_at=generated_at,
            allow_dirty=False,
        )
        source_customer = temporary_root / index["customer_agent_release"]["release_root"]
        reset_output_directory(CUSTOMER_ROOT)
        shutil.copytree(source_customer, CUSTOMER_ROOT)

    verification = verify_packet()
    manifest_path = CUSTOMER_ROOT / "manifest.json"
    verification_path = CUSTOMER_ROOT / "verification.json"
    receipt = {
        "schema_version": "ashr.m40_06_customer_verification_receipt.v1",
        "generated_at": generated_at,
        "source": {
            "repository": "https://github.com/3351666087/ashr-codex-factory",
            "release_package_commit": source_commit,
            "clean": True,
        },
        "customer_release": {
            "release_id": verification["agent_release_id"],
            "decision": verification["decision"],
            "manifest_sha256": sha256_file(manifest_path),
            "verification_sha256": sha256_file(verification_path),
        },
        "identity_alignment": verification["identity_alignment"],
        "authoritative_blockers": verification["blocking_reasons"],
        "evidence": {
            "manifest": file_ref(manifest_path),
            "verification": file_ref(verification_path),
        },
        "safety": {
            "a2_decision_recomputed": False,
            "no_go_relabelled_as_go": False,
            "human_approval_invented": False,
            "production_authority_claimed": False,
            "secrets_included": False,
        },
    }
    write_json(RECEIPT_PATH, receipt)
    return check()


def check() -> dict[str, Any]:
    from services.customer_release import verify_customer_agent_release_manifest

    manifest_path = CUSTOMER_ROOT / "manifest.json"
    verification_path = CUSTOMER_ROOT / "verification.json"
    receipt = read_json(RECEIPT_PATH)
    committed_verification = read_json(verification_path)
    recomputed = verify_customer_agent_release_manifest(
        manifest_path,
        release_root=CUSTOMER_ROOT,
    )
    if recomputed != committed_verification:
        raise ValueError("committed Customer verification differs from recomputation")
    alignment = recomputed.get("identity_alignment", {})
    assert_equal(alignment.get("status"), "passed", "identity alignment")
    assert_equal(alignment.get("mismatch_reasons"), [], "identity mismatch reasons")
    for field, expected in (
        ("candidate_id", EXPECTED["candidate_id"]),
        ("run_id", EXPECTED["run_id"]),
        ("evidence_release_version", EXPECTED["release_version"]),
        ("a1_candidate_source_commit", EXPECTED["a1_source_commit"]),
        ("a2_authority_commit", EXPECTED["a2_authority_commit"]),
        ("a3_implementation_commit", EXPECTED["a3_implementation_commit"]),
        ("a2_decision_ledger_head_hash", EXPECTED["a2_decision_head"]),
        ("a2_grades_hash", EXPECTED["a2_grades_hash"]),
    ):
        assert_equal(alignment.get(field), expected, field)
    assert_equal(recomputed.get("decision"), "block_customer_agent_release", "Customer decision")
    assert_equal(recomputed.get("product_release_decision"), "block_product_release", "Product decision")
    assert_equal(recomputed.get("a2_authoritative_decision"), "block", "A2 decision")
    assert_equal(recomputed.get("a3_recomputed_a2_decision"), False, "A3 recomputation marker")
    blockers = set(recomputed.get("blocking_reasons", []))
    missing_blockers = sorted(REQUIRED_BLOCKERS - blockers)
    if missing_blockers:
        raise ValueError(f"required fail-closed blockers are missing: {missing_blockers}")
    if receipt.get("customer_release", {}).get("manifest_sha256") != sha256_file(manifest_path):
        raise ValueError("receipt manifest hash mismatch")
    if receipt.get("customer_release", {}).get("verification_sha256") != sha256_file(verification_path):
        raise ValueError("receipt verification hash mismatch")
    scan_public_packet()
    return {
        "schema_version": "ashr.m40_06_customer_verification_check.v1",
        "status": "passed",
        "release_package_commit": alignment.get("release_package_commit"),
        "candidate_id": alignment.get("candidate_id"),
        "run_id": alignment.get("run_id"),
        "release_version": alignment.get("evidence_release_version"),
        "identity_alignment": "passed",
        "identity_mismatch_reasons": [],
        "customer_decision": recomputed.get("decision"),
        "product_decision": recomputed.get("product_release_decision"),
        "a2_decision": recomputed.get("a2_authoritative_decision"),
        "blocking_reasons": sorted(blockers),
        "safety": receipt.get("safety"),
    }


def verify_packet() -> dict[str, Any]:
    from services.customer_release import verify_customer_agent_release_manifest

    manifest_path = CUSTOMER_ROOT / "manifest.json"
    verification = verify_customer_agent_release_manifest(
        manifest_path,
        release_root=CUSTOMER_ROOT,
    )
    write_json(CUSTOMER_ROOT / "verification.json", verification)
    return verification


def scan_public_packet() -> None:
    for path in sorted(CUSTOMER_ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                raise ValueError(f"secret-like material found in {path.relative_to(ROOT)}")


def reset_output_directory(path: Path) -> None:
    resolved_root = OUTPUT_ROOT.resolve()
    resolved = path.resolve()
    if resolved.parent != resolved_root:
        raise ValueError("refusing to replace output outside the M40-06 fixture root")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved_root.mkdir(parents=True, exist_ok=True)


def file_ref(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, received {actual!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source-commit")
    parser.add_argument("--generated-at")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        result = check()
    else:
        result = build(
            generated_at=args.generated_at
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source_commit=args.source_commit or git("rev-parse", "HEAD"),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
