# Round19 Frontend API, Usage, Quota, and Lifecycle Extraction (A1)

Date: 2026-07-08
Source archive: `C:/Users/33516/Desktop/Ashr_frontend_mirror_20260707_125507.zip`
Inspection mode: extracted read-only to `%TEMP%/ashr_frontend_mirror_round19`; no mirror source, static asset, token, or captured payload was copied into tracked repo paths.

## Redaction posture

- This file records public-safe endpoint names, function names, field names, labels, and empty-state copy only.
- Authentication token values, browser storage values, cookies, account identifiers, customer data, request bodies, and response bodies are intentionally omitted.
- The frontend bundle contains an optional `token` field and `auth_provider` field in the API envelope; this document records the field names only.

## API Transport Hints

Mirror evidence:
- `_report/api-like-observed-skipped.json` records `https://api.ashr.io/testing-platform-api` as the observed API-like endpoint.
- `mirror/lab.ashr.io/assets/index-DSO2XOq6.js` contains the shared API client.

Public-safe transport shape inferred from the client:

```json
{
  "function": "<api_function_name>",
  "token": "<redacted optional auth token>",
  "auth_provider": "<provider name, default google>",
  "...": "function-specific payload fields"
}
```

Client behavior hints:
- Requests are JSON `POST` calls to the single testing-platform endpoint.
- The client treats response `status: "error"` as a failed API call.
- Public-facing failure classes include timeout, network error, non-JSON server error, unexpected HTTP status, and auth-expired/unauthorized messages.
- `evaluate_run` is called with a longer timeout than the default client timeout.

## A1-Relevant Function Names

Observed in `call("...")` sites in `mirror/lab.ashr.io/assets/*.js`.

Dataset/request/run lifecycle:
- `list_datasets`, `get_dataset`, `create_dataset`, `update_dataset`, `delete_dataset`
- `list_requests`, `get_request`, `create_request`, `update_request_status`, `delete_request`
- `list_runs`, `get_run`, `create_run`, `update_run_result`, `delete_run`, `evaluate_run`

Agent linkage:
- `list_agents`, `create_agent`, `update_agent`, `delete_agent`
- `get_agent_datasets`, `set_dataset_agent`
- `get_tools_by_agent`, `get_agent_tool_performance`

Usage, billing, and API keys:
- `get_usage`
- `billing_get_status`, `billing_get_public_pricing`
- `billing_create_checkout_session`, `billing_create_portal_session`
- `list_api_keys`, `create_api_key`, `revoke_api_key`

Media, downloads, and voice/observability adjacency:
- `get_upload_link`, `get_download_link`
- `list_voice_sessions`, `get_voice_session`, `get_voice_session_turns`, `get_voice_session_audio_url`
- `get_voice_analytics_overview`, `get_voice_charts`, `get_voice_call_insights`, `generate_voice_call_insights`
- `get_lightberry_scenario`

## Front-End Field Names

Observed frontend field names that should remain stable or have adapters in A1 fixtures/tests:

- API envelope/auth: `function`, `token`, `auth_provider`
- Request cards/details: `request_status`, `request_name`, `requestor_details`, `request_input_schema`, `actual_duration_s`, `estimated_duration_s`
- Run/evaluation summaries: `aggregate_metrics`, `total_tests`, `tests_passed`, `tests_failed`
- Common timestamps/counts: `created_at`, `last_run_at`, `run_count`
- Dataset/agent metadata: `agent_details`, `creator_details`, `dataset_source`
- Signed asset links/API keys: `expires_seconds`, `api_key_id`

## Run and Request Lifecycle Hints

Observed UI status mapping:
- `pending` renders as `Queued`.
- `processing` renders as `Processing`.
- `failed` renders as `Failed` and unlocks retry/edit retry flows.
- `completed` renders as `Completed` where run/test result summaries are available.

Observed retry/action copy:
- `Retry`, `Edit & retry`, `Retrying...`, `Generation failed`, `Being worked on...`

A1 implications:
- A1 request fixtures should include both raw status values and frontend label expectations.
- A1 run fixtures should support `aggregate_metrics` first, with a fallback path to result/test arrays where aggregate metrics are absent.
- Retry UX should preserve the failed request identity and avoid requiring raw mirrored payloads in public docs.

## Usage and Quota Hints

Mirror evidence:
- `mirror/lab.ashr.io/assets/UsagePage-CoD18uzD.js` contains the usage page label map and quota card logic.

Observed usage metric labels:
- `Videos`
- `Images`
- `Simulations`
- `Audio`
- `Files`
- `Graded scenarios`
- `Observations`
- `Voice minutes`

Observed usage tabs/modes and states:
- Tabs/modes: `Plan limits`, `Assets`
- Limit states: `Limit reached`, `Overage billing`, `Over included usage`
- Plan/billing action surfaces: `Current plan`, `Upgrade`, checkout session, portal session

Observed quota threshold behavior:
- Below 75 percent: success/normal color.
- 75 percent through 90 percent: warning color.
- Above 90 percent: error color.
- When used amount is at or above the limit, the badge is either `Limit reached` or `Overage billing` depending on cap mode.

A1 implications:
- A1 quota fixtures should model both hard-limit and overage cap modes.
- Usage model naming should include video, simulation, observation, and voice-minute placeholders even if Round19 execution is focused on text/audio/file/image parity.
- Field adapters should tolerate backend-ish plural keys such as `images`, `simulations`, `audios`, `files`, `graded_scenarios`, `observations`, and `voice_minutes` while rendering buyer-facing labels.

## Empty and Loading States

Observed public-safe copy:
- API keys: `No API keys yet`; hint: `Create your first API key to get started with programmatic access.`
- Agents: `Loading agents...`, `Couldn't load agents: <error>`, `No agents yet.`
- Datasets: `Loading datasets...`, `Couldn't load datasets: <error>`, `No datasets match your filters.`, `Clear all filters`
- Agent/dataset linkage: `No datasets assigned to this agent yet.`
- Folders adjacency: `This folder is empty`; hint: `Click "Add datasets" to start organizing`

A1 implications:
- Public docs should keep empty states action-oriented and non-secret-bearing.
- Tests can assert that empty states do not require private tenant/account identifiers.

## Fixture

The compact public fixture derived from this extraction is stored at:

- `tests/a1/fixtures/round19_frontend_contract_public.json`

It intentionally contains only names, labels, thresholds, and redaction notes.
