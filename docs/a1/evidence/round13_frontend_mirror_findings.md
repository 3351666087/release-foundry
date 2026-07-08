# Round13 Frontend Mirror Findings (A1)

Date: 2026-07-07
Source: `C:/Users/33516/Desktop/Ashr_frontend_mirror_20260707_125507.zip`
Mode: read-only extraction to `%TEMP%`; the zip and raw mirrored files were not copied into tracked repo paths.

## A1-relevant findings

- Mirror scan found Ashr docs/API reference pages under `mirror/ashr.io/docs/python-sdk/...` and `mirror/ashr.io/docs/typescript-sdk/...`.
- Python SDK API reference mirror contains first-class media/generation terms: `text`, `audio`, `file`, `image`, `video`, `conversation`, `simulation`, plus `generate_audio`, `generate_files`, `generate_images`, `generate_videos`, and `generate_simulations`.
- Public/frontend text includes product navigation and commercial surfaces such as `Usage`, `Images`, `Audio`, `Files`, `Agents`, `Datasets`, `Analytics`, `Trust`, `API Keys`, `Team`, `Upgrade`, `Developer`, `Startup`, and `Enterprise`.
- A1 implication: local SDK/runner/probe/calibrator should continue treating text/audio/file/image/video as equal first-class request envelope modalities, with conversation/simulation tracked as adjacent hosted capabilities.
- A1 implementation link this round: `output_policy` evidence metadata was added so real API / gate / quota evidence can explain private/public sink behavior in a buyer-auditable way without exposing raw mirrored or private API payloads.

## Safe handling

- No raw API key or desktop key file was read.
- The frontend mirror zip and extracted files were not staged.
- This summary only records redacted/high-level field names needed for A1 parity work.

## Follow-up code tasks

1. Add mirror-derived media parity fixture for Python and TypeScript request schema tests.
2. Add public-safe frontend field map JSON summarizing usage/nav/API labels.
3. Compare mirror TS SDK docs against local TS SDK exports for missing official names.
4. Keep `conversation` and `simulation` as tracked adjacent modalities even if A1 runner execution focuses on text/audio/file/image/video.
5. Use mirror labels to drive future Usage/quota ledger naming (`Images`, `Audio`, `Files`, plus future `Videos`/`Simulations`).


## Static frontend API client details

Observed single API entrypoint:
- `https://api.ashr.io/testing-platform-api`

Observed JSON request envelope shape:

```json
{
  "function": "<function_name>",
  "token": "<redacted when authenticated>",
  "auth_provider": "<provider, default google>"
}
```

Frontend error handling hints:
- `status: "error"` marks a failed API response.
- Failure copy can use `message` plus optional `error` details.
- Transport fallbacks include timeout, network error, non-JSON 5xx, and unexpected HTTP status messages.

## Frontend-observed A1 function map

Dataset/request/run lifecycle:
- `list_datasets`, `get_dataset`, `create_dataset`, `update_dataset`, `delete_dataset`
- `list_requests`, `get_request`, `create_request`, `update_request_status`, `delete_request`
- `list_runs`, `get_run`, `create_run`, `update_run_result`, `delete_run`, `evaluate_run`

Agent linkage:
- `list_agents`, `create_agent`, `update_agent`, `delete_agent`
- `get_agent_datasets`, `set_dataset_agent`
- `get_tools_by_agent`, `get_agent_tool_performance`

Usage/billing/API key:
- `get_usage`, `billing_get_status`, `billing_get_public_pricing`
- `billing_create_checkout_session`, `billing_create_portal_session`
- `list_api_keys`, `create_api_key`, `revoke_api_key`

Media/upload/download:
- `get_upload_link`, `get_download_link`
- `get_lightberry_scenario`, `list_voice_sessions`, `get_voice_session_audio_url`

## Usage/quota labels and modes

Mirror-observed usage labels:
- `Videos`, `Images`, `Simulations`, `Audio`, `Files`, `Graded scenarios`, `Observations`, `Voice minutes`

Mirror-observed UI modes:
- `Plan limits`, `Assets`
- `Limit reached`, `Overage billing`, `Plan limit reached`, `Over included usage`
- Gauge thresholds: below 75 percent success, 75-90 percent warning, above 90 percent error.

A1 implication:
- Quota ledger should model both hard-block and overage modes.
- Media quota model should not stop at image/audio/file; video/simulation and voice/observation counters need public-safe placeholders.

## Request/run lifecycle hints

Observed request fields and labels:
- Raw-ish fields: `request_status`, `status`, `created_at`, `actual_duration_s`, `estimated_duration_s`, `request_name`, `requestor_details.name`, `request_input_schema`, nested `request`, `_failure.error`.
- UI labels: `Queued`, `Processing`, `Failed`, `Generation failed`, `Completed`, `Being worked on...`, `Retry`, `Edit & retry`, `Retrying...`.

Observed run/evaluation hints:
- `aggregate_metrics.total_tests`, `aggregate_metrics.tests_passed`, `aggregate_metrics.tests_failed`.
- If aggregate metrics are missing, frontend falls back to `result.tests[]`.
- Test statuses counted as passing include `passed` and `completed`; failing includes `failed`.

A1 implication:
- Keep request lifecycle, run lifecycle, and test lifecycle separate in SDK/runner schemas.
- Preserve request `_failure.error`, API top-level `message/error`, and run/test status as distinct evidence paths.

## Create-request frontend shape hints

Mirror-observed create request payload keeps:
- top-level `request_name`, `request`, `request_input_schema`, `request_status`, optional `prompt_version_id`, optional `agent_id`, optional `folder_id`.
- `generation_options` includes `generate_audio`, `generate_files`, `generate_simulations`, provider/model/seed style options.
- 3D branch uses `generation_options.dataset_strategy: "3d"` and `request_input_schema.kind: "3d_lightberry"`.

A1 implication:
- Maintain request/request_input_schema split in examples and adapters.
- Keep frontend-static function names marked as static evidence, not backend response proof, until real API probes validate each function.
