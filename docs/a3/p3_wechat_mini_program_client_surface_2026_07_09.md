# A3 WeChat Mini Program Client Surface - 2026-07-09

## Scope

This round moves `wechat-mini-program-client-surface` from missing to a testable A3 client-surface contract.

Implemented evidence:

- `apps/wechat-miniprogram/project.config.json`
- `apps/wechat-miniprogram/app.json`
- `apps/wechat-miniprogram/pages/release-approval/index.*`
- `apps/wechat-miniprogram/pages/incident-alert/index.*`
- `apps/wechat-miniprogram/contracts/a3-client-surface.contract.js`
- `tests/a3/a3_wechat_mini_program_client_surface.test.mjs`

Safety boundary:

- No `.env.local` read.
- No dependency installation.
- No live Ashr, GitHub, WeChat, billing, hosted auth, team, API-key, Trust, or cloud mutation.
- No A1 runner or A2 judge semantics changed.
- No token, cookie, raw key, Authorization header, raw signed URL, private prompt body, or private account value is stored in the mini program contract.

## API Contract

The mini program is a read-mostly client surface. It consumes A3 server-side redacted APIs:

- `GET /api/a3/releases/:releaseId/evidence-summary?version=2`
- `GET /api/a3/releases/:releaseId/evidence-health`
- `GET /api/a3/releases/:releaseId/evidence-diff`
- `GET /api/a3/releases/:releaseId/readbacks`
- `GET /api/a3/reports/:reportId/manifest`
- `GET /api/a3/review/workflow?releaseId=:releaseId`

Planned guarded write contract:

- `POST /api/a3/review/actions/submit`

The write path is contract-only in this shell. Any future approval or incident acknowledgement must be server-authenticated, RBAC-checked, audit-logged, and redacted before a WeChat client sees it.

## DB Contract

The client does not own DB writes. A3 backend read models should project:

- `release_evidence_snapshots`
- `release_evidence_readbacks`
- `hosted_reports`
- `review_workflow_records`
- `audit_events`
- `usage_ledger`
- `artifact_registry_entries`

Future guarded write models:

- `review_action_requests`
- `incident_alert_acknowledgements`

Every row must keep tenant columns: `tenant_id`, `project_id`, and `release_id`.

## Event Contract

Mini program events are ids/status/hash/count only:

- `wechat.release_approval_viewed`
- `wechat.release_approval_requested`
- `wechat.incident_alert_viewed`
- `wechat.incident_alert_acknowledged`

Events must not contain raw prompts, raw outputs, raw signed URLs, tokens, cookies, raw keys, Authorization headers, or account-private values.

## Artifact Contract

The pages may render redacted references to:

- `release_evidence_summary`
- `hosted_report_snapshot`
- `reviewer_workflow_board`
- `incident_replay_packet`
- `audit_bundle_index`
- `artifact_registry_entry`

The pages must never render or persist raw tokens, cookies, raw API keys, raw signed URLs, private prompt bodies, or unredacted customer payloads.

## Tenant / Auth / RBAC / Usage / Audit / Redaction

Tenant:

- API responses must be scoped by authenticated `tenant_id`, `project_id`, and `release_id`.
- The mini program query string may carry ids for navigation, but it is not authority.

Auth:

- The mini program contract forbids token, cookie, raw key, and Authorization header persistence.
- Auth must be server-backed before any approval action can affect release state.

RBAC:

- Release approval requires `release_owner`, `reviewer`, or `auditor`.
- Incident acknowledgement requires `release_owner`, `incident_reviewer`, or `auditor`.
- RBAC decisions are server-side and must be visible as redacted status only.

Usage:

- Meter page views, approval requests, incident acknowledgements, readbacks viewed, and hosted report opens.
- Usage rows should link to `summary_id`, `release_id`, `tenant_id`, and `project_id`.

Audit:

- Append audit events for page viewed, approval requested, alert acknowledged, report opened, and denied access.
- Audit events should contain actor aliases and artifact hashes, not private account values.

Redaction:

- Render aliases, statuses, counts, hashes, and hosted report links only.
- Denied or expired report access must not render report body evidence.

## A1 / A2 / A3 Integration

A1 integration is downstream only:

- A1 RunResult
- A1 Trace
- A1 ToolCall
- A1 Observation

A2 integration is downstream only:

- A2 GradeResult
- A2 ReleaseGate
- A2 FailureTaxonomy
- A2 CommercialReadiness

A3 integration:

- A3 hosted report
- A3 release evidence
- A3 reviewer workflow
- A3 usage ledger
- A3 audit bundle

The mini program shell does not alter A1 runner semantics or A2 judge semantics. It gives China commercial users a mobile entry point for release approval and incident alert review once A3 backend auth/RBAC/readback evidence is production-ready.

## Acceptance

Run:

```text
node --test tests/a3/a3_wechat_mini_program_client_surface.test.mjs
python scripts\cl_guard.py commercial
```

Expected:

- WeChat project config exists and includes `appid` plus `miniprogramRoot`.
- Page declarations exist for release approval and incident alert.
- Contract names hosted report, release evidence, reviewer workflow, A1, A2, and A3 integration terms.
- Tenant/auth/RBAC/usage/audit/redaction guardrails are present.
- Commercial CL guard no longer reports `wechat-mini-program-client-surface` as missing.
