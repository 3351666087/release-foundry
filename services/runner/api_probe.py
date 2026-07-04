from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SDK_PATH = Path(__file__).resolve().parents[2] / "packages" / "sdk"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from ashr_clone.api_client import ASHR_API_ENV_VAR, ASHR_LABS_API_ENV_VAR, AshrApiClient, AshrApiError, MissingAshrApiKeyError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quota-safe Ashr API calibration probe.")
    parser.add_argument("operation", choices=["init", "list-datasets", "get-dataset", "list-runs", "get-run", "poll-run", "list-requests", "get-request", "poll-request", "create-request", "create-run"])
    parser.add_argument("--execute", action="store_true", help="Perform the real API call. Omit for dry-run planning.")
    parser.add_argument("--allow-mutate", action="store_true", help="Required with --execute for create-run and create-request.")
    parser.add_argument("--output", help="JSON output path. Defaults to docs/evidence/private_refs.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dataset-id", type=int)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--request-id", type=int)
    parser.add_argument("--result-file", help="Run result JSON for create-run.")
    parser.add_argument("--request-name", help="Request name for create-request.")
    parser.add_argument("--request-file", help="Generation request config JSON for create-request.")
    parser.add_argument("--request-schema-file", help="Optional request input schema JSON for create-request.")
    parser.add_argument("--poll-timeout", type=int, default=300)
    parser.add_argument("--poll-interval", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dry_run = not args.execute
    output = Path(args.output) if args.output else default_output_path(args.operation, dry_run=dry_run)

    try:
        if args.execute and args.operation in MUTATING_OPERATIONS and not args.allow_mutate:
            raise ValueError(f"{args.operation} is mutating; rerun with --allow-mutate after reviewing the dry-run plan")
        client_kwargs: dict[str, Any] = {"timeout": args.timeout, "max_retries": args.max_retries}
        if args.base_url:
            client_kwargs["base_url"] = args.base_url
        client = AshrApiClient.from_env(required=args.execute, **client_kwargs)
        record = run_operation(client, args, output=output, dry_run=dry_run)
        print("{mode} {operation}: status={status} attempts={attempts} output={output}".format(mode="executed" if args.execute else "planned", operation=args.operation, status=record["status"], attempts=record["attempts"], output=output))
        return 0
    except MissingAshrApiKeyError as exc:
        print(f"api probe error: {exc}", file=sys.stderr)
        print(f"hint: set {ASHR_API_ENV_VAR} or {ASHR_LABS_API_ENV_VAR} in the current process", file=sys.stderr)
        return 2
    except (AshrApiError, RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"api probe error: {exc}", file=sys.stderr)
        return 2


def run_operation(client: AshrApiClient, args: argparse.Namespace, *, output: Path, dry_run: bool) -> dict[str, Any]:
    if args.operation == "init":
        return client.init(output_path=output, dry_run=dry_run)
    if args.operation == "list-datasets":
        return client.list_datasets(limit=args.limit, output_path=output, dry_run=dry_run)
    if args.operation == "get-dataset":
        require(args.dataset_id, "--dataset-id is required for get-dataset")
        return client.get_dataset(args.dataset_id, output_path=output, dry_run=dry_run)
    if args.operation == "list-runs":
        return client.list_runs(dataset_id=args.dataset_id, limit=args.limit, output_path=output, dry_run=dry_run)
    if args.operation == "get-run":
        require(args.run_id, "--run-id is required for get-run")
        return client.get_run(args.run_id, output_path=output, dry_run=dry_run)
    if args.operation == "poll-run":
        require(args.run_id, "--run-id is required for poll-run")
        return client.poll_run(run_id=args.run_id, timeout_seconds=args.poll_timeout, poll_interval_seconds=args.poll_interval, output_path=output, dry_run=dry_run)
    if args.operation == "list-requests":
        return client.list_requests(limit=args.limit, output_path=output, dry_run=dry_run)
    if args.operation == "get-request":
        require(args.request_id, "--request-id is required for get-request")
        return client.get_request(args.request_id, output_path=output, dry_run=dry_run)
    if args.operation == "poll-request":
        require(args.request_id, "--request-id is required for poll-request")
        return client.poll_request(request_id=args.request_id, timeout_seconds=args.poll_timeout, poll_interval_seconds=args.poll_interval, output_path=output, dry_run=dry_run)
    if args.operation == "create-request":
        require(args.request_name, "--request-name is required for create-request")
        require(args.request_file, "--request-file is required for create-request")
        request = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
        request_schema = json.loads(Path(args.request_schema_file).read_text(encoding="utf-8")) if args.request_schema_file else None
        return client.create_request(request_name=args.request_name, request=request, request_input_schema=request_schema, output_path=output, dry_run=dry_run)
    if args.operation == "create-run":
        require(args.dataset_id, "--dataset-id is required for create-run")
        require(args.result_file, "--result-file is required for create-run")
        result = json.loads(Path(args.result_file).read_text(encoding="utf-8"))
        return client.create_run(dataset_id=args.dataset_id, result=result, output_path=output, dry_run=dry_run)
    raise ValueError(f"unsupported operation: {args.operation}")


def default_output_path(operation: str, *, dry_run: bool) -> Path:
    suffix = "dry_run" if dry_run else "real"
    safe_operation = operation.replace("-", "_")
    return Path("docs") / "evidence" / "private_refs" / f"a1_api_{safe_operation}_{suffix}.json"


def require(value: Any, message: str) -> None:
    if value is None:
        raise ValueError(message)


MUTATING_OPERATIONS = {"create-run", "create-request"}


if __name__ == "__main__":
    sys.exit(main())
