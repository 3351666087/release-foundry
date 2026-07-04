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
    parser.add_argument("operation", choices=["init", "health-check", "list-datasets", "get-dataset", "list-runs", "get-run", "poll-run", "list-requests", "list-agents", "get-request", "poll-request", "create-request", "create-run"])
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
    parser.add_argument("--allow-media-generation", action="store_true", help="Allow create-request configs that enable audio, file, image, video, or simulation generation.")
    parser.add_argument("--allow-non-text-inputs", action="store_true", help="Allow create-request configs whose accepted_inputs include audio, files, images, videos, or conversations.")
    parser.add_argument("--max-request-variations", type=int, default=1, help="Maximum known num_variations allowed for create-request execution.")
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
        if args.execute and args.operation in MUTATING_OPERATIONS and args.max_retries != 0:
            raise ValueError(f"{args.operation} execution requires --max-retries 0 to avoid duplicate mutation on retry")
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
    except (AshrApiError, RuntimeError, TimeoutError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"api probe error: {exc}", file=sys.stderr)
        return 2


def run_operation(client: AshrApiClient, args: argparse.Namespace, *, output: Path, dry_run: bool) -> dict[str, Any]:
    if args.operation == "init":
        return client.init(output_path=output, dry_run=dry_run)
    if args.operation == "health-check":
        return client.health_check(output_path=output, dry_run=dry_run)
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
    if args.operation == "list-agents":
        return client.list_agents(output_path=output, dry_run=dry_run)
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
        preflight = summarize_generation_request(request)
        preflight["request_input_schema_source"] = "file" if request_schema is not None else "client_default"
        if not dry_run:
            enforce_create_request_preflight(
                preflight,
                allow_media_generation=args.allow_media_generation,
                allow_non_text_inputs=args.allow_non_text_inputs,
                max_request_variations=args.max_request_variations,
            )
        return client.create_request(
            request_name=args.request_name,
            request=request,
            request_input_schema=request_schema,
            output_path=output,
            dry_run=dry_run,
            preflight=preflight,
        )
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


def summarize_generation_request(request: dict[str, Any]) -> dict[str, Any]:
    generation_options = request.get("generation_options") if isinstance(request.get("generation_options"), dict) else {}
    test_config = request.get("test_config") if isinstance(request.get("test_config"), dict) else {}
    agent = request.get("agent") if isinstance(request.get("agent"), dict) else {}
    accepted_inputs_raw = agent.get("accepted_inputs") if isinstance(agent, dict) else None
    accepted_inputs_provided = accepted_inputs_raw is not None
    accepted_inputs_shape_supported = accepted_inputs_raw is None or isinstance(accepted_inputs_raw, dict)
    accepted_inputs = accepted_inputs_raw if isinstance(accepted_inputs_raw, dict) else {}
    accepted_flags: dict[str, bool] = {}
    accepted_flag_shapes: dict[str, bool] = {}
    for key in ("text", "audio", "file", "image", "video", "conversation"):
        if not accepted_inputs_provided:
            accepted_flags[key] = key == "text"
            accepted_flag_shapes[key] = True
            continue
        enabled, shape_supported = _accepted_input_enabled(accepted_inputs.get(key))
        accepted_flags[key] = enabled
        accepted_flag_shapes[key] = shape_supported
    accepted_inputs_known = accepted_inputs_shape_supported and all(accepted_flag_shapes.values())
    agent_input_part_types = []
    if accepted_flags.get("text"):
        agent_input_part_types.append("text")
    agent_input_part_types.extend(key for key in ("image", "audio", "file") if accepted_flags.get(key))
    media_flags = {
        "audio": bool(generation_options.get("generate_audio")),
        "files": bool(generation_options.get("generate_files")),
        "images": bool(generation_options.get("generate_images")),
        "videos": bool(generation_options.get("generate_videos")),
        "simulations": bool(generation_options.get("generate_simulations")),
    }
    raw_variations = test_config.get("num_variations", request.get("num_variations"))
    num_variations = _coerce_positive_int(raw_variations)
    return {
        "num_variations": num_variations,
        "num_variations_known": num_variations is not None,
        "media_generation": media_flags,
        "media_generation_enabled": any(media_flags.values()),
        "accepted_inputs_known": accepted_inputs_known,
        "accepted_input_flags": accepted_flags,
        "agent_input_part_types": agent_input_part_types,
        "agent_input_schema_version": "ashr.clone.agent_input.v1" if any(part_type != "text" for part_type in agent_input_part_types) else None,
        "non_text_inputs_enabled": any(accepted_flags[key] for key in ("audio", "file", "image", "video", "conversation")),
        "small_batch": num_variations is not None and num_variations <= 1,
        "notes": [
            "dry-run-first mutating create_request calibration",
            "use --max-retries 0 for real mutating execution",
            "request params are recorded as shape summaries; raw API responses stay private",
        ],
    }


def enforce_create_request_preflight(preflight: dict[str, Any], *, allow_media_generation: bool, allow_non_text_inputs: bool, max_request_variations: int) -> None:
    if not preflight.get("accepted_inputs_known", True):
        raise ValueError("create-request accepted_inputs shape is unsupported; use booleans or {enabled: bool} before real execution")
    if not preflight.get("num_variations_known"):
        raise ValueError("create-request num_variations is unknown; set test_config.num_variations before real execution")
    if preflight.get("media_generation_enabled") and not allow_media_generation:
        raise ValueError("create-request enables media generation; rerun with --allow-media-generation only after reviewing usage/cost risk")
    if preflight.get("non_text_inputs_enabled") and not allow_non_text_inputs:
        raise ValueError("create-request accepts non-text inputs; rerun with --allow-non-text-inputs only after reviewing usage/cost risk")
    num_variations = preflight.get("num_variations")
    if isinstance(num_variations, int) and num_variations > max_request_variations:
        raise ValueError(f"create-request num_variations={num_variations} exceeds --max-request-variations={max_request_variations}")


def _coerce_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdecimal():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _accepted_input_enabled(value: Any) -> tuple[bool, bool]:
    if value is None:
        return False, True
    if isinstance(value, bool):
        return value, True
    if isinstance(value, dict) and isinstance(value.get("enabled"), bool):
        return value["enabled"], True
    return False, False


MUTATING_OPERATIONS = {"create-run", "create-request"}


if __name__ == "__main__":
    sys.exit(main())
