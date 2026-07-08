from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SECRET_RE = re.compile(r"(tp_[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]+)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the A1 fresh-setup readiness matrix.")
    parser.add_argument("--summary-output", default="docs/evidence/private_refs/a1_readiness_summary.json")
    parser.add_argument("--skip-python", action="store_true")
    parser.add_argument("--skip-ts", action="store_true")
    parser.add_argument("--skip-calibration", action="store_true")
    parser.add_argument("--real-readonly", action="store_true", help="Also run the real read-only Ashr API calibrator with max retries 0.")
    args = parser.parse_args(argv)

    results: list[dict[str, Any]] = []
    if not args.skip_python:
        results.append(run_step("python-a1-tests", [sys.executable, "-B", "-m", "pytest", "tests/a1", "-q", "-p", "no:cacheprovider"]))
    if not args.skip_ts:
        results.append(run_step("ts-tests", [npm_command(), "test", "--prefix", "packages/ts/ashr-clone"]))
    if not args.skip_calibration:
        results.append(run_step("calibrator-dry-run", [sys.executable, "-m", "packages.sdk.ashr_clone.calibrate", "--include-mutating", "--allow-paid-media", "--output", "docs/evidence/private_refs/a1_readiness_calibration_dry_run.json"]))
        if args.real_readonly:
            results.append(run_step("calibrator-real-readonly", [sys.executable, "-m", "packages.sdk.ashr_clone.calibrate", "--execute", "--small-batch", "--max-retries", "0", "--limit", "1", "--output", "docs/evidence/private_refs/a1_readiness_calibration_real_readonly.json"]))
    results.append(validate_public_evidence_index())
    results.append(run_step("git-diff-check", ["git", "diff", "--check"]))

    summary = {
        "schema_version": "ashr.clone.a1_readiness.v1",
        "status": "ok" if all(item["status"] == "ok" for item in results) else "failed",
        "env": {"ASHR_API_KEY_present": bool(os.environ.get("ASHR_API_KEY")), "ASHR_LABS_API_KEY_present": bool(os.environ.get("ASHR_LABS_API_KEY"))},
        "results": results,
    }
    output = ROOT / args.summary_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "summary_output": args.summary_output, "steps": len(results)}, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1



def npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"

def run_step(name: str, command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    return {
        "name": name,
        "command": command,
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout_tail": tail(completed.stdout),
        "stderr_tail": tail(completed.stderr),
    }


def validate_public_evidence_index() -> dict[str, Any]:
    path = ROOT / "docs/a1/api_calibration/real_api_evidence_index.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        payload = json.dumps(data, sort_keys=True)
        absolute_paths = [record.get("path") for record in data.get("records", []) if isinstance(record, dict) and (":" in str(record.get("path")) or "\\" in str(record.get("path")))]
        if data.get("schema_version") != "ashr.clone.evidence_index.v1":
            raise ValueError("unexpected evidence index schema_version")
        if int(data.get("total_records", -1)) != len(data.get("records", [])):
            raise ValueError("evidence index total_records does not match records length")
        if SECRET_RE.search(payload):
            raise ValueError("evidence index contains secret-like text")
        if absolute_paths:
            raise ValueError("evidence index contains absolute/local paths")
        return {"name": "public-evidence-index", "status": "ok", "path": path.as_posix(), "total_records": data.get("total_records")}
    except Exception as exc:  # noqa: BLE001 - readiness should return a structured failure.
        return {"name": "public-evidence-index", "status": "failed", "path": path.as_posix(), "error": str(exc)}


def tail(value: str | None, limit: int = 2000) -> str:
    cleaned = SECRET_RE.sub("[redacted]", value or "")
    return cleaned[-limit:]


if __name__ == "__main__":
    raise SystemExit(main())
