# A3 Acceptance Checklist

## G2.3 Dashboard Skeleton

- [x] `apps/dashboard` exists.
- [x] Dashboard can load local fixture JSON.
- [x] Dashboard shows summary metrics.
- [x] Dashboard shows Run List.
- [x] Dashboard shows Case Detail.
- [x] Dashboard shows Expected vs Actual.
- [x] Dashboard shows Trace Timeline.
- [x] Dashboard shows Failure Clusters.
- [x] Dashboard exposes JSON/CSV/Markdown export actions.
- [x] Dashboard exposes 6 filters: status, family, failure class, run, severity, score band.
- [x] Dashboard shows per-judge drilldown for selected cases.
- [x] `services/report` contains shared report/normalization logic.
- [x] `tests/a3` verifies summary, clustering, and export shapes.
- [x] `tests/a3` verifies filter options and filter behavior.
- [x] Browser screenshot evidence captured under `docs/screenshots`.

## G2 Contract Safety

- [x] No real Ashr API calls.
- [x] No real keys or secrets.
- [x] A1 runner logic not modified.
- [x] A2 judge semantics not modified.
- [x] A1/A2 draft PR branches not merged.
- [x] A3 mock fixtures cite A1/A2 PR source paths.

## P3 Ashr Calibration

- [x] Confirmed `.env.local` exists and is ignored.
- [x] Did not print, document, or commit the Ashr key.
- [x] Ran minimal read-only Ashr SDK smoke test.
- [x] Confirmed `init()` and `health_check()` succeed.
- [x] Confirmed `list_datasets()`, `list_runs()`, and `list_requests()` return usable field shapes.
- [x] Saved sanitized fixtures under `fixtures/a3/p3`.
- [x] Documented P3 plan in `docs/a3/p3_ashr_calibration_plan.md`.
- [x] Documented field mapping in `docs/a3/p3_field_mapping.md`.
- [x] Documented worklog and evidence in `docs/a3/p3_worklog.md`.
- [x] Added small P3 mapper in `services/report/p3_ashr_mapper.mjs`.
- [x] Added mapper tests in `tests/a3/p3_ashr_mapper.test.mjs`.
- [x] Confirmed existing A3 report builder tests still pass.
- [x] Confirmed new P3 mapper tests pass.
- [ ] Verify native backend failure-class field with a real failing run.
- [ ] Decide score source: `semantic_similarity` vs a later server grade field.
- [ ] Join dataset scenario titles into mapped A3 cases.

## Next Acceptance Targets

- [ ] Replace A3 mock fixtures with generated fixtures from merged A1/A2 outputs.
- [x] Add case-level judge drilldown.
- [x] Add severity and score-band filters.
- [ ] Add judge-mode filter after A2 exposes more varied judge-mode cases.
- [x] Expand from current 4 screenshots to 10 demo screenshots.
