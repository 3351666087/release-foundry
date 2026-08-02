# A1 Final Bus Audit - 2026-07-03

Role: Bus-Auditor final final follow-up
Repo: `C:\Users\33516\Documents\ReleaseFoundry`
Scope constraint: no business code was written by this audit; only this audit file was updated.

## Verdict

**PASS after main-agent remediation, Round 3 hardening, Round 4 evidence/timeout hygiene, and Round 5 A2 handoff polish.** The A1 implementation and evidence are present in the current filesystem, A1 behavioral acceptance checks pass, and the bytecode-cache blocker identified during audit was removed with explicit literal-path cleanup.

Repository status after Round 4 was clean at `3617fd2` and pushed to draft PR #1. Round 5 rechecked the branch/PR, current evidence, A2 peer handoff impact, and public ReleaseFoundry pages; a tiny A1-owned A2 projection helper was added without changing shared contracts or judge semantics.

## Current Scope Check

All requested paths exist and resolve inside `C:\Users\33516\Documents\ReleaseFoundry`:

- `packages/sdk/releasefoundry`
- `services/runner`
- `examples/agents`
- `tests/a1`
- `docs/a1`
- `docs/evidence`

## A1 Acceptance Check

| Requirement | Current Result | Evidence |
| --- | --- | --- |
| SDK field map >= 25 | Pass | `docs/a1/sdk_field_map.md` contains 56 unique mapped fields. |
| MockAgent + CLI | Pass | `examples/agents/mock_agent.py` provides `MockAgent`/fixture CLI; `services/runner/cli.py` provides runner CLI. |
| 30-case run evidence | Pass | `docs/a1/evidence/local_run_30.json` has `total_cases: 30`, `passed: 30`, `failed: 0`, `errored: 0`, `timed_out: 0`. |
| `max_workers >= 4` | Pass | Evidence reports `max_workers: 4`; runner enforces `MIN_MAX_WORKERS = 4`. |
| Trace completeness >= 95% | Pass | Evidence reports `trace_completeness: 1.0`; 30/30 cases have observations and observation-level VM stream data. Timeout/error tests now also emit replayable synthetic VM streams. |
| >= 3 A3 fixtures | Pass | `examples/agents/fixtures` contains 3 JSON fixtures: `echo_success.json`, `recoverable_error.json`, `tool_math_success.json`. |
| No ReleaseFoundry API/key use | Pass | No production code network/API client or env-key usage found; run metadata reports `local_only: true`, `releasefoundry_api_used: false`. Public API/key strings appear only in documentation field mapping/explorer notes. |
| A1 tests | Pass | `python -B -m pytest tests/a1 -q -p no:cacheprovider` passed: 39 tests. |
| Negative timeout schema safety | Pass | Default negative timeouts are rejected; per-case negative timeouts emit schema-safe error cases with non-negative timing fields. |
| A2 local handoff projection | Pass | `releasefoundry.to_a2_judge_run(...)` maps A1 `AgentTurn` / `agent_output` into local A2 `final_response` plus `tool_calls[].tool` / `tool_calls[].args` without changing Gate contracts. |
| Schema snapshots | Pass | `docs/a1/schemas` contains local JSON schema snapshots for AgentTurn, RunResult, run fixtures, trace events, and VM stream frames. |
| Pycache absence | Pass after remediation | Main agent removed `packages/sdk/releasefoundry/__pycache__` and `services/runner/__pycache__` by explicit literal path; final status check found no `__pycache__` directories. |

## Follow-Up

1. Stage only this A1-owned Round 5 handoff/evidence follow-up plus required `docs/evidence` files.
2. Commit and push to the A1 role branch.
3. Keep A2 Scenario/Judge/Golden adapter behind Gate contract.
4. Do not use recursive PowerShell cleanup with `-Include '*.pyc'`; use `python -B`/`pytest -p no:cacheprovider` and explicit literal-path cache cleanup only.
