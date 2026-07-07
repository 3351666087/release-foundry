# P3 Observability Replay Matrix Growth

## Goal

Move A3 closer to a production incident review product by turning failed cases into an observability replay matrix.

This is the layer between Incident Replay and Reviewer Workflow:

- Incident Replay says which failed cases must be replayed.
- Observability Replay says what trace, tool-error, latency, judge, media, and official Observability evidence is available.
- Reviewer Workflow says who must review and whether waiver or approval can proceed.

## Added Capability

- Added `summarizeObservabilityReplayMatrix()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `observability_replay_matrix`
- Added Markdown report section:
  - `Observability Replay Matrix`
- Added dashboard panel:
  - `Observability Replay`
- Added print/PDF report section:
  - `Observability Replay Matrix`
- Added report-builder and dashboard-wiring tests.

## What The Matrix Shows

The matrix summarizes:

- replay case count
- trace-ready count
- tool/error case count
- latency/duration case count
- media evidence count
- A2 judge-linked count
- blocked replay count
- official Observability code-crawl parity
- replay lanes
- per-case replay items

Each replay item includes:

- run id
- case id
- scenario id
- owner lane
- production risk
- observability state
- score
- severity
- A2 primary failure class
- A1 trace count
- A1 observation count
- latency/duration fields when available
- tool diff count
- tool/error signal count
- A2 judge evidence count
- media evidence count
- official parity source
- next action

## A1/A2/Official Calibration

This matrix is intentionally calibrated against three evidence sources:

- A1: trace events, observations, tool-call diffs, latency/duration fields, and tool-error text.
- A2: score, pass/fail, primary failure class, judge evidence, and remediation.
- Official Ashr frontend: clean-room ObservabilityPage / trace / latency / error signals from `ashr_frontend_code_crawl_summary.redacted.json`.

The matrix does not copy official source code and does not call live APIs.

## Commercial Meaning

This is a sellable production-readiness feature:

> Before a risky agent release ships, A3 can show whether each top failed case has enough trace, tool-error, judge, and media evidence to reproduce the incident and block release if needed.

It supports:

- release blocking
- production replay
- incident review
- reviewer sign-off
- audit export
- self-host evidence review

## Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
48 tests
48 pass
0 fail
```

## Safety

- No `.env.local` read.
- No API key, cookie, token, email, account data, or signed URL saved.
- No official source code committed.
- Media evidence remains metadata-only.
- A1 runner logic and A2 judge semantics are unchanged.
