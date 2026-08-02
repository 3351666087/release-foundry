# A3 Signed Approval / Sign-Off Growth Audit - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Signed Approval Auditor.

Focus: signed approval, management sign-off, approval validation, reviewer identity, reviewed artifact hash binding, separation of duties, GitHub/OIDC/SSO provenance, immutable audit bundle, self-host retention, and required-check readiness.

Safety boundary followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed media URLs.
- Did not call the live ReleaseFoundry API.
- Did not call the live GitHub API.
- Wrote only this file: `docs/a3/p3_growth_auditor_signed_approval_2026_07_07.md`.
- Did not modify `services/report/a3_gate_cli.mjs`, `tests/a3/a3_gate_cli.test.mjs`, `fixtures/a3/p3`, `docs/a3/worklog.md`, `docs/a3/p3_worklog.md`, or `docs/a3/acceptance_checklist.md`.

Evidence reviewed:

- `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`
- `docs/a3/p3_gate_cli_growth_2026_07_07.md`
- `docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md`
- `docs/a3/p3_waiver_validation_growth_2026_07_07.md`
- `docs/a3/p3_github_dry_run_integration_2026_07_07.md`
- `docs/a3/p3_github_action_workflow_example.yml`
- `docs/a3/p3_growth_auditor_waiver_workflow_2026_07_07.md`
- `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`
- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- `fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json`
- `fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json`
- `fixtures/a3/p3/a3_github_check_create_request.redacted.json`

## Executive Verdict

A3 now has a credible local release governance chain: Release Gate can block a risky agent release, PR Gate can produce GitHub-shaped evidence, Gate CLI can emit machine-readable and human-readable artifacts, generated artifact manifest hashes the main gate outputs, and waiver validation can accept or reject a local `a3.waiver.v1` file.

The next commercial maturity gap is signed approval. A3 can now prove that a waiver file satisfies local policy, but it cannot yet fully prove that a specific authenticated person, acting in an authorized role, signed a specific decision, after reviewing a specific immutable evidence bundle, with separation of duties and retention guarantees.

Narrow maturity read:

| Dimension | Current read | Reason |
|---|---:|---|
| Release decision clarity | 8/10 | Gate decision, failed checks, risk score, and required approvers are explicit. |
| Waiver validation | 7/10 | Local `a3.waiver.v1` and `a3.waiver_review.v1` validate scope, expiry, required roles, failed-check coverage, and reviewed artifact hashes. |
| Approval/signature evidence | 3/10 | Waiver has `approved_by`, but there is no separate signed approval record, identity source, or cryptographic/non-repudiation layer. |
| Reviewed evidence binding | 6/10 | Waiver references the generated artifact manifest hash, but there is no bundle root hash over all source, generated, waiver, approval, and redaction artifacts. |
| Decision binding | 4/10 | Approval is not yet bound to an explicit approve/reject/waive decision object with policy version and required-check effect. |
| Separation of duties | 2.5/10 | Required roles exist, but release author versus approver conflicts are not enforced. |
| GitHub/OIDC/SSO identity | 2/10 | GitHub check dry-run exists, but signer identity is not tied to GitHub actor, OIDC claims, SSO group, or enterprise directory. |
| Immutable audit bundle | 4.5/10 | Input and output hashes exist, but no sealed bundle, root hash, signature, append-only event log, or retention class exists. |
| Required-check readiness | 6/10 | CLI and GitHub dry-run payloads exist; live required check and branch protection are still absent. |
| Self-host compliance retention | 3/10 | Local-first evidence is promising, but persistence, RBAC, legal hold, deletion audit, backup, and retention policy are missing. |

## Why Signed Approval Matters Commercially

Signed approval is not paperwork decoration. It is the control that turns an A3 release gate from a smart report into an enterprise governance product.

For enterprise paid adoption:

1. Buyers pay more for accountable controls than for dashboards. A dashboard explains risk; signed approval proves who accepted or rejected it.
2. Agent releases create operational, safety, privacy, and brand risk. Enterprises need a release control that fits procurement, security review, and audit language.
3. Waiver validation reduces chaos, but signed approval creates accountability. A buyer can say, "This exception was approved by the right person for the right release and expired on this date."
4. Signed approval creates a premium SKU path: RBAC, SSO, immutable bundles, retention, branch protection, audit exports, and self-host compliance are all enterprise-tier features.
5. Approval history increases product stickiness. Once A3 becomes the release decision ledger, teams return to it for audits, incident reviews, renewals, and management reviews.

For boss sign-off:

1. Executives do not want raw eval traces. They need a concise decision packet with gate result, failed controls, waiver status, approvers, expiry, follow-up owner, and bundle hash.
2. A boss signature must bind to exactly what was reviewed. If the evidence can change after sign-off, the sign-off is weak.
3. Management needs risk acceptance in business language: why ship, who owns remediation, what is the expiry, and whether production remains blocked.
4. Signed approval makes "ship anyway" a deliberate accountable action instead of an informal Slack decision.

For compliance audit:

1. Auditors ask who approved what, when, under which policy, and against which evidence. Signed approval is the answer format.
2. Artifact hashes and manifest hashes make evidence tamper-evident. Approval records need to reference those hashes.
3. Separation of duties prevents self-approval. This is basic compliance hygiene for risky releases.
4. Retention policy makes the evidence discoverable months later. Without retention, the approval chain can disappear.
5. Required-check integration shows enforcement. A report that says "blocks merge" is useful; a branch-protected check that actually blocks merge is a control.

## Current A3 Evidence Chain

Current strengths:

- Release Gate can produce `block_release`, `needs_review`, or `approve_release`.
- The local blocked fixture records `decision: block_release`, `risk_score: 100`, `blocks_merge: true`, and GitHub check conclusion `failure`.
- Failed checks are explicit: `pass_rate`, `critical_failures`, `policy_failures`, and `required_tool_coverage`.
- Required approver roles are explicit: Release owner, A3 triage owner, Safety reviewer, and A1 runner/tooling owner.
- PR Gate emits GitHub-shaped check output and PR comment Markdown.
- Gate CLI emits `a3.gate_cli.v1`, `release_gate`, `release_workflow`, `waiver_review`, GitHub check payload, PR comment body, input `audit_manifest`, and redaction log.
- Generated artifact manifest uses `a3.generated_artifact_manifest.v1` and hashes the generated JSON report, Markdown report, GitHub check payload, and PR comment Markdown.
- Waiver request uses `a3.waiver.v1` and includes release version, environment, run id, head SHA, waiver owner, business reason, risk acceptance, expiry, follow-up issue, blocked checks, case ids, approvals, and reviewed artifact hash.
- Waiver review uses `a3.waiver_review.v1`, marks the demo waiver as `valid_exceptional_waiver`, confirms missing approvers are empty, confirms missing failed checks are empty, and keeps `automatic_unblock: false`.
- GitHub dry-run request uses `a3.github_check_request.v1`, records `checks:write` as needed scope, and marks requests as dry-run only with no token included.
- GitHub Actions example shows the future CI path: build gate artifacts, upload them, and enforce `exit_code_hint`.

Current commercial meaning:

A3 can already tell a buyer, "This risky release is blocked; here are the failed controls; here are the required approver roles; here is a valid local exceptional waiver; here are hashed gate outputs; and this waiver does not automatically unblock the release."

That is a serious paid-pilot foundation. It is not yet a signed enterprise approval system.

## What Is Still Missing After Waiver Validation

Waiver validation answers, "Does this exception request satisfy local policy?" Signed approval must answer a harder set of questions.

| Missing capability | Current state | Needed approval/signature maturity |
|---|---|---|
| Dedicated approval schema | `a3.waiver.v1` includes `approved_by`, but approval is embedded in the waiver. | Add `a3.approval.v1` as a separate record with approval id, waiver id, release id, signer, role, decision, reviewed bundle hash, timestamp, and policy version. |
| Signer identity source | Approver records have role, name, and timestamp. | Bind signer to GitHub actor, OIDC subject, SSO user id, enterprise email hash, or file-backed self-host identity. |
| Signer authorization | Required roles are checked, but role membership is not proven. | Validate signer role against GitHub team, SSO group, OIDC claim, or local RBAC policy. |
| Cryptographic signature | No signature field exists. | Add optional local signature, Sigstore/cosign-compatible metadata, or enterprise key reference. |
| Reviewed artifact binding | Waiver references generated artifact manifest hash. | Approval should bind to a bundle root hash covering source inputs, generated outputs, waiver, approval policy, redaction log, and replay pack. |
| Decision binding | Approval does not have a first-class decision object. | Bind approval to `approve_release`, `reject_release`, `approve_exceptional_waiver`, `request_changes`, or `acknowledge_blocked_release`. |
| Required-check effect | Waiver review says automatic unblock is false. | Define whether a valid approval changes required-check conclusion, leaves it blocked, or creates a separate "exception accepted" status. |
| Separation of duties | No visible release-author conflict check. | Prevent release author, PR author, run creator, or policy owner from self-approving certain risk classes. |
| Multi-approver quorum | Required roles exist. | Define all-of, any-of, quorum, executive override, and safety-veto rules. |
| Approval lifecycle | Waiver has expiry. | Approval needs statuses: pending, approved, rejected, revoked, expired, superseded, remediated, and revalidated. |
| Revocation | No approval revocation record. | Add revocation reason, revoked_by, revoked_at, and replacement approval id. |
| Policy version | Gate thresholds exist, but approvals are not tied to policy version. | Store release policy version, waiver policy version, role policy version, and signature policy version. |
| Chain of custody | Generated artifacts are hashed. | Add append-only events for generated, reviewed, approved, waived, verified, expired, revoked, retained, and deleted. |
| Immutable bundle | No sealed release bundle exists. | Create bundle id, root hash, signature, archive path, storage backend, and verification command. |
| Self-host retention | No durable retention model. | Define retention days, legal hold, delete-after, storage class, backup/restore, deletion audit, and WORM/object-lock option. |
| GitHub required check | Dry-run payload exists. | Add live required check writer behind explicit dry-run/live boundary plus branch-protection fixture. |
| OIDC provenance | GitHub workflow can pass head SHA. | Record workflow run id, run attempt, actor, OIDC subject, repository, ref, and head SHA in approval provenance. |
| SSO/RBAC | No enterprise identity contract. | Add role mapping for SSO groups, GitHub teams, and self-host RBAC roles. |
| Follow-up issue authority | Waiver has `follow_up_issue`. | Validate issue owner, due date, status, repository/project, and relation to waived checks. |
| Audit export | Markdown/PDF sign-off is implied. | Generate management sign-off packet that includes gate decision, waiver review, approvals, bundle hash, expiry, and verification instructions. |

## Next Growth Points

These growth points are intentionally biased toward revenue-grade signed approval. They cover approval schema, signer identity, reviewed artifact hash, decision binding, separation of duties, OIDC/GitHub actor/SSO, immutable bundle, self-host retention, and required check.

| ID | Growth point | Why it matters | Lane |
|---|---|---|---|
| SA-1 | Add `a3.approval.v1` schema. | Separates approval evidence from waiver request content. | Approval schema |
| SA-2 | Include `approval_id`, `waiver_id`, `release_version`, `environment`, `run_id`, `head_sha`, and `repo`. | Prevents approvals from being reused across releases. | Approval schema |
| SA-3 | Add first-class `decision`: approve, reject, approve_exceptional_waiver, request_changes, acknowledge_blocked_release. | Makes the sign-off meaning machine-readable. | Decision binding |
| SA-4 | Bind approval to `release_gate.decision`, failed checks, top-risk case ids, and waiver review status. | Proves the signer accepted the actual risk state. | Decision binding |
| SA-5 | Require `reviewed_artifacts[]` with SHA-256 values. | Shows exactly what evidence the signer reviewed. | Reviewed artifact hash |
| SA-6 | Add `reviewed_bundle_root_hash`. | Gives one stable hash for the entire sign-off packet. | Reviewed artifact hash |
| SA-7 | Add `policy_versions` for gate, waiver, approval, role, redaction, and retention policies. | Makes future audits reproducible after policies change. | Approval schema |
| SA-8 | Add `signature` block with algorithm, key id, signature value, certificate chain or key reference, and verification status. | Moves from attestation text to stronger non-repudiation. | Signature |
| SA-9 | Support unsigned local-dev approvals with explicit `signature_mode: local_attestation`. | Keeps pilots practical while making the trust level visible. | Signature |
| ID-1 | Add signer identity fields: display name, email hash, GitHub actor, GitHub actor id, OIDC subject, SSO subject, and tenant id. | Turns role labels into accountable people without exposing secrets. | Signer identity |
| ID-2 | Record identity source: GitHub Actions OIDC, GitHub App, SSO/SAML, OIDC provider, local file-backed user, or admin import. | Lets auditors understand the trust boundary. | OIDC/GitHub/SSO |
| ID-3 | Add role mapping policy from GitHub teams, SSO groups, OIDC claims, or local RBAC roles to A3 approver roles. | Proves the signer was allowed to approve. | OIDC/GitHub/SSO |
| ID-4 | Hash or redact personal identity fields in exported fixtures. | Preserves audit value without leaking sensitive user data. | Signer identity |
| SOD-1 | Enforce release author cannot approve their own blocked release. | Prevents the most obvious self-approval failure. | Separation of duties |
| SOD-2 | Enforce PR author, gate runner, and waiver owner conflict checks. | Reduces insider and process-risk concerns. | Separation of duties |
| SOD-3 | Add safety-veto rule: Safety reviewer rejection overrides release-owner approval for policy failures. | Makes high-risk safety controls meaningful. | Separation of duties |
| SOD-4 | Define quorum rules: all required roles, any one executive, two-person rule, or emergency override. | Matches real enterprise approval policy. | Separation of duties |
| BND-1 | Add immutable bundle id and root hash over inputs, generated outputs, waiver, approvals, redaction log, and replay evidence. | Creates one evidence handle for sign-off. | Immutable bundle |
| BND-2 | Add `releasefoundry gate verify --bundle` or `--manifest` command. | Lets buyers verify the signed packet later. | Immutable bundle |
| BND-3 | Add append-only chain-of-custody events. | Shows generation, review, approval, waiver, export, retention, deletion, and verification history. | Immutable bundle |
| BND-4 | Package signed approval bundle as zip/tar with manifest, reports, GitHub check payload, PR comment, waiver, approvals, and replay pack. | Creates a customer-deliverable audit artifact. | Immutable bundle |
| BND-5 | Hash PDF/print packet and screenshots in the generated artifact manifest. | Makes boss-facing sign-off material tamper-evident. | Immutable bundle |
| GH-1 | Add live GitHub Check writer behind explicit dry-run/live flag. | Turns advisory payload into actual merge control. | Required check |
| GH-2 | Add branch-protection and required-check policy fixture. | Documents what makes "blocks merge" real. | Required check |
| GH-3 | Persist check-run id by repo, PR, head SHA, and A3 run id. | Allows safe update mode without duplicate check noise. | Required check |
| GH-4 | Add approval state to GitHub check summary and PR comment. | Makes reviewer status visible where merge decisions happen. | Required check |
| GH-5 | Record GitHub workflow run id, run attempt, actor, event name, repository, ref, head SHA, and OIDC subject in audit manifest. | Connects CI provenance to approval evidence. | OIDC/GitHub/SSO |
| RET-1 | Define self-host retention policy schema. | Gives regulated customers a durable evidence lifecycle. | Self-host retention |
| RET-2 | Add retention metadata to bundles: storage backend, retention days, legal hold, delete-after, and deletion policy. | Makes the signed approval discoverable and governable. | Self-host retention |
| RET-3 | Add local SQLite/Postgres persistence for approvals, waivers, manifests, and audit events. | Moves from file-only pilot to self-host workflow. | Self-host retention |
| RET-4 | Add WORM/object-lock compatible archive option. | Supports higher-compliance customers. | Self-host retention |
| RET-5 | Add backup/restore and deletion audit docs. | Makes self-host operations credible. | Self-host retention |
| UX-1 | Add management sign-off packet. | Gives executives a concise document worth signing. | Boss sign-off |
| UX-2 | Add dashboard Approval panel showing required roles, collected signatures, expiry, conflicts, and bundle hash. | Makes governance status legible without reading JSON. | Boss sign-off |
| UX-3 | Add PR comment approval summary: pending approvers, invalid signatures, expiry, and required-check effect. | Reduces reviewer friction in GitHub. | Required check |
| ISSUE-1 | Validate follow-up issue shape, owner, due date, and waived-check mapping. | Ensures accepted risk produces remediation work. | Approval validation |
| ISSUE-2 | Later add live GitHub/Jira issue validation behind explicit dry-run/live boundary. | Prevents stale or fake remediation references. | Approval validation |
| SEC-1 | Add redaction finding log with field paths and reasons. | Proves sensitive data was handled intentionally. | Compliance |
| SEC-2 | Add fail-closed export mode when suspicious secrets remain. | Keeps audit bundles safe enough for enterprise sharing. | Compliance |

## Parallel Execution

Several workstreams can move at the same time. The team should not wait for live GitHub integration before improving local approval maturity.

| Lane | Can start now? | First useful deliverable | Can run in parallel with |
|---|---|---|---|
| Approval schema | Yes | `a3.approval.v1` JSON schema and redacted fixture. | Identity, bundle hash, UI packet |
| Decision binding | Yes | Approval record references gate decision, failed checks, waiver status, and required-check effect. | Approval schema and waiver validation |
| Reviewed artifact hash | Yes | Approval references generated artifact manifest SHA-256 and future bundle root hash. | Immutable bundle |
| Signer identity | Yes | File-backed identity source fields plus GitHub/OIDC/SSO placeholders. | Role mapping and redaction |
| Role authorization | Yes | Local role policy mapping required approver roles to allowed signer identities. | Separation of duties |
| Separation of duties | Yes | Conflict checks for release author, PR author, waiver owner, and approver. | Approval validation |
| Immutable bundle | Yes | Bundle id, root hash, and verify command over existing input/output hashes. | Approval and redaction log |
| Required check | Partly | Branch-protection policy fixture and dry-run/live boundary. | Approval state summary |
| Self-host retention | Yes for design | Retention policy schema and storage lifecycle docs. | Persistence and immutable bundle |
| Management sign-off UX | Yes | Markdown/PDF sign-off section referencing bundle hash and approval state. | Approval schema |
| Redaction hardening | Yes | Redaction finding log and fail-closed tests. | Bundle and approval export |
| Live GitHub writer | Later | Only after auth, branch protection, and token boundaries are approved. | Should consume the same local approval contract |

Suggested parallel sprint:

1. One engineer adds `a3.approval.v1` and a redacted local approval fixture.
2. One engineer adds role mapping and separation-of-duties validation.
3. One engineer adds bundle root hash and `releasefoundry gate verify`.
4. One engineer adds management sign-off Markdown/PDF section.
5. One engineer drafts self-host retention and RBAC policy.
6. One engineer keeps GitHub required-check work dry-run until auth and branch protection are approved.

## Impact If The Main Agent Implements Local Approval Validation

If the main agent implements local approval validation, A3's commercial maturity improves in the exact place enterprise buyers care about most: from "valid exception request" to "enforceable, attributable, auditable sign-off."

Expected uplift:

| Area | Before local approval validation | After local approval validation |
|---|---|---|
| Sign-off credibility | Waiver contains approver names and timestamps. | A separate approval record proves signer, role, decision, reviewed hashes, and policy version. |
| Buyer trust | A3 validates waiver policy locally. | A3 validates whether the right people approved the right evidence for the right release. |
| Boss signature | Executives see a report and waiver status. | Executives can sign a packet tied to a manifest or bundle hash. |
| Compliance audit | Auditors see waiver review status. | Auditors see approval provenance, authorization, separation of duties, and evidence binding. |
| Required-check readiness | Gate can fail CI and report missing waiver. | Gate can fail on missing, invalid, unauthorized, stale, or conflicted approvals. |
| Self-host story | Local files prove the contract shape. | Local regulated pilots can run approval governance without SaaS, live ReleaseFoundry, or live GitHub. |
| Enterprise pricing | A3 is a release intelligence pilot. | A3 starts to look like a paid governance system with approval records, policy enforcement, and audit exports. |

Commercial maturity estimate after local approval validation:

- Signed approval: 3/10 to about 6/10.
- Approval validation: 3.5/10 to about 6.5/10.
- Compliance posture: 6/10 to about 7/10.
- Executive sign-off readiness: 4.5/10 to about 6.5/10.
- Required-check readiness: 6/10 to about 7/10.
- Enterprise paid-pilot readiness: about 7/10 to about 7.5/10.
- Self-host compliance readiness: 3/10 to about 4.5/10.

The highest-value local approval validator behavior:

1. Fail if approval is absent when waiver review is valid but blocked release still requires manual sign-off.
2. Fail if approval scope does not match release version, environment, repo, run id, head SHA, failed checks, waiver id, and generated artifact manifest hash.
3. Fail if signer role is not one of the required approver roles.
4. Fail if signer identity cannot be resolved from the configured identity source.
5. Fail if separation-of-duties rules are violated.
6. Fail if approval decision does not match the release policy, for example approving production when waiver states staging only.
7. Fail if approval was created before the generated artifact manifest or waiver review it claims to approve.
8. Fail if reviewed artifact hashes are malformed or do not match the generated manifest.
9. Fail if approval is expired, revoked, superseded, or tied to an outdated policy version.
10. Emit approval validation status into JSON, Markdown, PR comment, GitHub check payload, generated artifact manifest, and management sign-off packet.

## Final Auditor Call

A3 has already crossed an important line: waiver validation is no longer just prose. It is a local contract with schema, scope, expiry, roles, failed-check coverage, and reviewed artifact hash evidence.

The next line is signed approval. That is where A3 becomes easier to sell to enterprises because it answers the uncomfortable questions that appear in every real release review:

- Who signed?
- Were they allowed to sign?
- What exact evidence did they review?
- What decision did they bind themselves to?
- Did anyone self-approve?
- Can the bundle be verified later?
- Will the evidence still exist during an audit?
- Did the required check actually enforce the policy?

Best next sequence:

1. Add `a3.approval.v1`.
2. Bind approvals to generated artifact manifest hash and later bundle root hash.
3. Add signer identity source and role authorization policy.
4. Enforce separation of duties.
5. Add approval lifecycle: pending, approved, rejected, expired, revoked, superseded.
6. Add management sign-off packet.
7. Add immutable bundle root hash and verify command.
8. Add self-host retention schema and audit event log.
9. Add required-check policy fixture.
10. Wire live GitHub required check only after auth, branch protection, and live-call boundaries are approved.

What this audit did not do:

- Did not modify Gate CLI, tests, fixtures, worklogs, or checklist files owned by the main agent.
- Did not revert or overwrite existing changes.
- Did not call live ReleaseFoundry or GitHub APIs.
- Did not read or print secret-bearing files.
