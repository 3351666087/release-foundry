# M40-03 rc.3 A1 Candidate Run Handoff

## Identity

- Candidate: `a3-golden-agent@0.2.0-rc.3`
- Candidate source commit: `1d292047e991995fdf52f0545ffff410ee19a171`
- Evidence release version: `0.2.0-rc.3`
- A1 run: `a3-golden-20260720-003`
- Dataset: `a3-golden-path-20260720-rc3`
- Runner: `a3-golden-agent-v3`

The Runner performed its Git preflight before execution. `HEAD` matched the candidate source commit, the source tree was clean, and the exact cases array was bound by SHA-256.

## A1 Result

- Cases: `3/3 passed`
- Failed / errored / timed out: `0 / 0 / 0`
- Trace completeness: `100%`
- Tool Calls: `4` (`web.search`, `media.fetch`, `image.view`, `media.classify`)
- Hosted ReleaseFoundry API used: `false`

The rc.3 cases array is intentionally unchanged from rc.2. This isolates candidate/source binding from test-content changes. The archived rc.3 case-set metadata names the new dataset, while its cases array recomputes to the same hash recorded before execution.

## Evidence

- Receipt: `fixtures/a3/golden-path/rc3/a1_candidate_run_receipt.json`
- RunResult: `fixtures/a3/golden-path/rc3/a3_new_run_result.redacted.json`
- Replay fixture: `fixtures/a3/golden-path/rc3/a1_run_fixture.redacted.json`
- Archived case set: `fixtures/a3/golden-path/rc3/a3_new_run_cases.json`
- Evidence bundle hash: `sha256:3240e097cc4e793520d9bbb0b2a600081a5440c751bf842cbe3b8cc9e495cd9f`

The evidence test recomputes file hashes, the canonical cases-array hash, the bundle hash, candidate metadata, run summary, Trace coverage, Tool Calls, and public-safety checks.

## Verification

- `python -B -m pytest tests/release/test_m40_a1_candidate_run.py -q -p no:cacheprovider`: `1 passed`
- `python -B -m pytest tests/release -q -p no:cacheprovider`: `20 passed`
- focused TypeScript candidate-binding, Runner and schema tests: `16 passed`
- exact rc.3 RunResult validation against `docs/a1/schemas/run_result.schema.json`: passed
- ignored dual-release development index verification: `12` assets, no integrity issues

The dual-release verification build was intentionally dirty because it ran after evidence archival. It remained explicit `NO-GO`, was not committed, and was not published. It is not a deployment or release receipt.

## A2 Input

Use these exact A1 binding fields when generating M40-04:

| A2 shared identity field | A1 value |
| --- | --- |
| `candidate_id` | `a3-golden-agent@0.2.0-rc.3` |
| `git_sha` | `1d292047e991995fdf52f0545ffff410ee19a171` |
| `evidence_bundle_hash` | `sha256:3240e097cc4e793520d9bbb0b2a600081a5440c751bf842cbe3b8cc9e495cd9f` |
| `run_id` | `a3-golden-20260720-003` |

This handoff is A1 execution evidence only. It does not grant release authority, create an A2 decision, or claim that A3 delivery is ready.
