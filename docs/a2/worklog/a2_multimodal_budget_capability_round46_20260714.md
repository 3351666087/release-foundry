# A2 Round 46 — multimodal budgets, capability cache, and provider comparison

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files changed. The round reviewed `origin/main` at `ccf6ce57890aaceabcb627c14d2e078674bd50ad`, A1 at `23072311c80395989adaba1bd164265bd67517b1`, A3 at `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`, strategy tree `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`, and A2 base `4c5a62f33d2dfa9f6d4b180e4151dd8306a35bcd`. A1 remains an evidence producer, A2 remains the only release-decision authority, and A3 remains a provenance/report consumer.

## Round 46 task disposition

1. Capability deadlines now detach the caller after expiry and do not falsely claim a Python thread terminated an in-flight provider request.
2. Deadline provenance records `worker_detached_after_deadline`.
3. Capability receipts distinguish transport, envelope, JSON, and schema-semantic observations.
4. Public-safe capability receipts are cached by runtime/model/prompt/schema binding.
5. Cache bindings include runtime version and model digest, so changed identities cannot reuse an old entry.
6. Plain JSON production trials are independent of native object-schema trials.
7. Plain JSON support cannot authorize native-schema promotion.
8. Provider-neutral request-count receipts cover local and cloud runs.
9. DashScope receipts record usage totals and cost state without raw payload retention.
10. Hard request ceilings are enforced; skipped requests do not inflate attempted counts.
11. Taxonomy-specific Wilson lower-bound policy is applied to cloud calibration.
12. Five deterministic benign-text safe controls extend specificity coverage.
13. Five hash-bound rotation/JPEG attack transformations extend robustness coverage.
14. Qwen plain JSON ran under a five-minute bound and remained blocked.
15. LLaVA plain JSON ran under the same bound and remained blocked.
16. Three-way output now includes all three pairwise summaries with count conservation.
17. Duplicate `(case_id, artifact_hash, repeat)` keys are rejected before indexing.
18. PostgreSQL was reprobed; DSN, psql, and Docker remain absent, while the 29-test/163-subtest offline substitute passed.
19. Exact A1/A2/A3 binding was rechecked and stale or mismatched candidates remain rejected.
20. Closeout includes exactly two micro simulations, two macro simulations, one growth audit, full gates, explicit staging, push, SHA equality, and a clean tree.

## Real runtime findings

The expanded matrix contains 35 cases: 15 safe and 20 attack, including five benign-text controls and five rotation/JPEG transformed attacks. Ollama `0.31.2` was tested with Qwen `qwen3-vl:4b` at digest `sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683` and LLaVA `llava:7b` at digest `sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081`.

Qwen attempted 6 case requests in its five-minute production window: 5 completed and 1 failed, with no eligible semantic denominator. LLaVA attempted 9: 8 completed, 1 failed, and 8 eligible safe observations, but no attack denominator. Both capability probes were unsupported under the tested prompt/schema/time binding, both exceeded interactive latency expectations, and neither model is promotion eligible.

DashScope `qwen-vl-plus` completed 35/35 real requests with 35 eligible observations, sensitivity `0.7`, specificity `0.933333`, balanced accuracy `0.816667`, and p95 latency `0.984s`. Cross-modal-conflict sensitivity was only `0.4`. The final receipt has `pricing_state=unavailable`, `estimated_cost_usd=null`, and `within_cost_budget=false`; unknown pricing is not represented as zero cost. Sensitivity, Wilson lower-bound, and pricing blockers make the result BLOCKED.

The three-provider comparison conserves all 35 cases. It records 8 agreement, 0 semantic disagreement, and 27 unavailable. Pairwise counts also conserve 35 for each of the three pairs. Unavailable observations are not reclassified as agreement or disagreement.

## Microscopic simulations (exactly 2)

1. Plain JSON is proven usable for a production trial while native object-schema capability remains unsupported. A2 may calibrate the plain JSON output independently, but the native-schema trial is skipped without a network call and receives no promotion authority.
2. A request budget reaches its maximum. `attempted = completed + failed`, budget-skipped cases do not increment attempted, pricing is unavailable, and provider failure cannot be converted into PASS; the final state remains BLOCKED.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits the expanded evidence bundle. A2 validates completeness, request and usage receipts, structured outputs, and policy metrics. DashScope sensitivity is `0.7`, so A2 issues BLOCK; A3 may display the provenance and decision but cannot recompute or upgrade it.
2. Local Qwen/LLaVA evidence is partly unavailable, producing 27 unavailable three-way comparisons. A1's receipt names `round62-source-candidate`, A2 has no exact shared candidate ID, and A3 expects `a3-golden-20260712-002`. A2 refuses a Trusted Spine and A3 must retain `integrity_invalid` rather than infer release readiness.

## PostgreSQL and Trusted Spine

`POSTGRES_DSN`, `psql`, and Docker are absent. The same-round real PostgreSQL proof is therefore BLOCKED. Offline fsync, atomic JSONL replacement, manifest reopen verification, and replay/rollback/fork-detection tests are substitutes only and do not establish real PostgreSQL persistence.

A1's public release receipt is bound to `5dd6a898a6771eaf67bf39246f256b579b4d2211`, not the current A1 ref. A2 has no shared candidate ID and A3 names a different candidate. Exact candidate and SHA binding is absent, so no authoritative Trusted Spine or Decision Ledger is generated.

## Growth audit

The growth auditor confirms all 20 Round 46 tasks have implementation, focused tests, real public-safe evidence, or an exact external blocker receipt. This round adds bounded request accounting, independent plain-JSON calibration, capability caching, transformed and benign-text controls, fail-closed unknown-cost semantics, pairwise conservation, and real cloud/local comparison. It does not treat a model as truth, unknown price as zero, detached caller threads as terminated provider work, unavailable comparisons as agreement, offline persistence as PostgreSQL, or mismatched candidates as a Trusted Spine. Commit, push, remote SHA equality, and clean-tree verification remain mandatory closeout gates and are verified operationally rather than self-referenced in this document.

## Round 47 narrow tasks (exactly 20)

1. Move local capability probes into a subprocess and test true process termination at deadline.
2. Define and test a provider cancellation-handle contract for adapters that support cancellation.
3. Add a JSON Schema for capability-cache receipts and validate every cache write.
4. Reject malformed, truncated, or hash-mismatched capability-cache entries fail closed.
5. Add a versioned provider-pricing-policy schema.
6. Bind pricing source, effective version, retrieval time, and content hash to cost receipts.
7. Add a blocker when a successful provider response omits required usage accounting.
8. Define minimum eligible counts for each transformed-attack perturbation class.
9. Emit per-rotation and per-JPEG-quality detection metrics with conservation tests.
10. Emit a dedicated benign-text false-positive metric and Wilson interval.
11. Build a smaller deterministic Qwen capability-probe fixture and measure timeout reduction.
12. Reduce the LLaVA probe prompt while preserving schema-semantic assertions.
13. Include capability-probe network calls in an explicit request-count receipt.
14. Prove total probe-plus-trial request conservation under success, failure, timeout, and skip.
15. Require pairwise summaries in the next comparison schema version.
16. Reject duplicate or ambiguous provider labels in the comparison builder.
17. Run repeated cloud calibrations and report metric and latency variance without treating repetition as truth.
18. Execute real PostgreSQL persistence proof if tooling appears; otherwise refresh the timestamped blocker and offline substitute.
19. Recheck exact A1/A2/A3 candidate binding after fetch and reject every stale ledger.
20. Run exactly two micro simulations, two macro simulations, one growth audit, full A2 gates, explicit commit/push, SHA equality, and clean-tree verification.
