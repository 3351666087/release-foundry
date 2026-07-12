# Ashr++ Gate CLI Report

- Command shape: ashr gate --json
- Source: a3-golden-path-rc2
- Run: a3-golden-20260712-002
- Decision: Block release
- Risk score: 0
- Check conclusion: failure
- Blocks merge: yes
- A2 authority: blocked
- A2 upstream decision: block
- A2 release ready: no
- Waiver: A3 waiver and approval records cannot override an A2 Decision Ledger block.

## Audit Manifest

- runs: ee0428cef01b6797ec9fd6a9bb8363a9af342e48042cea58de86eec1fe1d1a36 (fixtures/a3/golden-path/rc2/a3_new_run_result.redacted.json)
- grades: c9c636d737efa7abfddf984dc7ca2dd02e000a439200a8d88fb01fbed19db577 (fixtures/a3/golden-path/rc2/a2_new_run_judge_response.redacted.json)
- coverage: 3e5f8c572056c38c38d93361c64ef6e76850a1e8a5716947c48be6b0cc19d14f (fixtures/a2/results/a2_g3_coverage_report.json)
- thresholds: fb4360ed42e60a4d8123ccb432bf968cb200f7fe22554e158b1b8a5ac3426729 (fixtures/a3/release_gate_thresholds.json)

## Waiver Review

- Status: not_required
- Accepted: yes
- Automatic unblock: no
- Reason: Release does not require waiver evidence.

## Approval Review

- Status: missing_required_approval
- Accepted: no
- Automatic unblock: no
- Reason: Release requires approval evidence, but no approval file was provided.

## PR Comment

<!-- ashr-plus-plus:release-gate:a3-golden-20260712-002 -->
## Ashr++ Release Gate

Decision: **Block release**
Authority: **A2 Decision Ledger**
Release: `0.2.0-rc.2`
Environment: `staging`
Candidate SHA: `c8420813ed6cb94535bd108b30bd97663b906bdb`

| Signal | Value |
|---|---|
| Run | `a3-golden-20260712-002` |
| A1/A2 case pass rate | 100% |
| Local quality gate | Approve release |
| Local quality risk score | 0 |
| Authoritative A2 decision | block |
| A2 release ready | no |
| Merge blocked | yes |

### Why blocked

- `a2_decision_blocks_release`
- `a2_release_not_ready`
- `a2_hard_blockers_present`

### Required action

- Do not merge or publish until A2 issues an allow Decision Ledger record for a3-golden-20260712-002.
- A3 did not recompute A2 scores, pass/fail, failure classes, or release authority.
- An A3 waiver cannot convert this A2 block into approval.
