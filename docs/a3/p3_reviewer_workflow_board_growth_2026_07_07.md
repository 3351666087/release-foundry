# P3 Reviewer Workflow Board Growth

## Goal

Turn A3 from a dashboard that shows failed cases into a reviewer workflow that says who must review each risky case, what evidence is ready, what evidence is missing, and whether waiver or approval can proceed.

This is a small product slice, not a full login or cloud-admin system. It keeps the MVP focused on A3-owned release triage, report export, and review readiness.

## Added Capability

- `summarizeReviewerWorkflowBoard()` in `services/report/report_builder.mjs`
- JSON export field:
  - `reviewer_workflow_board`
- Markdown section:
  - `Reviewer Workflow Board`
- Dashboard panel:
  - `Reviewer Workflow`
- Print/PDF report section:
  - `Reviewer Workflow Board`

## What The Board Shows

Each board includes:

- board state: ready, needs review, blocked, or no evidence
- GitHub check conclusion and merge-blocking state
- waiver policy state
- required reviewer count and required approvers
- open item count
- blocked item count
- missing evidence count
- waiver-blocked count
- approval-ready count
- reviewer lanes
- per-case reviewer items
- A1/A2 calibration counts
- required review steps

Each reviewer item includes:

- case id
- run id
- scenario id
- owner lane
- review state
- release blocker flag
- score
- severity
- A2 primary failure class
- failure summary
- required artifacts
- ready artifacts
- missing artifacts
- waiver state
- approval readiness
- A1 trace/tool-call evidence counts
- A2 judge evidence count
- media evidence count
- next action

## A1/A2 Calibration

This board is intentionally derived from upstream work:

- A1 supplies trace events, observations, expected vs actual tool calls, and tool-call diffs.
- A2 supplies score, pass/fail, failure class, judge evidence, remediation, and coverage health.
- A3 uses those signals to assign owner lanes and review states.

The board does not replace A1 or A2. It sits on top of their evidence and makes it operational for human reviewers.

## Why It Matters

Before this slice, A3 could show:

- which cases failed
- what the release gate decided
- which incidents need replay

After this slice, A3 can also say:

- who must look at each failed case
- what evidence is still missing
- whether a blocker needs fix, waiver, or executive exception
- whether reviewers have enough evidence to approve

This makes A3 more like a commercial review console instead of a static report.

## MVP Boundary

Copied now:

- reviewer lanes
- owner assignment by failure type
- blocked / needs evidence / needs review / approval-ready states
- A1/A2 evidence counters
- report export and print/PDF inclusion

Not copied yet:

- real login
- team invite management
- API key creation or reveal
- billing or quota mutation
- durable reviewer identity
- signed live approvals in a database
- cloud-side board persistence

Those are future enterprise features, not required for the current A3 MVP.

## Safety

- No API key, token, cookie, email, or live signed URL is saved.
- Media evidence stays metadata-only.
- No A1 runner core logic is changed.
- No A2 judge semantics are changed.
- The board is local-read-only and export-safe.

## Verification

Focused test command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
44 tests
44 pass
0 fail
```

Full A3 test command should also pass before push:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_releasefoundry_mapper.test.mjs
```

## Next Growth Targets

- Add a durable `a3.review_board.v1` fixture.
- Add reviewer disposition history per replay case.
- Add board summary into PR comments and required-check output.
- Bind reviewer board state into audit bundle index and verifier.
- Add signed reviewer approvals after identity and storage are defined.
