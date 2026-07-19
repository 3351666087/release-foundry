#!/usr/bin/env python3
"""Verify an Ashr Product Release manifest.

Usage:
    python scripts/verify_product_release.py \
      --manifest dist/releases/ashr-product-1.0.0/manifest.json \
      --repo-root . \
      --output dist/releases/ashr-product-1.0.0/verification.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.product_release import verify_product_release_manifest  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed verifier for an installable Ashr Product Release.",
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_product_release_manifest(
        args.manifest,
        repo_root=args.repo_root,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if result["decision"] == "approve_product_release" else 2


if __name__ == "__main__":
    raise SystemExit(main())
