# A2 cryptographic and runtime binding — Round 32 (2026-07-13)

## Synchronization

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

Fresh fetch succeeded. A1 remains evidence producer, A2 remains the sole decision authority, and A3 consumes committed A2 decisions without recomputation.

## Round 32 disposition

1. Added Ed25519 receipt verification using public-key bytes only.
2. Bound issuer, key id, active key state, and canonical key-policy hash.
3. Bound receipts to request hash and cancellation operation-id hash.
4. Bound replay-set snapshot hashes into JSONL manifests.
5. Added a thread-safe concurrent replay admission regression.
6. Added recovery health-response schema-validity evidence and fail-closed blockers.
7. Added a public-safe hashed filesystem-volume observation without exposing its raw identifier.
8. Added injected post-replace corruption detection.
9. Added platform directory-flush capability discovery without overstating Windows durability.
10. Bound taxonomy-policy hash into decision identity, recovery envelope, and recovery reconstruction.
11. Rejected NaN and infinite taxonomy thresholds.
12. Added deterministic gradient and low-contrast PPM safe controls.
13. Bound provenance retrieval timestamp and content digest.
14. Added explicit decoder-independent PNG IHDR and JPEG SOF dimension tests.
15. Bound Ollama binary hash alongside the version-observation hash.
16. Cache dry-run now preserves relative paths and checks destination collisions; duplicate basenames in separate directories remained distinct, the source remained intact, and no destination was created.
17. PostgreSQL proof remained prerequisite-gated: `POSTGRES_DSN_PRESENT=False`, `PSQL_PRESENT=False`, `DOCKER_PRESENT=False`.
18. Required refs were refreshed before final validation and will be refreshed again before commit.
19. A new Trusted Spine is deferred until exact final A1/A2/A3 SHAs, run results, and grades exist.
20. Full tests, generated-fixture check, diff check, CL Gate, explicit staging, commit, push, and SHA verification close the round.

## Exactly two microscopic simulations

1. Eight workers submit the same signed receipt nonce concurrently. The locked replay set admits exactly one and rejects seven; replay pressure cannot create multiple accepted observations or a PASS.
2. An atomic JSONL replacement succeeds and an injected hook corrupts the destination before verification. Reopening the exact bytes detects the hash mismatch and raises an error rather than recording durable evidence.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 supplies a cancellation evidence bundle and Ed25519 receipt. A2 verifies key policy, request/operation binding, replay state, provider status, and policy; inactive keys, mismatches, replay, malformed output, or provider failure remain BLOCK/INCOMPLETE. A3 displays only the committed A2 result.
2. A1 supplies safe multimodal controls plus provenance and runtime evidence. A2 checks deterministic bytes, decoder-independent dimensions, taxonomy-policy hash, health schema validity, Ollama binary/version binding, latency, specificity, and sample gates. A3 cannot promote the model by reinterpreting provider labels.

## Growth auditor

The round changes only A2 judge/persistence code, A2 schemas, A2 tests, public-safe fixtures, one D:-only no-delete dry-run script, and this worklog. It contains no credential, raw provider payload, private reference, restricted image, or A1/A3 source change. The controls increase verifiability without granting provider output release authority. Remaining honest gaps are the current multimodal model's specificity/latency/hallucination failures, broader calibrated samples, real same-round PostgreSQL persistence evidence, OS-level Windows directory durability proof, and a final SHA-matched Trusted Spine.

## Exactly 20 Round 33 tasks

1. Add receipt key-policy effective-time and expiry validation.
2. Add revoked-key and not-yet-active-key regressions.
3. Bind signature algorithm and canonicalization version into receipt identity.
4. Persist replay snapshots across process restart with atomic locking evidence.
5. Add multi-process replay contention proof where supported.
6. Add health schema version compatibility and downgrade rejection.
7. Add Windows volume observation using a platform API when safely available.
8. Add parent-directory durability evidence without claiming unsupported guarantees.
9. Add recovery migration tests for legacy envelopes lacking taxonomy-policy hash.
10. Add explicit taxonomy-policy hash change idempotency-conflict tests.
11. Add taxonomy minimum-class-sample gates with confidence intervals.
12. Expand deterministic safe controls across brightness, noise, blur, and text-free classes.
13. Expand attack controls across every supported taxonomy class.
14. Add photographic provenance retrieval failure and digest mismatch regressions.
15. Observe real Ollama executable hash during a controlled runtime test.
16. Benchmark candidate multimodal models against latency and specificity gates.
17. Run real PostgreSQL persistence proof only when safe prerequisites exist.
18. Refresh main, active A1/A3, and strategy immediately before commit.
19. Generate Trusted Spine only after exact final SHAs, results, and grades.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, CL Gate, push, and three-way SHA verification.
