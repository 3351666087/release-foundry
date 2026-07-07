from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.service_wrapper import handle_internal_request  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the A2 internal judge service wrapper without a web server.")
    parser.add_argument(
        "endpoint",
        choices=[
            "/internal/judge/case",
            "/internal/judge/run",
            "/internal/judge/batch",
            "/internal/release-policy/evaluate",
            "/internal/regression/replay",
            "/internal/calibration/evaluate",
            "/internal/scenarios/select",
        ],
    )
    parser.add_argument("--method", default="POST")
    parser.add_argument("--input", default="-", help="JSON file path, or '-' for stdin.")
    parser.add_argument("--output", default="-", help="JSON output path, or '-' for stdout.")
    parser.add_argument(
        "--fail-on-release-block",
        action="store_true",
        help="For release-policy responses, return the embedded release gate exit_code.",
    )
    args = parser.parse_args()

    os.chdir(ROOT)
    payload = _read_payload(args.input)
    response = handle_internal_request(args.endpoint, payload, method=args.method)
    text = json.dumps(response, indent=2) + "\n"
    if args.output == "-":
        print(text, end="")
    else:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")

    if not response["ok"]:
        return 1
    if args.fail_on_release_block and args.endpoint == "/internal/release-policy/evaluate":
        return int(response["result"].get("exit_code", 0))
    return 0


def _read_payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    if not text.strip():
        return {}
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise SystemExit("service payload must be a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
