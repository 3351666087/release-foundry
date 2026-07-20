# M40-04 rc.3 A2 Candidate Authority Handoff

## Shared Identity

- Candidate: `a3-golden-agent@0.2.0-rc.3`
- A1 source commit: `1d292047e991995fdf52f0545ffff410ee19a171`
- A2 authority implementation: `d3529c356e49ce8502c050f0dad44020031ee0dd`
- A1 run: `a3-golden-20260720-003`
- Evidence release version: `0.2.0-rc.3`
- A1 evidence bundle: `sha256:0b4fb982ccc5a25a54c8c8ea8744285296502bb6be3113d5220af7f3340e3d6b`

The A2 authority SHA identifies the first PR commit containing the candidate
authority builder. The evidence is regenerated in the following commit and
the PR must use a merge commit so this implementation SHA remains reachable
from `main`. It does not replace the A1 source commit recorded by the
candidate-bound Runner.

## A2 Regrade

A2 consumed the candidate-bound A1 RunResult directly and independently ran
the existing five deterministic judges for each case. It did not inherit A1's
pass/fail field.

- Cases: `3`
- A2 local passes: `3`
- A2 local failures: `0`
- Scores: `100.0`, `100.0`, `100.0`
- Grade results hash: `sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304`

The three local grades passing does not independently authorize a release.

## Trusted Evidence And Decision

A2 froze one public-safe Evidence Snapshot for each case and chained three
Decision Records into one append-only ledger.

- Direct-answer snapshot: `complete`
- Required-web-tool snapshot: `complete`
- Media-pipeline snapshot: `evidence_missing`
- Decision Ledger head: `sha256:af84d7e9e3143f4da06341f2e20f3402c8f44ed5efc8221b18c8ef2869747a4e`
- Decision Ledger hash: `sha256:5755f8f1dc03b1b09e43acac60a38a6b5f629cf1b8ba830c54b77e994bca9672`
- Trusted Spine bundle hash: `sha256:48bba3c6a956fa4d771e69667f2b75597f828ea96fe036a18671b158c4bbc9d6`
- Authoritative A2 decision: `block`

The media case contains hashed image artifacts and the expected Tool Calls,
but it does not contain a production-eligible A2 derived-image evidence
record. A2 therefore records the image modality as missing instead of treating
the local classifier output as independent semantic proof.

The decision also preserves the latest A2 source state:

- Round 53 multimodal control quality is blocked on attack sensitivity.
- Round 53 repeated calibration is not promotion eligible.
- Round 53 cloud qualification remains blocked.
- Round 53 local runtime promotion remains blocked because structured output
  was invalid for all required profiles.
- Independent multimodal human review remains pending.
- Round 53 same-round PostgreSQL proof is verified and is not a blocker.

## Outputs

- A2 grades: `fixtures/a3/golden-path/rc3/a2_grade_results.json`
- Shared candidate identity: `fixtures/a3/golden-path/rc3/a2_shared_candidate_identity.json`
- Trusted Spine and Decision Ledger: `fixtures/a3/golden-path/rc3/a2_trusted_spine_handoff.snapshot.json`
- Generator: `scripts/a2_build_m40_rc3_authority.py`
- Core builder: `services/judge/candidate_authority.py`
- Schema: `docs/a2/schemas/candidate_trusted_spine.schema.json`
- Recompute test: `tests/release/test_m40_a2_candidate_authority.py`

## A3 Input For M40-05

A3 must consume these exact A2 values without recalculating them:

| A3 shared identity field | A2 value |
| --- | --- |
| `candidate_id` | `a3-golden-agent@0.2.0-rc.3` |
| `run_id` | `a3-golden-20260720-003` |
| `consumed_decision_hash` | `sha256:af84d7e9e3143f4da06341f2e20f3402c8f44ed5efc8221b18c8ef2869747a4e` |
| `consumed_grades_hash` | `sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304` |

The current shared identity intentionally remains `blocked` with
`a3_rc3_delivery_not_generated` and zero A3 consumption hashes. M40-05 must
replace those placeholders only after regenerating the A3 gate, delivery
index, audit bundle and archive for this exact candidate and run.

A3 must display `block`, keep `release_ready=false`, and preserve the ledger
head as provenance. It may not convert the three passing local grades into an
allow decision.

## Reproduction

```powershell
python scripts/a2_build_m40_rc3_authority.py --check
python -B -m pytest tests/release/test_m40_a2_candidate_authority.py -q -p no:cacheprovider
python -B -m pytest tests/release -q -p no:cacheprovider
```

The generator reads only committed public-safe fixtures. It does not use a
network, API key, raw provider payload, private artifact, or production
credential.
