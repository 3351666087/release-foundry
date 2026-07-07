# A1 SaaS ingestion SDK/CLI quickstart

This quickstart exercises the local A1 SaaS ingestion/control-plane client. It is intentionally local-only: do **not** set or paste real API keys. The client uses public `api_key_id` handles for scoped local auth checks and stores only redacted key metadata plus secret digests in local state.

## Python SDK

```python
from ashr_clone.saas import SaaSIngestionClient

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
python -B -m ashr_clone.saas_cli --state-output $state bootstrap --tenant-name "Quickstart Tenant" --project-name "Quickstart Project" --tenant-id tenant_cli --project-id project_cli --dataset-id dataset_cli
python -B -m ashr_clone.saas_cli --state-input $state --state-output $state api-key-create --tenant-id tenant_cli --project-id project_cli --name ingester --scope sdk:submit --scope run:upload --scope trace:ingest --key-id key_cli_ingester
python -B -m ashr_clone.saas_cli --state-input $state --state-output $state sdk-submit --tenant-id tenant_cli --project-id project_cli --dataset-id dataset_cli --agent-ref examples.agents.mock_agent:RespondingMockAgent --run-id run_cli --api-key-id key_cli_ingester
python -B -m ashr_clone.saas_cli --state-input $state --state-output $state run-upload --tenant-id tenant_cli --project-id project_cli --run-id run_cli --upload-id upload_cli --api-key-id key_cli_ingester --result-json '{"run_id":"run_cli","status":"completed"}'
python -B -m ashr_clone.saas_cli --state-input $state --state-output $state trace-ingest --tenant-id tenant_cli --project-id project_cli --run-id run_cli --batch-id trace_cli --api-key-id key_cli_ingester --observations-json '[{"observation_id":"obs_cli_1","type":"agent_message"}]'
python -B -m ashr_clone.saas_cli --state-input $state quota --tenant-id tenant_cli --project-id project_cli
python -B -m ashr_clone.saas_cli --state-input $state lifecycle --tenant-id tenant_cli --project-id project_cli --run-id run_cli
```

## Boundaries

- No hosted Ashr API calls are made by this quickstart.
- Raw API key values are rejected by the SDK surface; use `api_key_id` only.
- `--state-input`, `--metadata-file`, `--result-file`, `--observations-file`, and `--cases-file` refuse `.secrets` and `private_refs` paths.
- A3/A2 remain decoupled: this client records ingestion/lifecycle/quota state and does not import or require A2 judge contracts or A3 fixture exporters.
