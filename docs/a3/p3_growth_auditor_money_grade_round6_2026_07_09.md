# A3 Growth-Auditor Money-Grade Round 6 - 2026-07-09

Role: Growth-Auditor / Money-Grade Auditor.

Scope: docs-only commercial audit artifact. This round only adds this file
under `docs/a3/`. Existing A1/A2/A3 docs, fixtures, and test evidence were read
as public-safe evidence. No `.env.local`, private refs, raw keys, cookies,
tokens, signed URLs, account values, or live cloud state were read or quoted.

## Executive Verdict

A3 is now a credible paid pilot for **Agent Release Evidence / PR Gate
Governance**, not yet a production enterprise control plane. The repo has moved
past toy-dashboard territory because it has API-backed browser proof, local SQL
persistence, hosted report lifecycle, review records, audit-bundle verifier,
usage/billing readiness, and A1/A2 evidence consumption. But the money-grade
line remains clear:

```text
Sell now: controlled design-partner pilot for release evidence and review.
Do not sell yet: enforced production merge gate, enterprise SSO/RBAC,
immutable compliance archive, real billing, or turnkey self-host.
```

The direction closest to big money is:

```text
Enforced GitHub PR Gate
+ A1 trace/run ingestion receipts
+ A2 release gate/calibration evidence
+ A3 release evidence authority
+ identity-bound review
+ offline audit verifier
+ self-host/private deployment option
```

Why: this enters the buyer's merge path, reduces launch risk, creates an audit
record security teams understand, and naturally expands into self-host,
compliance, usage governance, and platform-wide rollout.

## Evidence Baseline

| Lane | Evidence path | Current signal | Money-grade interpretation |
|---|---|---|---|
| A3 commercial growth | `docs/a3/p3_commercial_growth_manifest_2026_07_09.md`; `fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json` | Machine-readable growth manifest with 20+ points, evidence bindings, API/DB/event/artifact contracts. | Good operating system for growth prioritization; still needs live API routes and tenant-scoped tables before becoming a hosted feature. |
| A3 round5 | `docs/a3/p3_growth_auditor_money_grade_round5_2026_07_09.md` | Prior verdict: design-partner release-governance pilot, not production enforcement. | Round6 agrees, but raises the urgency of turning v2 release evidence authority into the product spine. |
| Browser product proof | `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`; `docs/a3/p3_commercial_growth_round3_execution_2026_07_09.md`; `docs/a3/p3_commercial_growth_round4_e2e_review_admin_denied_2026_07_09.md` | API-backed dashboard, hosted report share/revoke, SaaS admin guardrail, review waiver/approval, denied hosted report E2E. | Strong paid-demo proof that buyers can see workflows, not only JSON fixtures. Still local fixture-backed, not hosted auth/RBAC. |
| Release evidence authority | `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | v1 API-backed release evidence exists; v2 authority contract is defined with health, readback, review, usage, storage, webhook, compliance fields. | Highest-leverage A3 spine. Must become canonical `summary_id` across PR, report, review, usage, audit, archive, and self-host. |
| GitHub readback | `docs/a3/p3_github_readback_contract_2026_07_08.md` | Contracts distinguish generated, posted, readback_confirmed, stale, missing, deleted, permission_denied, failed. Required check stays plan-only until branch-protection readback. | Near-money but not production claimable. Branch protection proof is the unlock. |
| Review workflow | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md` | API and SQLite-backed waiver/approval workflow, hash-sealed tenant/project records, validation reuse. | Sellable governance foundation; needs SSO/OIDC/GitHub identity, real signature verification, role policy. |
| Audit bundle | `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`; `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md` | Bundle verifier checks root hash, artifact hashes, byte sizes, custody event hashes, tampering. | Compliance buyer value is real; still needs signed immutable archive, offline customer packet, retention/legal-hold. |
| Persistence | `docs/a3/p3_sqlite_store_growth_2026_07_08.md` | Local SQLite store records imports, idempotency receipts, hosted reports, hashed share links, audit rows, usage ledger. | No longer fixture-only. Still not production Postgres/RLS or object custody. |
| SaaS admin | `docs/a3/p3_saas_admin_action_requests_2026_07_08.md` | Safe local admin action request rows for login/team/usage/API-key/trust/cloud workflows. | Good enterprise guardrail surface. Must stay plan-only until auth/RBAC/audit providers exist. |
| Billing readiness | `docs/a3/p3_billing_readiness_contract_2026_07_09.md` | `GET /api/a3/billing/readiness`; read-only usage/billing contract; no checkout/portal/invoice mutation. | Good monetization foundation; not billable infrastructure yet. |
| A3/A2 export bridge | `docs/a3/p3_a2_persistence_unblock_export_2026_07_09.md` | A3 now exports A2 result persistence and release unblock checklist summaries. | Stronger enterprise reviewer story: "what evidence is durable, and what unblocks release?" |
| Mobile client surfaces | `docs/a3/p3_mobile_expo_client_surface_2026_07_09.md`; `docs/a3/p3_wechat_mini_program_client_surface_2026_07_09.md` | Expo and WeChat approval/incident alert contracts exist; writes require hosted auth/RBAC/audit. | Useful market signal, especially China/mobile review. Not a product until backend identity and guarded writes exist. |
| Product system | `docs/a3/p3_tailwind_product_system_contract_2026_07_09.md` | Testable Tailwind token contract for A3 commercial UI. | Helps polish and consistency; not a revenue feature by itself. |
| A1 capability inventory | `docs/a1/commercial/capability_matrix.json` | 122 capabilities, 107 frontend-mirrored, 9 real-read verified, 30 test-covered; public evidence index has 368 records and 43 quota blocks. | A1 has broad shape awareness but only a small verified read subset. Do not overclaim full official API coverage. |
| A1 control plane kit | `docs/a1/commercial/control_plane_kit.json` | Status `enterprise_saas_read_only_verified_mutation_guarded`; real billing called false; checkout/portal called false. | Buyer-safe read-only control-plane story; paid mutation and real billing are still future. |
| A1 ingestion/runtime | `docs/a1/saas_ingestion_quickstart.md` | Local SDK/CLI ingestion, API-key lifecycle, quota, HTTP adapter, release evidence packet, usage rollup, object-store/webhook primitives. | This is the source of future usage-priced ingestion. A3 needs import receipts tied to release evidence. |
| A1 self-host | `docs/a1/self_host_runtime_scaffold.md` | Compose scaffold for API, worker, Postgres, Redis, object-store; provider-neutral Terraform skeleton; Rust verifier. | Good self-host skeleton; not yet turnkey install/backup/restore/upgrade. |
| A2 release gate | `fixtures/a2/results/a2_release_gate_report.json` | `ready_for_commercial_gate=false`, `decision=block`, `exit_code=2`, `risk_score=100`, 3 blocking gates, 4 evidence blockers. | Honest and valuable: A2 can block. But current strict gate says commercial readiness is not met. |
| A2 readiness | `fixtures/a2/results/a2_commercial_readiness_report.json`; `fixtures/a2/results/a2_evidence_readiness_report.json` | Commercial gate false; external collection ready true; C3 safe-to-mark-met false; 6 reviewed Ashr grading observations missing. | A3 must surface this as blocker evidence, not hide it. |
| A2 replay | `fixtures/a2/results/a2_regression_replay_report.json` | Replay ready true, maturity `seed`; target 3 cases, current 1, reviewed external evidence 0/3. | Good seed for incident-to-regression, not mature production replay. |
| A2 persistence/selection | `fixtures/a2/results/a2_result_persistence_manifest.json`; `fixtures/a2/results/a2_scenario_selection_report.json` | 162 public-safe persistence records; 12 prod scenarios selected. | Strong audit and per-project scenario story that can raise ACV once tied to A3 release packets. |
| A2 handoff/API | `docs/a2/a1_a3_handoff.md`; `docs/a2/openapi/a2_judge_service.openapi.json`; `docs/a2/README.md` | Stable A1 run normalization, A2 grade/readiness optional feeds, OpenAPI internal judge boundary. | Integration contract is credible; hosted eval service ownership remains A1/A3 dependent. |

## New Sellable Capability Assessment

| Capability | Can sell now? | Evidence | Buyer promise | Honest constraint |
|---|---|---|---|---|
| API-backed A3 Product Console | Yes, as paid pilot | `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`; `docs/a3/p3_commercial_growth_round3_execution_2026_07_09.md` | "See release evidence, report center, admin, review, A1/A2 evidence in one console." | Local API/mock-backed proof; no hosted identity or production DB. |
| Hosted report lifecycle | Yes, as governed sharing pilot | `docs/a3/p3_commercial_growth_round4_e2e_review_admin_denied_2026_07_09.md` | "Share, revoke, and deny evidence reports without leaking body details on denied pages." | Share tokens and lifecycle are local A3 store evidence; no enterprise auth yet. |
| Durable waiver/approval workflow | Yes, if scoped as governance evidence | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md` | "Approvals/waivers become tenant-scoped hash-sealed records." | Not identity-bound through SSO/OIDC/GitHub; not cryptographically verified. |
| Audit bundle verifier | Yes, as compliance pilot | `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md` | "Verify evidence package integrity after generation." | Needs signed immutable archive and offline verifier packet before regulated production claim. |
| GitHub Check/PR comment readback contract | Almost | `docs/a3/p3_github_readback_contract_2026_07_08.md` | "A3 can distinguish posted/readback/stale/missing/deleted GitHub evidence." | No live GitHub App/branch-protection enforcement proof in repo. |
| Release evidence authority | Almost; sell the v1, build the v2 | `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | "One redacted health object proves release gate, review, report, audit, usage, and storage state." | v2 is still roadmap/contract-heavy; must be implemented and persisted. |
| SQLite-backed A3 storage | Yes, as local MVP durability | `docs/a3/p3_sqlite_store_growth_2026_07_08.md` | "Not just static fixtures; evidence lifecycle can persist in SQL." | Production Postgres/RLS, migrations, backups, and object storage remain gaps. |
| SaaS admin action requests | Yes, as guardrail evidence | `docs/a3/p3_saas_admin_action_requests_2026_07_08.md` | "Dangerous admin actions are recorded safely before real mutation is enabled." | Cannot sell as real admin console until auth/RBAC/team/API-key/billing services exist. |
| Billing readiness | Yes, as buyer conversation artifact | `docs/a3/p3_billing_readiness_contract_2026_07_09.md`; `docs/a1/commercial/control_plane_kit.json` | "Usage meters and billing readiness are visible, no surprise live charge." | No real invoice, subscription, entitlement, checkout, portal, or payment webhook. |
| A2 persistence + unblock export | Yes, as audit/reviewer value | `docs/a3/p3_a2_persistence_unblock_export_2026_07_09.md`; `fixtures/a2/results/a2_result_persistence_manifest.json` | "A3 exports durable judge records and unblock next actions." | Needs artifact registry, audit bundle hashing, usage meters, and reviewer task mapping. |
| A1 ingestion to evidence packet | Sell as upcoming integration, not A3-native yet | `docs/a1/saas_ingestion_quickstart.md` | "Run/trace ingestion can feed release evidence packets." | A3 still needs production `POST /api/a3/traces/import` and import receipts. |
| Mobile/WeChat approval surfaces | Demo only | `docs/a3/p3_mobile_expo_client_surface_2026_07_09.md`; `docs/a3/p3_wechat_mini_program_client_surface_2026_07_09.md` | "Mobile release approval/incident alert flows are designed and testable." | Read-mostly contract shell; no hosted auth/RBAC/audit-backed write path. |
| Tailwind product system | Not directly sellable | `docs/a3/p3_tailwind_product_system_contract_2026_07_09.md` | "UI can become consistent and enterprise-dense." | It raises polish but does not create customer value alone. |

## Toy-To-Money Upgrade Recommendations

| Toy-like capability today | Why it still feels toy-like | Money-grade upgrade |
|---|---|---|
| GitHub required check | Required-check proof is plan-only until branch protection is read back. | Build GitHub App/CI readback worker, branch-protection verifier, admin approval receipt, and `enforced=true/false` evidence. |
| API-backed dashboard | Browser tests prove local flows, not hosted multi-tenant auth. | Add hosted auth/RBAC middleware, tenant-negative E2E, Postgres/RLS store, and immutable hosted snapshots. |
| Review approval | Hash-sealed local records are not accountable enterprise signatures. | Bind reviewer to SSO/OIDC/GitHub subject, role, expiry, artifact hash, signature status, and separation-of-duties result. |
| Audit bundle verifier | Verifies index/files, but archive custody is incomplete. | Add signed zip/tar archive, detached signature, offline verifier packet, retention/legal-hold fields, and object-lock readiness. |
| Billing readiness | Usage ledger is read-only; checkout/portal are mirrored but not real. | Add append-only usage event IDs, entitlement/quota policy, invoice-ready export, billing-admin approval, provider webhook verification later. |
| Self-host scaffold | Compose and contract exist, but ops lifecycle is missing. | Ship installable self-host package, migration apply/verify, backup/restore drill, object-store custody, upgrade check, offline verifier. |
| Trace/replay | A2 replay is seed maturity and A3 replay is mostly product context. | Define A3 replay pack, production trace import, runner receipt states, incident RCA export, and incident-to-regression promotion. |
| A2 calibration | Commercial gate blocks because C3/C4/C5 are partial. | Import six reviewed Ashr grading observations, audited semantic judge summaries, drift metrics, low-confidence review queue. |
| Mobile/WeChat | Contracts exist without real secure action path. | Keep read-only until server identity/RBAC/audit works, then allow guarded review action requests with usage/audit receipts. |
| Admin console | Requests are safely recorded, but real admin functions are absent. | Add real permission checks and provider-backed action executors only after audit, approval, and rollback controls exist. |
| Product system | Token contract exists, but UI still must prove professional density and no overlap. | Convert high-value release/review/report surfaces first; add Playwright screenshot/no-overlap/no-leak gates. |
| A1 official API parity | A1 has 107 mirrored functions but only 9 real-read verified. | Prioritize verified read/list/run/request/dataset paths needed for ingestion and release evidence; avoid broad official parity claims. |

## How To Improve Paid Conversion, ACV, Launch Safety, Enterprise, Self-Host, Audit, Compliance

| Lever | Concrete capability to add | Evidence anchor | Commercial effect |
|---|---|---|---|
| Paid conversion | 10-minute first-run onboarding: create org/project, import A1 run, join A2 gate, generate A3 hosted report, export audit packet. | `docs/a1/saas_ingestion_quickstart.md`; `docs/a2/a1_a3_handoff.md`; `docs/a3/p3_playwright_e2e_growth_2026_07_09.md` | Makes pilot value obvious before procurement friction. |
| Paid conversion | One redacted "release packet preview" link for every PR gate. | `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`; `docs/a3/p3_github_readback_contract_2026_07_08.md` | Turns CI output into buyer-visible artifact. |
| ACV | Enforced PR required check tier. | `docs/a3/p3_github_readback_contract_2026_07_08.md`; `fixtures/a2/results/a2_release_gate_report.json` | Moves from reporting budget to release-infrastructure budget. |
| ACV | Enterprise audit archive tier with signed archive and offline verifier. | `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`; `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md` | Security/compliance teams pay for defensible evidence custody. |
| ACV | Per-project scenario/policy packs: startup CI, team prod, regulated SaaS, enterprise strict. | `fixtures/a2/results/a2_scenario_selection_report.json`; `docs/a2/README.md` | Creates plan packaging and multi-team expansion. |
| ACV | Chargeback/usage export by team/project/repo/release. | `docs/a3/p3_billing_readiness_contract_2026_07_09.md`; `docs/a1/commercial/control_plane_kit.json` | Gives platform teams budget allocation and expansion mechanics. |
| Launch safety | Fail-closed redaction across JSON, Markdown, CSV, HTML, Check, Comment, screenshots, archive. | `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`; `docs/a3/p3_self_host_console_growth_2026_07_07.md` | Prevents the highest-trust-killing launch failure: leaked evidence. |
| Launch safety | A2 commercial readiness blocker displayed directly in A3. | `fixtures/a2/results/a2_commercial_readiness_report.json`; `fixtures/a2/results/a2_evidence_readiness_report.json` | Stops product from pretending judge evidence is stronger than it is. |
| Launch safety | Replay runner receipt: reproduced, fixed, flaky, new_failure, not_runnable. | `fixtures/a2/results/a2_regression_replay_report.json`; `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md` | Prevents regressions from being managed as screenshots or comments. |
| Enterprise | Identity-bound waiver/approval. | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md` | Makes sign-off defensible to release managers and auditors. |
| Enterprise | GitHub App installation contract and permission audit. | `docs/a3/p3_github_readback_contract_2026_07_08.md` | Replaces personal-token demos with enterprise integration posture. |
| Enterprise | Tenant/project negative tests for every API/store/report/usage route. | `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`; `docs/a3/p3_self_host_console_growth_2026_07_07.md` | Reduces catastrophic cross-tenant leakage risk. |
| Self-host | A3 self-host bundle with API, dashboard, DB, worker, object-store stub, verifier. | `docs/a1/self_host_runtime_scaffold.md`; `docs/a3/p3_self_host_console_growth_2026_07_07.md` | Opens regulated/private-data buyers. |
| Self-host | Backup/restore/upgrade verification. | `docs/a1/self_host_runtime_scaffold.md`; `docs/a3/p3_sqlite_store_growth_2026_07_08.md` | Gives operators confidence beyond a demo compose file. |
| Audit | Hash A2 persistence/unblock summaries into A3 artifact registry and audit bundle. | `docs/a3/p3_a2_persistence_unblock_export_2026_07_09.md`; `fixtures/a2/results/a2_result_persistence_manifest.json` | Connects judge evidence to release packet custody. |
| Compliance | Retention/legal-hold/purge eligibility receipts. | `docs/a3/p3_self_host_console_growth_2026_07_07.md`; `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | Turns "we store evidence" into compliance-operable controls. |
| Compliance | SOC2-style control map, even before certification. | `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md`; `docs/a1/commercial/control_plane_kit.json` | Speeds enterprise security review by mapping controls to artifacts. |

## What Still Does Not Feel Like A True Product

1. No live branch-protection readback proving `Ashr++ Release Gate` is enforced.
2. No GitHub App install/onboarding flow, permission audit, or org/repo selection UX.
3. No hosted SSO/RBAC/session enforcement across dashboard, reports, admin, review, and API routes.
4. No production Postgres/RLS deployment proof, migration apply/rollback, or two-tenant negative suite.
5. No customer onboarding loop that imports first run and produces first PR gate/report in under 10 minutes.
6. No A3 production trace import route with idempotency, redaction pre-scan, payload hash, and receipt.
7. No executable replay runner tied to A2 case book maturity; current A2 replay remains 1/3 seed.
8. No six reviewed Ashr grading observations in the public calibration matrix; C3 is still not safe to mark met.
9. No audited live semantic judge summaries; C4 remains harness-ready/offline-reference-heavy.
10. No judge trust dashboard showing calibration drift, false block, false pass, confidence, and low-confidence review.
11. No cryptographic approval signature verification or signer/key fingerprint binding.
12. No immutable signed archive package containing report, manifest, bundle, screenshots/PDF, and verifier receipt.
13. No retention/legal-hold/purge workflow that can survive enterprise audit review.
14. No object-storage custody proof; signed URLs/raw storage keys are correctly avoided, but private storage lifecycle is not real yet.
15. No billing provider integration, entitlement enforcement, seat accounting, invoice export approval, or webhook verification.
16. No public versioned A3 OpenAPI/SDK/webhook package for customers.
17. No mobile/WeChat backend action path; current client surfaces are read-mostly shells.
18. No real admin execution for API keys, team, Trust, billing, or cloud management; current admin requests are safe but plan-only.
19. No customer-safe RCA export that joins trace, replay, judge, reviewer, and regression promotion evidence.
20. No visual regression/no-leak/no-overlap gate across all commercial desktop/mobile states.

## Next-Round Growth Points

| ID | Growth point | Must land as | Evidence anchor | Why it grows money |
|---|---|---|---|---|
| R6-01 | Branch-protection verifier for `Ashr++ Release Gate`. | Redacted required-check readback receipt. | `docs/a3/p3_github_readback_contract_2026_07_08.md` | Converts PR gate from demo to enforcement. |
| R6-02 | GitHub App installation contract. | Permission/install/uninstall docs plus fixture. | `docs/a3/p3_github_readback_contract_2026_07_08.md` | Enterprise buyers distrust PAT-based demos. |
| R6-03 | v2 release evidence authority implementation. | `a3.release_evidence_summary.v2` builder, API negotiation, tests. | `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | Creates one product spine for PR/report/review/audit/usage. |
| R6-04 | Immutable hosted report snapshots. | Snapshot id/hash persisted; hosted report does not change after source changes. | `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`; `docs/a3/p3_commercial_growth_round4_e2e_review_admin_denied_2026_07_09.md` | Audit credibility for external sharing. |
| R6-05 | A3 trace ingestion route. | `POST /api/a3/traces/import` with idempotency, payload hash, redaction receipt. | `docs/a1/saas_ingestion_quickstart.md`; `docs/a1/schemas/trace_event.schema.json` | Unlocks real production data and usage pricing. |
| R6-06 | Replay pack schema. | `a3.replay_pack.v1` with A1 trace ids, tool calls, A2 judge refs, media hashes. | `fixtures/a2/results/a2_regression_replay_report.json`; `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md` | Turns incidents into durable quality assets. |
| R6-07 | Replay runner receipts. | Reproduced/fixed/flaky/new_failure/not_runnable states. | `fixtures/a2/results/a2_regression_replay_report.json` | Makes replay operational, not decorative. |
| R6-08 | Customer-safe RCA export. | Timeline, impacted cases, root cause hypothesis, replay state, reviewer owner. | `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md` | Expands value from CI to incident response. |
| R6-09 | Import six reviewed Ashr grading observations. | Public-safe merged calibration summary after private review. | `fixtures/a2/results/a2_evidence_readiness_report.json`; `docs/a2/a1_a3_handoff.md` | Unblocks C3 trust and reduces "local-only judge" objection. |
| R6-10 | Import six audited semantic judge summaries. | LLM judge rows with provider/model/hash/cost/confidence/review status. | `docs/a2/README.md`; `docs/a2/a1_a3_handoff.md` | Makes semantic gate credible for complex agents. |
| R6-11 | A2 maturity raise from 1/3 to 3/3 replay cases. | Case book/replay fixture with reviewed external evidence. | `fixtures/a2/results/a2_regression_replay_report.json` | Moves incident replay from seed to sellable maturity. |
| R6-12 | Calibration/drift panel in A3 release health. | Judge version, drift, disagreement, low-confidence queue fields. | `fixtures/a2/results/a2_commercial_readiness_report.json`; `fixtures/a2/results/a2_g3_calibration_matrix.json` | Reduces false-block buyer objections. |
| R6-13 | Identity-bound review records. | Provider subject alias, role, expiry, artifact hash, separation-of-duties proof. | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md` | Converts local approval into enterprise sign-off. |
| R6-14 | Cryptographic signature verification. | Signature status and key fingerprint alias in review/archive health. | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md`; `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md` | Required for regulated approvals. |
| R6-15 | Signed immutable audit archive. | Zip/tar + manifest + detached signature + offline verifier receipt. | `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`; `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md` | Compliance tier and legal defensibility. |
| R6-16 | PDF/screenshot artifact hashing. | Visual artifacts included in manifest and verifier. | `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`; `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md` | Closes common audit evidence gap. |
| R6-17 | Retention/legal-hold/purge receipts. | Plan-only first, then enforced after identity/RBAC. | `docs/a3/p3_self_host_console_growth_2026_07_07.md`; `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | Enterprise compliance upsell. |
| R6-18 | A3 self-host install bundle. | Compose/API/dashboard/DB/worker/object-store/verifier smoke receipt. | `docs/a1/self_host_runtime_scaffold.md`; `docs/a3/p3_self_host_console_growth_2026_07_07.md` | Opens private-data customers. |
| R6-19 | Backup/restore/upgrade drill. | Restore receipt, migration version, audit log continuity proof. | `docs/a1/self_host_runtime_scaffold.md`; `docs/a3/p3_sqlite_store_growth_2026_07_08.md` | Raises self-host ACV and operator trust. |
| R6-20 | Postgres/RLS tenant-negative suite. | Two-tenant API/store/report/usage tests. | `docs/a3/p3_self_host_console_growth_2026_07_07.md`; `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | Reduces enterprise SaaS launch risk. |
| R6-21 | Usage event id linkage to release evidence. | Append-only usage rows joined to `summary_id`, `manifest_id`, tenant. | `docs/a3/p3_billing_readiness_contract_2026_07_09.md`; `docs/a3/p3_sqlite_store_growth_2026_07_08.md` | Turns evidence volume into pricing. |
| R6-22 | Quota and chargeback preview. | Read-only report by team/project/repo/release. | `docs/a1/commercial/control_plane_kit.json`; `docs/a3/p3_billing_readiness_contract_2026_07_09.md` | Helps platform buyers allocate budget. |
| R6-23 | Billing export with admin approval. | Invoice/Stripe-ready CSV/JSON export; no live mutation by default. | `docs/a3/p3_billing_readiness_contract_2026_07_09.md`; `docs/a3/p3_saas_admin_action_requests_2026_07_08.md` | Monetization without accidental charges. |
| R6-24 | Public A3 OpenAPI. | Versioned schemas for release, reports, review, readback, trace, usage, webhooks. | `docs/a2/openapi/a2_judge_service.openapi.json`; `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | Makes integration enterprise-ready. |
| R6-25 | Webhook dry-run receipts. | Gate completed, readback changed, report shared/revoked, archive verified. | `docs/a1/saas_ingestion_quickstart.md`; `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | Lets customers embed A3 in release systems. |
| R6-26 | SDK examples for A3 import/gate/report/review/usage. | TypeScript/Python snippets and compatibility tests. | `docs/a1/saas_ingestion_quickstart.md`; `docs/a2/a1_a3_handoff.md` | Lowers onboarding cost. |
| R6-27 | Release unblock owner lanes. | Map C3/C4/C5 blockers to A1/A2/A3 owners and reviewer tasks. | `docs/a3/p3_a2_persistence_unblock_export_2026_07_09.md`; `fixtures/a2/results/a2_release_gate_report.json` | Makes blocked release actionable, not frustrating. |
| R6-28 | Admin action executor readiness. | Keep plan-only; add approval, audit, rollback, provider requirements per action. | `docs/a3/p3_saas_admin_action_requests_2026_07_08.md` | Builds trust without unsafe mutation. |
| R6-29 | Mobile/WeChat guarded action request. | Server-authenticated request submission only, not direct release mutation. | `docs/a3/p3_mobile_expo_client_surface_2026_07_09.md`; `docs/a3/p3_wechat_mini_program_client_surface_2026_07_09.md` | Makes mobile surfaces commercially plausible. |
| R6-30 | Visual no-leak/no-overlap gate. | Playwright desktop/mobile assertions and hashed screenshots. | `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`; `docs/a3/p3_tailwind_product_system_contract_2026_07_09.md` | Prevents demo/product trust erosion. |

## Must-Run-In-Parallel Work

These workstreams must not be serialized because each removes a different
commercial blocker:

| Lane | Parallel package | Why parallel |
|---|---|---|
| PR enforcement | R6-01, R6-02, R6-03, R6-04 | Enforcement, release authority, and immutable snapshots must converge for "blocks merge" to be credible. |
| Trace/replay/RCA | R6-05, R6-06, R6-07, R6-08, R6-11 | Production replay needs ingestion, pack, runner, RCA, and mature A2 seeds together. |
| Judge trust | R6-09, R6-10, R6-12, R6-27 | A3 cannot sell high-confidence blocking while A2 C3/C4/C5 remain hidden or partial. |
| Review/audit/compliance | R6-13, R6-14, R6-15, R6-16, R6-17 | Enterprise approvals, archive, visuals, retention, and legal hold form one compliance story. |
| Self-host/platform | R6-18, R6-19, R6-20, R6-24, R6-25, R6-26 | Private deployments need install, tenant isolation, APIs, webhooks, and SDKs at the same time. |
| Billing/usage/admin | R6-21, R6-22, R6-23, R6-28 | Usage pricing needs append-only events, chargeback, export approval, and safe admin governance. |
| Client/product polish | R6-29, R6-30 | Mobile/WeChat and visual gates should follow backend guardrails, but can prepare in parallel. |

Critical sequencing inside the parallel plan:

1. Define and freeze `a3.release_evidence_summary.v2` field names first.
2. Let every lane attach ids/hashes/statuses to that authority object.
3. Do not enable live mutation until redaction, tenant scope, identity, audit,
   and rollback/denied states are tested.

## Closest Direction To Big Money

Ranked by current evidence, buyer urgency, and ACV expansion:

| Rank | Direction | Why it is closest to big money | Must be true before selling hard |
|---:|---|---|---|
| 1 | Enforced PR Gate + Release Evidence Authority | Enters merge path and ties spend to launch safety. | Branch-protection readback, GitHub App path, v2 summary id, immutable snapshots, redaction fail-closed. |
| 2 | Enterprise Audit Archive + Identity Review | Security/compliance teams pay for evidence custody and accountable approvals. | Signed archive, offline verifier, SSO/OIDC/GitHub identity, signature verification, retention/legal hold. |
| 3 | Production Trace Ingestion + Replay/RCA | Creates daily operational use and incident-response value beyond pre-merge. | Trace import route, replay pack, runner receipt, RCA export, A2 replay maturity. |
| 4 | Self-Host Enterprise Edition | Unlocks regulated/private-data deals and larger contracts. | Install bundle, Postgres/RLS, backup/restore, object storage custody, offline verifier, ops docs. |
| 5 | Usage Governance / Chargeback / Billing Export | Turns evidence volume into expansion pricing. | Append-only usage ids, quota policy, chargeback reports, admin-approved billing export. |
| 6 | API/Webhook/SDK Platform | Lets A3 become embedded infrastructure rather than a standalone dashboard. | Versioned OpenAPI, SDK examples, webhook dry-run receipts, compatibility tests. |
| 7 | Mobile/WeChat Release Review | Valuable for China/mobile approval workflows, but depends on backend trust. | Server-side auth/RBAC/audit and guarded action request path. |

Auditor call: the first two directions should be packaged together as the main
enterprise offer:

```text
Ashr++ Enterprise Release Gate:
enforced PR gate + release evidence packet + identity-bound approval
+ offline audit verifier + self-host/private deployment option.
```

That is more valuable than "AI eval dashboard" because it owns a decision:
whether an agent release is allowed to merge, who approved exceptions, and what
evidence survives after the fact.

## Round 6 Acceptance Bar

The next implementation round should be considered commercially meaningful only
if it produces at least one of these hard outcomes:

1. A branch-protection readback receipt that proves required-check enforcement
   or explicitly proves it is not enforced.
2. A v2 release evidence summary that is referenced by dashboard, hosted
   report, report center, review workflow, usage ledger, audit bundle, and
   GitHub readback fixtures.
3. A self-host/offline verifier packet that a customer can run without cloud
   access.
4. A trace ingestion plus replay receipt path that turns a real run/trace into
   a replayable incident artifact.
5. A billing/usage export that is append-only, tenant-scoped, admin-approved,
   and still performs no live billing mutation.

If the next round only adds more panels or client shells without closing one of
those loops, it will improve demo breadth but not materially improve money-grade
readiness.
