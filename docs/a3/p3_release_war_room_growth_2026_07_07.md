# P3 Release War Room Growth

## Purpose

This pass adds the first A3 Release War Room layer.

In plain terms, Release Gate answers "can we ship?" and PR Gate answers "what should GitHub show?" Release War Room joins those signals into one reviewer/manager decision packet:

- release decision
- revenue risk score
- merge-block status
- waiver requirement
- top-risk incident replay cases
- required audit artifacts
- reviewer lanes
- official frontend parity evidence
- enterprise/self-host safety posture

## Why This Is Commercial

The commercial buyer is not paying for another chart. The buyer is paying because risky agent releases need a stop-the-line workflow that a release owner, safety reviewer, engineer, and auditor can all understand.

The War Room is useful because it turns scattered A3 evidence into one operational object:

- `release_gate`: pass/fail/no-go decision
- `release_workflow`: PR check, waiver, reviewers, audit bundle
- `incident_replay`: failed cases that should be replayed before approval
- `official_frontend_mirror`: which official Ashr concepts A3 is copying or excluding
- `media_readiness`: whether signed media evidence is safe to render
- `usage_quota`: whether usage/billing signals are mapped or OAuth-gated

## Implementation Added

- Added `summarizeReleaseWarRoom()` in `services/report/report_builder.mjs`.
- Added schema version `a3.release_war_room.v1`.
- Added JSON export field `release_war_room`.
- Added Markdown report section `Release War Room`.
- Added dashboard panel `Release War Room`.
- Added print/PDF report section `Release War Room`.
- Added redacted fixture:
  - `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- Added tests in:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_release_war_room_2026_07_07.md`

## Official Demo Result

The committed redacted War Room fixture is built from official demo dataset `884` and run `11926`.

Current result:

- Decision: `no_go`
- Revenue risk score: `93`
- Blocks merge: `true`
- Waiver required: `true`
- Safety: no secrets, raw tokens, cookies, or live signed URLs saved

## Safety Boundary

This pass did not call live Ashr API.

The War Room fixture uses existing redacted local evidence only. It does not store API keys, cookies, tokens, email, private account details, live signed media URLs, or official frontend source code.

## Next Growth Points

1. Add verifier result status directly into the War Room.
2. Add waiver and approval review status directly into the War Room.
3. Add GitHub PR number, head SHA, repo, environment, and policy version.
4. Add run-to-run regression delta: new failures, fixed failures, repeated failures.
5. Add executable replay status for each top-risk case.
6. Add self-host retention/storage status.
7. Add usage meter fields for gates, replay packs, verifier runs, and bundle bytes.
8. Add Slack/Jira/PagerDuty dry-run payloads.
9. Add enterprise policy fixture for production vs staging escalation rules.
10. Add immutable archive/zip verifier result into the War Room.
