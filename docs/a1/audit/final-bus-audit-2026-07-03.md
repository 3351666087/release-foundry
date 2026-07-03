# A1 Final Bus Audit - 2026-07-03

Role: Bus-Auditor final final follow-up
Repo: `C:\Users\33516\Documents\Ashr`
Scope constraint: no business code was written by this audit; only this audit file was updated.

## Verdict

**PASS after main-agent remediation and Round 3 hardening.** The A1 implementation and evidence are present in the current filesystem, A1 behavioral acceptance checks pass, and the bytecode-cache blocker identified during audit was removed with explicit literal-path cleanup.

Repository status after Round 2 was clean at `074c510` and pushed to draft PR #1. Round 3 introduced local A1 hardening changes for A3 timeout replayability, strict VM frame validation, AgentTurn schema versioning, and schema snapshots; these changes remain inside A1 owned directories and required evidence docs until the main agent stages, commits, and pushes this follow-up.

## Current Scope Check

All requested paths exist and resolve inside `C:\Users\33516\Documents\Ashr`:

- `packages/sdk/ashr_clone`
- `services/runner`
- `examples/agents`
- `tests/a1`
- `docs/a1`
- `docs/evidence`

## A1 Acceptance Check

| Requirement | Current Result | Evidence |
| --- | --- | --- |
| SDK field map >= 25 | Pass | `docs/a1/sdk_field_map.md` contains 63 unique mapped fields. |
| MockAgent + CLI | Pass | `examples/agents/mock_agent.py` provides `MockAgent`/fixture CLI; `services/runner/cli.py` provides runner CLI. |
| 30-case run evidence | Pass | `docs/a1/evidence/local_run_30.json` has `total_cases: 30`, `passed: 30`, `failed: 0`, `errored: 0`, `timed_out: 0`. |
| `max_workers >= 4` | Pass | Evidence reports `max_workers: 4`; runner enforces `MIN_MAX_WORKERS = 4`. |
| Trace completeness >= 95% | Pass | Evidence reports `trace_completeness: 1.0`; 30/30 cases have observations and VM stream data. Timeout/error tests now also emit replayable synthetic VM streams. |
| >= 3 A3 fixtures | Pass | `examples/agents/fixtures` contains 3 JSON fixtures: `echo_success.json`, `recoverable_error.json`, `tool_math_success.json`. |
| No Ashr API/key use | Pass | No production code network/API client or env-key usage found; run metadata reports `local_only: true`, `ashr_api_used: false`. Public API/key strings appear only in documentation field mapping/explorer notes. |
| A1 tests | Pass | `python -B -m pytest tests/a1 -q -p no:cacheprovider` passed: 33 tests. |
| Schema snapshots | Pass | `docs/a1/schemas` contains local JSON schema snapshots for AgentTurn, RunResult, run fixtures, trace events, and VM stream frames. |
| Pycache absence | Pass after remediation | Main agent removed `packages/sdk/ashr_clone/__pycache__` and `services/runner/__pycache__` by explicit literal path; final status check found no `__pycache__` directories. |

## Follow-Up

1. Stage only A1 owned directories plus required `docs/evidence` files for each round.
2. Commit and push to the A1 role branch.
3. Keep A2 Scenario/Judge/Golden adapter behind Gate contract.
4. Do not use recursive PowerShell cleanup with `-Include '*.pyc'`; use `python -B`/`pytest -p no:cacheprovider` and explicit literal-path cache cleanup only.
