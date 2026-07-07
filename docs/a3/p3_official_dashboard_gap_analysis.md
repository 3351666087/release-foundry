# P3 Official Ashr Dashboard Gap Analysis

## Purpose

This document compares the current A3 Dashboard / Triage / Report console with the real Ashr Lab product structure observed during P3 calibration.

The goal is not to clone account administration or hosted cloud operations. The useful MVP target is a local, read-only product console that helps a student team inspect agent evaluation failures and export evidence.

## Current A3 Coverage vs Official Ashr

| Official Ashr area | Current A3 state | Decision |
|---|---|---|
| Datasets | Partial. A3 shows dataset identity, source titles, run linkage, and request provenance when fixtures provide it. | Copy the dataset/run mental model, not the full dataset generator. |
| Runs | Covered. A3 has Run List and normalized run/case data. | Keep. This is central to A3. |
| Case detail | Covered locally. A3 shows selected case status, score, expected vs actual, judge evidence, tool-call diff, media evidence, and trace timeline. | Keep. This is the main triage workflow. |
| Expected vs actual | Covered. A3 compares expected response/tool calls against actual output/tool calls. | Keep. This is one of the clearest demo features. |
| Tool calls | Covered. A3 highlights missing, extra, wrong, reordered, and argument-level mismatches. | Keep. This is high-value debugging evidence. |
| Analytics | Partial. A3 has pass rate, average score, coverage health, failure clusters, and triage priority. | Keep local summary analytics; skip account-level charts for MVP. |
| Usage / quota | Partial. Real frontend shows Images, Audio, and Files quota modules; direct API-key probes were OAuth-gated. | Show read-only known-gap/calibration state; do not enforce quota. |
| Media evidence | Partial. A3 preserves redacted media metadata and VM stream evidence. | Keep metadata display; do not render live signed URLs yet. |
| Reports / exports | Covered for MVP. A3 exports JSON, CSV, Markdown, and print/PDF-ready report preview. | Keep. This replaces official public Trust publishing for student demo use. |
| Trust / public certificate | Not copied. Official product has a public trust/certificate concept. | Use only as inspiration for reports; public hosting is out of scope. |
| Agents | Metadata only. A3 uses runner/agent identity as a label/filter. | Do not build a full agent registry yet. |
| Folders | Not needed. | Skip for MVP. |
| API Keys | Not copied. | Do not build secret/key management. |
| Team | Not copied. | Do not build invites or account administration. |
| Login / OAuth | Not copied. | Do not implement auth for A3 MVP. |
| Billing / upgrade | Not copied. | Out of scope. |

## Improvement Added In This Round

A3 now has an Official Ashr Gap map:

- Dashboard panel: `Official Ashr Gap`
- Print/PDF report section: `Official Ashr Gap`
- JSON report field: `official_ashr_gap`
- Markdown report section: `Official Ashr Gap`

This gives reviewers a direct answer to:

- what A3 already copied from the official product
- what A3 only partially copied
- what is blocked by missing UI-visible hosted runs
- what is intentionally out of scope for the student MVP

## 2026-07-06 Official Demo Update

A3 now has one official-demo-backed data source, not only generic mock data:

- Official generated dataset: `884`
- Hosted run: `11925`
- A3 dashboard source: `P3 Official Demo 884/11925`
- Local URL: `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`
- Redacted relogin evidence: `fixtures/a3/p3/ashr_dataset_884_frontend_relogin_needed.redacted.json`
- Redacted authenticated frontend observation: `fixtures/a3/p3/ashr_dataset_884_official_frontend_observation.redacted.json`

This changes the remaining gap:

- Old gap: get or create one real hosted run.
- Current gap: official frontend Results does not list API-created run `11925`; it shows `Results (0)` and `No runs found`.

A3 can already demonstrate the run/case/evidence/report workflow locally from redacted official-demo evidence. It should not claim full official Results-page parity because the official frontend currently exposes only dataset/case browsing for this demo, not API-run result browsing.

## 2026-07-07 Official UI-Compatible Run Update

A3 now has a stronger official-demo-backed source:

- Official generated dataset: `884`
- Official UI-shaped hosted run: `11926`
- Result structure: `result.tests[].action_results[]`
- A3 dashboard source: `P3 Official Demo 884/11926`
- Local URL: `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`
- Local dashboard screenshot: `docs/screenshots/a3-dashboard-official-demo-884-11926.png`

Why this matters:

- The old run `11925` proved that Ashr can store an A1-like `result.cases[]` object.
- The new run `11926` proves that Ashr can store and return the official-style `result.tests[]` object.
- `list_runs(dataset_id=884, summary_only=true)` returns `11926`, matching the list-runs style observed in the official frontend bundle.

Updated gap:

- Old gap: API run exists but official frontend does not list it.
- Current gap: API run `11926` exists in frontend-style summary data, but visual Results-page confirmation still needs a logged-in browser pass.

## Why This Is The Right MVP Direction

The official Ashr product is a cloud SaaS console. It includes account, team, billing, API key, usage, trust, and dataset-generation flows.

A3 should not recreate all of that. The student MVP should focus on the highest-value evaluation loop:

1. load run/case data
2. see which cases passed or failed
3. compare expected vs actual
4. inspect trace and tool-call evidence
5. group failures
6. export a report

That is the part of the real product that directly helps users understand agent behavior.

## Remaining Official Gaps

| Gap | Why it remains | Next step |
|---|---|---|
| Official populated run detail UI | Hosted run `11926` exists with `result.tests[]` and appears in `summary_only` list-runs API evidence, but visual Results-page confirmation was blocked because the in-app browser was logged out. | Refresh `https://lab.ashr.io/?tab=analysis&dataset=884` in a logged-in Ashr browser and confirm whether Results lists run `11926`. |
| Native backend failure class | Real failed-run sample exposed status, grade, score, reason, and metrics, but no named `failure_class`. | Keep A3-derived failure clusters until a future sample proves a native field. |
| Live signed media rendering | Signed URL evidence is still incomplete for audio/image/video, and live URLs are sensitive. | Keep redacted metadata only until access/redaction rules are clear. |
| Real quota counters through API key | Usage/quota functions were observed in frontend, but API-key probes returned OAuth-only 403 responses. | Treat usage/quota as frontend-confirmed but API-key-gated. |

## Safety Boundary

A3 still must not:

- submit or store real API keys
- save browser cookies, tokens, headers, account email, or raw signed URLs
- create, delete, publish, invite, or mutate real Ashr cloud objects without approval
- implement real API key management, team management, billing, or OAuth login

## Short Team Explanation

We compared our A3 dashboard with the official Ashr Lab product. Our A3 already covers the core evaluation workflow: runs, cases, expected vs actual, trace timeline, tool-call diff, failure clusters, media evidence, and report export.

The main difference is that official Ashr is also a full cloud console with Datasets, Agents, Folders, Analytics, Usage, Trust, API Keys, and Team pages. We should copy the navigation and evaluation-review ideas, but not copy account/security/billing/team features for the MVP.

This round added an Official Ashr Gap panel and export/report section so the dashboard itself clearly explains what is copied, partial, blocked, or out of scope.
