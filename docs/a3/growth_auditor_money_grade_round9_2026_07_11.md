# A3 Growth Auditor / Money-Grade Round 9 - 2026-07-11

## 0. Audit Scope, Baseline, and Non-Claims

- Repository: `3351666087/release-foundry`.
- Branch/commit audited: `agent/a3-commercial-growth-round4` at `978a1cb`.
- PR audited: draft PR #32, `[agent] Advance A3 commercial release console`, base `main`, GitHub merge state `CLEAN` at audit time.
- Diff size: 47 files, 6,414 insertions, 342 deletions. The PR changes A3 dashboard/report/read-model/test/doc surfaces; it does not modify A1 runner/billing/storage implementation or A2 judge/release-policy implementation.
- A1/A2 authority remains read-only. A1 is authoritative for runner, ingestion, worker, storage, usage, billing, identity, and backend enforcement. A2 is authoritative for judge, failure taxonomy, release policy, security verification, and evidence correctness. This audit does not propose changing those semantics.
- Audit evidence is pinned to tracked files at the commit above. Concurrent untracked work from other agents was excluded.
- `mock`, `fixture`, `official-demo`, injected `fetch`, local memory, JSON-file, SQLite, contract-ready, plan-only, preview-only, and dry-run evidence are not called live.
- No local environment file or secret value was read. Public-safe secret-reference contracts are discussed only at the level already documented by the repository.

## 1. Executive Money Verdict

### 1.1 One-sentence verdict

PR #32 materially improves the product's **decision-compression and enterprise sales demo**, but it does not yet create a production SaaS control plane: the honest sell today is a paid design-partner pilot or self-managed evaluation package, not a multi-tenant release authority, billing system, compliance product, or live hosted service.

### 1.2 Scorecard

| Dimension | Score | Money-grade conclusion | Current evidence |
| --- | ---: | --- | --- |
| Demo sellability | 8/10 | A buyer can understand release evidence, review, export governance, and commercial blockers in one console. | `services/report/a3_live_ops_control_plane.mjs`; `services/report/a3_enterprise_readiness.mjs`; `tests/e2e/a3-dashboard-api-backed.spec.ts` |
| Paid-pilot utility | 6/10 | Local API + SQLite can support a tightly operated design-partner pilot, provided scope and non-live claims are explicit. | `services/report/a3_api_server.mjs`; `services/report/a3_sqlite_store.mjs`; `tests/a3/a3_sqlite_store.test.mjs` |
| Production hosted readiness | 2/10 | Hosted identity, trusted tenant context, production persistence, object custody, provider execution, and operational deployment are missing. | `services/report/a3_auth_rbac_boundary.mjs:233-261`; `services/report/a3_api_server.mjs:18-22`; `docs/a1/self_host_runtime_scaffold.md` |
| Enterprise readiness | 3/10 | Buyer-question packets exist; SSO/SCIM, enforceable RBAC, RLS, legal retention, DR, and compliance evidence do not. | `services/report/a3_enterprise_readiness.mjs`; `services/report/a3_saas_admin.mjs:932-975` |
| Billing readiness | 2/10 | Usage and invoice previews are commercially useful prototypes, but no customer invoice or money movement is ready. | `services/report/a3_billing_readiness.mjs:52-73`; `docs/a1/payment_provider_readiness.md` |
| Audit/evidence posture | 6/10 local, 2/10 hosted | Hashing, redaction, manifests, archive verification, and lifecycle records are strong locally; durable custody and enforcement are not hosted-proven. | `tests/a3/a3_audit_archive.test.mjs`; `tests/a3/a3_security_redaction_guard.test.mjs`; `docs/a1/evidence/object_storage_contract_20260709.md` |
| Product truthfulness | 5/10 | Many surfaces label preview/dry-run correctly, but the new sign-off aggregation can promote dry-run/local evidence to `ready_for_governed_publish`. | `services/report/a3_live_ops_control_plane.mjs:202-267` |

### 1.3 Willingness to pay and price ceiling

These are auditor estimates, not repository facts or validated market research.

| Offer now | Likely buyer | Defensible price now | Why they may pay | Ceiling blocker |
| --- | --- | ---: | --- | --- |
| Design-partner implementation pilot | AI application team with painful manual release review | CNY 50k-150k one-time, 6-12 weeks | Trace/judge triage, review packet, report export, and GitHub workflow shape can replace spreadsheet/manual review work. | Customer must accept local/self-managed operation and limited integration authority. |
| Self-managed evaluation package | Technical team willing to operate local tooling | CNY 3k-10k/month equivalent support license, or CNY 50k-120k/year | Local SQL durability, evidence exports, release gate artifacts, and redaction have real operational value. | No complete installer, upgrade/backup proof, SSO, SLA, or support plane. |
| Hosted Team subscription | Not honestly sale-ready | Target after P0 closure: CNY 60k-180k ARR | Review workflow + GitHub + hosted evidence + usage can justify team budget. | Trusted auth/tenant enforcement, Postgres/RLS, live GitHub readback, entitlement and billing are absent. |
| Enterprise/self-host | Not honestly sale-ready | Target after enterprise closure: CNY 300k-1.2m ARR plus CNY 100k-400k services | Release authority, customer-controlled custody, SSO, audit export, compliance mapping, and support can reach security/procurement budgets. | Current self-host stack does not include the full A2/A3 product and lacks DR/compliance/identity proof. |

The highest current willingness to pay is for **release evidence triage and audit packet preparation**, not for usage billing, payment, compliance certification, or hosted policy enforcement.

## 2. What Became More Sellable in PR #32

| Capability added or strengthened | Classification | Customer value | Evidence and honest boundary |
| --- | --- | --- | --- |
| Commercial sign-off summary | Sellable demo/read model | Compresses reviewer, GitHub, report, trust, usage, billing, and collections posture for a release owner. | `services/report/a3_live_ops_control_plane.mjs:270-341`; browser coverage at `tests/e2e/a3-dashboard-api-backed.spec.ts:402`. It is derived local state, not an authoritative release transaction. |
| Release publish chain | Sellable concept, unsafe authority claim | Makes missing reviewer, GitHub, and report steps easy to scan. | `services/report/a3_live_ops_control_plane.mjs:202-267`; `tests/a3/report_builder.test.mjs:2422`. Dry-run/local records can currently satisfy readiness. |
| Reviewer/GitHub/share/audit timelines | Sellable operator UX | Gives one place to reconstruct the release narrative. | `services/report/a3_live_ops_control_plane.mjs:475-507`; `tests/a3/report_builder.test.mjs:2290`. Timeline entries are summaries, not a tamper-evident hosted event stream. |
| Export audience governance | Strong paid-pilot capability | Separates internal, executive, auditor, and customer-external outputs and keeps unsafe external publish blocked. | `services/report/a3_report_center.mjs`; `tests/a3/report_center_index.test.mjs`; `tests/e2e/a3-dashboard-api-backed.spec.ts:375`. |
| Enterprise decision packets | Strong sales-enablement capability | Gives reviewers, executives, and customers different evidence narratives. | `services/report/a3_enterprise_readiness.mjs:173-278`; `tests/a3/dashboard_wiring.test.mjs:932`. Packet contracts exist; there is no external trust publication service. |
| Hosted-vs-self-host posture | Useful procurement narrative | Helps sales and solutions engineering frame identity, storage, and usage ownership. | `services/report/a3_enterprise_readiness.mjs`; A1 scaffold at `infra/docker/docker-compose.self-host.yml`. It is a posture/contract, not a complete deployable product. |
| A1/A2 integration radar | Strong internal/product trust feature | Makes contract ownership and schema drift visible without changing A1/A2 semantics. | `services/report/a3_schema_drift_radar.mjs`; `tests/a3/a3_schema_drift_radar.test.mjs`; `apps/dashboard/src/components/a1-a2-contract-radar.mjs`. It reads tracked contracts, not live service discovery. |
| China-first billing narrative | Sales localization, not payment capability | WeChat Pay, Alipay, manual invoice, and CNY language better fit domestic procurement conversations. | `services/report/a3_billing_readiness.mjs:52-65`; `services/report/a3_saas_admin.mjs:705-804`; A1 explicitly labels provider evidence plan-only in `docs/a1/payment_provider_readiness.md`. |
| Commercial/admin escalation surfaces | Sellable demo | Seats, quota risk, procurement, trust blockers, and workspace posture now look connected. | `services/report/a3_saas_admin.mjs`; `apps/dashboard/src/components/saas-admin-console.mjs`; `tests/a3/report_builder.test.mjs:2470`. Mutations remain plan/preview-only. |
| Component extraction and responsive radar | Product-quality improvement | Reduces first-viewport overload and makes contract evidence legible on mobile. | Added dashboard components; `tests/e2e/a3-dashboard-api-backed.spec.ts:99-186`. The overall app remains a very large single-page console. |

## 3. Toy or Non-Live Capabilities That Must Stay Labeled

1. **Default A3 API data plane is fixture-memory.** `createA3ApiHandler()` defaults to `createFixtureBackedA3Store()` and source `mock`; the executable entry point does not wire SQLite or Postgres (`services/report/a3_api_server.mjs:18-22`, `867-871`; `services/report/a3_store.mjs:1868-1876`).
2. **SQLite is real local durability but test-injected only.** The adapter persists reports, review records, audit rows, and usage (`services/report/a3_sqlite_store.mjs:11-120`), but repository references show it is instantiated only by `tests/a3/a3_sqlite_store.test.mjs`.
3. **Billing is read-only preview.** `invoice_preview.status=preview_only`, pricing source is not configured, checkout is disabled, and customer invoice is false (`services/report/a3_billing_readiness.mjs`).
4. **A1 payment rails are plan-only.** The A1 contract explicitly forbids live checkout, charges, and CI provider calls (`docs/a1/payment_provider_readiness.md`).
5. **Notifications are channel plans/previews.** A3 defines Slack/Teams/email/webhook triggers and artifacts, while its own boundary says A1 must own delivery execution and secret custody (`services/report/a3_notification_control_plane.mjs`).
6. **GitHub live-shaped tests are transport-injected.** Publisher code can issue network requests when explicitly live, but tests inject fetch and do not prove a production GitHub App installation or PR #32 live publication/readback (`services/report/a3_github_integration.mjs:474-633`; `tests/a3/a3_github_integration.test.mjs`).
7. **Self-host is an A1 runtime scaffold.** Compose includes A1 API/worker/Postgres/Redis/MinIO, but not the complete A2 judge service, A3 web console, identity provider, migration operator, observability stack, or upgrade/backup workflow (`infra/docker/docker-compose.self-host.yml`; `docs/a1/self_host_runtime_scaffold.md`).
8. **Compliance is a preview label.** A3 reports `soc2_surface: evidence_only_preview` and preview retention, not SOC 2, ISO 27001, PIPL, MLPS, data residency, DPA, or legal-hold compliance (`services/report/a3_saas_admin.mjs:965-969`).
9. **Schema drift radar is tracked-file validation.** It proves current schemas match expected required fields and fails closed on synthetic drift; it does not negotiate deployed service versions (`tests/a3/a3_schema_drift_radar.test.mjs`).
10. **Official-demo and redacted fixtures are evidence samples.** Browser E2E proves the product shell against local API sources; it does not prove customer traffic, production scale, or live custody (`fixtures/a3/`; `tests/e2e/a3-dashboard-api-backed.spec.ts`).

## 4. Launch Blockers and Product-Truth Findings

### P0 - Client-asserted identity can authorize local and potentially live external actions

`buildAuthContextFromRequest()` accepts role, actor, `hosted_session`, service-account flag, organization, tenant, workspace, project, and environment from body/query/custom headers (`services/report/a3_api_server.mjs:696-708`). `buildA3AuthContext()` defaults to local developer and says enforcement is contract-only (`services/report/a3_auth_rbac_boundary.mjs:233-261`). The live GitHub guard treats this client-asserted hosted/session or service-account state as sufficient (`services/report/a3_api_server.mjs:740-762`).

Impact: if a deployed process has a GitHub token, an untrusted caller could self-assert reviewer/hosted context and request a live mutation. This blocks hosted launch. The fix belongs to A1 identity/session/service-account validation; A3 must consume a trusted principal and must never derive authority from request-declared role/session flags.

### P0 - The new publish/sign-off state can overstate dry-run/local readiness

`checkReady` and `commentReady` are true for any timeline status other than the literal `missing_contract`, while missing entries currently use `missing`; dry-run `planned` also counts ready (`services/report/a3_live_ops_control_plane.mjs:209-224`, `484-507`). `ready_for_governed_publish` needs approval + shareable report + checkReady, but does not require A2 authoritative gate pass, non-dry-run GitHub receipt, readback confirmation, immutable approval authority, durable artifact custody, or comment readiness.

Impact: a sales demo can display governed/commercial readiness from local records that would not survive enterprise control review. Split `contract_ready`, `dry_run_ready`, `live_posted`, `readback_confirmed`, and `enforcement_confirmed`; only the last admissible state may drive release authority.

### P0 - Production persistence is not on the executable path

The default server uses fixture-memory storage; SQLite is only test-instantiated; Postgres is a generated migration contract, not an A3 runtime adapter. A restart loses default API writes. This blocks hosted approvals, revocations, audit history, usage, and evidence authority.

### P1 - Sensitive read routes are not consistently authorized

Only selected routes call `authorizeRequest()`. Dashboard, run/case detail, report center, report detail/manifest, admin console, enterprise readiness, billing, usage, live-ops, notification, and review-workflow GETs are served without an authz check (`services/report/a3_api_server.mjs:33-146`, `220-269`, `355-382`, `416-493`, `536-568`, `647-651`). Tenant query parameters are filtering inputs, not authenticated scope.

### P1 - Postgres tenant isolation is documented, not implemented in the migration generator

`services/report/a3_sql_migrations.mjs` creates tenant columns and indexes but no `ENABLE ROW LEVEL SECURITY` or `CREATE POLICY`. The RLS example lives in `docs/a3/p3_sql_adapter_contract_2026_07_07.md`, and `tests/a3/sql_adapter_contract.test.mjs` statically checks that documentation. This is not executable RLS evidence.

### P1 - Hard-coded price labels conflict with unconfigured pricing truth

SaaS Admin emits CNY unit price labels (`services/report/a3_saas_admin.mjs:804-813`) while billing readiness correctly says each invoice line has `pricing_source: not_configured` and customer invoice is not ready (`services/report/a3_billing_readiness.mjs:148-161`). Price display needs a versioned catalog and entitlement contract or must be explicitly marked illustrative.

### P1 - Self-host and enterprise packets are ahead of deploy evidence

`packet_contract_ready` and `self_host_contract_visible` are reasonable contract labels, but the actual self-host stack omits A2/A3 and enterprise identity/operations. No backup/restore/upgrade, air-gap, telemetry, support bundle, RTO/RPO, or customer IdP drill is proven.

### P1 - PR checks do not exercise the full claimed cross-lane matrix

At audit time, GitHub reports success for `Plan and hygiene`, `A3 dashboard/report/evidence contracts`, and `CL Gate summary`; A1/A2 Python, TypeScript SDK, Go, Rust verifier, and pinned-evidence jobs are skipped. Local tests are strong, but merge protection currently does not prove all claims on PR #32.

### P2 - PR hygiene and maintainability are not closed

`git diff --check origin/main...HEAD` fails on trailing whitespace/new blank lines in seven tracked files, including corrupted-looking worklog command text. The PR adds over 6,000 lines and still concentrates extensive orchestration in `apps/dashboard/src/app.mjs` and `apps/dashboard/src/components/saas-admin-console.mjs`.

## 5. What Still Does Not Feel Like a Real Product

1. A caller chooses its own role and tenant instead of presenting a validated session or service credential.
2. Many read APIs have no authorization decision or audit read event.
3. The default server reports DB-ready while running fixture-memory storage (`services/report/a3_api_server.mjs:33-40`).
4. There is no production A3 Postgres adapter, migration application, RLS verification, pool, backup, or failover.
5. There is no authoritative release transaction joining A2 decision, reviewer authority, GitHub readback, artifact hash, and immutable audit event.
6. GitHub App installation, token rotation, webhook verification, branch-protection readback, retry, and reconciliation are not operated end to end.
7. There is no real organization onboarding, login, SSO, MFA, SCIM, invite, seat entitlement, or account recovery.
8. There is no real checkout, subscription, invoice, tax, refund, reconciliation, dunning, or entitlement enforcement.
9. There is no real notification delivery, provider installation, retry queue, dead-letter queue, preference center, or delivery receipt reconciliation.
10. Self-host does not launch the complete A1+A2+A3 product and has no upgrade/restore proof.
11. Audit exports are strong local artifacts but lack production object-storage custody, KMS signing, retention lock, legal hold, and verifier distribution.
12. Compliance labels are UI posture rather than mapped controls with owners, evidence periods, exceptions, and assessor-ready artifacts.
13. The product is still a very tall multi-console page rather than task-oriented routes with stable URLs, pagination, loading/error states, and role-specific navigation.
14. Pricing and plan names are hard-coded narrative, not a catalog tied to usage meters and entitlements.
15. Customer value is not measured: there is no activation funnel, time-to-first-run, time-to-decision, prevented-release count, reviewer SLA, or evidence-export conversion metric.

## 6. Next-Round Executable Growth Points

Each item below is independently testable and names the required cross-lane contract. A1/A2 inputs are consumed read-only; semantic ownership stays with A1/A2.

### MG9-01 - Replace client-asserted auth with an A1 trusted-principal adapter

- **A1/A2 input:** A1 session/service-account/API-key verification result; A2 cross-lane security rules remain verifier input.
- **API/DB/event/artifact contract:** `TrustedPrincipal.v1` injected by middleware; no body/query role or hosted-session authority; `auth.decision` metadata event.
- **Tenant/auth/RBAC/usage/audit impact:** derive tenant and actor from verified principal, enforce role bindings server-side, meter auth decisions, audit allow/deny without raw identity.
- **Test and evidence:** negative tests for forged role/session headers and expired/wrong-tenant credentials in `tests/a3/a3_api_server.test.mjs`; A1 contract anchors `docs/a1/schemas/saas_control_plane.schema.json` and `tests/a1/test_worker_quota_auth.py`.
- **Money outcome:** removes the largest hosted-pilot blocker and unlocks credible enterprise security review.

### MG9-02 - Authorize every non-public A3 read route

- **A1/A2 input:** A1 trusted principal and tenant middleware; A2 audit/privacy policy for readable evidence classes.
- **API/DB/event/artifact contract:** route-permission registry covering dashboard, run, case, report, manifest, admin, enterprise, usage, billing, live-ops, notifications, and review reads.
- **Tenant/auth/RBAC/usage/audit impact:** fail closed on missing auth, bind scope to principal, meter reads, emit sampled metadata-only read audit events for sensitive resources.
- **Test and evidence:** table-driven 401/403/200 tests across all routes; cross-tenant ID enumeration tests; current gap anchor `services/report/a3_api_server.mjs`.
- **Money outcome:** required before any customer data can be hosted.

### MG9-03 - Wire a production Postgres A3 store as the non-test server mode

- **A1/A2 input:** A1 Postgres connection/migration/tenant conventions; A2 persistence records remain immutable input.
- **API/DB/event/artifact contract:** `A3Store.v2` adapter interface, connection health, transaction boundaries, migration ledger, idempotent imports and review/report writes.
- **Tenant/auth/RBAC/usage/audit impact:** all writes carry principal-derived tenant/actor/request/trace IDs; append audit and usage in the same transaction or transactional outbox.
- **Test and evidence:** live Postgres integration test with restart persistence and concurrent idempotency; compare to local SQLite behavior in `tests/a3/a3_sqlite_store.test.mjs`.
- **Money outcome:** converts local demo writes into a deployable paid-pilot data plane.

### MG9-04 - Implement and verify Postgres RLS

- **A1/A2 input:** A1 organization/project identity and DB session context; A2 cross-lane tenant isolation cases.
- **API/DB/event/artifact contract:** executable `ALTER TABLE ... ENABLE/FORCE ROW LEVEL SECURITY` and policies for every tenant-owned A3 table; migration verification artifact.
- **Tenant/auth/RBAC/usage/audit impact:** DB-level isolation backs API checks; privileged worker bypass is explicit and audited; usage/audit remain tenant partitioned.
- **Test and evidence:** two-tenant negative integration tests for read/write/update/delete and worker role; replace documentation-only proof in `tests/a3/sql_adapter_contract.test.mjs`.
- **Money outcome:** unlocks enterprise multi-tenant conversations and lowers breach risk.

### MG9-05 - Define an authoritative release-decision state machine

- **A1/A2 input:** A1 run/artifact/readback IDs; authoritative A2 `release_gate.v1` decision and release-policy version.
- **API/DB/event/artifact contract:** immutable `ReleaseDecision.v1` with explicit `contract_ready`, `dry_run`, `live_posted`, `readback_confirmed`, `enforced`; optimistic version and transition events.
- **Tenant/auth/RBAC/usage/audit impact:** reviewer/owner separation of duties, actor-bound transitions, decision meters, immutable audit lineage.
- **Test and evidence:** transition matrix rejects dry-run as governed publish, rejects stale A2 policy and missing artifact hash; current overclaim anchor `services/report/a3_live_ops_control_plane.mjs:202-341`.
- **Money outcome:** makes the release gate a product authority instead of a summary card.

### MG9-06 - Require live GitHub readback before enforcement-ready status

- **A1/A2 input:** A1 GitHub App worker/secret custody; A2 release gate conclusion/reason.
- **API/DB/event/artifact contract:** publish job, sanitized publish receipt, check/PR-comment readback, required-check proof, head-SHA binding, freshness/expiry.
- **Tenant/auth/RBAC/usage/audit impact:** installation scoped to tenant/project, release reviewer permission, publish/readback usage meters, request/response hash audit.
- **Test and evidence:** one human-controlled sandbox repository run with check creation, PR comment upsert, readback, stale-SHA and deleted-check tests; code anchor `services/report/a3_github_integration.mjs`.
- **Money outcome:** closes the clearest buyer-visible integration and supports Team pricing.

### MG9-07 - Move external mutations to an A1-owned durable worker/outbox

- **A1/A2 input:** A1 queue/retry/dead-letter/idempotency contracts; A2 policy result is payload reference only.
- **API/DB/event/artifact contract:** `ExternalMutationRequested.v1`, worker lease, retry schedule, dead-letter event, redacted delivery receipt artifact.
- **Tenant/auth/RBAC/usage/audit impact:** API never resolves provider secrets; worker principal and tenant are bound; attempts are metered and audited.
- **Test and evidence:** crash/retry/duplicate/concurrency tests based on A1 worker evidence and `services/report/a3_event_envelope.mjs`.
- **Money outcome:** creates the operational substrate for GitHub, notifications, and billing webhooks in parallel.

### MG9-08 - Put reports and audit bundles under A1 object-storage custody

- **A1/A2 input:** A1 object manifest/signature/readback contract; A2 redaction/verifier result.
- **API/DB/event/artifact contract:** artifact upload/finalize/readback, immutable snapshot hash, signed URL policy, retention class, bundle root/signature.
- **Tenant/auth/RBAC/usage/audit impact:** tenant-prefixed keys, auditor/export permissions, byte/storage/download meters, view/revoke/export audit events.
- **Test and evidence:** MinIO integration with tamper, cross-tenant key, expiry, revoke, checksum and restart tests; anchor `docs/a1/evidence/object_storage_contract_20260709.md` explicitly says no live MinIO/S3 call today.
- **Money outcome:** strengthens audit, self-host, and enterprise evidence-custody value.

### MG9-09 - Version the pricing catalog and meter mapping

- **A1/A2 input:** A1 canonical usage events/rollups; A2 model/judge cost and risk policy.
- **API/DB/event/artifact contract:** `PricingCatalog.v1`, plan version, currency, effective dates, meter-to-price mapping, tax-exclusive flag, quote snapshot artifact.
- **Tenant/auth/RBAC/usage/audit impact:** billing-admin read/write, tenant plan assignment, usage replay against catalog version, catalog-change audit.
- **Test and evidence:** golden invoice calculations, currency/rounding/effective-date tests; remove conflict between `a3_saas_admin.mjs:804-813` and `a3_billing_readiness.mjs:148-161`.
- **Money outcome:** turns decorative pricing into quoteable packaging.

### MG9-10 - Join usage to the A1 billing ledger and reconciliation report

- **A1/A2 input:** A1 append-only usage and billing ledger replay semantics; A2 judge cost categories.
- **API/DB/event/artifact contract:** usage event IDs, rollup IDs, invoice line lineage, accepted/duplicate/conflict provider event state, reconciliation artifact.
- **Tenant/auth/RBAC/usage/audit impact:** billing admin only, tenant/customer/account binding, no double charging, every adjustment audited.
- **Test and evidence:** replay/duplicate/conflict and late-event tests using `docs/a1/evidence/billing_sql_semantic_contract.json` and A1 billing tests.
- **Money outcome:** enables defensible usage-based invoices and renewals.

### MG9-11 - Implement domestic hosted-payment sandbox rails

- **A1/A2 input:** A1 WeChat Pay/Alipay provider boundary and webhook verification; A2 abuse/cost policy.
- **API/DB/event/artifact contract:** hosted checkout/order plan, provider object ref, hash-only webhook envelope, payment state transition, refund/void reference.
- **Tenant/auth/RBAC/usage/audit impact:** billing-admin/owner controls, customer/account tenancy, payment-attempt usage, immutable finance audit with no credential payload.
- **Test and evidence:** provider sandbox only, signature rejection, duplicate webhook, test/live boundary and redaction tests; anchor `docs/a1/payment_provider_readiness.md` remains plan-only until this evidence exists.
- **Money outcome:** unlocks China-first Team checkout without claiming live money movement prematurely.

### MG9-12 - Enforce plan, seat, and feature entitlements

- **A1/A2 input:** A1 organization members, quota, subscription and ledger state; A2 judge-mode/cost restrictions.
- **API/DB/event/artifact contract:** `EntitlementSnapshot.v1`, seat assignment, feature flags, quota decision, grace-period and suspension events.
- **Tenant/auth/RBAC/usage/audit impact:** owner/billing-admin separation, tenant plan scope, denied usage events, entitlement-change audit.
- **Test and evidence:** downgrade, over-seat, grace, suspended invoice, reviewer-seat and free-auditor-seat tests; current narrative anchor `services/report/a3_saas_admin.mjs`.
- **Money outcome:** converts plans into collectible value and controls COGS.

### MG9-13 - Add budget controls and usage-to-value analytics

- **A1/A2 input:** A1 usage rollups/quota events; A2 blocked-release and judge outcome counts.
- **API/DB/event/artifact contract:** budget thresholds, alert event, runway forecast, prevented-risk metric, monthly value report artifact.
- **Tenant/auth/RBAC/usage/audit impact:** billing-admin config, reviewer read, threshold-evaluation usage, config/alert audit.
- **Test and evidence:** period rollover, spike, missing data, alert dedupe, timezone tests; replace preview controls at `services/report/a3_saas_admin.mjs:661-701`.
- **Money outcome:** supports renewal and expansion with ROI evidence, not only consumption totals.

### MG9-14 - Build real reviewer assignment and separation of duties

- **A1/A2 input:** A1 users/teams/role bindings; A2 approval requirements and release policy.
- **API/DB/event/artifact contract:** assignment, due date, delegation, approval signature, denial, waiver, expiry, conflict-of-interest decision.
- **Tenant/auth/RBAC/usage/audit impact:** actor identity is verified; self-approval and cross-project action denied; reviewer SLA metered; every transition audited.
- **Test and evidence:** owner/reviewer/billing-admin matrix, self-approval, expired waiver, reassignment and concurrent decision tests; build on `tests/a3/a3_review_workflow.test.mjs`.
- **Money outcome:** makes sign-off operationally useful for regulated teams.

### MG9-15 - Add SSO/OIDC/SAML, MFA, and SCIM enterprise identity

- **A1/A2 input:** A1 enterprise identity adapters/session lifecycle; A2 auth abuse and recovery cases.
- **API/DB/event/artifact contract:** provider config refs, domain claim, session assurance, MFA state, SCIM user/group sync receipt.
- **Tenant/auth/RBAC/usage/audit impact:** organization-bound identity, group-to-role mapping, login/role-change audit, active-seat usage.
- **Test and evidence:** IdP sandbox login, signed assertion validation, deprovisioning, group drift, MFA and tenant-domain takeover tests.
- **Money outcome:** major Enterprise ACV gate and procurement requirement.

### MG9-16 - Ship the complete self-host product profile

- **A1/A2 input:** A1 API/worker/Postgres/Redis/MinIO/telemetry; A2 judge service and policy packs.
- **API/DB/event/artifact contract:** version compatibility matrix, health/readiness endpoints, install manifest, seeded admin, migration receipt, support bundle.
- **Tenant/auth/RBAC/usage/audit impact:** customer IdP and local admin, RLS enabled, local license/usage policy, operator audit.
- **Test and evidence:** clean-machine compose/Kubernetes install launching A1+A2+A3, offline smoke, upgrade and uninstall; current partial anchor `infra/docker/docker-compose.self-host.yml`.
- **Money outcome:** opens higher-ACV security-sensitive and data-residency deals.

### MG9-17 - Prove backup, restore, upgrade, and disaster recovery

- **A1/A2 input:** A1 DB/object-store/worker state; A2 policy and result version compatibility.
- **API/DB/event/artifact contract:** backup manifest, restore receipt, migration version, object checksum inventory, RPO/RTO measurement artifact.
- **Tenant/auth/RBAC/usage/audit impact:** operator-only action, tenant-consistent restore, backup storage metering, full operator audit.
- **Test and evidence:** corrupt DB, missing object, point-in-time restore, N-1 to N upgrade, rollback/forward-fix and audit continuity drills.
- **Money outcome:** removes a common self-host and enterprise operations veto.

### MG9-18 - Implement real notification delivery and dead-letter operations

- **A1/A2 input:** A1 integration/webhook worker and secret references; A2 release/reviewer trigger policy.
- **API/DB/event/artifact contract:** channel installation, preference, trigger, delivery attempt, retry, DLQ, redacted receipt and replay event.
- **Tenant/auth/RBAC/usage/audit impact:** admin config/reviewer read, tenant channel isolation, delivery usage, connector/action audit.
- **Test and evidence:** Slack/Teams/email/webhook sandbox adapters, timeout/rate-limit/retry/dedupe/DLQ tests; current plan anchor `services/report/a3_notification_control_plane.mjs`.
- **Money outcome:** reduces reviewer SLA and makes the product part of daily operations.

### MG9-19 - Add customer webhook signing and replay protection

- **A1/A2 input:** A1 webhook delivery and secret custody; A2 privacy/redaction policy.
- **API/DB/event/artifact contract:** endpoint hash, signing-key ref, payload schema/version, signature headers, idempotency key, delivery/readback receipt.
- **Tenant/auth/RBAC/usage/audit impact:** tenant endpoint ownership, admin-only rotation, delivery/egress meters, replay/rotation audit.
- **Test and evidence:** signature verification, replay window, rotation overlap, SSRF allowlist, redaction, retry tests.
- **Money outcome:** unlocks enterprise automation and integration expansion.

### MG9-20 - Turn audit export into an evidence-custody product

- **A1/A2 input:** A1 audit/event/object storage; A2 verifier/redaction correctness.
- **API/DB/event/artifact contract:** append-only audit schema, cursor pagination, actor/resource/action filters, export job, signed archive, offline verifier receipt.
- **Tenant/auth/RBAC/usage/audit impact:** auditor role, scoped export, export-byte/job usage, audit-the-audit event.
- **Test and evidence:** ordering, pagination, tamper, missing entry, large export, cross-tenant and verifier-version tests; build on `tests/a3/a3_audit_archive.test.mjs`.
- **Money outcome:** one of the strongest Enterprise upsell paths already supported by local evidence quality.

### MG9-21 - Add retention, deletion, legal hold, and data-residency controls

- **A1/A2 input:** A1 storage lifecycle and tenant region; A2 privacy/evidence-required policy.
- **API/DB/event/artifact contract:** retention policy version, legal hold, deletion request/job/receipt, region pin, exception and immutable hold artifact.
- **Tenant/auth/RBAC/usage/audit impact:** security-admin/auditor split, tenant/project policy, retained-byte usage, every hold/delete audited.
- **Test and evidence:** expiry, hold precedence, delete propagation, object/DB consistency, region mismatch and restore tests.
- **Money outcome:** required for regulated procurement and credible compliance positioning.

### MG9-22 - Publish a control-to-evidence compliance matrix

- **A1/A2 input:** A1 identity/storage/audit/operations evidence; A2 security/privacy/verifier evidence.
- **API/DB/event/artifact contract:** control ID, framework, owner, implementation state, evidence query/artifact, period, exception, reviewer sign-off.
- **Tenant/auth/RBAC/usage/audit impact:** security-admin maintains, auditor reviews, evidence collection metered, control and exception changes audited.
- **Test and evidence:** machine validation that no `implemented` control lacks current evidence; start with SOC 2 common criteria, ISO 27001 mapping, PIPL/MLPS gap labels, never certification claims.
- **Money outcome:** turns `evidence_only_preview` into procurement-grade trust work.

### MG9-23 - Split the console into task routes with server-backed filters

- **A1/A2 input:** existing A1 run/trace and A2 grade/release inputs unchanged.
- **API/DB/event/artifact contract:** paginated/filterable run, review, report, audit, billing and integration query contracts with stable deep links.
- **Tenant/auth/RBAC/usage/audit impact:** route-level permissions, tenant scope from session, query usage meters, sensitive-view audit where required.
- **Test and evidence:** Playwright role-based navigation, reload/deep-link, empty/loading/error, pagination, mobile and accessibility tests; current long-page evidence `apps/dashboard/src/app.mjs` and `tests/e2e/a3-dashboard-api-backed.spec.ts`.
- **Money outcome:** improves repeat use, onboarding, demo clarity, and operator efficiency.

### MG9-24 - Make the full cross-lane evidence matrix required in PR CI

- **A1/A2 input:** current read-only A1/A2 contract suites and pinned artifacts.
- **API/DB/event/artifact contract:** CI manifest that maps changed paths to required A1/A2/A3/TS/Go/Rust/evidence jobs and records a signed summary artifact.
- **Tenant/auth/RBAC/usage/audit impact:** no runtime tenant change; CI verifies contract, redaction, usage and audit invariants before merge.
- **Test and evidence:** require currently skipped PR #32 jobs, `git diff --check`, pinned-evidence verification, secret scan, Node/Playwright/Python matrices.
- **Money outcome:** protects sales claims from drift and lowers enterprise release risk.

## 7. Parallel Groups and Money Direction

### 7.1 Parallel execution groups

| Group | Work items | Primary owner | Can run in parallel with | Exit condition |
| --- | --- | --- | --- | --- |
| G0 Trusted boundary | MG9-01, 02, 04, 14, 15 | A1 identity/DB primary, A2 security verification, A3 consumer/UI | G1 contract design and G2 pricing catalog | Forged identity/tenant tests fail closed; all routes have permission coverage; RLS live test passes. |
| G1 Release authority and custody | MG9-03, 05, 06, 07, 08 | A1 persistence/worker/storage, A2 decision authority, A3 workflow | G0, G2, G4 | Restart-safe decision state; live sandbox GitHub readback; object checksum/signature custody; no dry-run overclaim. |
| G2 Revenue engine | MG9-09, 10, 11, 12, 13 | A1 billing/usage, A2 cost policy, A3 billing/admin UX | G0 and G1 after contract stubs | Versioned catalog, reconciled invoice preview, enforced entitlements, domestic sandbox payment evidence. |
| G3 Enterprise/self-host/trust | MG9-16, 17, 20, 21, 22 | A1 infra/storage/identity, A2 verifier/privacy, A3 admin/export | G1 and G2 | Full-stack install/upgrade/restore, custody-backed audit export, control-evidence matrix with honest gaps. |
| G4 Integrations and product adoption | MG9-18, 19, 23, 24 | A1 workers/webhooks/CI, A2 trigger/security, A3 product | All groups | Delivered notification receipts, signed webhooks, task routes, required cross-lane CI. |

### 7.2 Money-direction order

1. **Stop false authority and secure tenant boundaries:** MG9-01, 02, 04, 05. No revenue claim is durable while callers choose identity or dry-run becomes governed publish.
2. **Make one release path truly live and durable:** MG9-03, 06, 07, 08, 14. A single production-quality GitHub + review + evidence flow is worth more than additional shells.
3. **Monetize the proven flow:** MG9-09, 10, 12, 13, then MG9-11. Catalog, ledger lineage, entitlements, and value analytics precede payment-provider breadth.
4. **Raise ACV with enterprise control:** MG9-15, 16, 17, 20, 21, 22. SSO, full self-host, DR, custody, and compliance evidence are the enterprise multiplier.
5. **Expand daily use and integrations:** MG9-18, 19, 23. Notifications, webhooks, and task routes improve retention once authority is trustworthy.
6. **Make quality non-regressing:** MG9-24 is immediate and continuous; it should land alongside the first group, not at the end.

The best immediate money direction is:

```text
trusted principal + authoritative release decision + durable Postgres/RLS
+ live GitHub readback + object-custodied audit packet
```

This is a narrower but more valuable direction than adding more admin cards, more plan labels, or more preview integrations.

## 8. Verification Performed This Round

| Verification | Result | Interpretation |
| --- | --- | --- |
| `node --test tests/a3/*.test.mjs` | 290 passed, 0 failed | Strong local A3 unit/contract coverage. Many tests use fixtures, local stores, or injected transports. |
| `node node_modules/playwright/cli.js test` | 18 passed, 0 failed | Browser-proves the current local API-backed dashboard and interactions. It does not prove hosted services. |
| Focused A1/A2 pytest set for billing, storage, SaaS control plane, contracts, release policy, cross-lane security, persistence | 138 passed, 987 subtests passed | Current read-only contracts are consistent with A3 consumption. |
| GitHub PR #32 checks | 3 success, 5 skipped | A3/hygiene summary is green; cross-language/cross-lane jobs are not all executed on this PR. |
| `git diff --check origin/main...HEAD` | Failed | Trailing whitespace/new-blank-line findings remain in tracked PR files. |
| Secret handling | No secret file read; A3 suites include redaction/secret scans | Supports public-safe audit only; it is not a production secret-manager test. |

The first Playwright invocation through `npx.ps1` was blocked by local PowerShell execution policy. Direct Node invocation of the installed Playwright CLI succeeded and all 18 tests passed, so this was a launcher limitation rather than a product-test failure.

## 9. Final Audit Conclusion

### Approved claims

- A3 is a serious local/API-backed release-governance console prototype.
- It consumes current A1/A2 contracts without changing their semantics.
- It has strong local evidence rendering, redaction, artifact/export, report lifecycle, review-record, schema-drift, and browser coverage.
- PR #32 improves buyer comprehension and paid-pilot demo quality.
- Local SQLite durability exists and is tested when explicitly injected.
- GitHub publisher/readback code paths and payment/notification/self-host contracts exist at clearly bounded levels.

### Rejected claims

- Production multi-tenant SaaS.
- Hosted auth or enterprise RBAC enforcement.
- Production Postgres/RLS A3 persistence.
- Live billing, customer invoice, WeChat Pay, Alipay, Stripe, or entitlement enforcement.
- Live notification delivery.
- Complete self-host deployment.
- Compliance certification or production retention/legal-hold controls.
- Governed release readiness based solely on the current `ready_for_governed_publish` aggregation.
- Live GitHub enforcement without non-dry-run publish and branch-protection/readback evidence bound to the release.

### Merge/release recommendation

PR #32 is acceptable as a **draft A3 product/demo and read-model increment** after hygiene cleanup and truth-state naming correction. It is not acceptable as evidence for hosted production launch, enterprise security approval, live payment enablement, or release-authority enforcement. The next round should spend fewer lines on new shells and close the trusted-principal, authoritative decision, durable persistence/RLS, and live readback/custody path first.
