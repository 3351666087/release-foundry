# A2 cancellation, persistence, and provenance controls — Round 28 (2026-07-13)

## Synchronization

Fresh fetch before closure:

`	ext
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
`

A1 remains the evidence producer, A2 the sole release decision authority, and A3 a committed-decision consumer. Provider acknowledgements and health probes remain observations rather than truth.

## Round 28 task disposition

1–2. Added cancellation acknowledgement conformance behavior and distinct unavailable/rejected blockers.
3. Bound acknowledgement evidence to provider endpoint and runtime version hashes.
4. Recovery timestamps must be timezone-aware.
5. Added repeated-recovery p95 policy.
6–7. Added JSONL sequence numbers, replay/gap rejection, and independent chain-head pinning.
8. JSONL writes now use same-directory temporary files and atomic replacement; tests verify no temporary residue after success.
9. Added taxonomy policy schema.
10. Added a mixed positive/negative taxonomy fixture.
11. Added exact Wilson-threshold equality regression.
12. No new provider-labelled safe control was promoted; deterministic labels remain required. Expansion is represented by mixed controls and remains ongoing.
13–14. Added mutation MIME, byte-size, and deterministic transform-lineage bindings.
15. Added runtime environment hash to diagnostic receipts.
16. Added a reversible D:-drive relocation proposal without moving credentials or data.
17. PostgreSQL remains blocked because POSTGRES_DSN, psql, and Docker are unavailable; offline persistence is the substitute, not proof of PostgreSQL.
18. Required refs were refreshed above.
19. Trusted Spine remains deferred until exact final cross-project SHAs, runs, and grades exist.
20. Simulations, audit, full validation, CL Gate, explicit staging, push, and SHA verification close this round.

## Environment evidence

C: remains near 0.24 GB free and D: near 45.88 GB free. Ollama 0.31.2 is installed on D:. No installation or relocation was performed because an interrupted move at this capacity could destabilize the system. The checked-in plan excludes keys, private evidence, and user profiles.

## Exactly two microscopic simulations

1. A provider reports cancellation acknowledgement unavailable, then another explicitly rejects cancellation. A2 emits different blockers and binds both observations to endpoint/runtime hashes; neither is silently treated as acknowledged.
2. JSONL batch sequence 3 is presented as expected sequence 4 and with the wrong pinned chain head. Verification emits replay/gap and chain-pin blockers even though file bytes and record hashes are internally valid.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 submits complete evidence after a client timeout. Provider health recovers, but timestamps are timezone-naive and acknowledgement is unavailable. A2 returns INCOMPLETE/BLOCK; A3 displays that committed outcome without interpreting health as cancellation proof.
2. A1 supplies transformed hazard evidence with matching content hash but wrong MIME and size. A2 rejects provenance before model scoring. A3 consumes the rejection and cannot derive PASS from a model response.

## Growth auditor

Only A2-owned schemas, fixtures, judge/persistence code, tests, environment documentation, and this log are eligible. No secret, private ref, raw model payload, temporary cache, or A1/A3 code is included. New persistence controls detect replay and independently pinned chain divergence; runtime controls avoid cancellation overclaims. Remaining blockers are calibrated multimodal quality, safe storage migration, real PostgreSQL proof, and an exact final Trusted Spine.

## Exactly 20 Round 29 tasks

1. Add a schema for cancellation acknowledgement receipts.
2. Add acknowledged-state fixtures with provider-issued receipt hashes.
3. Reject acknowledged cancellation without a provider receipt hash.
4. Bind recovery probes to health-response hashes.
5. Add recovery p50/p95/max schema and sample minimums.
6. Add JSONL previous-sequence binding in addition to sequence number.
7. Add manifest timestamp and writer-version bindings.
8. Add interrupted-before-replace preservation regression.
9. Add manifest directory fsync capability reporting.
10. Add taxonomy policy application helper rather than manual keyword mapping.
11. Add taxonomy policy unknown-key rejection.
12. Add deterministic patterned and photographic safe-control fixtures.
13. Add safe-control fixture lineage schemas.
14. Add transform implementation-version hashes.
15. Recompute runtime binding from environment hash and reject mismatch.
16. Safely inventory only known cache directories for D:-migration sizing.
17. Run PostgreSQL transaction/RLS proof only with safe DSN/tooling.
18. Refresh main, active A1/A3, and strategy immediately before commit.
19. Generate Trusted Spine only after exact final SHAs, runs, and grades.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, CL Gate, push, and three-way SHA verification.
