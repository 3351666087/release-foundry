# Official Site Gaps

Date: 2026-07-04

A1 public-site checks were originally read-only and did not use a real key. In the A2 G3 phase, Kay explicitly authorized authenticated API calibration; `scripts/a2_real_api_smoke.py` ran `init`, `health_check`, `list_datasets`, `list_runs`, `list_requests`, and `list_agents`, then saved only a redacted summary in `docs/evidence/a2_real_api_smoke.json`.

Verified public-only:

- Homepage, Python SDK docs, TypeScript SDK docs, VM integration docs, API reference, and public Plans section were accessible in read-only Chrome checks.
- Public Plans copy was visible for Developer, Startup, and Enterprise tiers.
- Earlier `lab.ashr.io` read-only checks reached only unauthenticated sign-in/onboarding shell state; no private data was used as clone input.
- Round 4 recheck of `lab.ashr.io` reached title `Ashr Labs`, public Home/Docs/Blog links, and a dashboard-like `Datasets`/loading shell at `https://lab.ashr.io/?tab=analysis`; the earlier sign-in/onboarding plan-copy state could not be re-verified, and no authenticated dashboard fields or private data were used as clone input.
- Round 5 read-only checks observed both public lab shell variants without entering credentials: one pass saw `Datasets` loading shell, and Explorer-Chrome reproduced the unauthenticated sign-in/onboarding shell with `Continue with Google`, `Continue with Microsoft`, `Create your workspace`, `Pick a plan`, `FREE`, `$0/mo`, and sample quota copy.
- Public API docs list API key list/revoke methods; A2 smoke intentionally did not call key list/revoke endpoints.

Unverified or intentionally out of scope:

- Hosted/server-side grading behavior, including `run.deploy`, `poll_run`, dashboard deeplinks after deploy, and final hosted grade persistence.
- Authenticated dashboard persistence, private project/run/dataset content, tenant feature flags, and observability dashboard rendering. The A2 smoke only records counts and response key shapes.
- The reason lab shell variants differ between read-only checks; no private/authenticated state was used to resolve it.
- API key creation, key scopes, key expiry, API key list/revoke enforcement, and dashboard-only key management.
- Billing enforcement, Stripe checkout/portal behavior, hard-cap enforcement, metered overage calculation, and annual-plan discount application.
- Public pricing backend/API, if any; only rendered public Plans copy was inspected.
- TypeScript SDK runtime parity; the TypeScript docs were calibrated only to avoid field/process guessing.
- Voice-minute metering, data retention enforcement, and tenant/project limit enforcement.

2026-07-04 A1 update:

- Read-only Chrome recheck confirmed the public API reference exposed `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `request_status`, `generate_audio`, `generate_files`, `generate_images`, `generate_videos`, `generate_simulations`, and file-upload style media fields.
- A logged-in Usage page check showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` without a sign-in blocker; exact private counter values were not recorded in tracked docs.
- Public pricing/plans still did not clearly define per-category Image/Audio/File generation quota semantics, reset timing, or hosted media failure semantics. Keep those as known gaps and do not infer them from private counters.

2026-07-04 A1 cloud demo update:

- Read-only Chrome recheck confirmed the public API reference exposed `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_dataset`, `list_datasets`, `request_input_schema`, `accepted_inputs`, `request_status`, `health_check`, and `list_agents`.
- Logged-in Usage page loaded asynchronously and then showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact private counter values were not recorded. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_cloud_demo_2026-07-04.png`.

2026-07-04 A1 TypeScript quickstart update:

- Read-only Chrome recheck confirmed public TypeScript SDK references/tabs remain visible and the Python API reference still exposes dataset, run, request, and media-envelope fields used for parity.
- TypeScript runtime parity is now local-only in `packages/ts/ashr-clone`; hosted TypeScript API-client behavior, auth, and billing/usage semantics remain unverified and should stay dry-run/transport-injected until separately calibrated.

2026-07-04 A1 queue worker update:

- Read-only Chrome recheck confirmed the public API reference still exposes `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `request_status`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, and `generate_files`.
- The Usage page at `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` but showed sign-in copy during this pass. `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` labels were therefore not confirmed in this pass, and no private counters were recorded.
- Local queue worker status names (`queued`, `running`, `completed`, `failed`, `cancelled`) remain an A1 local runtime scaffold for polling and replay. Hosted Ashr queue semantics, cancellation semantics, and billing/quota timing remain unverified.

2026-07-04 A1 TypeScript API-client update:

- Main-thread Chrome recheck found that `https://ashr.io/docs/api-reference/` currently returns `404 Not Found`; the public API reference is reachable at `https://ashr.io/docs/python-sdk/api-reference/`.
- The current public API reference exposed `AshrLabsClient`, `health_check`, `list_agents`, `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, `generate_files`, `Trace`, `Span`, and `Generation`.
- `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` but showed sign-in copy in this pass; `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` labels were not confirmed. No private counters were recorded.
- TypeScript `AshrApiClient` now mirrors the Python dry-run/client guardrail surface locally, but no hosted TS API call has been executed. Hosted TS auth behavior, quota headers, media processing behavior, and billing/usage timing remain unverified.

2026-07-04 A1 queue persistence/replay update:

- Main-thread Chrome recheck confirmed the public API reference at `https://ashr.io/docs/python-sdk/api-reference/` exposed `AshrLabsClient`, `health_check`, `list_agents`, `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, and `generate_files`.
- `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` in the current Chrome session and showed the labels `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact private usage counters were not recorded in tracked docs.
- Local queue snapshot/replay state remains an A1 clone scaffold. Hosted persistence semantics, queue replay behavior, cancellation persistence, and Image/Audio/File quota reset/enforcement semantics remain unverified against Ashr's backend.

2026-07-04 A1 TypeScript probe CLI update:

- Chrome read-only checks verified `https://ashr.io/docs/typescript-sdk/api-reference/` and `https://ashr.io/docs/typescript-sdk/authentication/`. The TypeScript docs group showed Overview, Installation, Quick Start, Testing Your Agent, Authentication, VM Integration, API Reference, Error Handling, and Examples.
- TypeScript authentication docs showed `ASHR_LABS_API_KEY`, optional `ASHR_LABS_BASE_URL`, `fromEnv`, direct `apiKey` / `baseUrl` construction, API key list/revoke docs, and key-security guidance.
- TypeScript API reference exposed `AshrLabsClient`, `fromEnv`, `createRun`, `getRun`, `listRuns`, `deleteRun`, `createRequest`, `getRequest`, `listRequests`, `waitForRequest`, `generateDataset`, `healthCheck`, `Trace`, `Span`, `Generation`, `accepted_inputs`, `generate_audio`, and `generate_files`.
- The same TS API pass did not show `generate_images`, `listAgents`, or `pollRun`; A1 keeps those mapped from the Python API reference and local TS client parity until a later TS-doc/API calibration confirms exact hosted names.
- `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` and showed labels `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact private usage counters were not recorded.

2026-07-04 A1 queue batch update:

- Main-thread Chrome recheck verified `https://ashr.io/docs/typescript-sdk/api-reference/` and `https://ashr.io/docs/python-sdk/api-reference/`. TypeScript docs exposed `AshrLabsClient`, `fromEnv`, `createRun`, `getRun`, `listRuns`, `deleteRun`, `createRequest`, `getRequest`, `listRequests`, `waitForRequest`, `generateDataset`, `healthCheck`, `Trace`, `Span`, `Generation`, `accepted_inputs`, `generate_audio`, and `generate_files`.
- The same TypeScript docs pass did not show `generate_images`; Python docs did show `generate_images`, `generate_audio`, and `generate_files`. A1 keeps Image/Audio/Files envelope semantics grounded in Python docs and local schema tests until TS docs/API confirm the exact TS image field.
- `https://lab.ashr.io/?tab=usage` initially showed `Loading Usage...`, then settled to labels `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`. Exact private counter values were not recorded in tracked docs. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_queue_batch_round_2026-07-04.png`.
- Local queue batch replay remains an A1 local runtime scaffold. Hosted Ashr queue persistence, replay ordering, cancellation persistence, and per-run batch export semantics remain unverified against Ashr's backend.

2026-07-04 A1 TypeScript runner parity update:

- Explorer-Chrome read-only verification confirmed TypeScript API reference fields `AshrLabsClient`, `fromEnv`, `createRun`, `getRun`, `listRuns`, `deleteRun`, `createRequest`, `getRequest`, `listRequests`, `waitForRequest`, `generateDataset`, `healthCheck`, `Trace`, `Span`, `Generation`, accepted-input examples for text/audio/file/image/video, and generation options including `generate_audio`, `generate_files`, and `generate_simulations`.
- Python API reference confirmed `request_input_schema`, `accepted_inputs`, `generate_audio`, `generate_files`, `generate_images`, `create_run`, `get_run`, `list_runs`, `delete_run`, `poll_run`, `create_request`, `get_request`, `list_requests`, `wait_for_request`, and `generate_dataset`.
- Logged-in Usage page labels `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` were visible in the Explorer-Chrome pass; exact private counter values were not recorded. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_ts_python_parity_2026-07-04.png`.
- TypeScript docs still did not expose `generate_images`, `pollRun`, or `listAgents` in the verified pass. A1 keeps these as Python-doc/API-client parity mappings until hosted TS SDK/API calibration confirms exact names.
- Hosted TypeScript queue/runtime semantics, quota reset timing, media failure semantics, and real TS SDK authentication behavior remain unverified because no environment API key was present in this process.

If any of these become required for A1/A2/A3, they need a Gate decision or explicit user-provided authenticated test state without entering secrets into logs or committed artifacts.

2026-07-04 A1 TS cloud queue/media refresh:

- Explorer-Chrome read-only verification confirmed TypeScript API reference fields `AshrLabsClient`, `fromEnv`, `createRun`, `getRun`, `listRuns`, `deleteRun`, `createRequest`, `getRequest`, `listRequests`, `waitForRequest`, `generateDataset`, `healthCheck`, `Trace`, `Span`, `Generation`, and `accepted_inputs` with `text`, `audio`, `file`, `image`, and `video`.
- The same TypeScript docs pass showed `generate_audio`, `generate_files`, and `generate_simulations`, but did not expose `pollRun`, `listAgents`, `generate_images`, or `generate_videos`; Python docs continue to expose `poll_run`, `list_agents`, `generate_images`, and `generate_videos`.
- `lab.ashr.io/?tab=usage` loaded as `Ashr Labs` but settled into unauthenticated onboarding/pricing copy during this pass. Authenticated usage counters and exact quota values were not recorded.
- A1 local TypeScript now treats `text`, `audio`, `file`, `image`, and `video` as same-level `AgentInput.parts` values and dry-run request-schema values. Hosted TS SDK auth behavior, quota reset/enforcement timing, media generation failure semantics, and dashboard counter semantics remain unverified until a separate authenticated calibration uses env-only keys.
