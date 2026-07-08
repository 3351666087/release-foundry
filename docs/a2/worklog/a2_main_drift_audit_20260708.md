# A2 Main Drift Audit - 2026-07-08

## Scope

Agent: A2 Integration/Evidence-Agent

Task: audit A1/A3 drift between current A2 branch `dev/g3-a2-calibration` and GitHub `main` at `3738f70b325d485e428b92096491afdcf015bcd9`.

Rules followed:

- Used GitHub API and local refs because `git fetch` was reported unavailable.
- Did not read private refs.
- Did not read key files.
- Did not edit implementation code.
- This worklog is public-safe and contains only redacted/summarized evidence.

## Repo State

- Repo: `3351666087/ashr-codex-factory`
- Local branch: `dev/g3-a2-calibration`
- Local HEAD at audit start: `508cde400a860a14f75957f36b206a2d6c005263`
- Local HEAD after concurrent worktree update: `a9580e7b48de092cd1bc1e035637c76f3b5f30b2`
- Local `origin/dev/g3-a2-calibration`: `508cde400a860a14f75957f36b206a2d6c005263`
- Local `origin/main`: `69025b56146bc3f3d78fefe9f024e3c2a71e47e3`
- GitHub `main` audited target: `3738f70b325d485e428b92096491afdcf015bcd9`
- GitHub compare status for `508cde4...3738f70`: `diverged`
- GitHub compare counts: `ahead_by=24`, `behind_by=3`, `total_commits=24`

Interpretation: local `origin/main` is stale; drift judgment must use GitHub API evidence at `3738f70`, not local `origin/main`. The later local-only `a9580e7` commit adds `docs/a2/worklog/a2_money_grade_audit_20260708.md` only, so it does not change this A1/A3 requested-path drift audit.

## Commands / Evidence

```powershell
git status --short --branch
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git rev-parse origin/dev/g3-a2-calibration
gh repo view --json nameWithOwner,url,defaultBranchRef
gh api repos/3351666087/ashr-codex-factory/compare/508cde400a860a14f75957f36b206a2d6c005263...3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/docs/strategy/large-saas-a1-a2-a3-full-plan.md?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/docs/a1/release_gate_bridge.md?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/docs/a1/schemas/saas_release_evidence_verifier.schema.json?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/docs/a1/schemas/saas_platform.schema.json?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/packages/sdk/ashr_clone/saas.py?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/packages/ts/ashr-clone/src/saas.ts?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/services/report/a3_api_server.mjs?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/services/report/a3_store.mjs?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/services/report/a3_github_integration.mjs?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/services/report/a3_review_workflow.mjs?ref=3738f70b325d485e428b92096491afdcf015bcd9
gh api -H "Accept: application/vnd.github.raw" repos/3351666087/ashr-codex-factory/contents/services/report/a3_artifact_registry.mjs?ref=3738f70b325d485e428b92096491afdcf015bcd9
git show --name-status --oneline --stat a9580e7b48de092cd1bc1e035637c76f3b5f30b2
git diff --name-status 508cde400a860a14f75957f36b206a2d6c005263..a9580e7b48de092cd1bc1e035637c76f3b5f30b2
```

Local search note: `rg.exe` returned `Access is denied`, so local inspection used `git grep` and `git ls-tree`.

## Changed Path Counts

Only requested paths were counted.

| Prefix | Files | Additions | Deletions | Changes |
|---|---:|---:|---:|---:|
| `packages/sdk/` | 2 | 424 | 13 | 437 |
| `packages/ts/` | 9 | 2653 | 55 | 2708 |
| `services/runner/` | 0 | 0 | 0 | 0 |
| `services/report/` | 11 | 2230 | 25 | 2255 |
| `docs/a1/` | 14 | 3407 | 5 | 3412 |
| `docs/a3/` | 10 | 1270 | 3 | 1273 |
| `tests/a1/` | 15 | 262 | 0 | 262 |
| `tests/a3/` | 11 | 0 | 0 | 0 |
| `fixtures/a3/` | 3 | 181 | 0 | 181 |
| `docs/strategy/` | 1 | 933 | 1240 | 2173 |

Total matched files in requested paths: 76.

## A1 Drift Summary

Relevant commits on GitHub `main` include:

- `A1: add hosted control plane HTTP parity`
- `A1: add SaaS platform data and delivery primitives`
- `A1: add release evidence backend controls`
- `A1: expose hosted evidence verification`
- `A1: harden SaaS evidence verifier auth`
- `A1: enforce SaaS idempotency fingerprints`
- `A1: add polyglot SaaS runtime foundation`
- `A1: add SaaS worker retry and polyglot parity`
- `A1: close TypeScript SaaS parity gap`

Key A1 contract changes:

- `docs/a1/release_gate_bridge.md` defines A1 -> A2 bridge target `A2.release_gate.evaluate`.
- A1 bridge accepts A2 response either as a direct GradeResult-like object or wrapped as `{ "grade_result": { ... } }`.
- A1 control plane exposes `POST /v1/projects/{project_id}/runs/{run_id}/release-gate`.
- A1 release evidence paths now include build/verify packet behavior, hash-only bindings, usage event IDs, audit-chain verification, and `raw_payload_included=false`.
- Python SDK `packages/sdk/ashr_clone/saas.py` added/expanded release evidence packet build/verify, artifact manifest, audit chain, usage/quota, idempotency, and release-gate related client calls.
- TypeScript SDK `packages/ts/ashr-clone/src/saas.ts` now mirrors much of the SaaS control-plane contract: quota, idempotency, artifact manifests, audit chain verification, release evidence build/verify, release gate evaluation, worker job operations, and OpenAPI export.
- `services/runner/` had no requested-path drift in this compare.

## A3 Drift Summary

Relevant A3 commits on GitHub `main` include:

- `Add A3 artifact registry evidence catalog`
- `Add A3 SQLite store and report lifecycle controls`
- `Add A3 SaaS admin action requests`
- `Add A3 durable review workflow records`
- `Add A3 GitHub check publisher`
- `Add A3 GitHub PR comment publisher`
- `Refresh main artifacts after active branch merge`

Key A3 contract changes:

- `services/report/a3_api_server.mjs` exposes A2 import route `POST /api/a3/import/a2-grade-result`.
- A3 API/store now has review waiver/approval routes, artifact registry route, report center, usage ledger, hosted/shareable report lifecycle, and admin action request surfaces.
- `services/report/a3_store.mjs` validates and imports A2 GradeResult payloads, supports idempotency receipts, and preserves A2 source semantics at the A3 boundary.
- `services/report/report_builder.mjs` consumes A2 `a2.release_gate.v1`, A2 case book, regression replay, commercial readiness, and artifact registry summaries.
- `services/report/a3_github_integration.mjs` builds dry-run/live-capable GitHub Check, PR comment, and branch protection required-check plans. The check name is `Ashr++ Release Gate`.
- `fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json` shows failure conclusion driven by A2-style blocked evidence and top-risk A2 cases.
- `fixtures/a3/p3/a3_github_required_check_plan.redacted.json` plans required branch protection for `Ashr++ Release Gate`, dry-run only.
- `services/report/a3_review_workflow.mjs` hash-seals waiver/approval records and derives review state from release gate and report evidence.
- `services/report/a3_artifact_registry.mjs` creates public-safe artifact registry entries for reports, usage ledger, DB migration plan, product console, and SaaS admin guardrails.

## Strategy Drift Summary

`docs/strategy/large-saas-a1-a2-a3-full-plan.md` was heavily rewritten into a commercial SaaS strategy bus.

Relevant A2 implications:

- A2 is explicitly positioned as `Evaluation / Policy / Security`.
- Judge service direction is Python + FastAPI + Pydantic + OpenAPI.
- A2 should own judge, policy, scenario, calibration, regression, semantic eval, security verification, privacy validation, abuse detection, and bundle verifier correctness.
- TypeScript remains important for A3/product and SDK parity, but A2 does not need to own a full TypeScript runtime.
- SQL/PLpgSQL is A1-primary; A2 should review policy/security implications without expanding into SQL-heavy implementation unless contract-driven.

This aligns with the current A2 scope preference: keep Python deep, maintain JSON Schema/OpenAPI contracts, and avoid unnecessary SQL/TypeScript implementation expansion.

## A2 Impact Assessment

### Schema impact

Current A2 branch already has:

- `a2.grade_results.v1`
- `a2.grade_result.v1`
- `a2.release_gate.v1`
- `a2.regression_replay.release_gate_summary.v1`
- `docs/a2/openapi/a2_judge_service.openapi.json`
- `/internal/judge/case`
- `/internal/judge/run`
- `/internal/judge/batch`

No immediate public schema break was proven from GitHub `main`. A3 still consumes A2 as `grade_result`, `grade_results`, release gate report, case book, regression replay, and commercial readiness fixtures.

### SDK parity impact

A1 now has richer Python and TypeScript SaaS control-plane SDK parity. A2 does not need to implement TypeScript runtime code this round, but should add/keep tests proving that:

- A2 single GradeResult can be returned directly.
- A2 GradeResult can also be accepted through `{ "grade_result": { ... } }`.
- A2 release gate service output remains compatible with A1 `A2.release_gate.evaluate`.
- A2 release/evidence summaries remain hash-only and public-safe when consumed by A1/A3.

### Dashboard / A3 consumption impact

A3 consumption pressure increased. A3 now uses A2 output for:

- release gate GitHub Check and PR comment payloads;
- review workflow waiver/approval state;
- artifact registry and evidence packet summaries;
- report center and shareable report exports;
- regression, case book, commercial readiness, and reviewer workflow summaries.

This means A2 additive fields are safe, but breaking or renaming these core artifacts is high risk:

- `fixtures/a2/results/a2_g3_grade_results.json`
- `fixtures/a2/results/a2_release_gate_report.json`
- `fixtures/a2/results/a2_case_book.json`
- `fixtures/a2/results/a2_regression_replay_report.json`
- `fixtures/a2/results/a2_commercial_readiness_report.json`

## Recommendation

This round does not require immediate broad A2 code adaptation before merge. Existing A2 contracts appear compatible with the observed A1/A3 main drift.

However, one small follow-up is recommended before relying on main integration:

1. Add a focused A2 service-wrapper or contract test fixture for the A1 release-gate bridge request shape from `docs/a1/release_gate_bridge.md`.
2. Verify A2 can return a direct GradeResult-like response and/or a wrapped `{ "grade_result": { ... } }` form without breaking A1.
3. Verify `a2.release_gate.v1` and `a2.a3_release_gate_summary.v1` still provide fields required by A3 GitHub Check / PR comment / review workflow surfaces.
4. Keep A2 implementation Python-first; do not add SQL or full TS runtime ownership for this drift.

Priority: medium-high. Not a P0 break, but it is the clearest integration risk created by current main drift.

## Risks

- `git fetch` remains unavailable, so this audit relied on GitHub API and local refs. The local worktree has not materialized these main files.
- GitHub compare reports `diverged`, meaning a later merge may need conflict resolution beyond the requested path audit.
- A3 has expanded artifact registry, review workflow, and GitHub required-check behavior; A2 release gate fields should be treated as externally consumed contract fields.
- A1 TypeScript/Python SDK parity has advanced quickly; A2 should avoid schema churn until a coordinated versioned contract is agreed.
- No private evidence or real Ashr API key was used in this audit; real API calibration status was not revalidated.
