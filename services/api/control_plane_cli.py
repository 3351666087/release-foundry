from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Sequence

from packages.sdk.ashr_clone.api_client import redact_text

from .control_plane import (
    CONTROL_PLANE_SCHEMA_VERSION,
    SaaSControlPlaneService,
    control_plane_from_state_file,
    snapshot_control_plane,
    write_control_plane_state,
)
from .runtime import JsonDict, ValidationError

BLOCKED_INPUT_PATH_PARTS = {".secrets", "private_refs"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local-only Ashr SaaS control-plane bootstrap and ingestion CLI."
    )
    parser.add_argument(
        "--state-input",
        help="Optional local control-plane JSON state to read. Refuses .secrets/private_refs paths.",
    )
    parser.add_argument(
        "--state-output",
        help="Optional local control-plane JSON state path to write after the command.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Create tenant/project quota bootstrap state.")
    bootstrap.add_argument("--tenant-name", required=True)
    bootstrap.add_argument("--project-name", required=True)
    bootstrap.add_argument("--tenant-id")
    bootstrap.add_argument("--project-id")
    bootstrap.add_argument("--dataset-id")
    bootstrap.add_argument("--dataset-name", default="CLI Bootstrap Dataset")

    submit = subparsers.add_parser("sdk-submit", help="Create a local SDK-submitted queued run.")
    _add_project_args(submit)
    submit.add_argument("--dataset-id", required=True)
    submit.add_argument("--agent-ref", required=True)
    submit.add_argument("--run-id")
    submit.add_argument("--metadata-json")
    submit.add_argument("--metadata-file")
    _add_ingestion_auth_args(submit)

    upload = subparsers.add_parser("run-upload", help="Store a redacted local run-result upload record.")
    _add_run_args(upload)
    upload.add_argument("--upload-id")
    upload.add_argument("--result-json")
    upload.add_argument("--result-file")
    _add_ingestion_auth_args(upload)

    trace = subparsers.add_parser("trace-ingest", help="Append local trace observations to a run.")
    _add_run_args(trace)
    trace.add_argument("--batch-id")
    trace.add_argument("--observations-json")
    trace.add_argument("--observations-file")
    _add_ingestion_auth_args(trace)

    lifecycle = subparsers.add_parser("lifecycle-snapshot", help="Read tenant/project/run lifecycle state.")
    _add_run_args(lifecycle)

    state_read = subparsers.add_parser("state-read", help="Read and print a local public-safe state snapshot.")
    state_read.add_argument("--include-full", action="store_true", help="Include the full local state payload.")

    subparsers.add_parser("state-write", help="Write the current local state to --state-output.")

    key_create = subparsers.add_parser("api-key-create", help="Create a redacted local API key governance record.")
    _add_project_args(key_create)
    key_create.add_argument("--name", required=True)
    key_create.add_argument("--scope", action="append", dest="scopes", required=True)
    key_create.add_argument("--key-id")
    key_create.add_argument("--auth-key-id")

    key_list = subparsers.add_parser("api-key-list", help="List redacted local API key governance records.")
    _add_project_args(key_list)
    key_list.add_argument("--auth-key-id")

    key_revoke = subparsers.add_parser("api-key-revoke", help="Revoke a local API key governance record.")
    _add_project_args(key_revoke)
    key_revoke.add_argument("--key-id", required=True)
    key_revoke.add_argument("--auth-key-id")

    return parser


def _add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    _add_project_args(parser)
    parser.add_argument("--run-id", required=True)


def _add_ingestion_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-key-id")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--request-id")


def load_control_plane_state(path: str | None) -> SaaSControlPlaneService:
    if not path:
        return SaaSControlPlaneService()
    _assert_public_input_path(path)
    return control_plane_from_state_file(path)


def run_command(args: argparse.Namespace) -> JsonDict:
    service = load_control_plane_state(args.state_input)
    command = args.command
    if command == "bootstrap":
        result = service.bootstrap_project(
            tenant_name=args.tenant_name,
            project_name=args.project_name,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
        )
        if args.dataset_id:
            result["dataset"] = service.cloud.create_dataset(
                result["tenant"]["tenant_id"],
                result["project"]["project_id"],
                name=args.dataset_name,
                dataset_id=args.dataset_id,
                cases=[{"id": "cli-bootstrap-case", "prompt": "local bootstrap", "expected": {"text": "local bootstrap"}}],
            )
    elif command == "sdk-submit":
        result = service.sdk_submit_run(
            args.tenant_id,
            args.project_id,
            dataset_id=args.dataset_id,
            agent_ref=args.agent_ref,
            run_id=args.run_id,
            metadata=_load_object_arg(args.metadata_json, args.metadata_file, default={}),
            api_key_id=args.api_key_id,
            idempotency_key=args.idempotency_key,
            request_id=args.request_id,
        )
    elif command == "run-upload":
        result = service.upload_run_result(
            args.tenant_id,
            args.project_id,
            args.run_id,
            _load_object_arg(args.result_json, args.result_file, default={}),
            upload_id=args.upload_id,
            api_key_id=args.api_key_id,
            idempotency_key=args.idempotency_key,
            request_id=args.request_id,
        )
    elif command == "trace-ingest":
        observations = _load_array_arg(args.observations_json, args.observations_file)
        result = service.ingest_trace(
            args.tenant_id,
            args.project_id,
            args.run_id,
            observations,
            batch_id=args.batch_id,
            api_key_id=args.api_key_id,
            idempotency_key=args.idempotency_key,
            request_id=args.request_id,
        )
    elif command == "lifecycle-snapshot":
        result = service.lifecycle_snapshot(args.tenant_id, args.project_id, args.run_id)
    elif command == "state-read":
        snapshot = snapshot_control_plane(service)
        result = snapshot if args.include_full else _state_summary(snapshot)
    elif command == "state-write":
        result = _state_summary(snapshot_control_plane(service))
    elif command == "api-key-create":
        result = service.create_api_key(
            args.tenant_id,
            args.project_id,
            name=args.name,
            scopes=list(args.scopes),
            key_id=args.key_id,
            auth_key_id=args.auth_key_id,
        )
    elif command == "api-key-list":
        result = {"api_keys": service.list_api_keys(args.tenant_id, args.project_id, auth_key_id=args.auth_key_id)}
    elif command == "api-key-revoke":
        result = service.revoke_api_key(args.tenant_id, args.project_id, args.key_id, auth_key_id=args.auth_key_id)
    else:  # pragma: no cover - argparse prevents this branch.
        raise ValidationError(f"unsupported control-plane command: {command}")

    envelope: JsonDict = {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "command": command,
        "result": result,
        "metadata": {"local_only": True, "ashr_api_used": False},
    }
    if args.state_output:
        envelope["state_output"] = write_control_plane_state(service, args.state_output)
    return envelope


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        envelope = run_command(args)
        print(json.dumps(envelope, sort_keys=True))
        return 0
    except Exception as exc:
        parser.exit(2, f"control-plane cli error: {redact_text(str(exc))}\n")
    return 0


def invoke_json(argv: Sequence[str]) -> JsonDict:
    """Test/helper entrypoint returning parsed JSON without touching hosted APIs."""

    stdout = StringIO()
    with redirect_stdout(stdout):
        code = main(argv)
    if code != 0:
        raise RuntimeError(f"control-plane cli exited with {code}")
    return json.loads(stdout.getvalue())


def _load_object_arg(raw_json: str | None, path: str | None, *, default: Mapping[str, Any] | None = None) -> JsonDict:
    if raw_json and path:
        raise ValidationError("provide either inline JSON or a JSON file, not both")
    if path:
        payload = _read_json_file(path)
    elif raw_json:
        payload = json.loads(raw_json)
    else:
        payload = dict(default or {})
    if not isinstance(payload, Mapping):
        raise ValidationError("JSON payload must be an object")
    return dict(payload)


def _load_array_arg(raw_json: str | None, path: str | None) -> list[Mapping[str, Any]]:
    if raw_json and path:
        raise ValidationError("provide either inline JSON or a JSON file, not both")
    if path:
        payload = _read_json_file(path)
    elif raw_json:
        payload = json.loads(raw_json)
    else:
        raise ValidationError("trace-ingest requires --observations-json or --observations-file")
    if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
        raise ValidationError("observations payload must be a list of objects")
    return payload


def _read_json_file(path: str) -> Any:
    _assert_public_input_path(path)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _assert_public_input_path(path: str) -> None:
    parts = {part.lower() for part in Path(path).parts}
    if parts & BLOCKED_INPUT_PATH_PARTS:
        raise ValidationError("refusing to read private_refs or .secrets input paths")


def _state_summary(snapshot: Mapping[str, Any]) -> JsonDict:
    cloud = snapshot.get("cloud") if isinstance(snapshot.get("cloud"), Mapping) else {}
    store = cloud.get("store") if isinstance(cloud.get("store"), Mapping) else {}
    control = snapshot.get("control_plane") if isinstance(snapshot.get("control_plane"), Mapping) else {}
    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "cloud_counts": {name: len(value) for name, value in store.items() if isinstance(value, Mapping)},
        "control_plane_counts": {name: len(value) for name, value in control.items() if isinstance(value, Mapping)},
        "metadata": {"local_only": True, "ashr_api_used": False},
    }


if __name__ == "__main__":
    sys.exit(main())
