# A3 Growth-Auditor / Money-Grade Audit - 2026-07-07

## Audit Scope

Role: Growth-Auditor / Money-Grade Auditor.

Goal: judge whether A3 is closer to a commercial Agent Release Intelligence Platform.

Safety boundary followed in this audit:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or headers.
- Did not call the real Ashr API.
- Did not call the real GitHub API.
- Wrote only this file: `docs/a3/p3_growth_auditor_2026_07_07.md`.

Local verification snapshot:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs
tests 57
pass 57
fail 0
```

## Executive Verdict

A3 is now meaningfully closer to a sellable Agent Release Intelligence product than to a toy dashboard.

The strongest commercial motion is:

1. PR release gate for agent changes.
2. Audit bundle for enterprise review.
3. Incident replay / RCA starter pack.
4. Self-host compliance edition.
5. Usage governance and chargeback.

Money-grade score today:

| Dimension | Score | Reason |
|---|---:|---|
| Sales narrative | 8/10 | Release Gate, PR Gate, GitHub dry-run, audit bundle, and CLI map clearly to buyer pain. |
| Paid pilot readiness | 6.5/10 | Local CI-shaped artifacts and tests are strong, but live integration and persistence are missing. |
| Enterprise readiness | 4/10 | Audit/redaction/guardrail primitives exist, but no backend, tenant policy, RBAC, SSO, or signed approvals. |
| Self-host readiness | 3/10 | Local static console and CLI exist, but no packaged service, database, installer, or deployment contract. |
| Compliance posture | 5.5/10 | Redacted fixtures, hash manifest, cloud guardrails, and no-live-media policy are good starts; DLP/signing/retention are not there yet. |

## Evidence Snapshot

Core product evidence read:

- `docs/a3/acceptance_checklist.md:151-187` confirms official-demo run `11926`, Release Gate, PR Gate/audit workflow, Gate CLI, check payloads, annotations, and remaining gaps.
- `docs/a3/p3_release_gate_growth_round_2026_07_07.md:30-77` documents the release decision, checks, run `11926` result, risk score, and blockers.
- `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md:30-132` documents GitHub check shape, PR comment, waiver policy, reviewer lanes, audit bundle, incident replay, and gaps.
- `docs/a3/p3_gate_cli_growth_2026_07_07.md:36-145` documents `ashr gate --json`, outputs, hashes, redaction, and remaining gaps.
- `docs/a3/p3_github_dry_run_integration_2026_07_07.md:5-7` confirms no live GitHub API call; `:88-95` lists live-check gaps.
- `docs/a3/p3_github_action_workflow_example.yml:1-29` gives a concrete future GitHub Actions workflow.
- `services/report/report_builder.mjs:645-735` implements Release Gate checks, decision, risk score, top-risk cases, required approvers, and commercial value.
- `services/report/report_builder.mjs:738-840` implements release workflow with GitHub check, PR comment, waiver policy, reviewer lanes, audit bundle, and incident replay.
- `services/report/a3_gate_cli.mjs:13-69` builds the CLI payload with summary, release gate, workflow, GitHub check payload, PR comment, audit manifest, exit behavior, and redaction log.
- `services/report/a3_gate_cli.mjs:247-275` builds GitHub Check Run payload and annotations.
- `services/report/a3_gate_cli.mjs:294-345` applies lightweight output redaction.
- `services/report/a3_github_integration.mjs:4-42` builds GitHub Check create/update request shapes with dry-run safety metadata.
- `services/report/a3_github_integration.mjs:45-88` builds marker-based PR comment create/update plans.
- `apps/dashboard/index.html:1162-1313` wires Release Gate, PR Gate, Usage / Quota, Media Readiness, Cloud Console Shell, and Official Ashr Gap panels.
- `apps/dashboard/index.html:1809-1852` renders Release Gate and Release Workflow.
- `fixtures/a3/release_gate_thresholds.json:1-13` defines commercial local gate thresholds.
- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json:18-87` records a blocked release with risk score, failed checks, thresholds, and approvers.
- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json:203-257` records audit bundle artifacts and incident replay cases.
- `fixtures/a3/p3/a3_github_check_create_request.redacted.json:2-10` records a GitHub Check dry-run request shape.
- `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json:2-27` records a PR comment dry-run upsert plan.
- `docs/a3/p3_api_frontend_visibility_gap.md:93-126` confirms API summary-visible run `11926` and the still-missing logged-in visual Results check.
- `docs/a3/p3_signed_media_url_coverage.md:53-84` confirms file-like signed URL evidence only and blocks live audio/image/video rendering.

## 1. Current Sellable Capabilities

These are no longer just school-demo features. They can be positioned in a paid pilot if scoped honestly.

| Capability | Why It Is Sellable | Evidence |
|---|---|---|
| Release Gate | Converts eval evidence into approve / review / block decision with risk score and failed checks. | `services/report/report_builder.mjs:645-735` |
| PR Gate / Review Workflow | Packages release status into GitHub check shape, PR comment, waiver policy, reviewer lanes, audit bundle, and incident replay pack. | `services/report/report_builder.mjs:738-840` |
| Gate CLI | Gives teams a CI-shaped command: `ashr gate --json`, strict/no-fail modes, output files, input hashes, and redaction log. | `services/report/a3_gate_cli.mjs:13-69` |
| GitHub dry-run adapter | Produces create/update Check Run requests and PR comment upsert plans without a token or live API call. | `services/report/a3_github_integration.mjs:4-88` |
| GitHub Actions workflow example | Shows how a buyer could run the gate on pull requests and enforce `exit_code_hint`. | `docs/a3/p3_github_action_workflow_example.yml:1-29` |
| Official-demo-backed run source | A3 can show dataset `884`, run `11926`, 5 cases, 2 pass, 3 fail, 40% pass rate, 56.4 average score, expected vs actual, tool diffs, and media evidence locally. | `docs/a3/p3_status_handoff_2026_07_07_cn.md:3-22` |
| Tool-call diff with judge evidence | Highlights missing, unexpected, wrong, reordered, and wrong-argument tool calls, which is core agent release risk. | `docs/a3/acceptance_checklist.md:189-209` |
| Audit bundle | Defines required artifacts, redaction policy, screenshots policy, and case evidence for enterprise review. | `services/report/report_builder.mjs:822-833` |
| Incident replay seed | Extracts top-risk case IDs as a failed-cases-first replay pack. | `services/report/report_builder.mjs:834-838` |
| Media readiness / cloud guardrails | Shows media safety, signed URL status, read-only cloud shell, and blocked account/billing/API-key actions. | `docs/a3/p3_media_cloud_console_polish.md:20-95` |
| Usage / quota evidence panel | Shows frontend-confirmed usage/quota channels and OAuth-gated API status. | `docs/a3/p3_media_calibration.md:104-123` |
| Exportable reports | JSON, CSV, Markdown, and print/PDF-ready reports create buyer-facing evidence. | `docs/a3/acceptance_checklist.md:13,159-167,225-229` |

## 2. Toy Capabilities That Must Upgrade

These features look valuable, but are still mostly local contracts, fixtures, or UI shells.

| Area | Current Toy State | Required Upgrade |
|---|---|---|
| Live PR gate | Payloads exist, but no live GitHub required check. | GitHub App or Actions writer, branch protection policy, check-run id persistence. |
| GitHub adapter | Dry-run request builders only. | Explicit dry-run/live flag, token boundary, retries, rate-limit handling, audit log. |
| Waivers | Policy object exists, but no signed approval record. | Persisted waiver with approver identity, expiry, blocked checks, follow-up issue, immutable history. |
| Review workflow | Reviewer lanes are generated text/data. | Assignment state, notifications, SLA, merge-block handoff. |
| Audit manifest | CLI hashes input files only. | Hash generated JSON/Markdown/PDF/screenshots, sign manifest, store bundle immutably. |
| Redaction | Lightweight regex scrubber. | DLP-style structured redaction with fail-closed mode and per-field provenance. |
| Production replay | Incident replay is a list of case IDs. | Actual replay runner, deterministic fixtures, baseline/current diff, reproduce/fixed/new status. |
| Trace ingestion | A3 consumes fixture traces, not production traces. | Trace ingestion API/CLI, normalized event ids, OpenTelemetry/Ashr/A1 adapters. |
| Judge calibration | A2 evidence is summarized, not continuously calibrated. | Calibration matrix in gate, judge drift detection, golden-case confidence, disagreement handling. |
| Native failure class | A3 derives failure class because current Ashr samples lack native `failure_class`. | Adapter for native fields when available plus confidence label for derived classes. |
| Official frontend parity | Run `11926` exists in summary API, but visual Results tab confirmation is still missing. | Logged-in frontend visual recheck for dataset `884` / run `11926`. |
| Media rendering | Live media remains blocked; signed URL behavior confirmed only for file-like actions. | Per-modality signed URL samples, expiry/access rules, sandboxed preview policy. |
| Usage / billing | Usage is frontend-confirmed and API-key-gated, not metered by A3. | Run/case/tool/media metering, quotas, forecasts, team chargeback. |
| Enterprise policy | Thresholds are local JSON. | Tenant/project/repo policy store with versioned approvals. |
| Self-host | Static dashboard plus Node CLI. | Backend service, database, Docker/Compose, installer, backups, upgrade path. |
| API platform | No stable external API. | REST/JSON schemas, webhooks, SDK, API docs, versioning. |

## 3. Commercial Impact

### Raises Customer Willingness To Pay

- Release Gate: answers the buyer's core question, "Can this agent release ship?"
- PR Gate: embeds agent quality review into existing engineering workflow.
- Tool-call diff: makes agent failures concrete, not just "score went down."
- Official-demo-backed run `11926`: proves A3 can map real Ashr-shaped evidence into a product console.
- Reports and print/PDF: gives stakeholders something to attach to release review.

### Raises Average Contract Value

- Enterprise audit bundle: buyer can justify compliance/security spend.
- GitHub check and PR comment workflow: integrates with engineering approvals, not a standalone toy.
- Self-host path: unlocks regulated teams that cannot send traces to SaaS.
- Usage governance: creates a pricing story around runs, cases, tools, media, and teams.
- RBAC/SSO and approval lanes: unlocks multi-team enterprise deployment.

### Lowers Launch Risk

- Strict gate exit behavior blocks known-bad releases in CI.
- Risk score and failed checks make release risk explainable.
- Top-risk cases and incident replay list focus human review.
- Redaction policy and no-live-signed-media guardrail avoid accidental sensitive content exposure.
- Cloud Action Guardrails keep login, API-key, team, billing, trust, and delete actions disabled in MVP.

### Improves Enterprise / Self-Host / Audit / Compliance

- SHA-256 input hashes are a real audit primitive.
- Redacted fixtures and local-only evidence let teams inspect behavior without live secrets.
- GitHub dry-run request shapes can be audited before tokens are introduced.
- Workflow example documents required GitHub permissions.
- Audit bundle artifacts define the minimum package enterprise reviewers expect.

## 4. What Still Does Not Feel Like A Real Product

The product still feels like a strong local prototype in these areas:

- No backend service, database, tenant/project/repo model, or persisted run history.
- No real ingestion path from production traces or CI artifacts into A3.
- No live GitHub required check, despite strong dry-run contracts.
- No signed reviewer approvals, waiver expiry enforcement, or immutable approval history.
- No user-facing policy management; thresholds are local JSON.
- No packaging story: no Docker Compose, Helm, installer, admin docs, backup/restore, or upgrade path.
- No API surface for external systems to create gates, upload traces, or fetch audit bundles.
- No self-host security model: no SSO/RBAC, secrets management, network boundary, or retention policy.
- No cost/usage ledger; Usage / Quota is informational, not a billing or governance system.
- No visual confirmation that official Ashr Results page lists run `11926`.
- No safe live media preview because audio/image/video signed URL behavior is still unconfirmed.
- No evidence that the redaction system fails closed when a secret-like value survives scrub.

## 5. Next Growth Points By Category

Legend:

- Lane A: PR / CI integration.
- Lane B: replay / trace / judge intelligence.
- Lane C: enterprise audit / review / compliance.
- Lane D: self-host / API / platform.
- Lane E: billing / usage.

Items in different lanes can mostly run in parallel. Items inside a lane have light ordering dependencies.

| ID | Category | Growth Point | Why It Matters | Parallel Lane | Dependency |
|---|---|---|---|---|---|
| PR-1 | PR gate | Add live GitHub writer behind explicit `--dry-run` / `--live` flag. | Turns dry-run value into real merge control. | A | Requires approval/token design. |
| PR-2 | PR gate | Implement GitHub App installation contract instead of personal tokens. | Enterprise-friendly auth and revocation. | A | Can start with docs/schema before live writer. |
| PR-3 | PR gate | Persist check-run id per repo, PR, head SHA, and A3 run id. | Enables update mode and avoids duplicate checks. | A | After PR-1 storage stub. |
| PR-4 | PR gate | Add required-check / branch-protection policy fixture and validator. | Makes "blocks merge" operational. | A | Can parallel PR-1. |
| PR-5 | PR gate | Add PR comment update persistence by marker and comment id. | Stable single PR comment instead of noise. | A | Builds on current marker plan. |
| REPLAY-1 | Production replay | Turn `incident_replay.case_ids` into a replay fixture pack. | Moves from list to executable incident reproduction. | B | Can start now from top-risk cases. |
| REPLAY-2 | Production replay | Add run-to-run regression diff in CLI and PR comment. | Shows fixed/new/regressed agent behavior. | B | Needs baseline selection. |
| REPLAY-3 | Production replay | Add replay result states: reproduced, fixed, flaky, new failure. | Gives incident owners actionable status. | B | After REPLAY-1 runner exists. |
| AUDIT-1 | Enterprise audit | Hash generated JSON, Markdown, PDF, screenshots, and PR artifacts. | Completes audit bundle integrity. | C | Can start now. |
| AUDIT-2 | Enterprise audit | Add signed audit manifest with signer, timestamp, policy version, and bundle id. | Makes evidence defensible in compliance review. | C | After AUDIT-1. |
| AUDIT-3 | Enterprise audit | Add enforced redaction fail-closed mode and redaction finding log. | Prevents unsafe exports. | C | Can parallel AUDIT-1. |
| SELF-1 | Self-host | Package dashboard + CLI + local API as Docker Compose. | First credible self-host pilot path. | D | Needs minimal backend. |
| SELF-2 | Self-host | Add SQLite/Postgres persistence for runs, gates, approvals, manifests. | Required for real product state. | D | Can start as local-only DB. |
| SELF-3 | Self-host | Add SSO/RBAC role matrix: admin, release owner, reviewer, auditor, viewer. | Enterprise control and auditability. | D | Can design before implementation. |
| TRACE-1 | Trace ingestion | Define `a3.trace_ingestion.v1` schema for A1 events, Ashr observations, and OTEL spans. | Creates unified evidence pipeline. | B | Can start now. |
| TRACE-2 | Trace ingestion | Add `ashr trace ingest --input ... --json` CLI. | Lets CI/prod feed A3 without hand fixtures. | B | After TRACE-1. |
| TRACE-3 | Trace ingestion | Normalize stable trace event ids across run/case/tool evidence. | Enables deep links and reliable replay. | B | Can parallel TRACE-1. |
| JUDGE-1 | Judge calibration | Add calibration matrix into Release Gate risk scoring. | Prevents weak judges from approving releases. | B | Needs A2 matrix fixture. |
| JUDGE-2 | Judge calibration | Add judge drift detector against golden cases. | Catches silent evaluation regressions. | B | Can parallel replay work. |
| JUDGE-3 | Judge calibration | Add native failure-class adapter with derived/native/confidence labels. | Improves trust and explainability. | B | Needs future native field evidence. |
| INC-1 | Incident report | Generate RCA report from top-risk cases. | Turns gate failure into management-ready incident summary. | C | Can start from current top-risk data. |
| INC-2 | Incident report | Add Slack, Jira, and PagerDuty handoff payloads as dry-run artifacts. | Fits enterprise incident workflows. | C | Can parallel PR/Audit lanes. |
| INC-3 | Incident report | Add remediation owner, due date, and follow-up issue validation. | Connects evidence to accountability. | C | Helps waiver workflow. |
| REVIEW-1 | Review workflow | Persist signed approvals and waiver expiry. | Converts report policy into enterprise record. | C | Needs persistence from SELF-2 or file-backed v1. |
| REVIEW-2 | Review workflow | Add reviewer assignment state and SLA clocks. | Makes review workflow operational. | C | Can start with fixture schema. |
| REVIEW-3 | Review workflow | Block waiver close if follow-up issue is missing or expired. | Reduces governance theater. | C | After REVIEW-1. |
| BILL-1 | Billing/usage | Add usage meter by run, case, judge, tool call, media artifact, and replay. | Foundation for pricing and chargeback. | E | Can start from normalized report data. |
| BILL-2 | Billing/usage | Add cost forecast per PR/release and monthly team estimate. | Makes budget impact visible. | E | After BILL-1. |
| BILL-3 | Billing/usage | Add quota policy gate: warn/block based on usage budget. | Links governance to release control. | E | After BILL-1. |
| API-1 | API platform | Publish JSON schemas for gate payload, workflow, audit bundle, approvals, trace ingestion. | Stabilizes integrations and SDKs. | D | Can start now. |
| API-2 | API platform | Add local REST API for gate creation, artifact upload, approval write, bundle fetch. | Productizes beyond CLI. | D | After SELF-2 minimal persistence. |
| API-3 | API platform | Add webhook/event contract for CI, replay complete, waiver changed, incident created. | Enables platform ecosystem. | D | After API-1. |
| API-4 | API platform | Create SDK/CLI package docs with versioned command examples. | Makes adoption easier for buyers. | D | Can parallel API-1. |

## 6. Parallel Execution Recommendation

Parallel lanes for the next sprint:

| Lane | Owner Type | Can Run In Parallel With | Suggested First PR |
|---|---|---|---|
| Lane A: PR / CI | GitHub integration owner | B, C, E, parts of D | Live/dry-run flag plus branch-protection policy fixture. |
| Lane B: Replay / Trace / Judge | Evaluation systems owner | A, C, E | `a3.trace_ingestion.v1` schema and replay pack fixture. |
| Lane C: Audit / Review / Incident | Enterprise workflow owner | A, B, E | Hash generated artifacts and add signed waiver fixture. |
| Lane D: Self-host / API | Platform owner | A, B, C design work | JSON schemas first, then local persistence/API. |
| Lane E: Billing / Usage | Growth/platform owner | A, B, C | Usage meter from normalized reports. |

Do not sequence everything behind live GitHub. A3 can progress fastest by running these in parallel:

- PR live writer and branch-protection policy.
- Generated artifact hash manifest.
- Trace ingestion schema.
- Replay pack from top-risk cases.
- Signed waiver fixture.
- Usage meter schema.
- JSON schema publication.
- Self-host packaging design.

Blocking dependencies:

- Live required check depends on approved GitHub token/App boundary.
- Real persisted approvals depend on at least file-backed or DB-backed state.
- Production replay runner depends on trace/replay input schema.
- Billing forecast depends on usage meter.
- Official Results parity depends on a logged-in Ashr frontend recheck for dataset `884` / run `11926`.
- Live media preview depends on signed URL samples and expiry/access rules for audio, image, and video.

## Final Auditor Call

A3 has crossed from "nice dashboard" into "credible release-intelligence prototype." The best money-grade move is not more dashboard polish. It is converting the existing local gate into a live or near-live engineering control surface with audit-grade evidence.

Next best sequence:

1. Lock the PR gate integration path with dry-run/live separation and GitHub App policy.
2. Make audit bundles tamper-evident by hashing every generated artifact.
3. Persist approvals/waivers, even in a simple file-backed v1.
4. Add trace ingestion and replay pack execution.
5. Start self-host packaging and usage metering in parallel.

What I did not do:

- Did not modify dashboard, report builder, fixtures, tests, or dry-run adapter files.
- Did not revert or overwrite any main-agent changes.
- Did not read `.env.local`.
- Did not call live Ashr or GitHub APIs.
