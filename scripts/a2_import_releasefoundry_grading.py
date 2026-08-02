from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.calibration import (  # noqa: E402
    DEFAULT_CALIBRATION_OBSERVATIONS,
    extract_releasefoundry_runs,
    import_releasefoundry_grading_observations,
)
from services.judge.releasefoundry_test_receipts import (  # noqa: E402
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_terminal_receipt,
)
from services.judge.releasefoundry_dataset_identity import (  # noqa: E402
    DatasetIdentityError,
    load_verified_dataset_identity_binding,
)


DEFAULT_DATASET_IDENTITY = Path(
    "docs/evidence/private_refs/a2_releasefoundry_dataset_identity.private.json"
)
DEFAULT_DATASET_IDENTITY_RECEIPT = Path(
    "docs/evidence/a2_releasefoundry_dataset_identity_receipt.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert redacted ReleaseFoundry run records into A2 releasefoundry_grading calibration observations."
    )
    parser.add_argument("--input", required=True, help="Redacted ReleaseFoundry get-run/list-runs record or direct run JSON.")
    parser.add_argument("--case-map", help="Optional JSON map from ReleaseFoundry test_id to A2 case_id.")
    parser.add_argument(
        "--identity-file",
        default=DEFAULT_DATASET_IDENTITY.as_posix(),
        help=(
            "Private fixed ReleaseFoundry dataset identity manifest required by strict "
            "imports."
        ),
    )
    parser.add_argument(
        "--identity-receipt",
        default=DEFAULT_DATASET_IDENTITY_RECEIPT.as_posix(),
        help=(
            "Public verified ReleaseFoundry dataset identity receipt required by strict "
            "imports."
        ),
    )
    parser.add_argument(
        "--expected-judge-version",
        default="",
        help=(
            "Optional expected grader version to compare with the "
            "server-observed version; it cannot replace server provenance."
        ),
    )
    parser.add_argument("--evidence-ref", default="", help="Private evidence path to store as a reference only.")
    parser.add_argument(
        "--review-status",
        choices=["unreviewed", "reviewed"],
        default="unreviewed",
        help="Mark whether the redacted incoming evidence has been human reviewed.",
    )
    parser.add_argument(
        "--reviewer-receipt",
        help="Pseudonymous human reviewer receipt in canonical sha256:<64 lowercase hex> form.",
    )
    parser.add_argument(
        "--reviewed-at-unix-ms",
        type=int,
        help="Positive Unix timestamp in milliseconds for the human review.",
    )
    parser.add_argument(
        "--require-reviewed",
        action="store_true",
        help="Fail unless every imported observation is reviewed and has an evidence reference.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless reviewed observations exactly cover every calibration case.",
    )
    parser.add_argument(
        "--calibration",
        default=DEFAULT_CALIBRATION_OBSERVATIONS.as_posix(),
        help="Calibration observations file that defines expected cases for --require-complete.",
    )
    parser.add_argument("--output", help="Write imported observations JSON here. Omit to print to stdout.")
    args = parser.parse_args()

    payload = _read_json(Path(args.input))
    case_map = _read_json(Path(args.case_map)) if args.case_map else {}
    if not isinstance(case_map, dict):
        raise SystemExit("--case-map must point to a JSON object")

    expected_case_ids = _read_case_ids(Path(args.calibration)) if args.require_complete else None
    expected_dataset_id = None
    verified_dataset_identity = None
    if args.require_reviewed or args.require_complete:
        try:
            verified_dataset_identity = load_verified_dataset_identity_binding(
                Path(args.identity_receipt),
                Path(args.identity_file),
            )
        except DatasetIdentityError as exc:
            raise SystemExit(str(exc)) from exc
        expected_dataset_id = verified_dataset_identity.expectation.dataset_id
    try:
        observations = import_releasefoundry_grading_observations(
            payload,
            case_map={str(key): str(value) for key, value in case_map.items()},
            evidence_ref=args.evidence_ref,
            review_status=args.review_status,
            reviewer_receipt=args.reviewer_receipt,
            reviewed_at_unix_ms=args.reviewed_at_unix_ms,
            expected_case_ids=expected_case_ids,
            require_reviewed=args.require_reviewed,
            require_complete=args.require_complete,
            expected_dataset_id=expected_dataset_id,
            expected_judge_version=args.expected_judge_version,
            verified_dataset_identity=verified_dataset_identity,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output = {
        "schema_version": "a2.releasefoundry_grading_import.v2",
        "observation_count": len(observations),
        "observations": observations,
    }
    if args.require_reviewed or args.require_complete:
        private_run_receipt = build_releasefoundry_test_terminal_receipt(
            extract_releasefoundry_runs(payload)[0],
            case_map={str(key): str(value) for key, value in case_map.items()},
            expected_dataset_id=expected_dataset_id,
            expected_judge_version=args.expected_judge_version,
        )
        output["run_terminal_receipt"] = public_releasefoundry_test_terminal_receipt(
            private_run_receipt
        )
    text = json.dumps(output, indent=2) + "\n"
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_case_ids(path: Path) -> list[str]:
    payload = _read_json(path)
    return [
        str(case["case_id"])
        for case in payload.get("cases", [])
        if isinstance(case, dict) and case.get("case_id")
    ]


if __name__ == "__main__":
    raise SystemExit(main())
