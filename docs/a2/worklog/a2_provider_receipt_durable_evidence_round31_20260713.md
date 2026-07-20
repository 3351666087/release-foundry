# A2 provider receipt and durable evidence controls — Round 31 (2026-07-13)

## Synchronization

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

Fresh fetch succeeded. Review preserves the contract: A1 supplies evidence, A2 alone decides, and A3 consumes committed A2 outcomes without recomputation.

## Round 31 disposition

1. Added a provider-neutral signature verification adapter contract; verifier exceptions reject.
2. Added issuer allowlist evaluation and unknown-issuer blocker.
3. Added nonce hash binding distinct from receipt hash and independent replay blocking.
4. Added replay-set snapshot hash verification and tamper regression.
5. Added health HTTP/body semantic consistency checks.
6. Added predecessor verifier schema and schema test.
7. JSONL manifests now bind an optional observed filesystem-volume identifier hash.
8. Atomic writer reopens exact bytes and verifies their hash after replacement.
9. Added explicit durability qualification schema; Windows remains `atomic_replace_verified_durability_unproven` while directory fsync is not exposed.
10. Taxonomy evaluation emits the canonical policy hash.
11. Denominator and Wilson thresholds receive range validation before evaluation.
12. Added deterministic stripe and checker PPM safe controls with exact hashes.
13. Photographic provenance now binds URL and license-evidence hashes without committing photo bytes.
14. PPM header dimensions are verified directly without an image decoder.
15. Runtime receipt and binding now include the observed Ollama-version hash.
16. Added and tested a D:-only, no-delete cache-copy dry-run script. It produced a plan, created no destination, and preserved the source.
17. PostgreSQL proof remains blocked honestly: `POSTGRES_DSN_PRESENT=False`, `PSQL_PRESENT=False`, `DOCKER_PRESENT=False`; no database claim is made.
18. Required refs are refreshed above and will be refreshed again immediately before commit.
19. Trusted Spine remains deferred until the exact final A1/A2/A3 SHAs, final results, and grades exist.
20. Simulations, audit, validation, CL Gate, commit, push, and three-way SHA verification close this round.

## Exactly two microscopic simulations

1. A cryptographically reported cancellation receipt uses an unapproved issuer and a replayed nonce. A2 emits both blockers and does not prove cancellation even though the adapter says `verified`.
2. A recovery probe returns HTTP 503 while its body claims `healthy`. A2 emits `runtime_recovery_health_status_semantic_mismatch` and blocks qualification.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 submits timeout evidence plus a signed receipt and persisted replay snapshot. A2 independently checks issuer, signature binding, nonce freshness, snapshot integrity, and policy; any mismatch yields INCOMPLETE/BLOCK. A3 renders only the committed A2 blocker set.
2. A1 submits synthetic safe controls and external photographic provenance. A2 verifies exact bytes, decoder-independent dimensions, URL/license hashes, taxonomy-policy hash, and calibration thresholds before decision. A3 consumes the committed decision and provenance without treating provider labels as truth.

## Growth auditor

The change set is limited to A2 judge/persistence code, A2 schemas, A2 tests, public-safe fixtures, a no-delete A2 script, and this worklog. It includes no key, token, private reference, restricted photographic bytes, or A1/A3 code. Commit and push are required before closure. Remaining gaps include real cryptographic provider adapters, OS-specific durable directory flush evidence, larger calibrated multimodal samples, PostgreSQL same-round proof, and final Trusted Spine.

## Exactly 20 Round 32 tasks

1. Implement an Ed25519 receipt verifier adapter using public keys only.
2. Add signature key-id binding and key-rotation policy.
3. Bind receipt nonce to request hash and cancellation operation id.
4. Persist replay-set snapshots through the JSONL manifest chain.
5. Add concurrent replay insertion race tests.
6. Add health response schema validation before semantic comparison.
7. Observe Windows volume serial safely and hash it without exposing raw identifiers.
8. Add injected post-replace corruption regression.
9. Add platform-specific directory flush capability discovery.
10. Bind taxonomy policy hash into the release decision provenance.
11. Reject non-finite taxonomy thresholds.
12. Add deterministic gradient and low-contrast safe controls.
13. Add provenance retrieval timestamp and content digest contract.
14. Add PNG and JPEG decoder-independent dimension tests.
15. Bind Ollama binary hash as well as version observation hash.
16. Extend cache dry-run planning to preserve relative paths and detect collisions.
17. Run PostgreSQL proof only if a safe DSN and tooling become available.
18. Refresh main, active A1/A3, and strategy immediately before commit.
19. Generate Trusted Spine only after exact final SHAs, results, and grades.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, CL Gate, push, and three-way SHA verification.
