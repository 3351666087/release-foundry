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

## Contract Safety

- [x] No real Ashr API calls.
- [x] No real keys or secrets.
- [x] A1 runner logic not modified.
- [x] A2 judge semantics not modified.
- [x] A1/A2 draft PR branches not merged.
- [x] A3 mock fixtures cite A1/A2 PR source paths.

## Next Acceptance Targets

- [ ] Replace A3 mock fixtures with generated fixtures from merged A1/A2 outputs.
- [x] Add case-level judge drilldown.
- [x] Add severity and score-band filters.
- [ ] Add judge-mode filter after A2 exposes more varied judge-mode cases.
- [x] Expand from current 4 screenshots to 10 demo screenshots.
