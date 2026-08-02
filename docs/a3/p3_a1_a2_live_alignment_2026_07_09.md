# A3 Live Alignment With Latest A1/A2 Main

Date: 2026-07-09

Lane: A3 Product / Workflow / Commercial UI

Main snapshot inspected: `origin/main` at `9bcd5347fbbf5c6be45d8d7c42bb24dfadcffde2`
(`Sync main with latest A1 and README`).

Network note: `git fetch origin main` was blocked by a GitHub HTTPS connection reset, but
`gh api repos/3351666087/release-foundry/branches/main` confirmed that remote
`main` still points at the same SHA as local `origin/main`.

## Why This Doc Exists

A3 should not invent its own truth. It should render and package what A1 and A2
already produce:

- A1 is the source of run execution, traces, observations, tool calls, agent
  output, and runtime metadata.
- A2 is the source of evaluation results, pass/fail, score, failure taxonomy,
  release gate, and readiness blockers.
- A3 is the consumer: dashboard, triage, report, review workflow, and commercial
  release UI.

This alignment pass is documentation-only. It does not change A1 runner logic or
A2 judge semantics.

## A1 Outputs A3 Must Consume

Primary files inspected on `origin/main`:

- `docs/a1/schemas/run_result.schema.json`
- `docs/a1/schemas/case_result.schema.json`
- `docs/a1/schemas/trace_event.schema.json`
- `docs/a1/schemas/observation.schema.json`
- `docs/a1/schemas/agent_turn.schema.json`
- `docs/a1/schemas/run_fixture.schema.json`
- `docs/a1/sdk_field_map.md`
- `docs/a1/evidence/local_run_30.json`

### RunResult

`A1 RunResult` is the run-level object A3 should treat as the top-level runtime
source.

Important fields:

| A1 field | A3 use |
|---|---|
| `run_id` | Run List id, Case Detail join key, report id context. |
| `dataset_id` | Dataset/project grouping in dashboard filters. |
| `runner_id` | Shows which runner produced evidence. |
| `status` | Run List status and release workflow status. |
| `total_cases`, `passed`, `failed`, `errored`, `timed_out` | Summary cards and run health. |
| `started_at`, `ended_at`, `duration_ms` | Timeline, latency, and report metadata. |
| `trace_completeness` | Whether trace evidence is strong enough for review. |
| `cases[]` | Case Detail source rows. |
| `aggregate_metrics` | Optional summary/usage evidence. |
| `metadata.local_only`, `metadata.releasefoundry_api_used` | Safety/source labeling. |
| `field_map_version` | Contract drift/debug context. |

Observed sample shape from `docs/a1/evidence/local_run_30.json` has top-level
keys matching the schema: `aggregate_metrics`, `cases`, `dataset_id`,
`duration_ms`, `ended_at`, `errored`, `failed`, `field_map_version`,
`max_workers`, `metadata`, `passed`, `run_id`, `runner_id`, `started_at`,
`status`, `timed_out`, `total_cases`, and `trace_completeness`.

### CaseResult

`CaseResult` is the unit A3 should display in Case Detail.

Important fields:

| A1 field | A3 use |
|---|---|
| `case_id` | Stable case join key with A2. |
| `scenario_id` | Stable scenario join key with A2. |
| `title` | Human-readable case title. |
| `status` | Runtime status, not final judge truth if A2 grade exists. |
| `latency_ms`, `started_at`, `ended_at` | Case timing. |
| `observations[]` | Trace timeline fallback and raw step evidence. |
| `agent_output` | Actual response and actual tool calls. |
| `expected` | Expected text/tool calls from runner/scenario. |
| `grade` | A1 nested local grade; use only as fallback when A2 aggregate grade is absent. |
| `metadata` | Source labels, replay/debug context. |

Rule for A3: prefer A2 `GradeResult` for pass/fail, score, and failure class.
Use A1 `case.status` and `case.grade` only as fallback or runtime context.

### Observation

`Observation` is A1's per-turn runtime evidence.

Important fields:

| A1 field | A3 use |
|---|---|
| `observation_id` | Linkable timeline item id. |
| `run_id`, `case_id` | Join to run/case. |
| `turn_index` | Timeline ordering. |
| `event_type` | Message/tool/error grouping. |
| `role` | User/assistant/tool/source display. |
| `content` | Text body for timeline. |
| `tool_calls[]` | Actual tool-call evidence. |
| `started_at`, `ended_at`, `latency_ms` | Step timing. |
| `status`, `error` | Error and retry display. |
| `vm_stream` | Optional media/VM-stream evidence. |

### TraceEvent

`TraceEvent` is the structured timeline shape.

Important fields:

| A1 field | A3 use |
|---|---|
| `schema = releasefoundry.trace.v1` | Version guard. |
| `event_id` | Stable UI anchor and evidence link. |
| `seq` | Timeline ordering. |
| `timestamp` | Timeline timestamp. |
| `phase` | Grouping such as dialogue/tool/runtime. |
| `source` | Origin label, for example agent/runner/scenario. |
| `parent_id` | Nested trace rendering if present. |
| `tags[]` | Filters and badges. |
| `observation.kind/channel/status/text/data` | Display body and structured tool-call data. |

A3 should sort trace items by `seq` first, then timestamp if needed. It should
not infer pass/fail from trace alone.

### AgentTurn And ToolCall

`AgentTurn` carries final assistant text and actual tool calls.

Important fields:

| A1 field | A3 use |
|---|---|
| `schema_version = releasefoundry.agent_turn.v1` | Version guard. |
| `text` | Actual final response. |
| `tool_calls[]` | Actual tool calls for Expected vs Actual. |
| `status` | Agent output status. |
| `latency_ms` | Response timing. |
| `error` | Runtime error display. |

Tool-call shape can appear as A1-native `name` / `arguments` / `call_id`, A2
normalized `tool` / `args`, or OpenAI-like nested fields. A3 should keep its
normalization tolerant:

- tool name: `name || tool || tool_name || function.name`
- arguments: `arguments || args || parameters || function.arguments`
- id: `id || tool_call_id || call_id`

## A2 Outputs A3 Must Consume

Primary files inspected on `origin/main`:

- `docs/a2/a1_a3_handoff.md`
- `docs/a2/schemas/grade_results.schema.json`
- `docs/a2/schemas/release_gate.schema.json`
- `docs/a2/failure_taxonomy_v0.md`
- `fixtures/a2/results/a2_g3_grade_results.json`
- `fixtures/a2/results/a2_release_gate_report.json`
- `fixtures/a2/results/a2_commercial_readiness_report.json`

### GradeResultsReport

`a2.grade_results.v1` is A3's main evaluation feed.

Observed current aggregate:

- `report_id`: `a2_g3_grade_results`
- `dataset_id`: `a2-g3-calibration`
- `scenario_pack`: `packages/scenarios/a2_g3_full_pack.json`
- `total_cases`: 32
- `passed`: 2
- `failed`: 30

Important fields:

| A2 field | A3 use |
|---|---|
| `schema_version` | Version guard. |
| `report_id` | Report/evidence source label. |
| `dataset_id` | Join/filter context. |
| `scenario_pack` | Scenario pack provenance. |
| `total_cases`, `passed`, `failed` | Dashboard summary and release overview. |
| `grade_results[]` | Per-case evaluation truth. |

### Per-Case GradeResult

Each `grade_results[]` item should override A1 fallback grade for user-facing
evaluation.

Important fields:

| A2 field | A3 use |
|---|---|
| `scenario_id` | Join key with A1 case/scenario. |
| `case_id` | Join key with A1 case. |
| `passed` | PASS/FAIL badge. |
| `score` | Score display; A2 score is 0-100. |
| `primary_failure_class` | Failure Cluster grouping. |
| `judge_results[]` | Rubric details and evidence. |

Current A2 first grade has keys: `schema_version`, `scenario_id`, `case_id`,
`passed`, `score`, `primary_failure_class`, and `judge_results`.

### JudgeResult And FailureAnalysis

Important nested fields:

| A2 field | A3 use |
|---|---|
| `judge_mode` | Which judge made the decision. |
| `judge_version` | Reproducibility/debug display. |
| `passed`, `score`, `max_score` | Per-judge detail rows. |
| `rubric_scores[]` | Rubric breakdown. |
| `failure_analysis.primary_failure_class` | Confirmed cluster class. |
| `failure_analysis.severity` | Severity badge. |
| `failure_analysis.summary` | Main failure explanation. |
| `failure_analysis.details[]` | Case Detail evidence. |
| `failure_analysis.remediation[]` | Reviewer next action. |
| `failure_analysis.safety_blocking` | Release-risk flag. |
| `evidence.tool_call_ids` | Link judge evidence to A1 tool calls. |
| `evidence.final_response_excerpt` | Link judge evidence to actual response. |
| `evidence.trace_event_ids` if present | Link judge evidence to A1 trace timeline. |

### Failure Taxonomy

A3 must keep Failure Cluster categories aligned with A2 canonical classes:

- `none`
- `wrong_intent`
- `missing_required_tool`
- `unnecessary_tool_call`
- `forbidden_tool_call`
- `wrong_tool`
- `wrong_arguments`
- `wrong_tool_order`
- `missing_clarification`
- `hallucinated_tool_result`
- `ignored_tool_result`
- `unsafe_or_policy_violation`
- `poor_failure_recovery`

Rule for A3: unknown/non-canonical local signals should be normalized for display,
but A3 must not invent new canonical classes without a coordinated A2 contract
change.

### ReleaseGateReport

`a2.release_gate.v1` is A3's release decision feed.

Observed current status:

- `decision`: `block`
- `current_commercial_gate`: `C2`
- `ready_for_commercial_gate`: `false`
- blockers: 7
- warnings: 3
- required evidence:
  - `releasefoundry_grading`: 6 required, 0 currently available
  - `llm_judge`: 6 required, 0 currently available

Important fields:

| A2 field | A3 use |
|---|---|
| `decision` | Release gate badge: pass/warn/block. |
| `exit_code` | CI/CLI result display. |
| `risk_score` | Commercial release risk. |
| `current_commercial_gate` | Current maturity gate. |
| `ready_for_commercial_gate` | Release readiness. |
| `blockers[]` | Release Gate blocker list. |
| `warnings[]` | Advisory list. |
| `required_evidence[]` | Missing evidence checklist. |
| `scenario_selection_gate` | Scenario coverage readiness. |
| `a1_output_policy_gate` | A1 evidence safety readiness. |
| `pr_annotations[]` | PR/check/report annotation copy. |
| `machine_contract.stable_join_keys` | Join guidance: `case_id`, `scenario_id`, `gate`. |
| `evidence_refs[]` | Public-safe evidence links. |

Rule for A3: render release-gate blockers and required evidence exactly as A2
publishes them. A3 may add UI grouping, but it must not mark a blocked A2 gate
as ready.

## A3 Join Strategy After Latest Main

A3 should join data in this order:

1. Load A1 `RunResult` or A3-compatible run fixture.
2. Flatten `runs[].cases[]` into dashboard cases.
3. Build `gradeByCase` from A2 `grade_results[]` by `case_id`.
4. For each case:
   - runtime fields from A1: `run_id`, `dataset_id`, `runner_id`, timings,
     observations, trace events, actual agent output, expected fields.
   - evaluation fields from A2: `passed`, `score`, `primary_failure_class`,
     `judge_results`, failure summary, severity, remediation.
5. Build Expected vs Actual:
   - expected from `case.expected.tool_calls` / scenario-derived expected calls.
   - actual from `case.actual.tool_calls`, `case.agent_output.tool_calls`, or
     `case.run.tool_calls`.
   - trace links from A1 `trace_events` and `observations`.
   - judge links from A2 `judge_results[].evidence`.
6. Build Failure Clusters from A2 `primary_failure_class`, not from A1 runtime
   status.
7. Load optional A2 readiness feeds only when present. Missing optional feeds
   must not break dashboard/report rendering.
8. Load A2 `ReleaseGateReport` as the release workflow truth.

## Current A3 Compatibility Evidence

Current A3 code already has a focused compatibility test:

- `tests/a3/a1_a2_compatibility_contract.test.mjs`

That test verifies:

- A1 trace events remain visible in normalized cases.
- A1 expected and actual tool calls survive report normalization.
- A2 pass/fail, score, severity, and `primary_failure_class` override fallback
  runtime status.
- Expected vs Actual tool-call diffs preserve trace links and A2 judge evidence.
- JSON, CSV, Markdown, shareable report, and dashboard wiring expose the A1/A2
  fields.
- A2 release gate, result persistence, and unblock checklist remain visible in
  report output.

Because the current compatibility test already covers the required join
contract, this pass did not edit it.

## A3 Guardrails

A3 must:

- Treat A1 as source of runtime evidence.
- Treat A2 as source of evaluation truth.
- Keep A2 scores on 0-100 scale; normalize A1 0-1 fallback scores only when A2
  aggregate grade is absent.
- Preserve `case_id` and `scenario_id` through every dashboard/report/export
  path.
- Preserve `run_id`, `event_id`, and tool-call ids so evidence remains linkable.
- Show `trace_completeness` and missing evidence as review risk.
- Keep release-gate `decision=block` blocking in the UI/report.
- Keep optional A2 commercial/readiness feeds additive.
- Keep raw private evidence out of tracked docs, fixtures, reports, screenshots,
  and logs.

A3 must not:

- Modify A1 runner semantics.
- Modify A2 judge semantics.
- Invent new canonical failure classes.
- Treat A1 runtime status as final pass/fail when A2 grade exists.
- Treat missing external ReleaseFoundry/LLM evidence as complete.
- Read private evidence refs to render public dashboard pages.
- Print or commit `.env.local`, API keys, tokens, cookies, account values, or
  raw signed URLs.

## Blockers And Follow-Ups

Current blockers inherited from A2 release gate:

- C3 remains blocked until reviewed ReleaseFoundry grading observations exist for the six
  required calibration cases.
- C4 remains blocked until audited live semantic judge observations replace
  offline references.
- C5 remains partial until case-book/regression replay evidence matures beyond
  current seed level.

A3 follow-ups:

1. Keep the dashboard/API/report path reading A2 `ReleaseGateReport` as a
   first-class release panel.
2. Add a small schema drift check if A1/A2 introduce `v2` schemas.
3. When A1 adds real tenant-scoped ingestion APIs, map `organization_id`,
   `project_id`, `environment_id`, `run_id`, `case_id`, and trace/tool-call ids
   without changing A2 score/failure semantics.
4. When A2 publishes reviewed ReleaseFoundry grading or live semantic judge evidence,
   surface it as calibration evidence, not as raw private payload.

