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
from services.judge.ashr_collection import build_ashr_grading_collection_packet  # noqa: E402
from services.judge.calibration import build_calibration_matrix  # noqa: E402
from services.judge.casebook import build_case_book_report  # noqa: E402
from services.judge.coverage import build_coverage_report  # noqa: E402
from services.judge.evidence_readiness import build_evidence_readiness_report  # noqa: E402
from services.judge.incident_regression import build_incident_regression_candidate_report  # noqa: E402
from services.judge.readiness import build_commercial_readiness_report  # noqa: E402
from services.judge.release_gate import build_release_gate_report  # noqa: E402
from services.judge.regression_promotion import build_regression_promotion_queue_report  # noqa: E402
from services.judge.regression_replay import build_regression_replay_report  # noqa: E402
from services.judge.result_persistence import build_result_persistence_manifest  # noqa: E402
from services.judge.runner import grade_run, grade_runs  # noqa: E402
from services.judge.saas_control_plane import build_saas_control_plane_report  # noqa: E402
from services.judge.scenario_selection import build_scenario_selection_report  # noqa: E402
from services.judge.sdk_parity import build_sdk_parity_report  # noqa: E402
from services.judge.semantic_collection import build_semantic_judge_collection_packet  # noqa: E402
from services.judge.semantic_harness import build_semantic_harness_report  # noqa: E402
from services.judge.unblock_checklist import build_release_unblock_checklist  # noqa: E402
from services.judge.versioning import build_judge_version_registry  # noqa: E402


DEFAULT_PACK = Path("packages/scenarios/a2_g3_full_pack.json")
DEFAULT_GOLDEN = Path("fixtures/golden/a2_g2_golden_cases.json")
DEFAULT_RUN_DIR = Path("fixtures/a2/runs")
DEFAULT_RESULT_DIR = Path("fixtures/a2/results")
DEFAULT_GRADE_REPORT = DEFAULT_RESULT_DIR / "a2_g3_grade_results.json"
DEFAULT_COVERAGE_REPORT = DEFAULT_RESULT_DIR / "a2_g3_coverage_report.json"
DEFAULT_CALIBRATION_OBSERVATIONS = Path("fixtures/a2/calibration/a2_g3_calibration_observations.json")
DEFAULT_ASHR_GRADING_COLLECTION_PACKET = Path("fixtures/a2/calibration/a2_ashr_grading_collection_packet.json")
DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET = Path("fixtures/a2/calibration/a2_semantic_judge_collection_packet.json")
DEFAULT_CALIBRATION_MATRIX = DEFAULT_RESULT_DIR / "a2_g3_calibration_matrix.json"
DEFAULT_COMMERCIAL_READINESS = DEFAULT_RESULT_DIR / "a2_commercial_readiness_report.json"
DEFAULT_CASE_BOOK = DEFAULT_RESULT_DIR / "a2_case_book.json"
DEFAULT_SDK_PARITY = DEFAULT_RESULT_DIR / "a2_sdk_parity_report.json"
DEFAULT_BATCH_PLAN = DEFAULT_RESULT_DIR / "a2_batch_plan_report.json"
DEFAULT_SEMANTIC_HARNESS = DEFAULT_RESULT_DIR / "a2_semantic_harness_report.json"
DEFAULT_REGRESSION_REPLAY = DEFAULT_RESULT_DIR / "a2_regression_replay_report.json"
DEFAULT_INCIDENT_SUMMARY = Path("fixtures/a2/incidents/a2_prod_incident_summary.json")
DEFAULT_INCIDENT_REGRESSION_CANDIDATES = DEFAULT_RESULT_DIR / "a2_incident_regression_candidates.json"
DEFAULT_REGRESSION_PROMOTION_QUEUE = DEFAULT_RESULT_DIR / "a2_regression_promotion_queue.json"
DEFAULT_EVIDENCE_READINESS = DEFAULT_RESULT_DIR / "a2_evidence_readiness_report.json"
DEFAULT_RELEASE_GATE = DEFAULT_RESULT_DIR / "a2_release_gate_report.json"
DEFAULT_RELEASE_UNBLOCK_CHECKLIST = DEFAULT_RESULT_DIR / "a2_release_unblock_checklist.json"
DEFAULT_A1_EVIDENCE_INDEX = Path("docs/a1/api_calibration/real_api_evidence_index.json")
DEFAULT_SCENARIO_SELECTION_PROFILE = Path("fixtures/a2/config/a2_saas_project_selection_profile.json")
DEFAULT_SCENARIO_SELECTION = DEFAULT_RESULT_DIR / "a2_scenario_selection_report.json"
DEFAULT_RESULT_PERSISTENCE_MANIFEST = DEFAULT_RESULT_DIR / "a2_result_persistence_manifest.json"
DEFAULT_RELEASE_POLICY_CONFIG = Path("fixtures/a2/config/release_policies.json")
DEFAULT_SAAS_CONTROL_PLANE = DEFAULT_RESULT_DIR / "a2_saas_control_plane_report.json"
DEFAULT_JUDGE_VERSIONS = DEFAULT_RESULT_DIR / "a2_judge_versions.json"


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
    parser.add_argument("--ashr-grading-collection-packet", default=DEFAULT_ASHR_GRADING_COLLECTION_PACKET.as_posix())
    parser.add_argument("--semantic-judge-collection-packet", default=DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET.as_posix())
    parser.add_argument("--calibration-matrix", default=DEFAULT_CALIBRATION_MATRIX.as_posix())
    parser.add_argument("--commercial-readiness", default=DEFAULT_COMMERCIAL_READINESS.as_posix())
    parser.add_argument("--case-book", default=DEFAULT_CASE_BOOK.as_posix())
    parser.add_argument("--sdk-parity", default=DEFAULT_SDK_PARITY.as_posix())
    parser.add_argument("--batch-plan", default=DEFAULT_BATCH_PLAN.as_posix())
    parser.add_argument("--semantic-harness", default=DEFAULT_SEMANTIC_HARNESS.as_posix())
    parser.add_argument("--regression-replay", default=DEFAULT_REGRESSION_REPLAY.as_posix())
    parser.add_argument("--incident-summary", default=DEFAULT_INCIDENT_SUMMARY.as_posix())
    parser.add_argument("--incident-regression-candidates", default=DEFAULT_INCIDENT_REGRESSION_CANDIDATES.as_posix())
    parser.add_argument("--regression-promotion-queue", default=DEFAULT_REGRESSION_PROMOTION_QUEUE.as_posix())
    parser.add_argument("--evidence-readiness", default=DEFAULT_EVIDENCE_READINESS.as_posix())
    parser.add_argument("--release-gate", default=DEFAULT_RELEASE_GATE.as_posix())
    parser.add_argument("--release-unblock-checklist", default=DEFAULT_RELEASE_UNBLOCK_CHECKLIST.as_posix())
    parser.add_argument("--a1-evidence-index", default=DEFAULT_A1_EVIDENCE_INDEX.as_posix())
    parser.add_argument("--scenario-selection-profile", default=DEFAULT_SCENARIO_SELECTION_PROFILE.as_posix())
    parser.add_argument("--scenario-selection", default=DEFAULT_SCENARIO_SELECTION.as_posix())
    parser.add_argument("--result-persistence-manifest", default=DEFAULT_RESULT_PERSISTENCE_MANIFEST.as_posix())
    parser.add_argument("--release-policy-config", default=DEFAULT_RELEASE_POLICY_CONFIG.as_posix())
    parser.add_argument("--saas-control-plane", default=DEFAULT_SAAS_CONTROL_PLANE.as_posix())
    parser.add_argument("--judge-versions", default=DEFAULT_JUDGE_VERSIONS.as_posix())
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
        ashr_grading_collection_packet_path=Path(args.ashr_grading_collection_packet),
        semantic_judge_collection_packet_path=Path(args.semantic_judge_collection_packet),
        calibration_matrix_path=Path(args.calibration_matrix),
        commercial_readiness_path=Path(args.commercial_readiness),
        case_book_path=Path(args.case_book),
        sdk_parity_path=Path(args.sdk_parity),
        batch_plan_path=Path(args.batch_plan),
        semantic_harness_path=Path(args.semantic_harness),
        regression_replay_path=Path(args.regression_replay),
        incident_summary_path=Path(args.incident_summary),
        incident_regression_candidates_path=Path(args.incident_regression_candidates),
        regression_promotion_queue_path=Path(args.regression_promotion_queue),
        evidence_readiness_path=Path(args.evidence_readiness),
        release_gate_path=Path(args.release_gate),
        release_unblock_checklist_path=Path(args.release_unblock_checklist),
        a1_evidence_index_path=Path(args.a1_evidence_index),
        scenario_selection_profile_path=Path(args.scenario_selection_profile),
        scenario_selection_path=Path(args.scenario_selection),
        result_persistence_manifest_path=Path(args.result_persistence_manifest),
        release_policy_config_path=Path(args.release_policy_config),
        saas_control_plane_path=Path(args.saas_control_plane),
        judge_versions_path=Path(args.judge_versions),
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
    ashr_grading_collection_packet_path: Path,
    semantic_judge_collection_packet_path: Path,
    calibration_matrix_path: Path,
    commercial_readiness_path: Path,
    case_book_path: Path,
    sdk_parity_path: Path,
    batch_plan_path: Path,
    semantic_harness_path: Path,
    regression_replay_path: Path,
    incident_summary_path: Path,
    incident_regression_candidates_path: Path,
    regression_promotion_queue_path: Path,
    evidence_readiness_path: Path,
    release_gate_path: Path,
    release_unblock_checklist_path: Path,
    a1_evidence_index_path: Path,
    scenario_selection_profile_path: Path,
    scenario_selection_path: Path,
    result_persistence_manifest_path: Path,
    release_policy_config_path: Path,
    saas_control_plane_path: Path,
    judge_versions_path: Path,
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
    outputs[ashr_grading_collection_packet_path] = build_ashr_grading_collection_packet(
        pack_path=pack_path,
        run_dir=run_dir,
        observations_path=calibration_observations_path,
    )
    outputs[semantic_judge_collection_packet_path] = build_semantic_judge_collection_packet(
        pack_path=pack_path,
        run_dir=run_dir,
        observations_path=calibration_observations_path,
    )
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
    incident_regression_candidates = build_incident_regression_candidate_report(
        incident_summary_path,
        pack_path=pack_path,
    )
    outputs[incident_regression_candidates_path] = incident_regression_candidates
    outputs[regression_promotion_queue_path] = build_regression_promotion_queue_report(
        case_book,
        incident_regression_candidates,
        regression_replay,
    )
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
    commercial_readiness = build_commercial_readiness_report(
        coverage_report=coverage_report,
        calibration_matrix=calibration_matrix,
        case_book_report=case_book,
        sdk_parity_report=sdk_parity,
        batch_plan_report=batch_plan,
        semantic_harness_report=semantic_harness,
        regression_replay_report=regression_replay,
        evidence_readiness_report=evidence_readiness,
    )
    outputs[commercial_readiness_path] = commercial_readiness
    scenario_selection_profile = json.loads(scenario_selection_profile_path.read_text(encoding="utf-8"))
    scenario_selection = build_scenario_selection_report(
        scenario_selection_profile,
        pack_path=pack_path,
    )
    outputs[scenario_selection_path] = scenario_selection
    release_gate = build_release_gate_report(
        commercial_readiness,
        evidence_readiness,
        calibration_matrix,
        regression_replay,
        scenario_selection,
        _load_optional_object(a1_evidence_index_path),
    )
    outputs[release_gate_path] = release_gate
    outputs[release_unblock_checklist_path] = build_release_unblock_checklist(
        release_gate,
        evidence_readiness,
        regression_replay,
        outputs[regression_promotion_queue_path],
    )
    scenario_pack = json.loads(pack_path.read_text(encoding="utf-8"))
    result_persistence_manifest = build_result_persistence_manifest(
        outputs[grade_report_path],
        release_gate,
        scenario_pack,
        scenario_selection_report=scenario_selection,
        release_unblock_checklist_report=outputs[release_unblock_checklist_path],
        run_fixtures=fixture_payloads,
        source_refs={
            "grade_report": grade_report_path.as_posix(),
            "release_gate": release_gate_path.as_posix(),
            "scenario_pack": pack_path.as_posix(),
            "scenario_selection": scenario_selection_path.as_posix(),
            "regression_promotion_queue": regression_promotion_queue_path.as_posix(),
            "release_unblock_checklist": release_unblock_checklist_path.as_posix(),
        },
    )
    outputs[result_persistence_manifest_path] = result_persistence_manifest
    judge_version_registry = build_judge_version_registry(
        scenario_pack=scenario_pack,
        grade_report=outputs[grade_report_path],
    )
    outputs[judge_versions_path] = judge_version_registry
    release_policy_config = json.loads(release_policy_config_path.read_text(encoding="utf-8"))
    outputs[saas_control_plane_path] = build_saas_control_plane_report(
        grade_report=outputs[grade_report_path],
        coverage_report=coverage_report,
        calibration_matrix=calibration_matrix,
        release_gate_report=release_gate,
        scenario_selection_report=scenario_selection,
        result_persistence_manifest=result_persistence_manifest,
        judge_version_registry=judge_version_registry,
        release_policy_config=release_policy_config,
        source_refs={
            "grade_report": grade_report_path.as_posix(),
            "coverage_report": coverage_report_path.as_posix(),
            "calibration_matrix": calibration_matrix_path.as_posix(),
            "release_gate": release_gate_path.as_posix(),
            "scenario_selection": scenario_selection_path.as_posix(),
            "release_unblock_checklist": release_unblock_checklist_path.as_posix(),
            "result_persistence": result_persistence_manifest_path.as_posix(),
            "judge_versions": judge_versions_path.as_posix(),
            "release_policy_config": release_policy_config_path.as_posix(),
        },
    )
    return outputs


def load_run_fixtures(run_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    fixtures = []
    for path in sorted(run_dir.glob("*.json")):
        fixtures.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return fixtures


def _load_optional_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


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
