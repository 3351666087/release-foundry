# P3 A3 MVP Recommendations

## Must Build

1. Run List
   - Show run id, dataset id, status, pass/fail counts, score summary, and source.
   - Reason: real Ashr exposes runs as the main execution object.

2. Case Detail
   - Show selected case id, scenario title, pass/fail, score, severity, and failure summary.
   - Reason: triage happens at the individual case level.

3. Expected vs Actual
   - Show expected response/tool calls beside actual response/tool calls.
   - Reason: this is one of the clearest real Ashr product concepts and the easiest for reviewers to understand.

4. Tool Call Diff
   - Highlight missing tools, wrong tools, wrong arguments, and wrong order.
   - Reason: many agent failures are trace/tool-use failures, not just bad final text.

5. Failure Clusters and Triage Queue
   - Group failed cases by normalized failure class and prioritize severe/low-score cases.
   - Reason: this turns raw evaluation output into actionable debugging work.

6. Report Export
   - Keep JSON, CSV, Markdown, and print/PDF report flows.
   - Reason: student teams need evidence they can hand to instructors/reviewers.

## Should Build If Time Allows

- Dataset detail summary using `dataset_source.runs.*` and `intent_tags`.
- Signed media URL awareness, but only as redacted metadata until per-media access rules are clear.
- Usage/quota panel if a stable API source is found.
- Analytics summary inspired by the real Lab UI: run volume, pass rate, runs by agent, and pass rate by agent.

## Do Not Build For MVP

- Account settings.
- Billing/plan upgrade.
- API key management.
- Hosted mutation flows that create real requests/runs.
- The full 8-step New Dataset wizard.
- Team management.
- Public Trust/certificate publishing.
- Full observability trace product.
- Raw private content viewer.

## What Current A3 Already Covers

- Product console shell.
- Runs and cases.
- Expected vs Actual.
- Tool Call Diff.
- Failure clusters.
- Triage queue.
- Media Evidence panel.
- Report Center and print-ready report.
- A2 coverage health.
- Generated fixture path from merged A2 outputs.
- P3 mapper for real/redacted Ashr run shapes.
- Request Provenance panel from real/redacted Ashr request fields.

## Best Next 3

1. Visually refresh the logged-in official Results page for dataset `884` and confirm whether run `11926` appears; API `summary_only` evidence already lists it.
2. Keep backend failure class derived unless a future Ashr sample exposes a named native `failure_class`; the current real failed run and official demo run do not.
3. Confirm signed media URL behavior for audio, image, and video before rendering live media links; current evidence only confirms file-like `signed_url` fields.

## 2026-07-06 Update

A3 now has a stronger MVP demo source:

- Official generated dataset: `884`
- Hosted run result: `11926`
- Dashboard source: `P3 Official Demo 884/11926`
- Local URL: `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`

This means the MVP can demonstrate the full student-facing workflow:

```text
official generated dataset
  -> hosted run result
  -> A3 run list
  -> case detail
  -> expected vs actual
  -> tool-call diff
  -> failure cluster
  -> media readiness
  -> report export
```

The remaining work is no longer "create a real example"; that part exists. A3 now has both a local-clone-shaped run `11925` and an official-UI-shaped run `11926`. The remaining work is product calibration: visually confirm whether the official frontend Results tab lists run `11926`, which already appears in the frontend-style `list_runs(summary_only=true)` API response.

## 2026-07-07 Update

A3 upgraded the official demo source from run `11925` to run `11926`.

Why:

- `11925` used `result.cases[]`, which A3 can display but the official frontend may not use for Results.
- `11926` uses `result.tests[].action_results[]`, matching the official frontend's expected run-result shape.

Current demo facts:

- Dataset `884`
- Run `11926`
- 5 refund tests/cases
- 2 pass
- 3 fail
- 40% pass rate
- 56.4 average score
- 5 media-evidence cases
- local screenshot: `docs/screenshots/a3-dashboard-official-demo-884-11926.png`

## 2026-07-06 Authenticated UI Check

Direct Lab navigation is now confirmed through isolated Chrome/CDP observation. The real product's top-level console is:

- Datasets
- Agents
- Folders
- Analytics
- Usage
- Trust
- API Keys
- Team

For a student A3 MVP, only Datasets/Runs/Analytics-style triage/reporting concepts should be copied. API Keys, Team, Trust publishing, billing/upgrade, and full dataset generation are useful product context but outside the small MVP boundary.
