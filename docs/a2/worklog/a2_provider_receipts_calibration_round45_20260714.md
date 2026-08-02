# A2 Round 45 ? provider receipts and balanced multimodal calibration

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files changed. Fetch succeeded and the round reviewed `origin/main` `ccf6ce57890aaceabcb627c14d2e078674bd50ad`, A1 `23072311c80395989adaba1bd164265bd67517b1`, A3 `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`, strategy tree `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`, and A2 base `2d1899bb8ceb4aee2aab275d83419f22aeea2986`. A1 remains evidence producer, A2 remains the only release-decision authority, and A3 remains a consumer.

## Round 45 task disposition

1. OpenAI-compatible HTTP failures now emit the provider-neutral transport receipt.
2. DashScope-compatible 401/429/503/timeout/reset/refusal taxonomy tests pass without retaining bodies.
3. A shared duration receipt records provider-native Ollama duration or wall-clock fallback.
4. Schema rules reject cancellation receipts on completed or eligible trials and require fail-closed state.
5. Capability receipts bind runtime, prompt, and output-schema hashes.
6. Capability probing has its own explicit timeout/run budget and attempt receipts.
7. Unsupported native schema matrices skip by default; diagnostic override is explicit.
8. Every skipped trial has a public-safe capability skip receipt proving no network call started.
9. Native plus fallback attempts have an explicit one-or-two total limit.
10. Per-case wall budget is independent of per-model budget and fails closed.
11. The expanded distribution contains five cases for each of three attack taxonomies.
12. It adds ten text-free safe controls across distinct deterministic visual patterns.
13. Qwen was run on all 25 cases; its capability probe exhausted 60 seconds and all matrix cases were correctly skipped.
14. LLaVA was run identically; its probe also exhausted 60 seconds and all cases were correctly skipped.
15. DashScope ran 25 requests under a 180-second ceiling with no retry and no credential persistence.
16. Three-way summary conservation is enforced in code and tests.
17. Review receipt identity no longer depends on unrelated evidence/artifact-envelope changes; deterministic dedup is tested.
18. PostgreSQL was reprobed: DSN, psql, and Docker remain absent; the 29-test/163-subtest offline substitute passed.
19. A1/A2/A3 exact binding remains absent, so no Trusted Spine was generated.
20. Refs were fetched; exactly two micro and two macro simulations, one growth audit, fixtures, tests, both CL gates, secret/diff checks, explicit staging, push, SHA equality, and clean-tree verification form the closeout.

## Real runtime findings

Ollama `0.31.2` was bound to Qwen `qwen3-vl:4b` at `sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683` and LLaVA `llava:7b` at `sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081`. Each independent capability probe had a 60-second budget. Both ended `unsupported`; therefore 25/25 native-schema trials for each model were skipped with `network_call_started=false`, `promotion_eligible=false`, and no semantic metric contribution. This prevents the previous ten-to-fifteen minute fallback matrices from wasting compute or creating misleading eligible data.

DashScope `qwen-vl-plus` produced 25/25 eligible structured observations: 10 safe, 15 attack, sensitivity `0.666667`, specificity `1.0`, balanced accuracy `0.833333`, and p95 `0.974s`. It remains BLOCKED because sensitivity and its Wilson lower bound miss policy. The three-way comparison is 0 agreement, 0 semantic disagreement, and 25 unavailable because fewer than two providers were eligible. No review receipt was emitted. Provider/model observations are not truth and no model was promoted.

## Microscopic simulations (exactly 2)

1. A native-schema capability probe reports unsupported. The matrix creates a skip receipt, starts no case network call, records failed/not-attempted/null semantics, and cannot PASS or enter calibration denominators.
2. A completed provider response is maliciously paired with a cancellation receipt. JSON Schema rejects the trial; cancellation evidence is legal only for a failed, non-eligible, null-observation budget exhaustion.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete 25-case evidence bundle while only DashScope is eligible. A2 can use cloud output as calibration evidence but sensitivity policy produces BLOCK; A3 can display that decision but cannot upgrade it.
2. A1 names `round62-source-candidate` at a SHA not matching the current A1 ref, A2 has no shared candidate ID, and A3 names `a3-golden-20260712-002`. A2 refuses Trusted Spine generation and A3 must expose incomplete provenance.

## PostgreSQL and Trusted Spine

`POSTGRES_DSN`, `psql`, and Docker are absent. The same-round real PostgreSQL proof is BLOCKED; offline persistence evidence is explicitly not promoted to a PostgreSQL claim. Candidate IDs and SHAs are not exactly shared across A1/A2/A3, so `trusted_spine_generated=false` remains mandatory.

## Growth auditor

The auditor confirms all 20 Round 45 tasks have implementation, tests, real public-safe evidence, or exact external blocker evidence. The round materially reduced wasted local compute, preserved fail-closed eligibility, increased taxonomy coverage, improved specificity evidence, and made transport, duration, capability, skip, cancellation, and review routing independently auditable. It did not reinterpret cloud accuracy as truth, skipped trials as eligible, unavailable providers as disagreement, offline persistence as PostgreSQL, or mismatched candidates as a Trusted Spine.

## Round 46 narrow tasks (exactly 20)

1. Add a capability-probe worker cancellation mechanism that stops an in-flight local request at budget expiry.
2. Record whether probe timeout was enforced client-side, provider-side, or by worker termination.
3. Split capability support into transport support, envelope validity, JSON validity, and schema-semantic validity.
4. Cache capability receipts by model digest plus runtime/prompt/schema hash with an expiry policy.
5. Reject stale capability cache entries after Ollama version or model digest changes.
6. Add a plain-JSON production mode separate from diagnostic fallback and calibrate it independently.
7. Prevent plain-JSON capability from authorizing native-schema promotion.
8. Add a provider-neutral request-count receipt for local and cloud calibration runs.
9. Add DashScope usage-token and bounded estimated-cost receipts without storing raw payloads.
10. Enforce a hard maximum cloud request count at schema and runtime levels.
11. Add taxonomy-specific Wilson lower-bound blockers to the 25-case DashScope run.
12. Add five hard safe controls containing benign text to complement no-text specificity.
13. Add five attack controls with rotation/compression perturbations while preserving labels and hashes.
14. Run Qwen plain-JSON mode under a five-minute bound on the expanded set.
15. Run LLaVA plain-JSON mode under the identical bound and distribution.
16. Build pairwise summaries alongside three-way summaries and prove pairwise/three-way count conservation.
17. Add duplicate case-key rejection before three-way indexing to prevent silent overwrite.
18. Execute real PostgreSQL proof if DSN/tooling appears; otherwise rerun and timestamp the offline substitute and blocker.
19. Recheck exact A1/A2/A3 candidate binding after fetch and refuse all stale ledgers.
20. Run exactly two micro simulations, two macro simulations, one growth audit, full tests, fixtures, both CL gates, secret scan, explicit commit/push, SHA equality, and clean tree.
