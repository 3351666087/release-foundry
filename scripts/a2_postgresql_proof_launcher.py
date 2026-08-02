from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Any


def build_environment(dsn: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["POSTGRES_DSN"] = dsn
    return environment


def build_command(pytest_args: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        *(pytest_args or ["tests/a2/test_result_persistence.py"]),
    ]

def build_dry_run_receipt(pytest_args: list[str]) -> dict[str, Any]:
    command = build_command(pytest_args)
    return {
        "schema_version": "a2.postgresql_proof_launcher_dry_run.v1",
        "command": [command[0], "-m", "pytest", *command[3:]],
        "selected_tests": command[3:],
        "dsn_present": False,
        "executes_tests": False,
        "release_authority": False,
        "public_safe": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an A2 PostgreSQL proof with an ephemeral, non-persisted DSN."
    )
    parser.add_argument("--dsn")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("pytest_args", nargs="*")
    args = parser.parse_args()
    if args.dry_run:
        print(__import__("json").dumps(build_dry_run_receipt(args.pytest_args), sort_keys=True))
        return 0
    if not args.dsn:
        raise SystemExit("--dsn is required unless --dry-run is used")
    if not args.dsn.startswith(("postgres://", "postgresql://")):
        raise SystemExit("temporary DSN must use postgres:// or postgresql://")
    command = build_command(args.pytest_args)
    completed = subprocess.run(command, env=build_environment(args.dsn), check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
