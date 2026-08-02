# A3 Growth-Auditor Round - SQL Usage And Report Center - 2026-07-07

Role: A3 Growth-Auditor / commercial SaaS auditor.

Scope: documentation artifact only. This round focuses the next commercial implementation wave on SQL migrations, usage ledger, billing/read-only quotas, report center manifest, CI export firewall, PR gate integration, hosted report lifecycle, and self-host deployment. It does not change runtime code, tests, fixtures, schemas, credentials, or secret-bearing files.

Safety boundary:

- Read local repo evidence only.
- Did not read, print, edit, or rely on `.env.local`.
- Did not call live ReleaseFoundry, GitHub, billing, hosted auth, database, or external APIs.
- Did not modify code.
- Modified only this artifact, with an optional append-only worklog note in `docs/a3/worklog.md`.

## Auditor Summary

A3 now has the right commercial shape: import routes, hosted report HTML, redaction-aware exports, PR gate artifacts, audit bundle planning, SQL adapter contracts, and self-host console contracts. The next money round should stop treating these as separate features and make them one governed SaaS workflow.

The product should be able to prove this sentence:

> This release imported these exact A1/A2 evidence hashes, stored them in tenant-scoped SQL rows, charged only the intended usage units, exported only firewall-cleared artifacts, published a governed hosted report, linked the same sealed manifest to the PR gate, and can be operated by a customer in self-host mode.

Most valuable next round:

1. Land SQL migrations and adapter parity for imports, reports, share links, audit events, and usage ledger.
2. Make usage and quotas billing-safe while keeping local/admin mutation read-only until real billing exists.
3. Promote Report Center into the manifest and hosted-report lifecycle control plane.
4. Put the CI export firewall in front of JSON, Markdown, CSV, PR comments, GitHub checks, manifests, bundles, and hosted report bodies.
5. Wire PR Gate to the same import receipts, report manifest, hosted report, readiness status, and audit bundle root hash.
6. Make self-host deployment observable: migrations, object storage, export worker, audit log, retention, and redaction policy must be health-checked.

## Current Evidence Base

| Area | Current evidence | Commercial interpretation |
|---|---|---|
| SQL adapter contract | `docs/a3/p3_sql_adapter_contract_2026_07_07.md` defines Postgres-compatible tables, idempotency ledger, audit events, report share/view tables, usage ledger, indexes, and fixture-to-SQL migration. | Strong blueprint exists; buyers need migration files, adapter tests, tenant scoping, and durable operational checks. |
| Import and hosted report lifecycle | `docs/a3/p3_growth_auditor_round_import_hosted_report_2026_07_07.md` maps idempotent A1/A2 ingest, validation errors, hosted report expiry, revocation, view audit, SQL, and PR/report center commercialization. | The next round can build from a clear commercial path instead of discovering requirements from scratch. |
| Self-host contract | `docs/a3/p3_self_host_console_growth_2026_07_07.md` defines console pages, API surface, required DB tables, env vars, health checks, retention, redaction controls, and A1/A2 compatibility. | Self-host can become an enterprise SKU if deployment readiness is proven, not merely documented. |
| Redaction/export firewall | `docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md` identifies CLI redaction evidence and report builder gaps across JSON, Markdown, CSV, fixtures, docs, GitHub checks, and generated artifacts. | Export safety is the difference between demo reports and security-reviewable enterprise artifacts. |
| PR gate workflow | `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md` documents GitHub check payloads, PR comments, waiver policy, reviewer lanes, audit bundle manifest, and incident replay packs. | PR Gate is the highest-value workflow once it references durable SQL evidence and firewall-cleared hosted reports. |
| Generated artifact manifest | `docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md` documents output hashes for JSON, Markdown, GitHub Check, and PR comment artifacts. | Report Center should make this manifest user-visible and link it to the hosted report and audit bundle. |
| Usage and quota posture | Existing docs name `usage_ledger`, usage/quota panels, billing forecast placeholders, and read-only admin constraints. | A3 should meter usage but avoid pretending to mutate billing until auth/RBAC/billing services are real. |

## Growth Points

Each growth point is tagged with one or more of `code`, `test`, `API`, `UI`, `docs`, `evidence` and mapped to direct money value, enterprise value, and risk reduction.

| ID | Growth point | Tags | Concrete next build | Money value | Enterprise value | Risk reduction |
|---|---|---|---|---|---|---|
| SURC-01 | Create the first Postgres migration set for tenant and project roots. | code, test, API, docs, evidence | Add migrations for `organizations`, `projects`, `users`, `roles`, `team_members`, and `api_keys` with tenant columns, status fields, redacted identity fields, and safe indexes. | Enables paid multi-tenant SaaS packaging instead of one local workspace. | Gives security teams a recognizable org/project/user model. | Prevents accidental cross-project data mixing as data volume grows. |
| SURC-02 | Create core A1/A2 evidence migrations. | code, test, API, evidence | Add `runs`, `cases`, `tool_calls`, `trace_events`, `grade_results`, `failure_clusters`, `a1_*_imports`, and `a2_*_imports` tables with source ids and payload hashes. | Makes imported evidence durable enough for paid CI and audit workflows. | Lets customers retain release evidence under policy. | Reduces loss or mismatch from fixture/file-backed state. |
| SURC-03 | Create commercial report migrations. | code, test, API, evidence | Add `shareable_reports`, `report_exports`, `report_share_links`, `report_share_revocations`, `report_share_views`, and `trust_reports`. | Creates the backend for report sharing, retention, and premium evidence packets. | Supports controlled customer/security report distribution. | Reduces exposure from raw report ids, unmanaged links, and untracked views. |
| SURC-04 | Create append-only audit and usage migrations. | code, test, API, evidence | Add `audit_events`, `usage_ledger`, `retention_policies`, and `redaction_scans` with required indexes and hash-chain fields. | Creates metering and compliance foundations for expansion revenue. | Gives auditors durable custody, retention, and policy evidence. | Reduces disputes about who generated, shared, viewed, or charged an artifact. |
| SURC-05 | Add migration verification command and artifact. | code, test, docs, evidence | Add a migration smoke that reports migration version, required table presence, index presence, and safe row counts without DB URLs or secrets. | Makes self-host setup easier to sell and support. | Gives platform teams deployment confidence. | Catches missing or drifted schema before customer data lands. |
| SURC-06 | Add store adapter parity tests across memory/file/SQL. | code, test, API, evidence | Run the same import/report/share/read contract suite against existing stores and the SQL adapter using seeded A1/A2 evidence. | Protects paid workflows during DB migration. | Demonstrates self-host and hosted behavior match. | Reduces regressions where SQL mode returns different evidence than dashboard mode. |
| SURC-07 | Add tenant scoping tests for every SQL read and write. | code, test, API, evidence | Prove runs, cases, grades, reports, share links, audit events, and usage rows cannot cross `organization_id` and `project_id`. | Required for larger ACV customers and platform plans. | Addresses enterprise security review directly. | Prevents the highest-severity SaaS data leak class. |
| SURC-08 | Add idempotency ledger SQL enforcement. | code, test, API, evidence | Enforce unique `(organization_id, project_id, operation, idempotency_key_hash)` and replay semantics for imports, report snapshots, exports, share links, and revocations. | Prevents duplicate billing and duplicate release evidence. | Gives CI/webhook integrations reliable retry behavior. | Reduces inconsistent state from retries, timeouts, and webhook redelivery. |
| SURC-09 | Add usage ledger writes for imports. | code, test, API, evidence | Record `run.imported`, `case.imported`, `trace_event.imported`, `grade.imported`, and `media.reference_created` with source ids and quantities. | Creates a billable usage backbone for evidence ingestion. | Lets customers allocate cost by team, project, and release. | Reduces quota disputes and duplicate-count risk. |
| SURC-10 | Add usage ledger writes for reports and exports. | code, test, API, evidence | Record report snapshots, JSON/Markdown/CSV/PDF exports, audit bundle exports, hosted views, and verifier runs. | Enables pricing on high-value report and compliance activity. | Gives governance teams cost visibility for audit workflows. | Prevents unmetered export growth and storage surprises. |
| SURC-11 | Add read-only quota summaries from usage ledger. | code, test, API, UI, evidence | Derive current-period usage, remaining quotas, soft-limit warnings, hard-limit blocks, and forecast from ledger rows; keep billing mutation disabled. | Supports packaging and upsell while avoiding fake billing integration. | Shows finance and platform owners predictable controls. | Reduces product risk from premature charge, invoice, or plan mutations. |
| SURC-12 | Add quota policy fixtures and tests. | test, API, docs, evidence | Cover free/trial/team/enterprise/self-host policies for run imports, cases, trace rows, exports, hosted views, storage bytes, and retained days. | Makes plan design concrete for sales and pricing. | Helps procurement see enforceable entitlements. | Reduces ambiguous quota behavior during pilots. |
| SURC-13 | Add billing-safe admin action planning. | code, test, API, UI, docs | Keep create/upgrade/downgrade/payment actions as plan-only receipts until auth, RBAC, audit, and billing provider integration exist. | Lets demos show commercial controls without unsafe money movement. | Gives owners reviewable billing-intent evidence. | Prevents accidental paid-plan or invoice mutations from local/dev shells. |
| SURC-14 | Add Report Center manifest model. | code, test, API, UI, evidence | Introduce a report-center manifest that links import receipts, report snapshot id, generated artifact manifest, audit bundle root hash, share links, view audit, and PR gate status. | Turns Report Center into the paid evidence packet hub. | Gives managers and auditors one source of truth. | Reduces mismatch between dashboard, PR comment, hosted page, and bundle. |
| SURC-15 | Add Report Center packet presets backed by manifest policy. | UI, test, API, docs, evidence | Add presets for PR review, customer evidence, security audit, incident replay, executive sign-off, and self-host readiness. | Creates packageable workflows for sales and customer success. | Lets different buyer personas get the right evidence packet. | Reduces manual export mistakes and over-sharing. |
| SURC-16 | Add manifest completeness scoring. | code, test, API, UI, evidence | Score each report packet for required imports, redaction pass, artifact hashes, hosted policy, PR gate link, approval state, and retention policy. | Makes premium readiness visible in product. | Gives enterprise admins a go/no-go checklist. | Prevents publishing incomplete or unverifiable packets. |
| SURC-17 | Add CI export firewall preflight. | code, test, API, docs, evidence | Create a reusable preflight that scans JSON, Markdown, CSV, PR comment, GitHub Check, generated manifest, audit bundle, and hosted HTML before write/publish. | Makes CI-generated artifacts safe enough for paid teams. | Satisfies security teams before external sharing. | Reduces secret, signed URL, local path, and CSV injection leakage. |
| SURC-18 | Add fail-closed firewall status to generated manifests. | code, test, API, evidence | Store scan policy version, finding counts, field paths, blocked status, and redaction log hash in generated artifact and report-center manifests. | Increases trust in paid audit bundles. | Gives auditors evidence that exports were checked, not merely assumed safe. | Reduces unverifiable redaction claims. |
| SURC-19 | Add docs and fixture scanner to CI. | test, docs, evidence | Scan `docs/a3` and `fixtures/a3/p3/*.redacted.*` for secret-like values, signed URLs, local home paths, and disallowed raw source excerpts with allowlisted literals. | Keeps customer-facing collateral clean as the repo grows. | Helps regulated buyers trust committed evidence. | Reduces accidental credential/account leakage through docs artifacts. |
| SURC-20 | Add PR Gate required-check integration contract. | code, test, API, docs, evidence | Define live required-check inputs and outputs using import receipts, readiness status, report manifest id, hosted report URL, audit bundle root hash, and waiver/approval state. | Moves A3 from advisory reporting to merge-control infrastructure. | Fits engineering governance workflows customers already budget for. | Reduces release risk by blocking merges on missing or unsafe evidence. |
| SURC-21 | Add dry-run/live separation for GitHub writer. | code, test, API, docs, evidence | Require explicit live mode, installed app metadata, firewall pass, branch protection policy, and safe payload preview before any GitHub mutation. | Unlocks production PR-gate value without reckless rollout. | Gives platform admins a controlled activation path. | Reduces accidental PR comments, check spam, or token-backed writes. |
| SURC-22 | Add PR comment and Check Run manifest links. | code, test, API, evidence | Include the same report-center manifest id, hosted report link, generated artifact hash, and audit bundle root hash in PR comment and Check Run output. | Makes A3 visible inside the workflow where budget decisions happen. | Gives reviewers a stable trail from PR to audit packet. | Reduces broken chain of custody between CI and Report Center. |
| SURC-23 | Add hosted report snapshot immutability. | code, test, API, evidence | Persist builder version, redaction policy, source import ids, content hash, manifest id, audit bundle root hash, and created-by metadata. | Supports premium hosted report and compliance retention plans. | Lets auditors prove exactly what was shared. | Reduces disputes from mutable report bodies. |
| SURC-24 | Add share-token lifecycle enforcement. | code, test, API, UI, evidence | Use hashed tokens, expiry, revocation, scope, created-by, last-viewed, and controlled denied pages for expired/revoked links. | Makes hosted reports safe enough for customer-facing sharing. | Meets common enterprise link-control requirements. | Reduces exposure from leaked or stale report URLs. |
| SURC-25 | Add hosted report view audit ledger. | code, test, API, evidence | Record allowed and denied views with share id, report id, actor/session class, user-agent hash, IP hash, and access result. | Creates compliance value around shared evidence. | Gives admins an audit trail for external/customer access. | Reduces blind spots after accidental sharing or incident review. |
| SURC-26 | Add hosted report lifecycle UI in Report Center. | UI, test, API, evidence | Show status, expiry, revoke action, last viewed, view count, firewall status, manifest completeness, and sealed evidence hash. | Makes the paid control plane tangible to buyers. | Gives admins operational control without database access. | Reduces support escalations for "is this report still live?" |
| SURC-27 | Add self-host deployment manifest. | docs, API, UI, evidence | Document image version, migration version, DB type, object storage mode, base URL, redaction policy, retention policy, worker status, and health-check result. | Turns self-host into a SKU with deployable proof. | Gives platform teams a standard readiness artifact. | Reduces failed deployments and unclear environment drift. |
| SURC-28 | Add self-host health checks for commercial dependencies. | code, test, API, UI, evidence | Check DB migration version, DB read/write transaction, object storage probe, export worker heartbeat, audit append/read, redaction policy, and A1/A2 compatibility. | Lowers enterprise onboarding cost and support load. | Gives operators a single health surface. | Fails closed before unsafe report/export/admin actions. |
| SURC-29 | Add retention/legal-hold enforcement plan. | code, test, API, UI, docs, evidence | Plan-only first: show purge candidates, legal holds, retained classes, usage aggregation, and audit events before any destructive purge exists. | Supports enterprise compliance tiers and renewal conversations. | Addresses legal/security retention requirements. | Reduces risk of deleting evidence needed for audit or incident replay. |
| SURC-30 | Add object-storage contract for exports and media metadata. | code, test, API, docs, evidence | Store only `storage_key_hash`, content hash, byte size, MIME type, scan status, expiry, and short-lived access policy. | Enables paid export/media workflows without leaking durable URLs. | Fits customer-managed storage and private-bucket requirements. | Reduces signed URL and credential exposure. |
| SURC-31 | Add enterprise readiness gate from SQL-backed facts. | code, test, API, UI, evidence | Compute readiness from migrations, import completeness, score-scale validity, redaction scans, hosted policy, PR gate linkage, audit log, and retention policy. | Converts readiness into a paid release-control feature. | Gives executives and auditors a defensible release signal. | Reduces false readiness from static fixture summaries. |
| SURC-32 | Add evidence replay from report-center manifest. | code, test, API, UI, evidence | Rebuild a packet from manifest ids and hashes, compare current rows/exports to recorded hashes, and report pass/fail. | Creates a high-value verification feature for audits and incidents. | Lets customers prove artifacts were not tampered with. | Reduces integrity risk after storage migration or incident response. |

## Topic Coverage

| Required topic | Covered by growth points | Auditor note |
|---|---|---|
| SQL migrations | SURC-01 through SURC-08 | Migrations should land before more hosted/customer state accumulates. |
| Usage ledger | SURC-04, SURC-09, SURC-10, SURC-11, SURC-12 | Usage must be append-only and source-linked before pricing depends on it. |
| Billing/read-only quotas | SURC-11, SURC-12, SURC-13 | Show quota and billing intent, but keep mutation disabled until real auth/RBAC/billing exist. |
| Report Center manifest | SURC-14, SURC-15, SURC-16, SURC-22, SURC-32 | Manifest links are the commercial bridge between dashboard, PR gate, hosted report, and audit bundle. |
| CI export firewall | SURC-17, SURC-18, SURC-19, SURC-21 | Every CI-produced external artifact should be scanned before write or publish. |
| PR gate integration | SURC-20, SURC-21, SURC-22, SURC-31 | Required checks become sellable only when tied to durable evidence and safe live-mode activation. |
| Hosted report lifecycle | SURC-03, SURC-23, SURC-24, SURC-25, SURC-26 | Hosted reports need immutable snapshots, token lifecycle, view audit, and admin visibility. |
| Self-host deployment | SURC-05, SURC-27, SURC-28, SURC-29, SURC-30 | Self-host must be deployable, observable, and retention-aware. |

## Buyer-Value Stack Rank

| Rank | Build package | Why it is money-grade |
|---:|---|---|
| 1 | SQL migrations plus adapter parity | Converts demo state into durable tenant-scoped product state. |
| 2 | Usage ledger plus read-only quota governance | Creates the pricing and chargeback foundation without unsafe billing mutation. |
| 3 | Report Center manifest | Makes A3's evidence packet coherent across UI, hosted report, PR gate, and audit bundle. |
| 4 | CI export firewall | Makes generated artifacts safe enough for customer and GitHub-facing workflows. |
| 5 | PR Gate required-check integration | Places A3 in the merge decision, where release-risk budget lives. |
| 6 | Hosted report lifecycle | Enables safe external sharing, revocation, and view audit. |
| 7 | Self-host deployment readiness | Opens enterprise and regulated-customer deals that cannot use a pure hosted SaaS. |

## Acceptance Criteria For The Next Round

The next implementation round should be considered commercially complete only if it can prove:

- Postgres migrations create tenant, import, report, share-link, audit, usage, retention, and redaction-scan tables with required indexes.
- Store contract tests pass across memory/file/SQL modes for import, report creation, share-link lifecycle, audit events, and usage rows.
- Tenant scoping tests prove no run, case, grade, report, share link, audit event, or usage row crosses organization/project boundaries.
- Usage ledger rows are emitted for imports, cases, traces, grades, report snapshots, exports, hosted views, verifier runs, and retained storage units.
- Quota summaries are derived from usage ledger rows and expose read-only plan/forecast status without live billing mutation.
- Report Center shows a manifest linking import receipts, report snapshot, generated artifacts, hosted links, PR gate status, audit bundle root hash, and firewall status.
- CI export firewall scans JSON, Markdown, CSV, PR comment, GitHub Check, generated manifest, audit bundle, docs, fixtures, and hosted HTML outputs.
- PR Gate output links to the same manifest, hosted report, readiness result, import receipts, and audit bundle root hash.
- Hosted report links use token hashes, expiry, revocation, lifecycle UI, and view audit events for allowed and denied views.
- Self-host readiness reports migration version, DB health, object storage health, export worker health, audit log health, redaction policy, retention policy, and A1/A2 compatibility without printing secrets.

## Auditor Call

The next A3 round should be a coherence round, not another surface-area round. The highest-return work is to make SQL, usage, Report Center, CI firewall, PR Gate, hosted reports, and self-host deployment all point at the same durable evidence chain.

If this round succeeds, A3 can sell a stronger promise:

> "We do not just show a release report. We preserve the evidence, meter it, scan it, manifest it, gate it, share it safely, and let your platform team operate it."
