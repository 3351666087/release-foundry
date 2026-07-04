from __future__ import annotations

import argparse
import sys
from pathlib import Path

SDK_PATH = Path(__file__).resolve().parents[2] / "packages" / "sdk"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from ashr_clone.dataset_adapter import load_cases_from_api_record, write_cases  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert Ashr dataset_source records into A1 local runner cases.")
    parser.add_argument("--input", required=True, help="API probe record, get_dataset response, or dataset JSON containing dataset_source.")
    parser.add_argument("--output", required=True, help="Output cases JSON path.")
    parser.add_argument("--max-cases", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_cases_from_api_record(args.input, max_cases=args.max_cases)
        write_cases(args.output, cases)
        print(f"converted {len(cases)} Ashr dataset case(s) -> {args.output}")
        return 0
    except Exception as exc:
        build_parser().exit(2, f"dataset adapter error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
