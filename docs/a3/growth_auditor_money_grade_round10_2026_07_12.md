# A3 Growth Auditor / Money-Grade Round 10 - 2026-07-12

> Historical audit snapshot. The resource-isolation, principal-validation,
> denial-schema, share-token-time, unknown-route-audit, and demo live-mutation
> findings below drove follow-up implementation in the same worktree. Use the
> independent Round 11 audit and
> `docs/a3/a3_trusted_read_access_contract_2026_07_12.md` addendum for current
> status; do not quote the pre-fix verdict below as the final branch state.

## 0. Audit Scope and Evidence Rules

- Repository: `ashr-codex-factory`.
- Branch inspected: `codex/a3-main-contract-alignment-v2`.
- Audited state: the current uncommitted worktree, including the trusted-read-access source, OpenAPI, webapp, test, contract, and screenshot changes visible on 2026-07-12.
- Strategy authority: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
- Prior auditor baseline: `docs/a3/growth_auditor_money_grade_round9_2026_07_11.md`.
- Round contract: `docs/a3/a3_trusted_read_access_contract_2026_07_12.md`.
- Ownership boundary: this is an independent audit. No ordinary code was edited. A1 remains authoritative for identity, sessions, tenant membership, persistence, usage, billing, workers, storage, and deployment. A2 remains authoritative for judge, policy, score, pass/fail, Decision Ledger, and Release Decision semantics.
- Verification restraint: at the user's direction, no full or focused test suite was run by this auditor. The only current-round executed result recorded in repository evidence is `6 pass / 0 fail` for the OpenAPI contract command in the trusted-read contract. New test source and screenshots are inspectable artifacts, but they are not treated as independently rerun evidence.
- Round 9's `290 Node / 18 Playwright / 138 Python plus 987 subtests` results predate this worktree and do not prove this round's diff.

### Status vocabulary

| Status | Meaning in this audit |
| --- | --- |
| Implemented | Executable code exists and focused test code exists; where no current run was observed, that limitation is stated. |
| Contract-supported | OpenAPI, schema, fixture, documentation, migration shape, or local reference implementation exists. |
| Production-validated | Deployed in a customer-like environment with real identity, authoritative storage, isolation, operations, failure, recovery, and security evidence. |

No item in this round is classified as production-validated. In particular, this audit does not claim hosted login, PostgreSQL/RLS, or production deployment is complete.

## 1. Executive Money Verdict

### 1.1 Verdict

**Conditional implementation pass; production and money-grade launch fail.** The round materially reduces the risk of forged browser authority on A3 reads when the server is explicitly run in `hosted_enforced` mode with a server-side principal resolver. It also adds fail-closed read-audit persistence, removes browser-declared role headers from the Next.js client, and gives users distinct 401/403 states.

It does not close the Round 9 P0 set. The A1 verifier is still an injected function rather than a deployed login/session integration; the default non-production server mode still accepts demo assertions; downstream run, case, report, dashboard, and several aggregate reads do not consistently bind five-level trusted scope to the resource query; default storage remains fixture-memory; PostgreSQL/RLS is absent; and the dry-run publish-state P0 is unchanged.

### 1.2 Money-grade scorecard

| Dimension | Score | Auditor conclusion |
| --- | ---: | --- |
| Local/demo sellability | 8/10 | Better security story and clearer access-denied UX improve a controlled design-partner demo. |
| Paid-pilot risk posture | 6/10 | Explicit hosted enforcement can support a tightly operated integration pilot, but only with external A1 principal resolution and strict non-production claims. |
| Hosted SaaS readiness | 2/10 | No hosted login closure, production A3 database, RLS, resource-bound five-level isolation, or deployment proof. |
| Enterprise/self-host value | 4/10 | The trusted-principal adapter boundary and metadata audit shape are useful integration assets, but the full self-host product and customer IdP path remain shells. |
| Tenant data protection | 4/10 | Caller-to-principal scope equality is implemented; resource-to-principal row/object equality is not consistently implemented. |
| Audit posture | 7/10 local, 2/10 production | Allow/deny events, outbox metering, SQLite persistence, and fail-closed audit availability are valuable locally; no authoritative Postgres/object custody or retention proof exists. |
| Contract consistency | 5/10 | OpenAPI and docs are strong, but they omit seven protected runtime GETs and disagree with runtime denial and principal-kind shapes. |
| Production validation | 0/10 | No customer-like deployment, live A1 login, Postgres/RLS, load, failover, restore, or security review evidence was supplied. |

### 1.3 Sellability and price effect

- The sellable offer remains a **design-partner or self-managed evaluation**, not hosted multi-tenant SaaS or enterprise release authority.
- This round reduces a serious security objection and can shorten a technical pilot review. It does not justify raising the Round 9 price ceiling because no new production authority, custody, deployment, or billing capability became real.
- The defensible near-term offer remains approximately CNY 50k-150k for a scoped implementation pilot or CNY 50k-120k/year for a supported self-managed evaluation, with explicit limitations.
- Hosted Team ARR and enterprise/self-host ACV remain targets, not current offers. A buyer cannot yet verify customer IdP login, durable tenant isolation, RLS, disaster recovery, or an authoritative release transaction.

## 2. Round 9 Closure Decision

| Round 9 finding | Round 10 status | Independent evidence and decision |
| --- | --- | --- |
| P0: client-asserted identity can authorize local and potentially live external actions | **Partially closed, still P0** | `hosted_enforced` ignores browser role/actor headers and consumes `resolveTrustedPrincipal` (`services/report/a3_api_server.mjs`; `tests/a3/a3_hosted_api_access.test.mjs`). However, the executable defaults to `demo_contract` outside `NODE_ENV=production`; `buildAuthContextFromRequest()` still accepts `hosted_session` and service-account assertions in demo mode; `authorizeLiveGitHubPublish()` accepts those states for live requests. A demo process holding a real GitHub token therefore retains the Round 9 unsafe shape. No A1 verifier implementation is wired. |
| P0: publish/sign-off state can overstate dry-run/local readiness | **Not addressed** | No relevant release-state implementation changed. `services/report/a3_live_ops_control_plane.mjs` remains outside this diff. Contract labels for trusted reads do not make GitHub posting, readback, A2 decision authority, or evidence custody live. |
| P0: production persistence is not on the executable path | **Not addressed** | Access decisions now persist in memory and test-injected SQLite, but `createA3ApiHandler()` still defaults to `createFixtureBackedA3Store()`. There is no production A3 Postgres adapter, migration application path, pool, RLS, backup, or failover. |
| P1: sensitive read routes are not consistently authorized | **Substantially advanced, not closed** | A request-wide hosted guard covers the runtime registry and fails unknown routes closed. It records allow/deny decisions before handler execution. But trusted scope is often rewritten only into query selectors; run/case handlers pass only `source`, reports commonly match only organization/project, and several aggregate reads do not validate the stored resource's full five-level scope. |
| P1: Postgres tenant isolation is documented, not implemented | **Not addressed** | No PostgreSQL adapter or executable RLS policy was added. SQLite persistence is not RLS evidence. |
| P1: pricing truth conflict | **Not addressed** | No pricing catalog or billing-authority change is in this round. |
| P1: self-host packets ahead of deploy evidence | **Not addressed** | No full A1+A2+A3 installer, customer IdP drill, upgrade, backup, restore, or restricted-network evidence was added. |
| P1: incomplete cross-lane PR checks | **Not proven closed** | New focused tests exist, but no current full cross-lane CI result or required-check artifact was supplied. |
| P2: hygiene/maintainability | **Improved locally, not independently test-proven** | The route registry centralizes access policy, but it adds a large new module and keeps duplicated scope/auth paths in the API server. Final quick diff check is recorded below. |

**Round 9 P0 closure verdict: no.** One important hosted-read attack path is reduced, but all three P0 findings are not closed and the identity P0 still has a demo/live-mutation escape path.

## 3. Implemented, Contract-Supported, and Production-Validated

### 3.1 Implemented in this worktree

- A route registry derived from canonical A3 RBAC operations, with hosted and demo modes.
- A request-wide hosted access guard that resolves a server-supplied principal and rejects missing, untrusted, expired, malformed, under-permissioned, or scope-mismatched requests.
- Hosted unknown-route fail-closed behavior.
- Five required scope fields on the principal and on request scope assertions.
- Metadata-only allow/deny event envelopes, `api_requests` usage metering, event-outbox rows, and fail-closed behavior when access-audit persistence is unavailable.
- Memory and SQLite persistence hooks for access decisions.
- Same-origin cookie fetch behavior in the webapp, without `x-a3-role` or browser tenant headers.
- Distinct Chinese-first 401, 403, not-found, network, and server-failure UI states; stale dashboard data is cleared during reload/source changes.
- Removal of wildcard CORS response headers from the local A3 API response helpers.
- Hosted tests for forged headers, missing resolver, permission denial, query/body scope mismatch, audit unavailability, and public exceptions.

### 3.2 Contract-supported only

- `A1VerifiedSession` and `A1ServiceAccount` OpenAPI schemes.
- The `TrustedPrincipal` concept and A1/A3 ownership boundary.
- Twenty-eight protected OpenAPI GET operations with RBAC, scope, usage, audit, and sanitized denial metadata.
- Two public read exceptions: health and opaque share-token capability.
- Browser-session and service-account verification expectations.
- Full five-level row/object isolation as a stated requirement.
- Production Postgres/RLS, durable audit custody, hosted identity, and self-host identity integration remain contract goals, not implemented runtime capabilities.

### 3.3 Production-validated

None. There is no production or customer-like proof for hosted login, principal verification, Postgres/RLS, multi-instance operation, durable queue/outbox delivery, object custody, backup/restore, deployment, load, failover, or incident recovery.

## 4. Material Audit Findings

### P0 - Demo mode can still promote client assertions into live GitHub authority

`configuredRouteAccessMode()` defaults the handler to `demo_contract`. In that mode, `buildAuthContextFromRequest()` still accepts body/query/header role, `hosted_session`, service-account, actor, and tenant values. `authorizeLiveGitHubPublish()` allows a live request when that derived auth state is `hosted_session` or `service_account`. The direct executable selects hosted mode only under `NODE_ENV=production` or explicit configuration.

This means the trusted-read guard is not a universal trusted-principal boundary. A local/evaluation server with a real token in its environment can retain the exact external-mutation risk identified in Round 9. Demo mode must be technically incapable of live external mutation, regardless of request fields or token availability.

### P0 - Five-level request equality is not five-level resource isolation

The guard proves that explicit query/body scope assertions equal the resolved principal. When no assertion is supplied, the server copies the principal scope into the request URL. That is useful request normalization, but it is not proof that the selected row/object belongs to the principal.

Concrete gaps:

- `/api/a3/runs`, `/api/a3/runs/{runId}`, and `/api/a3/cases/{caseId}` call store methods with `source` only.
- `getDashboardSnapshot()` receives actor/auth context, not a mandatory data-access scope filter.
- Report matching and report tenant helpers compare only organization and project.
- Several aggregate stores call `snapshotWithScope()`, which can overlay requested scope onto a selected snapshot rather than reject a differently scoped resource.
- Release evidence handlers pass organization/project only, not tenant/workspace/environment.

The new cross-scope tests reject forged selectors before handler execution, but they do not seed two tenants and attempt to read a resource ID owned by the other tenant. Until that adversarial resource test passes against the authoritative store, the contract's row/object isolation requirement is not achieved.

### P1 - OpenAPI, runtime route registry, and denial schemas drift

- Runtime policy protects 35 non-public GET routes; OpenAPI describes 28. Missing OpenAPI reads include DB contract, DB migrations, release-decision provenance, release-evidence diff, release readbacks, admin actions, and `/reports/{reportId}`.
- The OpenAPI tests prove every non-public read *present in the spec* is protected; they do not prove every runtime read is represented in the spec.
- OpenAPI denial schemas permit only `schema_version`, `error`, and optional `request_id`, while runtime 401/403 bodies also emit `message`.
- The contract names principal kinds `browser_session | service_account`; runtime canonicalization reports `user | service_account | workload`, and accepts a workload shape not declared by this round's OpenAPI alternatives.

The runtime behavior is generic and does not expose the missing permission, but contract drift undermines generated-client, security-review, and conformance claims.

### P1 - Access audit is locally useful but not authoritative custody

Hosted mode correctly refuses a protected request if `recordAccessDecision()` is unavailable or fails. The event is metadata-only and emits an `api_requests` usage meter. This is strong local behavior.

However, memory and SQLite are the only wired stores in this round. The event and business read are not shown inside one Postgres transaction or durable cross-service protocol, SQLite restart evidence is test-local, and no retention, immutable object custody, SIEM export, backup, or multi-instance ordering is proven.

### P1 - Current test evidence is narrower than the claim surface

The repository records `6 pass / 0 fail` for the OpenAPI contract test. New Node tests and Playwright interception coverage are present, but this auditor did not rerun them at the user's direction. There is no current evidence for:

- two-tenant seeded resource-ID isolation;
- demo-mode live-mutation denial with a token available;
- all runtime GETs represented in OpenAPI;
- a real A1 session or service-account verifier;
- Postgres/RLS integration;
- multi-instance audit durability;
- customer-like deployment or recovery.

## 5. This Round's Concrete Growth Points

| ID | Concrete point | Result | Evidence and boundary |
| --- | --- | --- | --- |
| R10-01 | Central sensitive-route registry | **Achieved, implemented** | `services/report/a3_route_access_control.mjs` derives routes from `A3_AUTHZ_OPERATION_POLICIES`; focused registry tests exist. |
| R10-02 | Hosted server-side principal resolver hook | **Achieved, implemented** | `resolveTrustedPrincipal`/`trustedPrincipalResolver` is consumed before handlers. It is an adapter hook, not an A1 implementation. |
| R10-03 | Ignore forged browser role/actor headers in hosted mode | **Achieved, implemented** | Hosted API tests assert trusted viewer/auditor authority wins over `x-a3-role`. |
| R10-04 | Missing resolver fails protected reads with 401 | **Achieved, implemented** | Hosted API test verifies forged browser authority cannot substitute for principal resolution. |
| R10-05 | Expired/untrusted/malformed principal denial | **Achieved, implemented** | Route-access tests cover expiry, trust flag, and incomplete scope. No real revocation service is involved. |
| R10-06 | Canonical RBAC permission enforcement | **Achieved, implemented** | Static role permissions are intersected with resolver-supplied permissions; 403 tests exist. Durable role bindings are absent. |
| R10-07 | Five required principal scope fields | **Achieved, implemented** | Organization, tenant, workspace, project, and environment are validated in the guard. |
| R10-08 | Reject mismatched query and nested body scope assertions | **Achieved, implemented** | Hosted test covers project mismatch and recursively nested mutation scope. |
| R10-09 | Unknown hosted routes fail closed | **Achieved, implemented** | Unregistered hosted routes produce a denial before ordinary handler fallback. |
| R10-10 | Public health exception | **Achieved, implemented** | Health remains public and reports access mode plus `production_auth_claimed: false`. `db_ready: true` remains misleading. |
| R10-11 | Public opaque share-token exception | **Achieved, implemented/contract-supported** | Route registry and OpenAPI distinguish capability access; existing store uses digest lookup and lifecycle status. No production custody proof. |
| R10-12 | Generic 401/403 response and `no-store` | **Partially achieved** | Runtime messages are generic and response helpers set `no-store`; runtime body shape disagrees with OpenAPI's closed schemas. |
| R10-13 | Metadata-only access decision evidence | **Achieved, implemented** | Principal/request/trace are fingerprinted; raw body, path values, cookies, credentials, and actor identity are excluded by construction/tests. |
| R10-14 | Fail closed when access audit cannot persist | **Achieved, implemented** | Hosted API returns 503 before the business handler if persistence is unavailable. |
| R10-15 | Access usage metering and event outbox | **Achieved, implemented locally** | `recordAccessDecision()` emits `api_requests: 1` and an outbox row. Delivery/reconciliation is not proven. |
| R10-16 | SQLite access-audit restart persistence | **Achieved locally, not production** | SQLite wrapper persists after access decisions; restart test source exists. SQLite is not the enterprise authority path. |
| R10-17 | Broad runtime GET protection | **Achieved at route-entry level** | The runtime registry covers 35 non-public GETs, plus protected writes. Resource-query isolation remains incomplete. |
| R10-18 | OpenAPI protected-read expansion | **Achieved as contract** | Twenty-eight GETs declare verified A1 security, permission, five-level scope, usage, audit, and denial responses. Seven runtime GETs are omitted. |
| R10-19 | Remove browser-declared authority from Next.js fetch | **Achieved, implemented** | `apps/webapp/lib/api.ts` uses same-origin `credentials: "include"` and sends no `x-a3-role`/tenant headers. |
| R10-20 | Distinct unauthenticated and forbidden UX | **Achieved, implemented** | `DataBoundary` renders separate Chinese-first 401 and 403 states; Playwright interception test and screenshots exist. This does not prove login. |
| R10-21 | Clear stale data on auth/source failure | **Achieved, implemented** | Provider clears model/error state before reload/source change and ignores aborted stale requests. |
| R10-22 | Preserve A2 block semantics | **Achieved in local fixture path** | Hosted dashboard test asserts A2 `block` remains `blocked`; no A2 semantics were modified. |
| R10-23 | Full five-level resource row/object isolation | **Not achieved** | Run/case calls are source-only; report matching is organization/project-only; no cross-tenant seeded object-ID test. |
| R10-24 | Real A1 hosted login/session/service-account verification | **Not achieved** | Only a resolver callback and OpenAPI schemes exist. No deployed verifier, revocation, rotation, account lifecycle, or IdP evidence. |
| R10-25 | Production Postgres adapter and RLS | **Not achieved** | No runtime adapter or live RLS policy/test was added. |
| R10-26 | Production durable A3 persistence | **Not achieved** | Default store remains fixture-memory; SQLite remains local/test-injected. |
| R10-27 | Eliminate client-asserted live mutation in demo mode | **Not achieved** | Demo context still accepts `hosted_session`/service-account assertions and the live GitHub guard trusts the resulting state. |
| R10-28 | Authoritative publish/sign-off state | **Not achieved** | The Round 9 dry-run readiness P0 is unchanged. |
| R10-29 | Complete self-host identity and data path | **Not achieved** | No full A1+A2+A3 deployment, customer IdP, Postgres/RLS, upgrade, backup, or restore evidence. |
| R10-30 | Production deployment validation | **Not achieved** | No customer-like install, load, failure, security, recovery, or operations evidence. |

## 6. What Remains a Shell or Blocker

1. **Trusted principal resolver:** executable adapter interface, not a hosted A1 login/session implementation.
2. **`/login` user path:** useful UX destination, not proof of registration, login, recovery, MFA, revocation, or SSO.
3. **Static RBAC map:** executable authorization logic, not durable organization role bindings or ABAC policy administration.
4. **Five-level scope:** principal/request contract exists; full DB row/object enforcement does not.
5. **OpenAPI security schemes:** strong contract, not production credential verification.
6. **Access audit:** useful local evidence, not immutable production custody or multi-instance authority.
7. **SQLite:** local durability only, not the strategic PostgreSQL authority path.
8. **Postgres/RLS:** blocker; neither runtime adapter nor live RLS evidence exists.
9. **Default API store:** fixture-memory and therefore restart-unsafe for authoritative approvals, audit, usage, and reports.
10. **Health readiness:** `db_ready: true` is still hard-coded and cannot substantiate production data readiness.
11. **Demo mode:** contract simulation remains capable of influencing live GitHub authorization if real credentials are present.
12. **Release authority:** dry-run/local evidence can still be overstated by unchanged publish/sign-off aggregation.
13. **Browser screenshots:** prove rendering against intercepted/local responses, not a hosted identity flow.
14. **Self-host:** A1 scaffold does not equal a complete A1+A2+A3 enterprise release.
15. **Production operations:** no SLO, load, failure, backup/restore, upgrade/rollback, penetration, or customer environment proof.

## 7. Next Round: Executable Growth Points

The next round should close one trustworthy vertical path before adding more console surfaces. Every item below preserves A1/A2 authority.

| ID | Executable growth point | A1/A2 and API/DB/event/artifact contract | Tenant/auth/RBAC/usage/audit impact | Tests/evidence | Money outcome |
| --- | --- | --- | --- | --- | --- |
| MG10-01 | Make demo mode technically incapable of live external mutation | **A1:** secret/worker authority; **A2:** release state unchanged; **API:** reject `allow_live`/`dry_run=false` unless hosted; **DB:** no write; **event:** `live_mutation.denied`; **artifact:** denial receipt. | **Tenant:** trusted scope only; **auth:** hosted principal mandatory; **RBAC:** `release:review`; **usage:** denied-attempt meter; **audit:** metadata allow/deny. | Start server in demo mode with fake token transport; assert zero transport calls for forged hosted/session/service flags. | Closes the remaining identity P0 escape path and reduces credential-loss risk. |
| MG10-02 | Wire a real A1 browser-session verifier adapter | **A1:** session lookup, expiry, revocation, assurance; **A2:** abuse fixtures; **API:** immutable `TrustedPrincipal.v1`; **DB:** session/role read; **event:** auth decision; **artifact:** verifier conformance report. | Tenant derived only from membership; auth uses HttpOnly cookie; RBAC server-resolved; usage counts auth decisions; audit hashes session/actor. | Real Go/A1 HTTP verifier integration tests for valid, expired, revoked, rotated, wrong-domain, and wrong-tenant sessions. | Unlocks credible hosted design-partner login and security review. |
| MG10-03 | Wire A1 service-account verification | **A1:** opaque key verification/rotation; **A2:** credential-abuse cases; **API:** service principal; **DB:** key hash/scope; **event:** service auth decision; **artifact:** rotation receipt. | Tenant fixed to account scope; auth never accepts boolean flags; RBAC least privilege; usage attributed to service account; audit fingerprints key ID. | Valid/revoked/expired/rotated/wrong-scope/bearer-replay integration matrix. | Enables CI and enterprise automation without human cookies. |
| MG10-04 | Freeze one exact trusted-principal schema | **A1:** emits schema; **A2:** validates security invariants; **API:** only `browser_session|service_account`; **DB:** versioned binding refs; **event:** schema version; **artifact:** JSON Schema/OpenAPI parity report. | All five scope fields required; auth assurance explicit; RBAC permissions immutable; usage principal-kind dimension; audit schema versioned. | Contract tests reject `user`, `workload`, unknown fields/kinds, missing assurance, and incompatible versions. | Reduces integration ambiguity and enterprise review time. |
| MG10-05 | Add a mandatory scoped repository interface for every tenant read | **A1:** tenancy contract; **A2:** evidence ownership unchanged; **API:** handlers pass `AccessScope`; **DB:** five-column predicates; **event:** scoped read; **artifact:** route-to-repository map. | Tenant scope cannot be overlaid onto a resource; auth context is the only source; RBAC checked before query; usage scoped; audit records query class. | Static test fails any tenant handler that calls a store without all five scope fields. | Removes the largest remaining data-exfiltration blocker. |
| MG10-06 | Enforce five-level scope for run and case reads | **A1:** Run/Case ownership keys; **A2:** grades join read-only; **API:** scoped list/detail; **DB:** composite predicates/indexes; **event:** run/case read; **artifact:** isolation report. | Tenant/resource match required; auth/RBAC `project:read`; usage list/detail meters; audit 404/deny without existence oracle. | Seed two tenants with colliding IDs; assert list/detail/case cannot cross organization, tenant, workspace, project, or environment. | Makes core evidence browsing credible for multi-tenant pilots. |
| MG10-07 | Enforce five-level scope for reports, manifests, and hosted-by-ID reads | **A1:** object/report ownership; **A2:** evidence refs immutable; **API:** scoped report endpoints; **DB:** full scope columns; **event:** report read; **artifact:** manifest ownership proof. | Tenant and object scope match; auth required for ID routes; RBAC `project:read`; usage report-view meter; audit 404 for cross-tenant IDs. | Two-tenant colliding report IDs plus revoke/view/manifest tests; share-token path remains separately capability-scoped. | Protects the most externally visible customer artifact. |
| MG10-08 | Enforce five-level scope for dashboards and aggregate control planes | **A1:** scoped aggregate APIs; **A2:** scoped decision/evidence feeds; **API:** no source-only selection; **DB:** scoped aggregates; **event:** aggregate read; **artifact:** aggregate lineage manifest. | Tenant scope fixed from principal; role-specific RBAC; usage aggregate query cost; audit source and scope fingerprints. | Cross-tenant fixtures for dashboard, usage, billing, admin, review, live ops, outbox, and evidence spine. | Prevents high-volume aggregate leakage and enables real workspace onboarding. |
| MG10-09 | Generate OpenAPI from the runtime route registry or enforce exact parity | **A1/A2:** ownership annotations retained; **API:** all 35+ GETs represented; **DB:** N/A; **event:** route contract build; **artifact:** generated diff manifest. | Tenant/auth/RBAC/usage/audit metadata required on every protected operation. | Bidirectional test: every runtime route is in OpenAPI and every OpenAPI operation resolves to a runtime policy. | Lowers buyer integration risk and prevents undocumented security surfaces. |
| MG10-10 | Align runtime denial bodies with closed OpenAPI schemas | **A1:** request ID source; **A2:** disclosure tests; **API:** exact 401/403 schema; **DB:** N/A; **event:** denial metadata; **artifact:** conformance result. | No tenant/role/permission leakage; auth category retained; RBAC details internal; usage denial meter; audit correlates hashed request ID. | Black-box schema validation for every denial class and malformed credential. | Improves client reliability and security-review confidence. |
| MG10-11 | Add a production A3 Postgres store | **A1:** Postgres ownership/connection contract; **A2:** decision refs; **API:** store selected by explicit production config; **DB:** migrations/pool/transactions; **event:** transactional outbox; **artifact:** migration receipt. | Five-level tenant keys mandatory; auth/RBAC before transactions; usage durable; audit durable and queryable. | Live Postgres CRUD/restart/concurrency/idempotency tests; production boot refuses memory/SQLite. | Converts the pilot from restart-unsafe demo to durable service foundation. |
| MG10-12 | Implement and verify RLS defense in depth | **A1:** DB session tenant context; **A2:** security verification; **API:** transaction-local scope; **DB:** `ENABLE/FORCE RLS` and policies; **event:** RLS denial; **artifact:** policy inventory. | Tenant isolation survives handler defects; auth maps principal to DB context; RBAC separate from RLS; usage/audit rows also scoped. | Live Postgres tests with two roles/tenants, pooled-connection reset, migration rollback, and bypass-role denial. | Required for hosted security approval and higher ACV. |
| MG10-13 | Make access audit and business read consistency explicit | **A1:** durable audit/outbox; **A2:** evidence audit rules; **API:** one correlation ID; **DB:** same transaction where possible or durable intent protocol; **event:** allow/deny/read-complete; **artifact:** reconciliation report. | Tenant scope immutable; auth/RBAC decision linked; usage exactly once; audit gaps detected. | Inject DB/outbox failures before/after read and prove no silent unaudited success or duplicate metering. | Makes audit claims defensible and lowers compliance risk. |
| MG10-14 | Replace hard-coded health readiness with dependency checks | **A1:** DB/queue/identity health; **A2:** judge dependency status; **API:** liveness/readiness split; **DB:** migration version check; **event:** readiness transition; **artifact:** health report. | Health exposes no tenant data; auth not required for liveness; RBAC for detailed diagnostics; usage excluded; audit operator diagnostics. | Stop DB/verifier/outbox and assert readiness fails without leaking configuration. | Prevents false production readiness and shortens operations triage. |
| MG10-15 | Add hosted boot-time configuration gates | **A1:** verifier, DB, KMS/secret refs; **A2:** required decision endpoint; **API:** startup refuses unsafe mode; **DB:** production store mandatory; **event:** boot validation; **artifact:** signed preflight result. | Tenant/auth/RBAC providers required; usage/audit backends required before serving; demo mode visibly isolated. | Production-mode matrix for missing resolver, memory store, absent audit, insecure cookie, and demo/live conflict. | Reduces deployment misconfiguration risk and procurement objections. |
| MG10-16 | Implement durable role bindings and scoped ABAC | **A1:** org/project/environment memberships; **A2:** reviewer conflict rules; **API:** role-binding reads; **DB:** versioned bindings; **event:** grant/revoke; **artifact:** effective-access export. | Tenant-specific roles; strong auth/re-auth for grants; RBAC+ABAC server evaluation; active-seat usage; complete audit. | Grant/revoke/session-refresh, stale cache, environment restriction, reviewer conflict, and break-glass tests. | Unlocks enterprise delegation and separation-of-duties sales. |
| MG10-17 | Put reports and bundles under A1 object-storage custody | **A1:** S3/MinIO, KMS, retention; **A2:** verifier/redaction; **API:** scoped signed download; **DB:** metadata/ownership; **event:** object lifecycle; **artifact:** checksum/signature manifest. | Tenant prefix and encryption context; auth/RBAC download policy; usage bytes/jobs; audit create/read/revoke/expire. | Cross-tenant object tests, tamper, expired URL, key rotation, missing object, and restore. | Turns local exports into an enterprise evidence-custody offer. |
| MG10-18 | Define the authoritative release-decision state machine | **A1:** durable workflow and integrations; **A2:** sole Decision Ledger authority; **API:** explicit contract/dry-run/live/readback/enforced states; **DB:** append-only transitions; **event:** transition; **artifact:** decision packet. | Tenant-scoped release; authenticated approvers; RBAC/separation of duties; usage workflow meter; immutable audit. | Prove dry-run/local records can never reach enforcement-ready; stale/invalid A2 decisions fail closed. | Closes Round 9's second P0 and creates the core paid value proposition. |
| MG10-19 | Move GitHub mutation to an A1-owned durable worker | **A1:** queue, secret custody, retries; **A2:** gate input; **API:** enqueue only; **DB:** job/outbox/idempotency; **event:** attempts/results; **artifact:** redacted receipt. | Tenant installation ownership; service-account auth; RBAC release permission; usage delivery attempts; audit request-to-result chain. | Rate limit, retry, duplicate, token rotation, revoked install, wrong repo, and DLQ replay tests. | Enables a sellable live integration without exposing tokens to A3. |
| MG10-20 | Require live GitHub readback before enforcement-ready | **A1:** GitHub App readback/webhook; **A2:** decision remains authoritative; **API:** branch-protection/check state; **DB:** receipt linkage; **event:** readback confirmed; **artifact:** signed readback packet. | Tenant/repo binding; auth via app installation; RBAC audit/release roles; usage polling/webhook; audit immutable receipt. | Sandbox repository end-to-end publish, webhook signature, branch protection, stale SHA, and reconciliation tests. | Converts demo integration into enforceable release automation. |
| MG10-21 | Ship a complete self-host identity/data profile | **A1:** API, identity, Postgres, queue, object storage; **A2:** judge/policy; **API:** A3 web/BFF; **DB:** migrations/RLS; **event:** full outbox; **artifact:** versioned install bundle. | Customer IdP/local admin; tenant bootstrap; RBAC role mapping; local usage/license; operator audit. | Clean VPC install with OIDC, A1+A2+A3 smoke, offline mode, restart, upgrade, and uninstall. | Opens data-residency and security-sensitive enterprise deals. |
| MG10-22 | Prove backup, restore, upgrade, and rollback | **A1:** DB/object/queue operations; **A2:** version compatibility; **API:** operator jobs; **DB:** PITR/migration; **event:** operation lifecycle; **artifact:** RPO/RTO receipt. | Operator-only auth/RBAC; tenant-consistent restore; backup-byte usage; complete audit. | Corrupt DB/object, restore to clean environment, N-1 to N upgrade, rollback/forward-fix, and audit continuity. | Removes a common self-host procurement veto. |
| MG10-23 | Require the cross-lane security matrix in CI | **A1/A2:** identity, tenancy, persistence, security suites; **API:** contract parity; **DB:** Postgres/RLS job; **event:** CI evidence; **artifact:** signed test manifest. | Verify tenant/auth/RBAC/usage/audit invariants on every relevant diff. | Required Node, Playwright, Python, TS, Go, Rust, Postgres, secret scan, and `git diff --check`; no skipped required jobs. | Prevents regression of the claims buyers evaluate. |
| MG10-24 | Productize audit search/export and SIEM delivery | **A1:** durable audit/object/webhook delivery; **A2:** redaction verifier; **API:** cursor/filter/export; **DB:** append-only indexed audit; **event:** export lifecycle; **artifact:** signed archive/offline verification. | Auditor role; tenant-scoped filters; strong auth for export; usage export bytes/jobs; audit-the-audit records. | Pagination/order/tamper/large export/cross-tenant/SIEM retry and verifier-version tests. | Creates a concrete enterprise upsell from this round's strongest local capability. |

## 8. Recommended Execution Order

1. **Immediate P0:** MG10-01, MG10-02, MG10-03, MG10-05, MG10-06, MG10-07, MG10-08.
2. **Contract and durability:** MG10-04, MG10-09, MG10-10, MG10-11, MG10-12, MG10-13, MG10-14, MG10-15.
3. **Core money path:** MG10-18, MG10-19, MG10-20, MG10-17.
4. **Enterprise ACV:** MG10-16, MG10-21, MG10-22, MG10-24.
5. **Non-regression:** MG10-23 must start with the first group and remain required.

The narrowest money-grade next path is:

```text
real A1 principal -> five-level scoped Postgres query -> RLS
-> durable metadata audit -> A2 Decision Ledger
-> queued GitHub publish -> live readback -> signed evidence packet
```

## 9. Evidence Register and Verification Limits

| Evidence | Observed result | Auditor interpretation |
| --- | --- | --- |
| Branch and worktree inspection | Correct requested branch; trusted-read changes are uncommitted | Auditable current state, but not an immutable release or commit. |
| `docs/a3/a3_trusted_read_access_contract_2026_07_12.md` | Records OpenAPI focused test `6 pass / 0 fail` | Current repository-recorded result; not independently rerun in this audit. |
| `tests/a3/a3_route_access_control.test.mjs` | 10 focused test definitions inspected | Strong source-level coverage of guard semantics; no execution claim here. |
| `tests/a3/a3_hosted_api_access.test.mjs` | 7 hosted black-box test definitions inspected | Covers forged authority and request-scope mismatch; lacks resource-owned-by-other-tenant fixture. |
| `tests/a3/a3_access_audit_persistence.test.mjs` | 3 persistence test definitions inspected | Covers local memory/SQLite evidence; not Postgres or multi-instance proof. |
| `tests/a3/a3_webapp_trusted_access.test.mjs` | 3 webapp contract test definitions inspected | Covers cookie fetch and stale-state behavior at source/test level. |
| `tests/e2e/a3-webapp-product-routes.spec.ts` | Added intercepted 401/403 browser test and two screenshots | Rendering evidence only; no hosted login/session flow. |
| OpenAPI v2 | 28 protected GETs and two public GETs | Strong contract subset; seven protected runtime GETs are absent. |
| Full suite | Not run by instruction | No current full Node, Playwright, A1/A2, Postgres, or cross-language pass claim. |
| Production evidence | None | No hosted login, Postgres/RLS, production deployment, load, failure, or recovery claim. |

## 10. Final Auditor Decision

### Approved claims

- A3 now has an implemented hosted-mode route-entry guard for trusted, server-supplied principals.
- Hosted mode materially rejects forged browser role and tenant assertions before protected handlers.
- Broad protected-route RBAC, generic denial, metadata-only access audit, local metering/outbox, and audit-unavailable fail-closed behavior exist.
- The webapp no longer sends browser-declared A3 role authority and has clearer 401/403 handling.
- A2 decision semantics remain read-only in this round.
- OpenAPI and documentation provide substantial trusted-read contract support.

### Rejected claims

- Round 9 P0 findings are closed.
- Hosted login or production A1 identity integration is complete.
- Five-level tenant isolation is enforced on every DB row/object read.
- Production PostgreSQL or RLS is implemented.
- Access audit has production-grade immutable custody.
- The default A3 server is a durable production data plane.
- The current OpenAPI exactly covers all runtime reads.
- Dry-run publish/sign-off is authoritative or production-safe.
- Complete self-host or production deployment is validated.

### Release recommendation

Accept this round as a **valuable contract and local implementation increment** for a design-partner branch. Do not market or release it as production hosted authorization, production multi-tenant isolation, enterprise self-host completion, or governed release authority. The next merge should be conditioned on demo live-mutation denial, resource-bound five-level isolation tests, OpenAPI/runtime parity, and an explicit plan to put the path on Postgres/RLS with a real A1 principal verifier.
