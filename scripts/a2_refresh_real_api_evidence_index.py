from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.sdk.releasefoundry.evidence import build_private_evidence_index, merge_evidence_indices, write_private_evidence_index  # noqa: E402


DEFAULT_OUTPUT = Path("docs/a1/api_calibration/real_api_evidence_index.json")
DEFAULT_PATTERNS = (
    "docs/evidence/private_refs/a1_real_*.json",
    "docs/evidence/private_refs/a1_ts_api_calibration_*.json",
    "docs/evidence/private_refs/a1_python_api_calibration_*.json",
    "docs/evidence/private_refs/a1_python_api_get_*_round2_real.json",
    "docs/evidence/private_refs/a1_api_probe_batch_plan_*.json",
    "docs/evidence/private_refs/a1_ts_api_probe_batch_plan_*.json",
    "docs/evidence/private_refs/a1_api_validate_gate_*.json",
    "docs/evidence/private_refs/a1_ts_api_validate_gate_*.json",
    "docs/evidence/private_refs/a1_*validate_gate*.json",
    "docs/evidence/private_refs/a2_g3_real_api_*/*/*.json",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the public-safe A1/A2 real API evidence index without losing preserved private refs."
    )
    parser.add_argument("--existing-index", default=DEFAULT_OUTPUT.as_posix())
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    parser.add_argument("--label", default="a2-g3-real-api-refresh")
    parser.add_argument("--include", action="append", default=[], help="Additional private evidence glob. Repeatable.")
    parser.add_argument("--replace-existing", action="store_true", help="Do not preserve records already in the existing public index.")
    args = parser.parse_args()

    old_index = None if args.replace_existing else _load_existing_index(Path(args.existing_index))
    paths = _collect_paths((*DEFAULT_PATTERNS, *args.include))
    fresh_index = build_private_evidence_index(paths, label=f"{args.label}-fresh")
    index = fresh_index if args.replace_existing else merge_evidence_indices(old_index, fresh_index, label=args.label)
    write_private_evidence_index(args.output, index)

    print(
        json.dumps(
            {
                "output": args.output,
                "label": index["label"],
                "records": index["total_records"],
                "fresh_records": fresh_index["total_records"],
                "preserved_existing": old_index is not None and not args.replace_existing,
                "status_counts": index["status_counts"],
                "function_counts": index["function_counts"],
                "quota_block_count": index["quota_block_count"],
            },
            sort_keys=True,
        )
    )
    return 0


def _load_existing_index(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _collect_paths(patterns: tuple[str, ...]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(path.relative_to(ROOT) for path in ROOT.glob(pattern) if path.is_file())
    return sorted(paths)


if __name__ == "__main__":
    raise SystemExit(main())
