# P3 CL Gate A1/A2 Contract Alignment - 2026-07-09

Role: A3 Contract-Agent.

Scope: documentation artifact only. This pass identifies concrete A1/A2/A3 contract checks that a commercial A3 change-list gate should enforce without broad, noisy false positives. It does not modify `scripts/cl_guard.py`, `.github/workflows/cl-gate.yml`, services, tests, fixtures, or private evidence. No `.env.local`, private refs, or secrets are required.

## Sources Read

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- `docs/a1/README.md`
- `docs/a1/release_gate_bridge.md`
- `docs/a1/evidence/README.md`
- `docs/a1/api_calibration/README.md`
- `docs/a1/docs/evidence/worker_runtime_queue_retry_dead_letter_2026_07_08.md`
- `docs/a1/schemas/run_result.schema.json`
- `docs/a1/schemas/saas_release_evidence_verifier.schema.json`
- `docs/a2/README.md`
- `docs/a2/a1_a3_handoff.md`
- `docs/a2/openapi/a2_judge_service.openapi.json`
- `docs/a2/schemas/grade_results.schema.json`
- `docs/a2/schemas/release_gate.schema.json`
- `docs/a2/worklog/a2_main_drift_audit_20260708.md`
- `docs/a2/worklog/a2_money_grade_audit_20260708.md`
- `docs/a3/acceptance_checklist.md`
- `docs/a3/worklog.md`
- `docs/a3/p3_worklog.md`
- `docs/a3/mock_fixture_contract.md`
- `docs/a3/p3_a1_a2_a3_contract_delta_2026_07_07.md`
- `docs/a3/p3_a1_a2_release_evidence_v2_contract_map_2026_07_08.md`
- `docs/a3/p3_readback_a1_a2_contract_alignment_2026_07_08.md`
- `scripts/cl_guard.py`
- `.github/workflows/cl-gate.yml`

## Gate Posture

The current `scripts/cl_guard.py` and `.github/workflows/cl-gate.yml` already have the right shape: selective planning, high-confidence hygiene blockers, and stack-specific jobs. The commercial gap is not "run everything on every PR"; it is naming the cross-lane contracts that matter and routing only the relevant deterministic checks.

Low-noise CL rules:

- Never read `.env.local`, `docs/evidence/private_refs/`, `.secrets/`, or raw private evidence in CI.
- Treat live Ashr, live GitHub, branch-protection mutation, billing mutation, browser screenshot, and Docker daemon checks as opt-in release/integration jobs, not default CL blockers.
- Do not run A2 `--fail-on-block` in normal PR CL. The current commercial A2 release gate intentionally reports `decision=block`; CL should verify the report is deterministic, not fail because the documented product gate blocks release.
- Keep generated artifact, audit bundle, GitHub check, PR comment, hosted report, and readback evidence downstream of A1 run evidence and A2 judge evidence.
- Prefer exact schema/version/hash/fixture checks over broad text heuristics.
- Fail on high-confidence secret formats and tracked private/generated paths; avoid broad token-like scans that would catch redacted examples.

## Executable Check Matrix

`Automate now` means the check can be enforced today with existing commands. `Current hook` means the present CL workflow already runs it under some path conditions. `Small extension` means no product code is needed, but `scripts/cl_guard.py` would need a new selector or command step.

| ID | Executable check | Files/contracts referenced | Low-noise trigger | Automate now |
|---|---|---|---|---|
| CL-001 | Confirm `origin/main` is an ancestor of the PR head before merge: `git merge-base --is-ancestor origin/main HEAD`. | `docs/strategy/large-saas-a1-a2-a3-full-plan.md` merge gate section. | Every PR. | Yes, small extension. |
| CL-002 | Build selective plan: `python scripts/cl_guard.py plan --base "$BASE" --head HEAD --github-output "$GITHUB_OUTPUT"`. | `scripts/cl_guard.py`, `.github/workflows/cl-gate.yml`. | Every PR. | Yes, current hook. |
| CL-003 | High-confidence hygiene: `python scripts/cl_guard.py hygiene`. | `SECRET_PATTERNS`, private path and pinned artifact checks in `scripts/cl_guard.py`. | Every PR. | Yes, current hook. |
| CL-004 | Whitespace/diff hygiene: `git diff --check`. | Strategy merge gate: `diff --check clean`. | Every PR or any text/code change. | Yes, small extension. |
| CL-005 | Full CL reroute if `scripts/cl_guard.py` or `.github/workflows/cl-gate.yml` changes. | Current plan marks workflow/guard changes as `full`. | Guard/workflow changed. | Yes, current hook. |
| A1-001 | A1 RunResult and trace fixture contract: `python -B -m pytest tests/a1/test_runner.py tests/a1/test_trace_fixture.py -q -p no:cacheprovider`. | `docs/a1/schemas/run_result.schema.json`, `case_result.schema.json`, `trace_event.schema.json`, `observation.schema.json`. | `services/runner/**`, `packages/sdk/ashr_clone/types.py`, A1 run/trace schemas or fixtures. | Yes, current Python job when A1 paths change. |
| A1-002 | A1 hosted API client guardrails: `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`. | `docs/a1/api_calibration/README.md`, `packages/sdk/ashr_clone/api_client.py`, `services/runner/api_probe.py`. | API probe/client/calibration paths. | Yes, current Python job when A1 paths change. |
| A1-003 | A1 local cloud API and queue lifecycle: `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`. | `docs/a1/README.md`, `services/api/runtime.py`, `services/api/queue_worker.py`. | `services/api/**`, queue/runtime docs, A1 CLI paths. | Yes, current Python job when A1 paths change. |
| A1-004 | A1 worker retry/dead-letter contract: `python -B -m pytest tests/a1/test_worker_data_model.py tests/a1/test_cloud_api.py -q -p no:cacheprovider`. | `docs/a1/schemas/worker_data_model.schema.json`, `.indexes.json`, `.migration.sqlish`, worker evidence doc. | Worker data model, queue worker, runtime, worker schema docs. | Yes, current Python job when A1 paths change. |
| A1-005 | A1 release-gate bridge and endpoint contract: `python -B -m pytest tests/a1/test_release_gate_bridge.py tests/a1/test_saas_release_gate_endpoint.py -q -p no:cacheprovider`. | `docs/a1/release_gate_bridge.md`, `docs/a2/openapi/a2_judge_service.openapi.json`, `docs/a2/schemas/release_gate.schema.json`. | A1 release bridge, A2 service wrapper, release gate docs/schemas. | Yes, current Python job when A1/A2 paths change. |
| A1-006 | A1 release evidence verifier stays hash-only/public-safe: `python -B -m pytest tests/a1/test_saas_platform.py tests/a1/test_commercial_control_plane.py -q -p no:cacheprovider`. | `docs/a1/schemas/saas_release_evidence_verifier.schema.json`, `saas_platform.schema.json`, strategy artifact/bundle rules. | SaaS platform, verifier schema, release evidence backend controls. | Yes, current Python job when A1 paths change. |
| A1-007 | A1 Postgres/RLS/compose static contract: `python -B -m pytest tests/a1/test_a1_control_plane_postgres_migration.py tests/a1/test_local_self_host_smoke_compose.py -q -p no:cacheprovider`. | `docs/a1/schemas/a1_control_plane_postgres_migration.sql`, `services/runner/docker-compose.a1.yml`, `docs/a1/evidence/README.md`. | SQL migration, compose, Go API backend docs. | Yes, current Python job when A1 paths change. |
| A1-008 | A1 public evidence index shape: `python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider`. | `docs/a1/api_calibration/real_api_evidence_index.json`, `docs/a1/schemas/evidence_index.schema.json`. | API calibration index/schemas/docs. | Yes, current Python job when A1 paths change. |
| A1-009 | TypeScript SDK parity and dry-run guardrails: `npm test --prefix packages/ts/ashr-clone`. | `packages/ts/ashr-clone/package.json`, `docs/a1/schemas/agent_input.schema.json`, A1 README TS parity section. | `packages/ts/ashr-clone/**` or shared A1 SDK schemas. | Yes, current TypeScript job when TS paths change. |
| A1-010 | Go SDK/control-plane backend tests: run `go test ./...` from `packages/go/ashrclone`. | `packages/go/ashrclone/**`, A1 platform/SQL/Go strategy boundary. | `packages/go/ashrclone/**`. | Yes, current Go job. |
| A1-011 | Go integration tests: run `go test ./...` from `tests/integration/go`. | `tests/integration/go/**`, Go/Python route contract evidence. | Go integration paths or API route contract changes. | Yes, current Go job. |
| A2-001 | A2 deterministic fixture reproducibility: `python -B scripts/a2_regenerate_fixtures.py --check`. | `fixtures/a2/results/*.json`, `fixtures/a2/runs/*.json`, `packages/scenarios/a2_g3_full_pack.json`, A2 schemas. | A2 judge/scenario/calibration/result fixture paths. | Yes, current Python job covers tests; small extension for explicit fixture drift. |
| A2-002 | A2 local-lite profile: `python -B scripts/a2_local_lite_check.py`. | `scripts/a2_local_lite_check.py`, `scripts/a2_regenerate_fixtures.py`, `tests/a2/**`. | A2-only changes or low-resource CL preflight. | Yes, small extension. |
| A2-003 | A2 grade result/failure taxonomy contract: `python -B -m pytest tests/a2/test_contracts.py tests/a2/test_judges.py -q -p no:cacheprovider`. | `docs/a2/schemas/grade_results.schema.json`, `docs/a2/failure_taxonomy_v0.md`, `services/judge/runner.py`. | A2 judge, taxonomy, schema, scenario fixtures. | Yes, current Python job. |
| A2-004 | A2 service wrapper/OpenAPI boundary: `python -B -m pytest tests/a2/test_service_wrapper.py -q -p no:cacheprovider`. | `docs/a2/openapi/a2_judge_service.openapi.json`, `services/judge/service_wrapper.py`, A1 bridge GradeResult-like envelope. | A2 service wrapper/OpenAPI or A1 release bridge changes. | Yes, current Python job. |
| A2-005 | A2 release policy and scenario selection: `python -B -m pytest tests/a2/test_release_policy.py tests/a2/test_scenario_selection.py -q -p no:cacheprovider`. | `docs/a2/schemas/release_policy.schema.json`, `scenario_selection.schema.json`, `fixtures/a2/config/release_policies.json`. | Policy/scenario/config changes. | Yes, current Python job. |
| A2-006 | A2 result persistence public-safe manifest: `python -B -m pytest tests/a2/test_result_persistence.py -q -p no:cacheprovider`. | `docs/a2/schemas/result_persistence_manifest.schema.json`, `fixtures/a2/results/a2_result_persistence_manifest.json`. | Result persistence or public-safe artifact changes. | Yes, current Python job. |
| A2-007 | A2 judge version registry: `python -B -m pytest tests/a2/test_judge_versioning.py -q -p no:cacheprovider`. | `docs/a2/schemas/judge_versions.schema.json`, `fixtures/a2/results/a2_judge_versions.json`. | Judge versioning, scenario pack, grade report changes. | Yes, current Python job. |
| A2-008 | A2 release gate fixture determinism without failing on intentional block: `python -B scripts/a2_build_release_gate_report.py --check`. | `fixtures/a2/results/a2_release_gate_report.json`, `docs/a2/schemas/release_gate.schema.json`, A2 money-grade audit. | A2 release gate/commercial readiness/evidence readiness changes. | Yes, small extension. |
| A2-009 | A2 external evidence preflight is public-only: `python -B scripts/a2_external_evidence_preflight.py --json`. | `docs/a2/schemas/external_evidence_preflight.schema.json`, `fixtures/a2/results/a2_evidence_readiness_report.json`, private evidence boundary docs. | External evidence readiness, C3/C4 import/preflight changes. | Yes, small extension. |
| A2-010 | A2 optional readiness feeds remain additive: `python -B scripts/a2_regenerate_fixtures.py --check` plus A3 report-builder tests. | `a2.commercial_readiness.v1`, `a2.case_book.v1`, `a2.regression_replay.v1`, `a2.sdk_parity.v1`, `a2.batch_plan.v1`, `a2.semantic_harness.v1`, `a2.evidence_readiness.v1`. | A2 optional result fixtures or A3 consumers. | Yes, current tests plus small explicit selector. |
| A3-001 | A3 mock fixture generation from A2 outputs: `node --test tests/a3/a3_fixture_builder.test.mjs`. | `docs/a3/mock_fixture_contract.md`, `services/report/a3_fixture_builder.mjs`, `fixtures/a3/mock_run_results.json`, `fixtures/a3/mock_grade_results.json`. | A2 scenario/grade/run fixture changes or A3 fixture builder changes. | Yes, current A3 Node job. |
| A3-002 | A3 report builder consumes A1/A2/P3 shapes and preserves failure classes: `node --test tests/a3/report_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs`. | `services/report/report_builder.mjs`, `services/report/p3_ashr_mapper.mjs`, A1/A2 handoff docs. | Report builder, mapper, A1/A2 display contract changes. | Yes, current A3 Node job. |
| A3-003 | A3 Gate CLI release decision, waiver, approval, GitHub payload, manifest, and bundle contracts: `node --test tests/a3/a3_gate_cli.test.mjs`. | `services/report/a3_gate_cli.mjs`, `fixtures/a3/release_gate_thresholds.json`, pinned A3 P3 fixtures. | Gate CLI, threshold, waiver, approval, pinned evidence changes. | Yes, current A3 Node job. |
| A3-004 | A3 pinned audit bundle verification: `node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --generated-at 2026-07-07T00:00:00.000Z --strict-exit --json`. | Strategy section 14 pinned fixture rule, `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`. | Pinned A3 audit/gate fixture changes. | Yes, current evidence job. |
| A3-005 | A3 audit archive manifest/verifier and export firewall: `node --test tests/a3/a3_audit_archive.test.mjs tests/a3/export_firewall_generated_artifacts.test.mjs`. | `services/report/a3_audit_archive.mjs`, `tests/a3/export_firewall_generated_artifacts.test.mjs`, docs/fixtures under `docs/a3` and `fixtures/a3`. | Generated A3 docs/fixtures, archive, redaction firewall changes. | Yes, current A3 Node job when A3 paths change. |
| A3-006 | A3 GitHub publish/readback contract states: `node --test tests/a3/a3_github_integration.test.mjs`. | `services/report/a3_github_integration.mjs`, `docs/a3/p3_github_readback_contract_2026_07_08.md`, GitHub dry-run fixtures. | GitHub integration, check/comment/readback fixtures/docs. | Yes, current A3 Node job. |
| A3-007 | A3 readback capture API/CLI and v2 release evidence: `node --test tests/a3/a3_readback_capture_cli.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_api_server.test.mjs`. | `services/report/a3_readback_capture_cli.mjs`, `a3_release_evidence.mjs`, readback capture docs. | Readback API/CLI, release evidence v1/v2, readback fixtures. | Yes, current A3 Node job. |
| A3-008 | A3 tenant scope and SQLite persistence: `node --test tests/a3/a3_store.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/a3_api_server.test.mjs`. | `services/report/a3_store.mjs`, `a3_sqlite_store.mjs`, `a3_api_server.mjs`, A3 worklog tenant-scope rules. | Store/API/SQLite/report lifecycle changes. | Yes, current A3 Node job. |
| A3-009 | Report Center manifest and Artifact Registry: `node --test tests/a3/report_center_index.test.mjs tests/a3/report_center_manifest_contract.test.mjs tests/a3/artifact_registry.test.mjs`. | `docs/a3/p3_report_center_manifest_growth_2026_07_07.md`, `services/report/a3_report_center*.mjs`, `a3_artifact_registry.mjs`. | Report Center, manifest, artifact registry, hosted report export changes. | Yes, current A3 Node job. |
| A3-010 | Durable review workflow does not auto-unblock without valid governance: `node --test tests/a3/a3_review_workflow.test.mjs tests/a3/a3_gate_cli.test.mjs`. | `services/report/a3_review_workflow.mjs`, Gate CLI waiver/approval schemas, A2 release gate review workflow. | Review workflow, waiver, approval, gate CLI changes. | Yes, current A3 Node job. |
| A3-011 | SaaS Admin action requests stay plan/guardrail-only: `node --test tests/a3/a3_saas_admin.test.mjs`. | `services/report/a3_saas_admin.mjs`, A3 acceptance checklist admin action rules. | Admin console, action request, usage/API-key/team/trust/cloud UI changes. | Yes, current A3 Node job. |
| A3-012 | Hosted/shareable report redaction and denied pages: `node --test tests/a3/shareable_report.test.mjs`. | `services/report/a3_shareable_report.mjs`, hosted report lifecycle acceptance entries. | Hosted report/share token/redaction changes. | Yes, current A3 Node job. |
| A3-013 | SQL adapter and usage/report-center contract: `node --test tests/a3/sql_adapter_contract.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/a3_sqlite_store.test.mjs`. | `docs/a3/p3_sql_adapter_contract_2026_07_07.md`, `services/report/a3_sql_migrations.mjs`, usage ledger contracts. | SQL migration/usage ledger/report center storage changes. | Yes, current A3 Node job. |
| A3-014 | Dashboard wiring smoke without browser dependence: `node --test tests/a3/dashboard_wiring.test.mjs`. | `apps/dashboard/src/app.mjs`, A3 acceptance checklist dashboard/report panels. | Dashboard app/component/report wiring changes. | Yes, current A3 Node job. |
| X-001 | Cross-lane score-scale safety: verify A1 0-1 and A2 0-100 scores preserve source/provenance in A3 summaries. | `docs/a1/schemas/grade_result.schema.json`, `docs/a2/schemas/grade_results.schema.json`, `docs/a3/p3_a1_a2_a3_contract_delta_2026_07_07.md`. | Report builder, fixture builder, P3 mapper, grade schemas. | Yes, small extension; partially covered by A3 report tests. |
| X-002 | Cross-lane tool-call alias normalization: run A2 contracts plus A3 report builder diff tests. | A1 `AgentTurn`, A2 `normalize_run_input`, A3 `buildToolCallDiffs`. | Tool-call adapter, judge runner, report builder, P3 mapper changes. | Yes, current Python/A3 tests; add a combined selector. |
| X-003 | Optional A2 feeds are missing/stale/additive, not blockers for core dashboard: run A3 report-builder tests with A2 fixtures. | A2 handoff optional feeds and A3 release evidence/readiness docs. | Optional A2 fixture or A3 report consumer changes. | Yes, current A3 tests; small extension for explicit fixture set. |

## Recommended CL Guard Wiring

The current workflow already has broad selectors. The next low-noise improvement is to split `python` into reasoned contract groups in `scripts/cl_guard.py` while preserving current job names:

| Selector | Paths | Suggested required checks |
|---|---|---|
| `a1_runtime_contract` | `services/runner/**`, `services/api/**`, `packages/sdk/ashr_clone/**`, `docs/a1/schemas/**`, `tests/a1/**` | A1-001 through A1-008. |
| `a1_ts_contract` | `packages/ts/ashr-clone/**`, shared A1 SDK schemas | A1-009. |
| `a1_go_contract` | `packages/go/ashrclone/**`, `tests/integration/go/**` | A1-010 and A1-011. |
| `a2_eval_contract` | `services/judge/**`, `scripts/a2_*.py`, `docs/a2/**`, `fixtures/a2/**`, `packages/scenarios/**`, `tests/a2/**` | A2-001 through A2-010. |
| `a3_commercial_contract` | `services/report/**`, `apps/dashboard/**`, `docs/a3/**`, `fixtures/a3/**`, `tests/a3/**` | A3-001 through A3-014. |
| `release_evidence_contract` | A3 gate/readback/audit bundle/archive/report center paths plus pinned A3 fixtures | A3-003 through A3-013 plus CL-003. |

For docs-only CLs, the gate should still run hygiene, diff check, and the matching doc-contract tests if they exist. It should not run live API, browser screenshot, Docker daemon, or paid calibration commands.

## Checks To Avoid As Default CL Blockers

These are valuable, but too noisy or environment-bound for the default A3 commercial CL gate:

- Live Ashr API smoke or mutating calibration. Use only explicit maintainer-approved jobs with private output.
- Live GitHub Check/PR comment publishing or branch-protection mutation. Default CL may build dry-run payloads and readback-shaped fixtures only.
- `python scripts/a2_build_release_gate_report.py --check --fail-on-block` in normal PRs. The current product gate blocks by design while C3/C4/C5 evidence is partial.
- Browser screenshot assertions. Keep them as release/demo evidence, not PR contract checks.
- Full Docker Compose startup. Keep static compose validation in CL; run live compose smoke in a separate self-host/integration lane.
- Repository-root `go test ./...`; the repo root is not a Go module. Run from `packages/go/ashrclone` and `tests/integration/go`.
- Broad secret regexes over all docs that flag intentional redaction examples. Keep high-confidence scanners and artifact firewall allowlists.

## Immediate Automation Priority

1. Add CL-001 and CL-004 as always-on shell checks.
2. Add explicit A2 fixture and release-gate determinism steps: A2-001 and A2-008.
3. Add A2 external evidence preflight: A2-009, because it proves no private evidence is needed before C3/C4 collection.
4. Keep A3 pinned evidence verification as-is, and add A3-005 firewall coverage to any PR that changes `docs/a3` or `fixtures/a3`.
5. Add cross-lane selector labels to the CL plan summary so reviewers can see whether a PR touched A1 runtime, A2 evaluation, A3 commercial evidence, or release evidence authority.

## Verdict

The A3 commercial CL gate can enforce more than 20 concrete A1/A2/A3 contracts today without becoming noisy. The safest default gate is selective, deterministic, public-safe, and artifact-aware:

- A1 checks prove run, trace, worker, API, SDK, Go, SQL, and release-evidence verifier contracts.
- A2 checks prove deterministic judging, schema stability, release policy, scenario selection, public-safe persistence, evidence preflight, and release gate determinism.
- A3 checks prove dashboard/report consumption, Gate CLI, waiver/approval governance, audit bundle/archive verification, GitHub publish/readback states, hosted report redaction, tenant scope, SQL/usage/report center contracts, and artifact registry safety.

The gate should not pretend to verify production branch protection, paid API calibration, hosted auth/RBAC, or live GitHub state until those are explicit integration jobs with reviewed private evidence boundaries.
