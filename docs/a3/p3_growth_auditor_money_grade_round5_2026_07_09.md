# A3 Growth-Auditor Money-Grade Round 5 - 2026-07-09

Role: Evidence-Agent / Growth-Auditor.

Scope: docs-only audit artifact. Write boundary for this round is this new file
under `docs/a3/`. Existing A1/A2/A3 docs, fixtures, services, and tests were
read only as evidence. No secrets, `.env*`, raw API keys, cookies, account
values, or private evidence were read or quoted.

## Executive Verdict

A3 is closer to a commercial SaaS than it was in the prior Money-Grade audit,
but the improvement is still mostly in evidence discipline, local API shape,
browser-level local proof, and audit packaging. The current product can be
framed as a design-partner release-governance pilot. It should not be framed as
production enterprise enforcement until GitHub branch-protection readback,
hosted identity/RBAC, production storage, object custody, billing export,
self-host install proof, and trace ingestion/replay receipts are real.

The strongest commercial wedge remains:

```text
A1 trace/run ingestion
  + A2 judge/release-gate evidence
  + A3 release evidence authority
  + PR gate/readback
  + review workflow
  + audit packet
```

This round should push A3 toward a commercial SaaS by making the above chain
live-shaped, tenant-scoped, verifiable, and priced. The next work should not be
more dashboard surface area unless it proves one of those controls.

## Evidence Baseline

| SaaS dimension | Current evidence | Commercial gap to close |
|---|---|---|
| PR gate | `docs/a3/p3_github_readback_contract_2026_07_08.md` distinguishes generated, posted, readback-confirmed, stale, missing, deleted, permission-denied, and failed states; `tests/a3/a3_gate_cli.test.mjs` asserts GitHub Check/PR comment shapes, audit bundle sealing, and redaction. | No live GitHub App/CI readback, no branch-protection required-check proof, and no worker identity binding. |
| Production replay | `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md` derives failed-case replay from A1 trace/tool-call data and A2 judge evidence; `fixtures/a2/results/a2_regression_replay_report.json` shows replay is still seed maturity with 1 current replay case and 3 reviewed external evidence targets missing. | Need production trace import, replay-pack schema, executable replay runner receipt, and incident-to-regression promotion. |
| Enterprise audit | `tests/a3/a3_gate_cli.test.mjs` verifies generated artifact manifests, audit bundle root hashes, bundle verification pass/fail, and tamper rejection; `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json` is committed redacted evidence. | Need detached signatures, key/signer binding, retention/legal hold, object-lock readiness, and offline customer verifier packet. |
| Self-host | `docs/a1/self_host_runtime_scaffold.md` documents local API/worker/Postgres/Redis/object-store scaffold; `docs/a3/p3_self_host_console_growth_2026_07_07.md` lists self-host console routes, tables, environment redaction, and operator health checks; `tests/a1/test_local_self_host_smoke_compose.py` validates compose boundaries. | Need installable package, Postgres/RLS apply drill, backup/restore, object storage custody, and no-cloud verifier. |
| Trace ingestion | `docs/a1/saas_ingestion_quickstart.md` has local SDK/CLI trace ingestion and release evidence packet flow; `docs/a1/schemas/trace_event.schema.json` anchors `ashr.clone.trace.v1`; `tests/a1/test_saas_control_plane.py` covers submit/upload/trace ingestion/quota/audit. | A3 still lacks a production `POST /api/a3/traces/import` route and trace ingestion receipt linked to release evidence. |
| Judge calibration | `fixtures/a2/results/a2_commercial_readiness_report.json` says `ready_for_commercial_gate=false`, semantic live evidence is not merged, 6 audited semantic observations are missing, and regression replay maturity is seed; `docs/a2/schemas/calibration_matrix.schema.json` anchors calibration shape. | Need live audited semantic judge calls, official grading reviewed rows, judge drift health, and low-confidence review queue. |
| Incident report | `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md` maps trace, tool-error, latency, judge, media, and replay readiness; `tests/a3/report_builder.test.mjs` covers A2 regression/commercial readiness summaries and incident/replay-linked report sections. | Need customer-safe RCA export with timeline, evidence refs, replay state, reviewer disposition, and regression promotion receipt. |
| Review workflow | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md` adds waiver/approval API and durable hash-sealed records; `tests/a3/a3_review_workflow.test.mjs` verifies accepted waiver/approval records, hashes, and no real cloud mutation. | Need SSO/OIDC/GitHub actor binding, cryptographic signature verification, role policy, SLA/escalation, and separation-of-duties enforcement at API level. |
| Billing/usage | `tests/a3/a3_sql_usage_report_center.test.mjs` verifies `a3.usage_ledger.v1`, read-only billing mutation disabled, meters for runs/cases/judges/reports/views/readbacks/imports; `docs/a1/saas_ingestion_quickstart.md` includes usage billing rollup primitives. | Need append-only usage event IDs, entitlement/quota policy, chargeback preview, billing-admin approval, and invoice/Stripe-ready export. |
| API platform | `docs/a3/p3_api_backed_release_evidence_2026_07_08.md` makes release evidence API-backed and DB-ready; `tests/a3/a3_api_server.test.mjs` verifies dashboard, release evidence v1/v2, health, diff, hosted report, review workflow, and denied report routes. | Need versioned OpenAPI for A3, compatibility tests, idempotency/error contracts, webhooks, SDK examples, and production auth/RBAC. |

## How This Round Should Move Toward Commercial SaaS

1. PR gate: convert readback contracts into a real CI/GitHub App worker path.
   Evidence says local receipts are not enough: `docs/a3/p3_github_readback_contract_2026_07_08.md` explicitly says required-check proof stays `plan_only` until branch-protection readback confirms enforcement. `tests/a3/a3_release_evidence.test.mjs` also asserts `required_check_proof.enforced=false` when proof is plan-only.

2. Production replay: stop treating replay as dashboard context only. A2 already has an executable regression replay fixture in `fixtures/a2/results/a2_regression_replay_report.json`, but the same fixture says current replay case count is 1 while target is 3 and reviewed external evidence count is 0. A3 should create replay packs and receipts instead of another replay panel.

3. Enterprise audit: make the audit bundle customer-verifiable outside the repo. Current proof is strong locally because `tests/a3/a3_gate_cli.test.mjs` covers bundle root hashes and tamper rejection, but enterprise buyers need a portable verifier packet, signature metadata, retention policy, and archive/object custody evidence.

4. Self-host: turn self-host from contract docs into an installation smoke. `docs/a1/self_host_runtime_scaffold.md` and `docs/a3/p3_self_host_console_growth_2026_07_07.md` define the path; `tests/a1/test_local_self_host_smoke_compose.py` validates public-secret hygiene. The missing SaaS proof is an end-to-end self-host receipt with API, dashboard, DB, worker, audit, and verifier passing together.

5. Trace ingestion: A1 has local trace ingest and A3-consumable release evidence packets in `docs/a1/saas_ingestion_quickstart.md`; A3 must expose an import route and receipt that preserves A1 trace hashes, observation counts, tool-call refs, and redaction status.

6. Judge calibration: A2 is honest about not being commercially ready. `fixtures/a2/results/a2_commercial_readiness_report.json` has `ready_for_commercial_gate=false`, missing reviewed Ashr grading observations, and offline-only semantic judge rows. A3 gate health should surface those as blockers, not bury them in docs.

7. Incident report: A3 has Incident Replay and Observability Replay docs, but no customer-safe RCA artifact. The next round should export timeline, impacted run/case, A1 trace refs, A2 judge result, replay status, reviewer decision, and follow-up regression link.

8. Review workflow: hash-sealed waiver/approval records are good evidence, but not production sign-off. `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md` says real reviewer identity binding through SSO/OIDC/GitHub is future work. That is the next paid-enterprise step.

9. Billing/usage: usage exists as read-only meters, not billing. `tests/a3/a3_sql_usage_report_center.test.mjs` proves `billing_mutations_enabled=false`. Keep that safety boundary, but add invoice-ready export behind billing-admin approval.

10. API platform: A3 has routes, but not a platform contract. `tests/a3/a3_api_server.test.mjs` already proves v1/v2 release evidence and denied hosted reports. The next round should publish OpenAPI, idempotency keys, safe error shapes, compatibility tests, and webhook dry-run receipts.

## Next-Round Growth Points

| ID | Category | Growth point | Evidence anchor | Next landed artifact |
|---|---|---|---|---|
| MG5-01 | PR gate | Build live GitHub Check readback worker that posts sanitized status into A3. | `docs/a3/p3_github_readback_contract_2026_07_08.md`; `tests/a3/a3_release_evidence.test.mjs` | `POST /api/a3/releases/:releaseId/readbacks` worker receipt fixture |
| MG5-02 | PR gate | Add branch-protection required-check verifier for `Ashr++ Release Gate`. | `tests/a3/a3_gate_cli.test.mjs`; `fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json` | required-check readback receipt with `enforced=true/false` |
| MG5-03 | PR gate | Add stale/missing/deleted PR comment readback states to release health. | `docs/a3/p3_github_readback_contract_2026_07_08.md` | release evidence v2 state transition tests |
| MG5-04 | Production replay | Define A3 replay-pack schema using A1 trace IDs, tool calls, A2 judge refs, media refs, and payload hashes. | `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`; `docs/a1/schemas/trace_event.schema.json`; `docs/a2/schemas/regression_replay.schema.json` | `a3.replay_pack.v1` schema and fixture |
| MG5-05 | Production replay | Add replay runner receipt statuses: reproduced, fixed, flaky, new_failure, not_runnable. | `fixtures/a2/results/a2_regression_replay_report.json`; `packages/ts/ashr-clone/test/cloud-queue.test.mjs` | replay receipt test and report export |
| MG5-06 | Production replay | Promote incident replay items into A2 regression candidates with reviewer disposition. | `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md`; `fixtures/a2/results/a2_regression_replay_report.json` | incident-to-regression promotion receipt |
| MG5-07 | Enterprise audit | Build portable offline verifier packet joining report, manifest, bundle index, archive receipt, and hashes. | `tests/a3/a3_gate_cli.test.mjs`; `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json` | `a3.audit_verifier_packet.v1` |
| MG5-08 | Enterprise audit | Add detached signature metadata and signer/key fingerprint checks to archive verification. | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md`; `tests/a3/a3_audit_archive.test.mjs` | signed archive verifier test |
| MG5-09 | Enterprise audit | Add retention/legal-hold plan-only controls and purge eligibility receipts. | `docs/a3/p3_self_host_console_growth_2026_07_07.md`; `docs/a3/p3_growth_auditor_round_sql_usage_report_center_2026_07_07.md` | retention policy API and audit events |
| MG5-10 | Self-host | Ship self-host smoke receipt across API, dashboard, DB, worker, audit, and verifier. | `docs/a1/self_host_runtime_scaffold.md`; `tests/a1/test_local_self_host_smoke_compose.py` | self-host smoke JSON and CLI command |
| MG5-11 | Self-host | Add Postgres/RLS migration apply/verify drill with tenant negative tests. | `tests/a3/a3_sql_usage_report_center.test.mjs`; `docs/a3/p3_sqlite_store_growth_2026_07_08.md` | Postgres/RLS contract test |
| MG5-12 | Self-host | Add backup/restore and no-cloud verifier flow for regulated buyers. | `docs/a3/p3_self_host_console_growth_2026_07_07.md` | offline restore receipt and verifier pass |
| MG5-13 | Trace ingestion | Add `POST /api/a3/traces/import` with idempotency, payload hash, tenant scope, and redaction pre-scan. | `docs/a1/saas_ingestion_quickstart.md`; `tests/a1/test_saas_control_plane.py` | trace import route test |
| MG5-14 | Trace ingestion | Store trace ingestion receipts in release evidence v2 and Report Center manifest. | `tests/a3/a3_release_evidence.test.mjs`; `tests/a3/a3_sql_usage_report_center.test.mjs` | `trace_ingestion_receipt` artifact |
| MG5-15 | Trace ingestion | Add media/signed-URL reference handling that stores hashes and metadata only. | `packages/ts/ashr-clone/test/cloud-api.test.mjs`; `tests/a3/report_builder.test.mjs` | media reference redaction test |
| MG5-16 | Judge calibration | Surface A2 calibration matrix, judge versions, and drift status in release health. | `docs/a2/schemas/calibration_matrix.schema.json`; `fixtures/a2/results/a2_commercial_readiness_report.json` | release evidence `judge_calibration` field |
| MG5-17 | Judge calibration | Import six reviewed Ashr grading observations before changing readiness claims. | `fixtures/a2/results/a2_commercial_readiness_report.json`; `docs/a2/worklog/a2_growth_audit_20260707.md` | reviewed grading import fixture and A3 summary |
| MG5-18 | Judge calibration | Add low-confidence/disagreement queue item to reviewer workflow. | `tests/a3/a3_review_workflow.test.mjs`; `fixtures/a2/results/a2_g3_calibration_matrix.json` | reviewer workflow calibration item |
| MG5-19 | Incident report | Add customer-safe RCA export with timeline, evidence refs, replay status, judge result, and next action. | `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`; `tests/a3/report_builder.test.mjs` | `a3.incident_report.v1` export |
| MG5-20 | Incident report | Link incident reports to hosted report snapshots and denied-view audit state. | `docs/a3/p3_commercial_growth_round4_e2e_review_admin_denied_2026_07_09.md`; `tests/e2e/a3-dashboard-api-backed.spec.ts` | incident hosted-report access audit |
| MG5-21 | Incident report | Add incident packet artifact to audit bundle and artifact registry. | `tests/a3/a3_gate_cli.test.mjs`; `docs/a3/p3_growth_auditor_artifact_registry_2026_07_07.md` | incident packet hash in bundle |
| MG5-22 | Review workflow | Bind approvals to SSO/OIDC/GitHub actor identity, org/project role, expiry, and artifact hashes. | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md`; `tests/a3/a3_review_workflow.test.mjs` | identity-bound approval receipt |
| MG5-23 | Review workflow | Verify cryptographic signatures before approval can affect release state. | `tests/a3/a3_gate_cli.test.mjs`; `docs/a3/p3_signed_approval_validation_growth_2026_07_07.md` | signature verification gate |
| MG5-24 | Review workflow | Add reviewer SLA/escalation fields for stale waivers and missing evidence. | `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md`; `tests/e2e/a3-dashboard-api-backed.spec.ts` | reviewer workflow SLA fixture |
| MG5-25 | Billing/usage | Attach append-only usage event IDs to `summary_id`, hosted views, readbacks, verifier runs, archive bytes, and retained days. | `tests/a3/a3_sql_usage_report_center.test.mjs`; `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | usage event linkage test |
| MG5-26 | Billing/usage | Add quota/chargeback preview by tenant, project, repo, and release candidate. | `docs/a1/saas_ingestion_quickstart.md`; `packages/ts/ashr-clone/test/cloud-api.test.mjs` | read-only chargeback report |
| MG5-27 | Billing/usage | Add billing export behind explicit billing-admin approval, still no live billing mutation by default. | `docs/a3/p3_saas_admin_action_requests_2026_07_08.md`; `tests/e2e/a3-dashboard-commercial.spec.ts` | invoice-ready export fixture |
| MG5-28 | API platform | Publish A3 OpenAPI for release evidence v1/v2, readbacks, health, diff, review, report center, usage, and errors. | `tests/a3/a3_api_server.test.mjs`; `docs/a2/openapi/a2_judge_service.openapi.json` | `docs/a3/openapi/a3_api.openapi.json` |
| MG5-29 | API platform | Add idempotency and safe error-shape tests for all mutating A3 routes. | `tests/a1/test_saas_control_plane.py`; `tests/a3/a3_api_server.test.mjs` | A3 idempotency/error contract tests |
| MG5-30 | API platform | Add webhook dry-run receipts for health changed, readback changed, share revoked, verifier failed, archive verified. | `docs/a1/saas_ingestion_quickstart.md`; `docs/a3/p3_release_evidence_authority_round_2026_07_08.md` | webhook receipt fixtures and docs |
| MG5-31 | Cross-cutting E2E | Put Playwright commercial specs in CI gate when browser install is stable. | `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`; `tests/e2e/a3-dashboard-commercial.spec.ts` | CI Playwright job with screenshot artifact |
| MG5-32 | Cross-cutting E2E | Add secret/leak/overflow/blank-panel screenshot assertions across desktop and mobile. | `tests/e2e/a3-dashboard-api-backed.spec.ts`; `tests/a3/tailwind_boundary_contract.test.mjs` | visual regression + no-leak E2E |

## Money Ranking

| Rank | Direction | Why it sells | Gate before claiming production |
|---:|---|---|---|
| 1 | Live PR gate | Enters the buyer's merge-control workflow and creates a direct block/release budget. | GitHub readback, branch-protection proof, worker identity. |
| 2 | Enterprise audit packet | Compliance/security buyers pay for evidence that survives disputes and audits. | Offline verifier, signatures, retention/legal hold, object custody. |
| 3 | Identity-bound review workflow | Converts release blocks into accountable human decisions. | SSO/OIDC/GitHub identity, signature checks, role policy. |
| 4 | Trace ingestion + replay | Moves A3 from pre-merge control to incident response and operations. | Trace import, replay pack, runner receipt, RCA export. |
| 5 | Self-host | Unlocks private-data and regulated-customer deals. | Install package, Postgres/RLS, backup/restore, object storage. |
| 6 | Billing/usage | Turns evidence volume into pricing and internal chargeback. | Usage event IDs, entitlements, billing-admin approval, invoice-ready export. |
| 7 | API platform | Lets enterprises integrate A3 into release portals and automation. | OpenAPI, webhooks, SDK examples, idempotency/error compatibility. |
| 8 | Judge calibration | Reduces false-block objections and improves trust in automated release gates. | Reviewed official grading rows, audited semantic calls, drift/low-confidence workflow. |

## Failure Points To Keep Honest

1. Required-check enforcement is still not proven until GitHub branch protection is read back.
2. Readback capture is not enterprise proof without signed worker identity.
3. A3 tenant scope is locally tested but not backed by hosted auth/RBAC.
4. Review records are durable hashes, not identity-bound production approvals.
5. A2 commercial readiness is explicitly false until reviewed official grading and audited semantic evidence land.
6. A2 regression replay is still seed maturity, with missing reviewed external evidence.
7. Usage ledger is not billing while `billing_mutations_enabled=false` and no entitlement/export flow exists.
8. Self-host is still a scaffold until install, DB, worker, audit, restore, and verifier pass together.
9. Trace/replay are evidence views until A3 imports production traces and records replay receipts.
10. Enterprise audit cannot claim retention/legal hold/object custody until those controls are implemented and tested.

## Auditor Call

The next A3 round should be a conversion round: convert local evidence and
contract docs into production-shaped receipts. The best target is not another
page. The best target is a live-shaped PR gate plus release-evidence authority
packet that can be verified offline, reviewed by identity-bound humans, metered
for usage, and installed in self-host mode without leaking secrets.

Recommended build order:

```text
1. GitHub readback worker and required-check proof
2. Release evidence v2 source snapshot and trace import receipt
3. Offline audit verifier packet with signature metadata
4. Identity-bound review approval receipt
5. Usage event IDs and OpenAPI/webhook contracts
6. Self-host smoke receipt
```

That is the shortest path from "credible local release-governance factory" to
"commercial SaaS control plane a platform/security buyer can pay for."
