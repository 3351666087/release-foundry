# P3 API Calibration Import Error Shapes - 2026-07-07

## Purpose

This artifact records the local A3 import validation and error-response shapes for the API-backed dashboard slice. It uses only local code inspection and already committed redacted P3 fixtures. No real ReleaseFoundry, GitHub, billing, usage, or browser API call was made for this pass.

The goal is to give A3 a reviewer-safe contract for importing A1 run results and A2 grade results while mapping the work back to official ReleaseFoundry calibration gaps that remain unresolved without secrets.

## Request Type

Local A3 import endpoints under inspection:

| Local request | Body envelope | Source default | Mutates real ReleaseFoundry |
|---|---|---|---|
| `POST /api/a3/import/a1-run-result` | `{ "source": "api-ingest", "run_result": { "runs": [...] } }` or a direct A1-like run result | `api-ingest` | No |
| `POST /api/a3/import/a2-grade-result` | `{ "source": "api-ingest", "grade_result": { "case_id": "...", "passed": false, "score": 0.31 } }` or a direct A2-like grade result | `api-ingest` | No |

The request shapes are local compatibility adapters. They are not official ReleaseFoundry mutation calls. They are designed to accept A1 `RunResult`, A2 grade output, and later official API-shaped run payloads after redaction and review.

## Response Fields

Successful local imports return `201` with receipt-style JSON. The current local happy-path fields are:

| Field | Meaning |
|---|---|
| `schema_version` | `a3.a1_run_result_ingest.v1` or `a3.a2_grade_result_ingest.v1` |
| `source` | Normalized source key, usually `api-ingest` for local import tests |
| `source_label` | Human-readable label, defaulting to `API Ingest` |
| `storage_mode` | Local store mode such as `memory` or fixture-backed mode |
| `db_ready` | Boolean marker that the response is shaped for future DB-backed storage |
| `imported_run_count` | Count of imported or currently joined run records |
| `imported_grade_count` | Count of imported or currently joined grade records |
| `dashboard_case_count` | Number of normalized cases visible to the dashboard after import |
| `summary` | A3 dashboard summary generated from normalized local evidence |
| `a1_a2_join_ready` | True when imported run and grade evidence can be joined for case review |

Official ReleaseFoundry calibration mapping:

| Official gap | Local A3 evidence response |
|---|---|
| API returns populated datasets/runs while frontend may show empty state | Import receipts let A3 preserve populated local evidence without depending on Lab visual state |
| Official run shapes vary between `result.cases[]` and `result.tests[].action_results[]` | Receipt counts and dashboard case counts make mapper/import regressions visible |
| No confirmed native `failure_class` field in failed-run samples | A3 keeps grade/judge fields explicit and derives failure classes locally |
| Future SaaS migration needs durable import accounting | Counts, source, storage mode, and schema version become the first DB-ready contract |

## Error Fields

The local API already returns an `a3.api_error.v1` envelope for route misses and thrown failures. The validation work should keep that base shape and add field-level detail for import failures.

Recommended import-validation error envelope:

```json
{
  "schema_version": "a3.api_error.v1",
  "error": "validation_error",
  "message": "A1 import requires run_result.runs[] or a direct run with cases[].",
  "request_type": "a1_run_result_import",
  "fields": [
    {
      "path": "run_result.runs",
      "code": "missing_required_field",
      "expected": "array"
    }
  ],
  "retryable": false,
  "status_code": 400
}
```

Required local validation cases:

| Case | Expected status | Expected `error` | Field signal |
|---|---:|---|---|
| Malformed JSON body | 400 | `invalid_json` | `message` only, no raw body echo |
| Missing A1 run records | 400 | `validation_error` | `run_result.runs` or `cases` |
| Missing A2 `case_id` | 400 | `validation_error` | `grade_result.case_id` |
| Unsupported import source key | 400 | `validation_error` | `source` |
| Unknown route | 404 | `not_found` | `kind`, `id` |
| Unexpected local exception | 500 | `internal_error` | sanitized `message` only |

The error response must not echo request headers, cookies, API keys, raw signed URLs, account emails, or unredacted payload text.

## Quota/Cost

This pass has zero live API cost:

| Activity | Count |
|---|---:|
| Real ReleaseFoundry API calls | 0 |
| Real GitHub API calls | 0 |
| Real billing or usage calls | 0 |
| Local file reads | Local repo only |
| App/service file edits | 0 |

The official Usage page and redacted P3 probes already show that Usage/Quota exists as a product surface, while direct API-key calls to `get_usage` and `billing_get_status` are OAuth-gated with `403` responses. A3 should therefore keep import validation local and cost-free until the next authorized calibration round.

## Private Evidence Path

No private evidence file was read or required for this artifact.

Reserved private-only path for a future authorized live validation run:

```text
docs/evidence/private_refs/a3_api_calibration_import_error_shapes_2026_07_07.local.md
```

That future file, if created outside the committed artifact set, should contain only command names, timestamps, local status codes, fixture hashes, and redaction decisions. It must not contain `.env.local` values, API keys, cookies, Authorization headers, raw signed media URLs, account emails, tenant identifiers, or raw private payloads.

## Redacted Summary

Evidence used:

| Evidence | Use |
|---|---|
| `tests/a3/a3_api_server.test.mjs` | Confirms local A1/A2 happy-path imports and receipt fields |
| `services/report/a3_api_server.mjs` | Confirms local routes and `a3.api_error.v1` base envelope |
| `services/report/a3_store.mjs` | Confirms import receipts, counts, source labels, and join readiness |
| `docs/a3/p3_api_frontend_visibility_gap.md` | Maps API-populated objects versus frontend visibility gap |
| `docs/a3/p3_field_mapping.md` | Maps official run, request, grade, score, and failure-like fields |
| `docs/a3/p3_media_calibration.md` | Maps usage/quota OAuth-gated gap and media evidence safety |
| `fixtures/a3/p3/*.redacted.json` | Confirms existing samples are redacted and fixture-backed |

Redaction posture:

- No live credentials were read.
- No `.env.local` content was opened.
- No raw headers, cookies, account identifiers, or signed URL values are included.
- Official gaps are described by field names, status codes, redacted fixture paths, and local contracts only.

## Next API Calibration

The next local-only step is to add import validation tests around malformed JSON, missing A1 run records, missing A2 `case_id`, unsupported source keys, and sanitized 400 envelopes.

The next authorized official ReleaseFoundry calibration, if approved later, should remain read-only unless explicitly scoped. It should verify whether official importable run detail still appears as `result.cases[]`, `result.tests[].action_results[]`, or both, and whether any native backend failure-class field appears. Results should be committed only as redacted summaries and fixture hashes.
