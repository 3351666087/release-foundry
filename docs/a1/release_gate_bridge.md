# A1 Worker Release-Gate Bridge

This A1 bridge turns a control-plane lifecycle snapshot into the existing `release_gate_bridge_payload` shape and submits it to an A2 release-gate evaluator.

## Scope

Implemented under `services/api/**` with tests in `tests/a1/**`. It is intentionally local/self-host friendly:

- no environment-key reads;
- no dependency beyond the Python standard library;
- no access to `recon/**`, `tools/**`, or private references;
- no raw lifecycle payload bytes in public response envelopes.

## Contract

`lifecycle_to_release_gate_request(...)` wraps `release_gate_bridge_payload(...)` with bridge metadata:

- `target_contract`: `A2.release_gate.evaluate`
- `request_id`: caller-provided or generated ID propagated to A2
- `idempotency_key`: caller-provided or stable hash over the A2 payload
- `bridge.timeout_seconds`: positive timeout budget
- `raw_payload_included`: `false`

The A2 response must be GradeResult-like and include:

```json
{
  "scenario_id": "run_id or scenario id",
  "passed": true,
  "score": 1.0,
  "label": "release_gate_pass",
  "reason": "human-readable reason",
  "expected": {},
  "actual": {},
  "metrics": {}
}
```

An A2 service may also return `{ "grade_result": { ... } }`; both forms normalize to `grade_result` in the bridge result.

## Local callable client

```python
from services.api import LocalReleaseGateBridgeClient, evaluate_lifecycle_with_release_gate


def evaluator(payload):
    return {
        "scenario_id": payload["run_id"],
        "passed": payload["decision_hint"] == "pass",
        "score": 1.0 if payload["decision_hint"] == "pass" else 0.0,
        "label": "release_gate_pass",
        "reason": "A2 self-host evaluator accepted the A1 lifecycle payload",
        "expected": payload["policy"],
        "actual": payload["inputs"],
        "metrics": {"target_contract": payload["target_contract"]},
    }

client = LocalReleaseGateBridgeClient(evaluator)
result = evaluate_lifecycle_with_release_gate(
    client,
    tenant_id="tenant_1",
    project_id="project_1",
    run_id="run_1",
    lifecycle=lifecycle_snapshot,
    request_id="req_123",
    idempotency_key="idem_123",
    timeout_seconds=5,
)
```

The local client caches successful results by `idempotency_key`, so retries do not call the evaluator again.

## Control-plane HTTP route

Round20 exposes release-gate evaluation as a first-class local control-plane route:

```http
POST /v1/projects/{project_id}/runs/{run_id}/release-gate
```

Request body/query fields:

```json
{
  "tenant_id": "tenant_1",
  "api_key_id": "key_release_gate",
  "request_id": "req_123",
  "idempotency_key": "idem_123",
  "timeout_seconds": 5,
  "policy": {"minimum_uploads": 1, "minimum_trace_batches": 1}
}
```

The route reads the run lifecycle snapshot, converts it through `lifecycle_to_release_gate_request(...)`, and evaluates it with a registered `LocalReleaseGateBridgeClient` evaluator. If no evaluator is registered, the control plane uses a deterministic local stub that gates only on public lifecycle counts (`upload_count`, `trace_batch_count`) and run status. It does not import A2 judge code, call hosted Ashr APIs, or expose raw lifecycle payloads.

Successful responses keep the normalized bridge envelope and add local control-plane metadata:

```json
{
  "schema_version": "ashr.clone.saas_control_plane.v1",
  "target_contract": "A2.release_gate.evaluate",
  "transport": "local_callable",
  "local_only": true,
  "ashr_api_used": false,
  "grade_result": {"passed": true, "score": 1.0}
}
```

Each evaluation appends a public-safe `release_gate.evaluate` audit event keyed by the run id, request id, and idempotency key.

## Audit query route

Audit events for API-key lifecycle, per-key rate-limit configuration, ingestion, and release-gate evaluation are available through:

```http
GET /v1/projects/{project_id}/audit-log?tenant_id=tenant_1&action=release_gate.evaluate&target_id=run_1&limit=20
```

The route accepts `auth_key_id`/`api_key_id` for `audit:read` enforcement, `action`, `target_id`, `audit_api_key_id`, and `limit`. Events include hashes of before/after payloads only; raw secrets, raw uploaded results, and raw trace payloads are not returned.

## HTTP client

```python
from services.api import HttpReleaseGateBridgeClient, evaluate_lifecycle_with_release_gate

client = HttpReleaseGateBridgeClient("http://127.0.0.1:8080/release-gate", timeout_seconds=5)
result = evaluate_lifecycle_with_release_gate(
    client,
    tenant_id="tenant_1",
    project_id="project_1",
    run_id="run_1",
    lifecycle=lifecycle_snapshot,
    request_id="req_123",
    idempotency_key="idem_123",
)
```

The HTTP client uses `urllib.request` and sends:

- `content-type: application/json`
- `accept: application/json`
- `x-request-id: <request_id>`
- `idempotency-key: <idempotency_key>`

Successful HTTP results are cached by `idempotency_key` in the client instance.

## Redaction and errors

The bridge recursively redacts sensitive keys and common inline secret patterns before sending payloads or surfacing errors. Redacted keys/patterns include API keys, authorization/bearer material, secrets, tokens, passwords, and credentials.

Errors are public-safe exception types:

- `ReleaseGateBridgeTimeout`
- `ReleaseGateBridgeResponseError`
- `ReleaseGateBridgeError`

Each exposes `to_dict()` with `code`, redacted `message`, optional `request_id`, and optional HTTP `status_code`.
