from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .saas import SaaSIngestionClient, SecretInputError, load_json_file, redacted_error_message


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local-only Ashr SaaS ingestion SDK client CLI.")
    parser.add_argument("--state-input", help="Optional public local control-plane state JSON. .secrets/private_refs are refused.")
    parser.add_argument("--state-output", help="Optional local control-plane state JSON to write after command completion.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Create local tenant/project quota bootstrap state.")
    bootstrap.add_argument("--tenant-name", required=True)
    bootstrap.add_argument("--project-name", required=True)
    bootstrap.add_argument("--tenant-id")
    bootstrap.add_argument("--project-id")
    bootstrap.add_argument("--dataset-id")
    bootstrap.add_argument("--dataset-name", default="SDK Bootstrap Dataset")
    bootstrap.add_argument("--cases-file")

    key_create = subparsers.add_parser("api-key-create", help="Create a redacted local API key record; never returns raw key material.")
    _add_project_args(key_create)
    key_create.add_argument("--name", required=True)
    key_create.add_argument("--scope", action="append", dest="scopes", required=True)
    key_create.add_argument("--key-id")
    key_create.add_argument("--auth-key-id")

    key_list = subparsers.add_parser("api-key-list", help="List redacted local API key records.")
    _add_project_args(key_list)
    key_list.add_argument("--auth-key-id")

    key_revoke = subparsers.add_parser("api-key-revoke", help="Revoke a local API key record by id.")
    _add_project_args(key_revoke)
    key_revoke.add_argument("--key-id", required=True)
    key_revoke.add_argument("--auth-key-id")

    submit = subparsers.add_parser("sdk-submit", help="Create a local SDK-submitted queued run.")
    _add_project_args(submit)
    submit.add_argument("--dataset-id", required=True)
    submit.add_argument("--agent-ref", required=True)
    submit.add_argument("--run-id")
    submit.add_argument("--metadata-json")
    submit.add_argument("--metadata-file")
    submit.add_argument("--api-key-id")
    _add_ingestion_retry_args(submit)

    upload = subparsers.add_parser("run-upload", help="Store a redacted local run-result upload record.")
    _add_run_args(upload)
    upload.add_argument("--upload-id")
    upload.add_argument("--result-json")
    upload.add_argument("--result-file")
    upload.add_argument("--api-key-id")
    _add_ingestion_retry_args(upload)

    trace = subparsers.add_parser("trace-ingest", help="Append local trace observations to a run.")
    _add_run_args(trace)
    trace.add_argument("--batch-id")
    trace.add_argument("--observations-json")
    trace.add_argument("--observations-file")
    trace.add_argument("--api-key-id")
    _add_ingestion_retry_args(trace)

    lifecycle = subparsers.add_parser("lifecycle", help="Read tenant/project/run lifecycle state.")
    _add_run_args(lifecycle)

    quota = subparsers.add_parser("quota", help="Read tenant/project quota snapshot.")
    _add_project_args(quota)

    state = subparsers.add_parser("state", help="Read a public-safe summary of local client state.")
    state.add_argument("--include-full", action="store_true")

    return parser


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    client = SaaSIngestionClient.from_state_file(args.state_input) if args.state_input else SaaSIngestionClient()
    command = args.command
    if command == "bootstrap":
        cases = _load_optional_array(args.cases_file)
        envelope = client.bootstrap_project(
            tenant_name=args.tenant_name,
            project_name=args.project_name,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            dataset_id=args.dataset_id,
            dataset_name=args.dataset_name,
            cases=cases,
        )
    elif command == "api-key-create":
        envelope = client.create_api_key(args.tenant_id, args.project_id, name=args.name, scopes=args.scopes, key_id=args.key_id, auth_key_id=args.auth_key_id)
    elif command == "api-key-list":
        envelope = client.list_api_keys(args.tenant_id, args.project_id, auth_key_id=args.auth_key_id)
    elif command == "api-key-revoke":
        envelope = client.revoke_api_key(args.tenant_id, args.project_id, args.key_id, auth_key_id=args.auth_key_id)
    elif command == "sdk-submit":
        envelope = client.sdk_submit(
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
        envelope = client.upload_run(
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
        envelope = client.ingest_trace(
            args.tenant_id,
            args.project_id,
            args.run_id,
            _load_array_arg(args.observations_json, args.observations_file),
            batch_id=args.batch_id,
            api_key_id=args.api_key_id,
            idempotency_key=args.idempotency_key,
            request_id=args.request_id,
        )
    elif command == "lifecycle":
        envelope = client.lifecycle_snapshot(args.tenant_id, args.project_id, args.run_id)
    elif command == "quota":
        envelope = client.quota_snapshot(args.tenant_id, args.project_id)
    elif command == "state":
        snapshot = client.snapshot_state()
        envelope = {
            "schema_version": "ashr.clone.saas_ingestion_client.v1",
            "operation": "state",
            "result": snapshot if args.include_full else _state_summary(snapshot),
            "metadata": {"local_only": True, "ashr_api_used": False, "raw_auth_material_used": False},
        }
    else:  # pragma: no cover
        raise SecretInputError(f"unsupported command: {command}")

    if args.state_output:
        envelope["state_output"] = client.write_state(args.state_output)
    return envelope


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run_command(args), sort_keys=True))
        return 0
    except Exception as exc:
        parser.exit(2, f"saas ingestion cli error: {redacted_error_message(exc)}\n")
    return 0


def _add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    _add_project_args(parser)
    parser.add_argument("--run-id", required=True)


def _add_ingestion_retry_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--idempotency-key")
    parser.add_argument("--request-id")


def _load_object_arg(raw_json: str | None, path: str | None, *, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if raw_json and path:
        raise SecretInputError("provide either inline JSON or a JSON file, not both")
    if path:
        payload = load_json_file(path)
    elif raw_json:
        payload = json.loads(raw_json)
    else:
        payload = dict(default or {})
    if not isinstance(payload, Mapping):
        raise SecretInputError("JSON payload must be an object")
    return dict(payload)


def _load_array_arg(raw_json: str | None, path: str | None) -> list[Mapping[str, Any]]:
    if raw_json and path:
        raise SecretInputError("provide either inline JSON or a JSON file, not both")
    if path:
        payload = load_json_file(path)
    elif raw_json:
        payload = json.loads(raw_json)
    else:
        raise SecretInputError("trace-ingest requires --observations-json or --observations-file")
    if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
        raise SecretInputError("observations payload must be a list of objects")
    return payload


def _load_optional_array(path: str | None) -> list[Mapping[str, Any]] | None:
    if not path:
        return None
    payload = load_json_file(path)
    if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
        raise SecretInputError("cases file must contain a list of objects")
    return payload


def _state_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    cloud = snapshot.get("cloud") if isinstance(snapshot.get("cloud"), Mapping) else {}
    store = cloud.get("store") if isinstance(cloud.get("store"), Mapping) else {}
    control = snapshot.get("control_plane") if isinstance(snapshot.get("control_plane"), Mapping) else {}
    return {
        "cloud_counts": {name: len(value) for name, value in store.items() if isinstance(value, Mapping)},
        "control_plane_counts": {name: len(value) for name, value in control.items() if isinstance(value, Mapping)},
    }


if __name__ == "__main__":
    sys.exit(main())
