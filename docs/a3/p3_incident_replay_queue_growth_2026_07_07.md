# P3 Incident Replay Queue Growth

## Goal

Move A3 closer to a commercial release-intelligence product by turning failed agent cases into a replay-first incident queue.

The queue is not a separate mock. It is derived from A1-style run/trace/tool-call data, A2 judge evidence, A3 release gate risk, and P3 media safety evidence.

## Added Capability

- `summarizeIncidentReplayQueue()` in `services/report/report_builder.mjs`
- JSON export field:
  - `incident_replay_queue`
- Markdown section:
  - `Incident Replay Queue`
- Dashboard panel:
  - `Incident Replay`
- Print/PDF report section:
  - `Incident Replay Queue`

## What The Queue Shows

Each queued failed case includes:

- rank
- run id
- case id
- scenario id
- score
- severity
- primary failure class
- release blocker flag
- owner lane
- trace event count
- observation count
- non-matching tool-call diff count
- linked A2 judge evidence count
- media evidence count
- replay actions
- reviewer packet artifacts

## A1/A2 Calibration

The queue intentionally depends on upstream A1/A2 evidence:

- A1 trace / observation timeline proves what happened.
- A1 expected-vs-actual tool calls prove missing, wrong, extra, reordered, or changed tool behavior.
- A2 judge evidence proves failure class, severity, summary, and remediation.
- A2 coverage fixtures prove the queue still works against current judge/coverage contracts.

This keeps A3 from becoming a standalone visual mock.

## Commercial Value

The customer-facing value is:

> Before a risky agent release is approved, reviewers can replay the highest-risk failures, inspect tool-call divergence, read judge evidence, and attach audit artifacts.

This supports:

- release sign-off
- incident review
- PR merge blocking
- waiver review
- audit export
- enterprise/self-host buyer conversations

## Safety

- No live signed media URLs are rendered.
- Media evidence remains metadata-only.
- No API key, cookie, token, email, account id, or secret is saved.
- No A1 runner core logic or A2 judge semantics are modified.

## Verification

Focused tests:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Expected result:

```text
42 tests
42 pass
0 fail
```

Full A3 test command should also be run before push:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_releasefoundry_mapper.test.mjs
```

Full result for this pass:

```text
78 tests
78 pass
0 fail
```

Screenshot:

- `docs/screenshots/a3-dashboard-incident-replay-queue.png`

## Next Growth Targets

- Add reviewer disposition states for every replay case.
- Add waiver/approval binding to replay cases.
- Add GitHub PR comment section with incident replay top cases.
- Add exportable replay packet manifest.
- Add trace step drilldown inside the dashboard panel.
- Add official frontend observability parity mapping for trace replay.
- Add real production incident import format.
- Add self-host retention policy for replay evidence.
