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
    DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
    import_semantic_judge_observations,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert reviewed semantic judge summaries into A2 llm_judge calibration observations."
    )
    parser.add_argument("--input", required=True, help="Reviewed semantic judge summary JSON.")
    parser.add_argument("--case-map", help="Optional JSON map from raw semantic case id to A2 case_id.")
    parser.add_argument("--evidence-ref", default="", help="Private evidence path to store as a reference only.")
    parser.add_argument(
        "--require-reviewed",
        action="store_true",
        help=(
            "Fail unless every row is reviewed live-model evidence with a canonical "
            "reviewer receipt, positive review timestamp, hashes, SDK language, and cost."
        ),
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless reviewed live evidence exactly covers every calibration case and both SDK languages.",
    )
    parser.add_argument(
        "--calibration",
        default=DEFAULT_CALIBRATION_OBSERVATIONS.as_posix(),
        help="Calibration observations file that defines expected cases for --require-complete.",
    )
    parser.add_argument(
        "--collection-packet",
        default=DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET.as_posix(),
        help=(
            "Exact C4 collection packet that binds case ids, SDK allocation, "
            "prompt template, and prompt-material hashes for strict imports."
        ),
    )
    parser.add_argument("--output", help="Write imported observations JSON here. Omit to print to stdout.")
    args = parser.parse_args()

    payload = _read_json(Path(args.input))
    case_map = _read_json(Path(args.case_map)) if args.case_map else {}
    if not isinstance(case_map, dict):
        raise SystemExit("--case-map must point to a JSON object")

    expected_case_ids = _read_case_ids(Path(args.calibration)) if args.require_complete else None
    try:
        observations = import_semantic_judge_observations(
            payload,
            case_map={str(key): str(value) for key, value in case_map.items()},
            evidence_ref=args.evidence_ref,
            expected_case_ids=expected_case_ids,
            require_reviewed=args.require_reviewed,
            require_complete=args.require_complete,
            collection_packet_path=args.collection_packet,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output = {
        "schema_version": "a2.semantic_judge_import.v2",
        "observation_count": len(observations),
        "observations": observations,
    }
    if isinstance(payload, dict) and isinstance(
        payload.get("semantic_human_review_receipt"),
        dict,
    ):
        output["semantic_human_review_receipt"] = payload[
            "semantic_human_review_receipt"
        ]
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
