#!/usr/bin/env python3
"""Verify a Customer Agent Release manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.customer_release import verify_customer_agent_release_manifest  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed Customer Agent Release verifier.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--release-root", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_customer_agent_release_manifest(
        args.manifest,
        release_root=args.release_root,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if result["decision"] == "approve_customer_agent_release" else 2


if __name__ == "__main__":
    raise SystemExit(main())
