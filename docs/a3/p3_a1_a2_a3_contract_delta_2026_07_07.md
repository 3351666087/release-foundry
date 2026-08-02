# P3 A1/A2/A3 Contract Delta - 2026-07-07

Author: A3 Integration Explorer
Scope: local repo calibration only. This pass did not read `.env.local` or secret files, and does not quote raw token-like fixture content.

## Files Checked

- A1 docs/schemas: `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/schemas/run_result.schema.json`, `docs/a1/schemas/case_result.schema.json`, `docs/a1/schemas/agent_turn.schema.json`, `docs/a1/schemas/observation.schema.json`, `docs/a1/schemas/trace_event.schema.json`, `docs/a1/schemas/grade_result.schema.json`.
- A1 runner/sdk code: `services/runner/runner.py`, `services/runner/dataset_adapter.py`, `services/runner/api_probe.py`, `services/runner/cli.py`, `packages/sdk/releasefoundry/types.py`, `packages/sdk/releasefoundry/adapter.py`, `packages/sdk/releasefoundry/dataset_adapter.py`, `packages/sdk/releasefoundry/trace.py`.
- A2 docs/schemas/fixtures/code: `docs/a2/a1_a3_handoff.md`, `docs/a2/schemas/grade_results.schema.json`, `docs/a2/schemas/coverage_report.schema.json`, `docs/a2/schemas/calibration_matrix.schema.json`, `fixtures/a2/results/*.json`, `fixtures/a2/runs/*.json`, `packages/scenarios/a2_g3_full_pack.json`, `services/judge/runner.py`.
- A3 docs/code/tests: `docs/a3/p3_field_mapping.md`, `services/report/report_builder.mjs`, `services/report/p3_releasefoundry_mapper.mjs`, `services/report/a3_fixture_builder.mjs`, `services/report/a3_gate_cli.mjs`, `tests/a3/*.mjs`.
- Expected but missing: `fixtures/a1` does not exist in this checkout. A1 public evidence is currently under `docs/a1/evidence` plus schemas/code, not a `fixtures/a1` directory.

## A1 Current Fields Available To A3

### Local `RunResult`

Source of truth:

- Schema: `docs/a1/schemas/run_result.schema.json`
- Dataclass/export: `packages/sdk/releasefoundry/types.py`
- Producer: `services/runner/runner.py`

Current A1 run-level fields that A3 can consume:

- Identity and grouping: `run_id`, `dataset_id`, `runner_id`, `field_map_version`.
- Status/counts: `status`, `total_cases`, `passed`, `failed`, `errored`, `timed_out`.
- Timing/execution: `started_at`, `ended_at`, `duration_ms`, `max_workers`, `trace_completeness`.
- Payloads: `cases[]`, `aggregate_metrics`, `metadata`.
- `aggregate_metrics` currently includes at least `schema_version`, `trace_completeness`, `passed`, `failed`, `errored`, `timed_out`, `total_tool_calls`.
- `metadata` explicitly supports `local_only=true` and `releasefoundry_api_used=false`.

### Local `CaseResult`

Source of truth:

- Schema: `docs/a1/schemas/case_result.schema.json`
- Dataclass/export: `packages/sdk/releasefoundry/types.py`
- Producer: `services/runner/runner.py`

Current case-level fields:

- Identity/display: `case_id`, `scenario_id`, `title`, `status`.
- Timing: `started_at`, `ended_at`, `latency_ms`.
- Replay/evidence: `observations[]`, `agent_output`, `expected`, `metadata`, optional `error`.
- Local grading: `grade`.

Current A1 nested `grade` fields:

- `scenario_id`, `passed`, `score`, `label`, `reason`, `expected`, `actual`, optional `metrics`.
- Important scale note: A1 `grade.score` is defined as 0-1 in `docs/a1/schemas/grade_result.schema.json`.

### Local `AgentTurn` / `ToolCall`

Source of truth:

- Schema: `docs/a1/schemas/agent_turn.schema.json`
- Dataclass/export: `packages/sdk/releasefoundry/types.py`
- Adapter: `packages/sdk/releasefoundry/adapter.py`

Current fields:

- `schema_version=releasefoundry.agent_turn.v1`
- `text`
- `tool_calls[]`
- `status`
- `latency_ms`
- `metadata`
- optional `error.type`, `error.message`

Current normalized tool-call fields available from the SDK:

- `name`
- `arguments`
- `arguments_json`
- `call_id`
- `output`
- `latency_ms`
- `error`

The A1-to-A2 projection in `packages/sdk/releasefoundry/adapter.py` exposes `to_a2_judge_run(...)`, which emits:

- `tool_calls[].tool`
- `tool_calls[].args`
- `tool_calls[].name`
- `tool_calls[].arguments`
- optional `tool_calls[].id`
- `final_response`
- optional `expected_keywords`
- optional `forbidden_keywords`

### Observations, Trace, And VM Stream

Source of truth:

- Observation schema: `docs/a1/schemas/observation.schema.json`
- Trace schema: `docs/a1/schemas/trace_event.schema.json`
- Trace code: `packages/sdk/releasefoundry/trace.py`
- Runner producer: `services/runner/runner.py`

Current `observations[]` fields:

- `observation_id`, `run_id`, `case_id`, `turn_index`, `event_type`, `role`, `content`, `tool_calls`, `started_at`, `ended_at`, `latency_ms`, `status`, optional `error`, `metadata`.
- Optional `vm_stream` with `provider`, `session_id`, `duration_ms`, `logs`, `metadata`.

Current `trace_events[]` / strict replay fixture fields:

- `schema=releasefoundry.trace.v1`
- `type=trace_event`
- `event_type`, `run_id`, `event_id`, `seq`, `timestamp`, `phase`, `source`, `parent_id`, `tags`, `observation`, `metadata`
- `observation.kind`, `observation.channel`, `observation.status`, `observation.text`, `observation.data`

### Dataset Source / Media Input Envelope

Source of truth:

- Field map: `docs/a1/sdk_field_map.md`
- Adapter: `packages/sdk/releasefoundry/dataset_adapter.py`
- CLI bridge: `services/runner/dataset_adapter.py`

Current A1 media/input fields that can feed A3 later:

- `AgentInput.schema_version=releasefoundry.agent_input.v1`
- `AgentInput.text`
- `AgentInput.parts[]`
- `AgentInput.metadata`
- part fields: `type`, `text`, `path`, `url`, `source`, `mime_type`, `name`, `description`
- accepted part types: `text`, `image`, `audio`, `file`

Current `dataset_source.runs` adapter fields:

- Run/scenario: `run_id`, `title`, `description`, `intent`, `intent_tags`, `audio_tags`, `actions[]`.
- Action: `actor`, `content`, `name`, `action_type`, `output_path`, `expected_response`, `action_tags`.
- Adapter-generated case metadata: `adapter_version`, `source`, `dataset_type`, `total_runs`, `source_run_hash`, `action_count`, `action_index`, `action_name`, `action_type`, `requires_external_judge`, `intent_tags`, `audio_tags`, `action_tags`.

## A2 Current Fields Available To A3

### A2 Normalized Run Input

Source of truth:

- Handoff doc: `docs/a2/a1_a3_handoff.md`
- Normalizer: `services/judge/runner.py`

A2 accepts the lightweight run shape:

- `tool_calls[]`
- `tool_calls[].tool`
- `tool_calls[].args`
- `final_response`
- optional `expected_keywords`
- optional `forbidden_keywords`

A2 also accepts native A1 shapes:

- `AgentTurn` / `agent_output`: `schema_version`, `text`, `tool_calls[].name`, `tool_calls[].arguments`, `tool_calls[].call_id`, `status`, `latency_ms`, `metadata`.
- `CaseResult`: `case_id`, `scenario_id`, `status`, `agent_output`, `observations`, `expected`, `actual`, `metadata`.

Normalizer details in `services/judge/runner.py`:

- `normalize_run_input(...)` copies `case_id`, `status`, `error`, `latency_ms`, `observations`, `trace_events`, `expected`, `actual`, `expected_keywords`, `forbidden_keywords`, `expected_facts`, `forbidden_facts`, `metadata` when present.
- `_normalize_tool_call(...)` maps `tool`, `name`, OpenAI-style `function.name`, `type`, `args`, `arguments`, `function.arguments`, `arguments_json`, `input`, `id`, and `call_id`.
- `_final_response(...)` reads `final_response`, `text`, `content`, or assistant observation content.

### A2 Local Judge Output

Source of truth:

- Schema: `docs/a2/schemas/grade_results.schema.json`
- Aggregated fixture: `fixtures/a2/results/a2_g3_grade_results.json`
- Handoff doc: `docs/a2/a1_a3_handoff.md`

Top-level aggregate fields:

- `schema_version=a2.grade_results.v1`
- `report_id`
- `dataset_id`
- `scenario_pack`
- `total_cases`
- `passed`
- `failed`
- `grade_results[]`

Each `grade_results[]` item:

- `schema_version=a2.local_judge_run.v1`
- `scenario_id`
- `case_id`
- `passed`
- `score`
- `primary_failure_class`
- `judge_results[]`

Important scale note: A2 `score` and judge `score` are 0-100, with `max_score=100` on per-judge results.

Each `judge_results[]` item:

- `schema_version=a2.grade_result.v1`
- `scenario_id`
- `case_id`
- `judge_mode`
- `judge_version`
- `passed`
- `score`
- `max_score`
- `rubric_scores[]`
- `failure_analysis`
- `evidence`
- `metadata`

Each `failure_analysis` item:

- `schema_version=a2.failure_analysis.v1`
- `primary_failure_class`
- `failure_classes[]`
- `severity`
- `blame_stage`
- `summary`
- `details[]`
- `remediation[]`
- `safety_blocking`

Current canonical A2 failure classes:

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

### A2 Coverage / Calibration / Readiness Feeds

Source of truth:

- Coverage schema: `docs/a2/schemas/coverage_report.schema.json`
- Calibration schema: `docs/a2/schemas/calibration_matrix.schema.json`
- Fixtures under `fixtures/a2/results/`

Required/current A2 optional feeds available to A3:

- `a2.coverage_report.v1`: `pack_id`, `assignment_checks`, `meets_assignment_minimums`, `scenario_count`, `scenario_dimension_counts`, `scenario_dimension_scenarios`, `scenario_quality_warnings`, `difficulty_counts`, `action_count_counts`, `environment_counts`, `tag_counts`, `tool_policy_shape_counts`, `required_tool_counts`, `optional_tool_counts`, `forbidden_tool_counts`, `ordered_tool_count`, `ordered_tool_pairs`, `fixture_type_counts`, `rubric_classes`, `judge_modes`, `primary_failure_class_counts`, `golden_failure_class_cases`, `executable_failure_class_cases`, `executable_media_case_refs`, `executable_tool_output_grounding_case_refs`, `coverage_warnings`.
- `a2.calibration_matrix.v1`: `matrix_id`, `dataset_id`, `scenario_pack`, `case_count`, `sources`, `source_coverage`, `agreement_summary`, `cost_ledger`, `calibration_warnings`, `cases[]`, `metadata`.
- `a2.evidence_readiness.v1`: `status`, `ready_for_external_collection`, `calibration_case_count`, `readiness_checks`, `releasefoundry_grading_preflight`, `semantic_judge_preflight`, `redaction_policy`, `batch_plan_refs`.
- Additional optional planning/evidence feeds observed in `fixtures/a2/results/`: `a2.case_book.v1`, `a2.regression_replay.v1`, `a2.sdk_parity.v1`, `a2.semantic_harness.v1`, `a2.batch_plan.v1`, `a2.commercial_readiness.v1`.

### A2 Scenario Pack Fields

Source of truth:

- `packages/scenarios/a2_g3_full_pack.json`

Current pack summary:

- `schema_version=a2.scenario_pack.v1`
- `scenario_count=60`
- top-level fields: `description`, `judge_modes`, `pack_id`, `rubric_classes`, `scenarios`, `schema_version`
- scenario fields: `id`, `title`, `family`, `difficulty`, `userTask`, `actions`, `toolPolicy`, `expectedBehaviors`, `expectedFacts`, `forbiddenFacts`, `expectedToolOutputFacts`, `failureSignals`, `primaryFailureClass`, `primaryRubric`, `rubric`, `fixtureRefs`, `tags`
- `toolPolicy` fields: `required`, `optional`, `forbidden`, `order`
- `actions[].expectedToolCalls`, `actions[].expectedResponse`, `actions[].environment` are used by the A3 fixture builder.

## A3 Current Consumed Fields

### Report Builder Core

Source of truth:

- `services/report/report_builder.mjs`
- `tests/a3/report_builder.test.mjs`

Core A3 inputs consumed by `normalizeCases(...)`:

- Run fixture: `runs[]`, or a direct run object with `run_id`.
- Run fields copied into each case: `run_id`, `dataset_id`, `runner_id`, `status` as `run_status`.
- Case fields: `case_id`, `scenario_id`, `title`, `family`, `status`, `score`, `primary_failure_class`, `failure_summary`, `severity`, `expected`, `actual`, `media_evidence`, `trace_events`, `observations`, `metadata`.
- Grade fixture: `grade_results[]`, joined by `case_id`.
- Grade fields: `case_id`, `passed`, `score`, `primary_failure_class`, `judge_results[]`, `metadata`.
- Judge fields: `judge_mode`, `passed`, `failure_analysis`.
- Failure analysis fields: `primary_failure_class`, `summary`, `severity`.

Core summary/output fields consumed or generated:

- `buildDashboardSummary(...)`: `totalRuns`, `totalCases`, `passed`, `failed`, `passRate`, `avgScore`, `traceCompleteness`, `mediaEvidenceCases`, `vmStreamCases`, `lastRunId`.
- `buildJsonReport(...)`: emits `schema_version=a3.export_report.v1`, `summary`, `coverage`, `evidence_readiness`, `request_provenance`, `usage_quota`, `media_readiness`, `cloud_console_shell`, `official_releasefoundry_gap`, `official_frontend_mirror`, `official_code_crawl_parity`, `official_parity_roadmap`, `release_gate`, `release_workflow`, `release_war_room`, `incident_replay_queue`, `reviewer_workflow_board`, `observability_replay_matrix`, `failure_clusters`, `cases[]`.
- `buildToolCallDiffs(...)` consumes `expected.tool_calls[]` and `actual.tool_calls[]`; `normalizeToolCalls(...)` recognizes `id`, `tool_call_id`, `tool_name`, `name`, `tool`, `arguments`, `args`, `parameters`.

A3 failure-class normalization:

- `canonicalPrimaryFailureClass(...)` accepts A2 canonical classes directly.
- It maps local A3/ReleaseFoundry-derived `bad_final_response`, `output_schema_invalid`, and `unknown_failure` into `wrong_intent` for failed cases.
- Passed cases with no class normalize to `none`.

### A2-to-A3 Fixture Builder

Source of truth:

- `services/report/a3_fixture_builder.mjs`
- `tests/a3/a3_fixture_builder.test.mjs`

Inputs consumed:

- Scenario pack: `packages/scenarios/a2_g3_full_pack.json`
- A2 grades: `fixtures/a2/results/a2_g3_grade_results.json`
- A2 executable run fixtures: `fixtures/a2/runs/*.json`

Fields consumed:

- Scenario: `id`, `title`, `family`, `userTask`, `actions[]`, `actions[].expectedToolCalls`, `actions[].expectedResponse`, `toolPolicy`, `expectedBehaviors`, `primaryRubric`, `difficulty`, `tags`.
- A2 grade: `case_id`, `scenario_id`, `passed`, `score`, `primary_failure_class`, `judge_results[]`, `judge_results[].failure_analysis`.
- A2 run fixture: `case_id`, `scenario_id`, `run.tool_calls[]`, `run.final_response`, `run.expected_facts`, `run.forbidden_facts`.

Fields emitted for A3:

- `runFixture.schema_version=a3.dashboard_fixture.v1`
- `runFixture.fixture_id`
- `runFixture.source_notes`
- `runs[].run_id`, `dataset_id`, `runner_id`, `status`, `total_cases`, `passed`, `failed`, `errored`, `timed_out`, `started_at`, `ended_at`, `duration_ms`, `max_workers`, `trace_completeness`, `metadata`, `cases[]`
- `cases[].case_id`, `scenario_id`, `title`, `family`, `status`, `score`, `latency_ms`, `primary_failure_class`, `severity`, `failure_summary`, `expected`, `actual`, `observations`, `trace_events`, `metadata`
- `gradeFixture.schema_version=a3.grade_fixture.v1`
- `gradeFixture.grade_results[]` preserves A2 `grade_results[]`.

### Real ReleaseFoundry / P3 Mapper

Source of truth:

- `docs/a3/p3_field_mapping.md`
- `services/report/p3_releasefoundry_mapper.mjs`
- `tests/a3/p3_releasefoundry_mapper.test.mjs`

Input shapes consumed:

- `response.run`, `run`, `runs[]`, `list_runs.runs[]`, `calls.list_runs.sample.runs[]`, direct `{id,result}` run.
- `response.dataset`, `dataset`, `datasets[]`, `list_datasets.datasets[]`, `calls.list_datasets.sample.datasets[]`, direct `{dataset_source}` dataset.
- `run.result.tests[]` with `tests[].action_results[]`.
- `run.result.cases[]` with `cases[].grade`, `cases[].expected`, `cases[].actual`, `cases[].observations`, `cases[].trace_events`, `cases[].metadata`.

Run fields consumed:

- `run.id`
- `run.created_at`
- `run.dataset`
- `run.runner`
- `run.dataset_details.id`
- `run.runner_details.id`
- `run.result.status`
- `run.result.started_at`
- `run.result.completed_at`
- `run.result.ended_at`
- `run.result.aggregate_metrics.total_tests`
- `run.result.aggregate_metrics.tests_passed`
- `run.result.aggregate_metrics.tests_failed`
- `run.result.aggregate_metrics.passed`
- `run.result.aggregate_metrics.failed`
- `run.result.total_cases`
- `run.result.passed`
- `run.result.failed`

Test/action fields consumed:

- `tests[].test_id`, `tests[].scenario_id`, `tests[].run_id`, `tests[].title`, `tests[].status`, `tests[].started_at`, `tests[].completed_at`, `tests[].coherence`
- `action_results[].actor`, `action_results[].action_type`, `action_results[].action_index`, `action_results[].text`, `action_results[].expected_response`, `action_results[].actual_response`, `action_results[].match_status`, `action_results[].semantic_similarity`, `action_results[].divergence_notes`, `action_results[].tool_calls[]`, `action_results[].action_tags`, `action_results[].output_path`, `action_results[].vm_stream`
- `tool_calls[].expected`, `tool_calls[].actual`, `tool_calls[].match_status`, `tool_calls[].argument_comparison`, `tool_calls[].divergence_notes`

Case-result fields consumed:

- `case.case_id`, `case.scenario_id`, `case.title`, `case.family`, `case.status`, `case.score`, `case.severity`, `case.failure_summary`, `case.expected`, `case.actual`, `case.agent_output`, `case.observations`, `case.trace_events`, `case.metadata`
- `case.grade.scenario_id`, `case.grade.expected`, `case.grade.actual`, `case.grade.passed`, `case.grade.score`, `case.grade.metrics`, `case.grade.reason`

Dataset scenario fields consumed:

- `dataset.id`, `dataset.dataset_id`, `dataset.dataset_source.dataset_type`, `dataset.dataset_source.runs`
- Scenario: `run_id`, `id`, `scenario_id`, `case_id`, `title`, `name`, `description`, `intent_tags`, `audio_tags`, `actions[]`
- Action: `action_type`, `action_tags`, `output_path`, `signed_url`

Fields emitted for A3:

- `runFixture.schema_version=a3.dashboard_fixture.v1`
- `gradeFixture.schema_version=a3.grade_fixture.v1`
- A3 run/case fields listed above.
- `media_evidence.schema_version=a3.media_evidence.v1`
- `media_evidence.source`
- `media_evidence.primary_media_type`
- `media_evidence.media_types[]`
- `media_evidence.evidence_items[]`
- `media_evidence.action_tags[]`
- `media_evidence.output_paths[]`
- `media_evidence.audio_tags[]`
- `media_evidence.intent_tags[]`
- `media_evidence.vm_streams[]`
- `media_evidence.known_gaps[]`
- synthetic `grade_result.schema_version=a3.p3_releasefoundry_grade_result.v1`
- `grade_result.metadata.score_source` and `score_source_detail`

### Optional A3 Feeds And Gate CLI

Source of truth:

- `services/report/report_builder.mjs`
- `services/report/a3_gate_cli.mjs`
- `tests/a3/report_builder.test.mjs`
- `tests/a3/a3_gate_cli.test.mjs`
- `tests/a3/dashboard_wiring.test.mjs`

A3 currently consumes optional A2/A3 feeds:

- Coverage: `a2.coverage_report.v1` via `summarizeCoverage(...)`.
- Evidence readiness: `a2.evidence_readiness.v1` via `summarizeEvidenceReadiness(...)`.
- Request provenance: request samples with `request_status`, `status`, `created_at`, `completed_at`, `actual_duration_s`, `estimated_duration_s`, `request.agent.accepted_inputs`, `request.generation_options`, `request.test_config`, `request.agent.tools`, `request_input_schema.tools`.
- Usage/quota: frontend/API summary fields such as `frontend_known_modules`, `api_paths`, `calls`, `field_paths`, `frontend_source_functions`.
- Media signed URL coverage: `signed_url_by_nearest_type`, `output_path_by_nearest_type`, `accepted_input_flags`, `generation_output_flags`, `conclusion`.
- Frontend mirror/code-crawl summaries: clean-room parity fields consumed by `summarizeOfficialFrontendMirror(...)` and `summarizeOfficialCodeCrawlParity(...)`.

Gate CLI currently consumes:

- Required: `--runs`, `--grades`.
- Optional: `--coverage`, `--media-signed-url-coverage`, `--thresholds`, `--waiver`, `--approval`.
- It emits `schema_version=a3.gate_cli.v1`, `summary`, `release_gate`, `release_workflow`, `waiver_review`, `approval_review`, `github_check_run`, `pr_comment_markdown`, `audit_manifest`, and redaction metadata.

## Contract Gaps

1. `fixtures/a1` is missing.
   - User-requested inspection target `fixtures/a1` does not exist.
   - A1 has schemas and evidence under `docs/a1/`, but no committed A1 fixture directory parallel to `fixtures/a2`.
   - A3 therefore cannot regression-test direct A1 fixture ingestion from a stable public fixture path.

2. A1 `RunResult` is close to A3 `runFixture.runs[]`, but there is no explicit A1-to-A3 fixture adapter contract.
   - A1 emits `RunResult` directly with `cases[]`.
   - A3 expects wrapper `schema_version=a3.dashboard_fixture.v1`, `fixture_id`, and `runs[]`.
   - A3 can tolerate direct run objects in `normalizeCases(...)`, but dashboards/tests mostly use wrapper fixtures.

3. A1 `grade.score` is 0-1, A2/A3 grade results are 0-100.
   - A3 `normalizeScore(...)` handles 0-1 nested case grades, but the boundary is implicit.
   - A1 `grade.score=0.62` becomes A3 `score=62`; A2 `score=62` remains `62`.
   - Next contract should record `score_scale` or `score_source` at A1 and A2 join points.

4. A1 `grade` lacks A2 canonical `primary_failure_class`.
   - A1 local `GradeResult` has `label`, `reason`, `metrics`, `expected`, `actual`.
   - A2/A3 triage depends on `primary_failure_class`, `failure_analysis.severity`, `blame_stage`, `details`, `remediation`, `safety_blocking`.
   - A3 currently falls back to `wrong_intent` for unknown failed classes.

5. A1 traces and A3 traces are compatible in spirit but not one stable field path.
   - A1 `Observation.vm_stream` lives under `cases[].observations[]`.
   - A1 strict `TraceEvent` exists, but `RunResult` schema does not require `cases[].trace_events`.
   - A3 consumes both `case.trace_events` and `case.observations`, but replay readiness is stronger when `trace_events[]` exists.

6. A2 consumes A1 `observations` and `trace_events`, but A2 grading evidence does not preserve all replay detail.
   - `services/judge/runner.py` passes these fields through normalized input.
   - A2 `judge_results[].evidence` stores compact facts such as `tool_call_ids`, `tool_sequence`, `final_response_excerpt`, `tool_call_count`, `observation_count`.
   - A3 reviewer/incident flows need both compact A2 judge evidence and fuller A1 replay evidence.

7. Tool-call naming is normalized in multiple places with slightly different names.
   - A1 SDK: `name`, `arguments`, `call_id`.
   - A2 lightweight input: `tool`, `args`, optional `id`.
   - A3 diff: `tool_name`, `name`, `tool`, `arguments`, `args`, `parameters`.
   - P3 ReleaseFoundry mapper: expected/actual often use `tool_name`.
   - No single shared `tool_registry` or alias table exists.

8. Media evidence has strong P3 mapper support, weaker A1/A2 first-class contract.
   - A1 supports `AgentInput.parts[]`, dataset `action_type`, `output_path`, `action_tags`, `audio_tags`, `intent_tags`, and `vm_stream`.
   - A2 coverage reports `executable_media_case_count`, `executable_media_case_refs`, and media expected class counts.
   - A3 uses `media_evidence.*`, but A1/A2 do not yet emit `media_evidence.schema_version=a3.media_evidence.v1` directly.

9. A2 optional feeds are documented as non-breaking, but A3 dashboard wiring now depends on many of them for richer panels.
   - Missing optional feeds should not break core A3, but current dashboard/gate tests exercise coverage, readiness, media URL coverage, frontend mirror, usage, request provenance, release gate, waiver, approval, and audit bundle flows.
   - Need a loader contract that declares which optional feeds are absent vs present vs stale.

10. Native backend failure class remains unavailable in P3 ReleaseFoundry evidence.
    - `docs/a3/p3_field_mapping.md` records no named backend `failure_class` in observed failed runs.
    - `services/report/p3_releasefoundry_mapper.mjs` derives `missing_required_tool`, `wrong_arguments`, `bad_final_response`, `run_error`, or `unknown_failure` from `grade.metrics`, `match_status`, `argument_comparison`, `expected/actual`, and status.
    - A3 then canonicalizes some local classes to A2 classes.

11. A2 `expectedBehaviors` shape is array-like in scenarios but summarized as multiple A3 fields.
    - `packages/scenarios/a2_g3_full_pack.json` has scenario `expectedBehaviors`.
    - `services/report/a3_fixture_builder.mjs` maps it to `expected.final_response_points`.
    - A2 run fixtures can also contain `run.expected_facts` and `run.forbidden_facts`, which A3 places under `actual.expected_facts` and `actual.forbidden_facts`; the naming is confusing for review.

12. A3 gate/audit artifacts are redacted, but source fixture safety is uneven by design.
    - `services/report/a3_gate_cli.mjs` redacts CLI payloads and generated artifacts.
    - Some A2 safety fixtures intentionally contain secret-like strings to test detection. A3 docs should reference only fields/paths, not raw values.

## Next Round Code Tasks

1. Add a public-safe A1 fixture set.
   - Create `fixtures/a1/` with one tiny `RunResult` fixture and one direct `AgentTurn` fixture.
   - Include `cases[].observations[]`, `cases[].agent_output.tool_calls[]`, `cases[].grade`, and one `vm_stream`.
   - Add tests that A3 `normalizeCases(...)` can consume the fixture without A2 grades.

2. Add an explicit A1-to-A3 wrapper builder.
   - New code task target: `services/report/a3_fixture_builder.mjs`.
   - Add `buildA3FixturesFromA1RunResult(...)`.
   - Map A1 `RunResult` to `a3.dashboard_fixture.v1`.
   - Preserve A1 `grade` as either `case.grade` or a generated `a3.grade_fixture.v1` entry with `metadata.score_source=a1_case_grade_score`.

3. Add score provenance everywhere A3 joins grades.
   - Add or normalize `metadata.score_source` and `metadata.score_scale`.
   - Expected values: `a1_case_grade_score_0_1`, `a2_local_judge_score_0_100`, `releasefoundry_case_grade_score`, `semantic_similarity_average`, `pass_fail_default`.
   - Test in `tests/a3/report_builder.test.mjs`.

4. Add A1 failure-class bridge.
   - Translate A1 `grade.metrics.text_match=false` to `wrong_intent` or `bad_final_response` before A3 canonicalization.
   - Translate A1 `grade.metrics.tool_match=false` with missing actual tool to `missing_required_tool`; with wrong args to `wrong_arguments`.
   - Preserve original A1 `grade.label` and `grade.reason` in `failure_summary` / metadata.

5. Promote `trace_events[]` into A1 `CaseResult` output when available.
   - `docs/a1/schemas/case_result.schema.json` currently does not require `trace_events`.
   - Add optional `trace_events` to A1 schema and `services/runner/runner.py` output if generated from `Observation.vm_stream`.
   - Keep `observations[]` as the stable minimum.

6. Create a shared tool-call normalization helper or spec.
   - Candidate shared fields: `id`, `name`, `arguments`, `output`, `expected`, `actual`, `match_status`.
   - Document aliases: `tool`, `tool_name`, `args`, `parameters`, `call_id`, `tool_call_id`.
   - Reuse in `packages/sdk/releasefoundry/adapter.py`, `services/judge/runner.py`, `services/report/report_builder.mjs`, and `services/report/p3_releasefoundry_mapper.mjs`.

7. Add an optional feed manifest for A3 dashboards.
   - New fixture shape: `a3.feed_manifest.v1`.
   - Track each feed path, schema_version, required/optional, loaded/missing/stale, and redaction status.
   - This will make missing `coverage`, `readiness`, `usage`, `request`, and `frontend mirror` data explicit instead of silent `{}`.

8. Add media evidence bridge from A1/A2 to A3.
   - Convert A1 `AgentInput.parts[]`, dataset `action_type`, `output_path`, `action_tags`, `audio_tags`, `intent_tags`, and `Observation.vm_stream` into `media_evidence`.
   - Convert A2 coverage media refs into report-level media readiness rows even when case-level media evidence is absent.

9. Add tests for direct A2 optional feeds in `buildJsonReport(...)`.
   - Current tests cover many optional feeds through fixture combinations.
   - Add one compact test that loads all A2 optional result fixtures from `fixtures/a2/results/` and asserts missing optional feeds remain non-breaking.

10. Add a contract-delta CI check.
    - Check that `docs/a1/schemas/*.json`, `docs/a2/schemas/*.json`, `services/report/report_builder.mjs`, and `services/report/p3_releasefoundry_mapper.mjs` do not drift without updating `docs/a3/*contract_delta*`.
    - This can be a lightweight timestamp/hash manifest, not a hard governance wall.

## Immediate Calibration Decision

- Core A1/A2/A3 path is viable today for local triage:
  - A1 can emit `RunResult.cases[]` with `grade`, `agent_output`, `observations`, and `vm_stream`.
  - A2 can grade A1 `AgentTurn` / `CaseResult` into `a2.grade_results.v1`.
  - A3 can join run fixtures plus grade fixtures, normalize scores, cluster canonical A2 failures, compute tool-call diffs, and package gate/reviewer/replay outputs.
- The strongest next move is not more dashboard UI. It is adding public-safe `fixtures/a1` plus a tested A1-to-A3 fixture wrapper, because that closes the only missing source directory in this pass and makes the A1 path as reproducible as the A2 path.
