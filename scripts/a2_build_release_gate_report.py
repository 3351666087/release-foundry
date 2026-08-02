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


def _multimodal_expected_bindings(
    *,
    modality_scope: list[str],
    binding_file: str | None,
    candidate_sha: str | None,
    dataset_manifest_hash: str | None,
    review_conservation_hash: str | None,
) -> dict[str, Any] | None:
    if "image" not in modality_scope:
        return None
    if not candidate_sha:
        raise SystemExit("--candidate-sha is required for image release candidates")
    if not dataset_manifest_hash:
        raise SystemExit(
            "--dataset-manifest-hash is required for image release candidates"
        )
    if not review_conservation_hash:
        raise SystemExit(
            "--multimodal-review-conservation-hash is required for image "
            "release candidates"
        )
    bindings = (
        _read_optional_json(Path(binding_file)) if binding_file else {}
    ) or {}
    required = {
        "candidate_sha": candidate_sha,
        "manifest_hash": dataset_manifest_hash,
        "review_conservation_hash": review_conservation_hash,
    }
    for field, expected in required.items():
        configured = bindings.get(field)
        if configured not in (None, expected):
            raise SystemExit(
                f"multimodal expected binding conflicts with CLI value: {field}"
            )
        bindings[field] = expected
    return bindings


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the A2 PR/release gate report.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    parser.add_argument("--commercial-readiness", default="fixtures/a2/results/a2_commercial_readiness_report.json")
    parser.add_argument("--evidence-readiness", default="fixtures/a2/results/a2_evidence_readiness_report.json")
    parser.add_argument("--calibration-matrix", default="fixtures/a2/results/a2_g3_calibration_matrix.json")
    parser.add_argument("--case-book", default="fixtures/a2/results/a2_case_book.json")
    parser.add_argument("--regression-replay", default="fixtures/a2/results/a2_regression_replay_report.json")
    parser.add_argument("--scenario-selection", default="fixtures/a2/results/a2_scenario_selection_report.json")
    parser.add_argument("--a1-evidence-index", default="docs/a1/api_calibration/real_api_evidence_index.json")
    parser.add_argument(
        "--judge-versions",
        default="fixtures/a2/results/a2_judge_versions.json",
    )
    parser.add_argument(
        "--modality-scope",
        action="append",
        choices=["text", "image"],
        default=None,
    )
    parser.add_argument("--multimodal-qualification")
    parser.add_argument(
        "--multimodal-expected-bindings",
        help="JSON file containing exact fields the multimodal qualification must bind",
    )
    parser.add_argument(
        "--candidate-sha",
        help="Exact release candidate Git SHA bound by image qualification",
    )
    parser.add_argument(
        "--dataset-manifest-hash",
        help="Exact image calibration dataset manifest hash",
    )
    parser.add_argument(
        "--multimodal-review-conservation-hash",
        help="Exact review-conservation receipt hash bound by image qualification",
    )
    parser.add_argument("--check", action="store_true", help="Compare generated report with the output path.")
    parser.add_argument("--fail-on-block", action="store_true", help="Return the report exit_code when decision is block or warn.")
    args = parser.parse_args()

    os.chdir(ROOT)
    modality_scope = args.modality_scope or ["text"]
    report = build_release_gate_report(
        _read_json(Path(args.commercial_readiness)),
        _read_json(Path(args.evidence_readiness)),
        _read_json(Path(args.calibration_matrix)),
        _read_json(Path(args.regression_replay)),
        _read_json(Path(args.scenario_selection)),
        _read_optional_json(Path(args.a1_evidence_index)),
        modality_scope,
        (
            _read_optional_json(Path(args.multimodal_qualification))
            if args.multimodal_qualification
            else None
        ),
        _multimodal_expected_bindings(
            modality_scope=modality_scope,
            binding_file=args.multimodal_expected_bindings,
            candidate_sha=args.candidate_sha,
            dataset_manifest_hash=args.dataset_manifest_hash,
            review_conservation_hash=args.multimodal_review_conservation_hash,
        ),
        judge_version_registry=_read_optional_json(Path(args.judge_versions)),
        case_book_report=_read_json(Path(args.case_book)),
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


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


if __name__ == "__main__":
    raise SystemExit(main())
