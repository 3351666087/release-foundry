# A3 Artifact Manifest / Waiver / Signed Approval Growth Audit - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Evidence Auditor.

Focus: artifact manifest, waiver, signed approval, and enterprise audit bundle maturity.

Safety boundary followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed URLs.
- Did not call the live Ashr API.
- Did not call the live GitHub API.
- Wrote only this file: `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`.

Evidence reviewed:

- `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`
- `docs/a3/p3_gate_cli_growth_2026_07_07.md`
- `docs/a3/p3_github_dry_run_integration_2026_07_07.md`
- `docs/a3/p3_github_action_workflow_example.yml`
- `docs/a3/p3_growth_auditor_2026_07_07.md`
- `services/report/report_builder.mjs`
- `services/report/a3_gate_cli.mjs`
- `services/report/a3_github_integration.mjs`
- `tests/a3/report_builder.test.mjs`
- `tests/a3/a3_gate_cli.test.mjs`
- `tests/a3/a3_github_integration.test.mjs`
- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- `fixtures/a3/p3/a3_github_check_create_request.redacted.json`
- `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json`

## Executive Verdict

A3 has the start of a sellable enterprise release-control story: Release Gate, PR Gate, Gate CLI, hashed input artifacts, dry-run GitHub Check payloads, PR comment plans, waiver policy, reviewer lanes, audit bundle metadata, and incident replay case lists.

But the current audit package is still not enough for compliance-grade customer approval or executive sign-off. The gap is no longer "can A3 explain a risky release?" It can. The gap is "can A3 prove exactly what evidence was reviewed, who approved it, when the approval expires, and that no artifact changed afterward?" Today, that proof chain is incomplete.

Commercial maturity score for this narrow audit-bundle track:

| Dimension | Score | Auditor read |
|---|---:|---|
| Release-control narrative | 8/10 | Clear block/review/approve gate with GitHub-shaped outputs. |
| Artifact integrity | 5.5/10 | CLI hashes input files, but generated exports are not fully hashed yet. |
| Waiver governance | 4/10 | Strong policy fields exist, but no persisted signed waiver record or expiry enforcement. |
| Reviewer identity | 3.5/10 | Reviewer lanes exist as roles, not authenticated people. |
| Immutable enterprise audit bundle | 3/10 | Bundle contents are described, but not sealed, signed, retained, or replay-verifiable. |
| Required-check readiness | 5/10 | Dry-run request shapes and workflow example exist; live branch-protected check does not. |

## 1. Where The Current A3 Gate Capabilities Can Sell

### Enterprise PR Gate For Agent Releases

Current assets:

- Release Gate decision: approve / needs review / block release.
- GitHub Check Run payload shape named `Ashr++ Release Gate`.
- PR comment Markdown.
- CLI output that can run in CI.
- Dry-run GitHub request builder.
- GitHub Actions example.

Who buys:

- Platform engineering teams responsible for AI-agent release controls.
- Agent teams shipping customer-facing support, refund, claims, billing, or ops agents.
- Engineering managers who want agent eval results in the same place as code review.

Buyer promise:

> "Every PR that changes an agent can produce a merge-blocking release gate with top-risk cases, failed checks, reviewer lanes, and audit artifacts."

What is sellable now:

- Paid pilot as a local or CI dry-run gate.
- Advisory implementation for GitHub Actions.
- Release-intelligence dashboard for review meetings.

What is not yet sellable as final enterprise control:

- A live GitHub required check backed by branch protection and durable check-run state.

### Audit Bundle For AI Governance / Security Review

Current assets:

- `release_workflow.audit_bundle` with required artifacts: JSON report, Markdown report, print/PDF packet, case evidence, redacted fixtures, optional screenshots.
- CLI `audit_manifest` with SHA-256 hashes for input artifacts.
- Redaction policy that forbids keys, cookies, tokens, emails, and live signed media URLs in exported artifacts.

Who buys:

- AI governance teams.
- Security review teams.
- Internal audit / compliance teams.
- Procurement teams evaluating agent release risk.

Buyer promise:

> "A3 can package an agent release decision into an evidence bundle that an auditor can inspect without touching live secrets."

What is sellable now:

- Compliance pilot artifact pack.
- Evidence review workflow for regulated agent changes.
- Pre-production release review export.

What is not yet enough:

- The bundle is not sealed with generated export hashes, a root hash, signed approval, retention policy, or immutable storage proof.

### Incident Replay / RCA Starter Pack

Current assets:

- Top-risk case list.
- `incident_replay.case_ids`.
- Failed-cases-first replay mode.
- Tool-call diff and judge evidence in the report pipeline.

Who buys:

- SRE / incident response teams.
- Support quality teams.
- Agent owners who need to reproduce customer-impacting failures.

Buyer promise:

> "When a release gate fails, A3 can identify the highest-risk failures and start an incident replay packet."

What is sellable now:

- RCA starter pack and reviewer workflow.
- Failed-case triage for pilots.

What is not yet enough:

- The replay evidence is a list of cases, not an executable replay bundle with input hashes, trace hashes, output hashes, and reproduced/fixed/new status.

### Self-Host Compliance Edition

Current assets:

- Local dashboard.
- Local Node CLI.
- Redacted fixture model.
- No-live-API dry-run GitHub integration.
- No-live-signed-media policy.

Who buys:

- Regulated enterprises that cannot send traces to a SaaS evaluator.
- Financial services, healthcare, insurance, public sector, and high-sensitivity support operations.

Buyer promise:

> "You can run release gates and inspect evidence locally without exposing live keys or signed media URLs."

What is sellable now:

- Early design partner conversation.
- Local prototype deployment.

What is not yet enough:

- No backend persistence, installer, RBAC/SSO, retention controls, backup/restore, or immutable bundle storage.

## 2. What The Audit Package Still Lacks

### Generated Export Hashes

Current state:

- CLI hashes input artifacts: runs, grades, coverage, thresholds, and optional media signed URL coverage.
- CLI can output JSON, Markdown, GitHub Check payload, and PR comment Markdown.

Gap:

- The generated outputs themselves are not yet fully represented as hashed artifacts in the manifest.

Why this matters:

- A manager cannot confidently sign `a3-dashboard-report.pdf` if the underlying JSON, Markdown, PR comment, and GitHub Check payload can be regenerated or edited without a recorded hash.
- An auditor needs to know whether the PDF, PR comment, and JSON came from the same release decision.

### Signed Approval Records

Current state:

- `reviewer_workflow` lists required approver roles and next actions.
- `waiver_policy` lists required waiver fields.

Gap:

- There is no signed approval object with signer identity, timestamp, gate decision, reviewed artifact hashes, and approval/denial result.

Why this matters:

- "Safety reviewer" is a lane, not a person.
- Compliance needs the identity of the approver and the exact evidence they approved.
- Executive sign-off needs non-repudiation or at least authenticated provenance.

### Waiver Expiry Enforcement

Current state:

- Blocked releases require exceptional waiver guidance.
- Blocked waiver expiry max is one day.
- Required fields include owner, reason, risk acceptance, expiry date, and follow-up issue.

Gap:

- Waivers are policy output, not persisted records.
- Expiry is described but not enforced by CLI/CI.
- No follow-up issue validation exists.

Why this matters:

- A waiver that never expires is a hidden permanent policy bypass.
- A buyer's auditor will ask whether expired waivers can still pass the release gate.
- A manager needs confidence that risk acceptance has a time limit and an accountable owner.

### Reviewer Identity And Authorization

Current state:

- A3 has reviewer lanes: release owner, safety reviewer, runner/tooling owner, judge/evidence/A3 triage owner.

Gap:

- No authenticated reviewer identity.
- No SSO/OIDC/GitHub actor binding.
- No reviewer role policy or separation-of-duties check.

Why this matters:

- Enterprise approvals often require "who approved what" and "was this person allowed to approve it?"
- For high-risk releases, the release author should not be able to self-approve a safety waiver.

### Immutable Audit Bundle

Current state:

- A3 names the audit bundle artifacts and redaction policy.
- CLI has input artifact hashes.

Gap:

- No bundle id, root hash, signature, immutable storage location, retention class, or verification command.

Why this matters:

- Without a sealed bundle, evidence can drift after approval.
- Audit review needs chain-of-custody: source evidence, generated exports, approval, waiver, replay evidence, and final bundle integrity.

### Self-Host Retention

Current state:

- Local-first execution exists.

Gap:

- No self-host retention policy: how long bundles are kept, where they are stored, who can delete them, and how deletion is logged.

Why this matters:

- Regulated customers need data retention, legal hold, deletion, and backup controls.
- A local CLI artifact directory is not an enterprise retention model.

### GitHub Required Check

Current state:

- GitHub Check request is dry-run only.
- GitHub Actions example uploads artifacts and can enforce local gate result by exit code.

Gap:

- No live GitHub writer.
- No branch protection configuration.
- No persisted check-run id.
- No required-check policy fixture.

Why this matters:

- "Blocks merge: yes" is commercially powerful only when GitHub actually blocks merge.
- Without branch protection, the check is advisory, not a control.

### Incident Replay Evidence

Current state:

- Top-risk case ids are included.
- Replay mode is described as failed-cases-first.

Gap:

- No replay command, replay input fixture hash, replay result hash, baseline/current diff hash, or reproduced/fixed/flaky status.

Why this matters:

- Incident review needs reproducibility, not just a pointer to failed cases.
- An executive can sign a mitigation only if the replay evidence proves the failure was reproduced or fixed.

## 3. Next Growth Points

These are the highest-value growth points for artifact manifest, waiver, signed approval, and enterprise audit bundle maturity.

| ID | Growth point | Why it matters | Suggested lane |
|---|---|---|---|
| AM-1 | Hash every generated JSON export. | Proves machine-readable report integrity. | Artifact manifest |
| AM-2 | Hash every generated Markdown export. | Proves PR/release note text did not drift after review. | Artifact manifest |
| AM-3 | Hash generated PDF / print packet output. | Makes executive sign-off packet tamper-evident. | Artifact manifest |
| AM-4 | Hash generated GitHub Check payload. | Connects CI status to reviewed evidence. | Artifact manifest |
| AM-5 | Hash generated PR comment Markdown. | Proves reviewer-facing PR summary matches the gate. | Artifact manifest |
| AM-6 | Hash generated screenshots and visual QA artifacts. | Lets auditors verify dashboard evidence snapshots. | Artifact manifest |
| AM-7 | Add `generated_artifacts[]` to `a3.gate_cli.audit_manifest.v1`. | Separates source inputs from generated outputs cleanly. | Artifact manifest |
| AM-8 | Add manifest root hash over source and generated artifacts. | Creates one integrity handle for the whole release package. | Artifact manifest |
| AM-9 | Add bundle id, release version, environment, repo, head SHA, and generated_at to the manifest. | Makes the bundle uniquely traceable to one release decision. | Artifact manifest |
| AM-10 | Add `ashr gate verify --manifest ...` command. | Lets customers verify an audit bundle after download or retention. | Artifact manifest |
| WA-1 | Persist waiver records as `a3.waiver.v1`. | Moves from policy guidance to actual governance evidence. | Waiver |
| WA-2 | Validate waiver expiry in CLI strict mode. | Prevents expired waivers from passing CI. | Waiver |
| WA-3 | Require waiver scope: repo, release version, environment, head SHA, blocked checks, and case ids. | Prevents broad reusable waivers. | Waiver |
| WA-4 | Validate follow-up issue URL/id and due date. | Connects accepted risk to remediation. | Waiver |
| WA-5 | Add waiver revocation and superseded status. | Handles rollback, re-review, and changed evidence. | Waiver |
| WA-6 | Hash waiver record into the audit bundle. | Proves the accepted-risk document was part of sign-off. | Waiver |
| SA-1 | Persist signed approval records as `a3.approval.v1`. | Establishes who approved or rejected the release. | Signed approval |
| SA-2 | Bind approval to reviewer identity from GitHub actor, OIDC, SSO, or file-backed dev identity. | Turns role lanes into accountable people. | Signed approval |
| SA-3 | Include reviewed manifest root hash in every approval. | Proves what evidence the reviewer saw. | Signed approval |
| SA-4 | Add separation-of-duties policy. | Prevents release author from self-approving safety or executive waivers. | Signed approval |
| SA-5 | Add approval timestamp, expiry, policy version, and decision reason. | Gives auditors durable governance fields. | Signed approval |
| SA-6 | Add optional Sigstore/cosign or local key signature for approvals. | Raises non-repudiation for enterprise customers. | Signed approval |
| IM-1 | Package immutable audit bundle as zip/tar with manifest, generated exports, approvals, waivers, redaction log, and replay pack. | Creates one customer-deliverable artifact. | Immutable bundle |
| IM-2 | Add bundle root hash and optional signature. | Makes the package tamper-evident. | Immutable bundle |
| IM-3 | Add retention metadata: storage backend, retention days, legal hold flag, deletion policy. | Supports regulated self-host operations. | Retention |
| IM-4 | Add append-only chain-of-custody events. | Shows creation, review, approval, waiver, export, retention, and verification actions. | Immutable bundle |
| IM-5 | Add WORM/object-lock storage option for self-host bundle archives. | Makes enterprise retention credible. | Retention |
| GH-1 | Add live GitHub Check writer behind explicit dry-run/live flag. | Turns advisory artifacts into operational merge control. | Required check |
| GH-2 | Add required-check / branch-protection policy fixture. | Documents and validates merge-blocking setup. | Required check |
| GH-3 | Persist check-run id by repo, PR, head SHA, and A3 run id. | Enables updates without duplicate checks. | Required check |
| GH-4 | Include GitHub run id, workflow name, attempt, actor, and head SHA in the audit manifest. | Connects CI provenance to the bundle. | Required check |
| IR-1 | Build incident replay pack with case input hashes, trace hashes, expected output hashes, and replay command. | Makes failures reproducible. | Incident replay |
| IR-2 | Add replay result hash and status: reproduced, fixed, new, flaky. | Turns triage into RCA evidence. | Incident replay |
| IR-3 | Add baseline/current regression diff hash. | Proves whether the release improved or regressed. | Incident replay |
| IR-4 | Include replay evidence in PR comment and audit bundle. | Lets reviewers inspect incident risk without hunting files. | Incident replay |
| RD-1 | Add redaction finding log with field paths and redaction reasons. | Shows exactly what was scrubbed. | Redaction |
| RD-2 | Add fail-closed export mode when suspicious secrets remain. | Prevents unsafe audit bundles. | Redaction |
| RD-3 | Hash redaction log into manifest. | Proves safety review was part of the exported bundle. | Redaction |
| SH-1 | Define self-host retention policy schema. | Gives regulated customers a deployment contract. | Self-host |
| SH-2 | Add local SQLite/Postgres persistence for manifests, waivers, approvals, and bundle events. | Required for durable audit workflow. | Self-host |
| SH-3 | Add RBAC roles: admin, release owner, safety reviewer, auditor, viewer. | Makes approvals enforceable. | Self-host |
| SH-4 | Add backup/restore and bundle verification docs. | Makes self-host operations credible. | Self-host |
| GR-1 | Export signed executive approval packet from reviewed manifest root hash. | Gives management a document worth signing. | Executive sign-off |
| GR-2 | Add management summary showing gate result, waiver status, approvers, expiry, and bundle hash. | Makes sign-off fast and defensible. | Executive sign-off |

## 4. Parallel Execution Plan

These workstreams can move in parallel because they touch different layers.

| Lane | Can start now? | First useful deliverable | Parallel with |
|---|---|---|---|
| Artifact manifest | Yes | Hash generated JSON/Markdown/Check/PR comment outputs and add `generated_artifacts[]`. | Waiver, signed approval schema, GitHub policy docs, replay pack design |
| Waiver governance | Yes | File-backed `a3.waiver.v1` fixture plus expiry validator. | Artifact manifest, reviewer identity design, incident replay |
| Signed approval | Yes | `a3.approval.v1` schema with reviewed manifest root hash and signer fields. | Waiver, RBAC/SSO design, generated manifest |
| Immutable bundle | Mostly yes | Bundle id/root hash and zip/tar export command. | Generated artifact hashes, redaction log |
| GitHub required check | Partly | Branch-protection policy fixture and dry-run/live CLI boundary. | Manifest work and waiver schema |
| Incident replay evidence | Yes | Replay pack fixture from current top-risk cases. | Manifest work and PR comment enhancement |
| Self-host retention | Yes for design | Retention schema and storage contract. | Persistence, approval, immutable bundle |
| Redaction hardening | Yes | Redaction finding log and fail-closed test fixture. | Manifest and immutable bundle |

Do not block everything on live GitHub. The fastest commercial lift is:

1. Hash generated exports.
2. Add manifest root hash.
3. Add signed approval and waiver schemas that reference that root hash.
4. Add expiry validation.
5. Package immutable audit bundle.
6. Then wire live GitHub required check and self-host persistence around the same contract.

## 5. Commercial Impact If Generated Artifact Manifest Lands This Round

If the main agent implements a generated artifact manifest, it raises commercial maturity in five specific ways.

### From Input Integrity To Output Integrity

Current CLI manifest proves the source files used by the gate. Generated artifact manifest would prove the files delivered to humans and CI:

- `ashr-gate.json`
- `ashr-gate.md`
- `ashr-check.json`
- `ashr-pr-comment.md`
- future print/PDF export
- screenshots or dashboard export artifacts

That closes the gap between "we evaluated these inputs" and "this is exactly the report/check/comment the reviewer saw."

### From Local Prototype To Audit Bundle Primitive

An enterprise audit bundle needs both source evidence and generated evidence. Generated artifact hashes would make A3's audit bundle much closer to a real evidence packet because the bundle could say:

- These inputs created the decision.
- These generated outputs represented the decision.
- These hashes identify the exact reviewed artifacts.
- The reviewer approval can bind to this manifest root hash.

### From Manager-Friendly PDF To Signable Packet

Without generated export hashes, a PDF or Markdown summary is only a convenient view. With generated export hashes, it becomes a controlled sign-off artifact.

This matters for executives because approval can reference:

- release version
- environment
- gate decision
- failed checks
- waiver requirement
- artifact hashes
- manifest root hash
- expiry and follow-up issue

That is the difference between "looks convincing" and "can be attached to an approval record."

### From Dry-Run GitHub To Required-Check Foundation

GitHub dry-run request shapes are already present. Generated artifact hashes would let a future live GitHub check include or link to the exact hash of:

- the check payload
- the PR comment
- the full gate JSON
- the audit manifest

That makes a required check easier to defend because the GitHub status is not a floating summary; it is backed by a tamper-evident bundle.

### From Compliance Theater To Evidence Chain

The current audit package has strong policy language. Generated artifact manifest would turn part of that policy into evidence.

Commercial maturity improvement:

- Artifact integrity: 5.5/10 to about 7/10.
- Compliance posture: 5.5/10 to about 6.5/10.
- Executive sign-off readiness: 4/10 to about 5.5/10.
- Enterprise pilot readiness: 6.5/10 to about 7/10.

Remaining blockers after generated artifact manifest:

- No signed reviewer approval.
- No persisted waiver with expiry enforcement.
- No authenticated reviewer identity.
- No immutable bundle storage or retention policy.
- No live GitHub required check.
- No executable incident replay evidence.

## Final Auditor Call

A3's commercial center of gravity should move from "dashboard that explains evals" to "tamper-evident release evidence package."

The current Release Gate, PR Gate, CLI, and GitHub dry-run work can already sell into paid pilots as an enterprise agent release-control workflow. The next money-grade step is generated artifact hashing, because it is the bridge from useful local output to enterprise audit evidence.

Best next sequence:

1. Generate and hash all output artifacts.
2. Add manifest root hash.
3. Add file-backed waiver and signed approval records referencing that root hash.
4. Enforce waiver expiry in strict CLI / CI mode.
5. Package immutable audit bundle with retention metadata.
6. Wire live GitHub required check once auth and branch protection are approved.

What this audit did not do:

- Did not modify `services/report/a3_gate_cli.mjs`.
- Did not modify `tests/a3/a3_gate_cli.test.mjs`.
- Did not modify `docs/a3/worklog.md`.
- Did not modify `docs/a3/p3_worklog.md`.
- Did not modify `docs/a3/acceptance_checklist.md`.
- Did not revert or overwrite any main-agent changes.
- Did not call live Ashr or GitHub APIs.
