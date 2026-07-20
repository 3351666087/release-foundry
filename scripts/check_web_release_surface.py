#!/usr/bin/env python3
"""Verify the production Web source for an Ashr Product Release."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.product_release import (  # noqa: E402
    VERIFICATION_RECEIPT_SCHEMA,
    WEB_SURFACE_RECEIPT_ID,
    verify_web_production_surface,
)


def _rfc3339_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed UTF-8, production-data-boundary, typography, and "
            "control-size verifier for the Ashr Product Release Web surface."
        ),
    )
    parser.add_argument(
        "--web-root",
        type=Path,
        default=REPOSITORY_ROOT / "apps" / "webapp",
    )
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    parser.add_argument("--product-release-id")
    parser.add_argument("--source-commit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.receipt_output and (
        not args.product_release_id or not args.source_commit
    ):
        raise SystemExit(
            "--receipt-output requires --product-release-id and --source-commit"
        )

    started_at = _rfc3339_now()
    result = verify_web_production_surface(
        args.web_root,
        repo_root=args.repo_root,
    )
    finished_at = _rfc3339_now()
    exit_code = 0 if result["decision"] == "approve_web_surface" else 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.receipt_output:
        receipt = {
            "schema_version": VERIFICATION_RECEIPT_SCHEMA,
            "receipt_id": WEB_SURFACE_RECEIPT_ID,
            "product_release_id": args.product_release_id,
            "source_commit": args.source_commit,
            "mode": "live",
            "status": "passed" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            "started_at": started_at,
            "finished_at": finished_at,
            "environment": {
                "os": platform.system().lower(),
                "arch": platform.machine().lower(),
            },
            "verification": result,
        }
        args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_output.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    sys.stdout.write(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
