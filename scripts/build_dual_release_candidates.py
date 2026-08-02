#!/usr/bin/env python3
"""Build independent Product and Customer Agent GitHub Release candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.release_distribution import (  # noqa: E402
    build_dual_release_candidates,
    verify_release_index,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build two independent ReleaseFoundry Release candidates.")
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output-root", type=Path, default=REPOSITORY_ROOT / "dist/releases")
    parser.add_argument("--product-version", default="1.0.0-rc.1")
    parser.add_argument("--agent-version", default="0.2.0-rc.3")
    parser.add_argument("--agent-org", default="demo")
    parser.add_argument("--agent-name", default="a3-golden-agent")
    parser.add_argument("--source-commit")
    parser.add_argument("--generated-at")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--verify-index", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verify_index:
        result = verify_release_index(args.verify_index)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" else 2
    result = build_dual_release_candidates(
        args.repo_root,
        args.output_root,
        product_version=args.product_version,
        agent_version=args.agent_version,
        agent_org=args.agent_org,
        agent_name=args.agent_name,
        source_commit=args.source_commit,
        generated_at=args.generated_at,
        allow_dirty=args.allow_dirty,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
