# P3 Release Evidence Authority Round API Handoff - 2026-07-08

Role: A3 release evidence authority handoff.

Scope: documentation artifact only. This file defines the next API, storage, verification, and product proof round for release evidence authority. It does not claim any live service was contacted.

Safety boundary:

- Write scope for this round is this file only.
- Do not edit runtime code, tests, fixtures, screenshots, generated reports, worklogs, or secret-bearing files in this handoff round.
- Do not read `.env.local`.
- Do not call live Ashr, GitHub, billing, identity, webhook, database, object storage, or hosted-report APIs.
- Do not include secret-bearing values, private contact values, credential values, browser session material, URL-bearing expiring media credentials, or local absolute user paths.
- Use repo-relative paths in evidence references and command examples.

Implementation note:

After this handoff was drafted, the same A3 authority round implemented the first safe subset of the plan:

- `services/report/a3_release_evidence.mjs`
- release evidence health, next action, and sanitized diff helpers
- release evidence API health/next-action fields
- tenant/project guards for release evidence reads
- tenant/project guards for report detail, manifest, view, revoke, and list routes
- scoped Report Center, Artifact Registry, Product Console, usage-ledger, and hosted snapshot inputs
- SQLite report tenant persistence
- API internal-error redaction

The remaining sections below still describe the broader v2 authority roadmap. They should not be read as fully completed production claims.

## Executive Handoff

A3 has crossed the first API-backed release evidence threshold:

- `/api/a3/dashboard` includes sanitized `release_evidence_summary`.
- `GET /api/a3/releases/:releaseId/evidence-summary` exists as a v1 API response contract.
- Hosted reports include `release_evidence_summary` and `release_evidence_snapshot`.
- Denied hosted report pages omit report body evidence.
- Report Center manifest includes `release_evidence_summary`.
- Artifact Registry treats `release_evidence_summary` as a first-class artifact.
- SQL migration contract includes `release_evidence_summaries`.
- SQLite persistence stores release evidence summary rows from dashboard snapshots.

The next release evidence authority round should not add another display surface. It should make release evidence the authoritative, tenant-scoped, immutable, API-backed health object used by Dashboard, War Room, Report Center, hosted reports, PR Gate, audit bundle, signed archive, usage ledger, and self-host verification.

Target buyer-facing promise:

```text
For each release candidate, A3 exposes one redacted evidence health object that proves what was imported, gated, reviewed, published, shared, verified, retained, billed, and blocked or approved.
```

## Current Repo Evidence

| Evidence | Current signal | Next authority requirement |
|---|---|---|
| `docs/a3/p3_api_backed_release_evidence_2026_07_08.md` | Records the current v1 API-backed release evidence work. | Promote from v1 summary to v2 authority/health contract. |
| `tests/a3/a3_api_server.test.mjs` | Asserts health, dashboard, release evidence API response, hosted report, manifest, Report Center, Artifact Registry, review workflow, and revoke paths. | Add tenant-negative, v2 health, evidence diff, webhook, and readback cases. |
| `tests/a3/shareable_report.test.mjs` | Proves hosted report payload wraps release evidence, denied pages omit body, and secret-like report data is redacted. | Prove immutable summary snapshot is frozen after hosted report creation. |
| `tests/a3/report_builder.test.mjs` | Proves report export emits release evidence and redaction behavior. | Prove v1/v2 compatibility and fail-closed publish eligibility. |
| `tests/a3/a3_sqlite_store.test.mjs` | Proves local SQL persistence for A3 store paths. | Add release evidence snapshots, readbacks, verifier receipts, and lifecycle rows. |
| `tests/a3/a3_sql_usage_report_center.test.mjs` | Proves usage ledger and Report Center linkage. | Join usage rows directly to release evidence summary id and manifest id. |
| `tests/a3/a3_github_integration.test.mjs` | Proves dry-run/live-capable publish shapes and sanitized receipts. | Add readback-confirmed Check and PR comment evidence with stale/missing states. |
| `tests/a3/a3_gate_cli.test.mjs` | Proves gate, artifact manifest, bundle, waiver, approval, and GitHub evidence sealing. | Bind Gate CLI outputs to the same release evidence summary id. |
| `tests/a3/a3_review_workflow.test.mjs` | Proves durable waiver/approval records and validation reuse. | Bind review records to provider identity, role, expiry, and separation-of-duties result. |
| `tests/a3/a3_audit_archive.test.mjs` | Proves signed archive manifest and verifier behavior. | Make archive verifier receipt a first-class release evidence health field. |
| `tests/a3/report_center_manifest_contract.test.mjs` | Proves Report Center manifest shape. | Require manifest references to summary snapshot, diff, readback, usage, verifier, and retention ids. |
| `tests/a3/sql_adapter_contract.test.mjs` | Proves SQL migration contract. | Extend SQLite/Postgres migration contract for v2 release evidence authority tables. |

## Authority Object

The canonical object for the next round is `a3.release_evidence_summary.v2`.

It should be treated as a health contract, not a decorative report field. Every surface may render a subset, but all surfaces must reference the same `summary_id`, `release_id`, `tenant_scope`, `source_snapshot_id`, and `content_hash`.

Required v2 envelope:

| Field | Requirement |
|---|---|
| `schema_version` | `a3.release_evidence_summary.v2`. |
| `summary_id` | Stable id referenced by API, hosted report, manifest, War Room, PR Gate, ledger, and verifier. |
| `tenant_scope` | Organization/project/repository boundary. All reads and joins must include tenant predicates. |
| `release_identity` | Release id, environment, repo slug alias, PR number, branch alias, head SHA, source import receipt ids. |
| `health` | Overall status, blocking reason, next action, accountable lane, stale evidence flags, and last computed time. |
| `release_gate` | Decision, policy version, threshold version, blocks-merge intent, and source report hash. |
| `github_check_readback` | Generated receipt status, readback status, check name, conclusion, head SHA match, stale/missing/deleted states, sanitized error class. |
| `pr_comment_readback` | Generated receipt status, readback status, marker hash, body hash match, head SHA match, stale/missing/deleted states, sanitized error class. |
| `required_check_proof` | Branch-protection readback status, required check name, enforcement state, admin approval receipt, stale policy state. |
| `review_identity` | Review/waiver/approval ids, actor provider, role, signer binding, expiry, separation-of-duties result. |
| `redaction` | Fail-closed status across JSON, Markdown, CSV, HTML, hosted report, Check payload, PR comment, manifest, bundle, archive, logs, and screenshots. |
| `hosted_report` | Snapshot id, snapshot hash, status, expiry state, revoke state, denied-view counts, auth-required state, redaction-blocked state. |
| `report_center_manifest` | Manifest id, artifact ids, lifecycle state, verification state, retention/legal-hold state. |
| `artifact_registry` | Artifact ids and hashes for report, hosted HTML, GitHub evidence, bundle, archive, visual evidence, and docs. |
| `audit_bundle` | Bundle id, root hash, artifact count, verifier receipt id, missing/tampered summary. |
| `signed_archive` | Archive id, archive hash, signature status, key fingerprint alias, signer binding, verifier receipt id. |
| `usage_ledger` | Usage event ids for imports, snapshots, views, denied views, revocations, verifier runs, retained bytes, and PR Gate events. |
| `storage` | SQLite readiness, Postgres migration readiness, migration version, immutable snapshot table readiness, object storage placeholder state. |
| `webhooks` | Last event ids and delivery contract state for summary-created, readback-changed, share-revoked, verifier-failed, and archive-verified events. |
| `api_docs` | OpenAPI schema version, examples version, error shape version, compatibility policy. |
| `compliance` | Retention policy, legal-hold state, purge eligibility, audit event chain, export safety status. |

Allowed health statuses:

- `missing`
- `collecting`
- `blocked_redaction`
- `blocked_required_check`
- `blocked_review`
- `blocked_verifier`
- `blocked_tenant_scope`
- `stale_readback`
- `ready_for_review`
- `ready_to_publish`
- `published`
- `archived`
- `retained`

## API Handoff Contract

The next implementation round should keep v1 stable and add v2 explicitly.

Required API surfaces:

| Route or contract | Authority behavior |
|---|---|
| `GET /api/a3/releases/:releaseId/evidence-summary` | Returns v1 by default until v2 is requested, then returns `a3.release_evidence_summary.v2`. |
| `GET /api/a3/releases/:releaseId/evidence-health` | Returns compact health summary for Dashboard, War Room, and PR Gate. |
| `GET /api/a3/releases/:releaseId/evidence-diff?from=<id>&to=<id>` | Compares two summaries or snapshots without exposing raw evidence bodies. |
| `GET /api/a3/reports/:reportId/manifest` | Includes summary id, snapshot id, v2 health state, usage event ids, verifier ids, and retention state. |
| `GET /api/a3/reports/center` | Lists release evidence health, lifecycle, and next action for each hosted report. |
| `GET /api/a3/artifacts/registry` | Includes release evidence summary, diff, GitHub readback, PR comment readback, required-check proof, visual evidence, bundle, and archive artifact entries. |
| Webhook contract | Emits versioned events for release evidence state changes, with dedupe key, tenant scope, payload hash, and no raw sensitive values. |

The API must fail closed:

- Unknown release id returns a controlled not-found error.
- Cross-tenant release id returns not-found or denied without body evidence.
- Redaction failure blocks every external publish path.
- Missing readback must never be reported as readback-confirmed.
- Required-check plan must never be reported as enforcement proof.
- Hosted report denied states must never render summary details or case evidence.

## Executable Growth Points

These are intentionally build-shaped. Each item has a concrete implementation target and proof path.

| ID | Topic | Build target | Required proof |
|---|---|---|---|
| REA-01 | v2 summary/health contract | Add `a3.release_evidence_summary.v2` schema with health, identity, readback, lifecycle, ledger, storage, webhook, and compliance fields. | `node --test tests/a3/release_evidence_summary_v2_contract.test.mjs` proves required fields, null-safe states, redaction defaults, and v1 compatibility. |
| REA-02 | API version negotiation | Extend `GET /api/a3/releases/:releaseId/evidence-summary` to serve v1 default and v2 explicit contract. | `node --test tests/a3/a3_api_server.test.mjs tests/a3/release_evidence_summary_v2_contract.test.mjs` proves default v1, explicit v2, 404, and sanitized errors. |
| REA-03 | Evidence health endpoint | Add compact `evidence-health` API for fast Dashboard, War Room, PR Gate, and monitor reads. | API test proves health status, blocking reason, next action, stale flags, and no body evidence. |
| REA-04 | Tenant scoping | Add tenant predicates to release evidence summary, snapshot, manifest, ledger, audit, and report reads. | `node --test tests/a3/tenant_scope_release_evidence.test.mjs` seeds two tenants and proves cross-tenant reads, revokes, views, manifests, and usage rows fail closed. |
| REA-05 | Immutable snapshots | Persist v2 summary snapshots with snapshot id, content hash, builder version, source receipt ids, redaction policy version, and created actor class. | `node --test tests/a3/shareable_report.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_sqlite_store.test.mjs` proves hosted reports render the original snapshot after source state changes. |
| REA-06 | Evidence diff | Add summary diff contract across attempts, head SHAs, hosted snapshots, and archive versions. | `node --test tests/a3/release_evidence_diff.test.mjs` proves fixed regression, new blocker, stale GitHub evidence, revoked report, archive change, and no raw body leakage. |
| REA-07 | GitHub Check readback | Add readback receipt fields for check id alias, check name, conclusion, repo alias, head SHA match, stale/missing/deleted state, and sanitized error class. | `node --test tests/a3/a3_github_integration.test.mjs tests/a3/github_readback_contract.test.mjs` proves dry-run, live-shaped mock readback, stale SHA, deleted check, missing permissions, and sanitized failure. |
| REA-08 | PR comment readback | Add marker hash, body hash, PR number, head SHA match, update time, stale/missing/deleted state, and sanitized error class. | `node --test tests/a3/a3_github_integration.test.mjs tests/a3/pr_comment_readback_contract.test.mjs` proves body hash match/mismatch, missing marker, deleted comment, stale SHA, and safe errors. |
| REA-09 | Required-check proof | Convert required-check plan into branch-protection readback proof with admin approval receipt and policy timestamp. | `node --test tests/a3/required_check_proof.test.mjs tests/a3/a3_github_integration.test.mjs` proves configured, missing, wrong check name, stale policy, insufficient permission, and plan-only states. |
| REA-10 | Review identity binding | Bind waiver/approval records to provider subject alias, role, expiry, artifact hash, signature verification status, and separation-of-duties result. | `node --test tests/a3/a3_review_workflow.test.mjs tests/a3/review_identity_binding.test.mjs` proves valid, expired, wrong role, same actor blocked, unknown signer, and review evidence only when not production-verified. |
| REA-11 | Redaction fail-closed | Make summary `external_publish_allowed=false` unless all external artifact classes pass redaction. | `node --test tests/a3/report_builder.test.mjs tests/a3/export_firewall_generated_artifacts.test.mjs tests/a3/release_evidence_redaction_fail_closed.test.mjs` proves JSON, Markdown, CSV, HTML, PR, Check, manifest, bundle, archive, logs, and screenshots block on findings. |
| REA-12 | Hosted report lifecycle | Record created, viewed, denied, expired, revoked, auth-required, and redaction-blocked states against summary snapshot id. | `node --test tests/a3/shareable_report.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs` proves denied pages omit body and lifecycle events attach to summary id. |
| REA-13 | Report Center manifest | Extend manifest release packet with summary id, snapshot id, diff id, readback ids, verifier ids, usage ids, retention state, and legal-hold state. | `node --test tests/a3/report_center_manifest_contract.test.mjs tests/a3/report_center_index.test.mjs` proves manifest readiness and artifact ids are stable. |
| REA-14 | Usage ledger linkage | Link imports, snapshots, hosted views, denied views, revocations, verifier runs, retained bytes, and PR Gate publish attempts to the summary id. | `node --test tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/usage_ledger_release_evidence.test.mjs` proves append-only rows join to summary id, report id, manifest id, and tenant scope. |
| REA-15 | SQLite/Postgres migration | Add release evidence v2 tables and migration contract for snapshots, diffs, readbacks, required-check proof, verifier receipts, webhook deliveries, and compliance state. | `node --test tests/a3/sql_adapter_contract.test.mjs tests/a3/a3_sqlite_store.test.mjs` plus a Postgres SQL syntax check fixture proves indexes, tenant keys, hash fields, and migration version. |
| REA-16 | Self-host offline verifier | Add export packet and verifier command that validates summary, manifest, bundle, archive, and hashes without cloud access. | `node --test tests/a3/self_host_offline_verifier.test.mjs tests/a3/self_host_console_contract.test.mjs tests/a3/a3_audit_archive.test.mjs` proves pass, tampered summary, missing artifact, bad archive signature, and offline mode. |
| REA-17 | Webhook contract | Define release evidence events: summary created, health changed, GitHub readback changed, PR comment readback changed, hosted report revoked, verifier failed, archive verified, retention changed. | `node --test tests/a3/release_evidence_webhook_contract.test.mjs` proves event schema, dedupe key, tenant scope, payload hash, retry class, and no raw evidence bodies. |
| REA-18 | Dashboard and War Room integration | Make Dashboard Release Evidence, War Room, Report Center, and Review Workflow consume the same v2 health object. | `node --test tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs` proves one summary id appears across dashboard payload, War Room JSON, Markdown, and report preview. |
| REA-19 | API docs | Add OpenAPI-style contract docs for v1/v2 summary, health, diff, manifest, webhook, error shapes, and compatibility rules. | `node --test tests/a3/api_docs_release_evidence.test.mjs` or docs contract test proves examples are placeholder-only, schema names match code, and errors are stable. |
| REA-20 | Playwright visual evidence | Add deterministic visual QA for Dashboard Release Evidence, War Room, Report Center, hosted report, denied page, and mobile layout. | `node --test tests/a3/playwright_release_evidence_visual.test.mjs` or equivalent Playwright command captures repo-relative screenshots and asserts no denied body leakage or overlapping key text. |
| REA-21 | Billing and usage | Add billing-adjacent usage plan fields without enabling billing mutations: metered event count, quota status, retained bytes, verifier run count, hosted view count, and overage preview. | `node --test tests/a3/a3_saas_admin.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/billing_usage_release_evidence.test.mjs` proves read-only billing state and ledger-backed counts. |
| REA-22 | Enterprise compliance | Add retention policy, legal-hold state, purge eligibility, audit chain ids, archive storage class, signer/key status aliases, and compliance export state. | `node --test tests/a3/a3_enterprise_readiness.test.mjs tests/a3/enterprise_compliance_release_evidence.test.mjs` proves retained, hold, purge blocked, purge eligible, archive verified, and compliance packet states. |
| REA-23 | Audit bundle and archive chain | Bind audit bundle root hash and signed archive verifier receipt into the same health object. | `node --test tests/a3/a3_gate_cli.test.mjs tests/a3/a3_audit_archive.test.mjs tests/a3/release_evidence_verifier_chain.test.mjs` proves bundle pass/fail and archive pass/fail flow into health. |
| REA-24 | Artifact Registry authority | Add first-class registry entries for v2 summary, health, diff, readbacks, required-check proof, verifier receipts, webhook receipts, visual evidence, and compliance packet. | `node --test tests/a3/artifact_registry.test.mjs tests/a3/report_center_index.test.mjs` proves packet presets include authority artifacts. |
| REA-25 | API error and idempotency guard | Add stable validation errors, idempotency keys for readback capture, and replay-safe summary recompute. | `node --test tests/a3/a3_api_server.test.mjs tests/a3/release_evidence_idempotency.test.mjs` proves duplicate replay, conflict, validation error, and sanitized error body. |
| REA-26 | Backward compatibility | Keep `a3.release_evidence_summary.v1`, `a3.release_evidence_api_response.v1`, hosted v1 snapshots, and existing report exports stable while v2 ships. | Current focused tests continue passing; new compatibility test proves v1 consumers can ignore v2 fields. |

## Parallelization Plan

Execution should be parallel after REA-01 defines the v2 field names:

- Contract lane: REA-01, REA-02, REA-03, REA-19, REA-26.
- Storage lane: REA-04, REA-05, REA-14, REA-15, REA-25.
- Evidence provider lane: REA-07, REA-08, REA-09, REA-10, REA-23.
- Safety and lifecycle lane: REA-11, REA-12, REA-13, REA-24.
- Product lane: REA-18, REA-20, REA-21, REA-22.
- Self-host/integration lane: REA-06, REA-16, REA-17.

Do not serialize GitHub readback, PR comment readback, tenant scoping, redaction fail-closed, immutable snapshots, and verifier chain work. They reduce different production risks and can land behind the same v2 summary contract.

## Acceptance Criteria

The next release evidence authority implementation round is accepted only when all criteria below pass:

- `a3.release_evidence_summary.v2` is documented, implemented, and tested while v1 remains stable.
- Every release evidence read is tenant/project scoped, including API, store, SQLite, manifest, usage ledger, audit events, and hosted report lifecycle.
- Dashboard, War Room, Report Center, hosted report, PR Check payload, PR comment payload, audit bundle, archive, and usage ledger all reference the same summary id.
- Hosted reports render immutable summary snapshots and do not change when source state changes after sharing.
- Evidence diff can compare two attempts or snapshots by id and show changed health states without raw body evidence.
- GitHub Check evidence distinguishes generated receipt, posted receipt, readback-confirmed state, stale state, missing state, deleted state, and sanitized error state.
- PR comment evidence distinguishes generated receipt, posted receipt, readback-confirmed state, marker mismatch, body hash mismatch, stale state, missing state, deleted state, and sanitized error state.
- Required-check proof comes from branch-protection readback, not from a plan-only artifact.
- Review approvals and waivers are bound to identity provider aliases, roles, expiry, artifact hash, signature status, and separation-of-duties result.
- Redaction fail-closed blocks JSON, Markdown, CSV, HTML, hosted report, GitHub Check, PR comment, manifest, bundle, archive, logs, and screenshots from external publish when unsafe.
- Hosted report active, expired, revoked, missing, auth-required, and redaction-blocked states are recorded and denied pages omit report body evidence.
- Report Center manifest includes summary id, snapshot id, readback ids, diff id, verifier ids, usage event ids, retention state, and legal-hold state.
- Usage ledger rows join to summary id and manifest id for imports, snapshots, views, denied views, revocations, verifier runs, retained bytes, and PR Gate events.
- SQLite store persists the v2 authority rows, and Postgres migration SQL is generated or contract-tested with equivalent keys and indexes.
- Self-host offline verifier can validate summary, manifest, bundle, archive, and hashes without cloud access.
- Webhook contract exists for release evidence state changes, with dedupe keys, payload hashes, retry classes, and tenant scoping.
- API docs include v1/v2 summary, health, diff, manifest, webhook, error, idempotency, compatibility, and redaction examples using placeholders only.
- Playwright or equivalent visual evidence proves Dashboard Release Evidence, War Room, Report Center, hosted report, denied page, and mobile layout render cleanly.
- Billing/usage remains read-only unless a separate billing system is approved, but usage counts are ledger-backed.
- Enterprise compliance states cover retention, legal hold, purge eligibility, audit chain, archive signature, signer binding, and offline verifier evidence.

## Exact Tests To Run

Current baseline commands after implementation:

```powershell
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/shareable_report.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
node --test tests/a3/a3_api_server.test.mjs
node --test tests/a3/a3_store.test.mjs
node --test tests/a3/a3_sqlite_store.test.mjs
node --test tests/a3/a3_sql_usage_report_center.test.mjs
node --test tests/a3/report_center_index.test.mjs
node --test tests/a3/report_center_manifest_contract.test.mjs
node --test tests/a3/artifact_registry.test.mjs
node --test tests/a3/a3_github_integration.test.mjs
node --test tests/a3/a3_gate_cli.test.mjs
node --test tests/a3/a3_review_workflow.test.mjs
node --test tests/a3/a3_audit_archive.test.mjs
node --test tests/a3/a3_enterprise_readiness.test.mjs
node --test tests/a3/a3_saas_admin.test.mjs
node --test tests/a3/sql_adapter_contract.test.mjs
node --test tests/a3/self_host_console_contract.test.mjs
node --test tests/a3/export_firewall_generated_artifacts.test.mjs
```

New authority tests to add and run:

```powershell
node --test tests/a3/release_evidence_summary_v2_contract.test.mjs
node --test tests/a3/tenant_scope_release_evidence.test.mjs
node --test tests/a3/release_evidence_diff.test.mjs
node --test tests/a3/github_readback_contract.test.mjs
node --test tests/a3/pr_comment_readback_contract.test.mjs
node --test tests/a3/required_check_proof.test.mjs
node --test tests/a3/review_identity_binding.test.mjs
node --test tests/a3/release_evidence_redaction_fail_closed.test.mjs
node --test tests/a3/usage_ledger_release_evidence.test.mjs
node --test tests/a3/self_host_offline_verifier.test.mjs
node --test tests/a3/release_evidence_webhook_contract.test.mjs
node --test tests/a3/api_docs_release_evidence.test.mjs
node --test tests/a3/playwright_release_evidence_visual.test.mjs
node --test tests/a3/billing_usage_release_evidence.test.mjs
node --test tests/a3/enterprise_compliance_release_evidence.test.mjs
node --test tests/a3/release_evidence_verifier_chain.test.mjs
node --test tests/a3/release_evidence_idempotency.test.mjs
```

Syntax and focused source checks expected after code changes:

```powershell
node --check services/report/a3_api_server.mjs
node --check services/report/a3_store.mjs
node --check services/report/a3_sqlite_store.mjs
node --check services/report/a3_github_integration.mjs
node --check services/report/a3_gate_cli.mjs
node --check services/report/a3_report_center.mjs
node --check services/report/a3_report_center_manifest.mjs
node --check services/report/a3_artifact_registry.mjs
node --check services/report/report_builder.mjs
node --check apps/dashboard/src/app.mjs
git diff --check
```

Full A3 regression command:

```powershell
node --test --test-concurrency=1 tests/a3/*.test.mjs
```

Visual evidence command shape for the future Playwright lane:

```powershell
node --test tests/a3/playwright_release_evidence_visual.test.mjs
```

The visual test must capture repo-relative artifacts for:

- Dashboard Release Evidence.
- Release War Room.
- Report Center manifest/inventory.
- Active hosted report.
- Revoked or expired hosted report denied page.
- Mobile release evidence layout.

## Evidence Artifacts To Produce

The next implementation round should produce these repo-safe artifacts or fixtures:

- Golden v1 summary fixture proving backward compatibility.
- Golden v2 summary fixture proving health contract completeness.
- Golden health response fixture.
- Golden diff fixture for improved, regressed, stale, and revoked states.
- Hosted report HTML fixture bound to a summary snapshot id and hash.
- Denied hosted report HTML fixture with no body evidence.
- Report Center manifest fixture with summary, snapshot, readback, usage, verifier, and retention ids.
- GitHub Check readback fixture with head SHA match/mismatch states and sanitized error classes.
- PR comment readback fixture with marker/body hash states and sanitized error classes.
- Required-check proof fixture distinguishing plan-only from enforced.
- Review identity binding fixture with role, expiry, signer status, and separation-of-duties result.
- Redaction fail-closed fixture for every external artifact class.
- SQLite fixture or migration output for release evidence v2 rows.
- Postgres migration SQL or SQL contract fixture for release evidence v2 rows.
- Offline verifier receipt fixture for pass, missing artifact, tampered hash, and bad archive signature.
- Webhook contract fixture for every release evidence event type.
- API docs fixture with placeholder examples only.
- Playwright screenshot set under repo-relative screenshot paths.
- Usage ledger fixture linked to summary id and manifest id.
- Enterprise compliance fixture with retention, legal hold, purge, archive, and verifier states.

## Explicit Non-Claims

This handoff does not claim:

- Live GitHub readback was performed.
- Branch protection was configured or mutated.
- PR comments were posted to a live pull request.
- Production auth, RBAC, SSO, or identity provider binding is complete.
- Postgres is deployed or serving production traffic.
- Billing mutations or invoice integrations are enabled.
- Object storage, legal-hold, or archive retention is production-grade.
- Self-host packaging is complete.
- Playwright authority screenshots already exist for the v2 workflow.

## Risk Notes For The Next Owner

| Risk | Why it matters | Guardrail |
|---|---|---|
| v2 becomes a larger fixture | Buyers will notice if API-backed means static JSON through HTTP. | Require SQLite and Postgres-ready persistence with tenant predicates and immutable hashes. |
| Required-check proof is overstated | A plan does not prove merge enforcement. | Only branch-protection readback can set `required_check_proof.enforced=true`. |
| Readback is confused with publish receipt | A local receipt does not prove external state still exists. | Separate generated, posted, readback-confirmed, stale, missing, deleted, and failed states. |
| Hosted report reads mutable data | External evidence becomes unauditable. | Hosted reports must render snapshot content by id and content hash. |
| Redaction is advisory | External report, PR, Check, or screenshot output could leak unsafe content. | Compute publish eligibility from fail-closed redaction results across every external artifact. |
| Tenant scope is implicit | Cross-tenant evidence leakage is a severe SaaS failure. | Add two-tenant negative tests for API, store, SQLite, manifest, ledger, audit, and hosted report lifecycle. |
| Review identity is free text | Enterprise sign-off needs accountable identity and policy checks. | Bind review records to provider aliases, role, expiry, signature status, and separation of duties. |
| Usage is disconnected from evidence | Billing and quota claims are not credible without source events. | Join append-only usage rows to summary id, report id, manifest id, and tenant scope. |
| Self-host verifier depends on cloud | Regulated customers need offline proof. | Verifier must run from exported packet inputs without cloud calls. |
| Visual evidence is screenshot-only | Screenshots can become stale or unverified. | Playwright must assert DOM state, denied-body absence, layout health, and artifact path/hash metadata. |

## Recommended Next Commit Scope

First implementation commit:

1. Add `a3.release_evidence_summary.v2` schema builder and contract tests.
2. Add v2 response negotiation on the existing evidence summary route.
3. Add summary id propagation to Dashboard, War Room, hosted report snapshot, Report Center manifest, Artifact Registry, and usage ledger.
4. Add tenant-scope negative tests before any live readback work.

Second implementation commit:

1. Add immutable snapshot persistence and evidence diff.
2. Add GitHub Check readback and PR comment readback using live-shaped local fixtures only.
3. Add required-check proof contract with plan-only versus enforced distinction.

Third implementation commit:

1. Add redaction fail-closed publish eligibility.
2. Add offline verifier packet.
3. Add webhook contract and API docs.
4. Add Playwright visual evidence and enterprise compliance fields.

That sequence makes the authority object real before expanding the external integration story.
