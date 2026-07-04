# P3 Tool Call Diff

## Purpose

This follow-up finishes the next A3 backlog item after media evidence: make tool-call failures understandable without forcing the reviewer to compare raw JSON by hand.

## What Changed

- Added `buildToolCallDiffs(caseResult)` in `services/report/report_builder.mjs`.
- Added JSON export field `tool_call_diffs`.
- Added dashboard `Tool Call Diff` panel in Case Detail.
- Added tests for:
  - missing required tool
  - wrong tool arguments

## Diff Statuses

The report builder now emits one row per expected/actual tool-call position:

- `match`
- `missing_required_tool`
- `unexpected_tool_call`
- `wrong_tool`
- `wrong_arguments`

## Dashboard Behavior

For each selected case, A3 shows:

- status badge
- short human-readable summary
- expected tool name and arguments
- actual tool name and arguments

Example outcomes:

- `Expected web.search, but no actual tool call was present at this position.`
- `Tool file.read was called with different arguments.`

## Verification

- `node --test tests/a3/report_builder.test.mjs`
- `node --test tests/a3/p3_ashr_mapper.test.mjs`
- Browser smoke on mock fixture.
- Screenshot:
  - `docs/screenshots/a3-p3-tool-call-diff.png`

## Remaining Gaps

- Diff is currently index-based, not semantic matching across reordered tool calls.
- It compares normalized names and JSON arguments; it does not yet produce field-level inline argument diffs.
- A future judge drilldown can link each diff row back to A2 judge evidence.
