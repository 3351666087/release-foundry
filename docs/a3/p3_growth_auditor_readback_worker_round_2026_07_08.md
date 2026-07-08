# A3 Growth-Auditor Readback Worker Round - 2026-07-08

Role: A3 Growth-Auditor / Money-Grade Auditor.

Scope: current A3 commercial audit after release evidence readback capture API, GitHub readback contracts, v2 release evidence authority surface, Report Center, Artifact Registry, usage ledger, review workflow, and A1/A2 handoff work.

Write boundary followed:

- Added only this document.
- Did not modify `services/report`.
- Did not modify `tests/a3`.
- Did not read or print `.env.local`.
- Did not call live Ashr, GitHub, billing, auth, database, object storage, or cloud APIs.
- Used local code, tests, fixtures, worklogs, and docs only.

## Executive Verdict

A3 has crossed from "pretty local report" into an early sellable release-governance control plane. The strongest current product sentence is:

> A3 can package A1/A2 evaluation evidence into a release packet, expose API-backed release evidence, record sanitized GitHub readback receipts, show report/share/audit lifecycle, meter usage, and keep waiver/approval evidence durable enough for a controlled enterprise pilot.

Money-grade score today:

| Area | Score | Auditor judgment |
|---|---:|---|
| Paid pilot readiness | 7.5/10 | Strong enough for a controlled pilot if claims stay honest: local-safe, dry-run-first, readback-capable, not fully enforced. |
| PR gate monetization | 6.5/10 | Check/PR comment publisher and readback contracts exist; branch protection enforcement still needs live maintainer-approved readback. |
| Release evidence authority | 7/10 | v2 summary, health, diff, snapshots, readbacks, usage linkage, and API routes exist; source artifact immutability is not fully authoritative yet. |
| Enterprise audit | 6.5/10 | Audit bundle, archive verification signals, report manifests, registry, and review records exist; signatures, identity, retention, and immutable storage remain gaps. |
| Self-host readiness | 5.5/10 | SQLite and SQL contracts are credible; packaged deploy, Postgres/RLS, object storage, backup/restore, and offline verifier UX remain incomplete. |
| Compliance readiness | 5/10 | Redaction and audit language are strong; SSO/RBAC, legal hold, purge receipts, key management, and formal control evidence are missing. |
| Toy risk | 5.5/10 risk | Less toy-like than before, but still prototype-like wherever local fixtures, query-param tenant scope, plan-only required checks, and unsigned approvals are involved. |

Closest money direction:

```text
GitHub required-check readback worker
  + immutable release evidence v2 authority
  + Report Center evidence packet inventory
  + identity-bound review approvals
  + offline audit verifier
```

The biggest commercial unlock is not another dashboard panel. It is proving that the release gate is enforced, the evidence packet is immutable, and an auditor can verify it later.

## Current Evidence Reviewed

| Evidence | What it proves |
|---|---|
| `services/report/a3_api_server.mjs` | Exposes `GET /evidence-summary`, `GET /evidence-health`, `GET /evidence-diff`, `POST /readbacks`, and `GET /readbacks` routes. |
| `services/report/a3_store.mjs` | Stores sanitized readbacks, applies idempotency, tenant-scope denial, audit event creation, v1/v2 summary building, and readback override into v2. |
| `services/report/a3_release_evidence.mjs` | Builds `a3.release_evidence_summary.v2`, `a3.release_evidence_health.v1`, next action, and safe diff. |
| `services/report/a3_github_integration.mjs` | Builds GitHub Check/PR comment publish plans, live-capable readers, readback receipts, and required-check proof while keeping plan-only separate from enforcement. |
| `services/report/a3_sql_migrations.mjs` | Defines release evidence summaries, snapshots, diffs, readbacks, review workflow, artifact registry, audit, and usage tables. |
| `services/report/a3_report_center.mjs` | Report Center summarizes hosted report lifecycle, manifest readiness, redaction, release evidence status, and artifact registry counts. |
| `services/report/a3_artifact_registry.mjs` | Treats `release_evidence_summary`, usage ledger, DB migration plan, SaaS admin guardrails, and `release_evidence_readback` as governed artifacts. |
| `services/report/a3_usage_ledger.mjs` | Meters A1/A2 evidence, hosted reports, views, revocations, readbacks, and API imports as read-only commercial usage. |
| `services/report/a3_review_workflow.mjs` | Creates hash-sealed waiver/approval workflow records and indexes them for durable review evidence. |
| `docs/a3/p3_release_evidence_readback_capture_api_2026_07_08.md` | Documents the readback capture API, safety boundary, usage meter, artifact entry, and verification command. |
| `docs/a3/p3_github_readback_contract_2026_07_08.md` | Documents generated/posted/readback-confirmed/stale/missing/deleted/permission-denied states. |
| `docs/a3/p3_a1_a2_release_evidence_v2_contract_map_2026_07_08.md` | Maps A1 run/trace/tool evidence and A2 judge/gate/failure evidence into future A3 v2 authority fields. |
| `docs/a3/acceptance_checklist.md` | Marks v2 summary, health, diff, readbacks, SQL rows, usage meter, and artifact registry readback entries complete. |
| `docs/a3/worklog.md` and `docs/a3/p3_worklog.md` | Record sequence, safety boundary, and prior verification results for the current A3 round. |

## 本轮新增 / 可卖能力判断

Current new sellable capabilities:

| Capability | Sellability | Why it matters |
|---|---|---|
| Release evidence readback capture API | Sellable for pilot | CI/GitHub worker can submit sanitized readback receipts into A3 instead of leaving readback as static fixture state. |
| Release-scoped readback inspection | Sellable for pilot | Release owners and auditors can ask "what did we read back for this release?" without parsing loose artifacts. |
| v2 release evidence authority surface | Sellable with caution | `a3.release_evidence_summary.v2` now carries tenant scope, A1/A2 evidence counts, readbacks, usage linkage, redaction, compliance placeholders, and next actions. |
| Evidence health endpoint | Sellable | Dashboard, PR gate, monitor, and future War Room can consume a compact decision object. |
| GitHub readback contract | Sellable with caution | A3 distinguishes generated, posted, readback-confirmed, stale, missing, deleted, permission-denied, and failed states. |
| Required-check proof contract | Sellable only as readiness | Plan-only can no longer honestly claim enforcement. This is a trust-building guardrail, not enforcement yet. |
| Readback usage meter | Sellable as monetization foundation | Readback checks can become billable/limited usage once backed by real service events. |
| Artifact Registry readback entries | Sellable | Captured readbacks become governed evidence assets, not ad hoc JSON files. |
| SQLite persistence for v2/readbacks | Sellable for local/self-host proof | Proves durability shape, though not production Postgres/RLS. |
| Durable review workflow records | Sellable for enterprise pilot | Waiver/approval records are hash-sealed and tenant-scoped, even though identity and crypto verification are not done. |

Auditor call:

```text
可卖: controlled pilot, release evidence API, PR readback workflow, governed report packet.
不可硬卖: production enforced PR gate, SOC2-grade compliance, complete self-host, real billing, identity-bound approval.
```

## 玩具能力升级点

| Current feature | Why it can still feel toy-like | Upgrade needed |
|---|---|---|
| Readback capture API accepts sanitized receipts | A bad or fake worker could submit a receipt unless auth/RBAC/service-account identity exists. | Signed service account auth, nonce/timestamp replay protection, worker identity, RBAC, audit chain. |
| Readback receipts override static state | API acceptance does not prove GitHub really had that state. | Live GitHub App worker reads provider state and submits signed receipt with provider request id and hash. |
| Required-check proof can be plan-only | A plan is not branch protection enforcement. | Branch-protection readback proving `Ashr++ Release Gate` is actually required on target branch. |
| v2 summary id is hash-derived | Recomputed ids can shift when source payload changes. | Persist summary rows immutably with source snapshot ids and content hashes. |
| Tenant scope is local/query/body scoped | It is not bound to real authenticated identity. | A1 auth middleware, org/project binding, service-account auth, and negative tests through real auth. |
| SQLite persistence works locally | SQLite is not enterprise durability by itself. | Postgres migrations, RLS policy, backup/restore, migration apply smoke, operational runbook. |
| Review workflow is hash-sealed | Signer identity is not SSO/OIDC/GitHub-bound and signatures are not cryptographically verified. | Provider subject alias, role, expiry, signature verifier, separation-of-duties enforcement. |
| Usage ledger is read-only | Billing value is visible, but not invoice/entitlement backed. | Append-only usage events, quotas, overage preview, billing export, plan enforcement. |
| Artifact Registry is metadata-rich | Not yet backed by object storage custody and retention. | Object store refs, byte size, SHA-256, retention class, legal hold, immutable archive proof. |
| Redaction is strong but distributed | Enterprise buyers need one fail-closed matrix across all external outputs. | Shared redaction firewall gating JSON, MD, CSV, HTML, hosted report, Check, PR comment, manifest, bundle, archive, logs, and screenshots. |

## 能提高客单价的能力

| ACV lever | Why it raises price | Proof needed |
|---|---|---|
| Enforced GitHub PR gate | Moves A3 into merge infrastructure budgets instead of dashboard budgets. | Live check/comment readback, branch-protection proof, stale SHA handling, required-check negative tests. |
| Release Evidence Authority | Gives platform/security one canonical evidence record per release. | Immutable summary/source snapshots, stable ids, source hashes, API docs, compatibility tests. |
| Report Center Evidence Inventory | Turns reports into governed assets with lifecycle, manifest, usage, and retention. | Detail page, filters, completeness score, readback/verifier joins, redaction gating. |
| Audit Bundle and Offline Verifier | Compliance teams pay for proof that survives time and migration. | Bundle verifier receipt, signed archive receipt, detached signatures, offline command, tamper tests. |
| Identity-bound review workflow | Enterprise approvals require accountable actors and roles. | SSO/OIDC/GitHub actor binding, role policy, expiry, signer verification, separation of duties. |
| Self-host Enterprise | Regulated buyers need private data processing. | Docker/Compose or Helm path, Postgres/RLS, object storage, backup/restore, offline verifier, health checks. |
| Usage governance and chargeback | Platform teams need rollout economics across teams/projects. | Usage event ids, quotas, retained bytes, verifier runs, report views, billing export. |
| Production trace ingestion and replay | Daily operational use increases stickiness and volume. | A1 trace ingestion wrapper, replay pack, replay runner receipt, run-to-run diff, RCA export. |
| Judge calibration and drift | Reduces objections to false blocks and false passes. | A2 calibration matrix, judge registry hash, drift monitor, human review for low confidence. |
| Webhooks/API platform | Lets enterprises embed A3 in release portals. | Versioned schemas, OpenAPI, webhook dry-run, idempotency, compatibility tests. |

## Enterprise / Self-Host / Compliance Value

Enterprise value already present:

- Tenant/project-scoped local contracts for dashboard, reports, readbacks, review records, usage, registry, and evidence summaries.
- Readback capture creates audit event `release_evidence.readback_captured`.
- Review workflow records are hash-sealed and durable in local/SQLite paths.
- Report Center and Artifact Registry make evidence lifecycle visible.
- SaaS admin actions remain request/audit records, not fake cloud mutations.
- API error redaction prevents secret-like internal errors from leaking.

Self-host value already present:

- SQL migration contract supports Postgres/MySQL/SQLite dialect targets.
- SQLite-backed store proves local durability for reports, usage, review, v2 snapshots, diffs, and readbacks.
- Self-host readiness is modeled as a product surface, not only a README promise.

Compliance value already present:

- Redaction discipline exists across reports and generated artifacts.
- Hosted report lifecycle has expiry, revoke, view audit, and denied-body behavior.
- Audit bundle and archive verification signals are already part of release evidence.
- Artifact Registry can describe retention class, hash readiness, share scope, and missing controls.

Still required before enterprise claims:

- Real auth/RBAC/SSO/OIDC/GitHub App actor binding.
- Immutable object storage, retention, legal hold, purge receipts, and backup/restore.
- Cryptographic signature verification for approvals and audit archives.
- Formal API docs, OpenAPI, compatibility policy, and webhook contracts.
- Production Postgres/RLS and migration apply evidence.
- Offline verifier packet with tamper/missing artifact tests.

## 还不像真产品的点

1. No maintainer-approved live GitHub App worker has read back real Check Run, PR comment, or branch protection in this repo.
2. Required-check enforcement is still not proven by branch-protection readback.
3. Query/body/options tenant scope is not the same as auth-bound tenant isolation.
4. v2 release evidence is still partly computed from local snapshots rather than persisted as the canonical immutable record everywhere.
5. A1 source artifacts are not yet wrapped with mandatory tenant/project/request/artifact/hash metadata.
6. A2 release gate, judge registry, scenario selection, and calibration outputs are not yet all hash-linked into v2 authority.
7. Review approvals are not tied to real SSO/OIDC/GitHub identity or cryptographic signatures.
8. Artifact Registry entries are metadata only until object storage and retention are implemented.
9. Usage ledger is read-only and not tied to entitlements, invoices, quotas, or billing export.
10. Report Center still needs production-grade filters, search, pagination, packet detail, and retention/legal-hold controls.
11. Redaction fail-closed policy is not yet one externally enforced matrix for every artifact class.
12. Self-host lacks install, upgrade, backup/restore, object storage, health checks, and offline verifier UX.
13. No public OpenAPI or SDK examples exist for the A3 release evidence/readback workflow.
14. No webhook delivery or dry-run delivery receipt exists for evidence-health changes.
15. Production trace ingestion/replay remains a contract direction, not a fully executable customer workflow.
16. Judge calibration/drift is not yet part of release evidence health.
17. Visual E2E evidence for the new readback/health/report center path is not current in this pass.
18. Billing/admin controls correctly avoid real mutation, but that also means enterprise admin is not yet operational.

## 下一轮增长点

At least 20 are required; below are 36 growth points, grouped by money path.

| ID | Growth point | Next executable target | Must parallel? | Money value |
|---|---|---|---|---|
| RBW-01 | GitHub readback worker | CI/GitHub App worker reads Check Run and submits sanitized readback via `POST /readbacks`. | Yes | Converts local contracts into provider proof. |
| RBW-02 | PR comment readback worker | Read marker/body hash/head SHA and submit stale/missing/deleted states. | Yes | Makes PR comments trustworthy. |
| RBW-03 | Branch-protection verifier | Read required status checks and prove `Ashr++ Release Gate` is required. | Yes | Highest PR gate ACV unlock. |
| RBW-04 | Worker service-account auth | Signed worker identity, key rotation, nonce/timestamp replay protection. | Yes | Prevents fake readback submissions. |
| RBW-05 | Readback diff/history API | Show generated -> posted -> confirmed/stale/missing transitions. | Yes | Helps release owners debug external state. |
| RBW-06 | Readback stale monitor | Periodic check for stale SHA, deleted comment, missing branch protection. | Yes | Turns A3 into continuous control, not one-time report. |
| AUTH-01 | A1 auth-bound tenant scope | Bind read/write tenant scope to API key/session/service account. | Yes | Required for SaaS credibility. |
| AUTH-02 | Cross-tenant negative suite | Cover summary, readbacks, reports, manifests, registry, usage, audit, review, SQLite rows. | Yes | Reduces catastrophic leakage risk. |
| AUTH-03 | RBAC permission matrix | View, submit readback, share, revoke, approve, waive, verify, archive, export. | Yes | Enterprise procurement requirement. |
| AUTH-04 | GitHub/OIDC actor binding | Map GitHub App actor or OIDC subject to reviewer/service account. | Yes | Makes PR/review evidence accountable. |
| V2-01 | Immutable v2 summary table | Persist summary id, content hash, source snapshot ids, health status, next action. | Yes | Makes release evidence authoritative. |
| V2-02 | Source snapshot ledger | Snapshot A1 run/trace/tool and A2 grade/gate/judge inputs with hashes. | Yes | Prevents mutable source ambiguity. |
| V2-03 | A1 artifact projection | `a1_run_result`, trace batch, tool-call batch artifacts with hashes and redaction state. | Yes | Connects backend evidence to audit packet. |
| V2-04 | A2 artifact projection | Grade report, scenario selection, judge registry, release gate artifacts with hashes. | Yes | Preserves A2 semantics without rewriting them. |
| V2-05 | Score provenance | Record A1 0-1 vs A2 0-100 source/scale/join completeness. | Yes | Avoids audit ambiguity. |
| V2-06 | Optional feed states | present/missing/stale/not_required for scenario selection, judge versions, calibration, replay. | Yes | Stops invented authority. |
| RC-01 | Report Center packet detail | Join hosted report, summary, readbacks, manifest, bundle, archive, review, usage, retention. | Yes | Makes Report Center a paid governance hub. |
| RC-02 | Evidence completeness score | Required/optional artifacts, stale readbacks, missing verifier, blocked redaction. | Yes | Manager/auditor-friendly signal. |
| RC-03 | Filters/search/pagination | Filter by stale readback, redaction blocked, required check missing, archive failed, retention due. | Yes | Needed at enterprise scale. |
| RC-04 | Share gating by evidence health | Block external share if redaction, bundle, archive, or required readback fails. | Yes | Security/compliance value. |
| REG-01 | Object storage registry | Store object key aliases, SHA-256, byte size, content type, retention class. | Yes | Moves registry from metadata to custody. |
| REG-02 | Artifact lifecycle events | generated, scanned, shared, viewed, revoked, verified, archived, retained, purged. | Yes | Chain-of-custody foundation. |
| AUD-01 | Offline verifier packet | Export summary, manifest, bundle index, archive receipt, verifier inputs without cloud dependency. | Yes | Self-host/regulated buyer wedge. |
| AUD-02 | Signed archive verifier | Detached signature, key fingerprint, signer binding, expiry/revocation status. | Yes | Compliance-grade archive claim. |
| AUD-03 | PDF/screenshot hash inclusion | Include visual evidence artifacts in bundle/archive verifier. | Yes | Closes common audit evidence gap. |
| AUD-04 | Retention/legal-hold states | retained_until, legal_hold, purge_eligible, purge_blocked_reason, object-lock readiness. | Yes | Enterprise compliance tier. |
| REVIEW-01 | Identity-bound approvals | Provider subject alias, role, expiry, artifact hashes, separation-of-duties result. | Yes | Makes approval workflow enterprise credible. |
| REVIEW-02 | Signature verification | Verify signer/key before approval can affect release state. | Yes | Regulated control. |
| REVIEW-03 | Reviewer SLA/escalation | Owner, due date, stale waiver, missing evidence, escalation state. | Yes | Operationalizes release workflow. |
| RED-01 | Unified fail-closed redaction matrix | JSON, MD, CSV, HTML, hosted report, Check, PR comment, manifest, bundle, archive, logs, screenshots. | Yes | Prevents sensitive evidence leaks. |
| USAGE-01 | Usage event ids | Link imports, readbacks, views, revokes, verifier runs, archive bytes, retained days to summary id. | Yes | Billing-ready evidence. |
| USAGE-02 | Quota and overage preview | Read-only quotas, forecasts, plan limits, retained bytes, verifier counts. | Yes | Monetization without dangerous billing mutation. |
| USAGE-03 | Billing export | Stripe/invoice-ready metering file after admin approval. | No | Bridges pilot to revenue ops. |
| API-01 | OpenAPI docs | Release evidence v1/v2, readbacks, health, diff, review, report center, error shapes, idempotency. | Yes | Enterprise integration readiness. |
| API-02 | Webhook dry-run receipts | health_changed, readback_changed, share_revoked, verifier_failed, archive_verified. | Yes | Workflow automation path. |
| SELF-01 | Self-host smoke package | API, dashboard, SQLite/Postgres, object storage stub, worker, offline verifier. | Yes | Private deployment sales. |
| SELF-02 | Backup/restore/upgrade drill | Verify DB migration version, object hashes, audit log, report snapshots, usage ledger. | Yes | Operations credibility. |
| TRACE-01 | Production trace ingestion wrapper | Attach tenant/project/request/artifact/hash metadata around A1 output without changing A1 core. | Yes | Gets out of fixture ceiling. |
| REPLAY-01 | Replay pack and runner receipt | reproduced/fixed/flaky/new-failure/not-runnable states. | Yes | Incident/release ops expansion. |
| JUDGE-01 | Judge calibration in health | A2 calibration matrix, judge version, drift, false-pass/false-block signal. | Yes | Increases trust in gate decisions. |
| E2E-01 | Visual E2E evidence | Dashboard, Report Center, hosted report, denied page, readback state, mobile. | No | Demo confidence and UX QA. |

## 哪些必须并行

Do not serialize these. They reduce different existential risks and can share the same schema anchor:

| Lane | Must start with | Can run in parallel with | Why parallel |
|---|---|---|---|
| A. Readback Worker | RBW-01/RBW-02/RBW-03 | Auth, v2, Report Center, registry | External proof is the fastest PR gate money path. |
| B. Auth/Tenant/RBAC | AUTH-01/AUTH-02/AUTH-03 | Readback, v2, review | A fake worker or cross-tenant read breaks trust instantly. |
| C. v2 Authority | V2-01/V2-02 | Readback, A1/A2 projections, Report Center | Every surface needs stable summary/source ids. |
| D. A1/A2 Source Projection | V2-03/V2-04/V2-05 | v2 authority, replay, calibration | A3 must reference source evidence instead of inventing authority. |
| E. Report Center/Registry | RC-01/REG-01 | v2, readback, usage, audit | Buyer-facing inventory should land as soon as ids exist. |
| F. Audit/Self-host | AUD-01/AUD-02/SELF-01 | registry, v2, retention | Offline verifier and self-host unlock larger deals. |
| G. Review/Identity | REVIEW-01/REVIEW-02 | auth, v2, audit | Approval value depends on real identity and artifact hash binding. |
| H. Usage/API/Webhooks | USAGE-01/API-01/API-02 | v2, readback, report center | Monetization and integrations need stable event ids early. |

Minimum dependency rule:

1. Agree on stable v2 ids and source snapshot fields.
2. In parallel, build readback worker, auth-bound tenant scope, source artifact projections, Report Center detail, and usage links.
3. Add offline verifier, identity-bound approvals, and retention/legal-hold once artifact ids and audit events are stable.

## 最接近大钱的方向

Ranked by urgency, ACV, and current repo fit:

| Rank | Direction | Why it is closest to big money | Required proof |
|---:|---|---|---|
| 1 | Enforced PR Gate with live readback | It sits in the merge path and can block risky agent releases. | GitHub App/CI worker, Check/Comment readback, branch-protection proof, stale/missing states, auth-bound worker. |
| 2 | Release Evidence Authority | Creates one canonical record for release, report, PR, review, usage, audit, and compliance. | Immutable v2 summary/source snapshots, content hashes, source artifact ids, Postgres/RLS. |
| 3 | Enterprise Audit Packet | Security/compliance buyers pay for retained, verifiable evidence. | Bundle verifier, signed archive verifier, object storage, retention/legal hold, offline verifier. |
| 4 | Identity-Bound Review Workflow | Turns waiver/approval from local record into enterprise sign-off control. | SSO/OIDC/GitHub actor, role, expiry, separation-of-duties, signature verification. |
| 5 | Self-host Enterprise | Regulated customers require private deployment and offline proof. | Install package, Postgres/RLS, object storage, backup/restore, health checks, offline verifier. |
| 6 | Usage Governance | Lets platform teams expand across teams and charge back usage. | Usage event ids, quotas, billing export, retained bytes, verifier runs, report views. |
| 7 | Production Trace Replay | Makes A3 a daily incident/release ops tool, not only a PR report. | Trace ingestion wrapper, replay pack, runner receipt, RCA export, judge calibration. |

Auditor call:

```text
The nearest big-money package is:

"A3 Enforced Agent PR Gate + Release Evidence Authority + Offline Audit Packet."

This is clearer and more budgetable than selling A3 as an eval dashboard.
```

## A1/A2 对接判断

Current compatibility:

- A1 still owns run, trace, observation, tool-call, SDK, worker, platform API, auth/storage direction, and usage source.
- A2 still owns judge, score, pass/fail, failure taxonomy, release policy, scenario selection, calibration, and verifier correctness.
- A3 correctly stays downstream: it packages, displays, shares, meters, reviews, and readbacks release evidence without changing A1 runner or A2 judge semantics.

Current gap:

- A1 local outputs are rich but not mandatory tenant/project/request/artifact/hash authority records.
- A2 outputs are semantically strong but not all hash-linked into the A3 v2 evidence chain.
- A3 v2 should reference source artifacts by id/hash, not embed raw A1/A2 payloads in public release evidence.
- Readback confirmed from GitHub is not the same as A1/A2 release verifier passed. Both need separate fields.

Next A1/A2 contract requirement:

```text
A1/A2 source artifacts
  -> immutable source snapshot ids and hashes
  -> A3 v2 summary id
  -> GitHub/readback/review/report/audit/usage links
```

## Failure Points / Risks

No test failures were observed in this audit run, but product failure points remain:

1. A malicious or buggy worker could submit a readback receipt unless signed worker auth/RBAC exists.
2. Branch-protection proof must remain plan-only until actual readback confirms enforcement.
3. Cross-tenant safety is local-contract strong but not hosted-auth strong.
4. v2 summary cannot become the durable authority until persisted source snapshots are immutable.
5. Report Center and Artifact Registry must not imply custody until object storage/hash retention exists.
6. Approval cannot unblock production until identity and signature verification are real.
7. Usage ledger should not be sold as billing until event ids, quotas, entitlements, and export/invoice links exist.
8. External sharing should fail closed on any redaction finding across every artifact class.
9. Self-host should not be marketed as complete until install, backup, restore, migration, health, object storage, and offline verifier evidence exist.
10. Existing docs have some time-lag wording about v2 builder availability; current source supersedes that older statement, but the source authority gap is still real.

## Verification Run

Command run locally:

```text
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/artifact_registry.test.mjs
```

Result:

```text
21 pass
0 fail
```

Covered areas:

- API server dashboard/release evidence/readback/usage/report center paths.
- Release evidence v2 authority summary, health, readback proof, next action, and diff.
- SQL migration contract for tenant-scoped import/report/audit/usage/readback tables.
- SQLite persistence for imports, reports, audit events, usage rows, v2 snapshots/diffs/readbacks.
- Store idempotency, hosted report lifecycle, file-backed persistence, and artifact registry.

## What Changed

Only one document was added:

```text
docs/a3/p3_growth_auditor_readback_worker_round_2026_07_08.md
```

No code, tests, services, fixtures, env files, or generated reports were changed by this audit document.

## Evidence Location

Primary current-state evidence:

- `services/report/a3_api_server.mjs`
- `services/report/a3_store.mjs`
- `services/report/a3_release_evidence.mjs`
- `services/report/a3_github_integration.mjs`
- `services/report/a3_sql_migrations.mjs`
- `services/report/a3_report_center.mjs`
- `services/report/a3_artifact_registry.mjs`
- `services/report/a3_usage_ledger.mjs`
- `services/report/a3_review_workflow.mjs`
- `docs/a3/p3_release_evidence_readback_capture_api_2026_07_08.md`
- `docs/a3/p3_github_readback_contract_2026_07_08.md`
- `docs/a3/p3_a1_a2_release_evidence_v2_contract_map_2026_07_08.md`
- `docs/a3/acceptance_checklist.md`
- `docs/a3/worklog.md`
- `docs/a3/p3_worklog.md`

Focused test evidence:

- `tests/a3/a3_api_server.test.mjs`
- `tests/a3/a3_store.test.mjs`
- `tests/a3/a3_sqlite_store.test.mjs`
- `tests/a3/a3_release_evidence.test.mjs`
- `tests/a3/a3_sql_usage_report_center.test.mjs`
- `tests/a3/artifact_registry.test.mjs`

## Final Money-Grade Call

A3 is now closest to a paid enterprise pilot as:

```text
Agent Release Evidence Authority for PRs
```

Best next build:

```text
live readback worker
+ branch-protection required-check proof
+ immutable v2 source snapshots
+ Report Center packet detail
+ identity-bound approvals
+ offline verifier packet
```

That is the shortest path from "excellent local product factory" to "release infrastructure that a platform/security buyer can pay real money for."
