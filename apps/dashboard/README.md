# A3 Dashboard Skeleton

Static dashboard for A3 Dashboard & Triage.

## Local preview

From the repository root:

```bash
python -m http.server 5173
```

Then open:

```text
http://127.0.0.1:5173/apps/dashboard/index.html
```

The dashboard reads:

- `fixtures/a3/mock_run_results.json`
- `fixtures/a3/mock_grade_results.json`
- `services/report/report_builder.mjs`

## Current scope

- Run List
- Case Detail
- Trace Timeline
- Expected vs Actual
- Failure Clusters
- JSON/CSV/Markdown report export

This is G2 local-only work. It does not call the real Ashr API and does not require secrets.
