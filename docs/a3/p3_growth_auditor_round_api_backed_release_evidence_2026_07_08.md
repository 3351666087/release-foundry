# A3 Growth-Auditor Round - API-Backed Release Evidence - 2026-07-08

Role: Growth-Auditor / commercial SaaS auditor.

Scope: documentation artifact only. This round evaluates the commercial value and product risk of making `release_evidence_summary` API-backed and hosted-report-backed instead of treating it as a local fixture/report decoration.

Safety boundary:

- Added only this file under `docs/a3`.
- Did not modify runtime code, tests, fixtures, generated reports, strategy docs, worklogs, or secrets.
- Did not read or print `.env.local`.
- Did not write tokens, cookies, Authorization headers, API keys, raw signed URLs, private emails, or live credentials.
- Did not call live Ashr, GitHub, billing, identity, database, hosted auth, or external APIs.

## Executive Verdict

A3 already exposes `release_evidence_summary` in the places that matter for a buyer demo:

- JSON report export includes `release_evidence_summary`.
- Markdown report export includes `## Release Evidence Summary`.
- Dashboard has a Release Evidence panel.
- Report Center can summarize hosted report lifecycle and manifest readiness.
- Shareable hosted reports wrap release evidence in a hosted-report payload.
- API-backed dashboard mode already expects `payload.release_evidence || payload.release_evidence_summary`.
- Tests cover report builder, shareable report, dashboard wiring, Report Center, API server, store lifecycle, SQLite store, GitHub integration, audit archive, and SQL usage/report center behavior.

The commercial opportunity is to stop treating release evidence as "a report field" and make it a hosted, tenant-scoped, API-backed release evidence object:

```text
A1/A2 import receipts
  -> Release Gate decision
  -> GitHub Check / PR comment publish evidence
  -> hosted report snapshot
  -> Report Center manifest
  -> audit bundle verification
  -> signed archive verification
  -> release_evidence_summary API
  -> Dashboard / Report Center / War Room / hosted report
```

Money-grade recommendation:

> Build `release_evidence_summary` as the canonical API-backed release evidence health object, and make every hosted report snapshot preserve the exact summary that was shown, shared, verified, revoked, archived, and cited in PR Gate output.

Score for this round:

| Dimension | Score | Auditor note |
|---|---:|---|
| Buyer clarity | 9/10 | "Every release has a hosted evidence health object with GitHub, bundle, archive, redaction, review, and share lifecycle proof" is easy to sell. |
| Paid pilot value | 8.5/10 | Platform, security, release, and compliance buyers can all use the same evidence packet. |
| ACV expansion | 8/10 | API-backed evidence moves A3 from local reporting into release governance, hosted reporting, and compliance archive budgets. |
| Enterprise readiness | 6.5/10 | Good contracts exist, but identity, RBAC, branch-protection readback, immutable storage, and cryptographic signing need hardening. |
| Self-host readiness | 6/10 | SQLite/store contracts are encouraging; packaged deployment, object storage, backups, migrations, and offline verifier UX remain incomplete. |
| Toy risk | 6.5/10 risk | If API-backed means "served JSON from fixtures," buyers will notice. It must be tenant-scoped, persisted, hash-bound, access-controlled, and replayable. |

## Current Evidence Reviewed

This artifact is grounded in local repo evidence, not a generic SaaS checklist.

| Evidence | Current signal | Commercial meaning |
|---|---|---|
| `services/report/report_builder.mjs` | Builds and emits `a3.release_evidence_summary.v1`; report Markdown includes `## Release Evidence Summary`; summary sanitizes raw details. | A canonical report-level evidence object exists and can become the API contract. |
| `apps/dashboard/src/app.mjs` | Reads `payload.release_evidence || payload.release_evidence_summary`; renders Release Evidence tile/panel and API-backed hosted report controls. | Dashboard is ready to consume server-backed release evidence without a UI rewrite. |
| `apps/dashboard/index.html` | Navigation and section markup include Release Evidence and API-backed hosted report controls. | Product surface is already visible to release owners. |
| `tests/a3/report_builder.test.mjs` | Asserts JSON/Markdown release evidence output, archive signature status, and secret/raw-detail redaction. | Existing regression coverage protects the report contract and no-secret promise. |
| `tests/a3/shareable_report.test.mjs` | Asserts hosted report wraps release evidence, denied pages do not render report body, and secrets are redacted. | Hosted report evidence is already a commercial surface, not just local export. |
| `tests/a3/dashboard_wiring.test.mjs` | Covers API-backed dashboard and hosted report sharing; asserts release evidence appears in the HTML. | API-backed UI path has test coverage and can be extended to live release evidence. |
| `tests/a3/a3_store.test.mjs` | Covers hosted report expiry, revoke, view audit, and file-backed shareable report metadata. | Lifecycle controls exist at the store-contract level. |
| `tests/a3/a3_sqlite_store.test.mjs` | Covers SQLite persistence for imports, hosted reports, audit events, and usage ledger rows. | Durable local SQL path is plausible for self-host and hosted SaaS MVP. |
| `tests/a3/a3_sql_usage_report_center.test.mjs` | Covers usage ledger and Report Center manifest linkage with hosted reports. | Report Center can become the inventory and metering control plane. |
| `tests/a3/a3_github_integration.test.mjs` | Covers GitHub publishing evidence paths. | PR Gate evidence can be joined to the same release evidence object. |
| `tests/a3/a3_audit_archive.test.mjs` | Covers audit archive evidence. | Archive verification can be part of the hosted evidence summary. |
| `docs/a3/acceptance_checklist.md` | Marks release evidence display, hosted report lifecycle, report center, and SQLite-backed store items complete. | The next round should focus on canonical API ownership and production proof, not another static display. |

## Product Thesis

`release_evidence_summary` should become the buyer-facing evidence-health API for every release packet.

Minimum canonical object:

```text
release_id
tenant_id / project_id
repo / PR / head SHA
source import receipt ids
Release Gate decision and policy version
GitHub Check publish receipt and readback status
PR comment publish receipt and readback status
required-check enforcement status
hosted report snapshot id and content hash
share-link lifecycle summary
Report Center manifest id
audit bundle id, root hash, verifier status
signed archive id, signature status, signer/key status
redaction firewall status
review/waiver/approval status
usage meter ids
retention/legal-hold status
next action and accountable owner
```

Commercial product sentence:

> "For every agent release, A3 gives you one API-backed evidence health object that proves what was imported, gated, published to GitHub, shared as a hosted report, verified as a bundle, signed as an archive, reviewed, retained, and blocked or approved."

## New Sellable Capabilities

| Capability | Buyer-visible promise | Why it sells |
|---|---|---|
| API-backed Release Evidence Health | Dashboard, Report Center, War Room, hosted report, PR comment, and Check Run all read the same `release_evidence_summary`. | Replaces inconsistent screenshots and local files with one authoritative release record. |
| Hosted Evidence Snapshot | Every hosted report preserves the exact release evidence summary, content hash, builder version, redaction policy, and source receipt ids. | Customers can prove later what external reviewers saw. |
| Evidence Health API | `GET /api/a3/releases/:releaseId/evidence-summary` returns a versioned, redacted, tenant-scoped object. | Lets enterprise teams embed A3 in internal release portals and audit workflows. |
| Evidence Summary Diff | Compares summary state across attempts, PR commits, report snapshots, and archive versions. | Helps release managers understand whether a fix actually improved audit readiness. |
| GitHub Publish Readback | Summary distinguishes planned, dry-run, published, readback-confirmed, stale-SHA, deleted, failed, and missing evidence. | Buyers trust PR integration only when A3 proves GitHub still contains the expected Check/Comment. |
| Required Check Enforcement Proof | Summary records branch-protection readback and admin-approved required-check status. | Moves A3 from advisory reporting into paid merge-control infrastructure. |
| Hosted Report Lifecycle Evidence | Summary includes active, expired, revoked, denied-view, redaction-blocked, and auth-required share states. | Security teams can approve external report sharing. |
| Report Center Evidence Inventory | Release evidence appears as managed assets with manifest id, hashes, lifecycle, retention, usage, and verification state. | Gives platform teams a control plane instead of loose downloads. |
| Bundle And Archive Verification Status | Summary shows audit bundle root hash, verifier receipt, signed archive id, signature status, key status, and storage target. | Compliance buyers pay for repeatable proof, not static reports. |
| Fail-Closed Publish Policy | Hosted report creation, PR publishing, archive promotion, and external sharing block on redaction or verification failures. | Enterprise buyers value controls that prevent unsafe evidence from escaping. |
| Self-Host Offline Verification | Summary links to verifier inputs that can be run without cloud services. | Opens regulated customers that require private deployments. |
| Usage-To-Value Metering | Summary references usage events for imports, hosted views, revocations, verifier runs, archive bytes, and retained days. | Creates quota, chargeback, renewal, and expansion paths. |
| Auditor Packet Export | A single packet contains hosted report snapshot, summary JSON, manifest, bundle verification, archive verification, and access audit summary. | Useful for security reviews, customer audits, procurement, and incident postmortems. |

## Toy Risk Register

| Risk | Why it feels toy-like | Money-grade requirement |
|---|---|---|
| API-backed means fixture-backed | Serving the same fixture through HTTP is not a SaaS product. | Persist release evidence rows or snapshots with tenant/project/run/PR identifiers and source hashes. |
| Summary mutates after sharing | If a hosted report points at live mutable state, external evidence cannot be audited later. | Hosted reports must store immutable snapshot content hash and the exact summary version shown. |
| GitHub publish is not read back | A local receipt does not prove GitHub accepted or still displays the Check/Comment. | Add readback status with check id/comment id, repo, PR, head SHA, conclusion, and sanitized error. |
| Required check is only advisory | Buyers will not pay enterprise prices for a gate that branch protection can ignore. | Add branch-protection verifier and required-check enforcement receipt. |
| Archive status is a badge | "Verified" without archive hash, signature verification, key identity, and storage target is decorative. | Include archive id, archive hash, signature algorithm, key fingerprint, signer binding, and verifier receipt. |
| Redaction is advisory | Hosted reports and PR comments can leak sensitive content if redaction does not block publish. | Make redaction fail closed for JSON, Markdown, CSV, HTML, PR comment, Check payload, manifest, bundle, archive, and screenshots. |
| Share token is treated as a report id | Internal ids in external URLs create security and support risk. | Use hashed share tokens, scopes, expiry, revocation, and denied-view audit. |
| Tenant scoping is implicit | Cross-tenant release evidence leakage is catastrophic. | Add row/API/store tests proving no release evidence, report, share link, audit event, or usage row crosses tenants. |
| Reviewer identity is text | Enterprise sign-off needs identity, role, provider subject, expiry, and separation of duties. | Bind approvals and waivers to SSO/OIDC/GitHub App actor identity and policy. |
| Self-host is just SQLite | SQLite evidence helps local durability, but buyers need operations. | Provide deployable package, migration verification, object storage, backup/restore, offline verifier, health checks, and upgrade notes. |
| Usage meters are disconnected | Billing claims without source event ids look fake. | Tie summary usage fields to append-only usage ledger events with release/report/share/archive ids. |
| No product owner for next action | A summary that only reports status does not run a release workflow. | Include `next_action`, owner lane, blocking reason, and allowed transitions. |

## ACV Impact

| ACV lever | Impact | Proof needed before selling hard |
|---|---|---|
| Enforced PR Gate | Moves A3 into CI/release infrastructure budgets, not dashboard budgets. | GitHub readback, branch-protection enforcement receipt, stale-SHA handling, required-check tests. |
| Hosted Evidence Reports | Supports customer-facing audit packets and executive/security review workflows. | Immutable hosted snapshot, share-token lifecycle, denied-view audit, redaction fail-closed proof. |
| Compliance Archive | Opens security, GRC, legal, and regulated retention budgets. | Signed archive verification, immutable storage target, retention/legal-hold state, offline verifier. |
| Enterprise Identity | Enables multi-team rollout, reviewer accountability, and approval controls. | SSO/OIDC/GitHub actor binding, RBAC, separation-of-duties tests, audit log. |
| Self-Host / Private Deployment | Raises deal size for regulated and security-sensitive accounts. | Packaged install, DB migrations, object storage, backups, health/readiness, offline verification. |
| Usage Metering | Supports platform chargeback and plan expansion. | Append-only ledger tied to imports, views, revocations, verifier runs, retained bytes, and archive events. |
| Report Center Control Plane | Gives admins a daily operational surface. | Inventory filters, manifest drilldown, lifecycle actions, verification state, policy matrix. |
| API Platform | Lets enterprises embed A3 in internal release portals. | Versioned schemas, OpenAPI docs, SDK examples, webhooks, backward compatibility tests. |

Expected ACV movement if built honestly:

- Small paid pilot: release evidence API plus hosted snapshot lifecycle can justify a team-level pilot.
- Mid-market expansion: PR Gate readback, Report Center inventory, and view audit can justify platform-team rollout.
- Enterprise expansion: branch protection, SSO/RBAC, signed archive, retention/legal hold, and self-host readiness move A3 into compliance and release-governance budgets.
- Self-host premium: offline verifier, object storage, backup/restore, and migration checks justify private deployment pricing.

## Enterprise / Self-Host / Compliance Requirements

Enterprise requirements:

- Tenant/project/repo/PR scoping on every evidence summary.
- Authenticated internal API access and scoped external share-token access.
- SSO/OIDC/GitHub App identity binding for release owners, reviewers, approvers, and waivers.
- RBAC for view, share, revoke, verify, archive, approve, waive, and export actions.
- Append-only audit events for create, read, share, view, deny, revoke, verify, archive, approve, waive, and export.
- Redaction fail-closed before any external render or publish.
- Branch-protection readback before claiming merge enforcement.

Self-host requirements:

- SQLite remains useful for local/dev/single-node proof, but self-host needs a supported Postgres path.
- Migration status must appear in readiness and evidence summaries.
- Object storage configuration must support hosted report snapshots, bundles, archives, and replay packs.
- Backup/restore must preserve report snapshots, share-link state, audit events, usage ledger, and archive hashes.
- Offline verifier must run against exported summary/manifest/bundle/archive without contacting Ashr cloud.
- Health checks must cover DB, object storage, audit append/read, redaction policy, worker queue, clock skew, and verifier binary version.

Compliance requirements:

- Immutable hosted report snapshots with content hash and builder/redaction policy versions.
- Signed archive verification with key fingerprint, signer binding, expiry/revocation status, and detached signature receipt.
- Retention and legal-hold state on evidence summaries and report-center manifests.
- Denied-view audit that never renders report body for expired, revoked, missing, auth-required, or redaction-blocked links.
- No raw tokens, secrets, private emails, raw signed URLs, or Authorization headers in summary JSON, hosted HTML, PR comments, Check payloads, logs, screenshots, or archives.

## What Still Remains Unlike A Real Product

A3 should not oversell this round as production SaaS until these gaps are closed:

- No proven live branch-protection enforcement loop for `Ashr++ Release Gate`.
- No full GitHub App installation, permission, and actor-mapping flow.
- No SSO/SAML/OIDC, SCIM, enterprise RBAC, or tenant administration.
- No production Postgres migration and operational runbook.
- No production object storage, retention/legal-hold engine, or immutable archive store.
- No real billing, entitlement enforcement, invoice integration, seat lifecycle, or overage workflow.
- No public versioned OpenAPI contract and compatibility policy for release evidence.
- No customer-facing SDK or webhook contract for evidence-health updates.
- No production trace ingestion and replay runner tied to the summary.
- No cryptographic approval signatures bound to enterprise identity.
- No full visual E2E suite proving Dashboard, Report Center, hosted report, War Room, and revoke/deny flows across desktop/mobile.

## Next Growth Points

At least 20 growth points are required. The following are intentionally concrete and designed as parallel workstreams. Items marked `parallel` can start concurrently once the canonical schema stub is agreed.

| ID | Must run in parallel? | Growth point | Concrete next build | Exact tests/evidence expected |
|---|---|---|---|---|
| ARE-01 | No, schema anchor first | Define `a3.release_evidence_summary.v2`. | Add a versioned schema contract for tenant, project, release, repo, PR, head SHA, source receipts, report snapshot, GitHub receipts, bundle, archive, redaction, review, usage, retention, and next action. | Schema fixture; contract test that v1 report output still works and v2 fields are redacted/nullable-safe. |
| ARE-02 | Yes | Add API route for release evidence summary. | `GET /api/a3/releases/:releaseId/evidence-summary` returns the canonical summary from store/API-backed source. | `tests/a3/a3_api_server.test.mjs` covers 200, 404, redacted payload, and no raw secrets. |
| ARE-03 | Yes | Store immutable summary snapshots. | Persist summary snapshots keyed by release id, report snapshot id, builder version, content hash, created actor, and created time. | Store tests prove snapshots are immutable after hosted report creation and expose stable content hashes. |
| ARE-04 | Yes | Bind hosted reports to exact summary snapshot. | Hosted HTML and shareable payload render the stored summary snapshot, not live mutable state. | `tests/a3/shareable_report.test.mjs` proves changing source state after creation does not change hosted report body/hash. |
| ARE-05 | Yes | Add Report Center summary inventory columns. | Report Center lists evidence status, summary snapshot id, manifest id, verification state, redaction state, share status, retention state, and next action. | `tests/a3/report_center_index.test.mjs` asserts summary inventory fields and manifest linkage. |
| ARE-06 | Yes | Dashboard consumes API-backed summary. | Dashboard release panel renders from the API-backed summary object and shows stale/missing states clearly. | `tests/a3/dashboard_wiring.test.mjs` covers API-backed mock, missing summary, and stale summary. |
| ARE-07 | Yes | Hosted report denied pages preserve no-body guarantee. | Expired, revoked, missing, auth-required, and redaction-blocked share links never render summary details. | `tests/a3/shareable_report.test.mjs` denied-page cases assert no release body, no secret-like values, controlled status text. |
| ARE-08 | Yes | GitHub Check readback evidence. | Add readback receipt fields: check id, name, conclusion, head SHA, repo, readback time, stale/missing/deleted status, sanitized error. | `tests/a3/a3_github_integration.test.mjs` covers dry-run, live-shaped mock readback, stale SHA, deleted/missing, sanitized error. |
| ARE-09 | Yes | PR comment readback evidence. | Track comment id, body hash, head SHA, last update time, readback status, and sanitized error. | GitHub integration tests assert body hash match/mismatch and no token leakage in errors. |
| ARE-10 | Yes | Required-check enforcement proof. | Add branch-protection readback result and maintainer/admin approval receipt to summary. | GitHub integration or contract test covers configured, missing, wrong check name, insufficient permissions, and admin action required. |
| ARE-11 | Yes | Redaction fail-closed summary status. | Release evidence summary computes external-publish eligibility from redaction firewall results across JSON, Markdown, CSV, HTML, PR, Check, manifest, bundle, archive. | Report builder/export firewall tests prove publish blocked when any external artifact has residual finding. |
| ARE-12 | Yes | Audit bundle verifier receipt. | Summary includes bundle id, root hash, artifact count, byte count, verifier status, missing/tampered list, receipt hash. | Audit bundle/verifier tests prove pass, missing artifact, tampered hash, and receipt included in summary. |
| ARE-13 | Yes | Signed archive verifier receipt. | Summary includes archive id, archive hash, signature status, key fingerprint, signer binding, expiry/revocation status, storage target. | `tests/a3/a3_audit_archive.test.mjs` covers verified, bad signature, unknown key, expired key, missing archive. |
| ARE-14 | Yes | Review/waiver identity binding. | Summary includes reviewer state, approval/waiver ids, actor provider, role, expiry, separation-of-duties result. | Review workflow tests cover approved, rejected, expired, waived, and same-actor blocked cases. |
| ARE-15 | Yes | Release evidence next-action engine. | Compute `next_action` from gate decision, GitHub state, redaction, hosted report lifecycle, verification, review, and retention. | Unit tests cover publish check, verify bundle, verify archive, request approval, revoke share, block merge, ship. |
| ARE-16 | Yes | Usage ledger linkage. | Summary references usage ledger event ids for imports, hosted views, revocations, verifier runs, archive bytes, retained days. | `tests/a3/a3_sql_usage_report_center.test.mjs` asserts usage rows join to release evidence ids and report manifest ids. |
| ARE-17 | Yes | Tenant/project scoping tests. | Ensure release evidence API, hosted report, share link, audit event, usage row, and manifest cannot cross tenant/project boundaries. | Store/API tests seed two tenants and prove cross-tenant reads return 404/denied without body leakage. |
| ARE-18 | Yes | SQLite/Postgres-ready migration contract. | Add migration contract for release evidence snapshots, summary events, verifier receipts, GitHub readbacks, retention state. | SQL adapter contract test validates columns, indexes, tenant keys, hash fields, and migration version in readiness. |
| ARE-19 | Yes | Self-host offline verifier bundle. | Export summary JSON, manifest, bundle index, archive signature receipt, and verifier command inputs without raw share tokens. | CLI/contract evidence: offline verifier passes on exported packet and fails on tampered summary/hash. |
| ARE-20 | Yes | Hosted report lifecycle API evidence. | Summary updates when share link is created, viewed, denied, expired, revoked, or redaction-blocked. | Store/API tests cover lifecycle transitions and audit events with hashed token only. |
| ARE-21 | Yes | War Room release evidence integration. | War Room shows summary status, blocking reason, owner lane, verifier state, GitHub readback, review state, replay readiness. | Dashboard wiring or UI contract test asserts War Room consumes same summary id as Dashboard and Report Center. |
| ARE-22 | Yes | PR Gate embeds summary references. | Check Run and PR comment include summary id, hosted report snapshot id, manifest id, bundle root hash, archive status, next action. | Gate CLI tests assert generated Check/Comment payloads include matching ids and redacted links. |
| ARE-23 | Yes | Evidence summary diff. | Compare two release attempts by head SHA/report snapshot and show what changed in gate, GitHub, redaction, review, verifier, archive, share lifecycle. | Unit test covers fixed regression, new failure, stale GitHub evidence, revoked link, archive changed. |
| ARE-24 | Yes | Public API docs and safe examples. | Document release evidence API, schema versions, errors, idempotency/readback semantics, share lifecycle, no-secret examples. | Docs lint/check plus curl-safe examples with placeholder tokens only; no real domains/secrets. |
| ARE-25 | Yes | Visual E2E evidence. | Capture Dashboard Release Evidence, Report Center inventory, hosted report, denied revoked page, War Room next action, mobile layout. | Playwright screenshots and DOM assertions; no overlapping text; hosted report body absent on denied page. |
| ARE-26 | Yes | Retention/legal-hold summary state. | Add retention policy, retained-until, legal-hold, purge eligibility, archive storage class, and audit event ids. | Store/API tests cover retained, legal hold, purge blocked, purge eligible, archived states. |
| ARE-27 | Yes | Webhook event contract. | Emit release evidence changed events for summary created, GitHub readback changed, hosted report shared/revoked, verifier failed, archive verified. | Contract tests assert event schema, tenant scoping, dedupe key, payload hash, and no raw secrets. |
| ARE-28 | Yes | Backward compatibility guard. | Keep `a3.release_evidence_summary.v1` report behavior stable while v2 API evolves. | Existing `report_builder`, `shareable_report`, and `dashboard_wiring` tests continue passing; add v1/v2 compatibility test. |

Parallel execution rule:

- ARE-01 must be decided first because every other lane needs the canonical field names.
- ARE-02 through ARE-07 can run in parallel as API/store/hosted-report/dashboard/report-center lanes.
- ARE-08 through ARE-14 can run in parallel as evidence-provider lanes.
- ARE-15 through ARE-18 can run in parallel as workflow/storage/scoping lanes.
- ARE-19 through ARE-28 can run in parallel as self-host, PR Gate, documentation, visual QA, retention, webhook, and compatibility lanes.
- Do not serialize GitHub readback, hosted report immutability, redaction fail-closed, tenant scoping, and archive verification; those are independent risk reducers and should land behind the same summary contract.

## Acceptance Criteria For The Implementation Round

The next build round is complete only when all of the following are true:

- `release_evidence_summary` has a versioned API contract with no raw secret-bearing fields.
- The Dashboard, Report Center, War Room, hosted report, PR Check, and PR comment can all reference the same summary id.
- Hosted reports store an immutable summary snapshot and do not change when live source state changes later.
- Expired, revoked, missing, auth-required, and redaction-blocked hosted report pages never render report body or summary details.
- GitHub Check and PR comment evidence distinguish generated receipts from readback-confirmed evidence.
- Required-check enforcement is represented as readback proof, not as a plan-only field.
- Audit bundle verification and signed archive verification include verifier receipts and failure states.
- Redaction fail-closed policy blocks every external publish path.
- Tenant/project scoping tests prove cross-tenant release evidence reads are denied.
- SQLite/store contract tests persist summary snapshots, hosted report lifecycle, audit events, usage ledger links, and verifier receipts.
- Self-host/offline export can verify summary, manifest, bundle, and archive without Ashr cloud access.
- Usage ledger rows can be joined back to the release evidence summary.
- API docs include curl-safe examples and stable error shapes.
- Playwright or equivalent visual evidence proves Release Evidence, Report Center, hosted report, denied page, and War Room render cleanly on desktop and mobile.

## Exact Test And Evidence Matrix

Expected local command evidence for the next implementation round:

```powershell
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/shareable_report.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
node --test tests/a3/a3_api_server.test.mjs
node --test tests/a3/a3_store.test.mjs
node --test tests/a3/a3_sqlite_store.test.mjs
node --test tests/a3/a3_sql_usage_report_center.test.mjs
node --test tests/a3/report_center_index.test.mjs
node --test tests/a3/report_center_manifest_contract.test.mjs
node --test tests/a3/a3_github_integration.test.mjs
node --test tests/a3/a3_gate_cli.test.mjs
node --test tests/a3/a3_audit_archive.test.mjs
node --test tests/a3/a3_review_workflow.test.mjs
node --test tests/a3/sql_adapter_contract.test.mjs
```

Expected artifact evidence:

- Golden JSON for `a3.release_evidence_summary.v1` and v2 compatibility.
- Golden hosted report HTML showing summary snapshot id, manifest id, redaction status, and verifier state.
- Denied hosted report HTML for expired/revoked/redaction-blocked states with no body leakage.
- Report Center manifest containing the same summary id, hosted report snapshot id, bundle root hash, archive id, and usage event ids.
- GitHub Check payload fixture with summary id, head SHA, readback status, and no raw token.
- PR comment payload fixture with summary id, hosted report link policy, bundle root hash, archive status, and no raw signed URL.
- Audit bundle verifier receipt with root hash, missing/tampered cases, and receipt hash.
- Signed archive verifier receipt with archive hash, key fingerprint, signer binding, and failure states.
- SQLite fixture or migration evidence for release evidence snapshots and verifier receipts.
- Playwright screenshots for Dashboard Release Evidence, Report Center inventory, hosted report, denied page, War Room, and mobile layout.
- Secret-scan evidence over JSON, Markdown, CSV, HTML, Check payload, PR comment, manifest, bundle, archive metadata, logs, and screenshots.

## Auditor Call

The next growth round should not be "show release evidence in more places." A3 already does that. The next round should make release evidence authoritative:

```text
one API-backed summary
one immutable hosted snapshot
one report-center manifest
one PR-gate reference
one verifier chain
one tenant-scoped audit trail
```

That is the difference between a polished demo and a product a platform/security buyer can approve for paid use.
