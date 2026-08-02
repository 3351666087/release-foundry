# A3 Growth Auditor - Product Console Export Artifacts - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Product Console Export Auditor.

Focus: whether the A3 Product Console is becoming the place where JSON, Markdown, CSV, print/PDF, hosted report, manifest, and audit artifacts enter a sellable customer workflow.

This is a bounded docs-only pass.

Safety boundary followed:

- Read local repo documentation only.
- Did not read `.env.local`, API keys, cookies, tokens, signed URLs, or account data.
- Did not call the live ReleaseFoundry API.
- Did not call the live GitHub API.
- Did not edit runtime code or tests.
- Created only `docs/a3/p3_growth_auditor_product_console_export_2026_07_07.md`.

Evidence reviewed:

- `docs/a3/a3_dashboard_polish.md`
- `docs/a3/p3_growth_auditor_2026_07_07.md`
- `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`
- `docs/a3/p3_growth_auditor_onboarding_audit_project_console_2026_07_07.md`
- `docs/a3/p3_report_center_manifest_growth_2026_07_07.md`
- `docs/a3/p3_report_center_control_plane_growth_2026_07_07.md`
- `docs/a3/p3_saas_admin_cloud_parity_growth_2026_07_07.md`
- `docs/a3/acceptance_checklist.md`

## Executive Verdict

A3 is now close to having a credible Product Console story for entering and managing release-evidence artifacts. The strongest current story is not "dashboard with charts." It is "one product surface where an agent team can generate, inspect, share, print, and later verify the evidence packet behind a release decision."

That matters commercially because enterprise buyers do not only want a pass rate. They want:

- machine-readable JSON for automation,
- Markdown for PRs and reviewer handoffs,
- CSV for triage and spreadsheet review,
- print/PDF for executive sign-off,
- hosted reports for controlled sharing,
- manifests and hashes for audit integrity,
- lifecycle and audit events for compliance review.

The current A3 Product Console is more than a toy because it already has documented export surfaces, Report Center direction, hosted report lifecycle concepts, redaction guardrails, audit log summaries, and product-console workflow state. It is still not enterprise-grade because artifact entry is not yet a durable, tenant-scoped, permissioned, signed, and fully verified workflow.

Commercial maturity score for this narrow Product Console export track:

| Dimension | Score | Auditor read |
|---|---:|---|
| Export narrative | 8/10 | JSON, CSV, Markdown, and print/PDF are clearly positioned as evidence outputs. |
| Product Console fit | 6.5/10 | Product Console can frame onboarding, project, audit, and readiness state, but artifact entry is still not the central workflow. |
| Report Center maturity | 6/10 | Report inventory, lifecycle, hosted reports, manifest readiness, and redaction status are defined, but still mostly local/API-backed. |
| Audit integrity | 5.5/10 | Hashes, manifests, bundle direction, and redaction rules exist; signed review and complete generated-artifact verification remain incomplete. |
| Enterprise readiness | 4.5/10 | RBAC, SQL, retention, share-token, approval, and self-host contracts exist as direction, not full enforcement. |
| Paid pilot readiness | 6.5/10 | Strong enough for local/self-host design partner demos if positioned honestly as controlled evidence workflow, not full SaaS governance. |

## 1. What "Artifact Entry" Should Mean

The Product Console should become the front door for every customer-facing A3 artifact. "Entry" should not mean only a download button. It should mean each artifact is created, cataloged, scanned, linked to source evidence, assigned a lifecycle state, and made available to the correct human or automation workflow.

Target artifact entry lifecycle:

| Step | Product Console responsibility | Buyer value |
|---|---|---|
| Source selection | Select A1 run, A2 grade set, A3 report snapshot, PR, release, or project. | Prevents reports from floating without provenance. |
| Artifact generation | Create JSON, Markdown, CSV, print/PDF, hosted report, PR comment, check payload, manifest, and bundle records. | Gives each audience the format it needs. |
| Redaction scan | Block secrets, local absolute paths, raw tokens, raw cookies, raw signed URLs, and CSV formula injection. | Makes exports safer for customer review. |
| Catalog entry | Register artifact id, format, schema, source snapshot, hash, size, status, retention, and audit events. | Turns one-off files into managed evidence. |
| Human workflow | Route Markdown, print/PDF, reviewer board, waiver, and approval records to reviewers. | Moves from dashboard viewing to sign-off workflow. |
| Automation workflow | Route JSON, GitHub Check, PR comment, manifest, and verification records to CI/API consumers. | Makes release gates operational. |
| Sharing workflow | Publish hosted report links with expiry, revoke, denied-view audit, and view counts. | Lets teams share evidence without exposing raw fixtures. |
| Verification workflow | Verify hashes, bundle root, redaction status, custody events, and signed approvals. | Gives audit teams defensible evidence. |

## 2. Current Sellable Capabilities

These capabilities can already support a paid pilot if the scope is local, redacted, and evidence-review focused.

| Capability | Why it can sell | Current buyer promise |
|---|---|---|
| JSON report export | Machine-readable report fields can feed CI, APIs, manifests, and future customer systems. | "Your release evidence can be automated and verified." |
| Markdown report export | Human-readable report output fits PR comments, review notes, and handoff docs. | "Reviewers can understand the release evidence without reading raw JSON." |
| CSV triage export | Failed cases and triage lists can move into spreadsheet workflows. | "Ops and QA teams can sort and assign failures quickly." |
| Print/PDF report preview | Browser-printable executive report supports review meetings and sign-off packets. | "Managers get a clean packet for release review." |
| Report Center | Export actions are moving toward report inventory and lifecycle control. | "Reports are managed assets, not throwaway downloads." |
| Hosted report lifecycle | Shareable hosted reports have documented expiry, revocation, view audit, and redaction needs. | "Evidence can be shared safely and revoked later." |
| Report Center manifest | Artifact ids, formats, schemas, hashes, lifecycle states, retention, and safety fields are defined. | "Every exported artifact can be cataloged and audited." |
| Product Console panel | Onboarding, project status, audit state, and commercial readiness are visible in one product workflow. | "A buyer sees a product, not a pile of fixtures." |
| Audit log summary | Import, report, share, and report-center events can become redacted audit signals. | "Security and compliance teams can see what happened." |
| Release Gate linkage | JSON/Markdown/print/report outputs can support approve, review, or block decisions. | "Exported evidence maps to release control." |
| PR Gate direction | Markdown and GitHub-shaped artifacts can enter engineering workflows. | "Agent eval evidence can appear where code review happens." |
| Redaction firewall direction | Export safety is a first-class requirement, not a last-minute cleanup. | "Customer packets should not leak secrets." |
| Self-host-compatible shape | Local docs, CLI, dashboard, and manifest contracts can become self-host artifacts. | "Regulated customers can pilot without sending sensitive traces to SaaS." |
| Usage and quota visibility | Usage evidence can become report/export/view/replay metering. | "Artifacts can become billable or governable events." |
| Commercial readiness scoring | Product Console can say whether evidence is demo-ready or blocked. | "Sales and customer success get an honest readiness signal." |

## 3. Toy Gaps And Upgrade Requirements

These gaps are where the current artifact workflow still feels local, mock-like, or incomplete.

| Gap | Current toy state | Required enterprise upgrade |
|---|---|---|
| Artifact entry is not the primary console workflow | Export buttons and report panels exist, but artifact creation is not modeled as a full workflow. | Add a Product Console artifact workspace with create, scan, catalog, share, verify, revoke, and retain states. |
| Generated artifacts are not all sealed | Existing docs emphasize hashing, but full PDF, screenshot, hosted HTML, PR comment, and check payload verification is still a growth point. | Hash every generated artifact and bind it to a source snapshot and bundle root. |
| No durable artifact registry | Report Center direction exists, but persistence is still local/API-contract oriented. | Store artifact records in SQL with tenant, project, release, snapshot, lifecycle, and retention scope. |
| No real authenticated actor | Reviewer and audit records are role-shaped, not identity-enforced. | Bind create/share/revoke/approve actions to SSO, GitHub actor, or local self-host identity. |
| No signed approvals | Print/PDF and Markdown can look review-ready, but approval is not yet a durable signed record. | Add `a3.approval.v1` bound to artifact hashes, signer, timestamp, role, policy, and decision. |
| Waivers are not fully operational | Waiver policy exists, but expiry, follow-up, and scope enforcement are not central to artifact entry. | Add waiver artifact records with expiry validation and bundle inclusion. |
| Hosted report access is not enterprise access control | Lifecycle states are documented, but production-grade token, auth, denied-view audit, and retention are not complete. | Add hashed share tokens, auth-required modes, denied-view audit, and revocation enforcement. |
| Print/PDF is browser-dependent | Print preview is useful, but generated PDF bytes and hashable output are not guaranteed. | Add deterministic PDF generation or captured print artifact hashing. |
| Markdown has no reviewer-state round trip | Markdown can be exported, but reviewer comments, approvals, and follow-ups do not flow back into Product Console. | Add reviewer packet import or API mutation records. |
| JSON lacks customer-facing schema governance | JSON reports exist, but external versioning and compatibility policy need to be explicit. | Publish schema contracts and migration rules for report consumers. |
| CSV remains spreadsheet-adjacent | CSV is useful, but enterprise spreadsheet safety needs fail-closed testing and artifact metadata. | Add formula injection scan result, content hash, and usage event. |
| Report Center is not yet the single source of truth | It summarizes reports, but PR Gate, audit bundle, hosted report, and Product Console are not fully unified around one manifest id. | Make Report Center manifest id the join key across exports, PR checks, approvals, usage, and audit bundle. |
| No full artifact search | Customers cannot search reports by run, case, failure class, source, status, approver, or retention class. | Add report/artifact search and filters. |
| No retention/legal hold workflow | Retention is documented as a field, not enforced policy. | Add retain, purge planned, legal hold, and backup/restore evidence. |
| No customer-safe packet preset | A3 has many artifacts, but not a one-click "external customer packet" shape. | Add packet presets for PR review, executive sign-off, security audit, incident replay, and customer support RCA. |

## 4. Enterprise And Audit Value

The Product Console export workflow can become a high-value enterprise surface because it joins three worlds that are usually scattered:

1. Evaluation truth: A1 traces, A2 judge results, A3 failure clusters, tool-call diffs, media readiness, and release gate decisions.
2. Human review: Markdown, print/PDF, reviewer board, waiver, approval, incident summary, and executive sign-off.
3. Machine governance: JSON, manifests, hashes, GitHub Check payloads, PR comments, usage ledger, SQL audit events, and verifier results.

Enterprise value:

- Gives engineering managers a project-level release-evidence console.
- Gives platform teams an API and manifest direction for CI integration.
- Gives security teams redaction, hosted report, and audit-log evidence.
- Gives compliance teams artifact lifecycle, retention, approval, and custody hooks.
- Gives procurement a credible self-host and governance story.
- Gives customer success a way to package evidence without exposing raw fixtures.

Audit value:

- JSON artifacts can be used as canonical machine evidence.
- Markdown artifacts can carry reviewer-readable release context.
- CSV artifacts can support triage and operational assignment.
- Print/PDF artifacts can become executive sign-off packets.
- Hosted reports can carry controlled sharing, expiry, revoke, and view audit.
- Manifests can bind artifact identity, schema, hash, size, redaction, lifecycle, and retention.
- Bundle verification can prove whether an exported packet changed after review.

Most important audit principle:

The Product Console should never treat a downloaded file as "done." A sellable enterprise artifact is done only after it has source provenance, redaction status, lifecycle state, content hash, retention class, audit events, and, where required, reviewer approval.

## 5. Next Growth Points

These are the highest-value growth points for making Product Console artifact entry commercial and audit-grade.

| ID | Growth point | Why it matters | Suggested lane |
|---|---|---|---|
| PCE-01 | Add Product Console artifact registry view. | Makes JSON, Markdown, CSV, print/PDF, hosted reports, manifests, and bundles visible in one surface. | Product Console |
| PCE-02 | Add `artifact_entry` lifecycle model. | Gives every artifact states such as planned, generated, scanned, shared, revoked, verified, retained, and purged. | API/model |
| PCE-03 | Use Report Center manifest id as the central join key. | Links export buttons, hosted reports, PR Gate, audit bundle, usage, and approvals. | Report Center |
| PCE-04 | Hash every JSON report generated from Product Console. | Makes machine-readable evidence tamper-evident. | Audit |
| PCE-05 | Hash every Markdown report generated from Product Console. | Proves reviewer-facing text matched the reviewed release. | Audit |
| PCE-06 | Hash CSV exports after formula-injection hardening. | Makes triage spreadsheets safer and auditable. | Security |
| PCE-07 | Generate or capture deterministic print/PDF artifact hashes. | Turns executive packets into signable evidence. | Report export |
| PCE-08 | Hash hosted report HTML snapshots. | Proves the shared page matched the reviewed report. | Hosted reports |
| PCE-09 | Add screenshot and visual QA artifact entries. | Lets reviewers verify what the console showed at approval time. | Evidence |
| PCE-10 | Add redaction scan result per artifact entry. | Keeps safety visible at the artifact level. | Security |
| PCE-11 | Add fail-closed publish for redaction findings. | Prevents unsafe hosted reports and downloads. | Security |
| PCE-12 | Add artifact packet presets. | Lets teams generate PR review, executive sign-off, security audit, incident replay, and customer packet bundles. | Product |
| PCE-13 | Add artifact detail route. | Lets users inspect schema, hash, source snapshot, lifecycle, audit events, and retention state. | UI/API |
| PCE-14 | Add artifact search and filters. | Helps enterprise teams find evidence by run, case, release, status, approver, or failure class. | UI/API |
| PCE-15 | Add tenant and project scope enforcement for artifacts. | Prevents cross-customer report leaks. | Security/API |
| PCE-16 | Add SQL tables for artifact entries and artifact events. | Makes Report Center durable and self-host ready. | DB |
| PCE-17 | Add append-only artifact audit events. | Records generate, scan, download, share, view, revoke, verify, approve, retain, and purge actions. | Audit |
| PCE-18 | Add signed approval artifact bound to manifest root hash. | Converts print/PDF and Markdown review into durable governance. | Review |
| PCE-19 | Add waiver artifact with expiry and follow-up issue validation. | Prevents hidden permanent policy bypasses. | Review |
| PCE-20 | Add separation-of-duties checks for artifact approval. | Stops release authors from self-approving high-risk evidence. | Compliance |
| PCE-21 | Add reviewer board linkage to artifact entries. | Shows which evidence each lane must review before sign-off. | Workflow |
| PCE-22 | Add PR comment Markdown artifact round trip. | Lets Product Console show the exact PR-facing summary and update status. | GitHub |
| PCE-23 | Add GitHub Check payload artifact entry. | Makes CI status traceable to the report and manifest. | GitHub |
| PCE-24 | Add branch-protection readiness state. | Shows whether the artifact-backed gate can actually block merge. | GitHub |
| PCE-25 | Add hosted report share token hashing. | Avoids storing raw share tokens while supporting revoke/view audit. | Hosted reports |
| PCE-26 | Add denied-view audit events. | Records expired, revoked, blocked, and not-found access attempts. | Hosted reports |
| PCE-27 | Add retention and legal-hold controls. | Makes artifact lifecycle credible for regulated customers. | Compliance |
| PCE-28 | Add bundle verification action from Product Console. | Lets a reviewer verify exported evidence without using a separate CLI first. | Audit |
| PCE-29 | Add usage ledger events for every artifact action. | Supports pricing, quota, chargeback, and abuse controls. | Usage |
| PCE-30 | Add cost forecast per artifact packet. | Makes report/replay/export cost visible before teams share large bundles. | Usage |
| PCE-31 | Add API schema docs for every artifact format. | Makes external consumers trust JSON, Markdown, CSV, PDF, hosted, and bundle contracts. | API |
| PCE-32 | Add webhook events for artifact generated, shared, revoked, approved, and verified. | Lets enterprise systems react to report lifecycle changes. | API |
| PCE-33 | Add customer-safe external packet view. | Provides a polished evidence packet that hides internal-only fields. | Product |
| PCE-34 | Add onboarding path for "upload JSON evidence." | Makes Product Console the first touch point for imported A1/A2/A3 artifacts. | Onboarding |
| PCE-35 | Add onboarding path for "connect GitHub Action." | Converts artifact entry into release workflow setup. | Onboarding |
| PCE-36 | Add onboarding path for "generate first print report." | Gets executives and non-technical reviewers to value quickly. | Onboarding |
| PCE-37 | Add Playwright evidence for artifact registry, print preview, hosted report, and revoke flow. | Proves the workflow visually, not just by contract. | QA |
| PCE-38 | Add self-host storage health next to artifact registry. | Shows whether DB/object storage/retention dependencies are ready. | Self-host |
| PCE-39 | Add backup and restore verification for artifact packets. | Makes self-host compliance more credible. | Self-host |
| PCE-40 | Add import compatibility checks for older report schemas. | Prevents customer archives from breaking when schemas evolve. | Migration |

## 6. Suggested Parallel Execution Plan

These lanes can move in parallel without waiting for one giant Product Console rewrite.

| Lane | First deliverable | Parallel with |
|---|---|---|
| Artifact registry | Product Console artifact list plus detail route over existing Report Center data. | Hashing, SQL contract, approvals |
| Generated artifact integrity | Hash JSON, Markdown, CSV, print/PDF, hosted HTML, PR comment, and check payload outputs. | UI registry, redaction, packet presets |
| Redaction and publish safety | Per-artifact scan result plus fail-closed share/download gate. | Hashing, hosted report lifecycle |
| Review and approval | Signed approval and waiver records bound to manifest root hash. | SQL, artifact registry, PR Gate |
| Hosted report lifecycle | Hashed share tokens, denied-view audit, revoke/expire enforcement. | Redaction, usage ledger |
| SQL/self-host | Artifact tables, event tables, retention fields, backup/restore contract. | UI and API schema work |
| PR/GitHub | PR comment and GitHub Check artifacts linked to manifest id. | Review workflow and branch-protection readiness |
| Usage/billing | Usage ledger events for generate, download, share, view, revoke, verify, and retain. | Artifact registry and hosted reports |
| QA/evidence | Playwright screenshots for registry, print preview, hosted report, revoke, and mobile. | All UI lanes |

Fastest money-grade sequence:

1. Add an artifact registry view to Product Console.
2. Bind JSON, Markdown, CSV, print/PDF, hosted report, PR comment, and GitHub Check outputs to one manifest id.
3. Hash the generated artifacts and show redaction state beside each one.
4. Add signed approval and waiver records that reference the manifest root hash.
5. Add hosted report share-token lifecycle and denied-view audit.
6. Add SQL persistence and self-host retention once the artifact model is stable.

## Final Auditor Call

The Product Console should become A3's evidence operating system.

The current repo already has the right ingredients: export actions, print-ready reports, Report Center direction, hosted report lifecycle concepts, manifest contracts, audit bundle direction, Product Console workflow state, and redaction safety. The missing commercial move is to make artifact entry explicit and durable.

Best next product promise:

> "A3 Product Console turns agent evaluation output into a managed release-evidence packet: JSON for automation, Markdown for reviewers, print/PDF for executives, hosted reports for sharing, and manifests for audit verification."

That is a sellable promise. It is not fully enterprise-ready until artifact entries are persisted, hashed, redacted fail-closed, tenant-scoped, access-controlled, retained, verified, and bound to signed approvals.

What this audit did not do:

- Did not modify dashboard code.
- Did not modify report builder code.
- Did not modify API/server code.
- Did not modify tests.
- Did not modify fixtures.
- Did not read `.env.local`.
- Did not call live ReleaseFoundry, GitHub, billing, browser, or cloud APIs.
