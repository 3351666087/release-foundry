from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.calibration import import_semantic_judge_observations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert reviewed semantic judge summaries into A2 llm_judge calibration observations."
    )
    parser.add_argument("--input", required=True, help="Reviewed semantic judge summary JSON.")
    parser.add_argument("--case-map", help="Optional JSON map from raw semantic case id to A2 case_id.")
    parser.add_argument("--evidence-ref", default="", help="Private evidence path to store as a reference only.")
    parser.add_argument("--output", help="Write imported observations JSON here. Omit to print to stdout.")
    args = parser.parse_args()

    payload = _read_json(Path(args.input))
    case_map = _read_json(Path(args.case_map)) if args.case_map else {}
    if not isinstance(case_map, dict):
        raise SystemExit("--case-map must point to a JSON object")

    observations = import_semantic_judge_observations(
        payload,
        case_map={str(key): str(value) for key, value in case_map.items()},
        evidence_ref=args.evidence_ref,
    )
    output = {
        "schema_version": "a2.semantic_judge_import.v1",
        "observation_count": len(observations),
        "observations": observations,
    }
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
