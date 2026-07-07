# A3 Product Console A1/A2 Compatibility Evidence - 2026-07-07

## Purpose

This artifact explains how the new A3 Product Console consumes A1 and A2 evidence without changing their source semantics.

The Product Console is not a replacement for A1 runner or A2 judge. It is a customer-facing workflow layer that reads normalized A1/A2 evidence and turns it into onboarding, project, audit, and commercial-readiness state.

## A1 Fields Consumed

| A1 Field | A3 Product Console Use |
|---|---|
| `run_id` | Project recent-runs list and release evidence scope. |
| `dataset_id` | Future project/dataset page join. |
| `runner_id` | Future ingestion/source attribution. |
| `status` | Run health and project release state. |
| `cases[]` | Project case count, failure count, onboarding first-run completion. |
| `case_id` | Audit/report/case deep-link identity. |
| `scenario_id` | Future scenario coverage and regression promotion. |
| `trace_events[]` | A1 trace-ingestion readiness check. |
| `observations[]` | Future observability/audit replay readiness. |
| `expected.tool_calls[]` | Tool-call evidence and diff readiness. |
| `actual.tool_calls[]` | Tool-call evidence and failure triage. |
| `media_evidence` | Future media onboarding and report evidence readiness. |

## A2 Fields Consumed

| A2 Field | A3 Product Console Use |
|---|---|
| `case_id` | Join key between A1 case evidence and A2 grade evidence. |
| `passed` | Project pass/fail and release health. |
| `score` | Project average score and commercial readiness. |
| `primary_failure_class` | Failure-class project summary and triage action. |
| `severity` | Future reviewer queue priority. |
| `judge_results[]` | A2 judge-join readiness and audit evidence. |
| `judge_mode` | Future judge-version and policy display. |
| `evidence` | Future trace/event refs in audit/reviewer workflow. |
| `remediation` | Future project action recommendation. |
| `rubric_result` | Future explainability drilldown. |

## Product Console Sections

| Section | A1/A2 Dependency | Why It Matters |
|---|---|---|
| Onboarding | A1 first run + A2 judge result + report center | Shows whether a new tenant reached first value. |
| Project Console | A1 runs/cases + A2 pass/fail/failure class | Shows project release health. |
| Audit Log | API imports + hosted report/share events | Shows review and compliance trail. |
| Commercial Readiness | A1 trace + A2 judge + usage + report + audit | Shows whether this tenant is credible for paid usage. |

## Risks

- If A1 omits trace events, Product Console readiness should not claim trace ingestion is ready.
- If A2 grade results cannot join by `case_id`, Product Console should show judge evidence missing.
- If report/audit events are absent, Product Console should show audit log empty instead of invented compliance.
- If usage ledger is missing, Product Console should not claim billing/usage readiness.
- If tenant scope is missing, Product Console must default to local-only `org-local/project-local` and avoid real multi-tenant claims.

## Contract Assertions Tests Should Cover

1. Product Console schema is `a3.product_console.v1`.
2. A1 run count drives onboarding `submit_first_run`.
3. A2 judge evidence drives onboarding `attach_judge_results`.
4. A1/A2 case count drives project console `summary.case_count`.
5. A2 failure class drives project console `failure_classes`.
6. Report Center report count drives onboarding `create_hosted_report`.
7. Usage ledger meters drive project console `usage_snapshot`.
8. Audit events are redacted-only and never include raw token/cookie/key values.
9. Empty inputs produce `setup_required`, `empty`, and `needs_more_real_evidence`.
10. API dashboard payload includes `product_console`.
11. `/api/a3/product/console` returns the same schema as dashboard payload.
12. Dashboard renders Onboarding Flow, Project Console, Audit Log, and Commercial Readiness.
13. Product Console does not mutate A1 runner logic.
14. Product Console does not mutate A2 judge semantics.
15. Missing hosted auth keeps invite/reviewer/billing operations pending or plan-only.

## Current Evidence

- Code: `services/report/a3_product_console.mjs`
- API route: `GET /api/a3/product/console`
- Dashboard component: `apps/dashboard/src/components/product-console-panel.mjs`
- Tests:
  - `tests/a3/a3_product_console.test.mjs`
  - `tests/a3/a3_api_server.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`

## Safety Boundary

- No `.env.local` read or printed.
- No live Ashr write call.
- No real API key, cookie, token, account email, signed URL, or official private source committed.
- Product Console is read-only workflow state until A1 hosted auth/project APIs exist.
