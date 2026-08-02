# P3 Growth Auditor Release Evidence V2 - 2026-07-08

Role: Growth-Auditor / Money-Grade Auditor

Scope: PR #18 local ahead work on branch `agent/a3-audit-evidence-bundle`.

Write boundary: this documentation artifact only.

Safety boundary:

- Did not read `.env.local`.
- Did not call live ReleaseFoundry, GitHub, billing, hosted auth, database, object storage, or cloud APIs.
- Did not modify runtime code, tests, fixtures, env files, generated reports, or secrets.
- Reviewed local strategy/worklog/code/test evidence only.

## Audit Inputs

Required documents read first:

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- latest sections of `docs/a3/worklog.md`

Local ahead evidence reviewed:

- `git status --short --branch`: branch is ahead of `origin/agent/a3-audit-evidence-bundle` by 1 commit.
- Ahead commit: `22e5f37 Add A3 release evidence authority guardrails`.
- Ahead diff scope: 12 files, 1074 insertions, 56 deletions.
- Main changed areas:
  - `services/report/a3_release_evidence.mjs`
  - `services/report/a3_store.mjs`
  - `services/report/a3_api_server.mjs`
  - `services/report/a3_sqlite_store.mjs`
  - `tests/a3/a3_release_evidence.test.mjs`
  - A3 API/store/SQLite test updates
  - `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`

Additional current working-tree observation:

- During this audit, the local worktree also showed uncommitted release-evidence v2 changes in:
  - `services/report/a3_api_server.mjs`
  - `services/report/a3_release_evidence.mjs`
  - `services/report/a3_store.mjs`
  - `tests/a3/a3_release_evidence.test.mjs`
- Those changes add a partial `a3.release_evidence_summary.v2` builder, API version negotiation, an `evidence-health` route, and a v2 additive/tenant-scoped unit test.
- I did not revert or modify those code files in this audit pass. This artifact treats them as local worktree evidence, not as completed production claims.

Local verification run during this audit:

```text
node --test tests/a3/a3_release_evidence.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_sqlite_store.test.mjs
```

Result:

```text
14 tests
14 pass
0 fail
```

Also reviewed earlier worklog evidence that the implementation round reported:

```text
node --check services/report/a3_release_evidence.mjs
node --check services/report/a3_store.mjs
node --check services/report/a3_api_server.mjs
node --check services/report/a3_sqlite_store.mjs
node --test tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/shareable_report.test.mjs tests/a3/report_center_index.test.mjs tests/a3/artifact_registry.test.mjs tests/a3/a3_sqlite_store.test.mjs
```

Reported result:

```text
20 pass
0 fail
```

## Money-Grade Verdict

A3 is no longer just a dashboard/report demo. The current PR #18 ahead work moves it into an early commercial control-plane shape: release evidence now has health, next action, deterministic hash identity, scoped report reads, hosted-report lifecycle linkage, SQLite tenant persistence, and safer internal-error redaction.

Commercial rating: `B- for sellable pilot`, `C for enterprise production`.

Why it can sell a pilot:

- It can explain release readiness in a buyer-readable way.
- It can show evidence health and next action instead of only static report text.
- The current worktree includes a partial v2 summary object with tenant scope, A1/A2 evidence counts, GitHub/PR readback placeholders, required-check proof state, usage linkage, redaction, and compliance placeholders.
- It has local tenant-scope negative tests for release evidence and reports.
- It has hosted report lifecycle, revoke/view audit, artifact registry, usage ledger, and SQLite persistence.
- It has dry-run/live-capable GitHub Check and PR comment publisher code paths, with live disabled unless explicitly opted in.

Why it is not production-enterprise yet:

- Required-check proof is still plan-only, not branch-protection readback.
- GitHub Check and PR comment readback are not live-confirmed.
- Auth/RBAC is not enforced by real middleware.
- Tenant scope is passed through local options/query/body, not bound to authenticated identity.
- The partial v2 summary is not yet persisted as an immutable authority table and is not yet wired through every surface as the single source of truth.
- SQLite proves local persistence, but production Postgres/RLS/object storage are not implemented.
- Billing remains read-only and not tied to an invoice/subscription ledger.
- Review approvals are durable records, but not cryptographically or SSO-bound production sign-off.

Most profitable direction: sell `Release Evidence Authority + GitHub Required Gate + Audit Bundle` as an enterprise release-control layer for AI agents. This is the clearest buyer pain, shortest path to budget, and strongest differentiation versus generic eval dashboards.

## What Is Real Commercial Capability Now

1. Release evidence is becoming an authority object.
   - Current work adds `release_evidence_health`, `next_action`, and sanitized diff helpers.
   - This supports buyer questions like "what blocks this release?" and "what evidence can I show auditors?"

2. Tenant leakage risk is being addressed locally.
   - Release evidence, report detail, manifest, view, revoke, list routes, dashboard inputs, report center, artifact registry, product console, and usage ledger now have scoped filtering or guards.
   - This is critical for SaaS credibility.

3. Hosted report lifecycle is buyer-legible.
   - Shareable reports can expire, be revoked, and record view/revoke audit events.
   - Denied hosted pages omit report body evidence.

4. Evidence surfaces are converging.
   - Dashboard, Report Center, Artifact Registry, hosted reports, usage ledger, audit bundle, signed archive, GitHub Check, and PR comments are all moving toward one release evidence packet.

5. The implementation is honest about non-claims.
   - The docs and worklog repeatedly state no live GitHub, no branch protection mutation, no real billing/auth/team/cloud mutation, and no `.env.local` access.

## Toy Capabilities And Required Upgrades

| Current capability | Toy/prototype limitation | Upgrade required before enterprise sale |
|---|---|---|
| `a3.release_evidence_health.v1` | Derived from local summary data; not yet canonical persisted authority. | Persist health with summary id, content hash, source receipt ids, and state machine history. |
| Partial `a3.release_evidence_summary.v2` | Builder/test exists in current worktree, but it is additive/local and not yet a durable system of record. | Store v2 summaries immutably, expose stable API docs, and require every surface to reference the same `summary_id`. |
| Required-check plan | Plan artifact can be mistaken for enforcement. | Branch-protection readback must prove `ReleaseFoundry Release Gate` is actually required. |
| GitHub Check publisher | Live-capable but not live-evidenced in this pass. | Add readback receipt: check id alias, conclusion, head SHA match, stale/missing/deleted states. |
| PR comment publisher | Can build/upsert, but no live readback evidence. | Add marker/body hash readback and stale/deleted/missing states. |
| Tenant scope guards | Query/body/options-based local guards, not authenticated tenant identity. | Bind org/project scope to A1 auth middleware, session, API key, or service account. |
| SQLite store | Good local proof; not production durability. | Add Postgres migrations, RLS, indexes, transaction tests, backup/restore drill. |
| Hosted report snapshots | Snapshot metadata exists, but v2 immutable source-change tests need to be stronger. | Persist immutable summary snapshots by id/hash and prove source mutation does not alter shared evidence. |
| Usage ledger | Read-only billing-adjacent evidence. | Join release evidence summary ids to usage events, quota, retained bytes, and invoice previews. |
| Review workflow | Durable waiver/approval records, but identity is not production-bound. | Bind reviewer to SSO/OIDC/GitHub identity, role, signer key, expiry, separation-of-duties result. |
| Redaction | Strong local scrubbing, but external publish eligibility is not one fail-closed policy. | One redaction firewall must gate JSON, Markdown, CSV, HTML, Check, PR, manifest, bundle, archive, logs, and screenshots. |
| Artifact registry | Registry entries exist, but not yet storage-backed chain of custody. | Persist registry rows, object hashes, retention class, legal hold, and verifier receipts. |
| Self-host readiness | Contract/docs exist. | Offline verifier packet, install command, local object storage, license/activation boundary, and backup/restore evidence. |

## Next Growth Points

Legend:

- Pay: directly helps customers decide to pay.
- Risk: lowers launch/merge/security risk.
- Ent: supports enterprise, self-host, audit, or compliance.
- ACV: can raise contract size or unlock enterprise tier.

| ID | Growth point | Next executable target | Pay | Risk | Ent | ACV |
|---|---|---|---|---|---|---|
| G-01 | Release evidence v2 authority object | Complete the partial `a3.release_evidence_summary.v2` into a persisted authority contract with immutable snapshots, source receipt ids, health history, readbacks, ledger, storage, retention, and compliance fields. | yes | yes | yes | yes |
| G-02 | API version negotiation | Keep v1 default and add explicit v2 response on `GET /api/a3/releases/:releaseId/evidence-summary`. | yes | yes | yes | no |
| G-03 | Compact evidence health endpoint | Add `GET /api/a3/releases/:releaseId/evidence-health` for dashboard, monitor, PR gate, and CI reads. | yes | yes | yes | no |
| G-04 | Auth-bound tenant scope | Replace local query/body tenant trust with A1-authenticated org/project/session/API-key scope. | yes | yes | yes | yes |
| G-05 | Two-tenant negative test suite | Seed two tenants and prove release evidence, report detail, manifest, view, revoke, list, usage, audit, SQLite rows fail closed cross-tenant. | no | yes | yes | yes |
| G-06 | Immutable hosted summary snapshots | Persist snapshot id/hash/builder version and prove hosted report keeps original evidence after source data changes. | yes | yes | yes | yes |
| G-07 | Evidence diff API | Add `GET /api/a3/releases/:releaseId/evidence-diff?from=&to=` with no raw evidence leakage. | yes | yes | yes | no |
| G-08 | GitHub Check readback | Store generated, posted, readback-confirmed, stale, missing, deleted, permission-denied, and error states. | yes | yes | yes | yes |
| G-09 | PR comment readback | Store marker hash, body hash, PR number, head SHA match, stale/missing/deleted states. | yes | yes | yes | no |
| G-10 | Required-check enforcement proof | Read branch protection and prove required check exists before claiming merge enforcement. | yes | yes | yes | yes |
| G-11 | Review identity binding | Bind approvals/waivers to provider subject alias, role, expiry, artifact hash, signer status, and separation-of-duties result. | yes | yes | yes | yes |
| G-12 | Cryptographic approval verification | Verify signature/key fingerprint and record verifier receipt before approval can affect release status. | yes | yes | yes | yes |
| G-13 | Redaction fail-closed publish policy | Compute `external_publish_allowed=false` unless every external artifact class passes redaction. | yes | yes | yes | yes |
| G-14 | External artifact class matrix | Cover JSON, Markdown, CSV, HTML, hosted report, GitHub Check, PR comment, manifest, bundle, archive, logs, screenshots. | no | yes | yes | yes |
| G-15 | Release evidence usage ledger linkage | Attach imports, snapshots, hosted views, denied views, revokes, verifier runs, retained bytes, and PR gate attempts to `summary_id`. | yes | yes | yes | yes |
| G-16 | Billing-ready quota preview | Add read-only quota status, overage preview, retained bytes, verifier count, hosted views, and PR gate event count. | yes | no | yes | yes |
| G-17 | Postgres migration contract | Add production-ready release evidence v2 tables, indexes, unique constraints, RLS-ready tenant columns, and migration tests. | yes | yes | yes | yes |
| G-18 | SQLite/Postgres parity tests | Prove local SQLite behavior and Postgres SQL contract agree on tenant keys, hashes, lifecycle rows, and idempotency. | no | yes | yes | yes |
| G-19 | Object storage artifact persistence | Store report/export/bundle/archive artifact refs with SHA-256, byte size, content type, retention class, and storage key alias. | yes | yes | yes | yes |
| G-20 | Offline self-host verifier | Export a packet and verifier command that validates summary, manifest, bundle, archive, and hashes without cloud access. | yes | yes | yes | yes |
| G-21 | Compliance retention states | Add retention policy, legal hold, purge eligibility, purge blocked reason, archive storage class, signer status, and audit chain ids. | yes | yes | yes | yes |
| G-22 | Webhook contract | Emit summary-created, health-changed, readback-changed, share-revoked, verifier-failed, archive-verified, retention-changed events. | yes | yes | yes | yes |
| G-23 | Idempotent summary recompute | Add idempotency keys and replay/conflict behavior for summary recompute and readback capture. | no | yes | yes | no |
| G-24 | Report Center authority manifest | Manifest must include summary id, snapshot id, diff id, readback ids, verifier ids, usage event ids, retention, legal hold. | yes | yes | yes | yes |
| G-25 | Artifact Registry authority entries | Add first-class entries for v2 summary, health, diff, readbacks, required-check proof, verifier receipts, webhooks, compliance packet. | yes | yes | yes | yes |
| G-26 | PR Gate required-check product flow | Add UI/API state for plan-only, configured, enforced, stale, missing permission, and head-SHA mismatch. | yes | yes | yes | yes |
| G-27 | Enterprise audit export | One export button should produce redacted audit packet: summary, report, manifest, bundle, archive verifier, usage, retention, review identities. | yes | yes | yes | yes |
| G-28 | Self-host install smoke | Add local self-host smoke path: SQLite/Postgres target, object storage stub, offline verifier, no cloud dependency. | yes | yes | yes | yes |
| G-29 | OpenAPI docs | Document v1/v2 summary, health, diff, manifest, webhook, error shape, idempotency, compatibility, redaction examples. | yes | yes | yes | no |
| G-30 | Playwright visual evidence | Capture Dashboard Release Evidence, War Room, Report Center, hosted report, denied page, and mobile state with leakage/layout assertions. | yes | yes | yes | no |
| G-31 | Enterprise admin read-only proof | Show org/project/team/API-key/billing/trust states as read-only evidence until real A1 identity/billing exists. | yes | yes | yes | yes |
| G-32 | Customer-facing pricing package | Create packaging docs for Team, Pro, Enterprise, Self-host Enterprise based on gates, retention, offline verifier, SSO, required checks. | yes | no | yes | yes |
| G-33 | Audit event chain hardening | Every release evidence state transition should append audit event with previous hash, actor, request id, and trace id. | yes | yes | yes | yes |
| G-34 | Stale evidence monitor | Add monitor that flags stale GitHub readback, stale hosted snapshot, expired waiver, missing verifier, and retention drift. | yes | yes | yes | yes |
| G-35 | Customer onboarding sample | Produce a safe sample customer flow: upload/import run, gate blocks, reviewer waiver, required check proof, hosted audit packet. | yes | yes | yes | yes |

## Priority Stack

### P0: Make the gate enforceable

Build:

- GitHub Check readback.
- PR comment readback.
- Branch-protection required-check readback.
- Required check proof must distinguish `plan_only`, `configured`, `enforced`, `stale`, `missing_permission`, and `wrong_check_name`.

Why this makes money:

- Buyers pay for a release gate that blocks bad agent releases, not for a report that only explains them.
- This is the shortest path to a paid DevSecOps / platform engineering pilot.

### P1: Make evidence immutable and auditable

Build:

- v2 summary snapshots.
- Summary hash and source receipt ids.
- Evidence diff.
- Report Center authority manifest.
- Offline verifier packet.

Why this raises ACV:

- Enterprise and regulated customers buy auditability, retention, chain of custody, and self-host verification.

### P2: Make tenant/auth/billing credible

Build:

- Auth-bound tenant scope through A1.
- Postgres/RLS migration.
- Usage ledger joined to summary id.
- Read-only quota/overage preview.

Why this reduces launch risk:

- Cross-tenant leakage and billing ambiguity are existential SaaS risks. Fixing these turns the product from a lab tool into a deployable control plane.

## Commercial Packaging Recommendation

Best paid wedge:

```text
ReleaseFoundry Release Evidence Authority for AI Agent PRs
```

Buyer promise:

```text
Every AI-agent release candidate gets a verifiable evidence packet, required GitHub gate, reviewer sign-off trail, hosted audit report, and offline verifier.
```

Suggested tiers:

| Tier | Sellable feature | Notes |
|---|---|---|
| Team | Local release evidence, hosted report, PR comment, basic GitHub Check dry-run/live publish. | Good for early pilots. |
| Pro | Required-check enforcement proof, evidence diff, immutable snapshots, usage ledger. | Best startup/team upsell. |
| Enterprise | SSO/RBAC reviewer identity, retention/legal hold, audit bundle/archive verifier, webhooks, compliance export. | Main ACV driver. |
| Self-host Enterprise | Offline verifier, Postgres/RLS, object storage, no-cloud packet validation, backup/restore drill. | Highest ACV and regulated buyer fit. |

## Audit Risks To Call Out Before Merge

1. Do not market required-check enforcement until branch-protection readback exists.
2. Do not market live GitHub evidence until readback is captured and tested.
3. Do not market production tenant isolation until A1 auth/RBAC binds org/project scope.
4. Do not market production billing until usage ledger rows connect to subscription/invoice state.
5. Do not market compliance retention until legal hold, purge eligibility, retention class, and offline verifier are implemented.
6. Do not allow a reviewer approval to unblock release without identity binding and signature verification.
7. Do not call a hosted report immutable unless snapshot content is persisted and source mutations are proven not to affect it.
8. Do not let internal errors include provider messages without redaction.

## Release Readiness Scorecard

| Area | Current score | Reason |
|---|---:|---|
| Buyer story | 8/10 | Strong release evidence and audit story. |
| PR gate monetization | 6/10 | Live-capable, but required-check/readback proof missing. |
| Enterprise audit | 6/10 | Bundle/archive/report registry exists, but v2 authority/offline verifier not complete. |
| Tenant safety | 5/10 | Local guardrails improved; auth-bound tenant enforcement missing. |
| Self-host | 4/10 | Contract shape exists; install/offline/Postgres/RLS path incomplete. |
| Billing/usage | 4/10 | Usage ledger exists; billing remains read-only. |
| Compliance | 4/10 | Retention/legal hold/purge/signer identity not complete. |
| Production operations | 3/10 | No real deployment, observability, webhooks, or incident drill. |

## Final Money Direction

The most profitable next round is:

```text
GitHub required-check readback + immutable release evidence v2 + offline audit verifier.
```

That combination turns A3 from "excellent evidence dashboard" into "agent release control system." It can block risky releases, prove why, satisfy auditors, and justify Enterprise/Self-host pricing.
