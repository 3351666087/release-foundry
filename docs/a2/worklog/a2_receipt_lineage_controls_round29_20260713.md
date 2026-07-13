# A2 receipt, lineage, and deterministic control evidence — Round 29 (2026-07-13)

## Synchronization

`	ext
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
`

Fresh fetch succeeded. A1 evidence remains input, A2 remains sole decision authority, and A3 remains a consumer.

## Round 29 disposition

1–3. Added cancellation acknowledgement schema, acknowledged fixture, provider receipt hash, and missing-receipt rejection.
4–5. Recovery summaries bind health-response hashes and publish p50/p95/max with minimum sample gates.
6–7. JSONL manifests bind previous sequence, creation timestamp, and writer version.
8. Atomic replacement regression proves the old target is not partially appended and no temp residue remains after success; injected OS-level crash testing remains a later hardening task.
9. Manifest reports directory fsync capability as `not_exposed` rather than claiming durability.
10–11. Added taxonomy policy application helper and unknown-key rejection.
12–13. Added deterministic patterned and curated photographic safe-control lineage fixtures and schema; provider labels are forbidden.
14. Safe-control and mutation lineage bind transform implementation-version hashes.
15. Added runtime binding recomputation including environment hash and mismatch rejection.
16. Inventoried only named cache directories without recursive unknown-path scanning, credential scanning, modification, or deletion.
17. PostgreSQL remains unavailable: no DSN, psql, or Docker; offline tests remain substitute evidence only.
18. Required refs refreshed above.
19. Trusted Spine remains deferred pending exact final cross-project SHAs, runs, and grades.
20. Required simulations, audit, validation, CL Gate, commit, push, and SHA verification close this round.

## Exactly two microscopic simulations

1. Provider marks cancellation acknowledged but omits its receipt hash. A2 keeps equest_cancellation_proven=false and emits provider_cancellation_receipt_missing.
2. A valid JSONL file claims sequence 3 but previous sequence 1. A2 rejects the lineage even when file and record hashes match; directory fsync remains explicitly unproven.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 submits timeout evidence plus provider cancellation status but no receipt. A2 emits INCOMPLETE/BLOCK and A3 displays that committed decision without interpreting the status string as proof.
2. A1 submits patterned and photographic safe controls with deterministic/human lineage. A2 may count them only after schema and hash validation; model labels are not used as truth. A3 consumes the resulting committed metrics without recomputation.

## Growth auditor

The change set is A2-only: schemas, public-safe fixtures, judge/persistence code, tests, cache inventory, and this log. No credential, private evidence, raw provider response, or cross-project code is staged. Remaining blockers include real PostgreSQL proof, OS-level crash/fsync durability, calibrated high-quality multimodal performance, safe cache migration, and final Trusted Spine generation.

## Exactly 20 Round 30 tasks

1. Add provider receipt issuer and signature-algorithm bindings.
2. Add cancellation receipt freshness windows.
3. Reject replayed provider cancellation receipt hashes.
4. Add health-response endpoint and status-code bindings.
5. Add recovery summary schema tests for insufficient hash coverage.
6. Add manifest previous-manifest sequence/hash cross-validation helper.
7. Add writer build hash to JSONL manifests.
8. Add injectable atomic-replace failure regression preserving old bytes.
9. Add Windows directory durability capability documentation.
10. Add taxonomy policy schema-version validation in helper.
11. Add taxonomy policy threshold type validation before evaluation.
12. Generate real deterministic patterned image bytes and hashes.
13. Add licensed/public-safe photographic control provenance without committing restricted bytes.
14. Bind safe-control dimensions and MIME types.
15. Repair the Round 25 runtime fixture to contain a correctly recomputed environment-aware binding hash.
16. Measure only approved D:-migration cache directories after confirming no credentials are inside.
17. Run PostgreSQL proof only when safe DSN/tooling becomes available.
18. Refresh main, active A1/A3, and strategy immediately before commit.
19. Generate Trusted Spine only after exact final SHAs, results, and grades.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, CL Gate, push, and three-way SHA verification.

