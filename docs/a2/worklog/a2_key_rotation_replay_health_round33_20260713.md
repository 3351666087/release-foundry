# A2 key rotation, replay persistence, and health governance — Round 33 (2026-07-13)

## Synchronization and cross-project review

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = 8a92d4169ae0da96247be679146dd0f027031a59
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

A3 advanced from `c3c3c9e` to `8a92d41` with release-candidate comparison UI and storage. Review confirms A3 is comparing and presenting committed release candidates; A2 must continue to provide the sole governed decision and provenance rather than letting A3 recompute it.

## Round 33 disposition

1. Receipt key policies now enforce effective time and expiry.
2. Added revoked, not-yet-active, and expired key regressions.
3. Bound signature algorithm and canonicalization version into the signed identity.
4. Added atomically replaced persistent replay snapshots with OS locking.
5. Six-process contention admits exactly one replay nonce.
6. Recovery health evidence now binds accepted schema versions.
7. Added hashed Windows volume serial observation when the platform API is available, with safe fallback.
8. Added parent-directory flush evidence that does not claim Windows durability when unavailable.
9. Legacy recovery envelopes missing taxonomy-policy hash fail closed under the governed schema.
10. Changing taxonomy-policy hash under the same idempotency key produces a conflict.
11. Existing per-taxonomy positive/negative sample and Wilson confidence gates were exercised and retained.
12. Added brightness, noise, blur, and text-free deterministic safe controls.
13. Added public-safe hashed controls covering five attack/safety taxonomy classes.
14. Added provenance retrieval failure and content-digest mismatch regressions.
15. Real Ollama executable observation was attempted; `OLLAMA_PRESENT=False`, so no binary hash claim is made.
16. Candidate multimodal benchmarking remains prerequisite-gated because no Ollama runtime/model is present in this environment; the prior specificity and latency blockers remain authoritative.
17. PostgreSQL proof remains prerequisite-gated: `POSTGRES_DSN_PRESENT=False`, `PSQL_PRESENT=False`, `DOCKER_PRESENT=False`.
18. Main, A1, A3, and strategy refs were refreshed, including the new A3 head.
19. Trusted Spine remains deferred until exact final A1/A2/A3 SHAs, results, and grades exist.
20. Simulations, growth audit, full tests, fixture check, CL Gate, explicit staging, commit, push, and SHA verification close this round.

## Exactly two microscopic simulations

1. Six independent Python processes race to admit the same nonce into one persistent replay snapshot. The OS lock and atomic replacement admit exactly one process and reject five, proving restart/process boundaries cannot turn replay into acceptance.
2. A cryptographically valid receipt is evaluated before key activation, at expiry, after revocation, and with an altered canonicalization identifier. Each condition yields a distinct blocker and never becomes verified.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 supplies a signed cancellation receipt after a worker restart. A2 reconstructs the persistent replay state, checks key timing, algorithm/canonicalization identity, request binding, and policy, then commits the only decision. A3 compares releases using that committed outcome and cannot reinterpret the receipt.
2. A1 supplies expanded safe and attack controls plus photographic provenance. A2 applies taxonomy sample/confidence gates, provenance retrieval/digest validation, health schema-version governance, runtime binding, latency, and specificity requirements. A3 may compare candidate reports but cannot promote a candidate blocked by A2.

## Growth auditor

The diff contains only A2-owned services, schemas, tests, public-safe fixtures, and this worklog. It contains no credential, provider raw payload, private reference, restricted image, or A1/A3 source edit. Commit and push are mandatory. Honest remaining gaps are a real available Ollama runtime with candidate multimodal models, larger labeled coverage with measured confidence, same-round PostgreSQL persistence, stronger Windows durability primitives, and the final SHA-matched Trusted Spine.

## Exactly 20 Round 34 tasks

1. Add key-policy overlap and rotation handoff validation.
2. Reject ambiguous duplicate issuer/key-id mappings.
3. Add canonicalization test vectors shared across adapters.
4. Bind replay snapshot predecessor hash and sequence number.
5. Add crash injection between replay fsync and atomic replace.
6. Add bounded lock wait and lock-timeout fail-closed evidence.
7. Validate health schema payload fields in addition to version.
8. Add health downgrade/upgrade compatibility policy hashes.
9. Add Windows volume API error classification without raw identifiers.
10. Add durability receipts separating file fsync, replace, and directory flush.
11. Add an explicit safe migration helper for legacy empty taxonomy-policy identity.
12. Add taxonomy class allowlist and unknown-class blocking.
13. Generate more deterministic safe controls with exact semantic labels.
14. Add balanced attack/safe examples for every governed taxonomy.
15. Add provenance freshness and maximum-age policy.
16. Discover or safely install an Ollama-compatible runtime on D: when feasible.
17. Benchmark at least one available multimodal candidate or record exact prerequisite failure.
18. Run PostgreSQL proof only when DSN and tooling are safely available.
19. Refresh refs and generate Trusted Spine only after final exact SHAs and grades.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, CL Gate, push, and three-way SHA verification.
