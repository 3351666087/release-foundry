from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - jsonschema is optional in the light test env
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

ARTIFACT = ROOT / "docs" / "a1" / "go_python_route_contract_evidence.json"
SCHEMA = ROOT / "docs" / "a1" / "schemas" / "go_python_route_contract_evidence.schema.json"
ROUTE_SNAPSHOT = ROOT / "docs" / "a1" / "evidence" / "go_python_ts_route_parity_snapshot.json"
GO_SERVER = ROOT / "packages" / "go" / "ashrclone" / "server.go"
PY_SAAS = ROOT / "packages" / "sdk" / "ashr_clone" / "saas.py"
TS_SAAS = ROOT / "packages" / "ts" / "ashr-clone" / "src" / "saas.ts"


GO_EXECUTABLE_ROUTE_SET = {
    "POST /v1/bootstrap",
    "POST /v1/projects/{project_id}/sdk-submit",
    "POST /v1/projects/{project_id}/worker-jobs/enqueue",
    "POST /v1/projects/{project_id}/worker-jobs/lease",
    "GET /v1/projects/{project_id}/worker-jobs",
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat",
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/complete",
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/fail",
}

PYTHON_TS_SHARED_HOSTED_ROUTES = {
    "POST /v1/bootstrap",
    "POST /v1/projects/{project_id}/api-keys",
    "GET /v1/projects/{project_id}/api-keys",
    "POST /v1/projects/{project_id}/api-keys/{key_id}/verify",
    "POST /v1/projects/{project_id}/api-keys/{key_id}/rate-limit",
    "GET /v1/projects/{project_id}/api-keys/rate-limits",
    "POST /v1/projects/{project_id}/api-keys/{key_id}/revoke",
    "POST /v1/projects/{project_id}/sdk-submit",
    "POST /v1/projects/{project_id}/runs/{run_id}/upload",
    "POST /v1/projects/{project_id}/runs/{run_id}/trace-events",
    "GET /v1/projects/{project_id}/runs/{run_id}/lifecycle",
    "GET /v1/projects/{project_id}/usage",
    "POST /v1/projects/{project_id}/runs/{run_id}/artifact-manifests",
    "GET /v1/projects/{project_id}/runs/{run_id}/artifact-manifests",
    "POST /v1/projects/{project_id}/worker-jobs/enqueue",
    "POST /v1/projects/{project_id}/worker-jobs/lease",
    "GET /v1/projects/{project_id}/worker-jobs",
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat",
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/complete",
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/fail",
    "GET /v1/projects/{project_id}/runs/{run_id}/release-evidence",
    "POST /v1/projects/{project_id}/runs/{run_id}/release-evidence/verify",
    "POST /v1/projects/{project_id}/audit-chain/verify",
}

PYTHON_ROUTE_EXAMPLES = {
    "bootstrap_project": {"project_id": "project_contract", "run_id": "run_contract", "key_id": "key_contract", "job_id": "job_contract"},
    "create_api_key": {"project_id": "project_contract"},
    "list_api_keys": {"project_id": "project_contract"},
    "verify_api_key_secret": {"project_id": "project_contract", "key_id": "key_contract"},
    "configure_api_key_rate_limit": {"project_id": "project_contract", "key_id": "key_contract"},
    "api_key_rate_limit_snapshot": {"project_id": "project_contract"},
    "revoke_api_key": {"project_id": "project_contract", "key_id": "key_contract"},
    "sdk_submit": {"project_id": "project_contract"},
    "upload_run": {"project_id": "project_contract", "run_id": "run_contract"},
    "ingest_trace": {"project_id": "project_contract", "run_id": "run_contract"},
    "lifecycle_snapshot": {"project_id": "project_contract", "run_id": "run_contract"},
    "quota_snapshot": {"project_id": "project_contract"},
    "usage_snapshot": {"project_id": "project_contract"},
    "audit_log": {"project_id": "project_contract"},
    "create_artifact_manifest": {"project_id": "project_contract", "run_id": "run_contract"},
    "list_artifact_manifests": {"project_id": "project_contract", "run_id": "run_contract"},
    "enqueue_worker_job": {"project_id": "project_contract"},
    "lease_worker_job": {"project_id": "project_contract"},
    "list_worker_jobs": {"project_id": "project_contract"},
    "heartbeat_worker_job": {"project_id": "project_contract", "job_id": "job_contract"},
    "complete_worker_job": {"project_id": "project_contract", "job_id": "job_contract"},
    "fail_worker_job": {"project_id": "project_contract", "job_id": "job_contract"},
    "release_evidence": {"project_id": "project_contract", "run_id": "run_contract"},
    "verify_release_evidence_packet": {"project_id": "project_contract", "run_id": "run_contract"},
    "verify_audit_chain": {"project_id": "project_contract"},
}


def _load_artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _load_route_snapshot() -> dict:
    return json.loads(ROUTE_SNAPSHOT.read_text(encoding="utf-8"))




def _go_structured_manifest_entries() -> list[dict]:
    text = GO_SERVER.read_text(encoding="utf-8")
    body_match = re.search(r"func GoRouteManifestEntries\(\) \[\]RouteManifestEntry \{(?P<body>.*?)\n\s*return entries\s*\n\}", text, re.S)
    assert body_match, "GoRouteManifestEntries literal not found"
    entries: list[dict] = []
    for match in re.finditer(r'go(?P<kind>Public|Admin|Scoped)Route\("(?P<method>[A-Z]+)", "(?P<path>[^"]+)", "(?P<operation>[^"]+)", "(?P<category>[^"]+)"(?P<scopes>[^\n]*)\)', body_match.group("body")):
        scopes = re.findall(r"Scope[A-Za-z0-9]+", match.group("scopes"))
        entries.append({
            "kind": match.group("kind"),
            "method": match.group("method"),
            "path": match.group("path"),
            "route": f"{match.group('method')} {match.group('path')}",
            "operation": match.group("operation"),
            "category": match.group("category"),
            "scopes": scopes,
        })
    assert entries, "Go structured manifest entries were not parsed"
    return entries

def _go_manifest_routes() -> set[str]:
    text = GO_SERVER.read_text(encoding="utf-8")
    match = re.search(r"func GoRouteManifestEntries\(\) \[\]RouteManifestEntry \{(?P<body>.*?)\n\}", text, re.S)
    assert match, "Go route manifest entries function not found"
    routes: set[str] = set()
    for call in re.finditer(r'go(?:Public|Admin|Scoped)Route\("(?P<method>[A-Z]+)",\s*"(?P<path>[^"]+)"', match.group("body")):
        routes.add(f"{call.group('method')} {call.group('path')}")
    assert routes, "Go route manifest entries not found"
    return routes


def _python_hosted_routes() -> set[str]:
    from ashr_clone.saas import _operation_route

    routes: set[str] = set()
    for operation, payload in PYTHON_ROUTE_EXAMPLES.items():
        method, path = _operation_route(operation, payload)
        normalized = path.replace("project_contract", "{project_id}").replace("run_contract", "{run_id}").replace("key_contract", "{key_id}").replace("job_contract", "{job_id}")
        routes.add(f"{method} {normalized}")
    return routes


def _ts_openapi_routes() -> set[str]:
    text = TS_SAAS.read_text(encoding="utf-8")
    routes: set[str] = set()
    for path_match in re.finditer(r'"(?P<path>/[^"\n]+)"\s*:\s*\{(?P<body>.*?)(?=\n\s*"/|\n\s*},\n\s*components:)', text, re.S):
        path = path_match.group("path")
        body = path_match.group("body")
        for method in ("get", "post", "put", "patch", "delete"):
            if re.search(rf"\b{method}\s*:", body):
                routes.add(f"{method.upper()} {path}")
    return routes


def test_go_python_route_contract_artifact_matches_schema_shape():
    artifact = _load_artifact()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    for field in schema["required"]:
        assert field in artifact
    assert artifact["schema_version"] == "ashr.clone.go_python_route_contract_evidence.v1"
    assert artifact["public_safe"] is True
    assert artifact["source_policy"]["private_evidence_read"] is False
    assert artifact["source_policy"]["raw_payloads_included"] is False
    assert artifact["source_policy"]["tokens_included"] is False

    if Draft202012Validator is not None:
        Draft202012Validator(schema).validate(artifact)


def test_go_python_route_contract_references_public_existing_paths():
    artifact = _load_artifact()

    paths: set[str] = set()
    for owner in artifact["ownership_summary"]:
        paths.update(owner["primary_paths"])
    for route in artifact["route_contracts"]:
        paths.update(route["producer_paths"])
    for consumer in artifact["consumer_contracts"]:
        paths.update(consumer["stable_inputs"])
    for evidence in artifact["evidence_artifacts"]:
        paths.add(evidence["path"])

    for path in sorted(paths):
        assert not Path(path).is_absolute(), path
        assert "private_refs" not in path, path
        assert not path.startswith(("recon/", "tools/", ".secrets/")), path
        assert (ROOT / path).exists(), path


def test_go_python_route_contract_does_not_leak_private_markers():
    text = ARTIFACT.read_text(encoding="utf-8")

    assert "docs/evidence/private_refs/**" in text
    for marker in ("tp_", "sk-", "Bearer ", "ashr_live_", "raw prompt", "owner@example.com"):
        assert marker not in text


def test_go_python_route_contract_symbols_match_current_source():
    artifact = _load_artifact()
    source_cache: dict[str, str] = {}

    for route in artifact["route_contracts"]:
        source_text = "\n".join(
            source_cache.setdefault(path, (ROOT / path).read_text(encoding="utf-8")) for path in route["producer_paths"]
        )
        for symbol in route["contract_symbols"]:
            if "." in symbol:
                symbol_name = symbol.rsplit(".", 1)[1]
            else:
                symbol_name = symbol
            assert symbol_name in source_text, f"{route['id']} references missing symbol {symbol}"


def test_go_python_route_contract_declares_a2_a3_handoffs():
    artifact = _load_artifact()

    consumers = {entry["consumer"]: entry for entry in artifact["consumer_contracts"]}
    assert set(consumers) == {"a2", "a3"}
    assert any("python.a2_judge_release_contracts" in item for item in consumers["a2"]["can_consume"])
    assert any("Go route family names" in item for item in consumers["a3"]["can_consume"])
    for consumer in consumers.values():
        joined_forbidden = "\n".join(consumer["must_not_consume"])
        assert "private" in joined_forbidden


def test_route_parity_snapshot_is_public_safe_and_current():
    snapshot = _load_route_snapshot()

    assert snapshot["schema_version"] == "ashr.clone.go_python_ts_route_parity_snapshot.v1"
    assert snapshot["public_safe"] is True
    assert snapshot["source_policy"] == {
        "private_evidence_read": False,
        "raw_payloads_included": False,
        "tokens_included": False,
    }
    assert snapshot["source_paths"] == [
        "packages/go/ashrclone/server.go",
        "packages/sdk/ashr_clone/saas.py",
        "packages/ts/ashr-clone/src/saas.ts",
    ]

    assert set(snapshot["go_manifest_routes"]) == _go_manifest_routes()
    assert set(snapshot["python_hosted_routes"]) == _python_hosted_routes()
    assert set(snapshot["ts_openapi_routes"]) == _ts_openapi_routes()


def test_go_manifest_keeps_executable_subset_shared_with_python_and_ts():
    go_routes = _go_manifest_routes()
    python_routes = _python_hosted_routes()
    ts_routes = _ts_openapi_routes()

    assert GO_EXECUTABLE_ROUTE_SET <= go_routes
    assert GO_EXECUTABLE_ROUTE_SET <= python_routes
    assert GO_EXECUTABLE_ROUTE_SET <= ts_routes


def test_python_and_ts_hosted_route_sets_do_not_drift_silently():
    python_routes = _python_hosted_routes()
    ts_routes = _ts_openapi_routes()
    snapshot = _load_route_snapshot()

    assert PYTHON_TS_SHARED_HOSTED_ROUTES <= python_routes
    assert PYTHON_TS_SHARED_HOSTED_ROUTES <= ts_routes
    assert set(snapshot["intentional_route_differences"]["python_only"]) == python_routes - ts_routes
    assert set(snapshot["intentional_route_differences"]["ts_only"]) == ts_routes - python_routes
    assert "POST /v1/projects/{project_id}/runs/{run_id}/release-gate" in snapshot["intentional_route_differences"]["ts_only"]
    assert "GET /v1/projects/{project_id}/quota" in snapshot["intentional_route_differences"]["python_only"]


def test_python_hosted_client_consumes_go_route_scope_manifest_publicly():
    from ashr_clone.saas import consume_go_route_scope_manifest, hosted_route_scope_manifest

    manifest = hosted_route_scope_manifest()
    consumption = consume_go_route_scope_manifest(ROUTE_SNAPSHOT)
    snapshot = _load_route_snapshot()

    assert manifest["schema_version"] == "ashr.clone.hosted_route_scope_manifest.v1"
    assert manifest["public_safe"] is True
    assert consumption["schema_version"] == "ashr.clone.go_route_scope_consumption.v1"
    assert consumption["public_safe"] is True
    assert consumption["source_policy"] == snapshot["source_policy"]

    manifest_routes = {entry["route"] for entry in manifest["routes"]}
    route_scopes = {entry["route"]: tuple(entry["required_scopes"]) for entry in consumption["route_scopes"]}
    assert set(consumption["consumable_go_routes"]) == set(snapshot["go_manifest_routes"]) & manifest_routes
    assert set(consumption["unsupported_go_routes"]) == set(snapshot["go_manifest_routes"]) - manifest_routes
    assert set(consumption["client_only_routes"]) == manifest_routes - set(snapshot["go_manifest_routes"])
    assert route_scopes["POST /v1/projects/{project_id}/sdk-submit"] == ("sdk:submit",)
    assert route_scopes["POST /v1/projects/{project_id}/worker-jobs/lease"] == ("worker_job:write",)
    assert route_scopes["GET /v1/projects/{project_id}/worker-jobs"] == ("worker_job:read",)
    assert route_scopes["GET /v1/projects/{project_id}/runs/{run_id}/release-evidence"] == ("evidence:read",)
    assert "POST /v1/projects/{project_id}/runs/submit" in consumption["unsupported_go_routes"]


def test_go_structured_route_scope_manifest_is_public_safe_and_saas_grade():
    entries = _go_structured_manifest_entries()
    by_route = {entry["route"]: entry for entry in entries}

    assert len(by_route) == len(entries)
    assert by_route["GET /v1/projects/{project_id}/audit-log"]["scopes"] == ["ScopeAuditRead"]
    assert by_route["GET /v1/projects/{project_id}/runs/{run_id}/release-evidence"]["scopes"] == ["ScopeEvidenceRead"]
    assert by_route["POST /v1/projects/{project_id}/runs/{run_id}/trace-events"]["scopes"] == ["ScopeTraceIngest"]
    assert by_route["POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat"]["scopes"] == ["ScopeWorkerJobLease"]

    categories = {entry["category"] for entry in entries}
    assert {"audit", "billing", "release", "trace", "worker", "artifact", "run"} <= categories

    payload = json.dumps(entries, sort_keys=True)
    for forbidden in ("tenant_", "project_contract", "run_contract", "key_contract", "Bearer ", "ASHR_API_KEY", "raw_payload"):
        assert forbidden not in payload


def test_shared_hosted_routes_are_declared_in_route_scope_manifest():
    from ashr_clone.saas import hosted_route_scope_manifest

    manifest_routes = {entry["route"] for entry in hosted_route_scope_manifest()["routes"]}
    assert PYTHON_TS_SHARED_HOSTED_ROUTES <= manifest_routes
