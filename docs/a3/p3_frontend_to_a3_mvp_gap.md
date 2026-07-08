# P3 Frontend To A3 MVP Gap

## Already Covered By A3

| Real Ashr Product Idea | Current A3 Coverage |
|---|---|
| Product console shell | `apps/dashboard/index.html` product console layout |
| Datasets and runs as top-level objects | Object summary panel and run list |
| Run/case detail | Case Detail panel |
| Expected vs actual | Expected vs Actual panel |
| Tool-call inspection | Tool Call Diff panel with argument diffs |
| Failure triage | Failure clusters, severity/score filters, Triage Queue |
| Score/pass-fail summary | Summary metrics and normalized case rows |
| Media evidence | Media Evidence panel and P3 media mapper |
| Report/export | JSON/CSV/Markdown export plus print-ready report preview |
| Coverage health | A2 coverage panel |
| Request provenance | Request Provenance panel plus JSON/Markdown export fields |

## Partially Covered

| Area | Current State | Gap |
|---|---|---|
| Usage/quota | Dashboard has known-gap panel | Real counters are not mapped into A3 fixtures. |
| Signed media URL | Field name `signed_url` observed in redacted dataset sample | A3 does not render live signed media links and should not until redaction/access rules are clear. |
| Native failure class | A3 derives failure class from local/A2/P3 fields | A real failed run was checked; the sample exposed grade metrics/reason but no named backend `failure_class`. |
| Authenticated frontend navigation | Direct Chrome/CDP observation confirmed top-level Lab tabs and dataset `884` case browsing | Hosted run `11925` now exists through API, but official Results still shows 0 runs. |
| New dataset request flow | Direct UI observation confirmed an 8-step wizard | A3 should not build the wizard; it should show provenance from generated datasets/runs. |
| Trust/certificate flow | Direct UI observation confirmed a public trust-page concept | A3 report export covers the student-MVP version; public hosting/certificates are out of scope. |

## Not Needed For Student MVP

- Account/team management.
- Billing and upgrades.
- API key creation/revocation UI.
- Hosted mutation flows from A3.
- Full 8-step dataset generator.
- Trust-page publishing / public certificate hosting.
- Full observability product.
- Raw private prompt/request editing.

## Recommended MVP Boundary

A student-team MVP should be a local, read-only product console:

- load local fixture-shaped data
- show run list and case detail
- compare expected vs actual
- explain tool-call mismatches
- group failures
- export a report

This matches the highest-value Ashr workflow without requiring production auth, billing, or mutating API operations.

## 2026-07-06 Direct UI Gap Update

The authenticated Lab UI was observed through an isolated Chrome profile. This removes the earlier navigation uncertainty: A3 can now cite real UI tabs for Datasets, Agents, Folders, Analytics, Usage, Trust, API Keys, and Team.

The remaining frontend gap is not login anymore. A 2026-07-06 API probe found a real failed run and confirmed backend fields, and A3 later created the official demo run `11925` for dataset `884`. After the user restored a logged-in Chrome session, the official frontend confirmed dataset/case browsing but still showed `Results (0)` and `No runs found`. A3 still needs an official UI-visible result path to verify how Ashr renders:

- run detail
- case detail
- expected vs actual
- tool calls
- trace/timeline
- native frontend failure labels

Confirmed official dataset/case UI:

- Dataset overview has Overview / Test cases / Results tabs.
- Test cases list shows title, case key, description, action count, and tag count.
- Case detail shows TEST DETAILS, tags, ACTIONS, actor, content, TEXT/AUDIO labels, and Tool Calls.
- `Open Most Recent Run` does not find a run for dataset `884`.

Backend/API note:

- Real failed-run API evidence now confirms `run.result.status`, per-case `grade.passed`, `grade.score`, `grade.reason`, and `grade.metrics`.
- Official demo run `11925` confirms the same A3-visible workflow with 5 refund cases, 2 pass, and 3 fail.
- Official-UI-compatible demo run `11926` confirms the `result.tests[].action_results[]` workflow with 5 refund tests, 2 pass, and 3 fail, and appears in `list_runs(dataset_id=884, summary_only=true)`.
- No native backend `failure_class` field was present in the failed-run or official demo evidence, so A3's derived failure clusters remain the correct MVP behavior.

Current MVP implication:

- A3 can proceed with run `11926` as the best official-demo source.
- The only remaining frontend-specific gap is visual confirmation in a logged-in Ashr browser that Results lists run `11926`.
