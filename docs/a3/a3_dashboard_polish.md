# A3 Dashboard Polish

## Purpose

This pass moves A3 from a demo dashboard toward a product-console workflow. The dashboard still stays local-only and fixture-driven, but it now gives reviewers faster answers to three operational questions:

1. Is the scenario and failure-class coverage healthy enough to trust the report?
2. Which failed cases should be triaged first?
3. What evidence is included when the report is exported?

## Added Console Areas

### Coverage Health

Uses the optional A2 coverage fixture through `summarizeCoverage()` and surfaces:

- scenario count
- executable case count
- rubric class count
- failure class count
- assignment minimum health
- top coverage warnings when present

This helps A3 show whether the underlying A2 scenario pack is broad enough for product-facing evidence.

### Triage Queue

Ranks failed cases from the active filtered case set. The queue prioritizes severity first, then lower score. Selecting a queue row opens the same Case Detail, Expected vs Actual, Tool Call Diff, Media Evidence, and Trace Timeline views.

This turns failure clusters into a practical "fix this first" workflow.

For redacted P3 samples where multiple cases can share the same displayed case ID, the P3 mapper now assigns stable fallback IDs such as `case_id__2` and records the original value in metadata. This keeps dashboard selection and triage highlighting deterministic.

### Report Center

Summarizes what the current export contains and mirrors the existing export actions:

- JSON: machine-readable case, coverage, tool-call diff, and media evidence payload
- CSV: spreadsheet-friendly triage list
- Markdown: human-readable handoff report
- Print/PDF: browser-printable executive report preview

The topbar export buttons and Report Center buttons share one export handler.

### Request Provenance

Uses the redacted P3 Ashr request fixture through `summarizeRequestProvenance()` and surfaces:

- latest request status
- actual vs estimated duration
- accepted input types
- requested generation outputs
- declared tool count
- test strategy when not redacted
- whether a request failure was recorded

This connects the A3 dashboard back to the upstream Ashr generation/request step without adding any hosted mutation flow.

### Report Preview

Adds a PDF-ready handoff report section inside the dashboard. It summarizes:

- source and run identity
- summary metrics
- A2 coverage health
- failure clusters
- triage queue
- selected case evidence
- linked tool-call diff and judge evidence
- request provenance when a P3 request fixture is loaded

The `Print Report` / `Print/PDF` actions refresh this preview and call browser print. Print CSS hides the interactive dashboard controls and keeps the report content.

## Visual Changes

- Added clearer product-console spacing, panel shadows, and status color accents.
- Added health styling for pass rate, average score, and trace completeness metrics.
- Kept the palette restrained and operational rather than landing-page oriented.
- Preserved the existing static HTML architecture so A3 remains easy to run with a local HTTP server.
- Added print-specific CSS so the report preview can be saved as PDF from the browser.

## Safety

- No real Ashr API calls were added.
- No secrets or keys are read by the dashboard.
- A1 runner logic and A2 judge semantics were not changed.
- The work stays inside A3-owned files.

## Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Latest request-provenance pass:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result: 32 tests passed.

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed Request Provenance rendered status, accepted inputs, generation outputs, tool count, strategy, and failure flag.
- Browser console warnings/errors: none.

Browser smoke checks passed for:

- `http://127.0.0.1:5173/apps/dashboard/index.html`
- `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`
- mobile viewport width 390

Screenshot evidence:

- `docs/screenshots/a3-dashboard-polish-overview.png`
- `docs/screenshots/a3-dashboard-polish-p3-media.png`
- `docs/screenshots/a3-dashboard-polish-mobile.png`
- `docs/screenshots/a3-dashboard-print-report.png`
- `docs/screenshots/a3-dashboard-request-provenance.png`
