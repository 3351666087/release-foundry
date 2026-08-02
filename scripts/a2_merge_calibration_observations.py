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
    merge_calibration_observations,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge reviewed external observations into an A2 calibration observations payload."
    )
    parser.add_argument("--base", default=DEFAULT_CALIBRATION_OBSERVATIONS.as_posix())
    parser.add_argument("--incoming", required=True, help="Importer output or observations JSON to merge.")
    parser.add_argument("--source", default="releasefoundry_grading", help="External source to merge, usually releasefoundry_grading or llm_judge.")
    parser.add_argument("--min-count", type=int, default=1, help="Require at least this many merged observations.")
    parser.add_argument(
        "--require-reviewed",
        action="store_true",
        help="Fail unless every merged row for the selected source passes reviewed-evidence validation.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless reviewed rows for the selected source exactly cover every base calibration case.",
    )
    parser.add_argument(
        "--semantic-collection-packet",
        default=DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET.as_posix(),
        help=(
            "Exact C4 collection packet used to validate strict llm_judge merges."
        ),
    )
    parser.add_argument("--output", help="Write merged calibration JSON here. Omit to print to stdout.")
    args = parser.parse_args()

    base = _read_json(Path(args.base))
    incoming = _read_json(Path(args.incoming))
    try:
        merged = merge_calibration_observations(
            base,
            incoming,
            source=args.source,
            require_reviewed=args.require_reviewed,
            require_complete=args.require_complete,
            semantic_collection_packet_path=args.semantic_collection_packet,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    merged_count = sum(1 for observation in merged.get("observations", []) if observation.get("source") == args.source)
    if merged_count < args.min_count:
        raise SystemExit(f"{args.source} merged count {merged_count} is below --min-count {args.min_count}")

    text = json.dumps(merged, indent=2) + "\n"
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
