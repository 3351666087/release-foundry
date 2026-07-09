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
    parser.add_argument("--base-url", help="Optional local hosted adapter base URL for HTTP JSON transport.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Create local tenant/project quota bootstrap state.")
    bootstrap.add_argument("--tenant-name", required=True)
    bootstrap.add_argument("--project-name", required=True)
    bootstrap.add_argument("--tenant-id")
    bootstrap.add_argument("--project-id")
    bootstrap.add_argument("--dataset-id")
    bootstrap.add_argument("--dataset-name", default="SDK Bootstrap Dataset")
    bootstrap.add_argument("--cases-file")

    key_create = subparsers.add_parser("api-key-create", help="Create a redacted local API key record; optionally reveals a one-time local secret.")
    _add_project_args(key_create)
    key_create.add_argument("--name", required=True)
    key_create.add_argument("--scope", action="append", dest="scopes", required=True)
    key_create.add_argument("--key-id")
    key_create.add_argument("--auth-key-id")
    key_create.add_argument("--reveal-secret", action="store_true", help="Return the synthetic local secret once in this command output.")

    key_list = subparsers.add_parser("api-key-list", help="List redacted local API key records.")
    _add_project_args(key_list)
    key_list.add_argument("--auth-key-id")

    key_revoke = subparsers.add_parser("api-key-revoke", help="Revoke a local API key record by id.")
    _add_project_args(key_revoke)
    key_revoke.add_argument("--key-id", required=True)
    key_revoke.add_argument("--auth-key-id")

    key_verify = subparsers.add_parser("api-key-verify", help="Verify a one-time local API key secret against its stored hash.")
    _add_project_args(key_verify)
    key_verify.add_argument("--key-id", required=True)
    key_verify.add_argument("--secret", required=True)
    key_verify.add_argument("--scope")

    key_rate = subparsers.add_parser("api-key-rate-limit", help="Configure a local per-key operation rate limit.")
    _add_project_args(key_rate)
    key_rate.add_argument("--key-id", required=True)
    key_rate.add_argument("--operation", required=True)
    key_rate.add_argument("--limit", required=True, type=int)
    key_rate.add_argument("--period", default="local-window")
    key_rate.add_argument("--auth-key-id")

    key_rate_snapshot = subparsers.add_parser("api-key-rate-limits", help="Read local per-key operation rate-limit buckets.")
    _add_project_args(key_rate_snapshot)
    key_rate_snapshot.add_argument("--key-id")

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

    usage = subparsers.add_parser("usage", help="Read tenant/project usage ledger snapshot.")
    _add_project_args(usage)
    usage.add_argument("--auth-key-id")

    artifact_create = subparsers.add_parser("artifact-manifest-create", help="Store a hash-only artifact manifest receipt for a run.")
    _add_run_args(artifact_create)
    artifact_create.add_argument("--manifest-json")
    artifact_create.add_argument("--manifest-file")
    artifact_create.add_argument("--artifact-id")
    artifact_create.add_argument("--api-key-id")
    _add_ingestion_retry_args(artifact_create)

    artifact_list = subparsers.add_parser("artifact-manifest-list", help="List artifact manifest receipts for a run.")
    _add_run_args(artifact_list)
    artifact_list.add_argument("--auth-key-id")

    audit_verify = subparsers.add_parser("audit-chain-verify", help="Verify the local hosted audit event hash chain.")
    _add_project_args(audit_verify)
    audit_verify.add_argument("--auth-key-id")
    audit_verify.add_argument("--action")
    audit_verify.add_argument("--target-id")
    audit_verify.add_argument("--audit-api-key-id")
    audit_verify.add_argument("--limit", type=int)
    audit_verify.add_argument("--request-id")

    release_verify = subparsers.add_parser("release-evidence-verify", help="Verify a release evidence packet JSON file.")
    _add_run_args(release_verify)
    release_verify.add_argument("--packet-json")
    release_verify.add_argument("--packet-file")
    release_verify.add_argument("--auth-key-id")
    release_verify.add_argument("--request-id")

    release_evidence = subparsers.add_parser("release-evidence", help="Build a public-safe release evidence packet from local control-plane state.")
    _add_run_args(release_evidence)
    release_evidence.add_argument("--auth-key-id")

    state = subparsers.add_parser("state", help="Read a public-safe summary of local client state.")
    state.add_argument("--include-full", action="store_true")

    return parser


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.base_url and args.state_input:
        raise SecretInputError("--base-url cannot be combined with --state-input")
    if args.base_url and args.state_output:
        raise SecretInputError("--base-url cannot be combined with --state-output")
    client = SaaSIngestionClient.from_base_url(args.base_url) if args.base_url else (SaaSIngestionClient.from_state_file(args.state_input) if args.state_input else SaaSIngestionClient())
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
        envelope = client.create_api_key(args.tenant_id, args.project_id, name=args.name, scopes=args.scopes, key_id=args.key_id, auth_key_id=args.auth_key_id, reveal_secret=args.reveal_secret)
    elif command == "api-key-list":
        envelope = client.list_api_keys(args.tenant_id, args.project_id, auth_key_id=args.auth_key_id)
    elif command == "api-key-revoke":
        envelope = client.revoke_api_key(args.tenant_id, args.project_id, args.key_id, auth_key_id=args.auth_key_id)
    elif command == "api-key-verify":
        envelope = client.verify_api_key_secret(args.tenant_id, args.project_id, args.key_id, secret=args.secret, scope=args.scope)
    elif command == "api-key-rate-limit":
        envelope = client.configure_api_key_rate_limit(args.tenant_id, args.project_id, args.key_id, operation=args.operation, limit=args.limit, period=args.period, auth_key_id=args.auth_key_id)
    elif command == "api-key-rate-limits":
        envelope = client.api_key_rate_limit_snapshot(args.tenant_id, args.project_id, key_id=args.key_id)
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
    elif command == "usage":
        envelope = client.usage_snapshot(args.tenant_id, args.project_id, auth_key_id=args.auth_key_id)
    elif command == "artifact-manifest-create":
        envelope = client.create_artifact_manifest(
            args.tenant_id,
            args.project_id,
            args.run_id,
            _load_object_arg(args.manifest_json, args.manifest_file, default={}),
            artifact_id=args.artifact_id,
            api_key_id=args.api_key_id,
            idempotency_key=args.idempotency_key,
            request_id=args.request_id,
        )
    elif command == "artifact-manifest-list":
        envelope = client.list_artifact_manifests(args.tenant_id, args.project_id, args.run_id, auth_key_id=args.auth_key_id)
    elif command == "audit-chain-verify":
        envelope = client.verify_audit_chain(args.tenant_id, args.project_id, auth_key_id=args.auth_key_id, action=args.action, target_id=args.target_id, api_key_id=args.audit_api_key_id, limit=args.limit, request_id=args.request_id)
    elif command == "release-evidence":
        envelope = client.build_release_evidence_packet(args.tenant_id, args.project_id, args.run_id, auth_key_id=args.auth_key_id)
    elif command == "release-evidence-verify":
        packet = _load_object_arg(args.packet_json, args.packet_file, default=None) if (args.packet_json or args.packet_file) else None
        envelope = client.verify_release_evidence_packet(args.tenant_id, args.project_id, args.run_id, packet=packet, auth_key_id=args.auth_key_id, request_id=args.request_id)
    elif command == "state":
        snapshot = client.snapshot_state()
        envelope = {
            "schema_version": "ashr.clone.saas_ingestion_client.v1",
            "operation": "state",
            "result": snapshot if args.include_full else _state_summary(snapshot),
            "metadata": _client_metadata(client),
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


def _client_metadata(client: SaaSIngestionClient) -> dict[str, Any]:
    if client.uses_http:
        return {"local_only": False, "ashr_api_used": False, "raw_auth_material_used": False, "transport": "http"}
    return {"local_only": True, "ashr_api_used": False, "raw_auth_material_used": False}


if __name__ == "__main__":
    sys.exit(main())
