# M20 Evaluation And Policy

Owner lane: A2. A3 displays A2 authority and never recomputes its release decision.

## Checklist

- [x] `M20-01` Scenario, golden case, rubric and failure taxonomy contracts exist.
- [x] `M20-02` Deterministic Judge, GradeResult and regression paths have tests.
- [x] `M20-03` Evidence Snapshot, Trusted Spine and Decision Ledger are consumable by A3.
- [x] `M20-04` Multimodal calibration and provider-neutral controls exist as public-safe evidence.
- [ ] `M20-05` Rebuild A2 evidence for the current candidate run and current Git SHA.
- [ ] `M20-06` Close authoritative multimodal specificity and latency blockers.
- [ ] `M20-07` Attach qualified live-provider and production multimodal receipts.

## Evidence To Load

- `docs/a2/README.md`
- `docs/a2/a1_a3_handoff.md`
- `packages/scenarios`
- `services/judge`
- `fixtures/a2/results`
- latest A2 Decision Ledger fixture only

## Evidence Log

- `2026-07-20`: the Customer Agent verifier preserved the current A2 `block` and reports stale candidate binding instead of promoting it.
