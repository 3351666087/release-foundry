"""Validate the origin/main A1 pytest baseline in an isolated worktree.

This command intentionally avoids checking out or modifying the caller's
worktree. It creates a detached temporary worktree at origin/main, runs the A1
pytest baseline there, reports the result, and removes the temporary worktree.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_TEST_COMMAND = [
    sys.executable,
    "-B",
    "-m",
    "pytest",
    "tests/a1",
    "-q",
    "-p",
    "no:cacheprovider",
]


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def repo_root() -> Path:
    result = run_command(["git", "rev-parse", "--show-toplevel"], Path.cwd())
    if result.returncode != 0:
        raise SystemExit(f"Could not resolve git repository root:\n{result.stderr.strip()}")
    return Path(result.stdout.strip()).resolve()


def ensure_ref(root: Path, ref: str) -> str:
    result = run_command(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], root)
    if result.returncode != 0:
        raise SystemExit(
            f"Could not resolve {ref}. Run `git fetch origin --prune` and retry.\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def make_temp_worktree(root: Path, ref: str) -> Path:
    temp_parent = Path(tempfile.mkdtemp(prefix="releasefoundry-a1-main-baseline-"))
    worktree = temp_parent / "worktree"
    result = run_command(["git", "worktree", "add", "--detach", str(worktree), ref], root)
    if result.returncode != 0:
        shutil.rmtree(temp_parent, ignore_errors=True)
        raise SystemExit(
            f"Could not create temporary worktree for {ref}.\n"
            f"stdout:\n{result.stdout.strip()}\n"
            f"stderr:\n{result.stderr.strip()}"
        )
    return worktree


def remove_temp_worktree(root: Path, worktree: Path) -> None:
    temp_root = Path(tempfile.gettempdir()).resolve()
    resolved_worktree = worktree.resolve()
    if temp_root not in resolved_worktree.parents:
        raise RuntimeError(f"Refusing to remove non-temp worktree: {resolved_worktree}")

    run_command(["git", "worktree", "remove", "--force", str(resolved_worktree)], root)
    shutil.rmtree(resolved_worktree.parent, ignore_errors=True)


def write_record(record: dict[str, object], output: Path | None) -> None:
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(payload, end="")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    print(f"Wrote baseline record to {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the origin/main A1 pytest baseline in a temporary git worktree."
    )
    parser.add_argument("--ref", default="origin/main", help="Git ref to validate. Default: origin/main")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for a JSON result record. Defaults to stdout.",
    )
    parser.add_argument(
        "--test-command",
        nargs=argparse.REMAINDER,
        help="Override command after --, for example: --test-command -- python -m pytest tests/a1 -q",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    commit = ensure_ref(root, args.ref)
    worktree: Path | None = None
    started_at = datetime.now(timezone.utc)
    test_command = args.test_command or DEFAULT_TEST_COMMAND

    try:
        worktree = make_temp_worktree(root, args.ref)
        test_result = run_command(test_command, worktree)
    finally:
        if worktree is not None:
            remove_temp_worktree(root, worktree)

    ended_at = datetime.now(timezone.utc)
    record: dict[str, object] = {
        "schema_version": "releasefoundry.a1.origin_main_baseline.v1",
        "ref": args.ref,
        "commit": commit,
        "repo_root": str(root),
        "test_command": test_command,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_seconds": round((ended_at - started_at).total_seconds(), 3),
        "passed": test_result.returncode == 0,
        "returncode": test_result.returncode,
        "stdout_tail": test_result.stdout[-4000:],
        "stderr_tail": test_result.stderr[-4000:],
    }
    write_record(record, args.output)
    return test_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
