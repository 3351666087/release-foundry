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
- `fixtures/a2/results/a2_g3_coverage_report.json` when available
- `services/report/report_builder.mjs`

## Current scope

- Run List
- Case Detail
- Trace Timeline
- Expected vs Actual
- Failure Clusters
- JSON/CSV/Markdown report export
- A2 coverage evidence in JSON/Markdown exports

This is G2 local-only work. It does not call the real ReleaseFoundry API and does not require secrets.

## API-backed preview

The SaaS slice can also serve the same dashboard data through the local A3 API.

Terminal 1:

```bash
node services/report/a3_api_server.mjs 4183
```

Terminal 2:

```bash
python -m http.server 5173
```

Then open:

```text
http://127.0.0.1:5173/apps/dashboard/index.html?source=api-mock&apiBase=http://127.0.0.1:4183
```

This path is still local and redacted. It demonstrates `static -> API-backed`, while the store contract keeps the next DB adapter compatible with the same dashboard payload.
