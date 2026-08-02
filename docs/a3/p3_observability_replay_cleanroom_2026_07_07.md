# A3 Observability Replay Clean-room - 2026-07-07

## Scope

This document turns the existing A1/A2/A3 fixtures and docs into an A3 replay plan for observability-driven incident review.

Clean-room boundary:

- Do not copy official ReleaseFoundry source code, styles, assets, bundled implementation bodies, cookies, tokens, account data, raw signed URLs, or secrets.
- Do not call the real ReleaseFoundry API from this pass.
- Treat official frontend evidence as product-shape evidence only: route/module names, labels, method names, keyword counts, state names, and redacted field names.
- This pass writes only this document.

## Evidence Inventory

| Evidence | Local source | Replay relevance |
|---|---|---|
| Official code crawl summary | `fixtures/a3/p3/releasefoundry_frontend_code_crawl_summary.redacted.json` | Clean-room module/chunk signals for Results review, Trace observability, Media evidence, Trust/audit, Usage, and admin exclusions. |
| Official frontend crawl notes | `docs/a3/p3_official_frontend_code_crawl_cleanroom_2026_07_07.md` | Defines clean-room boundary, route/page states, Observability product role, and A3 copy/non-copy decisions. |
| Code crawl parity growth | `docs/a3/p3_official_code_crawl_parity_growth_2026_07_07.md` | Records that `official_code_crawl_parity` is already exported to dashboard/report/print and covered by tests. |
| Official UI-compatible run | `fixtures/a3/p3/releasefoundry_dataset_884_run_11926_ui_tests_detail.redacted.json` | Shows the `run.result.tests[].action_results[]` shape that can become replay steps and tool-call diffs. |
| A3 run trace sample | `fixtures/a3/p3/releasefoundry_run_trace_sample.redacted.json` | Shows a redacted `run.result.cases[]` shape with observations, expected/actual, grade, pass/fail, score, and failure-like fields. |
| A1 schemas | `docs/a1/schemas/trace_event.schema.json`, `docs/a1/schemas/case_result.schema.json`, `docs/a1/schemas/run_result.schema.json` | Define the normalized trace event, case, and run fields A3 should replay. |
| A2 handoff and taxonomy | `docs/a2/a1_a3_handoff.md`, `docs/a2/failure_taxonomy_v0.md` | Define A1-to-A2 normalization and the canonical failure classes A3 should cluster by. |
| A2 grade schema | `docs/a2/schemas/grade_results.schema.json` | Defines judge mode, score, failure analysis, evidence, severity, remediation, and safety-blocking fields. |
| Existing replay docs | `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`, `docs/a3/p3_tool_call_diff.md` | Show the current A3 replay queue and tool-call diff behavior. |
| Current report/dashboard/tests | `services/report/report_builder.mjs`, `apps/dashboard/index.html`, `tests/a3/report_builder.test.mjs`, `tests/a3/dashboard_wiring.test.mjs`, `tests/a3/p3_releasefoundry_mapper.test.mjs` | Concrete places where replay fields are summarized, exported, rendered, and asserted. |

## Official Observability, Trace, And Code-crawl Evidence

The strongest official Observability signal is from the redacted code-crawl fixture, not from copied source. The fixture records:

- `schema_version: a3.official_frontend_code_crawl.v1`
- `generated_from: local zip entry names and keyword counts only`
- `crawl_scope.zip_file_count: 418`
- `crawl_scope.lab_javascript_chunk_count: 15`
- `crawl_scope.lab_css_chunk_count: 8`
- `crawl_scope.official_source_committed: false`
- `crawl_scope.raw_source_excerpt_committed: false`
- `safety.secret_values_saved: false`
- `safety.raw_cookies_saved: false`
- `safety.raw_tokens_saved: false`
- `safety.raw_signed_urls_saved: false`
- `safety.official_source_committed: false`

The official crawl identifies `ObservabilityPage-BmNyibq8.js` as `trace_observability`. Its clean-room keyword counts include trace, latency, errors, tool calls, voice, audio, and score. Its A3 decision is to copy trace, latency, error, and audio metadata concepts into incident replay, not to copy source or hosted account behavior.

The crawl also shows replay-adjacent supporting modules:

| Official signal | Clean-room role | A3 replay decision |
|---|---|---|
| `CreateRequestModal-LwtjGDgm.js` | request generation and results review | Use expected vs actual, score, tool-call, run history, timeline, and media review concepts. |
| `index-DSO2XOq6.js` | application shell and API client | Use read-only shell and release intelligence concepts; keep admin/mutation flows out of scope. |
| `DatasetsPage-C6F1zCF4.js` | dataset and run navigation | Use dataset/run navigation as local run list and case detail. |
| `AnalyticsPage-3IidZ_zD.js` | aggregate quality metrics | Use local pass-rate and trend concepts. |
| `TrustPage-DH1i4mLu.js` | trust and certificate | Use local audit bundle and verifier. |
| `UsagePage-CoD18uzD.js` | usage and billing shell | Keep read-only usage/quota awareness; no checkout or billing mutation. |
| `ApiKeysPage-DcsMtTi4.js`, `TeamPage-zKnEHkxH.js` | secret/admin flows | Out of scope for A3 MVP. |

The official parity targets already name `Trace observability` with official evidence from `ObservabilityPage-BmNyibq8.js` and `index-DSO2XOq6.js`. Its declared dependency is A1 trace/tool-call evidence plus A2 judge remediation. This is exactly the replay chain A3 should preserve.

## A1 Trace And Tool-call Fields For A3 Replay

A3 replay should start from the A1 evidence model because it proves what happened before any reviewer disposition is assigned.

Required A1 run fields that support replay:

| Field | Why A3 needs it |
|---|---|
| `run_id`, `dataset_id`, `runner_id` | Replay identity, provenance, report grouping, and run-level joins. |
| `status`, `total_cases`, `passed`, `failed`, `errored`, `timed_out` | Queue eligibility and release-risk summary. |
| `started_at`, `ended_at`, `duration_ms`, `latency_ms` | Timeline ordering and latency/error lanes inspired by ObservabilityPage. |
| `trace_completeness`, `aggregate_metrics.trace_completeness` | Whether the replay packet is trace-ready. |
| `cases[]` | Unit of replay, disposition, waiver, and report export. |

Required A1 case fields that support replay:

| Field | Why A3 needs it |
|---|---|
| `case_id`, `scenario_id`, `title`, `status` | Stable case detail and reviewer packet identity. |
| `expected` | Expected response points, expected tool calls, and tool policy. |
| `actual` or `agent_output` | Actual response and actual tool calls. |
| `observations[]` | Fallback timeline when normalized `trace_events[]` is missing. |
| `trace_events[]` | Primary replay timeline. |
| `metadata` | Media, source, fixture, route, and safety provenance. |

Required A1 trace event fields:

| Field | Replay use |
|---|---|
| `event_id`, `seq`, `timestamp`, `phase` | Deterministic replay ordering and trace anchor IDs. |
| `run_id`, `parent_id` | Join to run and nested event chains. |
| `event_type` | Classify dialogue, tool call, media event, VM stream, error, or retry. |
| `source`, `tags` | Distinguish local fixture, official-style import, media, retry, and judge-linked events. |
| `observation.kind`, `observation.channel`, `observation.status`, `observation.text`, `observation.data` | Human timeline row plus structured tool/media/error payload. |
| `metadata` | Redacted provenance and display hints. |

Required tool-call fields:

| Field | Replay use |
|---|---|
| `tool_calls[].name` or normalized `tool_calls[].tool` | Compare required vs actual tool category. |
| `tool_calls[].arguments` or normalized `tool_calls[].args` | Field-level argument diff. |
| `tool_calls[].call_id` or derived `tool_call_ids` | Join A1 trace rows to A2 judge evidence. |
| `expected.tool_calls[]` and `actual.tool_calls[]` | Build `tool_call_diffs[]`. |
| `output`, `error`, `status` when present | Detect ignored result, hallucinated result, or poor recovery. |

The official `11926` run fixture strengthens this mapping because it contains `run.result.tests[]` with per-test `action_results[]`. Within those actions, A3 can map:

- `action_type: tool_call`
- `tool_calls[].expected`
- `tool_calls[].actual`
- `tool_calls[].argument_comparison`
- `match_status`
- `divergence_notes`
- `expected_response`
- `actual_response`
- `semantic_similarity`
- media/input tags such as text, file, audio, or image-oriented action metadata

A3 should continue normalizing both official-style shapes:

- `run.result.cases[]` from older/direct run samples.
- `run.result.tests[].action_results[]` from UI-compatible result samples.

## A2 Judge And Failure Fields For Replay Disposition

A2 gives replay a disposition layer. A1 answers "what happened"; A2 answers "why it matters, who should review it, and what remediation is expected."

Required A2 top-level grade fields:

| Field | Replay disposition use |
|---|---|
| `schema_version: a2.local_judge_run.v1` | Contract guard for imported judge data. |
| `scenario_id`, `case_id` | Join to A1/A3 case rows. |
| `passed`, `score` | Queue ranking, release blocker thresholds, and report summary. |
| `primary_failure_class` | Failure cluster, owner lane, and replay queue grouping. |
| `judge_results[]` | Drilldown evidence per judge mode. |

Required nested judge fields:

| Field | Replay disposition use |
|---|---|
| `judge_mode`, `judge_version` | Distinguish trace, output, replay sandbox, semantic, and safety judges. |
| `rubric_scores[]` | Explain score contribution without rerunning judges. |
| `failure_analysis.primary_failure_class` | Judge-local failure label for detail panels. |
| `failure_analysis.failure_classes` | Secondary local signals for debugging. |
| `failure_analysis.severity` | Owner urgency and release blocker weighting. |
| `failure_analysis.blame_stage` | Route to tool-use, grounding, safety, or reasoning review lane. |
| `failure_analysis.summary`, `details`, `remediation` | Human disposition copy and next action. |
| `failure_analysis.safety_blocking` | Hard block for unsafe or secret-exposure paths. |
| `evidence.tool_call_ids` | Link judge finding to tool-call diff rows. |
| `evidence.trace_event_ids` when available | Link judge finding to replay timeline anchors. |
| `evidence.final_response_excerpt`, `tool_sequence`, `order_rules`, counts | Compact proof for report and reviewer packet. |

The canonical A2 disposition classes are:

`wrong_intent`, `missing_required_tool`, `unnecessary_tool_call`, `forbidden_tool_call`, `wrong_tool`, `wrong_arguments`, `wrong_tool_order`, `missing_clarification`, `hallucinated_tool_result`, `ignored_tool_result`, `unsafe_or_policy_violation`, and `poor_failure_recovery`.

A3 should keep `primary_failure_class` stable and canonical. Local or official-native signals can be preserved as nested evidence, but replay queue grouping should use the A2 canonical class or `none`.

## Replay Packet Model

A3 should make each failed or high-risk case replayable with one packet:

```json
{
  "schema_version": "a3.observability_replay_packet.v1",
  "run_id": "run-id",
  "case_id": "case-id",
  "scenario_id": "scenario-id",
  "source_shape": "a1_case_result|official_cases|official_tests_action_results",
  "official_route_hint": "?tab=analysis&dataset=884&run=11926",
  "result_visibility": "api_only|summary_api_visible|visual_confirmed|blocked",
  "trace_timeline": [],
  "tool_call_diffs": [],
  "judge_evidence": [],
  "media_evidence": [],
  "disposition": {
    "state": "new|needs_evidence|blocked|waiver_requested|approved|closed",
    "owner_lane": "tool_use|grounding|safety|reasoning|media|release",
    "primary_failure_class": "missing_required_tool",
    "severity": "major",
    "release_blocker": true,
    "next_action": "Replay trace, inspect missing confirm_cancel, then assign remediation."
  },
  "safety": {
    "redacted": true,
    "raw_signed_urls_saved": false,
    "secret_values_saved": false,
    "official_source_copied": false
  }
}
```

Replay readiness should be derived, not hand-labeled:

| Derived flag | True when |
|---|---|
| `trace_ready` | `trace_events[]` exists, or `observations[]`/`action_results[]` can be normalized. |
| `tool_diff_ready` | Expected and actual tool-call arrays exist or can be derived from `action_results[].tool_calls[]`. |
| `judge_evidence_ready` | A2 `judge_results[]` joins by `case_id`/`scenario_id`, with failure analysis or evidence IDs. |
| `media_metadata_ready` | Case/action metadata has media/input channel tags without live signed URLs. |
| `disposition_ready` | Failure class, severity, score, and remediation exist. |

## Recommended Schema Additions

Add these fields in a future code pass, keeping them optional until fixtures are migrated:

| Field | Location | Type | Purpose |
|---|---|---|---|
| `observability_replay_packets[]` | report JSON | array | Export replay-ready case packets for dashboard, Markdown, and audit bundle. |
| `source_shape` | case/replay packet | enum | Values: `a1_case_result`, `official_cases`, `official_tests_action_results`, `a3_generated_fixture`. |
| `official_observability_evidence` | report JSON | object | Records chunk names, route hints, page state, and redacted code-crawl fixture path. |
| `result_visibility` | case/replay packet | enum | Values: `not_applicable`, `empty`, `api_only`, `summary_api_visible`, `visual_confirmed`, `blocked`. |
| `official_route_hint` | case/replay packet | string/null | Non-secret route/query hint for manual parity review. |
| `trace_event_links[]` | tool diff and judge evidence | array | Stable references to `trace_events[].event_id`. |
| `tool_call_links[]` | trace event and judge evidence | array | Stable references to expected/actual tool-call rows. |
| `latency_ms` | trace event | number/null | Supports ObservabilityPage-style latency lanes. |
| `error_class` | trace event | string/null | Supports error/tool-error lanes without raw stack leakage. |
| `retry_index` | trace event | number/null | Makes retry/failure recovery replay explicit. |
| `disposition` | replay packet | object | Reviewer state, owner lane, blocker status, waiver/approval state, and next action. |
| `evidence_readiness` | replay packet | object | Booleans for trace/tool/judge/media/disposition readiness. |
| `clean_room_safety` | report JSON | object | Booleans for secrets, cookies, tokens, signed URLs, official source, and source excerpts. |

Suggested disposition states:

- `new`
- `needs_evidence`
- `blocked`
- `needs_owner_review`
- `waiver_requested`
- `approval_ready`
- `approved`
- `closed`

Suggested owner lanes:

- `tool_use`
- `grounding`
- `safety`
- `reasoning`
- `media`
- `observability`
- `release`

## Dashboard Assertions

Future `tests/a3/dashboard_wiring.test.mjs` coverage should assert:

1. The dashboard still renders `Official Code Crawl` with `ObservabilityPage-BmNyibq8.js` and classifies it as partial/copy-next trace evidence.
2. The dashboard renders an `Observability Replay` or `Incident Replay` panel with `trace_ready_count`, `tool_diff_ready_count`, and `judge_evidence_ready_count`.
3. Each replay row shows `run_id`, `case_id`, `primary_failure_class`, `severity`, score, owner lane, release blocker, trace count, tool-diff count, and judge-evidence count.
4. Selecting a replay row shows a timeline from `trace_events[]`, falling back to `observations[]` or official `action_results[]`.
5. Tool-call diffs show `match`, `missing_required_tool`, `unexpected_tool_call`, `wrong_tool`, `wrong_arguments`, and `wrong_tool_order`.
6. Judge evidence blocks show `judge_mode`, `score`, `failure_analysis.summary`, `severity`, `remediation`, `evidence.tool_call_ids`, and linked `trace_event_ids` when present.
7. Result visibility badges distinguish `api_only`, `summary_api_visible`, `visual_confirmed`, and `blocked`.
8. Admin/secret pages from the code crawl, especially API keys and Team, never become replay actions.
9. No raw signed URL, bearer token, cookie, API key, account email, or official source excerpt appears in the rendered HTML.

## Report Assertions

Future `tests/a3/report_builder.test.mjs` coverage should assert:

1. `buildJsonReport()` includes `official_code_crawl_parity.schema_version === "a3.official_code_crawl_parity.v1"`.
2. `official_code_crawl_parity.chunks[]` includes `ObservabilityPage-BmNyibq8.js` with trace-oriented top signals and `official_source_committed === false`.
3. `buildJsonReport()` includes `incident_replay_queue.schema_version === "a3.incident_replay_queue.v1"` and `observability_replay_packets[]` once added.
4. Replay packets join A1 `trace_events[]` and A2 `judge_results[]` by `case_id`/`scenario_id`.
5. Replay packets expose `trace_ready`, `tool_diff_ready`, `judge_evidence_ready`, `media_metadata_ready`, and `disposition_ready`.
6. Markdown output includes sections for `Official Code Crawl Parity`, `Incident Replay Queue`, and `Observability Replay` once added.
7. Markdown output includes replay steps that mention A1 trace/tool-call diffs and A2 judge evidence/remediation.
8. JSON and Markdown both preserve clean-room safety booleans: no source, no excerpts, no cookies, no tokens, no raw signed URLs, no secrets.
9. Print/PDF report data contains the same counts as JSON: replay queue count, trace-ready count, tool-diff-ready count, judge-evidence-ready count, and blocker count.

## Mapper Assertions

Future `tests/a3/p3_releasefoundry_mapper.test.mjs` coverage should assert:

1. `run.result.tests[].action_results[]` maps into normalized A3 cases.
2. `action_type: tool_call` maps expected and actual tool calls into `expected.tool_calls[]`, `actual.tool_calls[]`, and `tool_call_diffs[]`.
3. `argument_comparison` maps into field-level `argument_diffs[]`.
4. `match_status` maps to replay-compatible statuses such as exact/mismatch/partial/divergent and then into A3 failure summaries.
5. `expected_response`, `actual_response`, and `semantic_similarity` map into expected/actual response panels and score provenance.
6. Text, audio, image, and file action tags map to metadata-only media evidence.
7. `run.result.cases[]` and `run.result.tests[]` both produce the same required A3 case fields: `case_id`, `scenario_id`, `status`, `score`, `passed`, `expected`, `actual`, `observations`, and `trace_events`.
8. No mapper output contains raw signed URLs or secret-like values.

## Gate, Audit, And Redaction Assertions

Future gate/report tests should assert:

1. Release gate blocks when replay queue has critical safety failures or blocker cases without accepted waiver/approval evidence.
2. Reviewer workflow board requires `case_detail`, `expected_vs_actual`, `trace_timeline`, `tool_call_diff` when present, and `a2_judge_evidence`.
3. Waiver/approval records cannot mark replay cases as approved when required evidence artifacts are missing.
4. Audit manifest includes hashes/paths for A1 runs, A2 grades, coverage, thresholds, official code-crawl fixture, and replay packets.
5. Redaction scan rejects patterns for API keys, bearer tokens, cookies, raw signed URLs, private emails, and official source snippets.
6. `clean_room_safety.official_source_copied === false` and `clean_room_safety.raw_source_excerpt_committed === false` are hard assertions.

## Build Order

Recommended implementation order for a later code pass:

1. Add `summarizeObservabilityReplay()` that builds replay packets from existing incident replay items, trace events, tool-call diffs, and A2 judge evidence.
2. Add JSON export field `observability_replay`.
3. Add Markdown and print/PDF sections under existing replay/report flows.
4. Add dashboard panel or extend `Incident Replay` with Observability-specific trace, latency, error, retry, and tool-error lanes.
5. Add schema fixture or fixture-contract test for `a3.observability_replay_packet.v1`.
6. Add redaction regression tests before adding any richer official-observability fixture.

## Bottom Line

The clean-room replay thesis is simple: official Observability gives A3 the product direction, A1 gives the replayable trace and tool-call facts, and A2 gives the disposition language reviewers need to block, waive, approve, or remediate a risky release.

A3 should not clone the official Observability implementation. It should build an A3-owned replay layer from redacted fixtures, normalized trace events, tool-call diffs, judge evidence, and explicit clean-room safety checks.
