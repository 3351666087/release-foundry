# A3 Share Token Lifecycle Growth Audit - 2026-07-07

Role: A3 Growth-Auditor / Money-Grade Auditor.

Scope: documentation artifact only. This audit reviews the commercial value of moving hosted reports from internal report-id access, `/reports/:reportId`, toward external share-token access, `/r/:shareToken`. It intentionally stays in `docs/a3` and does not modify runtime code, dashboard code, or tests.

Safety boundary:

- Did not read, print, edit, or rely on `.env.local`.
- Did not write any API key, token value, cookie, account email, signed URL, or credential-like sample.
- Did not call live ReleaseFoundry, GitHub, billing, identity, database, storage, or hosted-report services.
- Did not modify `services/report`, `apps/dashboard`, or `tests/a3`.
- This document uses route templates such as `/r/:shareToken`; it does not contain any real share token.

## Auditor Summary

Moving hosted reports from `/reports/:reportId` to `/r/:shareToken` is commercially important because it changes the report from "an internal object with a web page" into "a governed evidence link with lifecycle." That distinction is where enterprise buyers start paying.

The report-id path is useful for local demos and authenticated admin views. The share-token path is the beginning of a sellable control plane: external reviewers can open a redacted report without learning internal ids, admins can expire or revoke access, view attempts can become audit evidence, and Report Center can show the lifecycle of every shared packet.

Money-grade thesis:

> A3 can sell hosted reports only when each shared report is a governed, expiring, revocable, audited evidence object; `/r/:shareToken` is the right product boundary for that.

This round is valuable because it creates the product grammar for customer-facing evidence sharing. It is not yet the full enterprise product unless token hashing, expiry enforcement, revocation, denied-view audit, tenant scoping, immutable report snapshots, and Report Center controls are all proven together.

## 本轮新增可卖能力

| Capability | Why it is newly sellable | Buyer-facing value |
|---|---|---|
| External share route shape: `/r/:shareToken` | The external URL no longer has to expose internal report ids. | Customers can share a report with security reviewers, managers, or customer stakeholders without making the internal data model visible. |
| Share-link lifecycle concept | Hosted reports now have a product lifecycle: created, active, viewed, expired, revoked, denied, and superseded. | Admins can answer "is this report still live?" without digging through logs or source data. |
| Expiry posture | Share links can be treated as temporary evidence access, not permanent public pages. | Security teams are more likely to approve external sharing when links naturally age out. |
| Revocation posture | A shared report can be pulled back after accidental sharing, changed evidence, policy failure, or customer offboarding. | Enterprise admins get recovery control, which is a common procurement requirement. |
| View audit posture | Allowed and denied views can become durable evidence events. | A3 can prove who or what class of actor attempted access, when, and under which policy result, without exposing raw identities. |
| Internal vs external boundary | `/reports/:reportId` can stay internal/authenticated while `/r/:shareToken` becomes the external edge. | The product can support both operator workflows and customer-safe links without mixing access semantics. |
| Report Center lifecycle surface | Report Center can show share status, expiry, revoke state, view count, and manifest readiness. | The control plane becomes visible and demoable, which helps sales, onboarding, and renewal conversations. |
| Commercial usage meter hooks | Hosted reports, views, revocations, and verifier runs can be metered as high-value governance activity. | Pricing can expand beyond raw eval volume into compliance/reporting value. |
| Audit packet chain | A share token can point to a sealed report snapshot and manifest rather than a mutable live report body. | Auditors can verify what was shared, not just that a page existed. |
| Policy gate before publish | Share-link creation can be blocked when redaction, manifest, retention, or readiness checks fail. | A3 becomes a governed evidence publisher instead of a loose export button. |

## 哪些仍然 Toy-Like

| Gap | Why it still feels toy-like | Money-grade requirement |
|---|---|---|
| Raw token handling is not proven in this artifact | A route template is not enough; buyers need proof that raw tokens are never persisted, logged, or displayed after creation. | Store only `token_hash`, show only lifecycle metadata, and redact all token-bearing paths from durable manifests/logs. |
| Expiry without denied-view audit is weak | If expired accesses disappear silently, the team cannot investigate stale links or abuse. | Record allowed and denied access results, including `expired`, `revoked`, `not_found`, `scope_denied`, and `redaction_blocked`. |
| Revocation without immutable history is only an admin flag | A boolean revoke state does not prove who revoked, when, and why. | Append `report.share_link_revoked` audit events and keep revocation reason metadata redacted but durable. |
| View counts alone are insufficient | A number can help UI, but it is not audit evidence by itself. | Keep a view ledger with timestamp, share-link id, report snapshot id, actor/session class, user-agent hash, IP hash, and access result. |
| Report body mutability is dangerous | If a report can change behind the same link, the share token loses audit meaning. | Link share tokens to immutable report snapshots with content hash, builder version, redaction policy version, and source evidence hashes. |
| Internal report-id route may remain too powerful | If `/reports/:reportId` stays unauthenticated or externally reachable, the token route does not fully reduce exposure. | Treat report-id paths as internal/authenticated or admin-only, and put all external access through `/r/:shareToken`. |
| Report Center can become decorative | Status badges without enforceable API policy are not enterprise control. | UI state must reflect server-side enforcement for expiry, revoke, redaction block, manifest completeness, and tenant scope. |
| Tenant scoping is the hard part | Token lookup without organization/project scoping risks cross-tenant leakage. | Every report, share link, view, audit event, and usage row must be scoped and tested across tenant boundaries. |
| No customer-safe share creation workflow yet | A backend route alone does not explain who can create a link, with which policy, for how long. | Add role-gated link creation with presets such as PR review, customer evidence, security audit, incident replay, and executive sign-off. |
| No retention/legal-hold story | Enterprise buyers will ask what happens after expiry, revocation, purge, and audit retention. | Define retention for report snapshots, share links, view events, revocation records, and audit bundles. |

## 客户为什么愿意付费

Customers do not pay for a prettier hosted page. They pay when the page becomes release evidence they can safely show outside the engineering team.

The strongest willingness-to-pay drivers are:

1. Security-approved sharing. A3 can give managers, customer security teams, or auditors a link that does not expose internal ids and can be expired or revoked.
2. Reduced release-review labor. Instead of manually exporting, redacting, attaching, and explaining evidence, a reviewer can publish a governed report packet.
3. Evidence chain of custody. The shared page can point back to import receipts, report snapshot hash, manifest completeness, PR gate result, waiver/approval status, and audit bundle root.
4. Procurement confidence. Expiry, revocation, view audit, and tenant scoping are recognizable enterprise controls.
5. Incident response. If a risky report was shared, admins can revoke it, inspect allowed and denied access attempts, and prove what was visible.
6. Compliance reporting. The hosted report becomes an audit artifact, not a transient web page.
7. Self-serve external review. Customer-facing teams can share a controlled evidence packet without giving external parties dashboard access.
8. Expansion pricing. Hosted report views, report snapshots, audit packets, and retention policies can support paid tiers beyond raw run volume.

In buyer language:

- Engineering managers pay because the report shortens review cycles.
- Security teams approve because access is revocable and auditable.
- Platform teams pay because the workflow is automatable and policy-driven.
- Compliance teams value it because the evidence can be retained and verified.
- Executives understand it because it turns "the AI eval passed" into a shareable release-risk packet.

## Enterprise / Self-Host / Audit 价值

| Lens | Value of `/r/:shareToken` lifecycle | What must be true before selling hard |
|---|---|---|
| Enterprise SaaS | Enables customer-safe report sharing with scoped, expiring, revocable links and audit events. | Token hashes, tenant scoping, RBAC, immutable snapshots, redaction fail-closed behavior, and Report Center lifecycle UI. |
| Self-host | Gives customer platform teams a clear model for external report access without exposing database ids or storage paths. | Configurable base URL, migration-backed `share_links`, audit log health, retention policy, and object-storage-safe exports. |
| Audit | Converts report views and denied attempts into evidence, making the report packet verifiable after the fact. | Append-only audit events, content hashes, manifest linkage, report snapshot immutability, and verifier output. |
| Security review | Shows concrete controls for stale links, accidental sharing, and external access. | Expiry defaults, maximum TTL policy, immediate revocation, no raw token logs, and no signed URL persistence. |
| Procurement | Reduces objections around public links and unmanaged exports. | Policy matrix by plan, admin visibility, export firewall, legal-hold/retention documentation, and incident response workflow. |
| Revenue packaging | Creates premium surfaces: governed sharing, view audit, retention, verifier, and compliance packet presets. | Usage ledger rows for report snapshots, hosted views, revocations, export artifacts, and verification runs. |

## 下一轮增长点

These growth points should be treated as one lifecycle program, not isolated polish. At least the first ten need to move together for the share-token route to feel money-grade.

| ID | Growth point | Surface | Concrete next build | Commercial value |
|---|---|---|---|---|
| STL-01 | Store only token hashes. | API/store/DB | Generate a high-entropy share token once, persist only `token_hash`, and never return the raw token after creation response. | Reduces credential leakage risk and makes security review credible. |
| STL-02 | Split internal and external routes. | API/auth | Keep `/reports/:reportId` internal/authenticated; make `/r/:shareToken` the only external report viewer. | Prevents internal ids from becoming public customer URLs. |
| STL-03 | Enforce expiry on every external view. | API/test | Reject expired share links before report payload render and return a controlled expired page. | Makes external sharing acceptable to enterprise security teams. |
| STL-04 | Add immediate revocation. | API/UI/test | Add revoke action, revoke receipt, revoked state, and denied page for revoked links. | Lets admins recover from accidental or outdated sharing. |
| STL-05 | Record denied view attempts. | API/audit | Write audit events for expired, revoked, not-found, scope-denied, and redaction-blocked access attempts. | Turns access failures into incident and compliance evidence. |
| STL-06 | Record allowed view audit. | API/audit | Record allowed views with report snapshot id, share-link id, timestamp, access result, actor/session class, and hashed request metadata. | Creates audit-grade proof of external report access. |
| STL-07 | Link tokens to immutable snapshots. | report/store | Bind every share link to a snapshot id and content hash rather than a mutable report builder result. | Makes "what was shared" verifiable. |
| STL-08 | Add report snapshot metadata. | report/store | Store builder version, redaction policy version, source import ids, manifest id, audit bundle root, and content hash. | Supports compliance retention and audit verification. |
| STL-09 | Fail closed on redaction findings. | report/API | Block external share creation when export firewall or redaction scan is not clean. | Prevents A3 from becoming a leak amplifier. |
| STL-10 | Add share policy presets. | UI/API | Add presets for PR review, customer evidence, security audit, incident replay, executive sign-off, and self-host readiness. | Makes the feature easy to sell and use by persona. |
| STL-11 | Show lifecycle in Report Center. | UI/API | Show status, expiry, revoked-at, last viewed, view count, denied count, manifest completeness, and redaction state. | Makes governance tangible in demos and daily operations. |
| STL-12 | Add share-link detail route. | API/UI | Return metadata, not token value: status, scope, created-by class, expiry, revoke receipt, view summary, and linked artifacts. | Lets admins inspect links without exposing secrets. |
| STL-13 | Add role-gated share creation. | auth/API | Require explicit permission to create external links and set max TTL by role/plan. | Aligns with enterprise RBAC expectations. |
| STL-14 | Add maximum TTL policy. | policy/API | Enforce default and maximum expiry windows by packet type and customer plan. | Converts link control into a packageable enterprise feature. |
| STL-15 | Add token rotation on republish. | report/API | When report content, source evidence, or redaction policy changes, supersede the old link and require a new share token. | Prevents stale evidence from looking current. |
| STL-16 | Add supersession state. | report/audit | Track active, expired, revoked, superseded, redaction-blocked, and deleted-under-retention states. | Gives lifecycle language to support and auditors. |
| STL-17 | Add usage ledger events. | usage/API | Meter report snapshots, share-link creation, hosted views, denied views, revocations, verifier runs, and retained artifacts. | Enables pricing, quotas, and chargeback. |
| STL-18 | Add tenant scoping tests. | tests/API/DB | Prove one organization/project cannot view or revoke another org/project share link. | Addresses the highest-severity SaaS data-leak class. |
| STL-19 | Add idempotent share creation. | API/store | Use operation idempotency for share-link creation so retries do not create duplicate live links. | Prevents duplicate links and confusing audit records. |
| STL-20 | Add audit-event hash chain. | audit/DB | Chain share-created, viewed, denied, revoked, expired, and superseded events. | Makes lifecycle evidence tamper-evident. |
| STL-21 | Add verifier command/input. | CLI/audit | Verify a hosted report snapshot, manifest id, view ledger summary, and audit event hashes without exposing raw token values. | Gives auditors and self-host operators a repeatable proof workflow. |
| STL-22 | Add export firewall scan for hosted HTML. | report/test | Scan hosted HTML for secrets, signed URL markers, local paths, raw tokens, and unsafe CSV/Markdown carryover before publish. | Makes external report pages security-reviewable. |
| STL-23 | Add customer-safe error pages. | HTML/API | Expired, revoked, blocked, and not-found pages should reveal no report metadata or internal ids. | Reduces information disclosure from invalid links. |
| STL-24 | Add access-result taxonomy. | docs/API | Standardize `allowed`, `expired`, `revoked`, `not_found`, `scope_denied`, `redaction_blocked`, `auth_required`, and `superseded`. | Makes logs, UI, support, and audit reports consistent. |
| STL-25 | Add optional auth-bound links. | auth/API | Support public-token links and authenticated-viewer links as distinct policy modes. | Unlocks stricter enterprise deployments without losing lightweight sharing. |
| STL-26 | Add self-host readiness checks. | self-host/API | Report share-link migration version, audit append health, base URL policy, retention policy, and export firewall status. | Makes the feature operable for customer platform teams. |
| STL-27 | Add retention/legal-hold policy. | policy/DB | Define retention for snapshots, links, view events, revocations, denied attempts, and verifier artifacts. | Satisfies compliance and incident-response requirements. |
| STL-28 | Add PR Gate linkage. | PR/API/docs | Include hosted report share status, expiry, manifest id, and audit bundle root in PR check output. | Puts A3 evidence in the workflow where teams decide to ship. |
| STL-29 | Add incident response packet. | report/audit | Generate a packet showing what link existed, what snapshot it exposed, when it was viewed, and when it was revoked. | Creates high-value post-incident evidence. |
| STL-30 | Add plan packaging matrix. | product/docs | Map public sharing, auth-bound sharing, view audit, retention, verifier, and legal hold to plan tiers. | Turns lifecycle controls into revenue architecture. |

## 必须并行推进的方向

The share-token route should not be implemented as a single endpoint and declared done. The following tracks need to move in parallel:

1. Security architecture: token hash storage, no raw token logging, route split, denied-page information minimization.
2. Persistence: SQL-backed report snapshots, share links, view ledger, revocation records, audit events, usage ledger, and retention policy.
3. Report integrity: immutable snapshots, content hashes, builder version, redaction policy version, manifest id, and source evidence hashes.
4. Product control plane: Report Center status, revoke controls, expiry visibility, packet presets, and share-link detail views.
5. Audit and verifier: append-only events, hash-chain proof, lifecycle summaries, and verifier command output.
6. PR Gate and release workflow: PR comments/checks should point to the same manifest, hosted report lifecycle, readiness result, and audit bundle.
7. Self-host readiness: migrations, base URL policy, object storage safety, audit log health, retention/legal hold, and operator diagnostics.
8. Pricing and packaging: usage ledger, quotas, plan matrix, and enterprise-only controls.

## 安全边界

Minimum security boundaries before this can be sold as enterprise-grade:

- Never persist raw share tokens. Persist only hashes and lifecycle metadata.
- Never print raw share tokens in logs, reports, manifests, audit events, screenshots, docs, or errors.
- Never place API keys, cookies, bearer tokens, account emails, signed URLs, local home paths, or storage keys in hosted report content.
- Do not render report content for expired, revoked, blocked, not-found, or scope-denied links.
- Do not reveal whether a specific internal report id exists from the external route.
- Do not let `/reports/:reportId` behave as a public external route once `/r/:shareToken` is available.
- Do not reuse the same share token after report content, source evidence, redaction policy, or access policy changes.
- Do not allow share-link creation when redaction/firewall status is unknown or failing.
- Do not allow cross-organization or cross-project lookup, view, revoke, or audit access.
- Do not treat view count as a substitute for durable view audit.
- Do not make billing, identity, invite, API-key, or retention-destroy mutations from local/demo-only shells.
- Keep live signed media rendering blocked unless safe preview, expiry, authorization, and redaction behavior are proven.

## Money-Grade Acceptance Criteria

This lifecycle should be considered commercially complete only when A3 can prove:

- External hosted reports use `/r/:shareToken` and never expose internal report ids.
- Raw share tokens are shown only at creation time and are never persisted, logged, or committed.
- `token_hash` lookup is tenant-scoped and covered by negative tests.
- Expired and revoked links return controlled pages with no report body.
- Allowed and denied views both emit audit events.
- Revocation writes an immutable revocation event with redacted reason metadata.
- Share links point to immutable report snapshots with content hash and redaction policy version.
- Report Center shows lifecycle status, expiry, revoke state, last-viewed summary, denied count, manifest status, and sealed evidence hash.
- PR Gate, Report Center, hosted report, and audit bundle all reference the same manifest or snapshot chain.
- Self-host readiness can verify migrations, audit append/read, retention policy, and external base URL policy without exposing secrets.

## Auditor Call

This is a high-leverage commercial move. `/r/:shareToken` is not just a nicer URL; it is the access boundary that lets A3 become a customer-safe evidence distribution product.

The next round should resist calling the feature complete at "route works." The paid version is lifecycle plus proof: hashed token, scoped lookup, expiry, revocation, denied-view audit, immutable snapshot, Report Center control, PR Gate linkage, usage metering, and self-host readiness.

Best sellable sentence after the next round:

> This report was published as a sealed snapshot, shared through a scoped expiring token, viewed under audited policy, revocable by admins, linked to the PR gate and audit bundle, and verifiable later without exposing secrets.
