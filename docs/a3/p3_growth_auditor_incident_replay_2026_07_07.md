# A3 Incident Replay Queue Growth Audit - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Money-Grade Auditor.

Theme: current A3 incident replay queue growth slice.

Boundaries followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed media URLs.
- Did not call live Ashr, GitHub, or other external APIs.
- Did not edit code, fixtures, worklogs, acceptance checklist, screenshots, or existing docs.
- Created only this artifact: `docs/a3/p3_growth_auditor_incident_replay_2026_07_07.md`.

Evidence basis:

- A1 local queue and replay evidence already supports queued runs, status history, persisted queue state, replay from restored state, terminal export guards, A3-consumable fixtures, trace completeness, observations, final responses, and tool calls.
- A1 documented local-only queue commands include `run-agent-queued`, `queue-run`, `replay-queued`, and `export-fixture`. The smoke path produced `queued -> running -> completed`, 30 local cases, 60 observations, trace completeness `1.0`, and no live API calls.
- A2 provides judge output, failure classes, scores, coverage health, regression replay seeds, and expected A1 handoff fields such as `tool_calls` plus `final_response`.
- A3 already has Release Gate, PR Gate, Gate CLI, waiver and signed approval validation, audit bundle index, verifier direction, generated artifact manifest, Release War Room direction, tool-call diff rows, and media evidence queue.
- A3 currently has incident replay case lists and replay-pack intent, but not a first-class Incident Replay Queue product object with owner, SLA, state, A1 trace/tool-call links, A2 judge links, replay command, audit hashes, and War Room status.
- Media evidence is still metadata-only by policy. Live signed URL rendering should stay disabled until expiry, redaction, and safe preview behavior are proven with approved samples.

## Executive Verdict

The new sellable concept is the Incident Replay Queue:

> "When an agent release fails, A3 turns top-risk failed cases into an owned replay queue with A1 trace/tool-call evidence, A2 judge evidence, release-gate impact, War Room status, and audit-bundle-ready proof."

This is stronger than a static incident replay pack. A pack is a file. A queue is an operational workflow.

Money-grade read:

| Dimension | Current replay list | Incident Replay Queue |
|---|---:|---:|
| Buyer clarity | 5/10 | 8/10 |
| Engineer actionability | 5/10 | 8.5/10 |
| Release-risk reduction | 6/10 | 8.5/10 |
| Enterprise audit value | 5.5/10 | 8/10 |
| Self-host value | 5/10 | 7.5/10 |
| ACV expansion potential | 6/10 | 8.5/10 |

Auditor call: Incident Replay Queue is the most natural next A3 growth slice after Release Gate and Release War Room. It converts "this release failed" into "these exact incidents must be replayed, assigned, verified, and attached to approval evidence before the release can move."

## New Sellable Capability

The Incident Replay Queue should sell these new capabilities:

| Capability | What the buyer gets | Evidence anchor |
|---|---|---|
| Failed-case work queue | Top-risk failed cases become queue items with priority, owner, status, due time, and next action. | A3 release gate top-risk cases and failure clusters. |
| A1 evidence attachment | Each queue item links to trace events, tool calls, arguments, final response, observations, run id, and status history. | A1 runner, trace, local cloud runtime, queue worker, and fixture export. |
| A2 judge attachment | Each queue item links to score, pass/fail, failure class, judge mode, coverage health, and regression replay evidence. | A2 judge results and case-book/regression replay artifacts. |
| Replay command contract | Each item has a local replay command or replay pack reference that can reproduce or recheck the failure. | A1 `queue-run -> replay-queued -> export-fixture` and future `a3.replay_pack.v1`. |
| Release decision linkage | Queue state affects Release Gate next action: replay required, waiver blocked, approval pending, or fixed. | A3 Release Gate and PR Gate workflow. |
| War Room lane | War Room shows queue counts, top incidents, stale items, replay result, and owner. | A3 Release War Room concept. |
| Audit-bundle inclusion | Replay inputs, outputs, trace hashes, judge hashes, and result status are indexed in the audit bundle. | A3 audit bundle index and verifier direction. |
| Metadata-only media safety | Media incidents include media type/channel/count and safety status without raw signed URL rendering. | A3 media evidence queue policy. |
| RCA evidence trail | Queue status becomes part of the incident RCA: reproduced, fixed, regressed, flaky, waived, or not replayed. | A2 regression replay plus A1 deterministic local replay. |
| Enterprise handoff | Queue items can generate PR, Jira, Slack, PagerDuty, or change-management handoff text without exposing secrets. | Existing dry-run PR Gate and War Room export direction. |

The buyer-facing upgrade is simple:

> "A3 does not only block risky agent releases. It tells the team which failures to replay first, why they matter, who owns them, and what evidence proves the fix."

## What Still Looks Like A Toy

Several parts still look toy-like unless upgraded:

| Area | Toy-like state | Money-grade requirement |
|---|---|---|
| Replay identity | Case ids are listed, but not always promoted into durable incident ids. | Stable queue item id bound to run id, case id, dataset id, release version, and evidence hashes. |
| Ownership | No persistent owner, assignee, reviewer lane, or escalation state. | Owner, role, reviewer lane, due time, escalation policy, and separation of duties. |
| Status model | Replay is a concept, not a workflow state machine. | `queued`, `assigned`, `replaying`, `reproduced`, `fixed`, `regressed`, `flaky`, `waived`, `closed`, `blocked`. |
| A1 linkage | A1 can export trace/tool-call fixtures, but A3 does not yet bind every replay item to those fields. | Queue item must include A1 trace hash, tool-call hash, final-response hash, status history, and replay command. |
| A2 linkage | A3 can show judge evidence, but replay queue items are not yet judge-evidence-native. | Queue item must include A2 grade id, score, failure class, judge mode, and coverage status. |
| Release gate | Gate can name top-risk cases, but queue freshness does not yet control release outcome. | Gate should fail or require waiver when high-risk replay items are unreplayed, stale, or unverified. |
| War Room | War Room direction exists, but incident replay is not yet a live operational lane. | War Room should show queue health, blockers, owner, SLA, and replay result. |
| Audit bundle | Replay evidence is not yet hashed as a required artifact. | `a3.replay_queue.v1` and `a3.replay_pack.v1` should be indexed and verified. |
| Media safety | Media queue is metadata-only, but replay queue could accidentally pressure teams to render unsafe media. | Fail-closed media preview policy: metadata only until redacted signed URL safety is proven. |
| Enterprise support | No SSO/RBAC, durable backend, retention policy, or integration history. | Authenticated identity, storage backend, immutable audit trail, and exportable compliance evidence. |

The queue becomes commercial when it is evidence-backed and policy-aware. It stays a toy if it is a pretty table of failed cases.

## Paid Value

Incident Replay Queue creates paid value in four buyer languages.

For engineering leaders:

- Faster path from failed eval to exact reproduction.
- Fewer ambiguous release review meetings.
- Clear owner and next action for every high-risk failure.
- Better regression proof before an agent release ships.

For AI safety and evaluation teams:

- A2 judge findings are attached to replayable A1 traces.
- Failure classes become operational work, not passive report labels.
- High-risk waivers require replay evidence before approval.
- Flaky and unreproduced failures are visible instead of hidden.

For compliance and audit:

- Replay evidence can be included in a tamper-evident bundle.
- The approval packet can prove what failed, what was replayed, and what was accepted.
- Metadata-only media policy reduces leakage of signed URLs and sensitive media.
- Offline verification supports self-host and regulated reviews.

For platform teams:

- Queue metrics become usage and capacity signals.
- Replay workload supports premium pricing by release, case count, storage, retention, and verifier runs.
- Dry-run integrations can later become GitHub, Jira, Slack, PagerDuty, or change-management integrations.

## Raising Average Contract Value

Incident Replay Queue can raise ACV by making A3 look like release operations infrastructure, not just an evaluation report.

High-ACV packaging:

| Package | What changes commercially |
|---|---|
| Enterprise Release Gate | Queue status becomes a merge-blocking or waiver-blocking control. |
| Release War Room | Queue is the operational lane that turns a blocked release into assigned remediation. |
| Audit Bundle Pro | Replay queue and replay results become required, hash-verified audit artifacts. |
| Self-Host Compliance Edition | Replay and verification run offline inside the buyer environment. |
| Incident RCA Add-on | Queue generates incident handoff, RCA timeline, and reproduced/fixed evidence. |
| Usage Governance | Charge by replayed case, stored bundle byte, verifier run, retention day, and high-risk release. |

Why this increases willingness to pay:

- Buyers pay more for release risk reduction than for dashboard visibility.
- Buyers pay more for audit-ready evidence than for screenshots.
- Buyers pay more for self-host/offline workflows than for SaaS-only reporting.
- Buyers pay more when blocked releases become manageable workflows with owners and proof.

## Lowering Launch Risk

Incident Replay Queue reduces launch risk by forcing high-risk failures through a repeatable evidence path.

| Launch risk | Queue control |
|---|---|
| Release approved without reproducing a top failure | Block or require exceptional waiver when top-risk queue items are not replayed. |
| Engineer cannot reproduce failure | Attach A1 trace events, tool calls, final response, observations, and replay command. |
| Judge disagreement is ignored | Attach A2 failure class, score, judge mode, and regression replay status. |
| Tool-call regression is missed | Surface tool name, arguments, expected-vs-actual diff, and A1 trace hash. |
| Unsafe media leaks during review | Keep media evidence metadata-only; do not render live signed URLs. |
| Audit bundle misses RCA evidence | Require replay queue and replay result hashes in bundle verification. |
| Waiver bypasses real remediation | Require replay-before-waiver for production/high-risk failures. |
| Flaky failure is treated as fixed | Track replay status as `flaky` and block clean approval until policy resolves it. |
| Stale replay evidence is reused | Bind queue item to release version, head SHA, run id, dataset id, and policy version. |
| Reviewers cannot see priority | Rank by release-gate impact, severity, failure class, policy status, and recurrence. |

This is a practical risk reducer because it uses evidence A1 and A2 already produce instead of inventing a separate incident system.

## Enterprise, Self-Host, Audit, And Compliance Support

### Enterprise

Enterprise support requires the queue to model people, policy, and workflow:

- queue owner and assignee;
- reviewer lane: release, safety, runner/tooling, judge, evidence, A3 triage, executive;
- due time and SLA by severity;
- escalation state;
- environment and release version;
- repo, PR, head SHA, and branch protection status when available;
- policy version and waiver rule;
- separation-of-duties check;
- audit-bundle and verifier status.

Minimum enterprise claim allowed now:

> "A3 can define the evidence-backed incident replay workflow around blocked releases."

Claim not allowed yet:

> "A3 has durable enterprise incident management with SSO/RBAC, required checks, and retained audit history."

### Self-Host

Self-host buyers need local operation with no live SaaS dependency:

- queue generation from local A3 fixtures and A1 replay state;
- offline replay with local agents and restored queue state;
- offline bundle verification;
- workspace-relative or bundle-relative paths only;
- local filesystem storage first, then SQLite/Postgres and S3-compatible object storage;
- backup/restore verification;
- retention days, legal hold, and deletion policy;
- no secrets, live API keys, cookies, or signed URL values in queue exports.

The A1 queue replay work is a strong self-host foundation because it already proves local state can be snapshotted, reloaded, replayed, and exported without hosted Ashr calls.

### Audit

Audit support requires queue items to be hashable and verifiable:

- queue schema version;
- queue item id;
- source release gate id;
- A1 run id, case id, trace hash, tool-call hash, final-response hash;
- A2 judge result id, score, failure class, judge mode, grade hash;
- replay command hash or replay pack hash;
- replay result status and result hash;
- media safety metadata and redaction status;
- owner/approval/waiver references;
- bundle root hash and verifier result.

The verifier should fail or warn when required replay evidence is missing for blocked production releases.

### Compliance

Compliance support requires policy, retention, and export hygiene:

- replay-before-approval policy for high-risk failures;
- waiver expiry and exceptional approval rule;
- redaction/DLP result for queue exports;
- metadata-only media evidence until signed URL safety is proven;
- immutable archive direction for retained evidence;
- generated PR comment, check payload, Markdown report, and bundle index should be consistent;
- no absolute local user paths, tokens, cookies, account emails, or raw signed URLs in exported queue artifacts.

## Where This Still Does Not Look Like A Real Product

A3 is close to a paid pilot story, but this queue slice is not yet a full product.

Current product gaps:

- No implemented `a3.replay_queue.v1` schema.
- No dashboard Incident Replay Queue panel.
- No queue state persisted in A3 outputs.
- No A3 command that generates replay queue JSON from Release Gate plus A1/A2 evidence.
- No replay queue included as a required audit bundle artifact.
- No verifier rules for replay queue or replay pack hashes.
- No owner, assignee, SLA, or escalation policy.
- No run-to-run incident deduplication.
- No recurrence detection across releases.
- No durable backend or storage lifecycle.
- No SSO/RBAC identity model.
- No GitHub required-check enforcement.
- No Jira/Slack/PagerDuty live integration.
- No immutable archive or signed replay results.
- No self-host installer, retention backend, or backup/restore story.
- No media sandbox; media remains metadata-only.

This is not a weakness if framed honestly. The right claim is "A3 has the evidence primitives and needs to productize them into an Incident Replay Queue." The wrong claim is "A3 already has enterprise incident management."

## Next Round Growth Points

At least 20 growth points should be considered for the next round. The highest-return list is below.

| ID | Growth point | Why it matters | Lane |
|---|---|---|---|
| IRQ-1 | Define `a3.replay_queue.v1`. | Stabilizes the product object for CLI, dashboard, PR comments, and audit bundles. | Schema |
| IRQ-2 | Define queue item id format. | Prevents replay work from being only case-id text. | Schema |
| IRQ-3 | Add queue states: `queued`, `assigned`, `replaying`, `reproduced`, `fixed`, `regressed`, `flaky`, `waived`, `closed`, `blocked`. | Makes replay operational. | Workflow |
| IRQ-4 | Generate queue from Release Gate top-risk cases. | Connects replay directly to release-blocking evidence. | Gate |
| IRQ-5 | Attach A1 trace evidence to each item. | Makes reproduction possible and auditable. | A1 evidence |
| IRQ-6 | Attach A1 tool-call evidence to each item. | Shows missing/wrong tool use and argument failures. | A1 evidence |
| IRQ-7 | Attach A1 final response and observation hashes. | Preserves what the agent actually did and said. | A1 evidence |
| IRQ-8 | Attach A1 queue status history. | Proves queued replay lifecycle and terminal export state. | A1 evidence |
| IRQ-9 | Attach A2 judge result id, score, failure class, and judge mode. | Keeps the queue tied to evaluation evidence. | A2 evidence |
| IRQ-10 | Attach A2 coverage health and regression replay status. | Prevents low-coverage or seed-only findings from looking stronger than they are. | A2 evidence |
| IRQ-11 | Add replay command or replay pack reference per item. | Turns queue rows into executable work. | Replay |
| IRQ-12 | Add replay result status and result hash. | Makes RCA and fix verification audit-ready. | Replay |
| IRQ-13 | Add stale replay detection by release version, head SHA, run id, dataset id, and policy version. | Prevents old replay evidence from approving new code. | Risk |
| IRQ-14 | Add priority scoring: severity, policy failure, recurrence, score drop, trace gap, media risk, and production environment. | Ensures teams replay the right failures first. | Risk |
| IRQ-15 | Add owner, assignee, reviewer lane, due time, and escalation. | Makes the queue enterprise-operational. | Workflow |
| IRQ-16 | Add replay-before-waiver policy. | Prevents exceptional approval without reproduction evidence. | Governance |
| IRQ-17 | Add War Room queue summary: counts by state, stale items, top blockers, owners, next action. | Makes the queue visible to release decision-makers. | War Room |
| IRQ-18 | Add PR comment block with top replay items and verifier status. | Brings replay work into code review. | PR Gate |
| IRQ-19 | Add GitHub Check summary fields for replay-required and replay-verified counts. | Makes future branch protection evidence-aware. | PR Gate |
| IRQ-20 | Include queue JSON and replay result JSON in audit bundle index. | Makes replay evidence tamper-evident. | Audit |
| IRQ-21 | Extend `ashr gate verify --index` to check replay queue artifacts. | Lets auditors prove replay evidence completeness. | Verifier |
| IRQ-22 | Add negative tests for missing replay pack, stale replay result, hash mismatch, and unsafe media URL leakage. | Proves the controls catch real failures. | Tests |
| IRQ-23 | Add metadata-only media fields: type, channel, evidence count, VM stream count, preview policy, redaction status. | Keeps media safety policy enforceable. | Media safety |
| IRQ-24 | Add recurrence detection across runs. | Distinguishes new failures from chronic failures. | RCA |
| IRQ-25 | Add fixed-vs-regressed comparison to baseline run. | Shows whether remediation actually improved the release. | RCA |
| IRQ-26 | Add Jira/Slack/PagerDuty dry-run payloads. | Makes enterprise handoff demoable without live API calls. | Integrations |
| IRQ-27 | Add self-host storage status for queue artifacts. | Supports offline regulated pilots. | Self-host |
| IRQ-28 | Add retention policy fields: retention days, legal hold, storage class, delete-after. | Moves replay evidence toward compliance. | Compliance |
| IRQ-29 | Add usage metering for replay queue items, replay runs, bundle bytes, verifier runs, and retention days. | Creates pricing and chargeback foundation. | Billing |
| IRQ-30 | Add dashboard Incident Replay Queue panel after JSON schema and tests land. | Makes the product visible without making UI the source of truth. | Dashboard |

## Work That Must Run In Parallel

Some work should not be serialized because each lane depends on the others for the commercial story.

| Parallel lane | First deliverable | Must run with |
|---|---|---|
| Queue schema | `a3.replay_queue.v1` fixture generated from current blocked release evidence. | A1/A2 evidence binding, gate summary, tests |
| A1 evidence binding | Queue item fields for trace, tool calls, final response, observations, queue status history, and replay command. | Queue schema, replay pack, verifier |
| A2 evidence binding | Queue item fields for score, failure class, judge mode, coverage, and regression replay status. | Queue schema, dashboard, gate |
| Release Gate integration | Gate next action becomes replay-aware. | Queue status model, waiver policy, PR comment |
| War Room integration | War Room displays queue health and blockers. | Gate integration, dashboard, audit bundle |
| Audit verifier | Verify queue/replay artifacts and hashes. | Audit bundle index, replay pack, negative tests |
| Metadata-only media safety | Media replay items stay metadata-only and fail closed. | Queue schema, verifier, dashboard |
| Self-host retention | Local storage and retention policy for queue artifacts. | Audit bundle, verifier, billing |
| Billing/usage | Meter replay workload and retained evidence. | Self-host retention, dashboard summary |
| Dashboard panel | Read-only Incident Replay Queue view. | Schema, gate, War Room, media safety |

The most important parallel dependency is this:

> Do not build the dashboard panel before the queue JSON contract, A1/A2 evidence links, and verifier rules exist. The UI should display evidence, not become the evidence.

## Closest Direction To Big Money

The closest direction to big money is not a standalone replay queue.

The closest direction is:

> Enterprise Release War Room plus Incident Replay Queue plus verifiable audit bundle.

Why this is the largest money path:

- Release Gate answers whether a release can ship.
- Incident Replay Queue answers what must be fixed or replayed.
- A1 evidence proves what the agent did.
- A2 evidence proves how the behavior was judged.
- War Room gives managers and reviewers one operational decision surface.
- Audit bundle and verifier make the evidence defensible later.
- Self-host retention makes regulated buyers comfortable.
- Usage metering creates premium pricing paths.

This bundle can be sold as release-risk infrastructure. A standalone incident queue is useful, but the buyer spends more when it controls merge decisions, approvals, RCA, and retained compliance evidence.

Best buyer-facing message:

> "A3 gives every risky agent release a replay queue. Engineers reproduce the failure, reviewers see the judge evidence, managers see the War Room status, and auditors can verify the retained bundle offline."

## Acceptance Evidence Expected

The next implementation round should aim for evidence like this:

1. `a3.replay_queue.v1` generated from current blocked release evidence.
2. Queue items include run id, dataset id, case id, release context, priority, state, owner placeholder, due time placeholder, and next action.
3. Queue items link to A1 trace/tool-call evidence, final response, observations, and queue status history.
4. Queue items link to A2 judge evidence: grade id, score, failure class, judge mode, coverage, and regression replay status when available.
5. Queue items include replay command or replay pack reference.
6. Release Gate output includes replay-required and replay-verified summary fields.
7. Release Gate blocks or requires exceptional waiver when high-risk replay items are not replayed.
8. War Room summary includes queue counts, stale items, top blockers, and owner/reviewer lane.
9. PR comment and GitHub Check dry-run payload include compact replay queue summary.
10. Audit bundle index includes replay queue and replay result artifacts.
11. Verifier checks replay queue artifact hashes and required evidence presence.
12. Metadata-only media safety is enforced for media replay items.
13. Tests prove unsafe raw signed media URL values are not exported.
14. Tests prove missing A1 trace evidence marks replay item incomplete.
15. Tests prove missing A2 judge evidence marks replay item evidence-incomplete or judge-unavailable, not silently clean.
16. Tests prove stale replay evidence cannot approve a new release context.
17. Tests prove high-risk unreplayed items affect gate next action.
18. Tests prove dashboard reads queue fields from JSON rather than hard-coded text.
19. Tests prove audit verifier catches missing or tampered replay queue artifacts.
20. Markdown report includes an `## Incident Replay Queue` section with top incidents and next actions.

## Final Auditor Call

Incident Replay Queue is a strong money-grade next slice because it sits exactly where A3 has momentum: release gate, PR workflow, War Room, A1 trace/tool-call evidence, A2 judge evidence, audit bundles, and metadata-only media safety.

The fastest high-value sequence is:

1. Define `a3.replay_queue.v1`.
2. Generate queue items from Release Gate top-risk cases.
3. Attach A1 trace/tool-call/final-response/status-history evidence.
4. Attach A2 judge/failure-class/coverage evidence.
5. Add replay command or replay pack reference.
6. Make Release Gate and War Room replay-aware.
7. Include queue artifacts in audit bundle index.
8. Extend verifier rules to replay queue and replay pack artifacts.
9. Keep media evidence metadata-only and fail closed.
10. Add dashboard and PR summary only after the data contract is real.

The product claim should be disciplined:

> "A3 can turn blocked agent-release failures into an evidence-backed replay queue ready for release review and audit."

Do not claim yet:

> "A3 has full enterprise incident management, live required-check enforcement, signed replay results, or durable self-host retention."

That honesty is what makes the current slice credible.
