# A2 Real API Calibration - 2026-07-09

## Scope

- Lane: A2 Evaluation / Policy / Security.
- Purpose: refresh real ReleaseFoundry API reachability and quota-gated mutating evidence for A2 evidence readiness.
- Public artifacts:
  - `docs/evidence/a2_real_api_smoke.json`
  - `docs/a1/api_calibration/real_api_evidence_index.json`
  - `fixtures/a2/results/a2_evidence_readiness_report.json`

## Real API Calls

- Read-only smoke:
  - Command category: official SDK read-only smoke.
  - Calls: `init`, `health_check`, `list_datasets`, `list_runs`, `list_requests`, `list_agents`.
  - Final status: 6/6 ok after retrying transient SSL EOF failures.
  - Output: redacted summary in `docs/evidence/a2_real_api_smoke.json`.

- Mutating probe:
  - Command category: quota-gated `create-request`.
  - Request type: text-only, one variation, no generated media, no non-text input.
  - Safety controls: private output, `--allow-mutate`, `--max-retries 0`, explicit quota override reason.
  - Status: API returned quota block, `requests 5/5 used`, `requested 1`, `remaining 0`.
  - Private evidence:
    - `docs/evidence/private_refs/a2_real_create_request_text_plan_20260709.json`
    - `docs/evidence/private_refs/a2_real_create_request_text_20260709.json`

## Public-Safe Summary

- `real_api_evidence_index` now includes the new private plan and quota-blocked create-request record.
- Public index label: `a2-real-api-2026-07-09-readonly-and-quota-gated-create-request`.
- Public index counts after refresh: 370 records, 36 `create_request` records, 44 quota blocks.
- No raw payload, API key, authorization header, signed URL, or private response body is committed.

## A2 Interpretation

- Read-only API reachability is current and successful.
- Mutating create-request is blocked by hosted request quota, not by A2 preflight.
- C3 remains blocked until scanner-confirmed 6/6 A2 C3 cases exist and reviewed `releasefoundry_grading` rows are imported.
