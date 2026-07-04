from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.coverage import build_coverage_report  # noqa: E402
from services.judge.runner import grade_run, grade_runs  # noqa: E402


DEFAULT_PACK = Path("packages/scenarios/a2_g3_full_pack.json")
DEFAULT_GOLDEN = Path("fixtures/golden/a2_g2_golden_cases.json")
DEFAULT_RUN_DIR = Path("fixtures/a2/runs")
DEFAULT_RESULT_DIR = Path("fixtures/a2/results")
DEFAULT_GRADE_REPORT = DEFAULT_RESULT_DIR / "a2_g3_grade_results.json"
DEFAULT_COVERAGE_REPORT = DEFAULT_RESULT_DIR / "a2_g3_coverage_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate or check deterministic A2 judge and coverage fixtures."
    )
    parser.add_argument("--check", action="store_true", help="Compare generated output with committed files.")
    parser.add_argument("--write", action="store_true", help="Write generated output. This is the default mode.")
    parser.add_argument("--pack", default=DEFAULT_PACK.as_posix())
    parser.add_argument("--golden", default=DEFAULT_GOLDEN.as_posix())
    parser.add_argument("--run-dir", default=DEFAULT_RUN_DIR.as_posix())
    parser.add_argument("--result-dir", default=DEFAULT_RESULT_DIR.as_posix())
    parser.add_argument("--grade-report", default=DEFAULT_GRADE_REPORT.as_posix())
    parser.add_argument("--coverage-report", default=DEFAULT_COVERAGE_REPORT.as_posix())
    args = parser.parse_args()

    if args.check and args.write:
        parser.error("--check and --write cannot be used together.")

    os.chdir(ROOT)
    outputs = generate_outputs(
        pack_path=Path(args.pack),
        golden_path=Path(args.golden),
        run_dir=Path(args.run_dir),
        result_dir=Path(args.result_dir),
        grade_report_path=Path(args.grade_report),
        coverage_report_path=Path(args.coverage_report),
    )

    if args.check:
        return check_outputs(outputs)

    write_outputs(outputs)
    print(f"wrote {len(outputs)} A2 generated fixture files")
    return 0


def generate_outputs(
    *,
    pack_path: Path,
    golden_path: Path,
    run_dir: Path,
    result_dir: Path,
    grade_report_path: Path,
    coverage_report_path: Path,
) -> dict[Path, dict[str, Any]]:
    run_fixtures = load_run_fixtures(run_dir)
    outputs: dict[Path, dict[str, Any]] = {}

    for fixture_path, fixture in run_fixtures:
        outputs[result_dir / f"{fixture_path.stem}_grade.json"] = grade_run(
            fixture["scenario_id"],
            fixture.get("run", fixture),
            pack_path=pack_path,
            case_id=fixture.get("case_id"),
        )

    fixture_payloads = [fixture for _, fixture in run_fixtures]
    outputs[grade_report_path] = grade_runs(
        fixture_payloads,
        pack_path=pack_path,
        report_id="a2_g3_grade_results",
        dataset_id="a2-g3-calibration",
    )
    outputs[coverage_report_path] = build_coverage_report(
        pack_path=pack_path,
        golden_path=golden_path,
        run_dir=run_dir,
    )
    return outputs


def load_run_fixtures(run_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    fixtures = []
    for path in sorted(run_dir.glob("*.json")):
        fixtures.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return fixtures


def check_outputs(outputs: dict[Path, dict[str, Any]]) -> int:
    drifted = []
    missing = []
    for path, payload in outputs.items():
        generated = json_text(payload)
        if not path.exists():
            missing.append(path)
            continue
        if path.read_text(encoding="utf-8") != generated:
            drifted.append(path)

    for path in missing:
        print(f"missing generated fixture: {path.as_posix()}")
    for path in drifted:
        print(f"generated fixture drift: {path.as_posix()}")
    if missing or drifted:
        print("run python scripts/a2_regenerate_fixtures.py --write to refresh A2 generated fixtures")
        return 1

    print(f"all {len(outputs)} A2 generated fixture files match committed output")
    return 0


def write_outputs(outputs: dict[Path, dict[str, Any]]) -> None:
    for path, payload in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_text(payload), encoding="utf-8")


def json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
