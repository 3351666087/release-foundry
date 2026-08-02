# P3 Readback A1/A2 Contract Alignment - 2026-07-08

## Purpose

This document is an A3 Contract-Agent readback of the A1/A2/A3 boundary after reading:

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- `docs/a1/api_calibration/README.md`
- `docs/a2/a1_a3_handoff.md`
- `docs/a3/p3_release_evidence_readback_capture_api_2026_07_08.md`

It is contract-only. It does not change A1 runner logic, A2 judge logic, A3 report code, fixtures, or tests.

## Non-Goals And Safety Boundary

- No `.env.local` read is required or allowed for this alignment.
- No live ReleaseFoundry API, GitHub API, model API, or hosted dashboard call is required or allowed.
- No `services/report` or `tests/a3` change is required or allowed in this round.
- Private A1 evidence paths named in the A1 calibration README remain private refs. A3 adapters may store their paths or redacted summaries only; they must not copy raw private evidence into tracked docs, artifacts, or UI state.
- A3 readback capture means "A3 accepted a sanitized external readback receipt." It is not, by itself, proof that A1 verifier passed or that GitHub branch protection is enforced.

## Shared Join Keys

All future adapters should preserve these cross-lane identifiers when present:

| Field | Contract Use |
| --- | --- |
| `organization_id` | Tenant/org isolation and audit scoping. |
| `tenant_id` | Compatibility with observed official API shapes and legacy local fixtures. |
| `project_id` | Project-scoped run, artifact, policy, and report joins. |
| `environment_id` | Future staging/production release-gate separation. |
| `run_id` | A1 run result, trace, observations, and A2 grading join. |
| `case_id` | A1 case result and A2 scenario/judge result join. |
| `scenario_id` | A2 deterministic grading and scenario coverage join. |
| `artifact_id` | Artifact registry, generated report, and evidence bundle join. |
| `evidence_bundle_id` / `bundle_id` | Bundle manifest, seal, verification, and export join. |
| `release_gate_id` | A3 release decision, waiver, approval, and readback join. |
| `audit_event_id` | Audit trail for capture, approval, waiver, and verifier events. |
| `actor_id` / `actor_hash` / `service_account_id` | Human or automation accountability without leaking private identity data. |
| `api_key_id` | Backend key lineage when exposed through safe metadata only. |
| `request_id` | API request correlation and idempotency debugging. |
| `trace_id` | Cross-service trace and artifact provenance correlation. |

## A1 Verifier, Run, Trace, And Artifact Fields A3 Can Consume

### A1 Verifier Packet

A3 should import A1 verifier output as a separate packet, not merge it into GitHub readback status.

| Field | A3 Mapping |
| --- | --- |
| `schema_version` | Versioned adapter gate, for example `a1.bundle_verifier.v1`. |
| `verifier_id` / `verification_id` | Stable verifier receipt id. |
| `verifier_version` | Display and bundle drift detection. |
| `evidence_bundle_id` / `bundle_id` | Join to A3 release evidence and export UI. |
| `bundle_manifest_ref` | Artifact reference, not raw manifest body. |
| `root_hash` | Bundle integrity summary. |
| `signature_status` | Signed/unsigned/invalid state. |
| `verification_status` | A1 authority status: `passed`, `failed`, `error`, or `not_run`. |
| `verification_command` | Reproducible local/CI verifier command summary. |
| `input_artifact_hashes` | Source artifact integrity join. |
| `generated_artifact_hashes` | Generated report/comment/check integrity join. |
| `judge_versions` | A2 dependency snapshot for release evidence. |
| `policy_versions` | A2 policy dependency snapshot for release evidence. |
| `release_decision` | Decision that was sealed, not a UI-only label. |
| `waiver_refs` | References to waiver artifacts or approval records. |
| `approval_refs` | Reviewer approval references. |
| `chain_of_custody` | Compact provenance summary or artifact ref. |
| `retention_policy` | Export and deletion policy display. |
| `verified_at` | Verifier execution timestamp. |
| `redaction_status` | Required before A3 report/export display. |
| `error_summary` | Redacted failure summary only. |

### A1 Run Result

A3 can display A1 run status and rollups, and can join A2 grading by `run_id`, `case_id`, and `scenario_id`.

| Field | A3 Mapping |
| --- | --- |
| `schema_version` | Run result schema gate. |
| `run_id` | Primary run join. |
| `dataset_id` | Dataset/report grouping. |
| `runner_id` | Runner/source display and usage attribution. |
| `status` | Run state display; do not infer A2 pass/fail from it. |
| `started_at` / `ended_at` | Timeline display. |
| `duration_ms` | Performance and usage summary. |
| `total_cases` | Run rollup. |
| `passed` / `failed` / `errored` / `timed_out` | A1 execution rollup. |
| `aggregate_metrics` | Optional rollup display. |
| `max_workers` | Execution configuration evidence. |
| `trace_completeness` | Trace health signal. |
| `field_map_version` | Adapter compatibility check. |
| `metadata` | Summary-only extension area. |
| `cases[]` | Case drilldown; raw private payloads stay out of A3 tracked state. |

Hosted API shapes observed by A1 also expose `created_at`, `dataset`, `dataset_details`, `id`, `result`, `runner`, `runner_details`, and `tenant`; adapters should normalize these into the local run fields above.

### A1 Trace And Tool Call Fields

A2 accepts normalized tool calls and final text. A3 can show trace/tool evidence after redaction.

| Field | A3 Mapping |
| --- | --- |
| `trace_id` | Cross-service trace join. |
| `request_id` | API request join. |
| `trace_events[]` | Ordered trace display or artifact ref. |
| `event_id` | Stable trace event id. |
| `event_type` | Event classifier, such as `trace.ingested`. |
| `schema_version` | Trace event schema gate. |
| `created_at` | Trace timeline display. |
| `tool_calls[]` | Tool-call evidence list. |
| `tool_calls[].id` / `call_id` | A2 `evidence.tool_call_ids` join. |
| `tool_calls[].name` / `tool` / `function.name` | Normalize to A2 exact tool contract names. |
| `tool_calls[].arguments` / `args` / `input` / `arguments_json` | Redacted argument summary or hash; raw sensitive values must not be displayed. |
| `text` / `final_response` | A2 final response source; A3 displays excerpt only. |
| `latency_ms` | Performance signal. |
| `redaction_status` | Required before report/export display. |

### A1 Artifact Fields

A3 should treat A1 artifacts as registry records or refs, not as raw payload copies.

| Field | A3 Mapping |
| --- | --- |
| `artifact_id` | Primary artifact join. |
| `artifact_type` | Must align with strategy artifact types such as `run_result`, `judge_result`, `github_check`, `pr_comment`, `bundle_verification`, or `release_gate_report`. |
| `payload_hash` / `checksum` | Integrity display and drift check. |
| `artifact_ref` / `object_ref` / `uri` | Storage pointer; signed/private URLs must be redacted or replaced with refs. |
| `content_type` | Report/render/export behavior. |
| `created_at` | Artifact timeline. |
| `created_by` / `actor_id` / `service_account_id` | Audit attribution. |
| `organization_id` / `tenant_id` / `project_id` | Tenant/project scope. |
| `run_id` / `case_id` / `release_gate_id` | Workflow joins. |
| `source_artifact_ids` | Reseal dependency graph. |
| `generated_artifact_ids` | Generated-output dependency graph. |
| `redaction_status` | Required for public/tracked surfaces. |
| `retention_policy` | Export and deletion UI. |
| `registry_status` | Registered/missing/drifted state. |

## A2 Judge, Policy, And Failure Fields A3 Can Consume

### Deterministic Grade Result

A2's deterministic local grading remains the stable required feed. A3 must not require live ReleaseFoundry grading or LLM judge data to render the existing report paths.

| Field | A3 Mapping |
| --- | --- |
| `schema_version` | Required for aggregate wrappers, especially `a2.grade_results.v1`. |
| `grade_results[]` | Per-case grade list. |
| `total_cases` / `passed` / `failed` | Aggregate outcome display. |
| `scenario_pack` | Scenario source display. |
| `dataset_id` | A1/A3 run/report join. |
| `report_id` | Report artifact join. |
| `case_id` | Case drilldown join. |
| `scenario_id` | Scenario/judge/rubric join. |
| `passed` | A2 behavioral pass/fail, separate from A1 execution status. |
| `score` | Normalize scale carefully; A2 aggregate uses 0-100 while some A1 nested case grades may use 0-1. |
| `primary_failure_class` | Canonical A2 failure clustering field. |
| `judge_results[]` | Per-judge score/detail display. |
| `judge_results[].score` / `max_score` | Per-judge scoring display. |
| `failure_analysis.summary` | Redacted reviewer-facing explanation. |
| `evidence.tool_call_ids` | Join to A1 trace/tool-call ids. |
| `evidence.final_response_excerpt` | Display-safe response excerpt. |

### Judge And Policy Fields

The documented local judge pipeline includes `ToolPolicyJudge`, `OutcomeJudge`, `TraceIntegrityJudge`, `GroundingJudge`, and `SafetyBoundaryJudge`. A3 can surface these as policy and readiness evidence without owning the judge semantics.

| Field | A3 Mapping |
| --- | --- |
| `judge_name` | Per-judge panel label. |
| `judge_version` | Drift and reproducibility signal. |
| `policy_id` | Release policy join when available. |
| `policy_version` | Bundle reseal and release-gate dependency. |
| `thresholds` | Display only; A2 owns semantics. |
| `blocked` | Release-gate blocking signal from A2 policy output. |
| `blockers[]` | Reviewer workflow and report detail. |
| `waiver_allowed` | A3 review workflow hint; not an approval by itself. |
| `evidence_refs[]` | Links to redacted evidence artifacts. |
| `calibration_source` | `local_judge`, future `releasefoundry_grading`, or `llm_judge`. |
| `cost_summary` | Model/cost panel if supplied by optional calibration artifacts. |
| `redaction_status` | Required before display/export. |

### Failure Contract

- Top-level `primary_failure_class` is reserved for A2's canonical failure classes or `none`.
- Nested `failure_analysis.failure_classes` may contain local debug signals, but A3 must normalize them before clustering and must not treat them as canonical replacements.
- Missing optional A2 feeds must not break existing A3 report/dashboard paths.
- Optional feeds that A3 may load additively include `a2.coverage_report.v1`, `a2.calibration_matrix.v1`, `a2.commercial_readiness.v1`, `a2.case_book.v1`, `a2.regression_replay.v1`, `a2.sdk_parity.v1`, `a2.batch_plan.v1`, `a2.semantic_harness.v1`, and `a2.evidence_readiness.v1`.
- `releasefoundry_grading` and `llm_judge` observations require reviewed/redacted summaries and evidence refs; their absence is not a local deterministic test failure.

## A3 Readback Capture Boundary

A3 readback capture owns the product workflow receipt that an external worker, GitHub App worker, CI job, or future A1 platform service submits after reading external control state.

### Accepted Readback Receipt Fields

| Field | Meaning |
| --- | --- |
| `readback.schema_version` | Versioned readback receipt, for example `a3.github_check_readback_receipt.v1`. |
| `readback.provider` | External provider, currently expected to include `github`. |
| `readback.resource_kind` | External resource kind such as `github_check`, `pr_comment`, or required-check configuration. |
| `readback.readback_id` | Stable external readback receipt id. |
| `readback.readback_status` | `readback_confirmed`, `readback_stale`, `readback_missing`, `readback_failed`, or equivalent versioned status. |
| `readback.payload_hash` | Hash of sanitized observed payload or canonical summary. |
| `readback.expected` | Sanitized expected-state summary. |
| `readback.observed` | Sanitized observed-state summary. |
| `readback.matches` | Boolean/diff summary, for example `body_hash_match=false`. |
| `actor_hash` | Redacted actor identity signal. |

### A3 Capture Receipt Fields

| Field | Meaning |
| --- | --- |
| `release_id` / `release_gate_id` | Release-scoped readback join. |
| `readback_id` | Stored receipt id. |
| `payload_hash` | A3 capture hash for drift checks. |
| `audit_event_id` | `release_evidence.readback_captured` audit event join. |
| `artifact_type` | `release_evidence_readback`. |
| `usage_meter` | `release_evidence_readbacks`. |
| `idempotency_key` | Readback capture dedupe namespace, separate from A1/A2 imports. |
| `captured_at` | A3 receipt capture timestamp. |
| `redaction_status` | Required before report/export display. |

### Boundary Rules

- A3 redacts nested `authorization`, bearer token, cookie, password, key, secret-like value, and email fields.
- A3 stores sanitized current-authority rows in `release_evidence_readbacks`; an append-only history table is still a future growth point.
- A3 release evidence summary may use the latest captured readback to override static fixture state for A3 UI/reporting only.
- A3 readback status must not override A1 `verification_status`.
- A3 readback status must not override A2 `primary_failure_class`, judge scores, or policy semantics.
- A3 readback capture does not prove branch protection was created or enforced; it proves a sanitized receipt was accepted.
- Cross-tenant readback inspection must remain 404/hidden, not merely empty/forbidden with leaked ids.

## Semantic Warning: GitHub Readback Is Not A1 Verifier

`GitHub readback confirmed` and `A1 verifier passed` are different authority statements.

| Statement | Authority | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| GitHub readback confirmed | A3 sanitized readback receipt | A worker observed expected external GitHub-facing state and A3 captured the receipt. | Bundle integrity, artifact registry completeness, judge/policy version correctness, root hash validity, or branch protection enforcement. |
| A1 verifier passed | A1 evidence/bundle verifier | Bundle manifest, hashes, signature/root hash, release decision, approvals/waivers, and verifier rules passed. | That GitHub currently still contains the expected check run/comment/config. |
| A2 deterministic grade passed | A2 judge/policy service | The run behavior passed A2's deterministic scenario/judge contract. | That A1 artifacts were sealed or that GitHub publication succeeded. |

A3 must display these as adjacent evidence lines, not collapse them into one badge.

## Contract Risks

1. Treating `readback_confirmed` as equivalent to A1 `verification_status=passed`.
2. Treating GitHub check or PR comment presence as proof that required branch protection is enforced.
3. Ignoring API-level `status=error` because HTTP status was `200`.
4. Reintroducing A1 poll completion drift by looking for only one historical result shape.
5. Retrying mutating A1 `create-run` or `create-request` without the required no-retry/dedupe guardrails.
6. Copying private A1 evidence JSON, screenshots, request bodies, emails, tokens, or raw hosted failures into tracked A3 docs or artifacts.
7. Making optional A2 readiness feeds required and breaking A3 dashboards when they are absent.
8. Mixing A2 canonical `primary_failure_class` with nested local debug failure classes.
9. Failing to normalize 0-100 A2 scores and legacy 0-1 nested A1 case grade scores.
10. Failing to normalize tool-call aliases such as `name`, `tool`, `function.name`, `arguments`, `args`, `input`, and `arguments_json`.
11. Dropping `organization_id`, `tenant_id`, `project_id`, `request_id`, or `trace_id`, causing audit gaps or cross-tenant ambiguity.
12. Confusing A3 `payload_hash` for sanitized readback payloads with A1 artifact checksum/root-hash semantics.
13. Letting stale readback rows override newer A1 verifier packets or newer A2 policy results.
14. Sharing idempotency namespaces between A3 readback capture and A1/A2 import receipts.
15. Displaying raw nested `_failure.error` values from hosted media request failures instead of safe shape summaries.
16. Treating unstable dashboard usage counters as authoritative quota evidence.
17. Missing a bundle reseal trigger when readback state becomes an input to exported release evidence.
18. Failing to record readback capture as usage, weakening commercial metering.

## Adapter Points

1. `A1VerifierPacketToA3EvidenceAdapter`: imports A1 verifier packets as distinct verifier evidence rows.
2. `A1RunResultToA3RunSummaryAdapter`: maps A1 local or hosted run shapes into A3 run summary cards and report sections.
3. `A1TraceToA2RunAdapter`: normalizes A1 `AgentTurn`/`CaseResult` tool calls and final text into A2 `grade_run` input.
4. `A1TraceToA3ToolEvidenceAdapter`: maps redacted trace/tool-call ids into A3 drilldowns and report evidence.
5. `A1ArtifactRegistryToA3ManifestAdapter`: imports artifact registry refs, hashes, types, and retention metadata without copying raw payloads.
6. `A1ApiCalibrationToA3CalibrationPanelAdapter`: surfaces public-safe field keys, counts, command summaries, and private evidence refs only.
7. `A2GradeResultsToA3FailureReportAdapter`: maps `a2.grade_results.v1` into run status, score, failure class, judge result, and evidence excerpts.
8. `A2CoverageToA3ScenarioCoverageAdapter`: loads `a2.coverage_report.v1` additively for coverage panels and markdown report sections.
9. `A2CalibrationMatrixToA3CalibrationAdapter`: displays local/ReleaseFoundry/LLM agreement summaries without requiring missing live sources.
10. `A2EvidenceReadinessToA3PreflightAdapter`: exposes C3/C4 readiness gates as advisory status, not deterministic test failure.
11. `GitHubWorkerToA3ReadbackApiAdapter`: submits sanitized GitHub check/comment/config readback receipts to `POST /api/a3/releases/:releaseId/readbacks`.
12. `A3ReadbackToArtifactRegistryAdapter`: registers captured readbacks as `release_evidence_readback` artifacts with payload hashes.
13. `A3ReadbackToAuditUsageAdapter`: emits `release_evidence.readback_captured` and increments `release_evidence_readbacks`.
14. `A3ReadbackToBundleResealAdapter`: marks future bundle reseal as required when readback state becomes part of exported evidence.
15. `IdentityServiceAccountToReadbackActorAdapter`: maps signed CI/GitHub worker identity to `actor_hash`/`service_account_id` without leaking raw actor data.
16. `OpenApiZodReadbackSchemaAdapter`: keeps A3 route schemas compatible with future A1 platform clients and A3 UI validation.

## Recommended Implementation Order

1. Keep A3 readback capture and A1 verifier import as separate records and separate badges.
2. Define a minimal versioned A1 verifier packet fixture before writing an importer.
3. Add redaction-first schema validation for verifier and readback packets.
4. Add optional A2 feed loaders that degrade gracefully when readiness/calibration files are absent.
5. Add a bundle reseal signal only after readback state is intentionally included in exported evidence.
6. Add UI/report copy that says "GitHub readback captured" and "A1 verifier passed" as separate statuses.

## Evidence From This Contract Readback

- Source docs read are listed in `Purpose`.
- No private evidence, `.env.local`, real API, or GitHub state was read.
- No service or test files were changed.
- This document is the only intended artifact from the round.
