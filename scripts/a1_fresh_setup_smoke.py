from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "docs" / "a1" / "evidence" / "local_agent_cases_30.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the A1 Python SDK/runner smoke without a configured PYTHONPATH."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--keep-output", type=Path)
    return parser


def run_smoke(cases: Path, output: Path) -> dict[str, object]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    command = [
        sys.executable,
        "-B",
        "-m",
        "services.runner.cli",
        "--input",
        str(cases.resolve()),
        "--output",
        str(output.resolve()),
        "--agent",
        "examples.agents.mock_agent:RespondingMockAgent",
        "--dataset-id",
        "a1-fresh-setup",
        "--runner-id",
        "a1-fresh-setup-smoke",
        "--max-workers",
        "4",
        "--timeout",
        "5",
        "--fail-on-case-failure",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "fresh setup runner failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    if payload.get("total_cases") != 30 or payload.get("passed") != 30:
        raise RuntimeError("fresh setup runner did not pass all 30 cases")
    if int(payload.get("max_workers", 0)) < 4:
        raise RuntimeError("fresh setup runner used fewer than four workers")
    if float(payload.get("trace_completeness", 0.0)) < 0.95:
        raise RuntimeError("fresh setup trace completeness is below 95%")
    return {
        "status": "passed",
        "total_cases": payload["total_cases"],
        "passed": payload["passed"],
        "max_workers": payload["max_workers"],
        "trace_completeness": payload["trace_completeness"],
        "pythonpath_required": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = args.cases if args.cases.is_absolute() else ROOT / args.cases
    if args.keep_output:
        output = args.keep_output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        summary = run_smoke(cases, output)
    else:
        with tempfile.TemporaryDirectory(prefix="ashr-a1-fresh-setup-") as temp_dir:
            summary = run_smoke(cases, Path(temp_dir) / "run.json")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
