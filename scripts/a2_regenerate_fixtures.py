from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.batch_plan import build_batch_plan_report  # noqa: E402
from services.judge.calibration import build_calibration_matrix  # noqa: E402
from services.judge.casebook import build_case_book_report  # noqa: E402
from services.judge.coverage import build_coverage_report  # noqa: E402
from services.judge.evidence_readiness import build_evidence_readiness_report  # noqa: E402
from services.judge.readiness import build_commercial_readiness_report  # noqa: E402
from services.judge.regression_replay import build_regression_replay_report  # noqa: E402
from services.judge.runner import grade_run, grade_runs  # noqa: E402
from services.judge.sdk_parity import build_sdk_parity_report  # noqa: E402
from services.judge.semantic_harness import build_semantic_harness_report  # noqa: E402


DEFAULT_PACK = Path("packages/scenarios/a2_g3_full_pack.json")
DEFAULT_GOLDEN = Path("fixtures/golden/a2_g2_golden_cases.json")
DEFAULT_RUN_DIR = Path("fixtures/a2/runs")
DEFAULT_RESULT_DIR = Path("fixtures/a2/results")
DEFAULT_GRADE_REPORT = DEFAULT_RESULT_DIR / "a2_g3_grade_results.json"
DEFAULT_COVERAGE_REPORT = DEFAULT_RESULT_DIR / "a2_g3_coverage_report.json"
DEFAULT_CALIBRATION_OBSERVATIONS = Path("fixtures/a2/calibration/a2_g3_calibration_observations.json")
DEFAULT_CALIBRATION_MATRIX = DEFAULT_RESULT_DIR / "a2_g3_calibration_matrix.json"
DEFAULT_COMMERCIAL_READINESS = DEFAULT_RESULT_DIR / "a2_commercial_readiness_report.json"
DEFAULT_CASE_BOOK = DEFAULT_RESULT_DIR / "a2_case_book.json"
DEFAULT_SDK_PARITY = DEFAULT_RESULT_DIR / "a2_sdk_parity_report.json"
DEFAULT_BATCH_PLAN = DEFAULT_RESULT_DIR / "a2_batch_plan_report.json"
DEFAULT_SEMANTIC_HARNESS = DEFAULT_RESULT_DIR / "a2_semantic_harness_report.json"
DEFAULT_REGRESSION_REPLAY = DEFAULT_RESULT_DIR / "a2_regression_replay_report.json"
DEFAULT_EVIDENCE_READINESS = DEFAULT_RESULT_DIR / "a2_evidence_readiness_report.json"


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
    parser.add_argument("--calibration-observations", default=DEFAULT_CALIBRATION_OBSERVATIONS.as_posix())
    parser.add_argument("--calibration-matrix", default=DEFAULT_CALIBRATION_MATRIX.as_posix())
    parser.add_argument("--commercial-readiness", default=DEFAULT_COMMERCIAL_READINESS.as_posix())
    parser.add_argument("--case-book", default=DEFAULT_CASE_BOOK.as_posix())
    parser.add_argument("--sdk-parity", default=DEFAULT_SDK_PARITY.as_posix())
    parser.add_argument("--batch-plan", default=DEFAULT_BATCH_PLAN.as_posix())
    parser.add_argument("--semantic-harness", default=DEFAULT_SEMANTIC_HARNESS.as_posix())
    parser.add_argument("--regression-replay", default=DEFAULT_REGRESSION_REPLAY.as_posix())
    parser.add_argument("--evidence-readiness", default=DEFAULT_EVIDENCE_READINESS.as_posix())
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
        calibration_observations_path=Path(args.calibration_observations),
        calibration_matrix_path=Path(args.calibration_matrix),
        commercial_readiness_path=Path(args.commercial_readiness),
        case_book_path=Path(args.case_book),
        sdk_parity_path=Path(args.sdk_parity),
        batch_plan_path=Path(args.batch_plan),
        semantic_harness_path=Path(args.semantic_harness),
        regression_replay_path=Path(args.regression_replay),
        evidence_readiness_path=Path(args.evidence_readiness),
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
    calibration_observations_path: Path,
    calibration_matrix_path: Path,
    commercial_readiness_path: Path,
    case_book_path: Path,
    sdk_parity_path: Path,
    batch_plan_path: Path,
    semantic_harness_path: Path,
    regression_replay_path: Path,
    evidence_readiness_path: Path,
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
    coverage_report = build_coverage_report(
        pack_path=pack_path,
        golden_path=golden_path,
        run_dir=run_dir,
    )
    outputs[coverage_report_path] = coverage_report
    calibration_matrix = build_calibration_matrix(
        pack_path=pack_path,
        run_dir=run_dir,
        observations_path=calibration_observations_path,
    )
    outputs[calibration_matrix_path] = calibration_matrix
    case_book = build_case_book_report(calibration_matrix)
    outputs[case_book_path] = case_book
    regression_replay = build_regression_replay_report(
        calibration_matrix,
        case_book,
        pack_path=pack_path,
    )
    outputs[regression_replay_path] = regression_replay
    sdk_parity = build_sdk_parity_report(pack_path=pack_path)
    outputs[sdk_parity_path] = sdk_parity
    semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
    outputs[semantic_harness_path] = semantic_harness
    batch_plan = build_batch_plan_report(
        coverage_report=coverage_report,
        calibration_matrix=calibration_matrix,
        case_book_report=case_book,
        sdk_parity_report=sdk_parity,
        semantic_harness_report=semantic_harness,
        regression_replay_report=regression_replay,
    )
    outputs[batch_plan_path] = batch_plan
    evidence_readiness = build_evidence_readiness_report(
        calibration_matrix=calibration_matrix,
        batch_plan_report=batch_plan,
        semantic_harness_report=semantic_harness,
    )
    outputs[evidence_readiness_path] = evidence_readiness
    outputs[commercial_readiness_path] = build_commercial_readiness_report(
        coverage_report=coverage_report,
        calibration_matrix=calibration_matrix,
        case_book_report=case_book,
        sdk_parity_report=sdk_parity,
        batch_plan_report=batch_plan,
        semantic_harness_report=semantic_harness,
        regression_replay_report=regression_replay,
        evidence_readiness_report=evidence_readiness,
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
