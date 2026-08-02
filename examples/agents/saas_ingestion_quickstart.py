"""Minimal SaaS ingestion SDK quickstart.

Run from the repository root without setting real API keys:

    python -B examples/agents/saas_ingestion_quickstart.py

The example writes local-only JSON state under tmp/ and prints a redacted
lifecycle snapshot. It does not read RELEASEFOUNDRY_API_KEY or RELEASEFOUNDRY_LEGACY_API_KEY.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
for path in (ROOT, SDK_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from releasefoundry.saas import SaaSIngestionClient  # noqa: E402


def main() -> int:
    state_path = ROOT / "tmp" / "a1_saas_ingestion_quickstart_state.json"
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
    state_path.parent.mkdir(parents=True, exist_ok=True)
    client.write_state(state_path)
    lifecycle = client.lifecycle_snapshot("tenant_quickstart", "project_quickstart", "run_quickstart")
    print(json.dumps({"state_path": str(state_path), "lifecycle": lifecycle["result"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
