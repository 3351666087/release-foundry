# Ashr++ Gate CLI Report

- Command shape: ashr gate --json
- Source: m40-05-rc3-local-candidate-binding
- Run: a3-golden-20260720-003
- Decision: Block release
- Risk score: 0
- Check conclusion: failure
- Blocks merge: yes
- A2 authority: blocked
- A2 upstream decision: block
- A2 release ready: no
- Waiver: A3 waiver and approval records cannot override an A2 Decision Ledger block.

## Audit Manifest

- runs: 74c6d5b61220ee94703194d1ca70c54a2129b9ea6a13c1e33aca9e2fade7623e (fixtures/a3/golden-path/rc3/a3_new_run_result.redacted.json)
- grades: 260834b3c5e0c05a5cef7f0275070083f926ddca31aafafb92877c4699e83eb5 (fixtures/a3/golden-path/rc3/a2_grade_results.json)
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

<!-- ashr-plus-plus:release-gate:a3-golden-20260720-003 -->
## Ashr++ Release Gate

Decision: **Block release**
Authority: **A2 Decision Ledger**
Release: `0.2.0-rc.3`
Environment: `staging`
Candidate SHA: `1d292047e991995fdf52f0545ffff410ee19a171`

| Signal | Value |
|---|---|
| Run | `a3-golden-20260720-003` |
| A1/A2 case pass rate | 100% |
| Local quality gate | Approve release |
| Local quality risk score | 0 |
| Authoritative A2 decision | block |
| A2 release ready | no |
| Merge blocked | yes |

### Why blocked

- `a2_decision_blocks_release`
- `a2_release_not_ready`
- `evidence_incomplete`
- `a2_hard_blockers_present`

### Required action

- Do not merge or publish until A2 issues an allow Decision Ledger record for a3-golden-20260720-003.
- A3 did not recompute A2 scores, pass/fail, failure classes, or release authority.
- An A3 waiver cannot convert this A2 block into approval.
