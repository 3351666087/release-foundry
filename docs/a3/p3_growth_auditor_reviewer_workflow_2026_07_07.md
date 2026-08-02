# A3 Reviewer Workflow Board Growth Audit - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Money-Grade Auditor.

Theme: next A3 reviewer workflow board growth slice.

Boundaries followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed media URLs.
- Did not call live ReleaseFoundry, GitHub, or other external APIs.
- Did not edit code, fixtures, worklogs, acceptance checklist, screenshots, or existing docs.
- Created only this artifact: `docs/a3/p3_growth_auditor_reviewer_workflow_2026_07_07.md`.

Evidence basis:

- A3 already has Release Gate, PR Gate, Gate CLI, waiver validation, signed approval validation, generated artifact manifest, audit bundle index and verifier direction, Release War Room direction, incident replay queue direction, and tool-call diff evidence.
- A1 evidence can support queued run state, trace completeness, observations, final responses, and tool-call evidence.
- A2 evidence can support judge result, score, pass/fail, failure class, coverage health, and regression replay signals.
- Existing A3 growth docs describe reviewer lanes, incident replay seeds, waiver/approval readiness, PR comment/check payloads, and audit bundle linkage, but the reviewer workflow board is not yet a durable first-class product object.

## Executive Verdict

The next sellable A3 slice should be the Reviewer Workflow Board:

> "A3 turns a risky agent release into an owned review board where release, safety, runner/tooling, judge/evidence, and audit reviewers can inspect A1 trace/tool-call evidence, A2 judge evidence, incident replay dispositions, waiver/approval readiness, PR Gate status, and audit bundle verification before sign-off."

This board is not just UI. The money-grade version is an operational release-control workflow. It should answer:

- Who needs to review this release?
- Which incidents must be replayed?
- What is each incident replay disposition?
- Which waiver or approval evidence is ready, missing, invalid, expired, or stale?
- Which A1 traces and tool calls prove what the agent did?
- Which A2 judge results explain why the behavior failed or passed?
- Does the PR Gate block merge, require waiver, or allow release?
- Is the audit bundle complete, hashed, and verifier-ready?

Money-grade read:

| Dimension | Current A3 direction | Reviewer Workflow Board target |
|---|---:|---:|
| Buyer clarity | 7/10 | 9/10 |
| Review actionability | 6/10 | 9/10 |
| Waiver/approval readiness | 6.5/10 | 8.5/10 |
| Incident replay usefulness | 6.5/10 | 8.5/10 |
| PR Gate linkage | 7/10 | 8.5/10 |
| Audit bundle linkage | 6.5/10 | 9/10 |
| Enterprise/self-host value | 5.5/10 | 8.5/10 |
| ACV expansion potential | 7/10 | 9/10 |

Auditor call: Reviewer Workflow Board is the clearest next A3 growth slice because it packages many already-strong primitives into one buyer-readable workflow. The board becomes the place where release risk, replay work, approvals, waivers, PR status, and audit evidence converge.

## 新增可卖能力

| Capability | What the buyer gets | Evidence anchor |
|---|---|---|
| Reviewer Workflow Board | One board for release owner, safety reviewer, runner/tooling reviewer, judge/evidence reviewer, A3 triage, audit reviewer, and executive approver. | Existing reviewer lanes plus Release War Room direction. |
| Incident replay dispositions | Every top-risk case gets a disposition such as `not_replayed`, `queued`, `reproduced`, `fixed`, `regressed`, `flaky`, `waived`, `blocked`, or `closed`. | Incident Replay Queue direction plus A1 replay evidence. |
| Waiver readiness | Board shows whether waiver evidence is missing, invalid, expired, scoped, reviewed, or exceptional-only. | Local `a3.waiver.v1` and waiver review direction. |
| Approval readiness | Board shows required signer roles, co-signers, reviewed artifact hashes, self-approval guardrail, and decision state. | Local `a3.approval.v1` and approval review direction. |
| A1 trace/tool-call evidence cards | Reviewers can see trace completeness, tool calls, arguments, final response, observations, and replay command references. | A1 queue/replay/tool-call evidence. |
| A2 judge evidence cards | Reviewers can see score, pass/fail, failure class, judge mode, coverage health, and regression replay state. | A2 judge evidence and failure-class direction. |
| PR Gate linkage | Board state feeds PR comment and GitHub Check dry-run shape: block merge, needs review, waiver required, approval pending, or release-ready. | Existing PR Gate workflow. |
| Audit bundle linkage | Board rows link to bundle artifacts, generated manifest hashes, bundle root hash, verifier status, redaction policy, and custody events. | Audit bundle index / verifier direction. |
| Management sign-off packet | Board can export a concise approval packet with gate decision, top incidents, waiver/approval status, root hash, and verify command. | Signed approval and audit bundle growth docs. |
| Self-host/offline review | Board can run from local fixtures and retained bundles without live ReleaseFoundry or GitHub calls. | Current local-only A3 contract. |

The sellable promise:

> "Before a risky agent release ships, every reviewer sees their lane, their required evidence, the incident replay disposition, and the exact audit bundle that will be retained."

## 玩具风险

The board becomes toy-like if it is only a dashboard table.

| Risk | Toy version | Money-grade requirement |
|---|---|---|
| Reviewer identity | Role labels without people. | Authenticated or file-backed reviewer identity, role binding, and separation of duties. |
| Board state | Static UI labels. | Durable `a3.review_board.v1` state generated from gate, replay, waiver, approval, and bundle evidence. |
| Incident replay | Case ids only. | Dispositions, replay command, replay result hash, owner, due time, and stale evidence detection. |
| A1 evidence | "Trace exists" text. | Trace hash, tool-call hash, final-response hash, status-history hash, and replay reference per item. |
| A2 evidence | Score copied into the UI. | Judge result id, score, failure class, judge mode, coverage, regression replay, and evidence hash. |
| Waiver/approval | Decorative readiness badge. | Validated scope, expiry, signer roles, reviewed artifact hashes, and self-approval guardrail. |
| PR Gate | Board says blocked, but CI does not know. | PR comment/check summary reflects board state and required next action. |
| Audit bundle | Link to folder. | Bundle index, root hash, verifier result, required artifact completeness, and redaction status. |
| Compliance | Manual sign-off screenshot. | Policy version, custody events, immutable retention metadata, and export-safe evidence. |
| Self-host | Works only in demo repo. | Local fixture mode, filesystem/DB storage contract, offline verifier, backup/restore story. |

Big warning: the board must not become the source of truth. It should display and summarize signed, hashed, validated evidence. If the board owns the truth, it is just a pretty risk spreadsheet.

## 付费价值

For engineering leaders:

- Converts blocked releases into assigned review work.
- Reduces long release meetings by showing owners, statuses, and next actions.
- Makes top-risk incident replay visible before approval.
- Shows whether the PR Gate is blocked by policy failure, missing replay, invalid waiver, missing approval, or incomplete bundle.

For safety/evaluation teams:

- Puts A1 trace/tool-call evidence beside A2 judge evidence.
- Forces high-risk failures to get replay dispositions before sign-off.
- Makes flaky, unreproduced, and waived failures visible instead of buried in JSON.
- Allows safety reviewer veto or escalation to be modeled.

For compliance and audit teams:

- Binds reviewer decisions to the exact artifacts they reviewed.
- Links waiver/approval readiness to audit bundle root hash and verifier state.
- Preserves a defensible chain from failed case to replay disposition to approval decision.
- Supports offline verification for retained bundles.

For platform/self-host teams:

- Keeps the workflow local-first and fixture-driven before live integrations.
- Creates a storage and retention object that can later move to SQLite/Postgres/S3-compatible backends.
- Gives customers a path to RBAC, SSO/OIDC, legal hold, and immutable archive without changing the review concept.

## 提高客单价

Reviewer Workflow Board can raise ACV because it moves A3 from "eval reporting" into "release governance."

| Packaging angle | Paid reason |
|---|---|
| Enterprise Review Board | Customers pay for controlled release decisions with assigned reviewers and evidence-backed status. |
| PR Gate Plus | Board state can become the human-readable reason behind required checks and merge blocking. |
| Incident Replay / RCA Add-on | Dispositions, replay packs, and fixed-vs-regressed proof become premium workflow. |
| Audit Bundle Pro | Verifiable bundle linkage, root hash, custody events, and retained proof become compliance value. |
| Self-Host Compliance Edition | Offline board, local storage, RBAC, retention policy, and verifier support regulated buyers. |
| Executive Sign-Off Packet | Managers pay for a concise release approval packet that legal/security can defend later. |
| Usage Governance | Charge by releases reviewed, replay items, retained bundle bytes, verifier runs, reviewer seats, and retention days. |

The strongest monetization line:

> "A3 is not just telling you the agent failed. It is running the release review workflow that decides whether the agent is allowed to ship."

## 降低上线风险

The Reviewer Workflow Board lowers launch risk by making missing evidence visible before release.

| Launch risk | Board control |
|---|---|
| Release ships with unreplayed top-risk failures | High-risk incident replay items stay `not_replayed` or `blocked`, forcing PR Gate review or exceptional waiver. |
| Waiver bypasses remediation | Waiver readiness requires scope, expiry, failed-check coverage, follow-up issue, and reviewed artifacts. |
| Approval signs the wrong evidence | Approval readiness binds reviewer decision to generated manifest or bundle root hash. |
| Tool-call regression is missed | A1 tool-call evidence appears on each relevant incident card. |
| Judge finding is ignored | A2 judge evidence and failure class appear beside the release decision. |
| Reviewer confusion causes slow launch | Board assigns lanes, owners, next actions, and SLA by severity. |
| Audit bundle is incomplete after release | Bundle completeness and verifier status are visible before sign-off. |
| Stale evidence is reused | Board binds evidence to run id, release version, environment, head SHA, dataset id, and policy version. |
| Unsafe media leaks | Media review stays metadata-only until redaction and signed URL safety are proven. |
| Emergency release has no accountability | Exceptional waiver and approval show who accepted risk, why, until when, and with what follow-up. |

## Enterprise / Self-Host / Audit / Compliance Support

Enterprise support needs:

- reviewer lanes mapped to release owner, safety reviewer, runner/tooling reviewer, judge/evidence reviewer, A3 triage, audit reviewer, and executive approver;
- reviewer identity source: local file-backed identity now, GitHub actor/OIDC/SSO later;
- separation-of-duties rules;
- SLA and escalation by risk severity;
- safety veto and executive exception paths;
- PR Gate status and branch-protection readiness;
- waiver/approval readiness surfaced as release controls, not comments.

Self-host support needs:

- board generated from local A3 artifacts without live ReleaseFoundry or GitHub calls;
- filesystem fixture mode first;
- SQLite/Postgres metadata plan for board items, waivers, approvals, replay items, and custody events;
- S3-compatible/object-lock storage option later;
- offline verifier for audit bundles;
- backup/restore and retention policy;
- no secrets, emails, cookies, tokens, live signed URLs, or absolute user paths in exports.

Audit support needs:

- board id and schema version;
- board item ids bound to release, run, environment, head SHA, case id, reviewer lane, and policy version;
- artifact hashes for A1 trace/tool-call evidence and A2 judge evidence;
- waiver and approval review ids;
- incident replay disposition history;
- audit bundle root hash;
- verifier result;
- chain-of-custody events for generated, reviewed, waived, approved, replayed, verified, retained, expired, revoked, and superseded.

Compliance support needs:

- redaction policy and redaction finding log;
- metadata-only media safety;
- fail-closed behavior for missing required evidence;
- retention days, legal hold, delete-after, and deletion approval;
- immutable bundle archive direction;
- management sign-off packet with bundle id, root hash, gate decision, waiver/approval state, and verify command.

## 哪里还不像真产品

The reviewer workflow board is not yet a real product until these gaps close:

- No `a3.review_board.v1` schema.
- No durable board item state.
- No board item state machine.
- No reviewer assignment, SLA clock, or escalation policy.
- No authenticated reviewer identity.
- No RBAC or SSO/OIDC role binding.
- No board-level chain-of-custody event log.
- No incident replay disposition history per case.
- No replay result hash per disposition.
- No board-level stale evidence check.
- No direct board linkage to A1 trace/tool-call hashes.
- No direct board linkage to A2 judge result hashes.
- No board summary in PR comment or GitHub Check payload.
- No board artifact in the audit bundle index.
- No verifier rule requiring board evidence for blocked releases.
- No durable self-host storage backend.
- No retention/legal-hold workflow.
- No management sign-off export generated from the board.
- No safety veto or executive exception workflow beyond local records.
- No live required-check enforcement.

The honest product claim today:

> "A3 has the evidence primitives for a reviewer workflow board."

The product claim after the next growth slice:

> "A3 can generate an evidence-backed reviewer workflow board for risky agent releases, linked to incident replay, waiver/approval readiness, PR Gate status, and audit bundle verification."

## 下一轮至少20个增长点

| ID | Growth point | Why it matters | Lane |
|---|---|---|---|
| RWB-1 | Define `a3.review_board.v1`. | Creates the first-class product object. | Schema |
| RWB-2 | Add board id, release version, environment, repo, run id, dataset id, head SHA, and policy version. | Prevents board reuse across releases. | Schema |
| RWB-3 | Define board item types: gate check, incident replay, waiver, approval, A1 evidence, A2 evidence, bundle evidence, reviewer task. | Gives the board a stable information model. | Schema |
| RWB-4 | Define reviewer lanes: release, safety, runner/tooling, judge/evidence, A3 triage, audit, executive. | Turns review into owned work. | Reviewer workflow |
| RWB-5 | Add reviewer assignment fields: owner, role, due time, SLA, escalation, and status. | Makes the board operational. | Reviewer workflow |
| RWB-6 | Add board item states: open, assigned, reviewing, blocked, ready, approved, rejected, waived, expired, closed. | Prevents static table behavior. | Workflow state |
| RWB-7 | Add incident replay dispositions: not_replayed, queued, reproduced, fixed, regressed, flaky, waived, blocked, closed. | Makes failed cases reviewable and auditable. | Incident replay |
| RWB-8 | Bind each top-risk incident to A1 trace hash, tool-call hash, final-response hash, observation hash, and replay command. | Proves what the agent did. | A1 evidence |
| RWB-9 | Bind each top-risk incident to A2 judge result id, score, failure class, judge mode, coverage health, and regression replay status. | Proves how the behavior was judged. | A2 evidence |
| RWB-10 | Add missing-evidence classification: A1 missing, A2 missing, replay missing, waiver missing, approval missing, bundle missing. | Helps reviewers understand blockers quickly. | Evidence health |
| RWB-11 | Add stale evidence detection by run id, head SHA, release version, dataset id, and policy version. | Prevents old evidence from approving new code. | Evidence health |
| RWB-12 | Add waiver readiness summary from `a3.waiver_review.v1`. | Makes exception governance visible. | Waiver |
| RWB-13 | Add approval readiness summary from `a3.approval_review.v1`. | Makes sign-off readiness visible. | Approval |
| RWB-14 | Add separation-of-duties status per approval item. | Prevents self-approval from becoming invisible. | Approval |
| RWB-15 | Add follow-up issue readiness: id/URL shape, owner, due date, and open-state placeholder. | Links risk acceptance to remediation. | Governance |
| RWB-16 | Add PR Gate summary block: conclusion, blocks merge, waiver required, approval pending, replay required, bundle verified. | Connects board to code review. | PR Gate |
| RWB-17 | Add PR comment board summary with top blockers and next actions. | Puts workflow where reviewers work. | PR Gate |
| RWB-18 | Add GitHub Check dry-run fields for board state. | Prepares future required-check enforcement. | PR Gate |
| RWB-19 | Add board artifact to audit bundle index. | Makes board evidence tamper-evident. | Audit bundle |
| RWB-20 | Add verifier rule for board artifact hash and required board fields. | Lets auditors prove the board was complete. | Verifier |
| RWB-21 | Add board root hash or bind board hash to audit bundle root hash. | Gives approvals one stable reviewed evidence handle. | Audit bundle |
| RWB-22 | Add custody events for board generated, item assigned, item dispositioned, waiver reviewed, approval reviewed, board verified, board sealed. | Creates a review history. | Chain of custody |
| RWB-23 | Add management sign-off packet generated from board state. | Makes executive approval fast and defensible. | Sign-off |
| RWB-24 | Add self-host storage contract for board items and disposition events. | Moves from generated file to durable workflow. | Self-host |
| RWB-25 | Add RBAC matrix for board actions: assign, approve, reject, waive, disposition replay, verify, export, delete, legal hold. | Makes enterprise control credible. | Enterprise |
| RWB-26 | Add metadata-only media evidence fields and fail-closed signed URL redaction checks. | Keeps review safe for media cases. | Compliance |
| RWB-27 | Add negative tests for missing A1 evidence, missing A2 evidence, invalid waiver, invalid approval, stale replay, and missing bundle hash. | Proves board controls catch real failures. | Tests |
| RWB-28 | Add dashboard Reviewer Workflow Board panel after JSON contract exists. | Makes the workflow visible without making UI the truth. | Dashboard |
| RWB-29 | Add usage metering for reviewers, board items, replay dispositions, verifier runs, retained bundles, and storage days. | Creates pricing foundation. | Billing |
| RWB-30 | Add export-safe board packet for auditors and customers. | Supports sales, procurement, and compliance review. | Export |

## 哪些必须并行

These lanes should run in parallel because the board only becomes valuable when evidence, governance, PR flow, and audit verification arrive together.

| Parallel lane | First deliverable | Must run with |
|---|---|---|
| Board schema | `a3.review_board.v1` fixture generated from current blocked release evidence. | A1/A2 binding, replay dispositions, PR Gate summary |
| Incident replay dispositions | Disposition enum plus top-risk case mapping. | Board schema, A1 replay evidence, A2 judge evidence |
| A1 evidence binding | Trace/tool-call/final-response/status-history hashes per board incident. | Replay dispositions, verifier, audit bundle |
| A2 evidence binding | Judge result/score/failure-class/coverage fields per board incident. | Replay dispositions, PR Gate summary, dashboard |
| Waiver/approval readiness | Board summaries from waiver and approval review records. | Board schema, audit bundle, management packet |
| PR Gate linkage | PR comment/check dry-run board summary. | Board schema, waiver/approval readiness, replay dispositions |
| Audit bundle linkage | Board artifact hashed into bundle index and verifier output. | Board schema, custody events, approval hash binding |
| Chain of custody | Events for board generation, assignment, disposition, approval, verification, and sealing. | Audit bundle, self-host retention |
| Self-host retention | Local storage contract and retention fields for board state and events. | RBAC, custody, audit bundle |
| Dashboard panel | Read-only board UI. | Schema, evidence binding, verifier status |

Critical sequencing rule:

> Do not build a rich dashboard first. Build the board JSON contract, incident replay dispositions, A1/A2 evidence bindings, waiver/approval readiness, PR Gate summary, and audit bundle verifier linkage first. The dashboard should display evidence, not invent it.

## 哪个方向最接近大钱

The closest direction to big money is:

> Enterprise Release Review Board plus PR Gate plus Incident Replay Dispositions plus Verifiable Audit Bundle.

Why this is the highest-money path:

- Release Gate answers whether the agent release can ship.
- Reviewer Workflow Board answers who must review and what each reviewer must decide.
- Incident replay dispositions answer whether the top failures were reproduced, fixed, regressed, flaky, waived, or still blocked.
- A1 trace/tool-call evidence proves what the agent did.
- A2 judge evidence proves why the behavior was scored as risky.
- Waiver/approval readiness proves whether exception governance is valid.
- PR Gate linkage puts the decision into code review and branch-protection flow.
- Audit bundle linkage gives auditors one retained, verifiable evidence package.
- Self-host and offline verification make the story credible for regulated customers.

Standalone board UI is not the big money. The big money is release-risk infrastructure:

> "Every risky agent release gets a review board, every board item links to evidence, every exception has waiver/approval readiness, every PR shows the gate state, and every final decision is retained in a verifiable audit bundle."

## Acceptance Evidence Expected

The next implementation round should aim for:

1. `a3.review_board.v1` generated from a blocked release.
2. Board items for reviewer lanes, top-risk incidents, waiver readiness, approval readiness, PR Gate status, and audit bundle status.
3. Incident replay dispositions represented as machine-readable fields.
4. A1 trace/tool-call evidence linked by ids and hashes.
5. A2 judge evidence linked by ids and hashes.
6. Waiver readiness imported from local waiver review result.
7. Approval readiness imported from local approval review result.
8. PR comment and GitHub Check dry-run summary include board blockers and next actions.
9. Audit bundle index includes board artifact hash.
10. Verifier checks board artifact presence, hash, required fields, and stale/missing evidence.
11. Markdown report includes `## Reviewer Workflow Board`.
12. Dashboard panel reads board JSON instead of hard-coded text.
13. Negative tests cover missing A1 evidence, missing A2 evidence, invalid waiver, invalid approval, stale replay, missing board artifact, and bundle hash mismatch.
14. Self-host docs define storage, retention, legal hold, and offline verification for board artifacts.
15. Management sign-off packet includes board id, PR Gate conclusion, replay dispositions, waiver/approval readiness, bundle root hash, and verify command.

## Final Auditor Call

Reviewer Workflow Board is the right next A3 growth slice because it connects the buyer's real workflow: review the risky agent release, inspect the incidents, verify the evidence, decide the waiver/approval state, see the PR impact, and retain the audit bundle.

The fastest money-grade sequence:

1. Define `a3.review_board.v1`.
2. Add incident replay dispositions.
3. Attach A1 trace/tool-call evidence.
4. Attach A2 judge evidence.
5. Import waiver/approval readiness.
6. Add PR Gate summary.
7. Hash the board into the audit bundle.
8. Extend verifier rules.
9. Add management sign-off packet.
10. Add dashboard view only after the data contract is real.

The product claim should stay disciplined:

> "A3 can generate an evidence-backed reviewer workflow board for risky agent releases."

Do not claim yet:

> "A3 already has durable enterprise review management, live required-check enforcement, authenticated SSO reviewer approvals, or immutable self-host retention."

That honesty makes the slice credible, and the board makes the commercial story much easier to sell.
