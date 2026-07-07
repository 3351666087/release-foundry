# P3 Frontend Workflow Notes

## Product Workflow

The real Ashr product appears to organize agent evaluation around this object flow:

```text
Request -> Dataset -> Run -> Case/Test Detail -> Evidence -> Report/Decision
```

Direct authenticated Lab observation on 2026-07-06 also shows a broader console flow:

```text
Agents / Datasets / Folders -> Analytics -> Usage -> Trust -> API Keys / Team
```

The visible UI was mostly empty-state because the observed account had no datasets, no agents, no folders, and no graded runs. Even so, the navigation confirms that Ashr treats evaluation as a product console with separate areas for artifacts, analytics, quota, trust/certification, access, and team management.

For A3, the most useful workflow is:

1. User opens a product console.
2. User picks a dataset or run.
3. User scans pass/fail, score, and failure clusters.
4. User opens a failed case.
5. User compares expected vs actual.
6. User inspects tool calls, media evidence, and trace-like events.
7. User exports or prints a report.

## API-Confirmed Objects

| Object | Confirmed Source | Notes |
|---|---|---|
| Account/session | `init` | Returns `features`, `tenant`, `user`, `notes`; values are redacted in fixtures. |
| Dataset | `list_datasets`, `get_dataset` | Carries `dataset_source`, `dataset_type`, generated scenario/storyboard source, and media/action tags. |
| Request | `list_requests`, `get_request` | Tracks generation jobs with `request_status`, timing, accepted inputs, and generation options. |
| Run | `list_runs`, `get_run` | Carries `result`; current detail sample uses `result.cases[]`. |
| Case/Test | `run.result.cases[]` or historical `run.result.tests[]` | A3 mapper supports both. |
| Expected vs Actual | `grade.expected`, `grade.actual`, action/tool comparisons | A3 maps to existing Expected vs Actual and Tool Call Diff panels. |
| Score / Pass-Fail | `grade.score`, `grade.passed`, aggregate metrics | A3 score-source policy already prefers explicit grade score. |
| Failure evidence | failed `run.result.cases[].grade.metrics` and `grade.reason` | Current real failed run does not expose a named backend `failure_class`; A3 derives the class. |
| Media Evidence | dataset action fields, request media flags, case metadata | Signed URL field name confirmed as `signed_url` in dataset source. |
| Observability Trace | feature-gated API | Current account has observability disabled, so A3 local trace timeline remains necessary. |

## Frontend Behavior A3 Should Copy

- Make objects visible at top level: requests, datasets, runs, usage, reports.
- Treat dataset/run/case as navigation hierarchy.
- Keep expected vs actual near evidence, not hidden inside raw JSON.
- Treat media files and VM stream evidence as case-level proof.
- Show request/dataset/run provenance so reviewers can explain where data came from.
- Keep known gaps visible instead of silently omitting unavailable platform fields.
- Use empty states deliberately. Real Ashr says when there are no datasets, no agents, no folders, or not enough analytics data; A3 should also explain missing data instead of showing blank panels.
- Treat analytics as a summary layer: run volume, pass rate over time, runs by agent, and pass rate by agent are real frontend concepts.
- Treat Trust as a downstream report/certification concept, not as the first MVP build target.

## Frontend Behavior A3 Should Avoid For MVP

- Account management and API key management.
- Full billing/plan/upgrade flows.
- Mutating generation requests from the dashboard.
- Production observability trace search when the account feature is unavailable.
- Direct signed URL rendering until redaction and permission rules are clear.
- Full dataset-request wizard. The real `New dataset` flow has 8 steps: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, and Review. A3 only needs to display the resulting dataset/run provenance.

## 2026-07-06 Authenticated Observation Status

Direct logged-in frontend observation is now complete for the top-level Lab navigation through an isolated Chrome profile and local CDP connection.

Confirmed pages:

- `?tab=analysis`: Datasets list, search, filters, sort/group, `New dataset`.
- `?tab=agents`: Agents list empty state.
- `?tab=folders`: Folders list, search, `New folder`, empty state.
- `?tab=analytics`: summary counters and charts for run volume/pass rate/agent performance.
- `?tab=usage`: Images, Audio, Files quota counters plus refresh/upgrade.
- `?tab=trust`: public certificate/trust-page preview with frozen metrics language.
- `?tab=api-keys`: API key management instructions; no key values were read or saved.
- `?tab=team`: team member management view; account-specific values were not saved.
- Settings menu: Theme and Low Power.
- New Dataset modal: 8-step request wizard opened and closed without submitting.

Still not directly observed in frontend:

- Populated dataset detail.
- Populated run detail.
- Case detail with expected vs actual.
- Trace/tool-call timeline.
- Native frontend failure-class display.

Reason: the observed account had no UI-visible datasets/runs to open. API samples still provide the current evidence for those deeper fields.

Additional 2026-07-06 API note:

- A read-only API probe found a real failed run with three failed cases.
- The failed run confirmed backend grade fields, pass/fail, score, reason, and metrics.
- The same failed run did not expose a native `failure_class`, so A3's derived failure clusters remain the right MVP behavior.
- The frontend still showed 0 UI-visible datasets/graded runs, so populated frontend detail pages remain unobserved.

Additional 2026-07-06 media/usage note:

- Usage page calls `get_usage` and `billing_get_status`.
- Direct API-key calls to both functions returned 403 OAuth-only messages.
- A3 now displays Usage / Quota as frontend-confirmed product logic, while clearly marking direct API-key access as blocked.

## 2026-07-06 Agent/Dataset Generation Workflow

The authenticated Chrome/CDP crawl confirmed that Ashr's official frontend does not start from an A3-style run triage table alone. It also has an upstream dataset generation workflow:

```text
New Dataset wizard
  -> Basic Info
  -> Agent
  -> Inputs
  -> Tools
  -> Context
  -> Test Config
  -> Behaviors
  -> Review
  -> Generate Test Suite
```

This means the official product has two layers:

1. Generation layer: define what should be tested.
2. Triage/report layer: inspect what happened after runs exist.

A3 should not rebuild the full generation layer for the student MVP. However, A3 should copy the provenance idea: every report should make it easy to answer "what agent, what input channels, what tools, what context, what rules, and what generation settings produced this result?"

### Prepared Demo Draft

The crawl prepared a minimal demo draft in the official wizard and stopped at the final Review step:

- Dataset: `A3 Refund Demo Dataset`
- Agent: `A3 Refund Demo Agent`
- Domain: `e-commerce`
- Accepted inputs: `text`, `audio`, `file`, `image`
- Tool: `confirm_cancel(booking_id: string)`
- Coverage: happy path, edge cases, error handling, multi-turn, multi-input
- Behavior rule: refund completion must be confirmed through the correct tool call

The final `Generate Test Suite` action was not clicked because it creates real hosted Ashr data. If the user explicitly confirms that action, the next goal is to observe whether the generated dataset appears in the UI and whether it can produce a populated run/case detail with expected vs actual, tool calls, pass/fail, and media evidence.

### A3 Copy Guidance

- Copy the Review step as a model for A3's Report Center and audit export.
- Copy accepted input channels into A3's Media Readiness panel.
- Copy tool definitions into A3's Tool Call Diff and expected-vs-actual panels.
- Copy behavior constraints into A3's judge/rubric explanation.
- Keep cloud generation itself outside the A3 MVP; A3 should mainly consume generated run/case evidence.

## 2026-07-06 Post-Generation Workflow Result

After explicit user confirmation, the official Review step was submitted. Ashr generated a frontend-visible dataset:

```text
Generate Test Suite
  -> Datasets list
  -> A3 Refund Demo Dataset
  -> Test cases (5)
  -> Results (0)
```

What this proves:

- The official frontend can generate a dataset/test-suite object from the 8-step wizard.
- Generated cases are visible in the dataset side panel.
- A case detail route uses `dataset=<id>&run=<generated_case_key>`.
- Case details are visible before execution and include scenario description, case key, tags, action count, and action/media types.

What it does not prove yet:

- It does not yet provide official run results.
- `Results (0)` means no official score/pass-fail/failure-reason/actual-tool-call trace is visible.
- `Agents` still shows no standalone agent list entry, so the wizard agent currently behaves as dataset provenance rather than a top-level agent object.

Updated A3 workflow interpretation:

```text
Official Ashr generation layer:
Request/Wizard -> Dataset -> Test Case definitions

Official Ashr result layer:
Run execution -> Results -> Case result -> Trace / tool calls / score

A3 MVP:
Display Dataset/Run/Case evidence and reports; do not rebuild the full wizard.
```

The new generated dataset is enough for A3 to copy official dataset/case browsing. A completed run is still required for frontend parity on pass/fail, expected-vs-actual actuals, traces, and failure-class display.

## 2026-07-06 Post-Run API Result

After the dataset was generated, A3 created one hosted run result for the same five official refund cases.

```text
A3 Refund Demo Dataset
  -> dataset id 884
  -> hosted run id 11925
  -> 5 cases
  -> 2 pass / 3 fail
  -> mapped into A3 dashboard source p3-official-demo
```

What this proves:

- A3 now has a complete demo path from official generated dataset to hosted run result to local dashboard triage.
- The API sample confirms pass/fail, score, expected vs actual, tool calls, trace-like observations, and media evidence.
- The A3 dashboard can display the official demo without calling the real API at page load.
- The media path is stronger than before because dataset action media types are joined into each mapped case.

What still needs direct frontend observation:

- Official Results page that lists run `11925`.
- Official run detail page for a UI-visible result.
- Official native trace/timeline UI.
- Whether official frontend shows a named backend failure class, or only score/reason/metrics.

Current MVP decision:

- A3 should keep the local read-only dashboard/report flow as the main deliverable.
- A3 can honestly claim it mirrors the official product's dataset -> run -> case -> evidence workflow.
- A3 should not claim that the official populated Results UI has been fully copied until a fresh logged-in frontend pass confirms it.

## 2026-07-06 Authenticated Dataset / Case UI Follow-up

The logged-in official frontend was observed again through normal Chrome/CDP.

Updated official workflow:

```text
Dataset overview
  -> Test cases (5)
  -> Case detail
  -> Open Most Recent Run
  -> Runs History / No runs found
```

Confirmed official case-browser fields:

- case ordinal
- title
- case key
- description
- action count
- tag count

Confirmed official case-detail fields:

- `TEST DETAILS`
- tags
- `ACTIONS`
- actor (`User`, `Agent`)
- action title/name
- content
- media/input type labels (`TEXT`, `AUDIO`)
- `Tool Calls`
- `Back to Tests`
- `Open Most Recent Run`

Updated interpretation:

- A3 should copy the official dataset -> test cases -> case detail browsing flow.
- A3 already goes beyond the official visible page for this demo by showing local pass/fail, score, expected-vs-actual result, trace-like events, and failure clusters from API run `11925`.
- Official Results parity is blocked because the frontend shows `Results (0)` for dataset `884` even though API run `11925` is retrievable.

## 2026-07-07 Run 11926 Workflow Update

A3 tried a second result path that better matches official frontend expectations:

```text
Dataset 884
  -> create_run with result.tests[]
  -> run 11926
  -> list_runs(summary_only=true) includes 11926
  -> A3 p3-official-demo dashboard renders 11926
```

Updated interpretation:

- A3 now has a run result shaped like the official Results API model, not only the local clone `cases[]` model.
- Local A3 dashboard can show run `11926` with pass/fail, score, expected-vs-actual, tool-call comparison, media evidence, failure clusters, and report export.
- Official visual Results parity is still not fully confirmed because the in-app browser was logged out; a logged-in browser refresh is needed to see whether Results lists run `11926`.
