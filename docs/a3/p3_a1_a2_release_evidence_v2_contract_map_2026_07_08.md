# P3 A1/A2 Release Evidence v2 Contract Map - 2026-07-08

Role: A3 Integration-Agent.

Scope: documentation artifact only. This pass maps the A3 release evidence v2/authority contract to current A1 runner/trace/tool-call outputs and A2 grade/scenario/judge/failure-taxonomy outputs. It does not change A1 runner core logic, A2 judge semantics, services, tests, fixtures, generated reports, or secret-bearing files. `.env.local` was not read.

## Strategy Anchor

Read first:

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`

Relevant bus requirements:

- Ashr is an Agent Release OS: release gate, evaluation platform, evidence system, audit system, collaboration backend, and usage/billing surface.
- A1 owns platform API, SDK, storage, worker, identity backend, tenant enforcement, usage source, and audit persistence.
- A2 owns evaluation, policy, calibration, regression, security verification, redaction correctness, and bundle verifier correctness.
- A3 owns product console, review workflow, report center, release service surface, GitHub workflow, hosted reports, and customer-visible evidence.
- Shared contract keys include `tenant_id`, `organization_id`, `project_id`, `environment_id`, `run_id`, `case_id`, `artifact_id`, `evidence_bundle_id`, `release_gate_id`, `audit_event_id`, `actor_id`, `api_key_id`, `request_id`, and `trace_id`.

## Evidence Read

Current A3 release evidence authority:

- `docs/a3/p3_api_backed_release_evidence_2026_07_08.md`
- `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`
- `docs/a3/p3_growth_auditor_round_release_evidence_display_2026_07_08.md`
- `services/report/a3_release_evidence.mjs`
- `services/report/report_builder.mjs`

Current A1 outputs:

- `docs/a1/schemas/run_result.schema.json`
- `docs/a1/schemas/case_result.schema.json`
- `docs/a1/schemas/agent_turn.schema.json`
- `docs/a1/schemas/observation.schema.json`
- `docs/a1/schemas/trace_event.schema.json`
- `packages/sdk/ashr_clone/types.py`
- `packages/sdk/ashr_clone/adapter.py`

Current A2 outputs:

- `docs/a2/a1_a3_handoff.md`
- `docs/a2/schemas/grade_results.schema.json`
- `docs/a2/schemas/scenario_selection.schema.json`
- `docs/a2/schemas/judge_versions.schema.json`
- `docs/a2/schemas/release_gate.schema.json`
- `docs/a2/failure_taxonomy_v0.md`

Prior A3 calibration:

- `docs/a3/p3_a1_a2_a3_contract_delta_2026_07_07.md`
- `docs/a3/p3_onboarding_audit_a1_a2_compatibility_2026_07_07.md`

## Current Output Calibration

### A1 Current Shape

`A1 RunResult` is local-run oriented and contains:

| Area | Fields available now |
|---|---|
| Run identity | `run_id`, `dataset_id`, `runner_id`, `field_map_version` |
| Run status | `status`, `total_cases`, `passed`, `failed`, `errored`, `timed_out` |
| Timing/execution | `started_at`, `ended_at`, `duration_ms`, `max_workers`, `trace_completeness` |
| Metrics | `aggregate_metrics.schema_version`, `trace_completeness`, pass/fail counts, `total_tool_calls` |
| Cases | `cases[]` with `case_id`, `scenario_id`, `title`, `status`, timing, `observations`, `grade`, `agent_output`, `expected`, `metadata` |
| Agent turn | `schema_version=ashr.clone.agent_turn.v1`, `text`, `tool_calls[]`, `status`, `latency_ms`, `metadata`, optional `error` |
| Tool call | `name`, `arguments`, `arguments_json`, `call_id`, `output`, `latency_ms`, `error` |
| Observation | `observation_id`, `run_id`, `case_id`, `turn_index`, `event_type`, `role`, `content`, `tool_calls`, timing, `status`, `metadata`, optional `vm_stream` |
| Trace event | `schema=ashr.clone.trace.v1`, `type=trace_event`, `event_type`, `run_id`, `event_id`, `seq`, `timestamp`, `phase`, `source`, `parent_id`, `tags`, `observation`, `metadata` |

A1 currently does not make tenant/auth/RBAC/artifact hash/release identity mandatory in `RunResult`.

### A2 Current Shape

`A2 GradeResultsReport` and related outputs are evaluation/policy oriented and contain:

| Area | Fields available now |
|---|---|
| Grade report | `schema_version=a2.grade_results.v1`, `report_id`, `dataset_id`, `scenario_pack`, totals, `grade_results[]` |
| Local judge run | `schema_version=a2.local_judge_run.v1`, `scenario_id`, `case_id`, `passed`, `score`, `primary_failure_class`, `judge_results[]` |
| Judge result | `schema_version=a2.grade_result.v1`, `judge_mode`, `judge_version`, pass/score, `rubric_scores`, `failure_analysis`, `evidence`, `metadata` |
| Failure analysis | `primary_failure_class`, `failure_classes[]`, `severity`, `blame_stage`, `summary`, `details[]`, `remediation[]`, `safety_blocking` |
| Scenario selection | `tenant.organization_id`, `workspace_id`, `tenant_id`, `project`, `environment`, `policy_profile`, selected scenarios, coverage/minimums, A3 consumption summary |
| Judge versions | `registry_id`, `scenario_pack_id`, `grade_report_id`, active release, judge version/pinning/migration/audit, `registry_hash` |
| Release gate | `decision`, `risk_score`, `hard_gate_ids`, gate counts, `scenario_selection_gate`, `a1_output_policy_gate`, blockers, warnings, required evidence, PR annotations, review workflow, machine contract, evidence refs |

Canonical A2 failure classes are stable: `none`, `wrong_intent`, `missing_required_tool`, `unnecessary_tool_call`, `forbidden_tool_call`, `wrong_tool`, `wrong_arguments`, `wrong_tool_order`, `missing_clarification`, `hallucinated_tool_result`, `ignored_tool_result`, `unsafe_or_policy_violation`, and `poor_failure_recovery`.

### A3 Current Release Evidence Shape

A3 has v1 API-backed release evidence, not full v2 authority:

| Area | Current signal |
|---|---|
| Summary | `a3.release_evidence_summary.v1` generated by report builder |
| API | `GET /api/a3/releases/:releaseId/evidence-summary` returns `a3.release_evidence_api_response.v1` |
| Health | `a3.release_evidence_health.v1` from `buildReleaseEvidenceHealth(...)` |
| Diff | `a3.release_evidence_diff.v1` for selected summary fields |
| Storage | SQL/SQLite contract includes `release_evidence_summaries` |
| Artifact | Report Center manifest and Artifact Registry include `release_evidence_summary` |
| Hosted report | `release_evidence_snapshot` preserves summary hash/snapshot metadata |

The authority handoff defines the next canonical object as `a3.release_evidence_summary.v2` with stable `summary_id`, `release_id`, `tenant_scope`, `source_snapshot_id`, and `content_hash`.

## Field Mapping Table

| A3 v2 authority field | Current A1 source | Current A2 source | Current A3 source | Gap / integration decision |
|---|---|---|---|---|
| `schema_version` | None | None | v1 summary/health constants | Add explicit `a3.release_evidence_summary.v2`; keep v1 default for compatibility. |
| `summary_id` | None | None | Health derives `res_<hash>` | A3 can derive, but DB/API must persist it as stable id instead of recomputing from mutable payload. |
| `tenant_scope.organization_id` | Not required in `RunResult`; SaaS/CLI paths may carry tenant separately | Scenario selection has `tenant.organization_id` | Health defaults to `org-local` | Need precedence rule: API-auth tenant > A1 ingestion tenant > A2 scenario-selection tenant > local placeholder. |
| `tenant_scope.project_id` | Not required in `RunResult`; SaaS paths may carry project separately | Scenario selection has `project` and `environment` | Health defaults to `project-local` | Need A1 hosted run/project contract before multi-tenant claims. |
| `tenant_scope.tenant_id/workspace_id` | Not in local schemas | Scenario selection has `tenant_id`, `workspace_id` | Not first-class in v1 health | v2 must preserve all shared tenant keys even if A3 display only shows org/project. |
| `release_identity.run_id` | `RunResult.run_id`; observations/trace share `run_id` | Release gate `release_candidate` may include release context | API release id/path | Direct map; require mismatch guard when release id and run id diverge. |
| `release_identity.dataset_id` | `RunResult.dataset_id` | `GradeResultsReport.dataset_id` | Report builder summary | Direct map; add hash/ref for immutable source snapshot. |
| `release_identity.runner_id` | `RunResult.runner_id` | None | Report builder summary | Direct map; useful for source attribution, not release decision alone. |
| `release_identity.case_count` | `total_cases`, `cases[]` | `total_cases` | Dashboard summary | Direct map; v2 should record A1/A2 count mismatch if joins are incomplete. |
| `release_identity.environment_id/environment` | Not required in RunResult | Scenario selection `environment`; release gate scenario gate `environment` | Sometimes report/gate context | Need normalized `environment_id` or string alias. |
| `release_identity.repo/pr/branch/head_sha` | None in core A1 | None in core A2 release gate schema | GitHub publish/PR gate artifacts | A3-owned integration data; must be nullable and cannot be inferred from run id. |
| `source_snapshot_id` | None | None | Hosted report snapshot id available | Need immutable source snapshot row/hash for A1 run + A2 grade + A2 gate inputs. Hosted report snapshot is downstream, not source. |
| `content_hash` | None in RunResult schema | `judge_versions.registry_hash`; gate evidence refs may imply artifacts | Summary hash computed in health | Need hash contract for A1 run, A1 trace batch, A2 grade report, A2 release gate, and A3 summary. |
| `health.overall_status` | `status`, pass/fail/error counts, trace completeness | release gate `decision`, `risk_score`, blockers, warnings | v1 `overall_status` values: `missing/partial/planned/verified` | Need v2 status precedence across A1 run failures, A2 blockers, redaction failures, readback stale, verifier failures, review state. |
| `health.blocking_reason` | `errored`, `timed_out`, `trace_completeness` gaps | `blockers[]`, `hard_gate_ids`, `primary_failure_class`, `safety_blocking` | `next_action.reason` | Need stable reason enum and mapping to accountable lane. |
| `health.accountable_lane` | A1 for ingestion/trace/storage gaps | A2 for judge/policy/redaction/verifier correctness | A3 for product workflow/readback/review/share | Add lane mapping rules; do not overload free-text blocker summaries. |
| `release_gate.decision` | A1 local `grade` is not authoritative release gate | `release_gate.decision`, `risk_score`, `hard_gate_ids` | A3 gate CLI/report workflow | A2 gate decision should feed v2; A3 can package but must not reinterpret A2 judge semantics. |
| `release_gate.policy_version` | None | `policy_profile.policy_id`, `judge_policy_id`, release gate `current_commercial_gate` | A3 gate thresholds maybe local | Need explicit policy/threshold version fields in release gate evidence. |
| `release_gate.source_report_hash` | None | Release gate `evidence_refs` only | Bundle/manifest hashes available downstream | Need hash of exact A2 gate report used by A3. |
| `a1_run_result` | Full `RunResult` | A2 can accept native A1 input but does not own it | A3 report builder normalizes | v2 should reference run artifact id/hash, not embed full raw run. |
| `a1_trace` | `trace_events[]` schema exists; `RunResult.cases[].trace_events` not required | Judge evidence has compact trace facts | A3 consumes `trace_events` and `observations` | Need trace batch artifact ids, completeness threshold, and redaction status. |
| `a1_tool_calls` | Agent/tool calls in `agent_output`, observations, trace observation data | A2 evidence may include `tool_call_ids`, tool sequence/count | A3 tool-call diffs normalize aliases | Need shared tool-call identity contract: `tool_call_id`, `name`, `arguments_hash`, `output_hash`, redaction class, status. |
| `a2_grade_results` | A1 local `grade` is 0-1 and noncanonical | `a2.grade_results.v1` 0-100 scores | A3 joins by `case_id` | Need score provenance and join completeness in v2. |
| `a2_failure_taxonomy` | A1 labels/reasons only | Canonical failure taxonomy | A3 canonicalizes some local signals | v2 should record canonical class counts, severity counts, and noncanonical-to-canonical mapping version. |
| `a2_judge_versions` | None | `a2.judge_versions.v1`, `registry_hash`, pinning | Not first-class in release evidence v1 | v2 must include judge registry id/hash and pinning status before production release claims. |
| `a2_scenario_selection` | `scenario_id`, dataset metadata | `a2.scenario_selection.v1` coverage/minimums/tenant | Report builder can summarize coverage/readiness | v2 should include selection id, scenario pack id, coverage readiness, minimums readiness, and gaps. |
| `github_check_readback` | None | None | v1 has publish receipt/status; authority doc requires readback | A3 integration gap: generated/posted/readback/stale/missing/deleted must be distinct. |
| `pr_comment_readback` | None | None | v1 has publish receipt/status | Same as GitHub Check; body/marker hash required. |
| `required_check_proof` | None | Release gate can emit PR annotations but not branch protection proof | v1 has required-check plan | Branch-protection readback is missing; plan-only must not count as enforced. |
| `review_identity` | A1 may later provide actor/service account | A2 release gate has `review_workflow` object but no provider binding guarantee | A3 review workflow/waiver/approval records | Need actor provider alias, role, expiry, signature status, separation-of-duties, and artifact hash binding. |
| `redaction` | A1 metadata says local/private boundaries; no full artifact-class redaction matrix | A2 evidence readiness/redaction policy and safety failure class | A3 redacts summary keys and generated artifacts | Need fail-closed matrix across JSON, Markdown, CSV, HTML, hosted report, Check, PR comment, manifest, bundle, archive, logs, screenshots. |
| `hosted_report` | None | None | Hosted snapshot id/hash/share state | A3-owned; must join to summary id and record denied/expired/revoked/auth-required states without body evidence leakage. |
| `report_center_manifest` | None | None | Manifest includes release evidence summary artifact | Need v2 manifest fields: summary id, source snapshot id, diff id, readback ids, verifier ids, usage ids, retention/legal-hold. |
| `artifact_registry` | A1 run/trace should become artifacts | A2 grade/gate/judge registry should become artifacts | A3 registry has release evidence summary | Need artifact ids/hashes for A1 run, A1 trace batch, A1 tool-call batch, A2 grades, A2 scenario selection, A2 gate, A2 judge registry. |
| `audit_bundle` | A1 evidence should feed input hashes | A2 gate/judge results should feed input hashes | A3 bundle verification status exists | Need chain from source artifacts to bundle root hash and verifier receipt. |
| `signed_archive` | None | None | A3 archive verification display exists/planned | Need real signature/key fingerprint/signer binding; do not infer from A1/A2. |
| `usage_ledger` | A1 owns usage source; local RunResult has no usage event ids | A2 cost policy/model usage optional feeds | A3 usage/report center tests exist | Need append-only usage event ids linked to summary id, manifest id, tenant scope, run/grade/gate artifact ids. |
| `audit_events` | A1 should persist audit mutations later | A2 can provide policy/evidence refs | A3 has audit archive/report lifecycle | Need event ids for summary created, snapshot created, readback changed, approval/waiver, bundle verified, archive verified, revoke/deny/view. |
| `webhooks` | A1 owns delivery backend later | A2 owns policy event semantics for judge/security | A3 authority doc defines event set | Need versioned event schema and no raw body payloads. |
| `api_docs` | A1 OpenAPI-first target | A2 FastAPI/OpenAPI target later | A3 local API route exists | Need documented v1/v2 negotiation, error shapes, idempotency, redaction examples, and compatibility rules. |
| `compliance` | A1 retention/storage/audit backend later | A2 security/privacy verification | A3 report center/archive display | Need retention/legal hold/purge eligibility/object-lock/key status fields. |

## Highest-Priority Contract Gaps

1. No canonical v2 schema file or builder exists yet.
   - Current code has `a3.release_evidence_summary.v1`, `a3.release_evidence_health.v1`, and `a3.release_evidence_diff.v1`.
   - Authority requires `a3.release_evidence_summary.v2` with health, identity, readback, lifecycle, ledger, storage, webhook, and compliance fields.

2. A1 local `RunResult` lacks tenant/project/release/artifact identity.
   - A1 has excellent local run/trace/tool-call evidence, but v2 cannot make SaaS authority claims from only `run_id`, `dataset_id`, and `runner_id`.
   - A3 should not modify A1 runner core; it should define an ingestion-side wrapper contract that attaches tenant/project/request/artifact/hash metadata around A1 output.

3. A1 trace and tool-call evidence are not artifact-addressable.
   - Tool calls exist in `AgentTurn`, observations, and trace events, but v2 needs stable ids, argument/output hashes, redaction state, and artifact registry ids.
   - The integration gap is a shared projection contract, not a runner semantics change.

4. A2 grade and release gate are strong semantically but not yet hashed into the evidence chain.
   - A2 provides canonical failure classes, judge versions, scenario selection, and release gate blockers.
   - v2 needs exact `grade_report_hash`, `release_gate_report_hash`, `judge_registry_hash`, and `scenario_selection_hash` references before immutable bundle/authority claims.

5. Score scale/provenance remains implicit.
   - A1 local `grade.score` is 0-1.
   - A2 score is 0-100.
   - A3 normalizes today, but v2 evidence should record `score_source`, `score_scale`, and join completeness to avoid audit ambiguity.

6. Required-check enforcement is still plan-only.
   - A3 v1 can show required-check plan fields.
   - v2 must distinguish `planned`, `posted`, `readback_confirmed`, `enforced`, `stale`, `missing`, and `permission_denied`.

7. GitHub Check and PR comment readback are not connected to A1/A2 authority.
   - A1/A2 provide the evaluated behavior and gate decision.
   - A3 provides publish/readback workflow.
   - v2 must bind readback receipts to `run_id`, `release_gate_id`, `head_sha`, `summary_id`, and artifact hashes.

8. Review identity is not enterprise-grade.
   - A3 has durable waiver/approval workflow evidence, and A2 release gate has `review_workflow`.
   - Missing: provider subject alias, role, expiry, signature verification, separation-of-duties result, and binding to bundle/archive hashes.

9. Redaction is not yet a single fail-closed matrix.
   - A3 sanitizes summaries and artifacts.
   - A2 owns redaction/security verification.
   - v2 needs one explicit matrix that blocks external publish/share/archive promotion when any external artifact class fails.

10. Usage/audit rows are not yet authoritative source events.
    - A1 owns usage/audit backend in the strategy bus.
    - A3 can show usage/report center state, but v2 needs append-only usage and audit event ids linked to summary id and tenant scope.

11. `source_snapshot_id` is not distinct from hosted report snapshot id.
    - Hosted report snapshots prove what was shared.
    - v2 also needs source snapshots proving which A1/A2 inputs were used to compute the summary.

12. Optional A2 feeds need stale/missing semantics.
    - Scenario selection, judge versions, evidence readiness, case book, regression replay, semantic harness, and calibration reports are intentionally optional.
    - v2 should record each as `present`, `missing`, `stale`, or `not_required`, not silently collapse absent feeds to `{}`.

## Proposed API Contract

Keep existing v1 stable:

```http
GET /api/a3/releases/:releaseId/evidence-summary
```

Default response remains `a3.release_evidence_api_response.v1` unless v2 is explicitly requested.

Add version negotiation:

```http
GET /api/a3/releases/:releaseId/evidence-summary?version=2
Accept: application/vnd.ashr.release-evidence-summary.v2+json
```

Required v2 response envelope:

```text
schema_version = a3.release_evidence_summary.v2
summary_id
tenant_scope
release_identity
source_snapshots
source_artifacts
health
a1_run
a1_trace
a1_tool_calls
a2_grade
a2_scenario_selection
a2_judge_versions
a2_release_gate
github_check_readback
pr_comment_readback
required_check_proof
review_identity
redaction
hosted_report
report_center_manifest
artifact_registry
audit_bundle
signed_archive
usage_ledger
audit_events
webhooks
api_docs
compliance
```

Error behavior:

- Unknown release id returns sanitized not-found.
- Cross-tenant release id returns not-found or denied without body evidence.
- Missing v2 source artifacts returns controlled `blocked_source_snapshot` or `collecting`, not partial success disguised as authority.
- Redaction failure sets external publish/share fields to fail closed.
- Missing readback cannot be represented as readback-confirmed.
- Required-check plan cannot be represented as branch-protection enforcement.

## Proposed DB Contract

Current A3 has `release_evidence_summaries`; v2 needs normalized authority tables or equivalent JSON-plus-index contract:

| Table / record | Required keys | Purpose |
|---|---|---|
| `release_evidence_summaries_v2` | `summary_id`, `organization_id`, `tenant_id`, `project_id`, `release_id`, `schema_version`, `content_hash`, `health_status`, `created_at` | Canonical v2 summary row. |
| `release_evidence_source_snapshots` | `source_snapshot_id`, `summary_id`, `source_type`, `artifact_id`, `artifact_hash`, `schema_version`, `captured_at` | Immutable A1/A2 input snapshot ledger. |
| `release_evidence_readbacks` | `readback_id`, `summary_id`, `provider`, `resource_kind`, `head_sha`, `status`, `payload_hash`, `error_class`, `checked_at` | GitHub Check, PR comment, required-check readback. |
| `release_evidence_review_bindings` | `review_binding_id`, `summary_id`, `actor_id`, `provider_subject_alias`, `role`, `expires_at`, `artifact_hash`, `signature_status`, `separation_of_duties` | Enterprise approval/waiver evidence. |
| `release_evidence_redaction_matrix` | `matrix_id`, `summary_id`, `artifact_class`, `status`, `finding_count`, `scanner_version`, `checked_at` | Fail-closed redaction authority. |
| `release_evidence_usage_links` | `summary_id`, `usage_event_id`, `meter`, `quantity`, `organization_id`, `project_id` | Billing/usage join without raw payloads. |
| `release_evidence_audit_links` | `summary_id`, `audit_event_id`, `event_type`, `actor_id`, `resource_type`, `resource_id` | Chain of custody for mutations and lifecycle. |
| `release_evidence_compliance_state` | `summary_id`, `retention_policy`, `legal_hold`, `purge_eligibility`, `archive_id`, `verifier_receipt_id` | Enterprise retention/export state. |

Indexes must include tenant/project/release predicates and hash/id lookup:

- `(organization_id, project_id, release_id)`
- `(tenant_id, summary_id)`
- `(summary_id, content_hash)`
- `(project_id, health_status)`
- `(summary_id, artifact_id)`
- `(summary_id, usage_event_id)`
- `(summary_id, audit_event_id)`

## Proposed Event Contract

Each event must include `event_id`, `event_type`, `schema_version`, `organization_id`, `tenant_id`, `project_id`, `actor_id` or `service_account_id`, `request_id`, `trace_id`, `resource_type`, `resource_id`, `created_at`, `payload_hash`, `payload_ref`, and `redaction_status`.

Minimum v2 event set:

| Event | Trigger | Payload boundary |
|---|---|---|
| `release_evidence.summary_created` | v2 summary first persisted | ids, hashes, health, no raw run/grade body |
| `release_evidence.health_changed` | health status/next action changes | old/new status and reason enum |
| `release_evidence.source_snapshot_created` | A1/A2 source inputs captured | source artifact ids and hashes |
| `release_evidence.github_check_readback_changed` | Check readback changes | check alias, head sha match, status, sanitized error class |
| `release_evidence.pr_comment_readback_changed` | PR comment readback changes | marker/body hash match, status, sanitized error class |
| `release_evidence.required_check_proof_changed` | branch-protection proof changes | enforced/planned/stale/missing state |
| `release_evidence.redaction_blocked` | external artifact class fails scan | artifact class, finding count, scanner version |
| `release_evidence.hosted_report_snapshot_created` | hosted report snapshot bound | snapshot id/hash and expiry/revoke state |
| `release_evidence.hosted_report_denied_viewed` | denied hosted report view | denied count/audit id, no body evidence |
| `release_evidence.review_bound` | approval/waiver bound to summary | actor alias, role, expiry, artifact hash |
| `release_evidence.bundle_verified` | audit bundle verifier result | bundle id, root hash, verifier receipt id, status |
| `release_evidence.archive_verified` | archive verifier result | archive id/hash, signature/key status, receipt id |
| `release_evidence.retention_changed` | legal hold/retention/purge changes | policy ids and state only |

## Proposed Artifact Contract

`a3.release_evidence_summary.v2` should reference, not embed, these artifacts:

| Artifact type | Producer lane | Required fields |
|---|---|---|
| `a1_run_result` | A1 | `artifact_id`, `run_id`, `schema_version`, `content_hash`, tenant/project refs |
| `a1_trace_event_batch` | A1 | `artifact_id`, `run_id`, `case_id` optional, `trace_id`, `event_count`, `content_hash`, redaction status |
| `a1_tool_call_batch` | A1/A3 projection | `artifact_id`, `run_id`, `case_id`, `tool_call_count`, argument/output hashes, redaction status |
| `a2_grade_results` | A2 | `artifact_id`, `report_id`, `dataset_id`, `scenario_pack`, `content_hash`, score scale |
| `a2_scenario_selection` | A2 | `artifact_id`, `selection_id`, `source_pack_id`, coverage/minimum readiness, content hash |
| `a2_judge_version_registry` | A2 | `artifact_id`, `registry_id`, `registry_hash`, active release/pinning |
| `a2_release_gate` | A2 | `artifact_id`, `release_gate_id`, `decision`, `risk_score`, `content_hash` |
| `a3_release_evidence_summary` | A3 | `summary_id`, `content_hash`, source snapshot ids |
| `a3_release_evidence_diff` | A3 | `diff_id`, before/after summary ids, safe changed fields |
| `github_check_readback` | A3 integration | readback id, payload hash, head sha match, status |
| `pr_comment_readback` | A3 integration | readback id, marker/body hash, head sha match, status |
| `required_check_proof` | A3 integration/A1 backend later | proof id, branch protection readback status, enforced flag |
| `hosted_report_snapshot` | A3 | snapshot id, snapshot hash, expiry/revoke/auth state |
| `audit_bundle_verifier_receipt` | A1/A2/A3 | bundle id, root hash, verifier version, status |
| `signed_archive_verifier_receipt` | A3/A1 storage later | archive id/hash, signature/key status, verifier receipt |
| `redaction_report` | A2/A3 | artifact class, scanner version, finding count, fail-closed status |
| `usage_rollup` | A1/A3 | usage event ids, meters, summary/report/manifest joins |
| `compliance_packet` | A3 | retention/legal-hold/purge/export state |

## Tenant / Auth / RBAC Impact

| Area | Current state | v2 requirement |
|---|---|---|
| Tenant scope | A3 health defaults to local org/project; A2 scenario selection has tenant fields; A1 local RunResult lacks mandatory tenant | Every v2 read/write joins by org/tenant/project and rejects cross-tenant ids without body evidence. |
| Auth | Current A3 release evidence API is local/dev evidence | v2 must require authenticated actor or service account before hosted SaaS claims. |
| RBAC | Review and report surfaces exist, but authority does not bind permissions to fields | Actions need permission names: view summary, create snapshot, publish readback, approve, waive, revoke, verify, export, purge. |
| Actor identity | A1/A2 local artifacts do not provide enterprise actor binding | v2 review/audit records require `actor_id`, provider subject alias, role, expiry, signature status, and separation-of-duties result. |
| API keys | A1 strategy owns scoped API keys; local run metadata has no api key id | Source snapshots from API ingestion must carry `api_key_id` or service account id, redacted in display. |

## Usage / Billing Impact

V2 should not enable billing mutations by itself. It should create read-only, ledger-backed links:

| Meter | Source lane | Link requirement |
|---|---|---|
| `run_count`, `case_count`, `trace_event_count`, `observation_count` | A1 | Link to run artifact and summary id. |
| `artifact_bytes_uploaded`, `artifact_bytes_stored_days` | A1/A3 | Link to artifact registry and retention state. |
| `judge_invocations`, `semantic_judge_tokens`, `model_cost_usd` | A2 | Link to grade/judge registry/calibration artifacts. |
| `report_exports`, `hosted_views`, `denied_views`, `revocations` | A3 | Link to hosted snapshot and report center manifest. |
| `webhook_deliveries`, `github_check_publishes`, `pr_comment_publishes` | A1/A3 integration | Link to readback ids and publish receipts. |
| `verifier_runs`, `archive_bytes`, `retained_days` | A1/A3 | Link to bundle/archive verifier receipts and compliance state. |

Billing UI should show counts only when usage event ids exist; otherwise v2 should report `usage_ledger.status=missing` or `plan_only`.

## Audit / Redaction Impact

Audit chain requirements:

- Every v2 summary creation, source snapshot, readback capture, approval/waiver, hosted share, revoke, denied view, bundle verification, archive verification, retention change, and purge attempt creates or references an audit event.
- Audit events must reference ids/hashes, not raw customer payloads.
- `request_id` and `trace_id` must be carried from API/worker paths into DB rows and events.

Redaction requirements:

- A1 run/trace/tool-call artifacts must expose redacted views and preserve raw/private payloads only behind private artifact refs when allowed.
- A2 grade/judge evidence must avoid raw private evidence in public report paths.
- A3 summary, hosted report, Check payload, PR comment, manifest, bundle, archive, logs, screenshots, JSON, Markdown, CSV, and HTML exports must share one fail-closed matrix.
- If any external artifact class is `blocked`, v2 sets `external_publish_allowed=false` and health becomes `blocked_redaction`.

## Test Recommendations

Do not change services/tests in this documentation pass. The next implementation round should add focused tests after the v2 schema contract is accepted:

| Test | Purpose |
|---|---|
| `tests/a3/release_evidence_summary_v2_contract.test.mjs` | Required fields, nullable-safe defaults, v1 compatibility, no raw secret fields. |
| `tests/a3/release_evidence_a1_source_snapshot_contract.test.mjs` | A1 RunResult/Trace/ToolCall source artifacts become ids/hashes without changing runner semantics. |
| `tests/a3/release_evidence_a2_source_snapshot_contract.test.mjs` | A2 GradeResults/ScenarioSelection/JudgeVersions/ReleaseGate become source artifacts with hashes. |
| `tests/a3/release_evidence_score_provenance.test.mjs` | A1 0-1 and A2 0-100 scores preserve `score_source` and `score_scale`. |
| `tests/a3/release_evidence_tool_call_identity.test.mjs` | Tool-call aliases normalize to stable ids/name/argument hash/output hash. |
| `tests/a3/tenant_scope_release_evidence.test.mjs` | Cross-tenant API/store/manifest/usage/audit/hosted report reads fail closed. |
| `tests/a3/release_evidence_redaction_fail_closed.test.mjs` | Every external artifact class blocks publish/share/archive on findings. |
| `tests/a3/github_readback_contract.test.mjs` | Generated, posted, readback-confirmed, stale, missing, deleted, permission-denied states. |
| `tests/a3/pr_comment_readback_contract.test.mjs` | Marker/body/head SHA matching and sanitized error handling. |
| `tests/a3/required_check_proof.test.mjs` | Plan-only cannot set `enforced=true`; branch protection readback required. |
| `tests/a3/review_identity_binding.test.mjs` | Provider alias, role, expiry, signature status, separation-of-duties, artifact hash binding. |
| `tests/a3/usage_ledger_release_evidence.test.mjs` | Usage rows join to summary id, manifest id, tenant scope, source artifacts. |
| `tests/a3/release_evidence_webhook_contract.test.mjs` | Event schema, dedupe key, tenant scope, payload hash, no raw body. |
| `tests/a3/release_evidence_verifier_chain.test.mjs` | A1/A2 source hashes flow into bundle/archive verifier receipts. |
| `tests/a3/release_evidence_optional_feed_state.test.mjs` | Optional A2 feeds are present/missing/stale/not-required, never silently invented. |

Suggested compatibility checks after implementation:

```powershell
node --test tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs
node --test tests/a3/report_builder.test.mjs tests/a3/shareable_report.test.mjs tests/a3/report_center_manifest_contract.test.mjs
node --test tests/a3/artifact_registry.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_review_workflow.test.mjs
git diff --check
```

## API / DB / Event / Artifact Contract Summary

| Contract class | Must add or strengthen | A1/A2 integration rule |
|---|---|---|
| API | v2 summary negotiation, compact health, safe diff, stable errors, idempotency/readback capture | A3 reads A1/A2 artifacts by id/hash; it does not mutate A1 runner or A2 judge semantics. |
| DB | Summary v2, source snapshots, readbacks, review bindings, redaction matrix, usage/audit links, compliance state | A1/A2 source rows are immutable references. Recompute creates new summary/source snapshot ids. |
| Event | Versioned release evidence lifecycle events with tenant/request/trace ids and payload hashes | Events carry refs/hashes only; no raw run/grade/tool payload. |
| Artifact | Registry entries for A1 run/trace/tool batch and A2 grade/scenario/judge/gate, plus A3 summary/diff/readbacks/verifier receipts | Each artifact has schema version, content hash, redaction status, producer lane, and tenant scope. |

## Failure Points For Next Owner

- Do not claim multi-tenant authority while A1 local run artifacts lack mandatory tenant/project/request metadata.
- Do not claim required PR gate enforcement from a required-check plan.
- Do not claim GitHub evidence is live/readback-confirmed from generated local receipts.
- Do not let A3 recompute `summary_id` from mutable payload as the durable database identity.
- Do not collapse missing A2 optional feeds into passing states.
- Do not mix A1 0-1 scores and A2 0-100 scores without provenance.
- Do not expose A1 trace/tool-call raw arguments or outputs in public v2 summary fields.
- Do not make review approval unblock production without identity/role/expiry/separation-of-duties binding.
- Do not allow report/share/PR/Check/archive output when redaction matrix has any blocking external class.

## Next Steps

1. Land a schema-only `a3.release_evidence_summary.v2` contract with placeholder-safe examples.
2. Add A1/A2 source snapshot contract fixtures that wrap existing outputs with tenant/project/artifact/hash metadata without changing A1 runner or A2 judge semantics.
3. Add version negotiation on the existing evidence-summary route after the schema is stable.
4. Add source artifact hash propagation from A1 run/trace/tool-call and A2 grade/scenario/judge/gate artifacts into the v2 summary.
5. Add tenant negative tests before any broader v2 UI display.
6. Add readback and required-check proof only after the v2 summary can distinguish plan/generated/posted/readback/enforced/stale/missing states.
7. Add fail-closed redaction matrix and usage/audit links before external audit-ready or billing-ready claims.

## Final Integration Verdict

The A1/A2/A3 path is compatible but not yet authority-grade.

A1 provides the behavioral evidence substrate: run results, case results, observations, traces, and tool calls. A2 provides the evaluation substrate: canonical failure classes, judge versions, scenario selection, and release gate semantics. A3 now has the first API-backed release evidence object and hosted/report/artifact surfaces.

The main integration gap is not UI. It is source authority: v2 must bind A1 and A2 source artifacts to stable tenant-scoped ids, hashes, snapshots, usage/audit events, redaction status, and readback/verifier receipts. Once that contract exists, A3 can safely become the customer-visible release evidence authority without modifying A1 runner core logic or A2 judge semantics.
