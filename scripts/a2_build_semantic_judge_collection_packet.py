from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.semantic_collection import (  # noqa: E402
    DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
    build_semantic_judge_collection_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the public-safe A2 C4 semantic judge collection packet."
    )
    parser.add_argument("--output", default=DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET.as_posix())
    parser.add_argument("--pack", default="packages/scenarios/a2_g3_full_pack.json")
    parser.add_argument("--run-dir", default="fixtures/a2/runs")
    parser.add_argument("--observations", default="fixtures/a2/calibration/a2_g3_calibration_observations.json")
    parser.add_argument("--check", action="store_true", help="Compare generated packet with the output path.")
    args = parser.parse_args()

    os.chdir(ROOT)
    packet = build_semantic_judge_collection_packet(
        pack_path=args.pack,
        run_dir=args.run_dir,
        observations_path=args.observations,
    )
    text = json.dumps(packet, indent=2) + "\n"
    output = Path(args.output)
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != text:
            print(f"A2 semantic judge collection packet drift: {output.as_posix()}")
            return 1
        print(f"A2 semantic judge collection packet matches {output.as_posix()}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"wrote {output.as_posix()} with {packet['case_count']} C4 cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
