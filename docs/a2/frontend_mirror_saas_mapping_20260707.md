# A2 Frontend Mirror SaaS Mapping 2026-07-07

Owner: Kay / A2
Source: `Ashr_frontend_mirror_20260707_125507(1).zip` local mirror inspection
Safety boundary: This file is a public-safe mapping only. Do not commit the mirror zip, raw JS chunks, browser report manifests, account payloads, API responses, key values, signed URLs, or exact private usage counters.

## Why This Mirror Matters

The mirror is useful for A2 because it exposes the real SaaS product vocabulary around request generation, datasets, runs, validators, usage, trust, team, API keys, and observability. A2 should not copy frontend implementation. A2 should use it to calibrate scenario design, judge policy, result persistence, and release gate semantics.

The most valuable surfaces are:

- `mirror/lab.ashr.io/assets/CreateRequestModal-LwtjGDgm.js`
- `mirror/lab.ashr.io/assets/RequestDetailDrawer-SLqhBzSz.js`
- `mirror/lab.ashr.io/assets/UsagePage-CoD18uzD.js`
- `mirror/lab.ashr.io/assets/TeamPage-zKnEHkxH.js`
- `mirror/lab.ashr.io/assets/TrustPage-DH1i4mLu.js`
- `mirror/lab.ashr.io/assets/ApiKeysPage-DcsMtTi4.js`
- `mirror/lab.ashr.io/assets/ObservabilityPage-BmNyibq8.js`
- `mirror/ashr.io/docs/python-sdk/*`
- `mirror/ashr.io/docs/typescript-sdk/*`

## Scenario Additions

| Scenario target | Frontend surface | A2 owner file candidates | Expected A2 behavior |
|---|---|---|---|
| Request generation contract | `CreateRequestModal-*` | `packages/scenarios/a2_g3_full_pack.json`, `docs/a2/case_book.md` | Cover accepted inputs, agent config, tools, output format, input schema, context, behaviors, complexity, and variations. |
| Expected behavior contract | `CreateRequestModal-*` | `services/judge/tool_policy.py`, `services/judge/outcome.py` | Grade required tools, optional tools, forbidden tools, tool order, must include, must not include, tone, length, similarity threshold, and tool divergence. |
| Request failure replay | `RequestDetailDrawer-*` | `services/judge/incident_regression.py`, `services/judge/regression_replay.py` | Convert failed/pending request states, failure reasons, retry/edit-retry paths, and generated dataset links into regression evidence. |
| Server-side grading | `CreateRequestModal-*`, SDK docs | `services/judge/service_wrapper.py`, `services/judge/semantic_harness.py`, `services/judge/calibration.py` | Track validator strategy, evaluated run, average score, score distribution, pass/fail, and server judge status. |
| Observability and voice quality | `ObservabilityPage-*`, Python observability docs | `services/judge/trace_integrity.py`, `services/judge/grounding.py` | Require explicit trace, observation, policy, errored turn, latency, and voice-quality evidence before claiming observability readiness. |
| Usage and quota gate | `UsagePage-*` | `services/judge/release_policy.py`, `fixtures/a2/config/release_policies.json` | Block or warn on plan limit reached, quota exhaustion, overage mode, and mutating generation without fresh usage evidence. |
| Team attribution | `TeamPage-*` | `services/judge/result_persistence.py`, `docs/a2/schemas/result_persistence_manifest.schema.json` | Preserve public-safe member/requestor attribution summaries without names, emails, or account payloads. |
| Trust publishability | `TrustPage-*` | `services/judge/release_gate.py`, `services/judge/release_policy.py` | Do not allow public trust/certificate claims without certifiable results, no blockers, and complete evidence bundle. |
| API key safety | `ApiKeysPage-*` | `services/judge/release_policy.py`, safety scenarios | Treat key create/list/revoke/print as explicit authorization boundaries; key-like values in public output are hard failures. |

## Judge Policy Rules To Add Or Calibrate

- `request_terminal_state_required`: pending or failed request records cannot pass release gate as completed evidence.
- `generation_error_requires_replay`: frontend failure reasons must become regression evidence or release blockers.
- `min_similarity_score_threshold`: default frontend semantics suggest a configurable threshold, observed as `0.7`.
- `max_tool_divergence_threshold`: default frontend semantics suggest a configurable threshold, observed as `0.3`.
- `forbidden_tool_hard_fail`: forbidden tool usage should be zero-tolerance in production profiles.
- `required_tool_missing_fail`: missing required tools should map to `missing_required_tool`.
- `tool_order_policy`: support flexible and ordered modes instead of a single hardcoded assumption.
- `response_requirements_policy`: `must_include`, `must_not_include`, tone, and max length should be judge-visible.
- `multi_input_evidence_required`: enabled text/audio/file/image/video/conversation inputs require corresponding evidence references.
- `observability_quality_floor`: low quality score or missing observability evidence should block observability readiness claims.
- `voice_error_policy`: slow TTS, low STT confidence, false interrupts, interruptions, and errored turns need explicit failure mapping.
- `usage_limit_policy`: plan limits should block mutating collection; metered overage should be recorded as business risk.
- `trust_publish_policy`: trust publication requires clean release gate and complete audit evidence.
- `api_key_auth_error_policy`: expired/revoked/malformed/permission errors are auth/config failures, not ordinary agent behavior failures.

## Result Persistence Fields

A2 persistence should be able to record these public-safe summaries when A1/A3 provide them:

- Request: `request_id`, `request_status`, `request_config_hash`, `input_schema_hash`, `requestor_ref`.
- Dataset: `dataset_id`, `dataset_ref`, `generated_from_request_id`, `folder_ref`.
- Agent: `agent_id`, `agent_config_hash`, `accepted_input_modes`, `tool_schema_hash`.
- Run: `run_id`, `run_status`, `validator_id`, `validator_strategy`, `judge_model_ref`.
- Scenario: `scenario_id`, `scenario_family`, `coverage_flags`, `complexity_level`, `persona_role`.
- Score: `score`, `avg_score`, `passed`, `failure_class`, `failure_summary`, `similarity_score`, `tool_divergence`.
- Expected behavior: `required_tools_ref`, `forbidden_tools_ref`, `tool_order_policy`, `response_requirements_ref`.
- Evidence: `trace_event_refs`, `tool_call_refs`, `observation_refs`, `media_evidence_refs`, `request_error_ref`.
- Observability: `trace_ref`, `quality_score_bucket`, `policy_name`, `error_signal_count`, `errored_turn_count`.
- Usage: `graded_scenarios_count`, `observations_count`, `voice_minutes_bucket`, `media_count_buckets`, `limit_state`.
- Team/trust: `member_ref`, `member_status`, `certifiable`, `published`, `trust_grade_bucket`, `public_url_present`.
- Privacy: `private_evidence_pointer`, `raw_private_evidence_not_recorded`, `secrets_not_recorded`.

## Private Evidence Only

The following must not be committed:

- The original mirror zip.
- Raw `mirror/lab.ashr.io/assets/*.js` chunks.
- Full `_report/download-manifest.json` and `_report/observed-browser-assets.json`.
- Any `api.ashr.io/testing-platform-api` request/response payload.
- API key names/values, generated key values, member emails/names, tenant IDs, account IDs, signed URLs, exact usage counters.
- Raw screenshots or browser payloads that identify the account.

Allowed public-safe artifacts:

- Surface names.
- High-level field categories.
- Redacted evidence summaries.
- Hashes and counts when they do not identify private account state.
- A2 scenario/policy/persistence requirements derived from the mirror.

## Mapping To Large SaaS Strategy

This mirror supports the A2 sections in `docs/strategy/large-saas-a1-a2-a3-full-plan.md`:

- A2-1 Judge Service: server-side grading and validator workflow.
- A2-3 Release Policy: usage/quota, trust publishability, API key safety, waiver/publish gates.
- A2-4 Scenario Library: request generation, expected behavior, multimodal inputs, observability, admin boundaries.
- A2-5 Ground Truth: expected tools, response requirements, similarity/tool-divergence thresholds.
- A2-6 Semantic Judge: hosted/server judge status, quality score, confidence, review state.
- A2-7 Calibration: official frontend/server grading versus local A2 judge drift.
- A2-8 Regression Intelligence: failed request retry/edit-retry to regression promotion.
- A2-9 Failure Taxonomy: auth/config failures, quota limits, trust publishing, voice/observability failures.

## Immediate A2 Backlog

1. Add a request generation scenario family for accepted inputs, tools, context, output format, and expected behavior.
2. Add request failure replay fixtures using pending/failed/completed terminal states.
3. Add usage/quota policy gates to production release policies.
4. Add trust publishability release gate checks.
5. Add API key safety scenarios and policy rules.
6. Extend result persistence with request/run/validator/usage/trust/team public-safe summary fields.
7. Add observability and voice-quality failure classes or taxonomy metadata.
8. Add server-side grading drift tracking between A2 local judge and reviewed Ashr grading evidence.
