# P3 Official Code Crawl Parity Growth

## Goal

Use the official Ashr frontend mirror as a clean-room product reference, then convert code-level page/module signals into A3-owned dashboard, report, and test coverage.

This does not copy official source code. It only records redacted structure: chunk names, keyword counts, page roles, A3 decisions, and A1/A2 dependencies.

## Added Capability

- Added redacted fixture:
  - `fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json`
- Added report summary:
  - `summarizeOfficialCodeCrawlParity()`
- Added JSON export field:
  - `official_code_crawl_parity`
- Added Markdown report section:
  - `Official Code Crawl Parity`
- Added dashboard panel:
  - `Official Code Crawl`
- Added print/PDF report section:
  - `Official Code Crawl Parity`
- Added report-builder and dashboard-wiring tests.

## What Was Observed

The clean-room crawl summarized official Lab chunks such as:

- `CreateRequestModal-LwtjGDgm.js`
- `index-DSO2XOq6.js`
- `ObservabilityPage-BmNyibq8.js`
- `DatasetsPage-C6F1zCF4.js`
- `AnalyticsPage-3IidZ_zD.js`
- `UsagePage-CoD18uzD.js`
- `TrustPage-DH1i4mLu.js`
- `ApiKeysPage-DcsMtTi4.js`
- `TeamPage-zKnEHkxH.js`

The strongest A3 copy signals are:

- results review
- expected vs actual
- score
- tool calls
- trace / observability
- media metadata
- run history
- trust / audit
- read-only usage

The strongest out-of-scope signals are:

- API key creation / reveal / revoke
- team invite and account admin
- billing checkout and portal mutation
- cloud-side destructive mutations

## A1/A2 Calibration

This feature is not a standalone UI shell. It maps official frontend concepts back to upstream evidence:

- Results review depends on A1 run/case/trace and A2 score/pass/fail/failure class.
- Trace observability depends on A1 trace/tool-call evidence and A2 judge remediation.
- Media evidence depends on A1 media metadata and A2 media failure taxonomy.
- Trust/audit depends on A1/A2 evidence packaged by A3 audit bundle and verifier.

## Safety

- No official source code is committed.
- No raw source excerpts are committed.
- No API key, cookie, token, account data, email, or signed URL is committed.
- The fixture records only module names, keyword counts, and A3 decisions.

## Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
46 tests
46 pass
0 fail
```

## Commercial Meaning

This makes A3 more commercially credible because it can now say:

> We are not guessing the product workflow. We mapped the official frontend structure, kept the legal/security boundary clean, and used that evidence to prioritize A3-owned release intelligence.

The most valuable copy targets remain:

- results review
- incident replay
- reviewer workflow
- trace observability
- audit/report export
- read-only usage and trust shell
