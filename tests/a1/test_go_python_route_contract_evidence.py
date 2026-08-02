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
GO_ROUTE_SCOPE_DOCS = ROOT / "docs" / "a1" / "evidence" / "go_route_scope_docs.json"
GO_ROUTE_SCOPE_DOCS_SCHEMA = ROOT / "docs" / "a1" / "schemas" / "go_route_scope_docs.schema.json"
MUTATING_CALIBRATION_INDEX = ROOT / "docs" / "a1" / "evidence" / "official_api_mutating_calibration_index.json"
MUTATING_CALIBRATION_INDEX_SCHEMA = ROOT / "docs" / "a1" / "schemas" / "official_api_mutating_calibration_index.schema.json"
GO_SERVER = ROOT / "packages" / "go" / "releasefoundry" / "server.go"
PY_SAAS = ROOT / "packages" / "sdk" / "releasefoundry" / "saas.py"
TS_SAAS = ROOT / "packages" / "ts" / "releasefoundry" / "src" / "saas.ts"
GO_AUTH = ROOT / "packages" / "go" / "releasefoundry" / "auth.go"


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
    "billing_checkout_plan": {"project_id": "project_contract"},
    "billing_portal_plan": {"project_id": "project_contract"},
    "billing_webhook_ingest": {"project_id": "project_contract"},
    "billing_ledger": {"project_id": "project_contract"},
    "configure_oauth_provider": {"project_id": "project_contract"},
    "create_oauth_session": {"project_id": "project_contract"},
    "revoke_oauth_session": {"project_id": "project_contract", "session_id": "session_contract"},
    "configure_commercial_provider": {"project_id": "project_contract"},
    "record_payment_mode_boundary": {"project_id": "project_contract"},
    "commercial_auth_payment_snapshot": {"project_id": "project_contract"},
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


def _load_go_route_scope_docs() -> dict:
    return json.loads(GO_ROUTE_SCOPE_DOCS.read_text(encoding="utf-8"))


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


def _go_route_scope_docs_fixture() -> dict:
    go_by_operation = {}
    go_scope_values = _go_scope_values()
    for entry in _go_structured_manifest_entries():
        go_by_operation.setdefault(entry["operation"], []).append(entry)

    def group(name: str, operations: list[str]) -> dict:
        routes: set[str] = set()
        scopes: set[str] = set()
        resolved_operations: set[str] = set()
        for operation in operations:
            for entry in go_by_operation.get(operation, []):
                routes.add(entry["route"])
                resolved_operations.add(operation)
                scopes.update(go_scope_values[scope_name] for scope_name in entry["scopes"])
        return {"name": name, "operations": sorted(resolved_operations), "routes": sorted(routes), "scopes": sorted(scopes)}

    return {
        "schema_version": "releasefoundry.go_route_scope_docs.v1",
        "public_safe": True,
        "raw_payloads_included": False,
        "source": "generated_from_go_route_manifest",
        "route_groups": [
            group("usage_quota", ["usage", "usage_quota.configure"]),
            group("run_lifecycle", ["lifecycle"]),
            group("audit", ["audit.chain.verify", "audit_log"]),
        ],
        "plan_limits": [
            {
                "plan": "Developer",
                "cap_mode": "hard_limit",
                "public_url": "https://www.releasefoundry.example/pricing",
                "limits": [
                    {"metric": "graded_scenarios", "limit": 5000, "unit": "scenario"},
                    {"metric": "observations", "limit": 250000, "unit": "observation"},
                    {"metric": "voice_minutes", "limit": 1000, "unit": "minute"},
                    {"metric": "projects", "limit": 1, "unit": "project"},
                ],
            },
            {
                "plan": "Startup",
                "cap_mode": "overage_billing",
                "public_url": "https://www.releasefoundry.example/pricing",
                "limits": [
                    {"metric": "graded_scenarios", "limit": 100000, "unit": "scenario"},
                    {"metric": "observations", "limit": 10000000, "unit": "observation"},
                    {"metric": "voice_minutes", "limit": 50000, "unit": "minute"},
                    {"metric": "projects", "limit": 0, "unit": "unlimited"},
                ],
            },
        ],
        "plan_metrics": [
            {"metric": "graded_scenarios", "unit": "scenario", "operations": ["sdk_submit"], "description": "Run submissions counted as graded scenario units."},
            {"metric": "observations", "unit": "observation", "operations": ["ingest_trace"], "description": "Trace observation rows accepted by the runtime."},
            {"metric": "voice_minutes", "unit": "minute", "operations": ["upload_run", "ingest_trace"], "description": "Voice/media usage documented for quota parity; local runtime records route coverage only."},
            {"metric": "projects", "unit": "project", "operations": ["bootstrap_project"], "description": "Project-count limit reference for billing documentation parity."},
        ],
        "notes": [
            "plan limits are public documentation references, not secret billing state",
            "route groups are derived from GoRouteManifestEntries",
            "captured HTTP bodies and tenant data are intentionally excluded",
        ],
    }


def _go_openapi_route_scope_fixture() -> dict:
    paths: dict[str, dict[str, dict]] = {}
    for route in sorted(_go_manifest_routes()):
        method, path = route.split(" ", 1)
        paths.setdefault(path, {})[method.lower()] = {"operationId": f"fixture_{method.lower()}_{path}"}
    return {
        "schema_version": "releasefoundry.saas_control_plane.v1",
        "manifest_schema_version": "releasefoundry.go_route_scope_manifest.v1",
        "public_safe": True,
        "raw_payloads_included": False,
        "source_policy": {"private_evidence_read": False, "raw_payloads_included": False, "tokens_included": False},
        "paths": paths,
        "route_scope_docs": _go_route_scope_docs_fixture(),
    }

def _go_scope_values() -> dict[str, str]:
    text = GO_AUTH.read_text(encoding="utf-8")
    return {
        match.group("name"): match.group("value")
        for match in re.finditer(r"(?P<name>Scope[A-Za-z0-9_]+)\s*=\s*\"(?P<value>[^\"]+)\"", text)
    }


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
    from releasefoundry.saas import _operation_route

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
    assert artifact["schema_version"] == "releasefoundry.go_python_route_contract_evidence.v1"
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
    for marker in ("tp_", "sk-", "Bearer ", "releasefoundry_live_", "raw prompt", "owner@example.com"):
        assert marker not in text


def test_go_route_scope_docs_artifact_matches_schema_and_public_safety():
    artifact = _load_go_route_scope_docs()
    schema = json.loads(GO_ROUTE_SCOPE_DOCS_SCHEMA.read_text(encoding="utf-8"))

    assert artifact["schema_version"] == "releasefoundry.go_route_scope_docs_artifact.v1"
    assert artifact["artifact_id"] == "go_route_scope_docs"
    assert artifact["owner"] == "a1.go"
    assert artifact["public_safe"] is True
    assert artifact["raw_payloads_included"] is False
    assert artifact["source_policy"] == {
        "private_evidence_read": False,
        "raw_payloads_included": False,
        "tokens_included": False,
        "allowed_source_paths": ["packages/go/releasefoundry/server.go"],
        "excluded_source_classes": [
                "private evidence",
                "tenant fixtures",
                "API keys or bearer tokens",
                "captured HTTP bodies or tenant data",
            ],
        }
    assert artifact["producer"]["stable_export"] == "route_scope_docs"
    assert "GoRouteScopeDocs" in artifact["producer"]["source_symbols"]
    assert artifact["route_scope_docs"] == _go_route_scope_docs_fixture()

    if Draft202012Validator is not None:
        Draft202012Validator(schema).validate(artifact)

    text = GO_ROUTE_SCOPE_DOCS.read_text(encoding="utf-8")
    for marker in ("tenant_", "project_contract", "key_contract", "Bearer ", "RELEASEFOUNDRY_API_KEY", "sk-", "raw_request_payload", "raw_response_payload"):
        assert marker not in text


def test_official_api_mutating_calibration_index_matches_schema_and_modalities():
    artifact = json.loads(MUTATING_CALIBRATION_INDEX.read_text(encoding="utf-8"))
    schema = json.loads(MUTATING_CALIBRATION_INDEX_SCHEMA.read_text(encoding="utf-8"))

    if Draft202012Validator is not None:
        Draft202012Validator(schema).validate(artifact)

    assert artifact["public_safe"] is True
    assert artifact["raw_payloads_included"] is False
    assert artifact["secret_values_included"] is False
    by_modality = {record["summary_modalities"][0]: record for record in artifact["records"]}
    assert set(by_modality) == {"text", "image", "audio", "file", "video"}
    for modality, record in by_modality.items():
        assert record["mutating_step_ids"] == [f"create-request-{modality}"]
        assert record["private_manifest"].startswith("docs/evidence/private_refs/")
        assert record["quota_block_count"] >= 1
        assert record["raw_payloads_included"] is False
    payload = json.dumps(artifact, sort_keys=True)
    for forbidden in ("RELEASEFOUNDRY_API_KEY", "Bearer ", "api_key=", "tp_", "sk-", "customer-private-body"):
        assert forbidden not in payload


def test_go_route_scope_docs_artifact_exports_required_route_families():
    docs = _load_go_route_scope_docs()["route_scope_docs"]
    groups = {group["name"]: group for group in docs["route_groups"]}

    assert set(groups) == {"usage_quota", "run_lifecycle", "audit"}
    assert groups["usage_quota"] == {
        "name": "usage_quota",
        "operations": ["usage", "usage_quota.configure"],
        "routes": ["GET /v1/projects/{project_id}/quota", "GET /v1/projects/{project_id}/usage", "POST /v1/projects/{project_id}/quota/limits", "POST /v1/projects/{project_id}/usage/quotas"],
        "scopes": ["usage:read"],
    }
    assert groups["run_lifecycle"] == {
        "name": "run_lifecycle",
        "operations": ["lifecycle"],
        "routes": ["GET /v1/projects/{project_id}/runs/{run_id}/lifecycle"],
        "scopes": ["run:lifecycle:read"],
    }
    assert groups["audit"] == {
        "name": "audit",
        "operations": ["audit.chain.verify", "audit_log"],
        "routes": [
            "GET /v1/projects/{project_id}/audit-chain/verify",
            "GET /v1/projects/{project_id}/audit-log",
            "POST /v1/projects/{project_id}/audit-chain/verify",
        ],
        "scopes": ["audit:read"],
    }

    go_routes = _go_manifest_routes()
    for group in groups.values():
        assert set(group["routes"]) <= go_routes


def test_go_route_scope_docs_artifact_exposes_public_plan_metrics_for_consumers():
    docs = _load_go_route_scope_docs()["route_scope_docs"]

    plans = {plan["plan"]: plan for plan in docs["plan_limits"]}
    assert set(plans) == {"Developer", "Startup"}
    metric_names = {metric["metric"] for metric in docs["plan_metrics"]}
    assert {"graded_scenarios", "observations", "voice_minutes", "projects"} <= metric_names

    developer_limits = {limit["metric"]: limit for limit in plans["Developer"]["limits"]}
    startup_limits = {limit["metric"]: limit for limit in plans["Startup"]["limits"]}
    assert developer_limits["graded_scenarios"] == {"metric": "graded_scenarios", "limit": 5000, "unit": "scenario"}
    assert developer_limits["observations"] == {"metric": "observations", "limit": 250000, "unit": "observation"}
    assert startup_limits["voice_minutes"] == {"metric": "voice_minutes", "limit": 50000, "unit": "minute"}
    assert startup_limits["projects"] == {"metric": "projects", "limit": 0, "unit": "unlimited"}


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

    assert snapshot["schema_version"] == "releasefoundry.go_python_ts_route_parity_snapshot.v1"
    assert snapshot["public_safe"] is True
    assert snapshot["source_policy"] == {
        "private_evidence_read": False,
        "raw_payloads_included": False,
        "tokens_included": False,
    }
    assert snapshot["source_paths"] == [
        "packages/go/releasefoundry/server.go",
        "packages/sdk/releasefoundry/saas.py",
        "packages/ts/releasefoundry/src/saas.ts",
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
    assert "GET /v1/projects/{project_id}/quota" in snapshot["intentional_route_differences"]["shared_all"]


def test_python_hosted_client_consumes_go_route_scope_manifest_publicly():
    from releasefoundry.saas import consume_go_route_scope_manifest, hosted_route_scope_manifest

    manifest = hosted_route_scope_manifest()
    consumption = consume_go_route_scope_manifest(ROUTE_SNAPSHOT)
    snapshot = _load_route_snapshot()

    assert manifest["schema_version"] == "releasefoundry.hosted_route_scope_manifest.v1"
    assert manifest["public_safe"] is True
    assert consumption["schema_version"] == "releasefoundry.go_route_scope_consumption.v1"
    assert consumption["public_safe"] is True
    assert consumption["source_policy"] == snapshot["source_policy"]

    manifest_routes = {entry["route"] for entry in manifest["routes"]}
    route_scopes = {entry["route"]: tuple(entry["required_scopes"]) for entry in consumption["route_scopes"]}
    assert set(consumption["consumable_go_routes"]) == set(snapshot["go_manifest_routes"]) & manifest_routes
    assert set(consumption["unsupported_go_routes"]) == set(snapshot["go_manifest_routes"]) - manifest_routes
    assert {entry["route"] for entry in consumption["unsupported_go_route_gaps"]} == set(consumption["unsupported_go_routes"])
    assert all(entry["reason"] and entry["consumer_action"] for entry in consumption["unsupported_go_route_gaps"])
    assert set(consumption["client_only_routes"]) == manifest_routes - set(snapshot["go_manifest_routes"])
    assert route_scopes["POST /v1/projects/{project_id}/sdk-submit"] == ("sdk:submit",)
    assert route_scopes["POST /v1/projects/{project_id}/worker-jobs/lease"] == ("worker_job:write",)
    assert route_scopes["GET /v1/projects/{project_id}/worker-jobs"] == ("worker_job:read",)
    assert route_scopes["GET /v1/projects/{project_id}/runs/{run_id}/release-evidence"] == ("evidence:read",)
    assert "POST /v1/projects/{project_id}/runs/submit" in consumption["unsupported_go_routes"]
    assert consumption["route_scope_docs"] is None


def test_python_hosted_client_consumes_go_openapi_route_scope_docs():
    from releasefoundry.saas import consume_go_route_scope_manifest

    openapi = _go_openapi_route_scope_fixture()
    openapi.pop("source_policy")
    consumption = consume_go_route_scope_manifest(openapi)

    assert "GET /v1/projects/{project_id}/usage" in consumption["consumable_go_routes"]
    assert "GET /v1/projects/{project_id}/runs/{run_id}/lifecycle" in consumption["consumable_go_routes"]
    docs = consumption["route_scope_docs"]
    assert docs["schema_version"] == "releasefoundry.go_route_scope_docs.v1"
    assert docs["source"] == "generated_from_go_route_manifest"
    assert docs["route_families"] == ["audit", "run_lifecycle", "usage_quota"]
    assert {"graded_scenarios", "observations", "projects", "voice_minutes"} <= set(docs["plan_metrics"])
    assert docs["plan_limits"] == ["Developer", "Startup"]


def test_python_hosted_client_consumes_future_route_artifact_wrapper():
    from releasefoundry.saas import consume_go_route_scope_manifest

    openapi = _go_openapi_route_scope_fixture()
    wrapped = {
        "schema_version": "releasefoundry.route_artifact.worker.v1",
        "public_safe": True,
        "source_policy": openapi["source_policy"],
        "paths": openapi["paths"],
        "artifact": {"route_scope_docs": openapi["route_scope_docs"]},
    }

    consumption = consume_go_route_scope_manifest(wrapped)
    assert consumption["route_scope_docs"]["route_families"] == ["audit", "run_lifecycle", "usage_quota"]


def test_python_go_openapi_route_scope_docs_reject_route_family_drift():
    from releasefoundry import saas

    openapi = _go_openapi_route_scope_fixture()
    openapi["route_scope_docs"]["route_groups"] = [
        group for group in openapi["route_scope_docs"]["route_groups"] if group["name"] != "usage_quota"
    ]

    try:
        saas.consume_go_route_scope_manifest(openapi)
    except saas.SaaSClientError as exc:
        assert "missing route families: usage_quota" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing Go route scope docs family was accepted")


def test_python_go_route_consumer_rejects_missing_or_stale_unsupported_gap_records(monkeypatch):
    from releasefoundry import saas

    snapshot = _load_route_snapshot()
    original_gaps = dict(saas.UNSUPPORTED_GO_ROUTE_GAPS)
    unsupported_route = "POST /v1/projects/{project_id}/runs/submit"

    missing_gaps = dict(original_gaps)
    missing_gaps.pop(unsupported_route)
    monkeypatch.setattr(saas, "UNSUPPORTED_GO_ROUTE_GAPS", missing_gaps)
    try:
        saas.consume_go_route_scope_manifest(snapshot)
    except saas.SaaSClientError as exc:
        assert "missing=POST /v1/projects/{project_id}/runs/submit" in str(exc)
    else:  # pragma: no cover - assertion aid if the drift check stops firing
        raise AssertionError("missing unsupported Go route gap was accepted")

    stale_gaps = dict(original_gaps)
    stale_gaps["GET /v1/projects/{project_id}/usage"] = {
        "reason": "stale fixture",
        "consumer_action": "should be rejected because the route is hosted",
    }
    monkeypatch.setattr(saas, "UNSUPPORTED_GO_ROUTE_GAPS", stale_gaps)
    try:
        saas.consume_go_route_scope_manifest(snapshot)
    except saas.SaaSClientError as exc:
        assert "stale=GET /v1/projects/{project_id}/usage" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("stale unsupported Go route gap was accepted")


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
    for forbidden in ("tenant_", "project_contract", "run_contract", "key_contract", "Bearer ", "RELEASEFOUNDRY_API_KEY", "raw_payload"):
        assert forbidden not in payload


def test_shared_hosted_routes_are_declared_in_route_scope_manifest():
    from releasefoundry.saas import hosted_route_scope_manifest

    route_scopes = {entry["route"]: entry["required_scopes"] for entry in hosted_route_scope_manifest()["routes"]}
    assert PYTHON_TS_SHARED_HOSTED_ROUTES <= set(route_scopes)
    assert all(isinstance(route_scopes[route], list) for route in PYTHON_TS_SHARED_HOSTED_ROUTES)


def test_shared_go_python_hosted_routes_have_matching_scope_values():
    from releasefoundry.saas import hosted_route_scope_manifest

    go_scope_values = _go_scope_values()
    go_by_route = {entry["route"]: entry for entry in _go_structured_manifest_entries()}
    python_by_route = {entry["route"]: entry for entry in hosted_route_scope_manifest()["routes"]}

    docs_routes = {
        route
        for group in _go_route_scope_docs_fixture()["route_groups"]
        for route in group["routes"]
    }
    task_route_families = {
        "GET /v1/projects/{project_id}/usage",
        "GET /v1/projects/{project_id}/quota",
        "GET /v1/projects/{project_id}/runs/{run_id}/lifecycle",
        "GET /v1/projects/{project_id}/audit-log",
        "POST /v1/projects/{project_id}/audit-chain/verify",
    }
    assert task_route_families <= docs_routes

    shared_routes = PYTHON_TS_SHARED_HOSTED_ROUTES & task_route_families & set(python_by_route)
    assert {
        "GET /v1/projects/{project_id}/usage",
        "GET /v1/projects/{project_id}/runs/{run_id}/lifecycle",
        "POST /v1/projects/{project_id}/audit-chain/verify",
    } <= shared_routes

    for route in sorted(shared_routes):
        go_scope_names = go_by_route[route]["scopes"]
        go_scopes = sorted(go_scope_values[name] for name in go_scope_names)
        assert go_scopes == sorted(python_by_route[route]["required_scopes"]), route
