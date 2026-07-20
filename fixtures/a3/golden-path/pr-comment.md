<!-- ashr-plus-plus:release-gate:a3-golden-20260712-001 -->
## Ashr++ Release Gate

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
