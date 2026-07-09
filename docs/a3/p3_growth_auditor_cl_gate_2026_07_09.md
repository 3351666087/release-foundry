# A3 Growth-Auditor CL Gate - 2026-07-09

Role: Growth-Auditor / Money-Grade Auditor.

Scope: A3 CL gate round from latest known `main` state. Local `main`, `origin/main`, and `codex/a3-commercial-cl-gate` all pointed at `bb09c81` (`Merge latest A1 local SDK runner into main`) during this audit. A remote fetch was attempted but GitHub was unreachable from this environment, so this report uses the latest local `origin/main` snapshot.

Safety boundary:

- Added this documentation artifact only.
- Did not edit runtime code, tests, fixtures, env files, strategy docs, or worklogs.
- Did not read or print `.env.local`.
- Did not call live Ashr, GitHub, billing, auth, database, object storage, or cloud APIs.
- Treated existing worktree and repo history as shared work; did not revert anyone else's changes.

## Inputs Reviewed

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- `docs/a3/acceptance_checklist.md`
- `docs/a3/worklog.md`
- `docs/a3/p3_worklog.md`
- Current A3 Growth-Auditor artifacts around release evidence v2, GitHub readback, readback capture, audit archive, SQL usage/report center, SaaS admin, reviewer workflow, incident replay, and self-host readiness.

## Executive Verdict

A3 is now sellable as an early release-governance control plane for AI-agent changes, not merely a dashboard. The strongest CL gate claim is:

> A3 can turn A1/A2 run and judge evidence into a change-list release packet, publish or plan GitHub Check/PR-comment gate artifacts, capture sanitized readback receipts through an API/worker path, show evidence health in dashboard/report surfaces, and retain review/audit/usage records around the same release evidence object.

This is pilot-sellable if the claims stay precise. It is not yet production-enterprise until branch protection, identity, tenant isolation, Postgres/RLS, billing, and immutable storage are proven.

## New CL Gate Capability That Makes A3 More Sellable

The new sellable capability is the readback-backed CL gate:

```text
A1/A2 evidence
  -> release evidence summary v2 / health / diff
  -> GitHub Check and PR comment gate artifacts
  -> sanitized readback capture API
  -> readback worker CLI path
  -> dashboard / Report Center / JSON / Markdown / print visibility
  -> artifact registry and usage meter linkage
```

Why this sells better than prior A3 work:

1. It moves A3 from "we generated a gate report" to "we can record what the external merge-control system says now."
2. It separates plan-only, posted, readback-confirmed, stale, missing, deleted, permission-denied, and failed states, which prevents inflated enterprise claims.
3. It creates a natural paid workflow: every risky CL/PR gets a machine-readable Check, a human-readable comment, an evidence packet, reviewer state, and audit trail.
4. It lets future CI or GitHub App workers submit sanitized receipts without exposing tokens, raw account values, Authorization headers, or `.env.local`.
5. It creates billable usage units around readbacks, release evidence snapshots, hosted report views, verifier runs, retained artifacts, and PR gate attempts.

Money-grade phrasing:

> "A3 can be the enforced evidence gate for agent PRs: it blocks risky changes, proves what evidence was used, records what GitHub showed, and gives reviewers and auditors the same packet."

## What Is Already Real

| Area | Current real signal | Sellable value |
|---|---|---|
| Release evidence v2 | v2 authority shape, health, diff, A1/A2 counts, readback placeholders, usage linkage, and SQL rows are documented and checked in current A3 worklogs. | One canonical evidence object can anchor dashboard, report, PR gate, review, audit, and usage. |
| GitHub gate path | Live-capable Check publisher, PR comment publisher, readback contracts, and required-check proof contract exist, with dry-run default and plan-only honesty. | Moves toward merge infrastructure budgets. |
| Readback capture | `POST`/`GET` readback capture path, idempotency, tenant-scope checks, audit event linkage, redaction, SQLite persistence, CLI worker path, and UI/report visibility are recorded in worklogs. | Makes external release-control proof capturable, not just local. |
| Report Center | Hosted report lifecycle, manifest readiness, redaction status, release evidence summary, artifact registry counts, usage, expiry/revoke/view audit. | Turns loose reports into governed evidence inventory. |
| Audit bundle/archive | Bundle index, verifier, signed archive manifest/verifier direction, root hashes, entry hashes, and missing-entry checks. | Compliance story is credible for pilot. |
| Review workflow | Durable hash-sealed waiver/approval records and reviewer workflow board concepts. | Converts blocked releases into assigned decision work. |
| Usage ledger | Runs, cases, trace events, tool-call cases, judge results, hosted reports, report views, revocations, readbacks, and API imports are metered in local/read-only form. | Pricing and chargeback foundation. |
| Self-host contracts | SQLite store, SQL migration contracts, self-host console/readiness docs. | Regulated-buyer wedge, though not packaged yet. |

## Toy-Like Pieces That Must Not Be Oversold

| Existing piece | Why it still feels toy-like | Money-grade upgrade |
|---|---|---|
| Required-check plan | A plan does not prove GitHub branch protection enforces `Ashr++ Release Gate`. | Live branch-protection readback plus admin-approved enforcement receipt. |
| GitHub Check/PR comment receipts | Dry-run or generated receipts do not prove provider state. | GitHub App/CI readback with check id, comment id, head SHA, body hash, stale/missing/deleted states. |
| Readback capture API | A fake worker can submit a nice-looking receipt without strong identity. | Service-account auth, signed receipts, nonce/timestamp replay defense, provider request id. |
| Tenant scope | Local query/body/options tenant scope is not real SaaS isolation. | A1 auth-bound org/project/session/API-key scope plus cross-tenant negative tests. |
| SQLite durability | Good local proof, but not enterprise production storage. | Postgres migrations, RLS, indexes, transactions, backup/restore, migration apply evidence. |
| Release evidence v2 | Partly computed from local/source snapshots; not yet the immutable system of record everywhere. | Persist immutable summary/source snapshots with content hashes and stable ids. |
| A1/A2 evidence linkage | Counts and mappings exist, but not every source artifact is hash-linked into v2 authority. | Mandatory A1 run/trace/tool and A2 grade/judge/policy artifact projections. |
| Review approvals | Hash-sealed records are useful, but identity/signatures are not production-bound. | SSO/OIDC/GitHub actor binding, role checks, cryptographic signature verification, separation of duties. |
| Incident replay | Queue/matrix/factory exist, but production replay is not fully executable from customer traces. | Trace ingestion schema, replay pack, replay runner receipt, RCA report. |
| Judge calibration | A2 evidence is referenced, but calibration/drift does not yet drive gate confidence. | Judge registry hash, calibration matrix, false-pass/false-block metrics, drift monitor. |
| Usage ledger | Read-only meters are not billing. | Append-only usage events, quotas, entitlements, chargeback, billing export, invoice preview. |
| Report Center | Valuable inventory idea, still needs enterprise scale controls. | Detail pages, filters/search/pagination, completeness score, retention/legal hold, share gating. |
| Artifact Registry | Metadata-rich but not object-storage-backed custody. | Object keys, SHA-256, byte size, retention class, legal hold, purge receipts. |
| Redaction | Good scrubbers, but no single fail-closed external-publish policy across all artifact classes. | Unified redaction matrix for JSON, MD, CSV, HTML, Check, PR comment, manifest, bundle, archive, logs, screenshots. |
| Self-host | Contracts exist, but no installable customer package. | Docker Compose/Helm, Postgres/RLS, object storage, worker, offline verifier, backup/restore, health checks. |
| API platform | Internal/local routes exist, but no public contract package. | Versioned OpenAPI, SDK examples, webhook schemas, compatibility tests, idempotency/error docs. |
| Billing/admin | Guarded plan-only/admin request posture is safe, but not operational. | Real identity/RBAC-backed admin flows plus billing provider/export path. |
| Visual proof | Prior screenshots exist, but newest readback/health path needs current E2E evidence. | Playwright desktop/mobile/hosted-report/denied-page screenshots with leak/layout assertions. |

## Next Growth Points

At least 20 are required; below are 32. Items marked `Yes` in the parallel column should start together once the v2 summary/source-snapshot ids are agreed.

| ID | Growth point | Concrete next build | Must run in parallel? | Money value |
|---|---|---|---|---|
| CL-01 | GitHub Check readback worker | CI/GitHub App reads Check Run by repo/head SHA/check name and submits sanitized receipt to readback API. | Yes | Turns generated check into provider proof. |
| CL-02 | PR comment readback worker | Read marker, comment id, body hash, PR number, head SHA, stale/missing/deleted states. | Yes | Makes human PR evidence trustworthy. |
| CL-03 | Branch-protection verifier | Prove `Ashr++ Release Gate` is configured and enforced as a required check. | Yes | Highest PR gate monetization unlock. |
| CL-04 | Worker identity | Signed service account, nonce, timestamp, key rotation, audit actor, replay protection. | Yes | Prevents fake readback submissions. |
| CL-05 | Readback history and stale monitor | Track generated -> posted -> confirmed/stale/missing/deleted transitions and periodic drift. | Yes | Makes gate continuous, not one-shot. |
| AUTH-01 | Auth-bound tenant scope | Bind tenant/project/repo scope to API key/session/service account. | Yes | Required for SaaS credibility. |
| AUTH-02 | Cross-tenant negative tests | Cover summaries, readbacks, reports, manifests, registry, usage, audit, review, SQLite rows. | Yes | Prevents catastrophic data leakage. |
| AUTH-03 | RBAC matrix | View, submit readback, share, revoke, approve, waive, verify, archive, export, legal hold. | Yes | Enterprise procurement requirement. |
| V2-01 | Immutable release evidence summary | Persist summary id, content hash, builder version, health, next action, source snapshot ids. | Yes | Makes the evidence packet authoritative. |
| V2-02 | Source snapshot ledger | Snapshot A1 run/trace/tool and A2 grade/gate/judge inputs with hashes and redaction state. | Yes | Prevents mutable-source ambiguity. |
| V2-03 | A1 artifact projection | First-class A1 run result, trace batch, observation batch, tool-call batch artifact refs. | Yes | Ties gate to backend evidence. |
| V2-04 | A2 artifact projection | First-class grade, scenario selection, release policy, judge registry, calibration artifacts. | Yes | Ties gate to evaluation authority. |
| V2-05 | Evidence diff API | Compare release attempts by head SHA/snapshot and show gate, GitHub, review, redaction, verifier changes. | Yes | Helps release owners prove fixes. |
| RC-01 | Report Center packet detail | Join summary, hosted report, manifest, readbacks, review records, bundle, archive, usage, retention. | Yes | Makes Report Center a paid governance hub. |
| RC-02 | Evidence completeness score | Required/optional artifacts, stale readbacks, missing verifier, blocked redaction, missing approvals. | Yes | Executive and auditor-friendly signal. |
| RC-03 | Search/filter/pagination | Filter by stale readback, required check missing, archive failed, redaction blocked, retention due. | Yes | Needed for enterprise scale. |
| RC-04 | Share gating by health | Block external share when redaction, bundle, archive, required readback, or retention checks fail. | Yes | Raises security value. |
| AUD-01 | Offline verifier packet | Export summary, manifest, bundle index, archive receipt, hashes, and local verify command. | Yes | Self-host/regulatory wedge. |
| AUD-02 | Signed archive hardening | Detached signature, key fingerprint, signer binding, expiry/revocation status, tamper tests. | Yes | Compliance-grade proof. |
| AUD-03 | Visual artifact hashes | Add PDF/screenshot/export hashes into bundle/archive verifier. | Yes | Closes audit evidence gap. |
| AUD-04 | Retention/legal hold | Retained until, legal hold, purge eligibility, purge blocked reason, object-lock readiness. | Yes | Enterprise compliance tier. |
| REVIEW-01 | Identity-bound approvals | Provider subject, role, org/project scope, expiry, artifact hashes, separation-of-duties result. | Yes | Makes review workflow enterprise credible. |
| REVIEW-02 | Signature verification | Verify signer/key before approval affects release state. | Yes | Regulated sign-off control. |
| REVIEW-03 | Reviewer SLA/escalation | Owner, due date, stale waiver, missing evidence, escalation target, disposition history. | Yes | Makes blocked releases operational. |
| TRACE-01 | Production trace ingestion contract | Normalize A1/Ashr/OTEL events, tool calls, errors, latency, media refs, hashes, idempotency. | Yes | Gets A3 out of fixture-only ceiling. |
| REPLAY-01 | Replay pack schema | Include case ids, trace ids, tool calls, expected outputs, judge refs, media metadata, payload hashes. | Yes | Turns incident review into product artifact. |
| REPLAY-02 | Replay runner receipt | reproduced/fixed/flaky/new-failure/not-runnable states with run-to-run diff. | Yes | Creates operational incident value. |
| JUDGE-01 | Calibration in gate health | Judge version, calibration matrix, drift, false-pass/false-block, confidence state. | Yes | Builds trust in automated blocking. |
| USAGE-01 | Usage event ids | Link imports, readbacks, views, revokes, verifier runs, archive bytes, retained days to summary id. | Yes | Billing-ready evidence. |
| USAGE-02 | Quota and chargeback preview | Read-only plan limits, forecasts, overage, team/project/repo chargeback. | Yes | Monetization without unsafe billing mutation. |
| API-01 | Versioned OpenAPI | Release evidence, readbacks, health, diff, review, report center, usage, webhooks, errors. | Yes | Enterprise integration readiness. |
| API-02 | Webhook dry-run receipts | health_changed, readback_changed, share_revoked, verifier_failed, archive_verified. | Yes | Lets enterprises plug A3 into release portals. |
| SELF-01 | Self-host smoke package | API, dashboard, SQLite/Postgres, object storage stub, worker, offline verifier, no cloud dependency. | Yes | Private deployment sales. |
| SELF-02 | Backup/restore/upgrade drill | Verify DB migration, object hashes, audit log, report snapshots, usage ledger, verifier packet. | Yes | Operations credibility. |
| E2E-01 | Current visual E2E | Dashboard, Report Center, hosted report, denied page, readback states, mobile. | No | Demo confidence and layout leak detection. |
| BILL-01 | Billing export | Stripe/invoice-ready metering file after admin approval, not live billing mutation. | No | Bridges pilot usage to revenue ops. |

## Work That Must Run In Parallel

Do not serialize the next round as "GitHub first, then audit later." The product becomes credible only when provider proof, tenant scope, evidence authority, and audit inventory arrive together.

| Parallel lane | Starts with | Must coordinate with | Why it must be parallel |
|---|---|---|---|
| A. CL/PR gate proof | CL-01, CL-02, CL-03, CL-05 | Auth, v2, Report Center, audit | External proof is the fastest money path, but it is unsafe without identity and stable ids. |
| B. Auth/RBAC/tenant | AUTH-01, AUTH-02, AUTH-03 | Readback worker, review identity, API docs | A fake worker or cross-tenant read kills trust instantly. |
| C. Evidence authority | V2-01, V2-02, V2-03, V2-04 | Every other lane | All surfaces need the same summary/source ids. |
| D. Report Center/Registry | RC-01, RC-02, RC-03, RC-04 | v2, audit, usage | Buyer-facing packet inventory must land as soon as stable ids exist. |
| E. Enterprise audit | AUD-01, AUD-02, AUD-03, AUD-04 | registry, v2, review, self-host | Offline proof and retention unlock larger contracts. |
| F. Review workflow | REVIEW-01, REVIEW-02, REVIEW-03 | auth, v2, audit, PR comments | Approvals matter only when bound to identity and exact artifacts. |
| G. Replay/trace/judge | TRACE-01, REPLAY-01, REPLAY-02, JUDGE-01 | A1/A2 projections, Report Center | Makes A3 useful after merge and reduces false-block objections. |
| H. Usage/API/platform | USAGE-01, USAGE-02, API-01, API-02 | v2, readback, report center | Monetization and integrations need stable event ids early. |
| I. Self-host/ops | SELF-01, SELF-02 | audit, registry, Postgres/RLS | Regulated buyers need private deploy proof, not only docs. |

Minimum order inside parallel execution:

1. Agree on `summary_id`, source snapshot ids, readback ids, artifact ids, and usage event ids.
2. Start readback worker, auth-bound scope, immutable v2 persistence, Report Center detail, and source artifact projections together.
3. Add offline verifier, identity-bound approvals, retention/legal hold, self-host package, and billing export once ids and audit events are stable.

## Money Direction Ranking

Required directions reviewed: PR gate, production replay, enterprise audit, self-host, trace ingestion, judge calibration, incident report, review workflow, billing/usage, API platform.

| Rank | Direction | Strength | Why | Required proof before selling hard |
|---:|---|---:|---|---|
| 1 | PR gate | 9.5/10 | Directly enters the merge path, has clear buyer budget, and builds on the newest readback/CL gate work. | Live Check/PR readback, branch-protection enforcement, worker auth, stale/missing tests. |
| 2 | Enterprise audit | 9/10 | Security/compliance buyers pay for retained, verifiable evidence that survives time and staff changes. | Offline verifier, signed archive, retention/legal hold, object storage custody. |
| 3 | Review workflow | 8.5/10 | Turns blocks into accountable human decisions and makes the PR gate operational. | Identity binding, signature verification, SLA/escalation, artifact-hash binding. |
| 4 | Production replay | 8/10 | Expands A3 from pre-merge gate to incident and regression operations. | Trace ingestion, replay pack, runner receipt, RCA export. |
| 5 | Trace ingestion | 8/10 | Creates data volume, daily use, and a non-fixture ceiling. | Versioned schema, idempotency, validation errors, A1/OTEL/Ashr adapters. |
| 6 | Self-host | 7.5/10 | Opens regulated/private-data deals and raises ACV. | Installable package, Postgres/RLS, object storage, backup/restore, offline verifier. |
| 7 | Billing/usage | 7/10 | Enables chargeback and expansion once product usage is real. | Usage event ids, quotas, billing export, entitlement model. |
| 8 | API platform | 7/10 | Helps enterprises embed A3 into release portals and automation. | OpenAPI, SDK examples, webhooks, compatibility tests. |
| 9 | Judge calibration | 6.5/10 | Reduces false-block objections and improves trust in decisions. | A2 calibration matrix, drift monitor, judge registry hash. |
| 10 | Incident report | 6.5/10 | Valuable expansion surface after replay exists. | RCA generator, incident-to-regression promotion, integrations. |

Strongest money direction:

```text
PR gate is the strongest single direction.
```

Strongest money package:

```text
Enforced Agent PR/CL Gate
  + Release Evidence Authority
  + Enterprise Audit Packet
  + Identity-Bound Review Workflow
```

This beats selling "production replay" first because PR/CL gate is budgetable immediately: it sits where engineering teams already accept required checks, branch protection, CI gates, and code-review controls. Production replay and trace ingestion should still run in parallel because they make the gate useful after incidents and increase long-term usage volume.

## Sell / Do Not Sell Yet

Can sell for controlled pilot:

- Readback-capable CL/PR gate workflow.
- API-backed release evidence health.
- Hosted evidence packet with report lifecycle.
- Report Center evidence inventory.
- Dry-run-first GitHub Check/PR comment publishing.
- Hash-sealed review records and audit bundle direction.
- Read-only usage/chargeback foundation.
- Self-host readiness plan and local SQLite durability proof.

Do not sell yet as production-enterprise:

- Enforced required GitHub gate.
- SOC2-grade compliance posture.
- Real SSO/RBAC reviewer approvals.
- Cryptographically verified production signatures.
- Full production Postgres/RLS/object-storage custody.
- Real billing/entitlement/checkout/invoice enforcement.
- Complete self-host install/backup/restore/upgrade offering.
- Full trace ingestion and executable production replay loop.

## Auditor Call

A3 should not spend the next round on broad dashboard expansion. The product is closest to money when it becomes release infrastructure:

> Every risky agent CL gets a required gate, every gate points to one immutable evidence packet, every reviewer decision is identity-bound, every external artifact is redaction-cleared, and every auditor can verify the packet offline.

Build the enforcement proof, not another decorative surface.
