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

If any of these become required for A1/A2/A3, they need a Gate decision or explicit user-provided authenticated test state without entering secrets into logs or committed artifacts.
