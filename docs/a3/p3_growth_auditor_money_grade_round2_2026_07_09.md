# A3 Growth-Auditor Money-Grade Round 2 - 2026-07-09

Role: A3 Growth-Auditor / Money-Grade Auditor.

Workspace: repository root, redacted for portability.

Branch/status checked first:

```text
## agent/a3-commercial-growth-round2...origin/agent/a3-commercial-cl-gate
```

The initial `git status --short --branch` output showed no modified files before this docs-only round.

Write boundary followed:

- Wrote this file.
- Appended checklist items to `docs/a3/acceptance_checklist.md`.
- Did not edit runtime code, tests, fixtures, workflows, env files, or generated evidence.
- Did not read or print `.env.local`.
- Did not call live ReleaseFoundry, GitHub, billing, auth, database, object storage, or cloud APIs.
- Did not revert or overwrite anyone else's work.

## Executive Verdict

A3 is no longer just a local dashboard. It is now pilot-sellable as an early release-governance control plane for AI-agent changes:

```text
A1/A2 run and judge evidence
  -> A3 release evidence authority
  -> PR gate / report / review / audit packet
  -> sanitized readback capture
  -> Report Center / Artifact Registry / usage ledger
```

Compared with a commercial ReleaseFoundry product, A3 has enough evidence discipline to sell a controlled design-partner or internal platform pilot. It is not ready to sell as production enterprise enforcement until live branch-protection readback, real identity/RBAC, immutable storage, object custody, self-host packaging, billing exports, and browser E2E proof are present.

Money-grade position:

| Area | Current A3 | Commercial ReleaseFoundry expectation | Auditor call |
|---|---|---|---|
| PR gate | CL commercial anchor gate, GitHub Check/PR comment payloads, readback contracts, readback capture API/CLI. | Live GitHub App/CI readback, branch protection required-check enforcement, stale/missing/deleted proof. | Strongest money wedge, but not enforceable yet. |
| Release evidence | v2 summary/health/diff, A1/A2 counts, readback linkage, SQL/SQLite contracts. | Immutable source snapshots, stable ids, content hashes, source artifact ledger, state history. | Pilot-sellable if framed as authority-in-progress. |
| Enterprise audit | Audit bundle, artifact registry, signed archive direction, export firewall, hosted report lifecycle. | Offline verifier packet, detached signatures, object lock, retention/legal hold, tamper tests. | Credible audit story, still pre-compliance. |
| Review workflow | Durable hash-sealed waiver/approval records and dashboard/report visibility. | SSO/OIDC/GitHub actor binding, signature verification, role policy, separation of duties. | Valuable, but cannot unblock production without identity proof. |
| Production replay | Incident Replay Queue, Observability Replay Matrix, Regression Factory concepts already exist. | Production trace ingestion, replay pack, executable replay runner receipt, RCA export. | Good expansion surface, not the first paid wedge. |
| Self-host | SQLite store, SQL migration contracts, self-host readiness docs. | Installable package, Postgres/RLS, object storage, backup/restore, offline verifier. | Raises ACV later; incomplete today. |
| Billing/usage | Read-only usage ledger for runs, cases, reports, views, revokes, readbacks, imports. | Append-only usage events, quota/entitlements, chargeback, invoice-ready export. | Monetization foundation, not billing yet. |
| API platform | Local API routes and route docs for A3 workflows. | Versioned OpenAPI, SDK examples, webhooks, compatibility/error/idempotency tests. | Needed for enterprise integration. |

Best paid package:

```text
Enforced Agent PR Gate
  + Release Evidence Authority
  + Enterprise Audit Packet
  + Identity-Bound Review Workflow
```

Do not sell A3 yet as:

- production-enforced GitHub required check;
- SOC2-grade compliance system;
- complete self-host install;
- real billing platform;
- SSO/RBAC-bound approval workflow;
- live production replay engine.

## Evidence Read This Round

Primary current-round evidence:

- `docs/a3/p3_growth_auditor_cl_gate_2026_07_09.md`
- `docs/a3/p3_cl_gate_typescript_playwright_gap_2026_07_09.md`
- `docs/a3/p3_cl_gate_a1_a2_contract_alignment_2026_07_09.md`
- `docs/a3/acceptance_checklist.md`

Release evidence/readback/review/storage evidence:

- `docs/a3/p3_release_evidence_readback_capture_api_2026_07_08.md`
- `docs/a3/p3_readback_worker_and_visibility_2026_07_08.md`
- `docs/a3/p3_growth_auditor_readback_worker_round_2026_07_08.md`
- `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md`
- `docs/a3/p3_sqlite_store_growth_2026_07_08.md`
- `docs/a3/p3_growth_auditor_release_evidence_v2_2026_07_08.md`

Supporting repo signal:

- `README.md` positions A3 as product/release control tower, not a finished hosted SaaS.
- `docs/a3/worklog.md` records CL commercial gate, Playwright advisory state, release evidence/readback, review workflow, SQL/usage/report center, and safety boundaries.

## This Round Parallel Progress

| Lane | Artifact | What advanced | Commercial interpretation |
|---|---|---|---|
| Playwright | `docs/a3/p3_cl_gate_typescript_playwright_gap_2026_07_09.md` | Named dashboard syntax, CSS quality, Playwright TS E2E, mobile/desktop layout, official-demo parity, admin/billing/review/report flows. | Advanced as executable specs and gap map, not as real Playwright CI proof. |
| Evidence | `docs/a3/p3_growth_auditor_cl_gate_2026_07_09.md` plus acceptance checklist entries | Framed A3 as readback-capable CL/PR gate with release evidence, report center, artifact registry, audit bundle, usage, review, self-host direction. | Advanced money narrative and evidence gate posture; live provider proof still missing. |
| Integration | `docs/a3/p3_cl_gate_a1_a2_contract_alignment_2026_07_09.md` | Mapped A1 runtime/trace/API/SDK contracts, A2 judge/release-policy/calibration contracts, and A3 report/gate/readback/audit contracts into low-noise CL checks. | Advanced cross-lane contract discipline; default CL still avoids live ReleaseFoundry/GitHub/browser/billing checks. |

## Next Growth Points

Scale used below:

- Paid willingness: whether the point makes a buyer more likely to pay.
- ACV: whether it can raise deal size.
- Launch risk: whether it lowers production/merge/security risk.
- Enterprise/self-host/audit: which enterprise value it supports.
- Parallel status: whether this round already pushed the area through Playwright, Evidence, or Integration docs.

| ID | Category | Growth point | Next landed artifact | Parallel status | Paid willingness | ACV | Launch risk | Enterprise/self-host/audit |
|---|---|---|---|---|---|---|---|---|
| PG-01 | PR gate | Live GitHub Check readback worker. | CI/GitHub App worker submits sanitized check receipt to `POST /api/a3/releases/:releaseId/readbacks`. | Evidence + Integration | High | High | High | Enterprise audit |
| PG-02 | PR gate | PR comment readback worker. | Marker/body hash/head SHA reader with stale/missing/deleted states. | Evidence + Integration | High | Medium | High | Enterprise audit |
| PG-03 | PR gate | Branch-protection required-check verifier. | Readback proving `ReleaseFoundry Release Gate` is configured and enforced on target branch. | Evidence + Integration | Very high | High | Very high | Enterprise audit |
| PRP-01 | Production replay | Replay pack schema. | Case ids, trace ids, tool calls, expected outputs, judge refs, media metadata, payload hashes. | Evidence | Medium | Medium | High | Audit |
| PRP-02 | Production replay | Replay runner receipt. | `reproduced`, `fixed`, `flaky`, `new_failure`, `not_runnable` receipt with diff. | Evidence | Medium | Medium | High | Audit |
| PRP-03 | Production replay | Replay state in release health. | Evidence health flags stale replay, missing replay pack, and regression mismatch. | Evidence + Integration | Medium | Medium | High | Enterprise audit |
| EA-01 | Enterprise audit | Offline verifier packet. | Export summary, manifest, bundle index, archive receipt, hashes, and verify command. | Evidence | High | High | High | Enterprise + self-host + audit |
| EA-02 | Enterprise audit | Signed archive verifier. | Detached signature, key fingerprint, signer binding, expiry/revocation, tamper tests. | Evidence | High | High | High | Enterprise audit |
| EA-03 | Enterprise audit | Retention/legal-hold controls. | `retained_until`, legal hold, purge eligibility, purge receipt, object-lock readiness. | Evidence | Medium | High | High | Enterprise audit |
| SH-01 | Self-host | Installable self-host smoke package. | API, dashboard, SQLite/Postgres target, object storage stub, worker, verifier. | Evidence | High | High | Medium | Self-host |
| SH-02 | Self-host | Postgres/RLS and migration drill. | Migration apply/verify, RLS tenant tests, backup/restore smoke. | Integration | High | High | Very high | Enterprise + self-host |
| SH-03 | Self-host | Offline no-cloud validation path. | Self-host command validates report/audit packet without external services. | Evidence | High | High | Medium | Self-host + audit |
| TI-01 | Trace ingestion | Production trace ingestion contract. | Versioned ingest schema for A1/ReleaseFoundry/OTEL trace events, tool calls, errors, latency, media refs. | Integration | High | Medium | High | Enterprise audit |
| TI-02 | Trace ingestion | Idempotent trace import route. | Batch trace import with validation errors, payload hashes, source refs, and tenant scope. | Integration | Medium | Medium | High | Enterprise |
| TI-03 | Trace ingestion | Redacted media/reference handling. | Signed URL redaction, media hash refs, screenshot/PDF artifact references. | Playwright + Evidence | Medium | Medium | High | Audit |
| JC-01 | Judge calibration | A2 calibration in gate health. | Gate health includes judge version, calibration matrix, confidence, drift, false-pass/false-block status. | Integration | High | Medium | High | Enterprise audit |
| JC-02 | Judge calibration | Judge registry hash linkage. | A3 v2 summary references A2 judge registry and release-policy hashes. | Integration | Medium | Medium | High | Audit |
| JC-03 | Judge calibration | Low-confidence review queue. | Reviewer workflow item opens when calibration drift or judge disagreement is detected. | Evidence + Integration | Medium | Medium | Medium | Enterprise |
| IR-01 | Incident report | Customer-safe RCA export. | Incident report with timeline, evidence refs, replay state, judge result, next action. | Evidence | Medium | Medium | Medium | Enterprise audit |
| IR-02 | Incident report | Incident-to-regression promotion. | One-click or CLI promotion from incident item into replay/regression candidate. | Evidence | Medium | Medium | High | Enterprise |
| IR-03 | Incident report | Incident evidence packet. | Packet joins trace, replay, reviewer, release evidence, hosted report, registry artifacts. | Evidence | Medium | High | Medium | Audit |
| RW-01 | Review workflow | Identity-bound approvals. | SSO/OIDC/GitHub actor alias, role, org/project scope, expiry, artifact hashes. | Evidence + Integration | High | High | High | Enterprise audit |
| RW-02 | Review workflow | Cryptographic signature verification. | Verify signer/key before approval can affect release state. | Evidence | High | High | High | Enterprise audit |
| RW-03 | Review workflow | Reviewer SLA/escalation. | Owner, due date, stale waiver, missing evidence, escalation target, disposition history. | Evidence | Medium | Medium | Medium | Enterprise |
| BU-01 | Billing/usage | Usage event ids tied to `summary_id`. | Append-only ids for imports, readbacks, views, revokes, verifier runs, archive bytes, retained days. | Evidence | High | Medium | Medium | Enterprise + billing audit |
| BU-02 | Billing/usage | Quota and chargeback preview. | Read-only plan limits, forecasts, overage, team/project/repo chargeback views. | Evidence | High | High | Low | Enterprise |
| BU-03 | Billing/usage | Billing export. | Stripe/invoice-ready metering export after admin approval, with no live billing mutation by default. | Evidence | High | High | Medium | Enterprise audit |
| API-01 | API platform | Versioned OpenAPI. | Release evidence v1/v2, readbacks, health, diff, review, report center, usage, errors, idempotency. | Integration | High | Medium | High | Enterprise |
| API-02 | API platform | Webhook dry-run receipts. | `health_changed`, `readback_changed`, `share_revoked`, `verifier_failed`, `archive_verified`. | Integration | Medium | Medium | Medium | Enterprise |
| API-03 | API platform | SDK examples and compatibility tests. | Public examples for import/gate/readback/report workflows plus backwards compatibility checks. | Integration | Medium | Medium | High | Enterprise + self-host |
| PW-01 | Cross-cutting visual proof | Real Playwright TS E2E lane. | Dashboard, Report Center, hosted report, denied page, admin/billing guardrails, review workflow, mobile screenshots. | Playwright | High | Medium | High | Enterprise audit |
| PW-02 | Cross-cutting visual proof | Layout/leak assertions. | Console-error, blank-panel, overflow, overlap, and secret-leak screenshot assertions. | Playwright | Medium | Medium | High | Enterprise audit |

## Category Coverage Summary

Required categories covered:

- PR gate: PG-01 through PG-03.
- Production replay: PRP-01 through PRP-03.
- Enterprise audit: EA-01 through EA-03.
- Self-host: SH-01 through SH-03.
- Trace ingestion: TI-01 through TI-03.
- Judge calibration: JC-01 through JC-03.
- Incident report: IR-01 through IR-03.
- Review workflow: RW-01 through RW-03.
- Billing/usage: BU-01 through BU-03.
- API platform: API-01 through API-03.

The table includes 32 growth points. The strongest next 10 are PG-03, PG-01, EA-01, RW-01, SH-02, API-01, TI-01, JC-01, BU-01, and PW-01.

## Money Ranking

| Rank | Direction | Why it can make money | What must be proven next |
|---:|---|---|---|
| 1 | PR gate | Directly enters merge-control budget and creates a clear block/release workflow. | Live Check/PR readback, branch-protection proof, worker identity. |
| 2 | Enterprise audit | Security/compliance buyers pay for evidence that survives time, staff changes, and disputes. | Offline verifier, signatures, retention/legal hold, object custody. |
| 3 | Review workflow | Turns blocked releases into accountable human decisions. | Identity binding, signature verification, SLA/escalation. |
| 4 | Trace ingestion + replay | Moves A3 from pre-merge evidence to daily operations and incident response. | Trace import, replay pack, runner receipt, RCA export. |
| 5 | Self-host | Opens private-data and regulated-buyer deals. | Install package, Postgres/RLS, object storage, backup/restore. |
| 6 | Billing/usage | Converts evidence volume into chargeback and pricing. | Event ids, quota preview, billing export. |
| 7 | API platform | Lets enterprises integrate A3 into release portals and automation. | OpenAPI, webhooks, SDK examples, compatibility tests. |
| 8 | Judge calibration | Reduces false-block objections and improves trust in automation. | Calibration matrix, drift monitor, low-confidence review queue. |

## Failure Points

No runtime test failure was observed in this docs-only audit round. Product failure points remain:

1. Live GitHub branch protection is not proven; required-check enforcement must stay a plan until readback exists.
2. Readback capture accepts sanitized evidence, but without signed worker identity it cannot prove who submitted it.
3. Tenant scope is locally tested, but not hosted-auth/RBAC enforced.
4. Release evidence v2 is strong, but source snapshots are not yet immutable across every surface.
5. Review approvals are durable records, not production sign-off until identity and signature verification are real.
6. Usage ledger is not billing until event ids, quotas, entitlements, and invoice/export flows exist.
7. Self-host is not complete until install, Postgres/RLS, object storage, backup/restore, and offline verification are proven.
8. Playwright coverage is still a specification/gap artifact, not an executed browser CI lane.
9. Enterprise audit should not claim retention/legal hold/object custody until those controls exist.
10. Production replay and incident reports remain expansion workflows until real trace ingestion and replay receipts land.

## Auditor Call

A3 should not spend the next round on broad dashboard polish. The shortest path to commercial ReleaseFoundry is:

```text
live PR gate readback
  + immutable release evidence source snapshots
  + offline audit verifier
  + identity-bound review approvals
  + OpenAPI/usage event ids
  + Playwright proof for the buyer-facing surfaces
```

This is the path from "good local product factory" to "agent release infrastructure a platform/security buyer can pay for."
