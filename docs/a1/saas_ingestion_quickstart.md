# A1 SaaS ingestion SDK/CLI quickstart

This quickstart exercises the local A1 SaaS ingestion/control-plane client. It is intentionally local-only: do **not** set or paste real API keys. The client uses public `api_key_id` handles for scoped local auth checks and stores only redacted key metadata plus secret digests in local state.

## Python SDK

```python
from releasefoundry.saas import SaaSIngestionClient

client = SaaSIngestionClient()
client.bootstrap_project(
    tenant_name="Quickstart Tenant",
    project_name="Quickstart Project",
    tenant_id="tenant_quickstart",
    project_id="project_quickstart",
    dataset_id="dataset_quickstart",
)
client.create_api_key(
    "tenant_quickstart",
    "project_quickstart",
    name="Local ingestion key handle",
    scopes=["sdk:submit", "run:upload", "trace:ingest"],
    key_id="key_quickstart_ingester",
)
client.sdk_submit(
    "tenant_quickstart",
    "project_quickstart",
    dataset_id="dataset_quickstart",
    agent_ref="examples.agents.mock_agent:RespondingMockAgent",
    run_id="run_quickstart",
    api_key_id="key_quickstart_ingester",
)
client.upload_run(
    "tenant_quickstart",
    "project_quickstart",
    "run_quickstart",
    {"run_id": "run_quickstart", "status": "completed", "score": 1.0},
    upload_id="upload_quickstart",
    api_key_id="key_quickstart_ingester",
)
client.ingest_trace(
    "tenant_quickstart",
    "project_quickstart",
    "run_quickstart",
    [{"observation_id": "obs_quickstart_1", "type": "agent_message", "content": "hello"}],
    batch_id="trace_quickstart",
    api_key_id="key_quickstart_ingester",
)
print(client.quota_snapshot("tenant_quickstart", "project_quickstart"))
```

Runnable example:

```powershell
$env:PYTHONPATH="packages/sdk;."
python -B examples/agents/saas_ingestion_quickstart.py
```

## CLI

```powershell
$env:PYTHONPATH="packages/sdk;."
$state="tmp/a1_saas_ingestion_cli_state.json"
python -B -m releasefoundry.saas_cli --state-output $state bootstrap --tenant-name "Quickstart Tenant" --project-name "Quickstart Project" --tenant-id tenant_cli --project-id project_cli --dataset-id dataset_cli
python -B -m releasefoundry.saas_cli --state-input $state --state-output $state api-key-create --tenant-id tenant_cli --project-id project_cli --name ingester --scope sdk:submit --scope run:upload --scope trace:ingest --key-id key_cli_ingester
python -B -m releasefoundry.saas_cli --state-input $state --state-output $state sdk-submit --tenant-id tenant_cli --project-id project_cli --dataset-id dataset_cli --agent-ref examples.agents.mock_agent:RespondingMockAgent --run-id run_cli --api-key-id key_cli_ingester
python -B -m releasefoundry.saas_cli --state-input $state --state-output $state run-upload --tenant-id tenant_cli --project-id project_cli --run-id run_cli --upload-id upload_cli --api-key-id key_cli_ingester --result-json '{"run_id":"run_cli","status":"completed"}'
python -B -m releasefoundry.saas_cli --state-input $state --state-output $state trace-ingest --tenant-id tenant_cli --project-id project_cli --run-id run_cli --batch-id trace_cli --api-key-id key_cli_ingester --observations-json '[{"observation_id":"obs_cli_1","type":"agent_message"}]'
python -B -m releasefoundry.saas_cli --state-input $state quota --tenant-id tenant_cli --project-id project_cli
python -B -m releasefoundry.saas_cli --state-input $state lifecycle --tenant-id tenant_cli --project-id project_cli --run-id run_cli
```

## API key lifecycle controls

Round19 adds local API-key lifecycle controls that are shaped like a hosted SaaS control plane but remain secret-safe by default:

- `api-key-create` returns redacted metadata unless `--reveal-secret` is set. When enabled, the synthetic local secret is returned once and the stored record keeps only a SHA-256 hash plus `secret_hash_present=true`.
- `api-key-verify` checks a one-time local secret against the stored hash and can optionally authenticate a required scope.
- `api-key-rate-limit` configures a per-key operation bucket such as `sdk:submit` or `run:upload`; ingestion consumes the bucket before mutating run state.
- `api-key-rate-limits` returns used/remaining counts for audit and quota-ledger views.

Example:

```powershell
$created = python -B -m releasefoundry.saas_cli --state-input $state --state-output $state api-key-create --tenant-id tenant_cli --project-id project_cli --name limited --scope sdk:submit --key-id key_cli_limited --reveal-secret | ConvertFrom-Json
$secret = $created.result.one_time_secret
python -B -m releasefoundry.saas_cli --state-input $state --state-output $state api-key-verify --tenant-id tenant_cli --project-id project_cli --key-id key_cli_limited --secret $secret --scope sdk:submit
python -B -m releasefoundry.saas_cli --state-input $state --state-output $state api-key-rate-limit --tenant-id tenant_cli --project-id project_cli --key-id key_cli_limited --operation sdk:submit --limit 30
python -B -m releasefoundry.saas_cli --state-input $state api-key-rate-limits --tenant-id tenant_cli --project-id project_cli --key-id key_cli_limited
```

The SDK equivalent is `SaaSIngestionClient.create_api_key(..., reveal_secret=True)`, `verify_api_key_secret(...)`, `configure_api_key_rate_limit(...)`, and `api_key_rate_limit_snapshot(...)`. This local surface does not read `RELEASEFOUNDRY_API_KEY`; official API calibration remains isolated in private evidence records.

## Boundaries

- No hosted ReleaseFoundry API calls are made by this quickstart.
- Raw API key values are rejected by the SDK surface; use `api_key_id` only.
- `--state-input`, `--metadata-file`, `--result-file`, `--observations-file`, and `--cases-file` refuse `.secrets` and `private_refs` paths.
- A3/A2 remain decoupled: this client records ingestion/lifecycle/quota state and does not import or require A2 judge contracts or A3 fixture exporters.

## Hosted/self-host HTTP adapter

Round17 adds a framework-free WSGI adapter for the same local SaaS control-plane contract. This moves A1 from only an in-process router toward a self-hostable API platform surface while still avoiding real ReleaseFoundry API calls and raw key material.

```python
from services.api import serve_control_plane_http

server = serve_control_plane_http("127.0.0.1", 8080)
server.serve_forever()
```

Public endpoints include `GET /healthz`, `GET /openapi.json`, and the existing `/v1/projects/{project_id}/...` ingestion routes for API key handles, key secret verification, per-key rate limits, SDK submit, run upload, trace ingestion, and lifecycle snapshots. Round20 adds `POST /v1/projects/{project_id}/runs/{run_id}/release-gate`, which evaluates the lifecycle snapshot through a registered local release-gate evaluator or the deterministic local stub, and `GET /v1/projects/{project_id}/audit-log`, which queries public-safe audit events for API-key, rate-limit, ingestion, and release-gate actions. The adapter never reads `RELEASEFOUNDRY_API_KEY`; auth remains the local `api_key_id` handle contract.

Example local HTTP release-gate and audit calls:

```powershell
$body = @{ tenant_id = "tenant_cli"; api_key_id = "key_cli_gate"; request_id = "req_cli_gate"; idempotency_key = "idem_cli_gate"; policy = @{ minimum_uploads = 1; minimum_trace_batches = 1 } } | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/v1/projects/project_cli/runs/run_cli/release-gate" -ContentType "application/json" -Body $body
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/v1/projects/project_cli/audit-log?tenant_id=tenant_cli&api_key_id=key_cli_gate&action=release_gate.evaluate&target_id=run_cli"
```

The Python SDK can target the hosted adapter with `SaaSIngestionClient.from_base_url("http://127.0.0.1:8080")`, and the CLI accepts `--base-url` for HTTP JSON transport. `--base-url` is intentionally mutually exclusive with local state file read/write flags.


## Release evidence packet

Round20 adds `build_release_evidence_packet(...)` for the commercial release-review loop. It accepts a lifecycle snapshot, artifact manifest, release-gate result, webhook delivery summary, and usage rollup, then emits a public-safe bundle with counts, hashes, usage totals, release-gate status, and an integrity digest. The packet intentionally omits raw run payloads, trace bodies, webhook secrets, and official API private evidence.

Expected flow:

```text
SDK submit -> run upload -> trace ingest -> artifact manifest -> release gate -> webhook delivery -> release evidence packet
```

This packet is shaped for A3 review surfaces and enterprise audit export while keeping A2 judge semantics outside A1.

## SaaS platform primitives

Round18 adds local commercial SaaS primitives below the hosted control-plane HTTP surface:

- `platform_schema_manifest()` and `platform_sql_migration_text()` describe DB-shaped tables and tenant-scoped indexes for organizations, workspaces, projects, environments, datasets, runs, case results, trace events, observations, artifacts, evidence bundles, API keys, webhook endpoints, usage ledger, quota policies, billing accounts, integrations, and audit log.
- `LocalObjectStore` records artifact metadata with `sha256`, `content_type`, `size_bytes`, tenant/project/run references, and `raw_payload_included=false`; it can issue local signed-upload placeholders.
- `WebhookRegistry` registers public-safe endpoints, stores only local secret handles/hashes, signs simulated deliveries with HMAC, and records delivery logs without raw payloads.
- `usage_billing_rollup()` turns usage ledger events into a billing-period operation summary.
- `release_gate_bridge_payload()` produces an A2-facing release-gate bridge payload from an A1 lifecycle snapshot.

These primitives are still local/self-host contract surfaces, not production Postgres/S3/webhook infrastructure. They make the migration path explicit and testable without calling mutating ReleaseFoundry APIs or storing secrets.
