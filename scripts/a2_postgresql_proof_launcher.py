from __future__ import annotations

import argparse
import os
import subprocess
import sys


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an A2 PostgreSQL proof with an ephemeral, non-persisted DSN."
    )
    parser.add_argument("--dsn", required=True)
    parser.add_argument("pytest_args", nargs="*")
    args = parser.parse_args()
    if not args.dsn.startswith(("postgres://", "postgresql://")):
        raise SystemExit("temporary DSN must use postgres:// or postgresql://")
    command = build_command(args.pytest_args)
    completed = subprocess.run(command, env=build_environment(args.dsn), check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
