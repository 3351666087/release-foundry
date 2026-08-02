from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.judge.candidate_authority import build_candidate_authority


A2_AUTHORITY_GIT_SHA = "e21ebcb1b09b2a709f5381e02f89933477453d82"
A3_BASELINE_GIT_SHA = "bad647acae613f372053771a0eb7219798c4cc20"
CREATED_AT = "2026-07-20T13:00:22Z"

SOURCE_PATHS = {
    "a1_receipt": "fixtures/a3/golden-path/rc3/a1_candidate_run_receipt.json",
    "a1_run_result": "fixtures/a3/golden-path/rc3/a3_new_run_result.redacted.json",
    "a2_release_gate": "fixtures/a2/results/a2_release_gate_report.json",
    "a2_multimodal_control": "docs/evidence/a2_multimodal_control_policy_assessment_round53.json",
    "a2_multimodal_repeat": "docs/evidence/a2_multimodal_multi_repeat_comparison_round53.json",
    "a2_cloud_control": "docs/evidence/a2_dashscope_round53_controls_round53.json",
    "a2_local_runtime": "docs/evidence/a2_qwen3vl8b_runtime_promotion_round53.json",
    "a2_postgresql_qualification": "docs/evidence/a2_postgresql_persistence_qualification_round53.json",
    "a2_review_collection": "docs/evidence/a2_multimodal_real_reviews_round52.json",
    "a2_review_conservation": "docs/evidence/a2_multimodal_review_conservation_round52.json",
}
GRADE_RESULTS_PATH = "fixtures/a3/golden-path/rc3/a2_grade_results.json"
SHARED_IDENTITY_PATH = (
    "fixtures/a3/golden-path/rc3/a2_shared_candidate_identity.json"
)
TRUSTED_SPINE_PATH = (
    "fixtures/a3/golden-path/rc3/a2_trusted_spine_handoff.snapshot.json"
)


def build_outputs() -> dict[str, dict[str, Any]]:
    source_values = {name: _load_json(path) for name, path in SOURCE_PATHS.items()}
    return build_candidate_authority(
        run_result=source_values["a1_run_result"],
        a1_receipt=source_values["a1_receipt"],
        source_release_gate=source_values["a2_release_gate"],
        multimodal_control=source_values["a2_multimodal_control"],
        multimodal_repeat=source_values["a2_multimodal_repeat"],
        cloud_control=source_values["a2_cloud_control"],
        local_runtime=source_values["a2_local_runtime"],
        postgresql_qualification=source_values[
            "a2_postgresql_qualification"
        ],
        review_collection=source_values["a2_review_collection"],
        review_conservation=source_values["a2_review_conservation"],
        run_result_file_hash=_file_hash(SOURCE_PATHS["a1_run_result"]),
        a1_receipt_file_hash=_file_hash(SOURCE_PATHS["a1_receipt"]),
        a2_git_sha=A2_AUTHORITY_GIT_SHA,
        a3_baseline_git_sha=A3_BASELINE_GIT_SHA,
        created_at=CREATED_AT,
        source_paths=SOURCE_PATHS,
        grade_results_path=GRADE_RESULTS_PATH,
        shared_identity_path=SHARED_IDENTITY_PATH,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when committed M40-04 outputs differ from recomputation.",
    )
    args = parser.parse_args()
    outputs = build_outputs()
    destinations = {
        GRADE_RESULTS_PATH: outputs["grade_results"],
        SHARED_IDENTITY_PATH: outputs["shared_candidate_identity"],
        TRUSTED_SPINE_PATH: outputs["trusted_spine"],
    }
    if args.check:
        mismatches = [
            path
            for path, value in destinations.items()
            if not (ROOT / path).exists() or _load_json(path) != value
        ]
        print(
            json.dumps(
                {
                    "verified": not mismatches,
                    "mismatches": mismatches,
                    "decision": outputs["trusted_spine"]["decision_summary"][
                        "decision"
                    ],
                },
                sort_keys=True,
            )
        )
        return 0 if not mismatches else 1
    for path, value in destinations.items():
        _write_json(path, value)
    print(
        json.dumps(
            {
                "written": sorted(destinations),
                "decision": outputs["trusted_spine"]["decision_summary"][
                    "decision"
                ],
                "ledger_head": outputs["trusted_spine"]["decision_ledger"][
                    "head_hash"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _load_json(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _file_hash(path: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _write_json(path: str, value: dict[str, Any]) -> None:
    destination = ROOT / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
