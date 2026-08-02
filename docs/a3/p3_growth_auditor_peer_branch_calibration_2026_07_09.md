# A3 Growth-Auditor Peer Branch Calibration - 2026-07-09

Role: Growth-Auditor / Money-Grade Auditor.

Scope: docs-only audit artifact for A3 peer branch calibration. This file is
about the current theme:

```text
A1 billing/auth/quota/evidence
+ A2 security/unblock/sql/backlog
+ A3 product-console/report/release-evidence calibration
```

Safety boundary:

- No `.env`, API key, token, cookie, account identifier, private evidence body,
  payment secret, or signed URL was read or written.
- No external API was called.
- No A1 runner, A2 judge, A3 dashboard, service, report, or test code was
  modified by this audit.
- This document treats peer-branch work as calibration input, not as merged
  production capability.

## Executive Verdict

A3 is becoming commercially sharper because it can now explain how upstream A1
and A2 capability affects a release decision. The money-grade opportunity is
not "show another dashboard panel." It is:

```text
Turn peer-branch evidence into a customer-facing release-control packet:
who is allowed, what quota/billing state exists, which evidence is durable,
which security/release gates block, what SQL/audit records back the claim,
and which backlog items unblock production launch.
```

Sellable now:

```text
Paid design-partner audit for agent release readiness:
A1 usage/auth/quota/evidence readiness + A2 security/unblock/persistence
signals + A3 report/release-evidence/audit-bundle presentation.
```

Not sellable yet:

```text
Production enterprise SaaS enforcement with real hosted auth, billing checkout,
quota enforcement, payment webhooks, Postgres/RLS, immutable object custody,
live GitHub branch protection, and compliance-grade identity binding.
```

## Evidence Basis

This audit is based on public-safe repository documentation and schema contracts:

| Area | Evidence read | Money-grade signal |
|---|---|---|
| A3 schema drift | `docs/a3/a3_a1_a2_schema_drift_radar_2026_07_09.md` | A3 already tracks A1/A2 upstream schema hashes and names peer-branch drift around A1 route/quota/evidence and A2 security/SQL/backlog. |
| A3 billing readiness | `docs/a3/p3_billing_readiness_contract_2026_07_09.md` and `docs/a3/a3_billing_usage_summary_2026_07_09.md` | A3 can show plan/quota/usage/overage risk without enabling payment mutations. |
| A3 auth/RBAC | `docs/a3/p3_auth_rbac_boundary_2026_07_09.md` and `docs/a3/a3_fail_closed_rbac_write_paths_2026_07_09.md` | A3 has local fail-closed authorization semantics, but hosted auth still belongs to A1. |
| A2 persistence/unblock | `docs/a3/p3_a2_persistence_unblock_export_2026_07_09.md` | A3 can consume A2 result persistence and release unblock checklist as report/export evidence. |
| A1 quota/readiness | `docs/a1/evidence/round19_frontend_api_usage_quota_lifecycle.md` and `docs/a1/schemas/api_probe_quota_gate.schema.json` | Usage, billing, API keys, quota states, and stop/go probes are visible as public-safe contract concepts. |
| A1 commercial control plane | `docs/a1/schemas/commercial_control_plane.schema.json` | A1 owns usage billing snapshot, API key inventory, observability summary, and readiness badge semantics. |
| A2 commercial/readiness | `docs/a2/schemas/commercial_readiness.schema.json` | A2 has a Growth-Auditor structure with money direction, toy risks, customer drivers, enterprise readiness, and 20+ growth points. |
| A2 result persistence | `docs/a2/schemas/result_persistence_manifest.schema.json` | A2 can describe tenant/project/run scoped judge, release gate, scenario selection, and ingestion digest records with hashes. |
| A2 release unblock | `docs/a2/schemas/release_unblock_checklist.schema.json` | A2 can turn blocked C3/C4/C5 gates into owner-role actions and A3 consumption summaries. |
| A3 operating index | `docs/a3/a3_slim_operating_index_2026_07_09.md` | A3 still lacks hosted auth, real billing, Postgres/RLS, full event envelope coverage, immutable storage, and live enforcement. |

## 1. 本轮新增可卖能力

This round's commercial value is a calibration layer, not a production backend.
It adds the ability to talk about A1/A2 peer-branch work as a coherent product
story that a buyer can understand.

1. A1 billing/quota readiness can be sold as "usage-risk visibility" instead
   of pretending payment integration is complete.
2. A1 auth/RBAC readiness can be sold as "permission boundary evidence" while
   clearly marking real hosted auth as future A1-owned work.
3. A1 evidence indexing can be sold as "source-of-truth lineage" for release
   reports, audit bundles, and customer review.
4. A1 API quota stop/go probes can be sold as "do not spend or mutate when
   quota is unsafe" release protection.
5. A2 security context can be sold as "cross-lane security signal" once it lands
   in public-safe fixture/schema form.
6. A2 release unblock checklist can be sold as "blocked release next actions,"
   not just "release failed."
7. A2 result persistence can be sold as "durable judge/release/policy record"
   for audit and postmortem review.
8. A2 SQL store report can be sold as "persistence readiness evidence" once A3
   imports it downstream.
9. A2 backlog/scenario-generation context can be sold as "risk coverage roadmap"
   for enterprise rollout.
10. A3 schema drift radar can be sold as "upstream contract monitoring" for A1
    and A2 changes.
11. A3 billing readiness can be sold as a safe customer-facing preview of what
    will become billable later.
12. A3 fail-closed RBAC local contract can be sold as a security posture demo:
    denied writes do not mutate local state.
13. A3 source artifact hashing can be sold as evidence lineage across A1 run
    data, A2 grades, A3 reports, readbacks, and bundles.
14. A3 release evidence v2 can be sold as the authority object that ties
    billing, auth, quota, unblock, and audit into one release packet.
15. A3 report/export consumption of A2 unblock and persistence can be sold as a
    management-ready artifact for customer release review.

Money-grade framing:

```text
The new sellable unit is not a feature page.
It is a release-readiness audit packet with billing/auth/quota/evidence,
security/unblock/persistence, and A3 review/report/audit presentation.
```

## 2. 玩具或不够商业的点

The current system is promising, but several parts still read as prototype
unless described honestly.

| Area | Toy signal | What would make it commercial |
|---|---|---|
| Billing | Read-only usage and readiness; no checkout, invoice, webhook, or payment provider event. | A1-owned usage events, rollups, billing provider webhook verification, billing-admin RBAC, invoice preview audit trail. |
| Quota | Quota is modeled and displayed, but not production-enforced across all mutating calls. | A1 quota gate before every paid/mutating operation, with reset/wait hints and denial receipts. |
| Auth | A3 has metadata/local role headers, not real SSO/session/API-key validation. | A1 hosted auth middleware, service-account scope, API key lifecycle, session binding, and audit events. |
| RBAC | Local fail-closed paths are good, but not tenant-backed production policy. | DB-backed role assignments, denied-state tests under multiple tenants, and production policy migration. |
| Evidence | Source hashes exist, but peer-branch evidence is not uniformly mandatory. | Mandatory source artifact registry for A1 run/trace/tool-call/quota and A2 grade/gate/unblock/security/SQL records. |
| A2 security | Cross-lane security is named as peer-branch work, not yet a fully visible A3 product surface. | Public-safe fixture/schema, A3 report section, dashboard status, release gate impact, and audit bundle entry. |
| A2 unblock | A3 can export unblock checklist, but workflow is not yet a live queue. | Owner assignment, due dates, waiver/approval status, reviewer identity, evidence upload refs, and unblock history. |
| SQL | SQLite/local SQL contracts are useful, but not production multi-tenant storage. | Postgres schema, RLS proof, migration plan, backup/retention story, and tenant-negative tests. |
| Backlog | Backlog/scenario generation context is not yet a product object. | Prioritized risk backlog with owner, customer impact, release gate linkage, and scenario-pack promotion. |
| Dashboard | A3 has many panels and routes, but it is still partly fixture/local-runtime shaped. | Full hosted app shell, account lifecycle, typed API client, stable navigation, and production monitoring. |

## 3. 客户为什么愿意付费

Customers pay when the product reduces release risk, saves engineering review
time, or creates evidence they can show to leadership, security, or auditors.

The strongest payment drivers are:

1. Stop unsafe agent releases before they reach customers.
2. Explain whether a release is blocked by auth, quota, missing evidence,
   security policy, SQL persistence, or unresolved evaluation failures.
3. Convert raw A1 runtime evidence and A2 judge output into a management-readable
   release packet.
4. Preserve source hashes, policy hashes, result hashes, and report hashes so
   release decisions are reviewable later.
5. Show usage/quota/overage risk before teams accidentally trigger paid or
   failing hosted operations.
6. Give reviewers an unblock checklist instead of a vague failed gate.
7. Provide public-safe artifacts that can be shared without exposing secrets,
   tokens, account identifiers, or private payloads.
8. Let engineering, security, product, and compliance teams speak from the same
   release-evidence object.
9. Reduce the time spent manually reconciling A1 run data, A2 evaluation output,
   GitHub/CI state, and customer-facing reports.
10. Create a concrete audit trail for design partners who want to trust agent
    workflows before buying a larger SaaS rollout.

## 4. 提高客单价的理由

Higher ACV comes from moving A3 from "reporting tool" to "release-control and
audit system."

| Premium lever | Why it raises price | Required proof |
|---|---|---|
| Enterprise release gate | The product becomes part of production approval, not post-hoc analytics. | A2 gate + A3 release evidence + live/CI readback + reviewer approval state. |
| Auth/RBAC/tenant proof | Security and platform teams can approve broader rollout. | A1 hosted auth, role binding, tenant-negative tests, denied receipts. |
| Usage/quota governance | Prevents runaway spend and accidental paid mutations. | A1 quota stop/go, A3 overage-risk report, durable usage events. |
| Audit bundle | Supports security review, vendor review, and incident retrospectives. | Source hashes, generated artifact hashes, event envelope, bundle reseal impact. |
| Self-host option | Regulated buyers pay for control and local verification. | Offline bundle, deterministic fixtures, DB migrations, redaction checks, no external-call mode. |
| Security/unblock workflow | Converts failed releases into managed remediation work. | A2 security context, unblock checklist, owner roles, waiver/approval lifecycle. |
| SQL persistence readiness | Makes evidence durable enough for enterprise retention. | A2/A3 persistence manifest, Postgres/RLS path, migration and retention plan. |
| Policy packs by plan | Creates packaging difference between Team, Pro, and Enterprise. | Scenario packs, release policies, quota policies, review policies, audit profiles. |
| Compliance-ready export | Helps buyers satisfy internal controls. | SOC2/ISO-style control mapping as product evidence, without claiming certification. |
| Multi-project governance | Larger customers need org/project/workspace rollups. | Tenant-scoped reports, per-project policy, cross-project drift radar, usage rollups. |

Best pricing story:

```text
Basic plan sells report visibility.
Pro sells release gates and usage/quota governance.
Enterprise sells auth/RBAC, audit bundles, self-host, SQL persistence,
security/unblock workflow, and compliance-ready evidence exports.
```

## 5. 降低上线风险

This calibration lowers launch risk when it is used as a control layer around
A1/A2 work.

Risk reductions already visible:

1. Schema drift radar reduces silent breakage when A1/A2 peer branches change
   contracts.
2. A1 quota stop/go semantics reduce the chance of paid or failing mutating
   calls when quota is blocked.
3. A3 billing readiness prevents the team from claiming real payment behavior
   before A1 billing backend exists.
4. Auth/RBAC boundary documents who may perform which A3 operation.
5. Fail-closed write paths prevent local mutation-like actions after denial.
6. A2 result persistence gives judge/release/policy output a durable evidence
   shape.
7. A2 release unblock checklist converts blocked gates into actionable work.
8. Source artifact hashes reduce disputes about which A1/A2 evidence a report
   used.
9. Redaction posture prevents secrets or private account data from entering
   public-safe artifacts.
10. A3 release evidence v2 gives downstream reviewers a single authority object
    instead of scattered fields.

Risks still requiring hardening:

1. Hosted auth/session/API-key enforcement is not production-ready.
2. Billing provider integration and webhooks are not implemented.
3. Quota enforcement is not universal across all paid/mutating actions.
4. Postgres/RLS proof is missing.
5. A2 cross-lane security and SQL peer-branch outputs need public-safe A3
   consumption before they can be sold as product-visible capabilities.
6. Reviewer identity is not yet cryptographically or SSO-bound.
7. Live GitHub branch protection is not enforced by A3.
8. Event envelope and idempotency are not uniformly attached to every
   mutation-like receipt.

## 6. Enterprise / Self-Host / Audit / Compliance 支持

### Enterprise

Supported today as contract/readiness:

- Organization/project/tenant fields appear in A3/A2 contracts.
- A3 Auth/RBAC boundary can explain local roles, permissions, decisions, and
  denied states.
- A3 report/release evidence can present A1 evidence counts and A2 gate/unblock
  status.
- Billing readiness can show plan/quota/usage/overage risk without mutating
  payments.

Missing for enterprise production:

- A1 hosted auth, real sessions, service accounts, API key lifecycle, billing
  backend, and quota enforcement.
- Production Postgres/RLS and DB-level tenant isolation.
- Real reviewer identity binding and durable approval persistence.
- Live GitHub App or branch-protection integration.

### Self-Host

Supported today as a direction:

- Public-safe schemas and deterministic fixtures can be validated offline.
- A3 has local store/SQLite-style contracts and report/export surfaces.
- A2 result persistence and release unblock contracts are self-host friendly
  because they avoid raw private evidence.
- A1/A2/A3 evidence can be packaged as hashes and summaries.

Missing:

- One signed self-host bundle manifest.
- Installation/upgrade/migration instructions for all A1/A2/A3 contracts.
- Offline license/usage handling.
- Object-storage custody and retention policy.

### Audit

Supported today:

- A2 result persistence records include tenant/project/run/case, policy hash,
  input hash, output hash, decision, score, and release-gate fields.
- A3 source artifact and release evidence contracts can connect A1 runtime
  evidence to A2 judge output and A3 generated reports.
- A3 audit bundle/index patterns already create a future anchor for immutable
  release packets.

Missing:

- Uniform event envelope across all write paths.
- Append-only production audit event store.
- Bundle reseal impact when source evidence, policy, waiver, approval, or report
  artifacts change.
- External verifier flow for customers.

### Compliance

Supported today:

- Redaction posture is explicit.
- Billing and auth are kept read-only/plan-only until production owner systems
  exist.
- Evidence artifacts avoid raw secrets and private evidence bodies.
- A2/A3 can map blocked gates to policy and reviewer workflow concepts.

Missing:

- Control mapping by framework.
- Retention, deletion, and legal hold policy.
- Access review exports.
- Signed approvals, revocation history, and waiver expiry enforcement.
- Formal audit report templates.

## 7. 仍不像真产品的地方

The most important non-product signals are:

1. The product still relies heavily on docs, fixtures, and local contracts.
2. A3 can describe billing but cannot charge, invoice, refund, or reconcile.
3. A3 can describe auth/RBAC but cannot create or validate real sessions.
4. Quota and usage are not yet the authoritative enforcement layer.
5. SQL persistence is not yet a hosted multi-tenant database with RLS.
6. A2 security/unblock/sql/backlog work is not yet fully visible as customer UI
   and report sections.
7. The unblock workflow is evidence-shaped, not a real assigned workflow with
   SLA, owner routing, notifications, and identity-bound signoff.
8. The audit bundle is not immutable object-storage-backed production custody.
9. Compliance posture exists as redaction and evidence discipline, not as a
   packaged control framework.
10. The dashboard can demonstrate many surfaces, but buyer onboarding,
    workspace setup, plan upgrade, team admin, and API-key lifecycle remain
    disabled or simulated.

The honest sales line:

```text
This is ready for an enterprise design-partner release-readiness pilot.
It is not ready to be sold as a fully enforced production control plane.
```

## 8. 下一轮至少 20 个增长点

| # | Growth point | Parallel track | Commercial value | Required artifact |
|---:|---|---|---|---|
| 1 | Extend A3 drift radar for A1 route-scope schemas | A1 calibration | Prevent A3 from breaking when A1 route ownership changes | Drift radar fixture/report |
| 2 | Extend A3 drift radar for A1 quota/billing schemas | A1 calibration | Makes quota and usage claims safer | Schema hash + field map |
| 3 | Import A1 quota stop/go summary into A3 release evidence | A1/A3 bridge | Blocks paid/mutating releases under unsafe quota | Release evidence field |
| 4 | Add A1 usage event and rollup contract mapping | Billing | Turns usage display into future billable source | Usage ledger mapping |
| 5 | Add A1 hosted auth adapter contract for A3 | Auth/RBAC | Converts local role headers into real session path | Adapter schema |
| 6 | Add A1 API key lifecycle redacted evidence contract | Security/admin | Enables enterprise API-key audit without secrets | Public-safe fixture |
| 7 | Make A1 evidence index hashes mandatory in A3 packets | Evidence | Strengthens report trust and auditability | Source artifact registry rule |
| 8 | Add A2 cross-lane security context to A3 report export | A2 security | Gives security buyers a visible risk section | Report section + schema |
| 9 | Add A2 cross-lane security context to dashboard/status API | A2 security | Makes security status operational, not hidden in files | API response field |
| 10 | Add A2 release unblock checklist dashboard view | A2 unblock | Converts blocked release into next actions | Dashboard/API contract |
| 11 | Add owner-role routing for C3/C4/C5 unblock items | Review workflow | Makes remediation assignable | Owner routing schema |
| 12 | Add unblock waiver/approval expiry fields | Compliance | Prevents permanent unsafe exceptions | Waiver policy fixture |
| 13 | Import A2 SQL store report into A3 source artifacts | SQL/audit | Connects persistence readiness to release evidence | Source artifact type |
| 14 | Add Postgres/RLS readiness checklist to A3 enterprise report | SQL/enterprise | Makes multi-tenant production gap explicit | Readiness section |
| 15 | Add A2 scenario-generation backlog as product backlog object | Backlog | Turns missing coverage into sellable roadmap | Backlog schema |
| 16 | Link backlog items to release blockers and customer impact | Backlog/revenue | Helps buyers justify paid remediation | Impact matrix |
| 17 | Add paid media evidence context to release evidence | A1/A2 media | Avoids false media-readiness claims under quota limits | Media evidence summary |
| 18 | Attach event envelope to all A3 mutation-like receipts | Audit/platform | Enables append-only audit trail later | `releasefoundry.event_envelope.v1` receipts |
| 19 | Add idempotency/conflict semantics for share/revoke/waiver/approval | Reliability | Prevents duplicate audit and reviewer records | Idempotency receipts |
| 20 | Add bundle reseal impact when A1/A2 peer evidence changes | Audit | Tells buyers when an audit packet is stale | Reseal impact field |
| 21 | Create enterprise policy-pack pricing matrix | Packaging | Raises ACV through clear plan differentiation | Policy-pack doc/schema |
| 22 | Create self-host bundle manifest | Self-host | Supports regulated deployment conversations | Bundle manifest |
| 23 | Add compliance export profile mapping | Compliance | Makes security review easier | Control mapping artifact |
| 24 | Add customer-facing OpenAPI/schema bundle for peer calibration | API/platform | Lets integrators build against stable contracts | OpenAPI/schema package |
| 25 | Add trial/demo dataset with no private values | Sales enablement | Lets buyers evaluate without dangerous data | Public-safe demo fixture |
| 26 | Add release-readiness score that combines A1/A2/A3 blockers | Product | Gives executives one explainable launch metric | Scored readiness object |
| 27 | Add cost-risk summary for semantic judge and paid media evidence | Billing/risk | Connects evaluation depth to spend governance | Cost-risk report |
| 28 | Add regression promotion from incident/backlog to A2 scenario pack | Regression | Turns customer failures into durable prevention | Promotion artifact |

## 9. 哪些可以并行推进

These tracks can run in parallel because they touch different ownership lanes
and produce compatible artifacts.

| Parallel lane | Owner boundary | Can proceed now | Dependency |
|---|---|---|---|
| A1 contract calibration | A1 owns auth, billing, quota, usage, API keys, source evidence | Schema/readiness mapping, redacted fixtures, quota stop/go summaries | Real hosted enforcement later |
| A2 risk calibration | A2 owns judge, security, release policy, unblock, SQL report, backlog | Security context fixture, unblock workflow schema, SQL store report, backlog object | A3 consumer surfaces |
| A3 control-plane hardening | A3 owns report, release evidence, review workflow, audit bundle | Event envelope, idempotency, source hashes, reseal impact | A1/A2 source contracts |
| Product visibility | A3 owns customer-facing UI/report/API | Release packet sections, readiness score, unblock view, billing/auth/quota status | Stable contract fields |
| Enterprise packaging | A3 plus strategy | Policy packs, self-host bundle, compliance export profile, sales demo fixture | Accurate gap labels |
| Validation/security | Cross-lane | Secret-free tests, schema drift, tenant-negative tests, redaction gates | Hosted systems later for production proof |

Work that should not be parallelized too early:

1. Real billing checkout and invoices should wait for A1 hosted auth, usage
   events, billing webhooks, and billing-admin RBAC.
2. Production branch protection should wait for live GitHub App/CI integration
   and reviewer identity binding.
3. Compliance certification claims should wait for formal control mapping,
   retention policy, audit event storage, and external review.
4. Postgres/RLS production claims should wait for migrations and tenant-negative
   proof, not just local SQLite contracts.

## 10. 哪个方向最接近大钱

The closest direction to big money is:

```text
Enterprise Release Control
+ Audit Evidence Bundle
+ A1 billing/auth/quota enforcement path
+ A2 security/unblock/persistence path
+ A3 release-readiness product packet
```

Why this is closest to large ACV:

1. It enters the production release approval workflow, where budgets are larger
   than ordinary analytics/reporting tools.
2. It speaks to engineering leadership, security, platform, and compliance at
   the same time.
3. It reduces risk that is expensive: unsafe agent releases, unauthorized
   actions, quota overspend, missing evidence, and unreproducible approvals.
4. It creates artifacts buyers can use internally: release packet, unblock
   checklist, source hashes, audit bundle, usage/quota readiness, and compliance
   export.
5. It gives a clean tiering path: Team buys visibility, Pro buys gates,
   Enterprise buys enforcement, audit, self-host, and compliance readiness.

Ranking:

1. Enterprise release control with audit bundle and unblock workflow.
2. A1 auth/billing/quota enforcement path feeding A3 readiness.
3. A2 security/persistence/SQL/unblock path feeding A3 release packets.
4. Self-host verification bundle for regulated customers.
5. Incident-to-regression promotion and scenario backlog intelligence.
6. Usage/cost governance for paid media and semantic judging.
7. Customer-facing OpenAPI/schema package for platform integration.
8. Dashboard polish and onboarding.

Money-grade call:

```text
Do not sell "we have a dashboard."
Sell "we can tell you whether an agent release is allowed, blocked, billable,
quota-safe, security-reviewed, evidence-backed, unblockable, and auditable."
```

