# A3 Official Frontend Clean-room Crawl - 2026-07-07

## Scope And Boundary

This document is the only artifact written by this pass.

Clean-room rule: A3 may use the official Ashr frontend only as product-reference evidence for page structure, route/query shape, visible labels, API method names, field names, state names, and safety boundaries. A3 must not copy official source code, styles, assets, component implementations, bundled JavaScript bodies, cookies, tokens, headers, account data, raw signed media URLs, or secret values.

I did not read `.env.local`. I did not print secrets. I did not open or copy official source code from the frontend mirror. The extraction below is derived from local redacted summaries, existing A3 notes, and path/name-level searches.

## Local Mirror Search Result

Search outcome:

| Target | Result |
|---|---|
| `Ashr_frontend_mirror_20260707_125507.zip` under project/date tree | Not found as a local file |
| Exact zip in the local WeChat file cache | Found outside the repository; used only for path/name-level and keyword-count clean-room extraction |
| Clean-room summary | Found: `fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json` |
| Related docs | Found: `docs/a3/p3_frontend_mirror_analysis_2026_07_07.md`, `docs/a3/p3_official_frontend_notes.md`, `docs/a3/p3_frontend_page_map.md`, `docs/a3/p3_frontend_field_mapping.md`, `docs/a3/p3_official_dashboard_gap_analysis.md` |

Important interpretation: the zip file exists outside the repository and must not be committed. A3 should keep only redacted summaries such as `fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json` and `fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json`.

## Evidence Sources

Primary evidence used:

- `fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json`
- `fixtures/a3/p3/ashr_dataset_884_official_frontend_observation.redacted.json`
- `docs/a3/p3_frontend_mirror_analysis_2026_07_07.md`
- `docs/a3/p3_official_frontend_notes.md`
- `docs/a3/p3_frontend_page_map.md`
- `docs/a3/p3_frontend_field_mapping.md`
- `docs/a3/p3_official_dashboard_gap_analysis.md`
- `docs/a3/mock_fixture_contract.md`
- `docs/a3/a3_integration_plan.md`

Supporting evidence paths named by the existing docs:

- `fixtures/a3/p3/ashr_dataset_884_run_11925_detail.redacted.json`
- `fixtures/a3/p3/ashr_dataset_884_run_11926_ui_tests_detail.redacted.json`
- `fixtures/a3/p3/ashr_dataset_884_list_runs_summary_ui_tests_after_create.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`
- `fixtures/a3/p3/ashr_run_trace_sample.redacted.json`

## Official Frontend Page And Route Structure

Confirmed or summarized top-level Lab routes:

| Product area | Observed or summarized route | A3 decision |
|---|---|---|
| Lab shell / sign-in | `https://lab.ashr.io/` | Keep A3 local-only; do not copy auth |
| Datasets / Analysis | `?tab=analysis` | Copy as primary dashboard shell |
| Dataset overview | `?tab=analysis&dataset=884` | Copy dataset provenance summary |
| Dataset case detail | `?tab=analysis&dataset=884&run=<case_key>` | Copy case detail and action timeline concepts |
| Results tab | Dataset page tab, e.g. `Results (0)` for dataset `884` | Copy result-review concept; visual parity still blocked |
| Direct API run URL | `?tab=analysis&dataset=884&run=11925` | Do not assume API run ids are frontend routes |
| Agents | `?tab=agents` | Metadata/filter only for A3 MVP |
| Folders | `?tab=folders` | Skip for MVP |
| Analytics | `?tab=analytics` | Copy local pass-rate/run-volume health concepts |
| Observability | `?tab=observability` or feature-gated area | Future incident/trace replay lane |
| Usage | `?tab=usage` | Read-only quota/media awareness only |
| Trust | `?tab=trust` | Use as local audit/export inspiration |
| API Keys | `?tab=api-keys` | Do not copy key creation or secret reveal |
| Team | `?tab=team` | Do not copy invites/account administration |
| Settings | Modal/menu, not a core eval route | Only theme/low-power style inspiration |

Official mirror summary also identifies route/module chunks by name only, such as `DatasetsPage`, `CreateRequestModal`, `RequestDetailDrawer`, `AgentsPage`, `FoldersPage`, `AnalyticsPage`, `UsagePage`, `TrustPage`, `ApiKeysPage`, `TeamPage`, `ObservabilityPage`, and `AgentEffectivenessChart`. These names are useful for product mapping only; A3 must not copy their implementation.

## Module Map For A3 Dashboard

| Official concept | Confirmed labels or method groups | A3 module mapping |
|---|---|---|
| Dashboard / Analysis | Datasets, Test cases, Results, Runs History | Main A3 dashboard shell, run list, case list |
| Results | Results tab, Runs History, pass/fail/score API evidence | A3 Run List, summary cards, release gate |
| Run detail | `get_run`, `list_runs`, `result.tests[]`, `result.cases[]` | A3 selected run/case detail |
| Case detail | TEST DETAILS, ACTIONS, Tool Calls, media/input type | A3 case detail, expected/actual, media evidence |
| Trace / Timeline | Timeline label, observations, `action_results[]`, observability methods | A3 trace timeline and incident replay |
| Settings | Theme, Low Power | Optional dashboard polish only |
| Usage | Images, Audio, Files, `get_usage`, `billing_get_status` | Read-only Usage / Quota panel |
| Team | Team page, member/invite concepts | Out of scope |
| API Key | API Keys page, SDK env guidance | Out of scope, no secret handling |
| Trust / report | Public trust/certificate concept | Local report/audit bundle only |
| Agents | Agent list, tool performance methods | Runner/agent metadata and filters only |
| Analytics | pass rate, run volume, by-agent charts | Local pass-rate, failure clusters, coverage health |

## Official API Method Groups To Product Concepts

The redacted summary lists method names only, not bodies. A3 should treat them as naming evidence:

| Group | Methods or signals | A3 use |
|---|---|---|
| `evaluation_core` | `list_datasets`, `get_dataset`, `create_dataset`, `list_runs`, `get_run`, `create_run`, `update_run_result` | Highest parity priority for datasets/runs/cases |
| `request_generation` | `list_requests`, `get_request`, `create_request`, `update_request_status` | Request provenance and generation lifecycle |
| `agent_registry` | `list_agents`, `get_agent_tool_performance`, `get_tools_by_agent` | Agent labels/effectiveness summaries only |
| `usage_billing` | `get_usage`, `billing_get_status`, checkout/portal names | Read-only usage; billing mutations out of scope |
| `trust_team_keys` | trust certificate, API key, user methods | Local audit concept only; no team/key mutation |
| `observability_voice` | trace analytics/errors/latency/tool errors, voice sessions | Future replay/incident lane with redacted fixtures |
| `folders` | folder list/membership methods | Low priority grouping only |

## Clean-room State Machine For A3

A3 should model official frontend parity as states, not as a claim that every page is visually confirmed.

| State | Trigger / evidence | A3 representation |
|---|---|---|
| `unauthenticated` | Lab shows sign-in / onboarding | A3 safety note only; no auth clone |
| `empty_workspace` | authenticated UI shows no datasets/agents/runs | Empty-state coverage in dashboard tests |
| `dataset_visible` | dataset `884`, display id `#00000374`, 5 test cases | Dataset provenance card and case browser |
| `case_definition_visible` | `?tab=analysis&dataset=884&run=<case_key>` | Case detail from scenario/action metadata |
| `results_empty` | official Results tab shows `Results (0)` and no runs | A3 must label visual result parity as blocked |
| `api_run_visible` | API run `11925` with `result.cases[]` | A3 can map local result-review fixture |
| `frontend_style_run_visible_api` | API run `11926` with `result.tests[].action_results[]`; summary-only list returns it | Default official-demo mapping target |
| `visual_results_pending` | official browser confirmation of run `11926` not yet captured | Keep as explicit gap |
| `trace_available_local` | observations/action results can become trace events | A3 trace timeline and replay queue |
| `media_metadata_available` | media/input tags and redacted URL metadata exist | Display metadata; do not render live signed URLs |
| `usage_frontend_confirmed_oauth_gated` | Usage labels and methods observed; API-key probes return OAuth-only 403 | Read-only Usage / Quota panel |
| `admin_out_of_scope` | API Keys, Team, billing, OAuth, destructive mutation | Documented non-goals |

## Field Mapping Into A3

Core fields A3 should keep stable:

| A3 field | Official/API evidence | Notes |
|---|---|---|
| `run_id` | `run.id`, `run.result.run_id`, API runs `11925` / `11926` | Do not assume visual route id |
| `dataset_id` | `dataset.id`, run `dataset` | Required for source identity |
| `dataset_display_id` | UI display id such as `#00000374` | Good provenance field |
| `case_id` | `case.case_id`, `test.test_id`, dataset case key | Must support both `cases[]` and `tests[]` shapes |
| `status` | run/case status, request status, aggregate pass/fail | Normalize for badges and gates |
| `passed` | `grade.passed`, aggregate counts | Primary result filter |
| `score` | `grade.score`, case/test score, semantic fallback | Normalize to 0-100 display |
| `expected` | expected response, expected tool calls, dataset actions | Expected panel |
| `actual` | actual response, actual tool calls | Actual panel |
| `tool_calls` | expected/actual tool calls, `action_results[].tool_calls[]` | Tool Call Diff |
| `trace_events` | observations, `action_results[]`, observability traces later | A1-compatible timeline |
| `failure_reason` | grade reason/metrics or derived summary | Detail and report |
| `primary_failure_class` | A2-derived until official native field appears | Failure clusters |
| `media_evidence` | action type, media/input tags, redacted signed URL metadata, VM stream metadata | Metadata only |
| `usage_quota` | Usage page labels and OAuth-gated methods | Known-gap/read-only area |
| `request_status` | request lifecycle and dataset generation status | Request provenance |

## Fixture, Schema, And Test Points To Add

Fixtures to add or extend:

- Add a compact fixture for official page-state parity with states such as `dataset_visible`, `results_empty`, `frontend_style_run_visible_api`, and `visual_results_pending`.
- Add or extend a fixture that pairs dataset `884` case definitions with run `11926` `result.tests[].action_results[]`.
- Add a redacted Usage fixture that records only channel labels, OAuth-gated status, and method names; no account counters if they are sensitive.
- Add a redaction fixture proving no `api_key`, cookie, bearer token, account email, raw signed URL, or secret-like value is exported.

Schema points:

- Add an `official_frontend_page_state` object with `page`, `route_hint`, `evidence_path`, `visibility_state`, `a3_decision`, and `blocked_reason`.
- Add a `result_visibility` enum: `not_applicable`, `empty`, `api_only`, `summary_api_visible`, `visual_confirmed`, `blocked`.
- Add support for both result shapes: `result.cases[]` and `result.tests[].action_results[]`.
- Add `dataset_display_id`, `case_frontend_key`, `media_or_input_types`, and `official_route_hint` as optional provenance fields.
- Add a `safety.redaction` object to report/export payloads with booleans for `secrets_saved`, `cookies_saved`, `tokens_saved`, `raw_signed_urls_saved`, and `official_source_copied`.

Test points:

- `p3_ashr_mapper.test.mjs`: prove `result.tests[].action_results[]` maps to A3 cases, expected/actual, tool diffs, trace events, score, and media evidence.
- `report_builder.test.mjs`: prove official frontend mirror/page-state summary appears in JSON and Markdown without source snippets or secrets.
- `dashboard_wiring.test.mjs`: prove dashboard renders route/module parity states and distinguishes `api_only` from `visual_confirmed`.
- `a3_gate_cli.test.mjs`: prove release/audit output redacts keys, tokens, cookies, emails, and signed URLs.
- Add one fixture-contract test for the new page-state schema and `result_visibility` enum.

## A1 / A2 / A3 Calibration Suggestions

A1 calibration:

- Emit stable `trace_events[]` for tool calls, media inputs, final responses, retries, and errors.
- Preserve source ids that A3 can join to official-style `test_id`, `case_id`, and `action_results[]`.
- Include media channel metadata without live signed URLs.
- Keep `run_id`, `dataset_id`, `runner_id`, `status`, timing, and trace completeness consistent.

A2 calibration:

- Keep failure taxonomy aligned with what A3 can show: `missing_required_tool`, `wrong_arguments`, `wrong_tool_order`, `bad_final_response`, `ignored_tool_result`, `unsafe_or_policy_violation`, `missing_clarification`, and `poor_failure_recovery`.
- Treat official native `failure_class` as unconfirmed; continue deriving `primary_failure_class` from judge evidence.
- Ensure judge evidence links back to trace event ids or tool-call ids when available.
- Add tests for media/tool-call failures that resemble dataset `884` cases.

A3 calibration:

- Keep the main product path as dataset -> run/results -> case detail -> expected vs actual -> tool-call diff -> trace timeline -> report/export.
- Label official Results visual parity as pending until a logged-in frontend pass confirms run `11926` in the Results tab.
- Keep Usage, Team, API Keys, billing, OAuth, and Trust as read-only/out-of-scope explanations, not cloned workflows.
- Make evidence provenance visible in the dashboard so users can tell the difference between official UI observation, redacted API evidence, and local A1/A2 fixtures.

## Next Executable Changes

1. Add a new `official_frontend_page_state` fixture from the evidence above.
2. Extend the A3 mapper/report schema to expose `result_visibility`, `dataset_display_id`, and `official_route_hint`.
3. Add mapper tests for `result.tests[].action_results[]` using run `11926`.
4. Add dashboard wiring tests for `api_only`, `summary_api_visible`, and `visual_results_pending` states.
5. Add a redaction regression test for exports that scans for secret-like patterns and raw signed URL patterns.
6. After a fresh logged-in browser pass, update the page-state fixture from `visual_results_pending` to either `visual_confirmed` or `blocked` for run `11926`.

## Bottom Line

The useful official frontend shape for A3 is not the full SaaS console. It is the evaluation-review loop: datasets, test cases, results, run/case details, expected vs actual, tool calls, timeline/trace, analytics, and local report/audit export.

A3 should continue to copy product logic and vocabulary, not source code or hosted account operations. The current strongest evidence is the redacted clean-room mirror summary plus dataset `884` UI observation and run `11926` API-shaped result evidence.
