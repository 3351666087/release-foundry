from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.release_gate import build_release_gate_report  # noqa: E402


DEFAULT_OUTPUT = Path("fixtures/a2/results/a2_release_gate_report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the A2 PR/release gate report.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    parser.add_argument("--commercial-readiness", default="fixtures/a2/results/a2_commercial_readiness_report.json")
    parser.add_argument("--evidence-readiness", default="fixtures/a2/results/a2_evidence_readiness_report.json")
    parser.add_argument("--calibration-matrix", default="fixtures/a2/results/a2_g3_calibration_matrix.json")
    parser.add_argument("--regression-replay", default="fixtures/a2/results/a2_regression_replay_report.json")
    parser.add_argument("--check", action="store_true", help="Compare generated report with the output path.")
    parser.add_argument("--fail-on-block", action="store_true", help="Return the report exit_code when decision is block or warn.")
    args = parser.parse_args()

    os.chdir(ROOT)
    report = build_release_gate_report(
        _read_json(Path(args.commercial_readiness)),
        _read_json(Path(args.evidence_readiness)),
        _read_json(Path(args.calibration_matrix)),
        _read_json(Path(args.regression_replay)),
    )
    text = json.dumps(report, indent=2) + "\n"
    output = Path(args.output)
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != text:
            print(f"A2 release gate report drift: {output.as_posix()}")
            return 1
        print(f"A2 release gate report matches {output.as_posix()}")
        return report["exit_code"] if args.fail_on_block else 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"wrote {output.as_posix()} decision={report['decision']} risk_score={report['risk_score']}")
    return report["exit_code"] if args.fail_on_block else 0


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path.as_posix()} must contain a JSON object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
