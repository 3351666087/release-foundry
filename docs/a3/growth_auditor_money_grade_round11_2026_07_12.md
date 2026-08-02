# A3 Growth Auditor / Money-Grade Round 11 - 2026-07-12

> Current independent audit snapshot for the A3 trusted-access and release
> publication boundary. Round 10 is historical pre-fix evidence. This document
> records the post-fix state and does not claim production validation.

## 1. Scope

- Branch: `agent/a3-main-contract-alignment-v2`.
- Strategy authority:
  `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
- A1 authority: identity, sessions, tenant membership, runtime, credentials,
  GitHub worker, usage, billing, storage, and deployment.
- A2 authority: evidence snapshot, judge, score, pass/fail, failure class,
  Decision Ledger, and Release Decision.
- A3 authority: product workflow, route authorization mapping, review/report
  UX, publication orchestration, and commercial UI.
- Audit rule: local code, tests, OpenAPI, SQLite, and screenshots are local
  implementation evidence. They are not customer-like production proof.

## 2. Executive Verdict

**Local/contract merge: GO. Production hosted Release Authority: NO-GO.**

The branch now fails closed for the previously discovered direct-start and
standalone-CLI live publication bypasses. It also proves local five-level
resource isolation, structured SQLite receipt/outbox persistence, honest
Partial/DB readiness UI, and exact runtime/OpenAPI parity.

It still lacks deployed A1 and A2 authority services, tenant GitHub App
installation and credential custody, production PostgreSQL/RLS, real GitHub
readback/enforcement, customer IdP, multi-instance transactions, and
deployment/recovery proof. Therefore it may be merged as an explicitly local,
contract, and dry-run implementation, but it may not be sold or described as
a production live merge gate or compliance signing system.

## 3. Finding Closure

| # | Original finding | Current status | Evidence and remaining boundary |
|---|---|---|---|
| 1 | Direct startup could default to demo authority | **Resolved** | `a3_api_server.mjs` defaults to `hosted_enforced` regardless of `NODE_ENV`; demo requires explicit configuration. |
| 2 | Standalone GitHub CLI could publish live without trusted authority | **Resolved** | `a3_github_publish_cli.mjs` rejects live mode before token lookup or transport. The example Action is read-only and dry-run. |
| 3 | Foreign-only waiver could satisfy exception approval | **Resolved** | Approval resolves waiver by source plus all five scope fields; the same ID in another tenant returns `invalid_approval`. |
| 4 | Recomputed A2 hashes proved integrity but not A2 identity | **Partial** | Hosted live requests now require a server-only `a2_trusted_service` resolver, exact ledger selectors, allow, release-ready, and five-level scope. No deployed signed or mTLS A2 authority service exists yet. |
| 5 | GitHub repository and credential were not tenant-bound | **Partial** | Hosted live requests require an A1 tenant installation resolver, exact repo and scope, and `a1_trusted_worker`. No production GitHub App installation, token custody, or worker is wired yet. |
| 6 | SQLite GitHub/outbox durability relied on an all-state JSON blob | **Resolved locally** | `github_publish_receipts` and `event_outbox` are dedicated SQL tables. Restart tests query both tables directly. SQLite is not production custody. |
| 7 | Same source name could overwrite another tenant snapshot | **Resolved locally** | Snapshot identity is source plus five-level scope hash. Same source, run ID, case ID, and idempotency key coexist across two tenants in tests. PostgreSQL/RLS proof remains open. |
| 8 | Health always claimed `db_ready=true` | **Resolved** | Fixture/memory health and dashboard storage report false. The SQLite adapter alone reports true in this repository state. |
| 9 | Empty state could hide Partial-scope exclusion | **Resolved** | `DataBoundary` renders the Partial warning before returning empty content. Desktop/mobile browser coverage remains bounded. |
| 10 | Runtime RBAC and OpenAPI differed | **Resolved contractually** | Synchronizer and tests prove `53/53` protected runtime operations with matching permissions. Two additional documented GETs are the intended public health/share routes. |

## 4. Security Properties Now Implemented

1. Browser role, identity, tenant, service-account, and hosted-session claims
   are not authority in hosted mode.
2. A per-request A1 trusted principal resolver is mandatory for protected
   hosted routes.
3. Unknown hosted routes fail closed and persist metadata-only denial audit.
4. Live GitHub publication cannot use fixture A2 evidence as an authenticity
   substitute.
5. Live publication requires four independent server-side conditions: trusted
   principal, trusted A2 authorization, trusted A1 executor, and tenant-bound
   GitHub target.
6. Client API base URL and token environment routing cannot reach the live
   executor.
7. Waiver and approval records remain exact-scope and separation-of-duties
   evidence. They do not rewrite A2's original decision.
8. New snapshot, receipt, audit, and outbox records retain source and all five
   scope values in the local reference path.
9. UI green state requires verified A2 `allow`; missing, unknown, review,
   block, or invalid integrity remains fail-closed.
10. Fixture and memory stores no longer present themselves as a ready database.

## 5. Verification

Main rollout verification:

- Full A3 Node: `387 pass / 0 fail`.
- Fresh-port Playwright: `33 pass / 0 fail`.
- Next.js TypeScript and production build: passed, 14 generated pages.
- A1 TypeScript session lifecycle: `35 pass / 0 fail`.
- A2 trusted spine: `7 pass / 0 fail`.
- Commercial guard: passed, 0 blockers and 0 advisories.
- Hygiene guard: passed, 0 findings.
- `git diff --check`: passed.
- Changed A3 text-file high-confidence secret scan: 0 matches.
- `.env.local`: ignored and absent from Git status.

Independent auditor replay:

- Focused security/parity tests: `79 pass / 0 fail`.
- `git diff --check`: passed.
- Repository files were not modified by the auditor.

## 6. Remaining Production Blockers

1. Deploy an A1 identity/session/service-account verifier and connect it to the
   A3 per-request principal resolver.
2. Deploy an A2 trusted authority service with authenticated attestation or a
   signed decision transport, rather than a test-injected function.
3. Use a tenant-owned GitHub App installation mapping with KMS-backed token
   custody and an A1 worker.
4. Move authoritative data to PostgreSQL with forced RLS, complete five-level
   keys, transaction tests, backup, restore, and failover evidence.
5. Prove real GitHub check/comment readback and required-branch-check
   enforcement on an approved non-production repository.
6. Close customer IdP, SSO/SCIM, deployment, upgrade, rollback, observability,
   load, incident, and recovery evidence.
7. Audit malformed JSON and protected OPTIONS attempts consistently.

## 7. Allowed Product Claim

Allowed:

> A3 provides a tested local and contract implementation of a fail-closed
> product console, review/report workflow, trusted-authority adapters, tenant
> scope isolation, dry-run GitHub publication planning, and structured local
> evidence persistence.

Not allowed:

> A3 is already a production multi-tenant SaaS, live GitHub merge gate,
> compliance signing authority, or fully deployed enterprise Release OS.
