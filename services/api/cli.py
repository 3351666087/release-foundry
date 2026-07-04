from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from packages.sdk.ashr_clone.api_client import redact_text
from services.runner.runner import DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, normalize_timeout_seconds

from .demo import run_agent_cloud_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local Ashr cloud API demo flows.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_agent = subparsers.add_parser("run-agent", help="Run an agent locally, submit it to CloudApiService, poll, and write a fixture.")
    run_agent.add_argument("-i", "--input", required=True)
    run_agent.add_argument("--agent", required=True)
    run_agent.add_argument("--fixture-output", required=True)
    run_agent.add_argument("--summary-output")
    run_agent.add_argument("--run-output")
    run_agent.add_argument("--tenant-id", default="tenant_local_demo")
    run_agent.add_argument("--project-id", default="project_local_demo")
    run_agent.add_argument("--tenant-name", default="Local Demo Tenant")
    run_agent.add_argument("--project-name", default="Local Demo Project")
    run_agent.add_argument("--dataset-id", default="dataset_local_demo")
    run_agent.add_argument("--dataset-name", default="Local Demo Dataset")
    run_agent.add_argument("--runner-id", default="a1-cloud-demo-runner")
    run_agent.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    run_agent.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    run_agent.add_argument("--no-timeout", action="store_true")
    run_agent.add_argument("--fail-on-case-failure", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run-agent":
            timeout = None if args.no_timeout else normalize_timeout_seconds(args.timeout, field_name="--timeout")
            summary = run_agent_cloud_demo(
                input_path=Path(args.input),
                agent=args.agent,
                fixture_output_path=Path(args.fixture_output),
                summary_output_path=Path(args.summary_output) if args.summary_output else None,
                run_output_path=Path(args.run_output) if args.run_output else None,
                tenant_id=args.tenant_id,
                project_id=args.project_id,
                tenant_name=args.tenant_name,
                project_name=args.project_name,
                dataset_id=args.dataset_id,
                dataset_name=args.dataset_name,
                runner_id=args.runner_id,
                max_workers=args.max_workers,
                timeout_seconds=timeout,
            )
            print(json.dumps(summary, sort_keys=True))
            run = summary["run"]
            has_failure = bool(run["failed"] or run["errored"] or run["timed_out"])
            return 1 if args.fail_on_case_failure and has_failure else 0
    except Exception as exc:
        parser.exit(2, f"cloud api error: {redact_text(str(exc))}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
