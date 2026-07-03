from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .runner import DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, run_agent_file, run_file
except ImportError:  # pragma: no cover
    from runner import DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, run_agent_file, run_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local batch of Ashr evaluation cases.")
    parser.add_argument("-i", "--input", required=True)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--agent")
    parser.add_argument("--dataset-id", default="local-dataset")
    parser.add_argument("--runner-id", default="a1-local-runner")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--no-timeout", action="store_true")
    parser.add_argument("--fail-on-case-failure", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    timeout = None if args.no_timeout else args.timeout
    try:
        if args.agent:
            results = run_agent_file(Path(args.input), Path(args.output), args.agent, dataset_id=args.dataset_id, runner_id=args.runner_id, max_workers=args.max_workers, timeout_seconds=timeout)
            print("ran {total_cases} agent cases: {passed} passed, {failed} failed, {errored} errors, {timed_out} timeouts, trace {trace_completeness:.2%} -> {output}".format(output=args.output, **results))
            return 1 if args.fail_on_case_failure and (results["failed"] or results["errored"] or results["timed_out"]) else 0
        results = run_file(Path(args.input), Path(args.output), max_workers=args.max_workers, timeout_seconds=timeout)
        summary = results["summary"]
        print("ran {total} cases: {passed} passed, {failed} failed, {errors} errors, {timeouts} timeouts -> {output}".format(output=args.output, **summary))
        return 1 if args.fail_on_case_failure and (summary["failed"] or summary["errors"] or summary["timeouts"]) else 0
    except Exception as exc:
        build_parser().exit(2, f"runner error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
