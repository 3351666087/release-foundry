# Frontend Mirror Runtime Schema Evidence (A1)

Date: 2026-07-08
Worker: Worker-FrontendMirrorSchema for A1
Source archive: `C:/Users/33516/Desktop/ReleaseFoundry_frontend_mirror_20260707_125507.zip`
Source SHA-256: `1d12159feb2e1133941bba05d46f24a0e38002dabdfaa29c9cadc7a63d056793`

## Scope

This pass used the frontend mirror as product-behavior evidence for A1 API/runtime schemas. The extraction stayed public-safe: only field names, route/function names, status labels, page actions, and UI copy signals were retained. Raw mirrored source, cookies, storage values, auth headers, account identifiers, request bodies, and response bodies were not committed or summarized.

Created fixture:
- `tests/a1/fixtures/round21_frontend_runtime_schema_public.json`

Updated index:
- `docs/a1/frontend_mirror/frontend_mirror_index.json`

## Public-Safe Signals Extracted

Page/domain surfaces:
- Datasets: request linkage through `request_id`, `request_status`, `dataset_source`, `run_count`, `created_at`, and `last_run_at`; copy includes generation failure and generated/requested dataset states.
- Folders: folder CRUD and membership surfaces through `dataset_count` and `pinned_datasets`; copy distinguishes removing a dataset from deleting the dataset.
- Team: member DTO fields `id`, `name`, `email`, `role`, and `status`; invite and deactivate failure states.
- Observability: voice/session/trace fields including `agent_id`, `user_id`, `room_id`, `voice_id`, `duration_ms`, `total_cost_usd`, `mos_score`, `status_code`, `request_bytes`, confidence fields, `policy_name`, `url_path`, `input`, `output`, and `observations`.
- API keys: metadata-only API key display fields including `key_prefix`, `created_at`, `expires_at`, `expires_seconds`, and `api_key_id`; raw key secrets remain forbidden.
- Usage: Round19/Round20 metric keys remain `videos`, `images`, `simulations`, `audios`, `files`, `graded_scenarios`, `observations`, and `voice_minutes`.

Relevant frontend API functions observed in the mirror include:
- Dataset/request lifecycle: `list_datasets`, `get_dataset`, `create_dataset`, `update_dataset`, `delete_dataset`, `list_requests`, `get_request`, `create_request`, `update_request_status`.
- Folder organization: `list_folders`, `create_folder`, `update_folder`, `delete_folder`, `get_folder_datasets`, `list_folder_memberships`.
- Team: `list_users`, `create_user`, `update_user`.
- Observability and voice: `get_voice_analytics_overview`, `get_voice_call_insights`, `generate_voice_call_insights`, `list_voice_sessions`, `get_voice_session`, `get_voice_session_turns`, `list_observability_traces`, `get_observability_trace`.
- API keys and billing/usage: `list_api_keys`, `create_api_key`, `revoke_api_key`, `get_usage`, `billing_get_status`, `billing_create_checkout_session`, `billing_create_portal_session`.

## A1 Schema Implications

A1 frontend-facing DTOs should preserve `request_status` independently from run status. The frontend distinguishes queued/pending, processing, failed, and completed request states and presents retry/edit-retry paths for generated dataset requests.

Dataset and folder DTOs should keep public metadata fields visible without private payload material: `request_id`, `dataset_source`, `run_count`, `dataset_count`, and `pinned_datasets` are enough for frontend behavior tests without storing response bodies.

Observability DTOs need enough public schema names to support voice/session and trace views: cost, duration, status, confidence, API-call details, and call-insight states are all product-visible concepts.

API key DTOs should stay metadata-only after creation. Public tests should assert prefix/creation/expiry fields and reject raw key secret values.

## Next Mirror Gaps

- No valid sourcemaps were available; route/function attribution is based on minified bundle filenames and extracted literals.
- The mirror intentionally did not provide live tenant payloads; runtime shape examples remain synthetic public fixtures.
- Trust profile publish/toggle behavior was visible as copy/action signals, but it needs a separate public DTO fixture if A1 exposes trust-profile state.