from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _checks() -> list[dict[str, Any]]:
    return [
        {
            "id": "a2_fixture_reproducibility",
            "purpose": "Verify generated A2 fixtures match committed output.",
            "command": [sys.executable, "-B", "scripts/a2_regenerate_fixtures.py", "--check"],
        },
        {
            "id": "a2_unit_tests",
            "purpose": "Run deterministic A2 unit and contract tests.",
            "command": [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/a2", "-v"],
        },
    ]


def _plan() -> dict[str, Any]:
    return {
        "schema_version": "a2.local_lite_plan.v1",
        "profile": "local-lite",
        "requires_network": False,
        "requires_node_modules": False,
        "requires_browser": False,
        "requires_releasefoundry_api_key": False,
        "writes_files": False,
        "checks": [
            {
                "id": check["id"],
                "purpose": check["purpose"],
                "command": _display_command(check["command"]),
            }
            for check in _checks()
        ],
        "excluded_by_design": [
            "TypeScript package install/build",
            "A3 dashboard/browser runtime",
            "live ReleaseFoundry API calls",
            "audited LLM judge calls",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the lightweight local A2 verification profile without Node, browser, or ReleaseFoundry API access."
    )
    parser.add_argument("--plan", action="store_true", help="Print the local-lite plan as JSON without running checks.")
    args = parser.parse_args()

    plan = _plan()
    if args.plan:
        print(json.dumps(plan, indent=2))
        return 0

    print("A2 local-lite check", flush=True)
    print("network: off | node_modules: not required | browser: not required | ReleaseFoundry API key: not required", flush=True)
    for check in _checks():
        print(f"\n[{check['id']}] {' '.join(_display_command(check['command']))}", flush=True)
        result = subprocess.run(check["command"], cwd=ROOT, check=False)
        if result.returncode != 0:
            print(f"\nfailed: {check['id']} exited with {result.returncode}", flush=True)
            return result.returncode

    print("\nlocal-lite checks passed", flush=True)
    return 0


def _display_command(command: list[str]) -> list[str]:
    if command and command[0] == sys.executable:
        return ["python", *command[1:]]
    return command


if __name__ == "__main__":
    raise SystemExit(main())
