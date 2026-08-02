# A3 Growth-Auditor / Money-Grade Release Evidence Display - 2026-07-08

Role: Growth-Auditor / Money-Grade auditor.

Scope: documentation artifact only. This artifact evaluates the business value of showing GitHub publish evidence, audit bundle verification, and signed audit archive verification inside the A3 Dashboard, Report Center, and Release War Room.

Strict strategy anchor: this round must follow `docs/strategy/large-saas-a1-a2-a3-full-plan.md` exactly. A3's job is not to become another local fixture generator. A3 must become the customer-facing product, workflow, and control tower for a multi-tenant hosted SaaS:

- Dashboard: show the release decision and evidence integrity where release owners work.
- Report Center: manage evidence packets, lifecycle, redaction, sharing, verifier state, usage, and retention.
- War Room: join gate, PR status, reviewer state, replay readiness, archive verification, and next action into one operational release decision.

Boundary followed:

- Add only this file under `docs/a3`.
- Do not modify code, fixtures, tests, acceptance checklists, worklogs, or strategy docs.
- Do not read or print `.env.local`.
- Do not write secrets, tokens, cookies, Authorization headers, API keys, raw signed URLs, private emails, or live credentials.
- Do not call live ReleaseFoundry, GitHub, billing, database, hosted auth, or external APIs.

## Executive Verdict

A3 already has valuable evidence primitives:

- GitHub Check publish evidence and PR comment publish evidence can be represented as sanitized receipts.
- Audit bundle indexes and generated artifact manifests can bind report/gate/review/GitHub artifacts with hashes.
- Audit bundle verification can prove that indexed evidence still matches.
- Signed audit archive verification is the missing commercial display layer that would turn bundle integrity into a buyer-readable enterprise control.

The next money-grade step is not "create more evidence." The next step is:

> Show release evidence integrity as a first-class product state across A3 Dashboard, Report Center, and War Room.

The buyer should be able to answer in one view:

```text
Did this release publish to GitHub?
Which Check Run and PR comment represented the decision?
Which hosted report snapshot was shared?
Which audit bundle root hash covers the packet?
Did bundle verification pass?
Did signed archive verification pass?
Who reviewed or waived the release?
What must happen next before merge or production deploy?
```

Money-grade score for this display round:

| Dimension | Score | Auditor note |
|---|---:|---|
| Buyer clarity | 8.5/10 | "Every release packet shows GitHub publish, bundle verification, and signed archive verification" is easy to understand. |
| Paid pilot value | 8/10 | This is directly demoable to platform, security, and release-management buyers. |
| A3 strategy fit | 9/10 | It advances the SaaS control tower called for in the large SaaS plan. |
| Production readiness | 5.5/10 | Evidence generation exists, but live enforcement, identity, immutable archive, and retention still need hardening. |
| Enterprise audit story | 7.5/10 | Hashes, verifier status, archive status, and report lifecycle become product-visible instead of hidden CLI output. |
| Self-host story | 7/10 | Offline verification plus archive display is a strong self-host wedge if storage/backup/upgrade paths are added. |
| Toy risk | 6/10 risk | A pretty panel without branch-protection proof, identity binding, and immutable archive semantics would still feel prototype-like. |

## Strategy Compliance

`docs/strategy/large-saas-a1-a2-a3-full-plan.md` says A3 must become the real user workflow and control tower. This evidence display round should therefore obey these strategy rules:

| Strategy requirement | How this round should comply |
|---|---|
| A3 owns product control tower | Dashboard, Report Center, and War Room must show evidence integrity, not bury it in CLI output. |
| A3 owns release workflow | GitHub publish evidence must be attached to the release decision and PR Gate state. |
| A3 owns reports/evidence sharing | Report Center must show hosted report lifecycle, manifest readiness, bundle verification, signed archive verification, and share status. |
| A3 owns reviewer/approval workflow | Verification state must influence next action: ship, block, verify, re-run, approve, waive, archive, or escalate. |
| A3 supports enterprise/self-host/audit | Archive status, verifier command, retention status, redaction state, and offline verification must be buyer-visible. |
| A3 avoids fixture-only demo | Each display field must map to a real contract: receipt id, artifact hash, bundle root hash, verifier result, archive signature status, report snapshot id. |

Auditor instruction: do not treat this as UI polish. Treat it as productizing the evidence chain required by the large SaaS plan.

## Product Thesis

A3 can sell a higher-value release-governance product when the evidence chain becomes visible:

```text
Run evidence -> Release Gate -> GitHub Check/PR Comment -> Hosted Report -> Audit Bundle -> Signed Archive -> Verification Result -> War Room decision
```

Without display, the evidence chain is a technical artifact. With display, it becomes a paid control:

- engineers trust the PR status;
- release managers know whether merge is blocked;
- auditors know whether the packet can be re-verified later;
- security reviewers know whether redaction and archive integrity passed;
- enterprise admins know whether the packet can be retained in hosted or self-host storage.

The business value is that A3 moves from "we generated a report" to:

> "We can prove which release evidence was published, sealed, verified, archived, shared, reviewed, and retained."

## Display Surfaces

### A3 Dashboard

The Dashboard should show evidence integrity as release health, not as an advanced export detail.

Minimum buyer-visible fields:

- GitHub Check publish status: dry-run, live, skipped, failed, or missing.
- PR comment publish status: dry-run, live, skipped, failed, or missing.
- Required-check evidence: configured, planned, missing, failed readback, or admin action required.
- Hosted report snapshot id and share status.
- Audit bundle root hash and verification status.
- Signed audit archive status: unsigned, signed, verified, failed, expired key, unknown key, or missing archive.
- Redaction status: passed, warnings, blocked, or not scanned.
- Reviewer state: no review, pending, waiver requested, approved, rejected, expired, or separation-of-duties failed.
- Next action: publish check, verify bundle, verify archive, request approval, replay failures, block merge, or ship.

Dashboard commercial promise:

> "A release owner can tell in 10 seconds whether a release is safe to merge and whether its evidence packet will survive audit."

### Report Center

Report Center should become the paid evidence inventory, not just a list of hosted reports.

Minimum buyer-visible fields:

- report id, run id, project/repo/PR/head SHA context;
- hosted snapshot id, share token lifecycle, expiry, revocation, denied-view audit;
- generated artifact manifest id and completeness score;
- GitHub publish receipts linked by artifact id and hash;
- audit bundle id, root hash, artifact count, byte count, and verification receipt;
- signed archive id, archive hash, signature status, verifier status, signer identity status;
- redaction scan status and last scan time;
- retention/legal-hold status;
- self-host storage target: local, CI artifact, object storage, immutable archive, or missing;
- usage meters for hosted views, verifier runs, archive bytes, retained days, PR publishes, and replay packs.

Report Center commercial promise:

> "A platform team can manage every release evidence packet like a governed asset: shared, verified, retained, revoked, or archived."

### Release War Room

The War Room should join release risk and evidence integrity into one decision object.

Minimum buyer-visible fields:

- current release state: shipping, blocked, warning, evidence_missing, verification_failed, archive_failed, approval_pending, replay_required, or exception_approved;
- Release Gate decision, risk score, failed checks, policy version, and top-risk cases;
- GitHub Check/PR Comment status and required-check enforcement status;
- audit bundle verification result and missing/tampered artifact list;
- signed archive verification result and signature/key status;
- waiver/approval timeline and identity-binding status;
- replay readiness and run-to-run regression delta;
- redaction fail-closed state;
- self-host/retention state;
- final next action and accountable owner.

War Room commercial promise:

> "When a release is risky or blocked, A3 gives every reviewer one room to decide, verify, approve, waive, replay, archive, or stop."

## 新增可卖能力 / New Sellable Capabilities

| Capability | Buyer-visible promise | Why it can be sold |
|---|---|---|
| Evidence Integrity Dashboard | Dashboard shows GitHub publish, bundle verification, and signed archive verification in the release summary. | Turns invisible audit plumbing into a release-control product. |
| Report Center Evidence Inventory | Every hosted report becomes an evidence packet with lifecycle, manifest, bundle, archive, verifier, redaction, and usage state. | Platform/security teams need governed inventory, not loose downloads. |
| Release War Room Verification State | War Room blocks or escalates releases when bundle/archive verification fails. | Makes evidence integrity part of merge/deploy governance. |
| GitHub Publish Evidence Display | Check Run receipt, PR comment receipt, required-check plan/readback, publish mode, and sanitized errors are visible. | Buyers trust PR integration only when they can see what actually happened. |
| Audit Bundle Verification Display | Bundle root hash, verifier result, artifact counts, missing artifacts, and custody chain status are visible. | Compliance buyers pay for proof that evidence was not tampered with. |
| Signed Audit Archive Verification Display | Archive hash, signature status, signer binding, key status, and verification receipt are visible. | Moves A3 toward regulated release evidence and legal retention. |
| Evidence Completeness Score | Report Center and War Room show required/optional artifacts, stale files, missing receipts, and unverified archive status. | Makes audit readiness simple enough for managers and auditors. |
| Fail-Closed Evidence Publishing | External share, PR publish, or archive promotion can be blocked when redaction or verification fails. | Enterprise buyers value controls that prevent unsafe evidence leakage. |
| Self-Host Offline Verification Panel | Self-host customers can see which packets can be verified without cloud services. | Opens regulated buyers who require private deployment. |
| Usage-To-Value Metering | Verification runs, archives, hosted views, retained bytes, PR publishes, and report packets are metered. | Creates a path to quota, chargeback, and expansion pricing. |
| Audit-Ready Customer Packet | A customer-facing packet can include report, GitHub evidence, verifier receipt, archive signature, and redaction summary. | Useful for security reviews, customer audits, and procurement proof. |
| Evidence Health API | Dashboard, Report Center, War Room, PR comments, and webhooks can all consume the same evidence-health object. | Makes A3 embeddable in enterprise release platforms. |

## 玩具风险 / Toy Risk

These are the ways this feature can look like a prototype if the display layer gets ahead of the production controls.

| Risk | Why it feels toy-like | Money-grade upgrade |
|---|---|---|
| Display says "published" without GitHub readback | A generated receipt is weaker than proof that GitHub actually accepted and still shows the Check/Comment. | Add GitHub readback receipt with check id, conclusion, head SHA, and sanitized error handling. |
| Required check is only a plan | Buyers will not pay enterprise prices for a gate that is not enforced in branch protection. | Add branch-protection verifier and admin-approved enforcement receipt. |
| Signed archive is simulated | "Signed" without real cryptographic verification or key identity is dangerous sales language. | Add detached signature verification, key fingerprint, signer binding, expiry/revocation status. |
| Bundle verification is hidden in CLI | If only engineers can run a command, managers and auditors will not perceive product value. | Show verifier status and receipt in Dashboard, Report Center, War Room, and exports. |
| Archive status is just a badge | A badge without archive hash, manifest, signature, storage, and verifier receipt is decorative. | Display archive id, hash, byte size, signature status, storage target, retention policy, verifier receipt. |
| Reviewer identity is local text | Enterprise buyers need role, provider subject, actor, org/project scope, and separation of duties. | Bind approvals to GitHub/OIDC/SSO identity and role policy. |
| Report Center is a static list | A list of reports is not evidence governance. | Add lifecycle, revocation, denied-view audit, manifest completeness, verification, retention, usage. |
| War Room repeats the dashboard | A second panel with the same data does not create workflow value. | War Room must add decision state, next action, accountable owner, reviewer timeline, replay readiness. |
| Redaction is not fail-closed | Evidence display can leak sensitive data if scanning is advisory only. | Block publish/share/archive promotion when redaction findings remain. |
| Self-host claim lacks operations | Offline verification is valuable but not enough for private enterprise deployment. | Add Docker/Compose or Helm path, backup/restore, migration checks, storage config, health checks. |
| Usage meters are hard-coded | Buyers notice fake billing data quickly. | Meter real events: publish, view, verify, archive, retained bytes, replay, report export. |
| No tenant/project scoping | Evidence from one customer must never appear in another customer's report center. | Add tenant-scoped evidence-health model and access tests before multi-tenant claims. |

## 付费驱动 / Paid Drivers

A3 can charge more when the display layer answers costly release-governance questions:

| Paid driver | Customer question | A3 display answer |
|---|---|---|
| Merge-risk control | Can this agent PR merge? | War Room shows gate decision, required-check state, GitHub publish status, verification status, and next action. |
| Audit readiness | Can we prove later what evidence supported this release? | Report Center shows bundle root hash, verifier receipt, archive signature, and retention state. |
| Security review | Did the exported packet pass redaction and access controls? | Dashboard/Report Center show redaction pass/fail, share token lifecycle, denied views, and fail-closed status. |
| Compliance retention | Is the release packet archived and verifiable? | Report Center shows signed archive verification, storage target, retention/legal hold, and audit log. |
| Release accountability | Who approved or waived this release? | War Room shows reviewer timeline, identity binding, expiry, roles, and separation-of-duties status. |
| Incident response | Which failed cases should be replayed before approval? | War Room shows top-risk cases, replay readiness, reproduced/fixed/flaky status, and RCA link. |
| Platform rollout | Which teams generate the most gates, reports, archive bytes, and verifier runs? | Report Center usage meters support chargeback and expansion. |
| Self-host procurement | Can we verify evidence without sending it to a hosted SaaS? | Self-host/offline verification panel shows bundle/archive verifier readiness. |

Simple sales sentence:

> "A3 does not only block risky agent releases; it shows the exact GitHub evidence, verifies the audit bundle, verifies the signed archive, and keeps that proof visible in the release workflow."

## ACV 提升 / ACV Uplift

Evidence display raises ACV because it connects A3 to budgets beyond developer tooling.

| ACV lever | Why it raises contract size | Product proof needed |
|---|---|---|
| Enforced PR Gate | Moves A3 into merge control and branch protection. | GitHub publish readback, branch-protection verifier, required-check receipt. |
| Enterprise Audit Archive | Security/compliance/legal teams pay for retained proof. | Signed archive verification, immutable storage, retention/legal hold, verifier export. |
| Report Center Governance | Turns report export into governed evidence inventory. | Lifecycle, redaction, verification, share audit, archive status, usage. |
| War Room Workflow | Turns eval output into cross-functional release operations. | Decision state, next action, owner, reviewer timeline, evidence-health gating. |
| Self-Host / Private Deployment | Regulated buyers often require private evidence processing. | Offline bundle/archive verification, object storage, backup/restore, upgrade path. |
| Identity-Bound Approvals | Enterprise sign-off requires real actor and role proof. | SSO/OIDC/GitHub binding, separation of duties, signature status. |
| Usage Governance | Platform teams need chargeback across projects and teams. | Metered gates, views, archives, verifier runs, retained bytes, replay jobs. |
| Compliance Pack | Buyers can use A3 evidence in procurement and customer audits. | Exportable customer-safe packet with hashes, signatures, redaction, retention. |
| API/Webhook Platform | Enterprise customers embed controls in internal systems. | Versioned evidence-health schemas, webhooks, SDK examples, compatibility tests. |

ACV call:

> The highest ACV increase comes when evidence display moves from "nice report" to "required release control plus retained, signed, verifiable audit archive."

## 上线风险降低 / Launch Risk Reduction

This display layer should reduce launch risk by making missing integrity impossible to miss.

| Launch risk | Display-based reducer |
|---|---|
| A release merges although GitHub publish failed | Dashboard/War Room show publish failure and next action `fix_github_publish`. |
| A release claims required-check enforcement without proof | War Room shows `required_check_readback: missing` or `admin_action_required`. |
| An auditor receives a stale or tampered report | Report Center shows bundle/archive verification failed and blocks external packet promotion. |
| A signed archive is unverifiable | Report Center shows signature failure, unknown key, expired key, or missing archive before share/export. |
| A sensitive artifact leaks through a hosted report | Redaction status blocks share and publish paths when findings remain. |
| Reviewers approve the wrong release packet | War Room binds approvals to run id, PR/head SHA, bundle root hash, archive hash, and policy version. |
| Self-host customer cannot reproduce verification | Report Center shows offline verifier command, bundle-relative paths, and storage readiness. |
| Support cannot debug GitHub publish issues | Sanitized receipt/error display gives check id, status, mode, endpoint class, and retry state without secrets. |
| Billing surprises customers | Usage display shows gates, published checks, views, verifier runs, archive bytes, and retained days. |
| Feature overclaims enterprise readiness | Toy-risk states remain visible: plan-only, dry-run-only, unsigned, unverified, missing identity, no retention. |

Minimum launch policy:

```text
No external "audit-ready" claim unless bundle verification passes.
No "signed archive" claim unless cryptographic archive verification passes.
No "required PR gate" claim unless branch-protection readback passes.
No hosted share when redaction status is blocked.
No approval-driven unblock unless reviewer identity and policy allow it.
```

## Enterprise / Self-Host / Audit / Compliance Support

### Enterprise

Enterprise buyers need display surfaces that support real governance:

- GitHub App installation and repository scope display.
- Required-check enforcement state and branch-protection readback.
- SSO/OIDC/GitHub actor binding for reviewers and approvers.
- Separation-of-duties display for release owner vs approver vs waiver signer.
- Policy version display for environment-specific release controls.
- Admin audit log for publish, verify, archive, share, revoke, approve, and waive actions.
- Report Center search by org, project, repo, PR, head SHA, run, archive, signer, and status.

### Self-Host

Self-host buyers need evidence to remain useful without hosted services:

- offline audit bundle verification;
- offline signed archive verification;
- bundle-relative paths and no local-user absolute paths;
- object storage target status;
- archive byte size, hash, and retention location;
- backup/restore verification status;
- migration/schema version status;
- health/readiness indicators for API, worker, store, object storage, verifier, redaction scanner;
- no reliance on live ReleaseFoundry or live GitHub for reading retained evidence.

Allowed self-host claim after display:

> "A3 can show whether retained release evidence is offline-verifiable."

Not yet allowed without packaging/ops:

> "A3 is a complete enterprise self-host release-governance platform."

### Audit

Audit support should be explicit:

- evidence packet id;
- generated artifact manifest id;
- audit bundle id and root hash;
- verifier receipt id and status;
- signed archive id, hash, signer, and verification status;
- chain-of-custody status;
- report snapshot id;
- GitHub Check/Comment receipt ids;
- redaction scan id;
- reviewer/waiver/approval record ids;
- retention/legal-hold state;
- exportable verification receipt.

### Compliance

Compliance support should remain honest:

- Good now: redaction status, bundle hashes, verifier results, archive status display, report lifecycle, share revocation, usage logs, self-host/offline story.
- Still needed: SOC2 evidence map, SSO/SAML, SCIM, data retention enforcement, legal hold, purge receipts, immutable object lock, key management, signer revocation, admin audit log search, tenant isolation tests, formal DPA/security docs.

Compliance phrasing to use:

> "SOC2-ready evidence controls" only after admin audit logs, retention, identity, access control, and operational controls exist.

Use now:

> "Audit-oriented release evidence display with hash verification and signed archive readiness."

## 不像真产品的地方 / What Still Does Not Feel Like A True Product

These gaps should stay visible in Growth-Auditor notes:

1. GitHub publish evidence can exist without live readback from GitHub.
2. Required-check enforcement is not yet proven by branch-protection verification.
3. GitHub App install, permission audit, uninstall behavior, and org/repo onboarding are not complete.
4. Signed audit archive verification is not yet fully productized with detached signatures, key fingerprints, expiry, revocation, and identity binding.
5. Reviewer approvals are not fully bound to SSO/OIDC/GitHub identity and role policy.
6. Report Center needs tenant/project scoping, pagination, filters, search, and stable detail views.
7. War Room needs one canonical evidence-health object instead of manually joined fields.
8. Redaction must fail closed across JSON, Markdown, CSV, HTML, PDF, screenshot, GitHub Check, PR comment, and archive paths.
9. Archive storage is not yet immutable with retention/legal-hold semantics.
10. Self-host is not yet packaged with install, backup, restore, upgrade, migration, and health verification.
11. Usage is not yet connected to plan entitlements, quotas, billing exports, or invoices.
12. Public API schemas, SDK examples, webhooks, and compatibility tests are incomplete.
13. Production trace ingestion and replay runner still need stronger contracts for real customer systems.
14. Judge calibration/drift status is not yet part of the release evidence-health display.
15. Customer onboarding does not yet connect GitHub, run first gate, publish check, open Report Center, and verify archive in under 10 minutes.

Auditor call:

> If A3 displays evidence states without proving enforcement, identity, archive verification, and retention, it will demo well but still feel like a sophisticated prototype.

## Evidence Health Model

The next implementation should introduce a shared display object, not three unrelated UI patches.

Suggested product contract:

```text
a3.release_evidence_health.v1
```

It should be generated from existing report/gate/bundle/archive inputs and consumed by Dashboard, Report Center, War Room, PR comments, hosted report pages, and webhooks.

Minimum fields:

```text
schema_version
release_context
  org_id/project_id/repo/pr/head_sha/environment/run_id/report_id
github_publish
  check_status/check_receipt_id/check_url_sanitized
  pr_comment_status/comment_receipt_id
  required_check_status/branch_protection_readback_status
report_packet
  hosted_report_id/share_status/snapshot_hash/redaction_status
audit_bundle
  bundle_id/root_hash/artifact_count/byte_count/completeness_status
  verification_status/verification_receipt_id/missing_artifacts/tamper_findings
signed_archive
  archive_id/archive_hash/signature_status/signer_status/key_status
  verification_status/verification_receipt_id/storage_target/retention_status
review
  approval_status/waiver_status/identity_binding_status/separation_of_duties_status
war_room
  state/next_action/owner/blocking_reasons
usage
  gate_count/published_checks/report_views/verifier_runs/archive_bytes/retained_days
safety
  redaction_status/secret_scan_status/export_allowed
```

Display rule:

```text
Dashboard = compact status and next action.
Report Center = packet inventory and lifecycle.
War Room = release decision, blockers, owner, reviewer timeline, and evidence-health gating.
```

## At Least 20 下一轮增长点 / Next Growth Points

The next round should run as productized evidence display, not broad dashboard expansion.

| ID | Surface | Growth point | Concrete build | Money value | Risk reduction |
|---|---|---|---|---|---|
| ED-01 | Shared model | Define `a3.release_evidence_health.v1`. | Join GitHub receipts, report snapshot, manifest, bundle verification, signed archive verification, redaction, review, and usage. | Creates one sellable control object. | Prevents Dashboard/Report Center/War Room drift. |
| ED-02 | Dashboard | Add compact Evidence Health card. | Show GitHub publish, bundle verified, archive verified, redaction, required-check, and next action. | Gives release owners instant value. | Makes missing integrity visible before merge. |
| ED-03 | Dashboard | Add evidence timeline drawer. | Show generated -> published -> shared -> bundled -> verified -> archived -> approved events. | Helps managers understand custody. | Catches skipped or stale steps. |
| ED-04 | Dashboard | Add sanitized GitHub receipt detail. | Display check id, conclusion, mode, head SHA, receipt hash, sanitized error, retry count. | Makes PR integration credible. | Reduces support/debug risk. |
| ED-05 | Dashboard | Add required-check readback state. | Show configured/planned/missing/failed/admin-required. | Converts PR Gate into release infrastructure. | Prevents overclaiming enforcement. |
| ED-06 | Report Center | Add evidence packet detail page. | Join hosted report, manifest, GitHub receipts, bundle, archive, verifier, redaction, usage, retention. | Makes Report Center a paid governance hub. | Reduces scattered evidence. |
| ED-07 | Report Center | Add completeness score. | Required artifacts present, optional artifacts present, stale/missing artifacts, verifier status. | Auditors and managers get a simple readiness signal. | Blocks incomplete packets. |
| ED-08 | Report Center | Add signed archive panel. | Show archive id, hash, byte size, signer, key fingerprint, signature status, verifier receipt, storage target. | Opens compliance/audit packaging. | Prevents fake "signed" claims. |
| ED-09 | Report Center | Add retention/legal-hold preview. | Show retain-until, legal-hold, purge-blocked, archive storage, object-lock readiness. | Enterprise compliance tier. | Prevents accidental evidence loss. |
| ED-10 | Report Center | Add offline verifier command export. | Provide bundle/archive verify commands using bundle-relative paths. | Strong self-host story. | Reduces unreproducible audit packets. |
| ED-11 | Report Center | Add share gating by evidence health. | Prevent external share when redaction, bundle, or archive verification fails. | Enterprise-safe report sharing. | Reduces leakage and audit disputes. |
| ED-12 | War Room | Add evidence-health driven state machine. | States: shipping, blocked, evidence_missing, verification_failed, archive_failed, approval_pending, replay_required. | Makes War Room operational. | Prevents ambiguous release decisions. |
| ED-13 | War Room | Add blocking reasons and next owner. | List verifier failure, missing check receipt, unsigned archive, pending approval, redaction block, replay missing. | Reduces stalled releases. | Clarifies accountability. |
| ED-14 | War Room | Add reviewer timeline binding to root hash/archive hash. | Approval/waiver records must reference release context, bundle root hash, archive hash, and policy version. | Enterprise sign-off value. | Prevents approval of the wrong packet. |
| ED-15 | War Room | Add archive verification blocker. | Production release cannot move to `shipping` if signed archive verification is required and failed. | Compliance-grade governance. | Prevents unverifiable release evidence. |
| ED-16 | War Room | Add replay readiness in evidence health. | Show top-risk cases, replay pack status, reproduced/fixed/flaky/new failure. | Expands product into incident/release ops. | Prevents approving unreplayed failures. |
| ED-17 | Hosted report | Add public-safe evidence summary. | Show non-sensitive report snapshot, bundle root hash, verification status, archive status, redaction status. | Makes external reports more trustworthy. | Avoids exposing internal-only fields. |
| ED-18 | PR comment | Add compact evidence-health block. | Include check status, report link, bundle root hash, verification status, archive status, next action. | Puts governance where engineers work. | Reduces dashboard-only adoption friction. |
| ED-19 | GitHub Check | Add evidence annotations. | Include verifier/archive status and links to hosted report/Report Center. | Strengthens branch protection story. | Prevents green check with broken evidence. |
| ED-20 | API | Publish evidence-health schema docs. | Versioned JSON schema with examples for pass, blocked, missing, tampered, archive failed. | Makes A3 platform-integratable. | Reduces contract drift. |
| ED-21 | API/Webhooks | Add evidence-health webhook dry-run. | Events: packet_verified, archive_verified, verification_failed, share_blocked, approval_bound. | Enterprise workflow automation. | Keeps side effects controlled in MVP. |
| ED-22 | Self-host | Add self-host evidence verification screen. | Show local verifier status, storage target, backup/restore status, migration version. | Private deployment upsell. | Reduces procurement risk. |
| ED-23 | Billing/usage | Meter evidence-health events. | Count publish receipts, report views, verifier runs, archive bytes, retained days, share revocations. | Enables quota and chargeback. | Prevents hidden cost growth. |
| ED-24 | Compliance | Add audit export bundle. | Export verification receipt, signed archive receipt, redaction summary, reviewer timeline, retention state. | Security/compliance buyer value. | Reduces manual audit prep. |
| ED-25 | Security | Add fail-closed redaction matrix. | Assert every external path respects blocked redaction: HTML, MD, JSON, CSV, PDF, screenshot, PR, Check, archive. | Enterprise safety. | Prevents sensitive evidence leakage. |
| ED-26 | Identity | Add signer/reviewer identity status. | Unknown, local-only, GitHub-bound, OIDC-bound, SSO-bound, expired, revoked. | Real enterprise approval story. | Prevents anonymous approvals. |
| ED-27 | Archive | Add detached signature verifier receipt. | Record archive hash, manifest hash, signature hash, key fingerprint, algorithm, verified_at. | Makes archive verification real. | Prevents decorative archive badges. |
| ED-28 | Search | Add Report Center filters. | Filter by verification failed, archive failed, redaction blocked, required-check missing, retention due. | Operational control at scale. | Prevents risky packets from hiding. |
| ED-29 | Onboarding | Add "first verified packet" flow. | Connect GitHub -> run gate -> publish dry-run/live -> create report -> verify bundle -> verify archive. | Makes value visible in first session. | Reduces pilot setup confusion. |
| ED-30 | E2E | Add evidence-health smoke scenario. | Blocked release with GitHub receipt, report, bundle verifier, signed archive verifier displayed across all three surfaces. | Demo confidence. | Catches cross-surface regressions. |

## 并行推进建议 / Parallel Execution Recommendation

Run this as six parallel lanes. Each lane can land independently as long as all consume the same `a3.release_evidence_health.v1` contract.

| Lane | Owner surface | First package | Parallel dependencies |
|---|---|---|---|
| A | Shared contract | Define evidence-health schema, statuses, state machine, fixture examples, and safety language. | Must start first; all other lanes consume it. |
| B | Dashboard | Compact Evidence Health card, GitHub receipt drawer, required-check state, next action. | Depends on A; can run with C/D/E/F. |
| C | Report Center | Evidence packet detail, completeness score, signed archive panel, offline verify command, retention preview. | Depends on A; can run with B/D/E/F. |
| D | War Room | Evidence-health state machine, blocking reasons, owner, reviewer timeline, archive verification blocker. | Depends on A; can run with B/C/E/F. |
| E | Enterprise/self-host | Offline verification display, storage target, backup/restore readiness, retention/legal-hold preview. | Depends on A/C; can run with B/D/F. |
| F | Monetization/API | Usage meters, evidence-health webhooks, schema docs, billing export fields. | Depends on A; can run after minimal B/C/D display exists. |

Recommended sequence:

1. Land `a3.release_evidence_health.v1`.
2. Render it in Dashboard and War Room first because those reduce release risk.
3. Expand Report Center detail because that creates paid audit inventory.
4. Add signed archive verification details and self-host/offline verifier display.
5. Add usage metering and API/webhook contracts.
6. Add branch-protection readback and identity-bound approvals before stronger enterprise claims.

## 最接近大钱方向 / Closest Direction To Big Money

Ranked by urgency, ACV potential, and fit with the large SaaS plan:

| Rank | Direction | Why it is closest to big money | Required proof before selling hard |
|---:|---|---|---|
| 1 | Enforced PR Gate with Evidence Health | It sits directly in the merge path and turns A3 into release infrastructure. | GitHub readback, branch-protection verifier, evidence-health card, fail-closed redaction. |
| 2 | Signed Audit Archive + Verification Display | Compliance/security buyers pay for retained, signed, verifiable release evidence. | Detached signature verifier, archive hash, signer/key status, retention/legal-hold display. |
| 3 | Report Center Evidence Inventory | Platform teams need a governed inventory of reports, bundles, archives, shares, and verifier receipts. | Evidence packet detail, completeness score, filters, search, share gating, usage. |
| 4 | Release War Room as Decision Cockpit | Cross-functional teams need a single room for blocked release decisions. | Evidence-health state machine, next action, owner, review timeline, replay readiness. |
| 5 | Self-Host Offline Verification | Regulated customers require private deployment and offline audit proof. | Bundle/archive verifier UI, storage target, backup/restore, migration, health checks. |
| 6 | Usage Governance / Chargeback | A3 becomes budgetable across teams when value and usage are visible. | Metered gates, publishes, verifier runs, archive bytes, retained days, report views. |

Auditor call:

> The closest big-money move is not a prettier dashboard. It is an evidence-health control plane that proves a PR gate was published, a report packet was bundled, a signed archive was verified, and the War Room blocked or approved the release for a defensible reason.

## Money-Grade Acceptance Criteria

This display round should not be considered money-grade until these are true:

1. Dashboard shows compact evidence health for the active release.
2. Report Center has a packet detail view joining report, GitHub receipts, bundle, verifier, signed archive, redaction, retention, and usage.
3. War Room state changes when bundle verification or archive verification fails.
4. GitHub publish evidence includes sanitized receipt id, mode, check/comment status, head SHA, and readback state when available.
5. Audit bundle display includes bundle id, root hash, artifact count, byte count, verifier status, and missing/tampered findings.
6. Signed archive display includes archive id, archive hash, signature status, signer/key status, verifier receipt, storage target, and retention state.
7. External share/export/publish can be blocked by redaction or verification failure.
8. Reviewer/approval display binds to release context, policy version, bundle root hash, and archive hash.
9. Self-host/offline verification path is visible and does not depend on absolute local user paths.
10. Usage meters include verifier runs, archive bytes, retained days, PR publishes, report views, and hosted shares.
11. The display uses a shared evidence-health object, not duplicated UI-only logic.
12. Safety copy distinguishes dry-run, plan-only, live, readback, verified, unsigned, unverified, and missing states.

## Final Auditor Call

A3 should strictly continue down the `large-saas-a1-a2-a3-full-plan.md` path: A1 handles production data/backend, A2 handles judge/policy/calibration, and A3 owns the customer-facing product workflow.

For A3, the highest-value next step is to make evidence integrity visible and actionable:

```text
Dashboard = Can this release move?
Report Center = Is this evidence packet complete, shared, retained, and verifiable?
War Room = What blocks this release, who owns it, and what proof supports the decision?
```

If A3 can display GitHub publish evidence, audit bundle verification, and signed audit archive verification across those three surfaces, the product moves from "evaluation report" to "enterprise release-governance control plane." That is the nearest path to serious money.
