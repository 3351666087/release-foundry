# A1 API Calibration

Round date: 2026-07-04

This folder records public, non-sensitive summaries from subscription-era A1 calibration. Raw API records and dashboard screenshots are kept under `docs/evidence/private_refs/`, which is locally ignored and must not be committed.

## Safety Contract

- API keys are read only from `ASHR_API_KEY` or the official SDK-compatible `ASHR_LABS_API_KEY`.
- Optional base URL override follows `ASHR_LABS_BASE_URL`.
- The probe CLI defaults to dry-run and writes a call plan before any real call.
- Real calls require `--execute`.
- Mutating operations, currently `create-request` and `create-run`, additionally require `--allow-mutate`.
- Records redact sensitive keys and selected headers; committed docs must contain only field names, counts, command summaries, and private evidence paths.

## Probe Surface

Implemented in `packages/sdk/ashr_clone/api_client.py` and `services/runner/api_probe.py`:

- `init`
- `list-datasets`
- `get-dataset`
- `list-runs`
- `get-run`
- `poll-run`
- `list-requests`
- `get-request`
- `poll-request`
- `create-request`
- `create-run`

The client follows the observed official Python SDK shape: one POST endpoint at `https://api.ashr.io/testing-platform-api` dispatches by a `function` field. List/create operations that need tenant or user context resolve session through `init` before the target function when executing real calls.

## Real Read-Only Calibration

Private evidence files:

- `docs/evidence/private_refs/a1_api_init_real_v2.json`
- `docs/evidence/private_refs/a1_api_list_datasets_real_v2.json`
- `docs/evidence/private_refs/a1_api_list_runs_real.json`
- `docs/evidence/private_refs/a1_api_list_requests_real.json`
- `docs/evidence/private_refs/a1_api_get_dataset_first_real.json`
- `docs/evidence/private_refs/a1_api_get_dataset_0_error_real.json`
- `docs/evidence/private_refs/ashr_lab_analysis_2026-07-04.png`

Observed non-sensitive field keys:

- `init` response keys: `features`, `notes`, `status`, `tenant`, `user`.
- `init.user` keys: `created_at`, `email`, `id`, `is_active`, `is_owner`, `name`, `tenant_id`.
- `init.tenant` keys: `created_at`, `id`, `is_active`, `owner_email`, `plan`, `signup_method`, `tenant_name`.
- `list_datasets` response keys: `_user`, `datasets`, `next_cursor`, `status`.
- Dataset item keys: `agent_details`, `agent_id`, `created_at`, `creator`, `creator_details`, `dataset_source`, `dataset_type`, `description`, `id`, `name`, `repo_id`, `request_id`, `run_count`, `tenant`.
- Full dataset source keys observed by Explorer-API: `dataset_type`, `runs`, `total_runs`; first run shape included `run_id`, `title`, `description`, `intent`, `intent_tags`, `audio_tags`, `simulation`, `actions`.
- `list_runs` response keys: `_user`, `runs`, `status`.
- Run item keys: `created_at`, `dataset`, `dataset_details`, `id`, `result`, `runner`, `runner_details`, `tenant`.
- `list_requests` response keys: `_user`, `next_cursor`, `requests`, `status`.
- Request item keys: `actual_duration_s`, `completed_at`, `created_at`, `estimated_duration_s`, `id`, `request`, `request_name`, `request_status`, `requestor_details`, `requestor_id`, `requestor_tenant`.

## Error And Retry Findings

- API-level errors can arrive with HTTP 200 and body `status: error`.
- A real invalid dataset probe produced a redacted record with `status=error`, `status_code=200`, and `error_kind=api`.
- HTTP status alone is insufficient for runner success classification.
- Local tests cover retry behavior for retryable HTTP status codes including 429.
- No quota counters or rate-limit headers were returned by the small successful calls in this round; the client now captures `retry-after` and `x-ratelimit-*` if present.

## Current Verification

- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: 14 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 53 passed.
- Real read-only probes executed: `init`, `list-datasets`, `list-runs`, `list-requests`, `get-dataset` for one existing dataset, and negative `get-dataset` for an invalid dataset.
- Chrome dashboard check reached logged-in `Ashr Labs` at `https://lab.ashr.io/?tab=analysis`; visible shell hints included `Datasets` and `Runs`.
- Error string redaction is covered at the text level: token-like values, bearer tokens, and email addresses are replaced before records or exception text are emitted.

## Next Candidates

1. Add a minimal second adapter that maps a real `dataset_source.runs` scenario into the existing A1 local runner cases.
2. Run one mutating `create-run` against an existing dataset after a reviewed dry-run plan and `--allow-mutate`.
3. Exercise `create-request` with `docs/a1/api_calibration/tiny_generation_request.json` only after quota/plan wording is confirmed in the dashboard.
