# ReleaseFoundry Gate CLI Report

- Command shape: releasefoundry gate --json
- Source: a3-golden-path
- Run: a3-golden-20260712-001
- Decision: Block release
- Risk score: 87
- Check conclusion: failure
- Blocks merge: yes
- A2 authority: blocked
- A2 upstream decision: block
- A2 release ready: no
- Waiver: A3 waiver and approval records cannot override an A2 Decision Ledger block.

## Audit Manifest

- runs: 765a566732207e105d1856d8aa01dbbdb93f4fae9e85131e1b6fb1c77242d2fd (fixtures/a3/golden-path/a3_new_run_result.redacted.json)
- grades: c2b056989c7155009f0136ba75997de7dfbdfb92daa71bdc4d483474ec3417cf (fixtures/a3/golden-path/a2_new_run_judge_response.redacted.json)
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

<!-- releasefoundry-plus-plus:release-gate:a3-golden-20260712-001 -->
## ReleaseFoundry Release Gate

Decision: **Block release**
Authority: **A2 Decision Ledger**
Release: `0.2.0-rc.1`
Environment: `staging`
Candidate SHA: `not-bound`

| Signal | Value |
|---|---|
| Run | `a3-golden-20260712-001` |
| A1/A2 case pass rate | 33.3% |
| Local quality gate | Block release |
| Local quality risk score | 87 |
| Authoritative A2 decision | block |
| A2 release ready | no |
| Merge blocked | yes |

### Why blocked

- `a2_decision_blocks_release`
- `a2_release_not_ready`
- `a2_hard_blockers_present`

### Required action

- Do not merge or publish until A2 issues an allow Decision Ledger record for a3-golden-20260712-001.
- A3 did not recompute A2 scores, pass/fail, failure classes, or release authority.
- An A3 waiver cannot convert this A2 block into approval.
