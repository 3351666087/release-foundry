# A3 Growth-Auditor Round - Import And Hosted Report Commercialization - 2026-07-07

Role: A3 Growth-Auditor / commercial SaaS auditor.

Scope: documentation artifact only. This round reviewed local repo evidence for A1/A2 API ingest, hosted report sharing, enterprise readiness, SQL/self-host posture, and PR gate/report center commercialization. It does not change runtime code, tests, fixtures, schemas, credentials, or secret-bearing files.

Safety boundary:

- Read local repo evidence only.
- Did not read, print, edit, or rely on `.env.local`.
- Did not call live Ashr, GitHub, billing, hosted auth, database, or external APIs.
- Did not modify code.
- Modified only this artifact, with an optional append-only worklog note in `docs/a3/worklog.md`.

## Auditor Summary

A3 has crossed an important line: it now has API routes for A1 RunResult ingest, A2 GradeResult ingest, an enterprise readiness endpoint, and an HTML hosted report route. The commercial gap is no longer "can A3 show a SaaS-shaped report?" The gap is trustable product behavior around repeated imports, bad payloads, hosted report lifecycle, view audit, SQL durability, self-host operation, and PR/report center buying motions.

Most valuable next round:

1. Make A1/A2 ingest idempotent, validated, and auditable.
2. Add hosted report expiry, revocation, view audit, and share-token separation.
3. Persist import jobs, report snapshots, share links, audit events, usage ledger, and reviewer state in SQL.
4. Promote enterprise readiness from a local report to a release gate input.
5. Turn PR Gate and Report Center into the paid evidence packet workflow.

Commercial one-liner:

> A3 should sell as the release-evidence control plane for agent changes: every PR can import A1/A2 evidence, validate it, gate it, publish a governed hosted report, prove who viewed it, and retain the packet for enterprise audit.

## Current Evidence Base

| Area | Current evidence | Commercial interpretation |
|---|---|---|
| A1 import route | `services/report/a3_api_server.mjs` exposes `POST /api/a3/import/a1-run-result`; `services/report/a3_store.mjs` has `importA1RunResult(...)`; `tests/a3/a3_api_server.test.mjs` covers happy-path ingest. | API-backed A1 ingest exists, but idempotency keys, validation error shapes, payload hash receipts, and duplicate detection are still the sellable gap. |
| A2 import route | `POST /api/a3/import/a2-grade-result`; `importA2GradeResult(...)`; tests join an imported grade to an imported case. | A2 ingest can enrich an imported run, but needs strict grade/case matching, score-scale validation, and partial failure handling before customers trust it. |
| Hosted report HTML | `GET /reports/:reportId` renders via `renderShareableReportHtml(...)`; `buildShareableReportPayload(...)` emits `a3.shareable_report.v1`. | Hosted report viewing exists, but expiry, revocation, access policy, share tokens, and view audit are the enterprise buying layer. |
| Redaction gate | `buildShareableReportPayload(...)` runs `redactExport(...)` and marks blocked reports. | Correct foundation for trust, but hosted publication should fail closed with explicit findings and audit events. |
| Enterprise readiness | `GET /api/a3/enterprise/readiness`; `services/report/a3_enterprise_readiness.mjs`; dashboard wiring checks. | Good enterprise posture model; next step is release gating, SQL-backed readiness evidence, and self-host diagnostics. |
| DB contract | `A3_DB_CONTRACT` lists tenant columns, tables, API surfaces, and guardrails. | Strong contract scaffold; money requires migrations, SQL adapter tests, row scoping, and audit-event immutability. |
| Report Center | Dashboard and report builder expose report center actions and hosted report availability. | Needs buyer-facing packet presets, share-link lifecycle controls, and proof that PR comments/checks link to the same sealed report. |
| PR Gate | Existing PR Gate docs, CLI, GitHub dry-run payloads, waiver/approval validation, and audit bundle docs. | Ready for commercialization if it links every check to import receipts, readiness, hosted report, reviewer board, and bundle verification. |

Known open checklist items in this exact lane:

- Add idempotency keys and validation error shapes to A1/A2 import routes.
- Add view audit event and expiry/revocation policy for hosted reports.

## Growth Points

Each growth point is tagged with at least one of `code`, `test`, `API`, `UI`, `docs`, `evidence` and mapped to direct money value.

| ID | Growth point | Tags | Concrete next build | Money value |
|---|---|---|---|---|
| IH-01 | Add required idempotency keys to A1 ingest. | code, test, API, evidence | Accept `Idempotency-Key` header or `idempotency_key` body, hash it with org/project/source, store it in an `import_jobs` record, and return the original receipt on exact replay. | Prevents duplicate run inflation, protects usage billing, and makes API ingest safe enough for paid CI automation. |
| IH-02 | Add payload hash duplicate detection for A1 ingest. | code, test, API, evidence | Compute `payload_hash` for the redacted canonical A1 RunResult and mark replays as `duplicate_payload` even when clients omit idempotency. | Reduces support tickets from repeated CI uploads and supports metered billing based on unique evidence. |
| IH-03 | Add A1 validation error shape. | code, test, API, docs | Return `a3.api_validation_error.v1` with `field_path`, `code`, `severity`, `message`, `redacted_value_hint`, and `correlation_id`; reject missing `run_id`, malformed `cases`, invalid status, and unsafe raw media URLs. | Converts failed onboarding from "call support" into self-serve integration, increasing trial-to-paid conversion. |
| IH-04 | Add A1 partial import policy. | code, test, API, docs, evidence | Decide whether one bad case rejects the whole run or creates `status=partial_rejected`; include accepted/rejected counts and field paths in the receipt. | Enterprise customers need deterministic ingest semantics before wiring A3 to release pipelines. |
| IH-05 | Add A1 trace/tool-call completeness validation. | code, test, API, evidence | Validate trace event order, case id joins, tool-call ids, and trace completeness; emit blockers for audit replay gaps. | Makes A3 valuable for incident replay and audit discovery, not just pass/fail dashboards. |
| IH-06 | Add required idempotency keys to A2 grade ingest. | code, test, API, evidence | Store A2 import job by org/project/source/idempotency key and payload hash; return stable receipt on retry. | Keeps judge billing and evidence counts stable when CI retries or webhooks redeliver. |
| IH-07 | Add A2 grade-to-case join validation. | code, test, API, evidence | Reject or quarantine grades whose `case_id`/`scenario_id` cannot join to imported A1 cases unless explicitly imported as unattached calibration evidence. | Protects customer trust in release decisions and avoids paid reports with misleading scores. |
| IH-08 | Add A2 score-scale and judge-mode validation. | code, test, API, docs | Validate 0-1 versus 0-100 score scale, required `passed`, allowed judge modes, severity enum, and primary failure class. | Reduces false blockers and false passes, which is the core willingness-to-pay driver for release gates. |
| IH-09 | Add import receipt audit events. | code, test, API, evidence | Emit `import.started`, `import.validated`, `import.duplicate`, `import.rejected`, `import.completed`, and `import.superseded` events with hash chaining. | Creates audit-grade proof for regulated buyers and supports incident investigation invoices. |
| IH-10 | Add import job UI in Report Center. | UI, API, test, evidence | Show latest A1/A2 import jobs, status, accepted counts, rejected counts, duplicate status, payload hash, and "view validation findings." | Turns invisible backend reliability into visible enterprise confidence and shortens sales demos. |
| IH-11 | Add import contract docs with curl-safe examples. | docs, API, evidence | Document A1/A2 routes, idempotency, validation errors, safe sample payloads, and retry semantics without secret values. | Improves developer adoption and lowers integration engineering cost for paid pilots. |
| IH-12 | Add hosted report share-token model separate from report ids. | code, test, API, docs | Create `share_links` with `token_hash`, scope, creator, expiry, revocation, and report snapshot id; keep `/reports/:reportId` internal/authenticated and add `/r/:shareToken` for external sharing. | Makes external customer evidence sharing viable without exposing internal identifiers. |
| IH-13 | Add hosted report expiry enforcement. | code, test, API, UI, evidence | Store `expires_at`; return a controlled expired page and JSON error after expiry; show expiry in Report Center and hosted HTML. | Lets security teams approve customer-facing links and supports premium retention policies. |
| IH-14 | Add hosted report revocation. | code, test, API, UI, evidence | Add `POST /api/a3/share-links/:shareId/revoke`, immediate deny on revoked tokens, and a visible revoked state in Report Center. | Enables enterprise admins to recover from accidental sharing, a common procurement requirement. |
| IH-15 | Add hosted report view audit. | code, test, API, evidence | Emit `report.viewed` with share id, report snapshot id, actor/session class, timestamp, user-agent hash, IP hash, and access result. | Turns hosted reports into compliance artifacts and supports enterprise trust/audit upsell. |
| IH-16 | Add hosted report access-result taxonomy. | code, test, API, docs | Record `allowed`, `expired`, `revoked`, `not_found`, `redaction_blocked`, `scope_denied`, and `auth_required` outcomes. | Gives customer admins clear evidence during security review and reduces ambiguity in incidents. |
| IH-17 | Add hosted report publish gate. | code, test, API, evidence | Block share-link creation when redaction findings remain, required import receipts are missing, or enterprise readiness is below policy threshold. | Sells A3 as a governed release evidence system, not a risky report-sharing toy. |
| IH-18 | Add report snapshot immutability proof. | code, test, API, evidence | Persist `report_snapshots` with builder version, redaction policy version, payload hash, source import ids, and audit bundle root hash. | Supports audit-grade retention and paid security/compliance plans. |
| IH-19 | Add hosted report lifecycle UI. | UI, API, test, evidence | In Report Center show report status, share links, expiry, revoke action plan, last viewed, view count, redaction status, and sealed evidence hash. | Makes Report Center a buyer-facing control panel and gives admins a reason to pay per seat. |
| IH-20 | Add enterprise readiness as a release gate input. | code, test, API, UI, evidence | Feed `a3.enterprise_readiness.v1` into PR Gate/Release Gate with blockers for missing A1 trace, missing A2 grade, missing DB readiness, missing hosted policy, or redaction gaps. | Moves enterprise readiness from nice-to-have dashboard copy into paid release-control value. |
| IH-21 | Add readiness score history. | code, test, API, evidence | Persist readiness snapshots per release/PR/head SHA and show deltas between attempts. | Lets teams prove governance improvement over time, useful for renewals and executive QBRs. |
| IH-22 | Add SQL migrations for core commercial tables. | code, test, API, docs, evidence | Create migrations for `organizations`, `projects`, `runs`, `cases`, `grade_results`, `trace_events`, `import_jobs`, `report_snapshots`, `share_links`, `audit_events`, `usage_ledger`, and `review_items`. | Converts local demo state into a sellable multi-tenant SaaS and self-host product. |
| IH-23 | Add SQL adapter contract tests. | code, test, API, evidence | Run the same store contract tests against memory/file/SQLite/Postgres adapters with seeded A1/A2 imports and hosted reports. | De-risks enterprise deployments and gives buyers confidence that self-host is not vaporware. |
| IH-24 | Add tenant scoping enforcement tests. | code, test, API, evidence | Prove imported runs, grades, reports, share links, and audit events cannot cross organization/project boundaries. | Required for enterprise security review and larger ACV deals. |
| IH-25 | Add self-host readiness health fields. | code, test, API, UI, docs | Extend health/readiness with DB migration version, object storage status, audit log writable, redaction policy version, share-link policy, retention policy, and background worker status. | Makes A3 operable by customer platform teams and unlocks self-host pricing. |
| IH-26 | Add retention and legal-hold policy model. | code, test, API, docs, evidence | Define retention windows for raw imports, normalized rows, traces, media metadata, exports, share links, and audit events; add plan-only purge/legal-hold actions. | Addresses procurement objections around data retention and supports enterprise compliance tiers. |
| IH-27 | Add usage ledger tied to imports and hosted reports. | code, test, API, evidence | Record usage events for imported runs, cases, grade rows, trace events, report snapshots, hosted views, export artifacts, and verifier runs. | Provides the metering backbone for SaaS packaging and expansion revenue. |
| IH-28 | Add PR Gate links to import receipts and hosted report. | code, test, API, docs, evidence | Include A1/A2 import receipt ids, validation status, hosted report link, share expiry, bundle root hash, and readiness blockers in check output and PR comment. | Makes A3 live inside the engineering buying workflow where budget is justified. |
| IH-29 | Add Report Center packet presets. | UI, test, docs, evidence | Add presets for "PR review", "customer evidence", "security audit", "incident replay", and "executive sign-off", each selecting artifacts and share policy. | Creates clear packaging for paid plans and reduces sales/demo friction. |
| IH-30 | Add commercial report center policy matrix. | UI, API, docs, evidence | Show which packet types require auth, expiry, redaction pass, approval, audit bundle, and view audit before sharing. | Helps security-conscious buyers see policy control immediately, increasing enterprise conversion. |
| IH-31 | Add live-required-check readiness gate for PR Gate. | code, test, API, docs, evidence | Keep dry-run/live boundary explicit, then require import validation, hosted-report policy, readiness pass, and audit bundle proof before enabling live GitHub required checks. | Moves A3 from advisory reports to merge-blocking infrastructure, the highest willingness-to-pay surface. |
| IH-32 | Add evidence bundle linkage across all surfaces. | code, test, API, UI, evidence | Ensure dashboard, PR Gate, hosted report, Report Center, enterprise readiness, audit bundle, and worklog all reference the same release id, PR SHA, source hashes, report snapshot id, and root hash. | Creates a defensible chain of custody, enabling compliance, security, and platform budgets. |

## Topic Coverage

| Required topic | Covered by growth points | Auditor note |
|---|---|---|
| A1/A2 API ingest idempotency | IH-01, IH-02, IH-06 | Existing happy-path ingest should become retry-safe and duplicate-safe before paid CI/webhook use. |
| A1/A2 validation | IH-03, IH-04, IH-05, IH-07, IH-08, IH-11 | Validation should be productized with stable error schemas and docs, not hidden as internal exceptions. |
| Hosted report expiry | IH-13, IH-19, IH-30 | Expiry should be both enforced and visible to admins/viewers. |
| Hosted report revocation | IH-14, IH-16, IH-19 | Revocation must be immediate and auditable. |
| Hosted report view audit | IH-15, IH-16, IH-18 | View audit turns sharing into enterprise evidence. |
| Enterprise readiness | IH-20, IH-21, IH-25, IH-26 | Readiness should drive release decisions and self-host diagnostics. |
| SQL/self-host next steps | IH-22, IH-23, IH-24, IH-25, IH-26, IH-27 | DB durability and tenant boundaries are the bridge from local demo to commercial SaaS/self-host. |
| PR gate commercialization | IH-28, IH-31, IH-32 | PR Gate should link directly to import receipts, hosted report, readiness, and bundle proof. |
| Report Center commercialization | IH-10, IH-19, IH-29, IH-30, IH-32 | Report Center should become the evidence packet builder and share-link console. |

## Buyer-Value Stack Rank

| Rank | Build package | Why it is money-grade |
|---:|---|---|
| 1 | Idempotent A1/A2 import plus validation errors | Makes A3 safe to connect to CI and customer automation, which is the first paid production motion. |
| 2 | Hosted report lifecycle: expiry, revocation, view audit | Satisfies security review for customer-facing report sharing and unlocks enterprise trust workflows. |
| 3 | SQL-backed import/report/share/audit records | Creates durable customer state, tenant isolation, retention, and metering. |
| 4 | PR Gate required-check commercialization | Moves A3 from dashboard to merge-control infrastructure. |
| 5 | Report Center evidence packet presets | Makes the product legible to engineering managers, security reviewers, and executives. |
| 6 | Enterprise/self-host readiness health | Enables larger customers to run A3 in their own environment with operational confidence. |

## Acceptance Criteria For The Next Commercial Round

The next implementation round should be considered complete only if it can prove:

- Re-posting the same A1 RunResult with the same idempotency key returns the same receipt and does not duplicate cases.
- Re-posting the same A2 GradeResult with the same idempotency key returns the same receipt and does not duplicate grade evidence.
- Invalid A1/A2 payloads return `a3.api_validation_error.v1` with stable field paths and no raw secret-bearing values.
- Every successful import emits an audit event and a receipt containing source kind, source id, payload hash, accepted counts, rejected counts, and normalized run/case/grade counts.
- Hosted report share links have separate token hashes, expiry, revocation, scope, created_by, created_at, last_viewed_at, and view count.
- Expired or revoked hosted report links return controlled pages and do not render report bodies.
- Hosted report views emit audit events for allowed and denied attempts.
- Report Center shows import receipts, hosted report lifecycle, sealed evidence hash, redaction status, and packet presets.
- PR Gate output links to the same import receipts, report snapshot, hosted share link, enterprise readiness result, and bundle root hash.
- SQL/store contract tests prove memory/file/local SQL behavior stays compatible before production Postgres is introduced.

## Auditor Call

A3 is now close enough to a commercial SaaS shape that the next work should stop adding isolated surfaces and start enforcing lifecycle invariants. The product gets paid when teams can trust repeated imports, reject bad evidence, share report pages safely, revoke links, prove views, retain SQL-backed custody records, and block PRs with a packet that auditors can verify later.

The most important product sentence is:

> "This PR imported these exact A1/A2 evidence hashes, validated them, produced this sealed report snapshot, shared it under this expiring policy, recorded these views, and blocked or approved the release under this enterprise readiness rule."

That sentence is the bridge from A3 dashboard polish to Ashr++ commercial release intelligence.
