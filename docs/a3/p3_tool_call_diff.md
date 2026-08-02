# P3 Tool Call Diff

## Purpose

This follow-up finishes the next A3 backlog item after media evidence: make tool-call failures understandable without forcing the reviewer to compare raw JSON by hand.

## What Changed

- Added `buildToolCallDiffs(caseResult)` in `services/report/report_builder.mjs`.
- Added JSON export field `tool_call_diffs`.
- Added dashboard `Tool Call Diff` panel in Case Detail.
- Added field-level `argument_diffs` for changed, missing, and unexpected arguments.
- Added `judge_evidence` links from each tool diff row back to matching A2 judge output.
- Added semantic pairing for reordered tool calls so A3 can distinguish order mistakes from wrong-tool mistakes.
- Added `match_strategy`, `expected_index`, `actual_index`, and `order_changed` to JSON diff rows.
- Added `trace_event_links` and linked judge `evidence.trace_event_ids` for matching tool trace events.
- Added tests for:
  - missing required tool
  - wrong tool arguments
  - field-level nested argument differences
  - judge evidence linkage
  - reordered tool-call semantic pairing
  - trace event evidence links

## Diff Statuses

The report builder now emits one row per expected/actual tool-call position:

- `match`
- `missing_required_tool`
- `unexpected_tool_call`
- `wrong_tool`
- `wrong_arguments`
- `wrong_tool_order`

## Dashboard Behavior

For each selected case, A3 shows:

- status badge
- short human-readable summary
- expected tool name and arguments
- actual tool name and arguments
- argument field path, status, expected value, and actual value when arguments differ
- matching judge evidence with judge mode, score, failure class, summary, details, remediation, and tool call IDs
- matching strategy and original expected/actual positions, for example `semantic_exact_reordered / expected #1 -> actual #2`
- linked trace event IDs under judge evidence when A1/A3 trace events include matching tool names or tool call IDs

Example outcomes:

- `Expected web.search, but no actual tool call was present at this position.`
- `Tool file.read was called with different arguments.`
- `path / changed_argument / fixtures/a2/contracts/vendor-alpha.txt / fixtures/a2/contracts/vendor-alfa.txt`
- `g1_trace_contract_judge / wrong_arguments / Show expected vs actual argument diff in A3 case detail.`
- `Tool web.search matched, but appeared in a different order.`
- `semantic_exact_reordered / expected #1 -> actual #2`
- `Trace events / sample-a2-s010-wrong-argument:trace:1`

## Verification

- `node --test tests/a3/report_builder.test.mjs`
- `node --test tests/a3/p3_releasefoundry_mapper.test.mjs`
- `node --test tests/a3/dashboard_wiring.test.mjs`
- Browser smoke on mock fixture.
- Screenshot:
  - `docs/screenshots/a3-dashboard-argument-diff.png`
  - `docs/screenshots/a3-dashboard-judge-evidence.png`

## Remaining Gaps

- A future pass can turn trace event IDs into clickable timeline anchors if the dashboard adds stable DOM anchors for each event row.
