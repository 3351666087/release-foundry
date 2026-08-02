# A3 Growth Auditor - Product Console Artifact Registry - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Money-Grade Auditor.

Focus: Product Console artifact registry as a sellable enterprise feature for the next A3 Artifact Registry round.

This is a bounded docs-only artifact. It audits whether A3 can turn report exports, hosted reports, GitHub artifacts, reviewer packets, replay bundles, manifests, audit bundles, and usage events into a durable Product Console registry that a buyer can understand, operate, and trust.

Safety boundary followed:

- Read local repo documentation and safe search results only.
- Did not read `.env.local`.
- Did not read API keys, cookies, tokens, live signed URLs, account data, or local secrets.
- Did not call the live ReleaseFoundry API.
- Did not call the live GitHub API.
- Did not edit code, tests, or fixtures.
- Created only `docs/a3/p3_growth_auditor_artifact_registry_2026_07_07.md`.

Evidence reviewed:

- `docs/a3/p3_growth_auditor_product_console_export_2026_07_07.md`
- `docs/a3/p3_report_center_manifest_growth_2026_07_07.md`
- `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`
- `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`
- `docs/a3/p3_self_host_console_growth_2026_07_07.md`
- `docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md`
- `docs/a3/p3_growth_auditor_onboarding_audit_project_console_2026_07_07.md`
- `docs/a3/acceptance_checklist.md`

## Executive Verdict

The Product Console artifact registry can become one of A3's most sellable enterprise features, but only if it is positioned as an evidence operating layer, not a file list.

The current A3 direction already has strong ingredients: Report Center manifest contract, required artifact names, lifecycle states, generated artifact manifest, audit bundle root hash, redaction safety requirements, hosted report lifecycle concepts, Product Console workflow state, self-host DB table direction, and usage-ledger direction.

That is enough for a credible paid design-partner pitch:

> "A3 does not just export an agent evaluation report. It registers every release-evidence artifact, binds it to source evidence, scans it for safety, tracks lifecycle events, and prepares it for review, sharing, verification, retention, and audit."

It is not yet enough for a production enterprise claim. The registry is still mostly a contract and growth direction, not a durable Product Console workflow with SQL rows, authenticated actors, object storage, access controls, enforceable retention, reviewer approvals, and full verification from source snapshot through customer-facing packet.

Commercial maturity score for this narrow artifact-registry track:

| Dimension | Score | Auditor read |
|---|---:|---|
| Buyer story | 8/10 | A managed evidence registry is easy for enterprise buyers to understand and budget for. |
| Contract clarity | 7.5/10 | Artifact ids, formats, lifecycle fields, safety fields, and audit events are documented. |
| Product Console fit | 6.5/10 | The console can become the front door, but registry UX is not yet the primary workflow. |
| Audit integrity | 6/10 | Hashing, manifest, bundle, root hash, and redaction direction exist; full sealed workflow remains unfinished. |
| Enterprise controls | 4.5/10 | Tenant scope, RBAC, SQL, retention, and usage are planned more than enforced. |
| Self-host readiness | 5/10 | The table and API direction is strong, but installer/storage/backup/restore are not complete. |
| Paid pilot readiness | 7/10 | Strong enough for local/self-host design partners if framed as controlled evidence workflow. |

## 1. Money-Grade Product Thesis

The artifact registry should be the Product Console's inventory of customer-facing evidence.

It should answer five enterprise buyer questions:

1. What artifacts exist for this release decision?
2. Which source run, judge result, PR, release, or report snapshot produced them?
3. Were they redacted, hashed, verified, approved, shared, revoked, retained, or purged?
4. Who did each action, under what tenant/project scope, and when?
5. Can an auditor later prove that the reviewed evidence did not change?

That is more valuable than another dashboard chart. Dashboards help teams notice risk. A registry helps teams govern risk.

The sellable feature name should be direct:

> Product Console Artifact Registry

Enterprise SKU language:

> "A tenant-scoped registry for AI release-evidence artifacts, including report exports, hosted reports, GitHub evidence, audit bundles, replay packs, reviewer boards, usage ledgers, hashes, redaction status, lifecycle events, and retention policy."

## 2. Capabilities That Can Sell

These capabilities are commercially useful now or immediately after a focused registry implementation round.

| Capability | Why it can sell | Buyer persona | Honest readiness |
|---|---|---|---|
| Registered JSON report | Gives automation and CI a canonical machine-readable evidence artifact. | Platform engineering | Contract-ready, needs durable registry row. |
| Registered Markdown report | Gives reviewers the exact human-readable packet they reviewed. | Engineering manager, reviewer | Strong pilot value. |
| Registered CSV export | Lets QA and operations triage failures in spreadsheet workflows. | QA, support ops | Needs CSV safety proof. |
| Registered PDF/print packet | Gives executives a sign-off artifact with a hashable identity. | Director, VP, audit lead | Needs deterministic PDF or captured print hash. |
| Hosted report registry entry | Tracks shared report lifecycle, expiry, revocation, and view audit. | Security, customer success | Strong buyer story, enforcement still pending. |
| PR comment artifact | Shows the exact PR-facing release evidence summary. | Engineering teams | Useful once linked to manifest id and update marker. |
| GitHub Check artifact | Makes release-gate status auditable beyond a transient CI run. | Platform engineering | Needs live required-check path later. |
| Generated artifact manifest | Hashes customer-facing outputs and reduces drift between formats. | Auditor, security | Already strong as direction; expand coverage. |
| Audit bundle index | Groups source, generated, governance, and custody records under a root hash. | Compliance, internal audit | Strong local evidence; needs durable packaging. |
| Bundle verifier result | Lets a reviewer prove whether the packet changed after sign-off. | Auditor, release owner | Sellable in local mode with clear caveats. |
| Reviewer board artifact | Makes required review lanes visible as evidence, not tribal process. | Safety reviewer, manager | Needs identity and approval integration. |
| Waiver artifact | Turns exception handling into a scoped, expiring, auditable object. | Governance, legal, manager | Needs enforced expiry and follow-up validation. |
| Signed approval artifact | Converts sign-off into a durable governance record. | Release owner, auditor | High-value gap, very sellable once implemented. |
| Incident replay pack | Preserves failed cases and reproduction evidence for RCA. | SRE, support, agent owner | Needs executable replay bundle. |
| Usage ledger artifact | Connects generate/share/view/verify/retain actions to quota and pricing. | Admin, finance, platform | Needed for SaaS and self-host chargeback. |
| Redaction scan artifact | Proves exports were scanned before sharing or retention. | Security, compliance | Needs universal fail-closed firewall. |
| Retention/legal-hold state | Tells auditors whether release evidence is retained or purge-planned. | Compliance, legal | Contract exists, enforcement pending. |
| Self-host storage health | Shows whether DB, object store, export worker, and audit log can support registry workloads. | Enterprise admin | Valuable for regulated pilots. |

## 3. Why This Is More Than A Toy

The current artifact-registry direction is not a toy because it already has the right enterprise nouns:

- stable artifact ids,
- schema versions,
- content hashes,
- byte sizes,
- source snapshot ids,
- lifecycle states,
- redaction status,
- verification status,
- hosted report expiry and revoke fields,
- retention policy,
- audit event ids,
- usage event ids,
- bundle root hash direction,
- chain-of-custody direction,
- SQL and self-host table direction,
- safety invariants that forbid secrets, absolute local paths, raw tokens, raw cookies, and raw signed URLs.

This is the language enterprise buyers expect. The remaining work is to make the language true in the running Product Console.

## 4. Toy Gaps Blocking Enterprise Claim

These are the gaps that still make the artifact registry feel local, mock-like, or incomplete.

| Gap | Current toy state | Enterprise upgrade |
|---|---|---|
| Registry is not yet a first-class console page | The manifest contract defines records, but users do not yet live in a registry workspace. | Add Product Console routes for artifact list, artifact detail, packet detail, and lifecycle timeline. |
| No durable artifact table | Registry fields are documented, but not enforced as durable tenant/project-scoped rows. | Add SQL-backed `artifact_entries` and `artifact_events` or an equivalent Report Center table contract. |
| No object storage lifecycle | Artifacts can be local files or planned exports, but production storage state is not complete. | Add private object-store keys, hash verification, restore checks, and no raw signed URLs in registry rows. |
| No authenticated actor chain | `created_by` and reviewer roles are not enough for enterprise audit. | Bind actions to SSO/GitHub/local self-host users and role grants. |
| No full generated-output seal | Some artifacts are hashed, but PDF, hosted HTML, screenshots, PR comments, and check payloads need full coverage. | Hash every generated output and bind all to one manifest id. |
| Redaction is not universal | CLI path is stronger than all Product Console export surfaces. | Add shared fail-closed redaction firewall before registry publish/share. |
| No artifact publish gate | A generated artifact can be considered useful before redaction/verification is complete. | Only allow `published` or `shared` after required scans pass. |
| No signed approval record in registry | Approval is still more direction than durable artifact identity. | Add signed approval artifact bound to manifest root hash and reviewer identity. |
| Waiver lifecycle is not central | Waivers are policy objects, not fully managed registry artifacts. | Add waiver artifact with expiry, scope, blocked checks, follow-up issue, and validation state. |
| Hosted report access control is incomplete | Expiry/revoke/view audit are documented but need enforcement. | Add hashed share tokens, denied-view events, auth-required modes, and revoke enforcement. |
| No registry search | Enterprise users cannot find evidence by release, PR, run, case, failure class, owner, approver, or retention class. | Add search, filters, saved views, and exportable registry index. |
| No legal hold or purge workflow | Retention is a field, not an operational workflow. | Add retain, legal hold, purge planned, purge blocked, and purge completed states. |
| No self-host backup proof | Self-host value needs recoverability, not just local operation. | Add backup/restore verification artifact and health panel. |
| No packet preset productization | Buyers need one-click packets, not a menu of unrelated files. | Add PR review, executive sign-off, security audit, incident RCA, and customer-support packet presets. |
| No compatibility migration story | Artifact schemas will evolve, but customer archives must remain readable. | Add import/migration compatibility checks and schema deprecation policy. |

## 5. Enterprise Value

The registry can become an enterprise control plane for agent release evidence.

Value by buyer:

| Buyer | Value |
|---|---|
| VP Engineering | Can see whether an agent release has the evidence needed for go/no-go. |
| Platform engineering | Gets CI-ready JSON, GitHub Check, PR comment, manifest, and verifier artifacts. |
| Security | Gets redaction status, hosted report controls, access events, and no-secret guarantees. |
| Compliance | Gets lifecycle state, retention policy, legal hold direction, approvals, and custody trail. |
| Internal audit | Gets a registry of evidence packets with hashes, timestamps, and verification status. |
| SRE / incident response | Gets replay packs tied to risky cases and release decisions. |
| Customer success | Gets customer-safe packets without exposing raw traces or local fixtures. |
| Procurement | Gets a credible self-host and governance story for sensitive environments. |

The registry also creates a pricing surface:

- artifact generation,
- hosted report publishing,
- share-link views,
- replay pack generation,
- verifier runs,
- retained bundle storage,
- legal hold,
- long-term audit retention,
- enterprise export packets,
- self-host support.

That makes it a better monetization unit than raw dashboard views.

## 6. Audit Value

The audit value is simple: the Product Console should make evidence review repeatable and provable.

Minimum audit chain:

1. Source evidence is imported or selected.
2. A source snapshot id is created.
3. Artifacts are generated from that snapshot.
4. Each artifact is redaction-scanned.
5. Each generated artifact is hashed.
6. The artifact registry records lifecycle events.
7. The generated artifact manifest binds outputs together.
8. The audit bundle index binds source, output, governance, and custody records.
9. Waivers and approvals reference the same bundle or manifest root.
10. A verifier can later prove whether the evidence changed.

The registry must never imply that a file is audit-ready merely because it exists. Audit-ready means source-bound, scanned, hashed, permissioned, lifecycle-tracked, retained, and verifiable.

## 7. Self-Host Value

The registry is especially strong for self-host buyers because regulated customers often cannot send raw traces, media, prompts, support transcripts, or incident evidence to a SaaS system.

Self-host registry value:

- keeps artifacts under the customer's tenant and project boundary,
- supports private DB and object storage,
- avoids durable raw signed URLs,
- stores tokens and storage keys only as hashes or private references,
- lets admins verify DB/object-store/export-worker/audit-log health,
- gives compliance teams local retention and legal hold control,
- supports air-gapped or restricted-network review flows later,
- lets customer auditors verify release evidence without exposing live systems.

Self-host caution:

The current repo direction is strong enough for self-host architecture and design-partner discovery, but not yet for claiming production self-host compliance. Production self-host needs migrations, installer, RBAC/SSO, backup/restore, object-store probes, retention jobs, audit-log immutability, and operational runbooks.

## 8. Concrete Next Growth Points

These are the highest-value growth points for the next A3 Artifact Registry round.

| ID | Growth point | Why it matters | Lane |
|---|---|---|---|
| AR-01 | Add Product Console artifact registry route. | Makes the registry a visible paid feature, not only a manifest contract. | UI |
| AR-02 | Add artifact detail route. | Lets users inspect schema, hash, source snapshot, lifecycle, safety, events, and retention. | UI |
| AR-03 | Add packet detail route grouped by manifest id. | Shows all artifacts for one release-evidence packet in one place. | UI |
| AR-04 | Add registry empty, loading, error, and redaction-blocked states. | Makes the workflow credible during real operations. | UI |
| AR-05 | Add artifact lifecycle timeline. | Shows generate, scan, publish, share, view, revoke, verify, approve, retain, and purge events. | UI/audit |
| AR-06 | Add `artifact_entries` persistence contract. | Gives every artifact durable tenant/project identity. | DB |
| AR-07 | Add `artifact_events` append-only contract. | Turns lifecycle changes into audit evidence. | DB/audit |
| AR-08 | Keep Report Center manifest id as the registry join key. | Prevents JSON, Markdown, PDF, hosted, PR, check, bundle, and approval artifacts from drifting apart. | Data model |
| AR-09 | Bind every registry artifact to `source_snapshot_id`. | Proves all formats came from the same release evidence. | Data model |
| AR-10 | Hash JSON report artifacts. | Makes machine-readable evidence tamper-evident. | Integrity |
| AR-11 | Hash Markdown report artifacts. | Proves reviewer-readable text did not change after review. | Integrity |
| AR-12 | Hash CSV export artifacts after formula hardening. | Makes triage sheets safer and auditable. | Security |
| AR-13 | Hash deterministic PDF or captured print artifacts. | Makes executive sign-off packets verifiable. | Integrity |
| AR-14 | Hash hosted report HTML snapshots. | Proves shared pages match reviewed evidence. | Hosted report |
| AR-15 | Hash PR comment Markdown artifacts. | Shows exactly what PR reviewers saw. | GitHub |
| AR-16 | Hash GitHub Check payload artifacts. | Makes CI gate status traceable to the evidence packet. | GitHub |
| AR-17 | Add screenshot/visual QA artifact entries. | Captures what the Product Console displayed during approval. | QA/evidence |
| AR-18 | Add fail-closed redaction status per artifact. | Prevents unsafe artifacts from being shared or retained as customer packets. | Security |
| AR-19 | Add redaction findings log hash. | Proves the scan result was part of the evidence packet. | Security/audit |
| AR-20 | Add universal export-surface registry. | Stops new export formats from bypassing the firewall. | Security |
| AR-21 | Add signed approval artifact. | Converts human sign-off into durable governance evidence. | Review |
| AR-22 | Bind approvals to bundle root hash. | Proves exactly what evidence was approved. | Review/audit |
| AR-23 | Add waiver artifact entry. | Makes exceptions visible, scoped, expiring, and auditable. | Governance |
| AR-24 | Enforce waiver expiry in registry status. | Prevents stale exceptions from silently unblocking future releases. | Governance |
| AR-25 | Add follow-up issue field and validation for waivers. | Creates accountability for accepted risk. | Governance |
| AR-26 | Add separation-of-duties status. | Prevents release authors from self-approving high-risk packets. | Compliance |
| AR-27 | Add reviewer board artifact linkage. | Shows which lanes must inspect which artifacts. | Workflow |
| AR-28 | Add registry search by run, release, PR, case, failure class, status, owner, approver, and retention. | Makes enterprise-scale evidence findable. | Product |
| AR-29 | Add saved registry filters for auditor, release owner, security, and support views. | Gives each persona a focused workflow. | Product |
| AR-30 | Add packet presets for PR review, executive sign-off, security audit, incident RCA, and customer support. | Turns many artifacts into sellable workflows. | Product |
| AR-31 | Add hosted report share-token hash records. | Avoids storing raw share tokens while preserving revoke and view audit. | Hosted report |
| AR-32 | Add denied-view audit events. | Records expired, revoked, not-found, auth-required, and redaction-blocked access attempts. | Hosted report |
| AR-33 | Add registry usage ledger events. | Supports quota, pricing, chargeback, and abuse analysis. | Usage |
| AR-34 | Add retained byte counts per packet. | Makes long-term evidence retention measurable and billable. | Usage/storage |
| AR-35 | Add legal hold state. | Makes regulated retention workflows credible. | Compliance |
| AR-36 | Add purge-planned and purge-completed states. | Gives data lifecycle teams a real evidence disposal story. | Compliance |
| AR-37 | Add object storage health artifact. | Helps self-host admins prove export storage is ready. | Self-host |
| AR-38 | Add backup verification artifact. | Proves registry packets can survive disaster recovery. | Self-host |
| AR-39 | Add restore verification artifact. | Proves archived evidence can be recovered and verified. | Self-host |
| AR-40 | Add schema compatibility check for older artifact packets. | Protects customer archives as A3 evolves. | Migration |
| AR-41 | Add registry API schema docs. | Lets customers integrate artifact records with internal governance systems. | API |
| AR-42 | Add webhook events for generated, published, shared, revoked, approved, verified, retained, and purged. | Lets enterprise systems react to evidence lifecycle changes. | API |
| AR-43 | Add GitHub branch-protection readiness state. | Shows whether registry-backed checks can actually block merges. | GitHub |
| AR-44 | Add registry Playwright screenshots. | Proves the registry workflow visually for sales and QA. | QA |
| AR-45 | Add registry fixture scanner in CI. | Prevents committed registry evidence from leaking secrets or local paths. | QA/security |

## 9. Fastest Sellable Round

The next round should not try to build every enterprise feature at once. The fastest money-grade sequence is:

1. Add the Product Console artifact registry view and artifact detail route.
2. Use the Report Center manifest id as the central packet id.
3. Register JSON, Markdown, CSV, print/PDF, hosted report, PR comment, GitHub Check, generated artifact manifest, audit bundle index, reviewer board, replay pack, and usage ledger artifacts.
4. Show source snapshot id, schema, format, lifecycle state, redaction state, hash state, retention class, and audit event count for each artifact.
5. Add fail-closed publish/share status based on redaction state.
6. Bind generated artifacts to hashes where already available, and mark missing hashes as `pending` or `not_implemented`.
7. Add one registry screenshot artifact as visual proof.
8. Add docs and tests in a later implementation round to prove no secret values, raw signed URLs, raw cookies, raw tokens, or local absolute paths appear.

This sequence would let the team demo a coherent enterprise workflow without pretending the full production stack exists.

## 10. Final Auditor Position

The Product Console artifact registry is worth prioritizing because it converts A3 from "a report generator" into "a release-evidence governance product."

The sellable wedge is not that A3 can download files. The sellable wedge is that A3 can manage evidence artifacts through lifecycle, safety, review, sharing, verification, and retention.

The honest commercial claim for the next round:

> "A3 Product Console Artifact Registry gives every agent-release evidence artifact a durable identity, source binding, safety status, lifecycle state, and audit path, with a roadmap to signed approvals, self-host retention, and bundle verification."

Do not claim full enterprise compliance yet. Claim a credible controlled evidence workflow, then prove it with a registry UI, manifest linkage, hashes, fail-closed redaction status, and a self-host persistence path.
