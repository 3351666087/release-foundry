# A2 Round 47 — multimodal governance, release binding, and repeated cloud calibration

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`
A2 base: `186697204432f0f20bef76399ec30f7532cd3dd3`

## Scope and upstream review

Only A2-owned files are changed. The round reviewed `origin/main` at `ccf6ce57890aaceabcb627c14d2e078674bd50ad`, A1 at `23072311c80395989adaba1bd164265bd67517b1`, A3 at `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`, A2 tracking at `186697204432f0f20bef76399ec30f7532cd3dd3`, and strategy tree `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`. The first final A1 fetch attempt was reset by the network; a retry succeeded and confirmed the same A1 remote-tracking SHA. A1 remains the evidence producer, A2 remains the sole release-decision authority, and A3 remains a provenance/report consumer.

## Round 47 task disposition

1. Live Ollama capability probes now run in a spawn-safe subprocess and terminate/kill that worker at the caller deadline; injected generic callables retain the honest detached-thread receipt.
2. A provider cancellation-handle contract and public-safe cancellation receipt were added without claiming remote termination.
3. Capability-cache writes are validated against a dedicated JSON Schema.
4. Malformed, truncated, schema-invalid, future-dated, digest/runtime-drifted, and receipt-hash-mismatched cache entries fail closed.
5. A versioned provider-pricing-policy schema was added.
6. Cost provenance can bind provider, model, currency, rates, effective time, retrieval time, source hash, and content hash.
7. Successful provider responses with absent, boolean, non-object, or non-conserving usage are marked incomplete and block qualification.
8. Transformed-attack buckets now have a configurable minimum eligible count and a fail-closed blocker.
9. Rotation-degree and JPEG-quality sensitivity/Wilson metrics conserve classified transformed observations.
10. Benign-text false-positive rate and Wilson interval are emitted separately.
11. Capability probes use a deterministic 32×32 non-safety PPM fixture rather than the first production manifest case.
12. The LLaVA probe prompt was reduced while preserving structured semantic checks.
13. Capability-probe calls have their own request-count receipt.
14. Probe, trial, and combined receipts conserve success/failure/timeout/skip accounting.
15. Comparison v2 requires all three pairwise summaries.
16. Empty, whitespace-ambiguous, delimiter-containing, normalized-duplicate, and unknown partial-journal provider labels are rejected.
17. Two independent DashScope calibrations were executed and a public-safe variance receipt was generated without treating repetition as truth.
18. Real PostgreSQL tooling remained absent; the 29-test/163-subtest offline substitute passed and a same-round blocker receipt was refreshed.
19. Exact A1/A2/A3 binding was rechecked; stale and mismatched identities still prevent Trusted Spine generation.
20. This closeout contains exactly two micro simulations, two macro simulations, one growth audit, 20 next-round tasks, full gates, explicit staging, commit/push, SHA equality, and clean-tree verification as mandatory operational steps.

## Real provider findings

Ollama `0.31.2` was tested with `qwen3-vl:4b` (`sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683`) and `llava:7b` (`sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081`). Qwen's capability probe took about `68.13s` and remained unsupported under the tested token/prompt binding; its production trial took about `62.12s` and ended with an empty response. LLaVA's object-schema probe completed in about `46.73s`, but its production trial took about `35.12s` and produced nonempty invalid JSON. Both local candidates remain BLOCKED and neither is treated as truth.

DashScope `qwen-vl-plus` completed two independent 35-case runs. Run 1 sensitivity was `0.70`, specificity `0.933333`, balanced accuracy `0.816667`, p95 latency `1.249s`, and total usage `6250` tokens. Run 2 sensitivity was `0.65`, specificity `0.933333`, balanced accuracy `0.791667`, p95 latency `0.957s`, and total usage `6260` tokens. The sensitivity range was `0.05`, balanced-accuracy range `0.025`, p95 range `0.292s`, and token range `10`. Both runs are BLOCKED by sensitivity, sensitivity Wilson lower bound, and unavailable authoritative pricing. Repetition measures variance only; it does not establish ground truth.

The authoritative release-gate path now requires image candidates to provide a blocker-free multimodal qualification plus nonempty expected bindings. Exact fields such as manifest hash, model identity, prompt/schema hash, provider capability hash, or candidate SHA can be supplied by the caller; any mismatch blocks MM1. Provider failure, missing usage, unavailable pricing, stale artifacts, or absent expected bindings cannot become PASS.

## Microscopic simulations (exactly 2)

1. A live Ollama capability call exceeds its caller deadline. A2 terminates and, if necessary, kills the spawned worker, records `subprocess_terminated_after_deadline`, and does not claim remote request termination. For an injected non-process-safe callable, A2 records `worker_detached_after_deadline` instead of making a false cancellation claim.
2. A provider returns an HTTP-success envelope with boolean or non-conserving token usage. Usage becomes `missing_or_invalid`, qualification receives `dashscope_successful_response_usage_missing`, and an image-scoped release gate also blocks when usage/pricing or exact expected bindings are incomplete. No provider failure path can produce PASS.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a hash-bound image evidence bundle. A2 validates completeness, structure, usage, calibration, and caller-supplied manifest/model/prompt/schema bindings. The repeated cloud runs have sensitivity `0.70` and `0.65`, so A2 emits BLOCK. A3 may display the decision and provenance but cannot recompute, suppress, or upgrade it.
2. A1 still names `round62-source-candidate` with a stale receipt SHA, A2 has no exact shared candidate ID, A3 names `a3-golden-20260712-002`, and same-round PostgreSQL proof is absent. A2 refuses to generate a Trusted Spine or authoritative Decision Ledger; A3 must preserve the blocked integrity state.

## PostgreSQL and Trusted Spine

`POSTGRES_DSN`, `psql`, and Docker are absent. Real PostgreSQL persistence remains BLOCKED. Fsync, atomic JSONL replacement, manifest reopen verification, and replay/rollback/fork-detection tests are offline substitutes only.

A1's public receipt SHA `5dd6a898a6771eaf67bf39246f256b579b4d2211` does not match the reviewed A1 ref. A2 has no shared candidate ID and A3 names a different candidate. The Round 47 binding receipt therefore records `trusted_spine_generated=false`.

## Growth audit (exactly 1)

The growth auditor confirms all 20 Round 47 tasks have code, focused tests, real public-safe evidence, or an exact external-blocker receipt. The audit specifically rejects five misleading shortcuts: detached threads are not called terminated requests; two-provider consensus is not called three-way agreement; repeated cloud output is not called truth; offline persistence is not called PostgreSQL proof; and stale candidate identities are not called a Trusted Spine. Full gates, explicit staging, commit/push, local/tracking/remote SHA equality, and a clean worktree remain operational closeout checks and are not inferred from this document.

## Round 48 narrow tasks (exactly 20)

1. Add a deterministic subprocess-deadline test that records the child PID and proves it no longer exists after timeout.
2. Add bounded response-body byte limits to Ollama and OpenAI-compatible multimodal adapters.
3. Add tests for oversized, truncated, and decompression-amplified provider responses.
4. Add a request identifier and cancellation-handle correlation hash to every multimodal attempt receipt.
5. Add adapter-specific cancellation implementation for one protocol that exposes a real cancellable handle.
6. Add an authoritative pricing-policy loader to the DashScope CLI instead of accepting unbound numeric rate flags.
7. Reject pricing policies whose provider, model, region, currency, or effective window mismatches the run.
8. Add exact candidate SHA and dataset-manifest binding fields to the image release-gate CLI fixture.
9. Add a stale-qualified-artifact regression showing an otherwise passing image artifact blocks after any expected hash changes.
10. Add per-perturbation minimum counts to the versioned policy file rather than CLI-only configuration.
11. Add minimum benign-text eligible count and maximum false-positive/Wilson-upper policies.
12. Expand rotation/JPEG fixtures so every perturbation bucket meets a statistically meaningful minimum.
13. Add transformed-attack sensitivity thresholds and Wilson-lower blockers per bucket.
14. Build a Qwen capability probe profile that accounts for thinking tokens without accepting empty final content.
15. Measure warm and cold Ollama capability latency separately and bind the startup state to evidence.
16. Add a four-way comparison input while preserving explicit three-way and pairwise naming semantics.
17. Add a human-review receipt for pairwise agreement when the unavailable provider is the designated high-quality reference.
18. Execute real PostgreSQL persistence proof if DSN/client/runtime appears; otherwise refresh the exact blocker and offline proof.
19. Re-fetch A1/A2/A3/main, re-evaluate exact shared-candidate binding, and reject every stale ledger.
20. Run exactly two micro simulations, two macro simulations, one growth audit, full gates, explicit commit/push, SHA equality, and clean-tree verification.
