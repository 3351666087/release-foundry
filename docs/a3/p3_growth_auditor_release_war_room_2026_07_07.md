# A3 Release War Room Growth Audit - 2026-07-07

## Audit Scope

Role: Growth-Auditor / Money-Grade Auditor for the ReleaseFoundry A3 round.

Boundaries followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed media URLs.
- Did not call live ReleaseFoundry, GitHub, or other external APIs.
- Did not edit code, tests, fixtures, worklogs, acceptance checklist, or existing docs.
- Created only this artifact: `docs/a3/p3_growth_auditor_release_war_room_2026_07_07.md`.

Evidence basis:

- A3 already has Release Gate, PR Gate, Gate CLI, GitHub dry-run request shapes, generated artifact manifest, waiver validation, approval validation, audit bundle index, bundle root hash, chain-of-custody hashes, and audit bundle verifier.
- Existing docs name "release war room panel" as a next growth point, but no dedicated Release War Room capability is implemented yet.
- Current official-demo release evidence remains blocked: dataset `884`, run `11926`, 5 cases, 2 pass, 3 fail, 40% pass rate, average score 56.4, risk score 70.

## 1. What This Round's Release War Room Capability Should Sell

The Release War Room should sell one thing clearly:

> "When an agent release is risky, A3 gives engineering, safety, and audit reviewers one command center to decide whether to block, approve, waive, replay, or escalate the release, with every decision tied to verifiable evidence."

This should not sell as another dashboard panel. It should sell as the buyer's blocked-release control room.

The commercial promise:

- Release owners see the gate decision, risk score, failed checks, thresholds, top-risk cases, and merge-block status.
- Engineers see expected-vs-actual, tool-call diffs, trace evidence, and replay candidates.
- Safety/compliance reviewers see policy failures, signed media status, redaction state, waiver status, approval status, bundle root hash, and verifier status.
- Managers see the decision packet: ship, block, exceptional waiver, required approvers, expiry, owner, follow-up issue, and audit bundle.
- Auditors get a durable evidence handle: bundle id, root hash, custody chain, and `releasefoundry gate verify --index`.

Money-grade positioning:

- Primary SKU: Enterprise Agent Release War Room.
- Buyer pain: "We cannot let unreviewed agent behavior ship through normal CI because eval failures are hard to explain and hard to audit later."
- Product answer: "A3 turns failed eval evidence into a release-control workflow with reviewer lanes, replay evidence, waiver/approval governance, and verifiable audit bundles."
- Closest current foundation: PR Gate plus audit bundle verifier.
- Main missing product surface: one operational view that joins the existing artifacts into a release incident room.

## 2. 20 Specific Next Growth Points

| ID | Growth point | Commercial or toy? | Why it matters |
|---|---|---|---|
| RWR-1 | Add a Release War Room summary model that joins `release_gate`, `release_workflow`, waiver review, approval review, audit bundle index, and verification result. | Commercial | Converts scattered artifacts into one sellable workflow object. |
| RWR-2 | Add War Room status states: `shipping`, `blocked`, `waiver_requested`, `approval_pending`, `exception_approved`, `replay_required`, `audit_failed`. | Commercial | Gives executives and CI one simple state machine. |
| RWR-3 | Add a dashboard War Room panel for the selected run/release with decision, risk score, failed checks, approvers, waiver/approval status, and root hash. | Commercial | This is the visible product buyers can understand in a demo. |
| RWR-4 | Add War Room JSON export schema `a3.release_war_room.v1`. | Commercial | Stabilizes API, CLI, dashboard, PR comment, and self-host consumers. |
| RWR-5 | Add War Room Markdown section for PR comments and management sign-off packets. | Commercial | Makes blocked-release decisions reviewable outside the dashboard. |
| RWR-6 | Add verifier status into War Room: passed, failed, warning, missing artifacts, custody broken, root hash mismatch. | Commercial | Moves audit integrity into the release decision, not a separate afterthought. |
| RWR-7 | Add replay readiness summary from top-risk cases: replay pack missing, ready, reproduced, fixed, flaky, not replayed. | Commercial | Turns "failed cases" into incident response and RCA workflow. |
| RWR-8 | Add release owner, environment, release version, repo, PR number, head SHA, and policy version to War Room context. | Commercial | Prevents evidence from being detached from the real change being released. |
| RWR-9 | Add waiver/approval timeline with timestamps, expiry, required roles, signer roles, and separation-of-duties result. | Commercial | Makes exception handling enterprise-legible. |
| RWR-10 | Add required next action: block merge, replay failed cases, request waiver, add approval, verify bundle, re-run gate, or ship. | Commercial | Reduces reviewer confusion and makes the tool operational. |
| RWR-11 | Add GitHub PR comment War Room block with current state, failed checks, top risks, bundle root hash, and verify command. | Commercial | Embeds the control room where engineers already approve changes. |
| RWR-12 | Add GitHub Check summary fields for War Room state and audit verifier result. | Commercial | Connects branch protection to evidence integrity. |
| RWR-13 | Add Slack/Jira/PagerDuty dry-run handoff payloads from War Room state. | Commercial | Useful for enterprise incident and release-management workflows. |
| RWR-14 | Add War Room redaction/DLP status and fail-closed export signal. | Commercial | Keeps sensitive release evidence from leaking through reports. |
| RWR-15 | Add War Room audit bundle completeness score: required artifacts present, optional artifacts present, stale/missing artifacts, generated outputs hashed. | Commercial | Gives audit reviewers a quick evidence-health answer. |
| RWR-16 | Add run-to-run regression summary: new failures, fixed failures, repeated failures, risk delta. | Commercial | Makes the war room more valuable than a single-run dashboard. |
| RWR-17 | Add enterprise policy fixture for War Room escalation rules by environment and severity. | Commercial | Lets customers encode production vs staging release governance. |
| RWR-18 | Add self-host storage/readiness line: local file, CI artifact, sealed archive, retained object store, or missing. | Commercial | Supports regulated teams evaluating deployment path. |
| RWR-19 | Add billing/usage meter fields for gates, verifier runs, replay packs, bundle bytes, and retained days. | Commercial | Creates a future pricing and chargeback foundation. |
| RWR-20 | Add visual polish only after the above data model exists. | Toy until data-backed | A pretty panel without joined evidence would demo well but not change buyer trust. |

## 3. Commercial vs Toy Call

Commercial now or near-term:

- War Room state model joining gate, workflow, waiver, approval, bundle, verifier, and replay evidence.
- PR comment and GitHub Check summary fed by War Room state.
- Audit bundle completeness and verifier status inside release review.
- Replay readiness and regression delta.
- Environment-aware escalation policy.
- Self-host retention status and audit evidence handle.
- Usage/billing meter for gate, replay, bundle, verifier, and storage activity.

Toy unless upgraded:

- A standalone "War Room" visual panel that only repeats current Release Gate and PR Gate text.
- Manual reviewer names without persisted identity, role binding, or signer evidence.
- Incident handoff buttons that do not include case ids, root hash, policy version, and owner.
- Replay links that are only case-id lists, not executable replay packs.
- Audit status that says "bundle exists" without verifier result and missing-artifact checks.
- Billing forecast that is hard-coded placeholder text instead of computed usage fields.
- Self-host badge without storage, retention, backup/restore, and offline verification semantics.

Auditor call: the Release War Room is commercial if it becomes the operational join layer over the existing A3 governance artifacts. It is a toy if it becomes another static dashboard section.

## 4. Enterprise / Audit / Self-Host Implications

### Enterprise

The War Room should be designed as a multi-role release decision packet:

- Release owner: accountable for release version, environment, head SHA, and final decision.
- Safety reviewer: accountable for policy/tool/media failures.
- Runner/tooling reviewer: accountable for trace completeness, missing tools, wrong arguments, and replayability.
- Judge/evaluation reviewer: accountable for scoring, calibration, derived failure class, and judge drift.
- Evidence/audit reviewer: accountable for redaction, bundle completeness, root hash, custody chain, and verifier status.
- Executive approver: accountable for exceptional approval and follow-up ownership.

Enterprise readiness requires persisted identity, role policy, expiry, branch protection, and separation of duties. Local file-backed approvals are good scaffolding but not final enterprise identity.

### Audit

The War Room must make audit evidence first-class:

- bundle id and root hash are visible in the release decision;
- verifier command and verifier result are visible;
- required and missing artifacts are explicit;
- waiver and approval records bind to the release context and eventually to the bundle root hash;
- chain-of-custody event status is visible;
- redaction policy and redaction finding log are visible;
- generated JSON, Markdown, GitHub Check, PR comment, PDF, screenshots, replay packs, and signed archive should all be hashable.

Minimum audit claim this round should target:

> "A3 can assemble a release war-room packet from local redacted evidence and show whether the blocked-release evidence bundle is complete and verifiable."

It should not yet claim cryptographic non-repudiation, durable legal retention, or live required-check enforcement.

### Self-Host

Self-host buyers will care that the War Room can run without live ReleaseFoundry, live GitHub, or SaaS callbacks.

Implications:

- War Room generation should work from local fixtures, CLI outputs, and retained bundle indexes.
- Verification should run offline.
- Paths should remain workspace-relative or bundle-relative, never local user absolute paths.
- Storage status should distinguish working-tree files, CI artifacts, sealed local archive, filesystem retention, database metadata, and object storage.
- Future packaging should include Docker Compose, filesystem storage, SQLite/Postgres metadata, S3-compatible archive backend, backup/restore verification, SSO/RBAC, and retention/legal-hold policy.

Self-host claim allowed now:

> "A3 has local, offline-verifiable release evidence primitives."

Self-host claim not allowed yet:

> "A3 is an enterprise self-host release-governance platform."

## 5. Acceptance Evidence Expected

Expected artifact evidence for this Release War Room capability:

1. `a3.release_war_room.v1` JSON fixture generated from existing blocked release evidence.
2. War Room includes release context: source, run id, dataset id when known, release version, environment, owner, repo/PR/head SHA when known, and policy versions.
3. War Room includes Release Gate decision, risk score, pass rate, failed checks, thresholds, top-risk cases, and next action.
4. War Room includes PR Gate status: GitHub check conclusion, blocks merge, PR comment availability, annotations count, and dry-run/live mode.
5. War Room includes waiver review status and approval review status when files are supplied.
6. War Room includes audit bundle id, root hash, artifact counts, completeness status, chain-of-custody status, and verifier result.
7. War Room includes replay readiness: top-risk case ids, replay pack status, and replay-before-approval requirement for blocked production releases.
8. War Room includes redaction status and a fail-closed export signal.
9. War Room includes self-host status: local-only, CI artifact, sealed archive, retained storage, or missing.
10. War Room includes usage counters for release gate, verifier run, artifact count, bundle bytes, replay case count, and retention days placeholder.
11. Markdown report contains a `## Release War Room` section with current state, next action, failed checks, waiver/approval summary, root hash, and verify command.
12. PR comment output contains a compact War Room block suitable for reviewers.
13. GitHub Check payload summary includes War Room state and verifier status.
14. Dashboard has a War Room panel, but only after JSON/Markdown data contracts exist.
15. Tests assert blocked evidence produces `blocked` or `audit_failed` state, not an ambiguous neutral state.
16. Tests assert an approved clean fixture produces `shipping` only when gate and evidence integrity both pass.
17. Tests assert missing audit bundle or failed verifier changes next action to `verify_bundle` or `fix_audit_bundle`.
18. Tests assert waiver/approval evidence does not automatically unblock a blocked release unless policy explicitly allows it.
19. Tests assert generated War Room fixtures contain no local user paths, bearer tokens, cookies, API keys, emails, or live signed media URLs.
20. Browser or static render evidence shows the War Room panel for run `11926`, including blocked state, risk score 70, failed checks, next action, and bundle/verification status.

Suggested verification commands once implemented:

```text
node --test tests/a3/a3_gate_cli.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --json --no-fail
```

## Final Auditor Call

The Release War Room is the right next commercial layer for A3, but only if it becomes the decision cockpit over the evidence chain already built in this round.

The highest-value path is:

1. Define `a3.release_war_room.v1`.
2. Join gate, PR workflow, waiver, approval, bundle, verifier, replay, redaction, and self-host status.
3. Emit JSON and Markdown before UI polish.
4. Surface the same state in PR comment, GitHub Check summary, and dashboard.
5. Keep all live integrations behind explicit dry-run/live boundaries.

This would let A3 sell a coherent enterprise story: not just "we evaluate agents," but "we operate the blocked-release room, preserve the evidence, verify the bundle, and guide the approval path."
