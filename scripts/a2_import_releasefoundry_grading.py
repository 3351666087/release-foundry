from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.calibration import import_releasefoundry_grading_observations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert redacted ReleaseFoundry run records into A2 releasefoundry_grading calibration observations."
    )
    parser.add_argument("--input", required=True, help="Redacted ReleaseFoundry get-run/list-runs record or direct run JSON.")
    parser.add_argument("--case-map", help="Optional JSON map from ReleaseFoundry test_id to A2 case_id.")
    parser.add_argument("--evidence-ref", default="", help="Private evidence path to store as a reference only.")
    parser.add_argument(
        "--review-status",
        choices=["unreviewed", "reviewed"],
        default="unreviewed",
        help="Mark whether the redacted incoming evidence has been human reviewed.",
    )
    parser.add_argument("--output", help="Write imported observations JSON here. Omit to print to stdout.")
    args = parser.parse_args()

    payload = _read_json(Path(args.input))
    case_map = _read_json(Path(args.case_map)) if args.case_map else {}
    if not isinstance(case_map, dict):
        raise SystemExit("--case-map must point to a JSON object")

    observations = import_releasefoundry_grading_observations(
        payload,
        case_map={str(key): str(value) for key, value in case_map.items()},
        evidence_ref=args.evidence_ref,
        review_status=args.review_status,
    )
    output = {"schema_version": "a2.releasefoundry_grading_import.v1", "observation_count": len(observations), "observations": observations}
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


if __name__ == "__main__":
    raise SystemExit(main())
