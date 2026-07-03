# A1 Final Bus Audit - 2026-07-03

Role: Bus-Auditor final final follow-up
Repo: `C:\Users\33516\Documents\Ashr`
Scope constraint: no business code was written by this audit; only this audit file was updated.

## Verdict

**PASS after main-agent remediation, Round 3 hardening, and Round 4 evidence/timeout hygiene.** The A1 implementation and evidence are present in the current filesystem, A1 behavioral acceptance checks pass, and the bytecode-cache blocker identified during audit was removed with explicit literal-path cleanup.

Repository status after Round 3 was clean at `aa3c2fd` and pushed to draft PR #1. Round 4 rechecked the branch/PR, current evidence, and subagent audits; a reviewer-found negative-timeout schema bug was remediated inside A1-owned runner/tests plus evidence docs.

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
| SDK field map >= 25 | Pass | `docs/a1/sdk_field_map.md` contains 56 unique mapped fields. |
| MockAgent + CLI | Pass | `examples/agents/mock_agent.py` provides `MockAgent`/fixture CLI; `services/runner/cli.py` provides runner CLI. |
| 30-case run evidence | Pass | `docs/a1/evidence/local_run_30.json` has `total_cases: 30`, `passed: 30`, `failed: 0`, `errored: 0`, `timed_out: 0`. |
| `max_workers >= 4` | Pass | Evidence reports `max_workers: 4`; runner enforces `MIN_MAX_WORKERS = 4`. |
| Trace completeness >= 95% | Pass | Evidence reports `trace_completeness: 1.0`; 30/30 cases have observations and observation-level VM stream data. Timeout/error tests now also emit replayable synthetic VM streams. |
| >= 3 A3 fixtures | Pass | `examples/agents/fixtures` contains 3 JSON fixtures: `echo_success.json`, `recoverable_error.json`, `tool_math_success.json`. |
| No Ashr API/key use | Pass | No production code network/API client or env-key usage found; run metadata reports `local_only: true`, `ashr_api_used: false`. Public API/key strings appear only in documentation field mapping/explorer notes. |
| A1 tests | Pass | `python -B -m pytest tests/a1 -q -p no:cacheprovider` passed: 37 tests. |
| Negative timeout schema safety | Pass | Default negative timeouts are rejected; per-case negative timeouts emit schema-safe error cases with non-negative timing fields. |
| Schema snapshots | Pass | `docs/a1/schemas` contains local JSON schema snapshots for AgentTurn, RunResult, run fixtures, trace events, and VM stream frames. |
| Pycache absence | Pass after remediation | Main agent removed `packages/sdk/ashr_clone/__pycache__` and `services/runner/__pycache__` by explicit literal path; final status check found no `__pycache__` directories. |

## Follow-Up

1. Stage only this A1-owned Round 4 timeout/evidence hygiene follow-up plus required `docs/evidence` files.
2. Commit and push to the A1 role branch.
3. Keep A2 Scenario/Judge/Golden adapter behind Gate contract.
4. Do not use recursive PowerShell cleanup with `-Include '*.pyc'`; use `python -B`/`pytest -p no:cacheprovider` and explicit literal-path cache cleanup only.
