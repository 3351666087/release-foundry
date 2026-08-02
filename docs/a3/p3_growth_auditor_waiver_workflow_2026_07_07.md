# A3 Waiver Workflow Growth Audit - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Waiver Workflow Auditor.

Focus: waiver workflow, signed approval, reviewer identity, expiry validation, follow-up issue enforcement, immutable audit evidence, GitHub required check readiness, compliance posture, and self-host retention.

Safety boundary followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed media URLs.
- Did not call the live ReleaseFoundry API.
- Did not call the live GitHub API.
- Wrote only this file: `docs/a3/p3_growth_auditor_waiver_workflow_2026_07_07.md`.

Evidence reviewed:

- `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`
- `docs/a3/p3_gate_cli_growth_2026_07_07.md`
- `docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md`
- `docs/a3/p3_growth_auditor_2026_07_07.md`
- `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`
- `fixtures/a3/release_gate_thresholds.json`
- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- Gate and report source/test snippets around Release Gate, PR Gate, CLI payload, waiver policy, reviewer lanes, audit bundle, and generated artifact manifest.

## Executive Verdict

A3 now has a credible enterprise release-control story: Release Gate decides approve / review / block, PR Gate emits GitHub-shaped evidence, Gate CLI can run locally or in CI shape, and the generated artifact manifest hashes the main generated gate outputs.

The waiver track is the next high-value maturity gap. Today A3 can say "a waiver is required and here are the required fields." It cannot yet prove "this exact person, with this role, signed this exact risk acceptance, for this exact manifest hash, until this expiry, with this follow-up issue." That proof chain is what enterprise buyers pay for.

Narrow maturity read:

| Dimension | Current read | Why |
|---|---:|---|
| Waiver policy shape | 7/10 | Required fields, exceptional-only blocked-release policy, one-day expiry guidance, blocked checks, and follow-up issue requirement already exist. |
| Local waiver validation | 2/10 | No persisted waiver record or CLI validator is visible yet. |
| Signed approval | 2/10 | Reviewer lanes exist, but no signed approval object or reviewed manifest hash binding. |
| Reviewer identity / role | 3/10 | Required approver roles are listed, but identities are not authenticated or authorized. |
| Expiry enforcement | 3/10 | `expiry_max_days` exists, but expired waiver blocking is not enforced. |
| Immutable audit chain | 5/10 | Input hashes and generated artifact hashes exist, but no root hash, signature, append-only event log, or retention store. |
| Required-check readiness | 5.5/10 | Check payload and CLI exit hints exist; live branch-protected required check is still missing. |
| Self-host compliance readiness | 3.5/10 | Local-first and redacted evidence are strong starts; persistence, RBAC, retention, and deletion policy are missing. |

## Why Waiver Matters Commercially

Waiver is not a side feature. For enterprise customers it is the difference between a useful eval report and a release governance product.

1. Buyers need a controlled exception path. A hard gate that only blocks can be politically hard to adopt, while a gate with signed, expiring waivers can fit real release pressure without becoming theater.
2. Security and compliance teams need risk acceptance evidence. They will ask who accepted the risk, why, for how long, and against which evidence bundle.
3. Engineering managers need accountability. A waiver turns "we know it failed but shipped anyway" into an owned decision with a follow-up issue and expiry.
4. Procurement needs defensible controls. A signed waiver workflow makes A3 easier to justify as audit infrastructure, not just a dashboard.
5. Self-host customers need local governance. Regulated teams often cannot send traces or approvals to SaaS, so file-backed or DB-backed waiver records with retention policy are a strong paid-tier wedge.
6. GitHub required checks need an exception model. If A3 becomes merge-blocking, customers need a governed way to override in emergencies.
7. Expiry creates recurring value. A3 can monitor expired waivers, reopen risk, and force remediation evidence, which makes it operationally sticky.
8. Signed approval raises ACV. Approval history, RBAC, retention, immutable bundles, and compliance exports are enterprise-grade features buyers expect in higher-priced plans.

## Current A3 Waiver Evidence

What exists now:

- Release Gate can produce `block_release`, `needs_review`, or `approve_release`.
- The blocked mock fixture records `blocks_merge: true`, `github_check.conclusion: failure`, risk score 100, and failed checks including pass rate, critical failures, policy failures, and missing required tool coverage.
- `release_workflow.waiver_policy` exists in the gate output.
- Blocked releases are exceptional-only, with `expiry_max_days: 1`.
- Required waiver fields include `waiver_owner`, `business_reason`, `risk_acceptance`, `expiry_date`, and `follow_up_issue`.
- Waiver guidance says blocked releases require explicit executive exception and one-day expiry.
- Reviewer workflow lists required approvers and review lanes such as Release owner, Safety reviewer, Runner/tooling owner, and A3 triage owner.
- Audit bundle metadata exists, including JSON report, Markdown report, print/PDF packet, case evidence, redacted fixtures, and screenshots policy.
- Gate CLI hashes input artifacts in `audit_manifest`.
- Generated artifact manifest hashes JSON report, Markdown report, GitHub check payload, and PR comment Markdown.
- Redaction policy forbids API keys, cookies, tokens, emails, and live signed media URLs in exported artifacts.

What this means commercially:

A3 can already tell a buyer: "This release is blocked, here are the failed controls, here are the roles that must review it, and here is the waiver policy shape." That is strong pilot material.

## What Is Still Missing

The missing layer is enforceable governance.

| Gap | Current state | Enterprise requirement |
|---|---|---|
| Persisted waiver record | Policy fields are emitted, but no `a3.waiver.v1` record is stored. | A durable waiver object with id, scope, owner, reason, risk acceptance, expiry, follow-up issue, blocked checks, case ids, and status. |
| Local validation | CLI reports waiver policy, but does not validate an input waiver file. | `releasefoundry gate --waiver waiver.json --strict-exit` should pass/fail based on scope, expiry, role, and issue validity. |
| Signed approval | No approval record binds a reviewer to the evidence. | `a3.approval.v1` with signer identity, role, timestamp, decision, reviewed manifest hash, and optional signature. |
| Reviewer identity | Roles are labels. | GitHub actor, OIDC subject, SSO user id, or local dev identity bound to role policy. |
| Reviewer authorization | No role validation. | Safety waiver must be approved by Safety reviewer or executive approver, not just release author. |
| Separation of duties | Not visible. | Release author cannot self-approve high-risk safety waivers. |
| Expiry enforcement | `expiry_max_days` is guidance. | Expired or over-long waivers fail the gate. |
| Follow-up issue validation | Field is required, but not checked. | Issue id/URL, due date, owner, and open state should be validated or at least locally proven. |
| Immutable bundle | Artifacts are hashed, but bundle is not sealed. | Manifest root hash, signature, append-only event log, bundle id, and verification command. |
| Required GitHub check | Payload exists, but no live branch-protected check. | Live required check or Actions enforcement with branch protection and persisted check-run id. |
| Compliance retention | No self-host retention policy. | Retention days, legal hold, deletion audit, WORM/object-lock option, backup/restore contract. |
| Waiver lifecycle | No statuses. | requested, approved, rejected, expired, revoked, superseded, remediated. |

## Next Growth Points

These are the highest-value next steps. They intentionally cover signed approval, expiry, reviewer role, follow-up issue, immutable audit, GitHub required check, compliance, and self-host retention.

| ID | Growth point | Why it matters | Lane |
|---|---|---|---|
| W-1 | Add `a3.waiver.v1` schema. | Converts policy guidance into a durable governance artifact. | Waiver |
| W-2 | Add file-backed waiver fixture under a safe redacted path. | Enables local validation without backend dependency. | Waiver |
| W-3 | Require waiver scope: repo, release version, environment, head SHA, run id, blocked checks, and case ids. | Prevents broad reusable waivers. | Waiver |
| W-4 | Validate waiver expiry date and max days. | Stops expired or over-long exceptions from passing CI. | Expiry |
| W-5 | Validate waiver status: requested, approved, rejected, expired, revoked, superseded. | Supports real lifecycle governance. | Waiver |
| W-6 | Add waiver revocation and supersession fields. | Handles new evidence, rollback, and re-review. | Waiver |
| W-7 | Hash waiver record into generated artifact manifest or bundle manifest. | Proves the approved exception was part of the release packet. | Immutable audit |
| A-1 | Add `a3.approval.v1` schema. | Establishes who approved or rejected the release. | Signed approval |
| A-2 | Bind approval to reviewed generated artifact manifest hash. | Proves exactly what evidence was reviewed. | Signed approval |
| A-3 | Include signer identity, signer role, timestamp, decision, reason, and policy version. | Gives auditors durable approval fields. | Signed approval |
| A-4 | Add optional local signature or Sigstore/cosign-friendly signature fields. | Raises non-repudiation for enterprise customers. | Signed approval |
| A-5 | Add approval chain for multiple required approvers. | Matches blocked releases that require release, safety, tooling, and executive review. | Signed approval |
| R-1 | Add reviewer role policy schema. | Turns lanes into enforceable authorization. | Reviewer role |
| R-2 | Map roles to GitHub teams, OIDC claims, SSO groups, or local file-backed users. | Supports both SaaS CI and self-host pilots. | Reviewer role |
| R-3 | Enforce separation of duties. | Prevents release author from self-approving high-risk waivers. | Reviewer role |
| R-4 | Add reviewer assignment state and SLA. | Makes review workflow operational instead of descriptive. | Reviewer role |
| F-1 | Validate `follow_up_issue` field shape. | Ensures risk acceptance leads to remediation. | Follow-up issue |
| F-2 | Add follow-up due date and owner. | Makes waiver accountability time-bound. | Follow-up issue |
| F-3 | Add dry-run issue validator with no live GitHub call. | Keeps safety boundary while proving issue metadata shape. | Follow-up issue |
| F-4 | Later add live issue-state validation behind explicit dry-run/live boundary. | Ensures closed or missing follow-up issues cannot justify waiver. | Follow-up issue |
| I-1 | Add bundle id and manifest root hash over inputs, generated outputs, waiver, approvals, and redaction log. | Creates one tamper-evident release evidence handle. | Immutable audit |
| I-2 | Add `releasefoundry gate verify --manifest ...`. | Lets customers verify bundles after export or retention. | Immutable audit |
| I-3 | Add append-only audit events: generated, reviewed, waived, approved, expired, revoked, verified. | Creates chain-of-custody. | Immutable audit |
| I-4 | Package immutable bundle as zip/tar with manifest, reports, check payload, PR comment, waiver, approvals, and replay pack. | Makes a customer-deliverable audit artifact. | Immutable audit |
| G-1 | Add live GitHub Check writer behind explicit dry-run/live flag. | Turns "blocks merge" into actual merge control. | GitHub required check |
| G-2 | Add branch-protection / required-check policy fixture. | Documents and validates the operational control. | GitHub required check |
| G-3 | Persist check-run id by repo, PR, head SHA, and A3 run id. | Enables update mode and avoids duplicate check noise. | GitHub required check |
| G-4 | Include GitHub workflow run id, attempt, actor, and head SHA in audit manifest. | Connects CI provenance to audit evidence. | GitHub required check |
| C-1 | Add compliance policy version to gate, waiver, approval, and bundle. | Makes audits reproducible across policy changes. | Compliance |
| C-2 | Add redaction finding log with field paths and reasons. | Proves sensitive values were scrubbed deliberately. | Compliance |
| C-3 | Add fail-closed export mode when suspicious secrets remain. | Prevents unsafe audit bundles. | Compliance |
| C-4 | Add management sign-off packet showing gate result, waiver status, approvers, expiry, and bundle hash. | Creates executive-ready evidence. | Compliance |
| S-1 | Define self-host retention policy schema. | Gives regulated customers a deployment contract. | Self-host retention |
| S-2 | Add retention metadata to every bundle: storage backend, retention days, legal hold, delete-after date. | Makes evidence lifecycle auditable. | Self-host retention |
| S-3 | Add local SQLite/Postgres persistence for waivers, approvals, manifests, and audit events. | Required for durable self-host workflow. | Self-host retention |
| S-4 | Add WORM/object-lock compatible storage option for bundle archives. | Supports higher-compliance buyers. | Self-host retention |
| S-5 | Add backup/restore and deletion audit docs. | Makes self-host operations credible. | Self-host retention |
| S-6 | Add RBAC roles: admin, release owner, safety reviewer, auditor, viewer. | Controls who can approve, waive, verify, retain, or delete. | Self-host retention |

## Parallel Execution

Several workstreams can move at the same time. Do not block everything on live GitHub.

| Lane | Can start now? | First useful deliverable | Can run in parallel with |
|---|---|---|---|
| Waiver validation | Yes | `a3.waiver.v1` fixture plus local expiry/scope validator. | Signed approval, reviewer role, immutable manifest |
| Signed approval | Yes | `a3.approval.v1` schema binding signer to generated manifest hash. | Waiver validation, compliance policy, self-host persistence design |
| Reviewer role policy | Yes | File-backed role policy for local/dev plus GitHub/OIDC mapping fields. | Waiver and approval schemas |
| Follow-up issue | Yes | Local shape validator for issue id/URL, owner, due date. | Waiver validation and PR comment enhancements |
| Immutable audit bundle | Yes | Root hash and verify command over existing input/output hashes. | Waiver, approval, redaction log |
| GitHub required check | Partly | Branch-protection policy fixture and dry-run/live boundary. | Waiver schemas and immutable bundle |
| Compliance hardening | Yes | Policy version fields, redaction finding log, fail-closed export test. | All lanes |
| Self-host retention | Yes for design | Retention schema and storage contract. | Persistence, RBAC, immutable bundle |

Suggested parallel sprint:

1. One engineer adds local `a3.waiver.v1` validation with expiry and scope checks.
2. One engineer adds `a3.approval.v1` and reviewer role policy fixtures.
3. One engineer adds manifest root hash and `releasefoundry gate verify`.
4. One engineer adds branch-protection policy fixture and keeps GitHub live calls behind an explicit future boundary.
5. One engineer drafts self-host retention schema and storage lifecycle docs.

## Impact If Main Agent Implements Local Waiver Validation

If the main agent implements local waiver validation now, A3's commercial maturity improves in a very specific place: it moves from policy description to enforceable release governance.

Expected uplift:

| Area | Before local validation | After local validation |
|---|---|---|
| Waiver governance | A3 says a waiver is required. | A3 can accept/reject a waiver file based on scope, expiry, required fields, and blocked checks. |
| CI credibility | Blocked release has exit hint and policy text. | Strict CI mode can fail if waiver is missing, expired, or mismatched. |
| Buyer trust | Waiver is a promise in report output. | Waiver becomes a testable artifact in the release packet. |
| Compliance posture | Auditors see required fields. | Auditors can see validation result, policy version, and why a waiver passed or failed. |
| Signed approval path | Approvals are future work. | Approval records can bind to the same waiver id and manifest hash. |
| Required-check readiness | GitHub check can report failure. | Future required check can distinguish "blocked", "valid temporary waiver", and "invalid waiver". |
| Self-host story | Local artifacts exist. | Local regulated pilots can run waiver governance without SaaS or live GitHub. |

Commercial maturity estimate after local waiver validation:

- Waiver governance: 4/10 to about 6.5/10.
- Required-check readiness: 5.5/10 to about 6.5/10.
- Compliance posture: 5.5/10 to about 6.5/10.
- Enterprise paid-pilot readiness: 6.5/10 to about 7/10.
- Self-host compliance readiness: 3.5/10 to about 4.5/10.

The highest-value local validator behavior:

- Fail if waiver is absent when `waiver_policy.required` is true.
- Fail if blocked release waiver is not explicitly marked executive/exceptional.
- Fail if `expiry_date` is missing, already expired, or beyond `expiry_max_days`.
- Fail if waiver scope does not match release version, environment, run id, head SHA, blocked checks, or case ids.
- Fail if required fields are blank.
- Warn or fail if `follow_up_issue` is missing, malformed, or lacks owner/due date.
- Fail if approver role is not in the required approver set.
- Fail if release author and approver are the same for high-risk waivers.
- Emit a waiver validation result into JSON, Markdown, GitHub check output, PR comment, and generated artifact manifest.

## Final Auditor Call

A3's waiver work is the best next commercial upgrade because it sits exactly where enterprise buyers feel pain: they need risk exceptions, but they cannot tolerate invisible, permanent, unaudited bypasses.

The current A3 already has the right nouns: Release Gate, PR Gate, waiver policy, reviewer lanes, audit bundle, input hashes, generated artifact hashes, redaction policy, and incident replay seeds. The next step is to make waiver and approval records enforceable, scoped, expiring, reviewable, and tied to immutable evidence.

Best next sequence:

1. Add local `a3.waiver.v1` validation.
2. Bind waiver to generated artifact manifest hash and blocked checks.
3. Add `a3.approval.v1` signed approval records.
4. Add reviewer role and separation-of-duties policy.
5. Add follow-up issue validation.
6. Add manifest root hash and verify command.
7. Add self-host retention schema and audit event log.
8. Wire live GitHub required check after auth and branch-protection policy are approved.

What this audit did not do:

- Did not modify `services/report/a3_gate_cli.mjs`.
- Did not modify `tests/a3/a3_gate_cli.test.mjs`.
- Did not modify `fixtures/a3/p3`.
- Did not modify `docs/a3/worklog.md`.
- Did not modify `docs/a3/p3_worklog.md`.
- Did not modify `docs/a3/acceptance_checklist.md`.
- Did not revert or overwrite any main-agent changes.
- Did not call live ReleaseFoundry or GitHub APIs.
