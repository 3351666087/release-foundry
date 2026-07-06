from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.calibration import extract_ashr_runs  # noqa: E402


DEFAULT_CASE_MAP = Path("fixtures/a2/calibration/ashr_grading_batch_case_map.json")
SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan private Ashr run evidence for the A2 C3 grading case IDs without printing raw payloads."
    )
    parser.add_argument("--input", nargs="+", required=True, help="One or more Ashr get-run/list-runs JSON files or glob patterns.")
    parser.add_argument("--case-map", default=DEFAULT_CASE_MAP.as_posix())
    parser.add_argument("--output", help="Optional public-safe JSON summary path.")
    args = parser.parse_args()

    os.chdir(ROOT)
    input_paths = _expand_inputs(args.input)
    summary = scan_evidence(input_paths, case_map_path=Path(args.case_map))
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def scan_evidence(input_paths: list[Path], *, case_map_path: Path = DEFAULT_CASE_MAP) -> dict[str, Any]:
    case_map = _load_case_map(case_map_path)
    expected_case_ids = list(dict.fromkeys(case_map.values()))
    matched_by_case: dict[str, list[dict[str, Any]]] = {case_id: [] for case_id in expected_case_ids}
    file_summaries = []
    warnings = []

    for path in input_paths:
        payload = _read_json(path)
        runs = extract_ashr_runs(payload)
        file_summary = _scan_file(path, runs, case_map, expected_case_ids)
        file_summaries.append(file_summary)
        for run in file_summary["runs"]:
            for case_id in run["matched_case_ids"]:
                matched_by_case.setdefault(case_id, []).append(
                    {
                        "evidence_ref": file_summary["evidence_ref"],
                        "run_id": run["run_id"],
                    }
                )
        if not runs:
            warnings.append(f"{file_summary['evidence_ref']} did not contain extractable Ashr run records.")

    matched_case_ids = [case_id for case_id in expected_case_ids if matched_by_case.get(case_id)]
    missing_case_ids = [case_id for case_id in expected_case_ids if not matched_by_case.get(case_id)]
    complete = bool(expected_case_ids) and not missing_case_ids
    matched_tests_with_action_results = sum(
        run["matched_tests_with_action_results"]
        for file_summary in file_summaries
        for run in file_summary["runs"]
    )
    matched_test_count = sum(
        run["matched_case_count"]
        for file_summary in file_summaries
        for run in file_summary["runs"]
    )
    if complete and matched_tests_with_action_results < len(expected_case_ids):
        warnings.append("Some matched C3 tests do not expose action_results; human review should confirm those rows before import.")

    return {
        "schema_version": "a2.ashr_grading_evidence_scan.v1",
        "scan_id": "a2_c3_ashr_grading_evidence_scan",
        "reads_private_payloads": True,
        "writes_files": False,
        "case_map_path": _display_path(case_map_path),
        "expected_case_count": len(expected_case_ids),
        "expected_case_ids": expected_case_ids,
        "matched_case_count": len(matched_case_ids),
        "matched_case_ids": matched_case_ids,
        "missing_case_count": len(missing_case_ids),
        "missing_case_ids": missing_case_ids,
        "matched_test_count": matched_test_count,
        "matched_tests_with_action_results": matched_tests_with_action_results,
        "complete_expected_match": complete,
        "import_ready_when_reviewed": complete,
        "safe_to_mark_c3_met": False,
        "public_merge_required": True,
        "files": file_summaries,
        "warnings": warnings,
        "next_action": _next_action(complete),
        "recommended_commands": _recommended_commands(complete, file_summaries, case_map_path, len(expected_case_ids)),
        "redaction_policy": {
            "outputs_case_ids_only": True,
            "omits_unmapped_test_ids": True,
            "omits_raw_responses": True,
            "secret_patterns_redacted": True,
        },
    }


def _scan_file(
    path: Path,
    runs: list[dict[str, Any]],
    case_map: dict[str, str],
    expected_case_ids: list[str],
) -> dict[str, Any]:
    expected_set = set(expected_case_ids)
    file_matched: set[str] = set()
    run_summaries = []
    unmapped_test_count = 0
    total_test_count = 0

    for run in runs:
        tests = _ashr_tests(run)
        total_test_count += len(tests)
        matched: set[str] = set()
        action_result_count = 0
        for test in tests:
            raw_case_id = str(test.get("test_id") or test.get("case_id") or "")
            case_id = case_map.get(raw_case_id)
            if not case_id:
                if raw_case_id:
                    unmapped_test_count += 1
                continue
            if case_id in expected_set:
                matched.add(case_id)
                file_matched.add(case_id)
                if isinstance(test.get("action_results"), list) and test["action_results"]:
                    action_result_count += 1
        run_summaries.append(
            {
                "run_id": _redact_text(str(run.get("id", ""))),
                "test_count": len(tests),
                "matched_case_count": len(matched),
                "matched_case_ids": [case_id for case_id in expected_case_ids if case_id in matched],
                "matched_tests_with_action_results": action_result_count,
            }
        )

    return {
        "evidence_ref": _display_path(path),
        "run_count": len(runs),
        "test_count": total_test_count,
        "matched_case_count": len(file_matched),
        "matched_case_ids": [case_id for case_id in expected_case_ids if case_id in file_matched],
        "missing_case_ids": [case_id for case_id in expected_case_ids if case_id not in file_matched],
        "unmapped_test_count": unmapped_test_count,
        "runs": run_summaries,
    }


def _recommended_commands(
    complete: bool,
    file_summaries: list[dict[str, Any]],
    case_map_path: Path,
    expected_count: int,
) -> list[str]:
    if not complete:
        return [
            "Run read-only list-runs/get-run probes until one reviewed Ashr grading record contains all expected C3 case IDs.",
            "Re-run this scanner before importing private evidence into the public calibration matrix.",
        ]
    complete_files = [item for item in file_summaries if not item["missing_case_ids"]]
    if not complete_files:
        return [
            "Combine the matched private run records into one reviewed JSON payload before importing.",
            "python scripts/a2_import_ashr_grading.py --input docs/evidence/private_refs/a2_ashr_get_run.redacted.json --case-map fixtures/a2/calibration/ashr_grading_batch_case_map.json --evidence-ref docs/evidence/private_refs/a2_ashr_get_run.redacted.json --review-status reviewed --output docs/evidence/private_refs/a2_ashr_grading_import.review.json",
            f"python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_ashr_grading_import.review.json --source ashr_grading --min-count {expected_count} --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
            "python scripts/a2_regenerate_fixtures.py --write",
        ]
    evidence_ref = complete_files[0]["evidence_ref"]
    return [
        f"python scripts/a2_import_ashr_grading.py --input {evidence_ref} --case-map {_display_path(case_map_path)} --evidence-ref {evidence_ref} --review-status reviewed --output docs/evidence/private_refs/a2_ashr_grading_import.review.json",
        f"python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_ashr_grading_import.review.json --source ashr_grading --min-count {expected_count} --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "python scripts/a2_regenerate_fixtures.py --write",
    ]


def _next_action(complete: bool) -> str:
    if complete:
        return "Human-review the private Ashr grading evidence, then import reviewed summaries and regenerate A2 fixtures."
    return "Do not import yet; collect or identify an Ashr grading run whose result.tests cover all expected A2 C3 case IDs."


def _expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matched = [Path(item) for item in glob.glob(pattern)]
        if matched:
            paths.extend(sorted(matched))
            continue
        path = Path(pattern)
        if path.exists():
            paths.append(path)
            continue
        raise SystemExit(f"input path or glob did not match: {pattern}")
    return list(dict.fromkeys(paths))


def _load_case_map(path: Path) -> dict[str, str]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit("--case-map must point to a JSON object")
    return {str(key): str(value) for key, value in payload.items()}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ashr_tests(run: dict[str, Any]) -> list[dict[str, Any]]:
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    tests = result.get("tests")
    return [item for item in tests if isinstance(item, dict)] if isinstance(tests, list) else []


def _display_path(path: Path) -> str:
    resolved = Path(path)
    if not resolved.is_absolute():
        return resolved.as_posix()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.name


def _redact_text(value: str) -> str:
    redacted = str(value)
    for pattern in SECRET_LIKE_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
