# A2 Round 48 — bounded multimodal execution and exact release binding

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`
A2 base: `6eaa7a2296f6b88539f776ef4ff13f6baf886463`

## Scope and upstream review

Only A2-owned files are changed. A final fetch succeeded. Reviewed refs are main `ccf6ce57890aaceabcb627c14d2e078674bd50ad`, A1 `23072311c80395989adaba1bd164265bd67517b1`, A2 tracking `6eaa7a2296f6b88539f776ef4ff13f6baf886463`, A3 `8bcbd3a60b8b35366267bee5d45f2f031e811eb9` on `origin/agent/a3-main-contract-alignment-v2`, and strategy tree `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`. The former A3 remote branch was deleted; no stale name was treated as current.

## Round 48 task disposition

1. A deterministic local HTTP deadline test records the spawned child PID and proves that PID is gone after timeout.
2. Ollama and OpenAI-compatible response reads are capped at 1 MiB by default.
3. Content-Length overflow, actual overflow, truncation, gzip amplification/truncation, malformed UTF-8/JSON, non-object JSON, and unsupported encoding fail closed.
4. Every real attempt has a public-safe request correlation hash; cancellation receipts bind to the final attempt without retaining raw request IDs.
5. The Ollama adapter uses a process handle that is terminated and then killed if required. This proves local worker termination only and never claims remote inference cancellation.
6. DashScope live calibration loads an authoritative, schema-validated, content-hash-bound pricing policy.
7. Provider, model, region, currency, source class, effective time, expiry, and policy hash mismatches are rejected.
8. Image release-gate CLI input now requires exact candidate SHA and dataset-manifest hash bindings.
9. A stale otherwise-qualified multimodal artifact blocks after candidate SHA changes.
10. Perturbation minimum counts are versioned policy fields and participate in policy hashing when non-default.
11. Benign-text minimum count, false-positive ceiling, and Wilson-upper ceiling are versioned policy fields.
12. Round 48 adds 15 distinct-source transformed attacks: three samples each for rotation 5/10 degrees and JPEG quality 40/60/80.
13. Per-bucket sensitivity and Wilson-lower thresholds emit bucket-specific blockers.
14. Qwen thinking content is hashed and observable, but thinking-only or empty final content remains ineligible after the bounded retry.
15. Cold and warm Ollama latency are reported separately and startup class is bound per trial.
16. A schema-validated four-way comparison preserves explicit four-way, three-way-with-unavailable, pairwise-with-unavailable, disagreement, and unavailable names plus all six pairwise summaries.
17. Pairwise or three-way agreement cannot bypass review when the designated high-quality reference is unavailable.
18. Real PostgreSQL proof remains externally blocked because DSN, `psql`, and Docker are absent; the 39-test/163-subtest persistence substitute passed and the blocker receipt was refreshed.
19. Main/A1/A2/A3 were fetched, exact shared-candidate binding was rechecked, and stale ledger identities remain rejected.
20. Closeout contains exactly two micro simulations, two macro simulations, one growth audit, and exactly 20 next-round narrow tasks.

## Real provider status

The Windows CurrentUser `DASHSCOPE_API_KEY` is present with the expected shape. A prior same-session PNG probe to `qwen-vl-plus` succeeded with a 2xx-class response, non-empty content, complete usage, about 0.514 seconds latency, and no retained response body. The key and raw provider payload were not printed, copied into evidence, deleted, overwritten, or staged.

This connectivity proof does not promote the provider. The latest full DashScope calibration remains blocked by sensitivity and authoritative-pricing requirements. Existing real local LLaVA/Qwen results also remain blocked for false positives, empty/invalid final content, hallucination risk, and latency.

## Microscopic simulations (exactly 2)

1. An Ollama-compatible local endpoint sleeps past the caller deadline. A2 terminates/kills its spawned worker, confirms the captured PID is no longer running, emits a fail-closed transport error, and makes no claim that a remote model server stopped inference.
2. An HTTP-success provider returns a gzip-compressed body that expands beyond the configured limit, or a Qwen envelope containing thinking text but no final content. A2 records the appropriate bounded-read or empty-response failure, excludes the attempt from promotion metrics, and cannot produce PASS.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 supplies a complete image evidence bundle plus candidate SHA and manifest hash. A2 validates evidence integrity, invokes the real judge, checks usage/pricing/calibration and exact bindings, then emits structured findings and PASS/BLOCK/INCOMPLETE. Any provider failure or stale qualified artifact yields BLOCK/INCOMPLETE. A3 consumes the signed decision and provenance without recomputing it.
2. A1 names `round62-source-candidate` with a receipt SHA that does not match the reviewed A1 ref; A2 has no shared candidate ID; A3 names `a3-golden-20260712-002`; same-round PostgreSQL proof is absent. A2 refuses to generate a Trusted Spine or authoritative Decision Ledger, and A3 must preserve that blocked state.

## Growth audit (exactly 1)

The growth audit confirms the round materially narrows false promotion paths: bounded response reads, exact release bindings, authoritative pricing provenance, per-bucket calibration policy, designated-reference review, and four-way naming are all executable contracts with tests. It also rejects overclaiming: local PID disappearance is not remote cancellation, a successful connectivity probe is not calibration, expanded fixtures are not model quality, offline persistence is not PostgreSQL proof, and repeated model agreement is not truth. Commit/push and SHA/clean-tree checks remain operational closeout gates.

## Round 49 narrow tasks (exactly 20)

1. Run the expanded 50-case Round 48 manifest against DashScope under a reviewed request/cost cap.
2. Publish a public-safe calibration summary for each new rotation/JPEG bucket without provider text.
3. Add bootstrap confidence intervals comparing Round 47 and Round 48 transformed-attack sensitivity.
4. Add a policy minimum requiring at least three distinct source-case hashes per perturbation bucket.
5. Reject duplicate-source perturbation inflation even when artifact hashes differ.
6. Add a cancellation receipt field distinguishing pre-invoke budget expiry from in-flight local worker termination.
7. Prove the Ollama worker process tree has no surviving descendants after timeout.
8. Add bounded streaming-response support without assembling an unbounded intermediate buffer.
9. Add Brotli handling only if an adapter advertises and tests an explicit bounded decoder.
10. Add OpenAI-compatible request-id header hashing without retaining raw headers.
11. Add DashScope request-id correlation hashing from response metadata without public raw IDs.
12. Bind four-way comparison artifacts to prompt/schema/model capability hashes.
13. Add four-way partial-journal resume and duplicate-key regression tests.
14. Add human-review receipt conservation tests across mixed disagreement/reference-unavailable cases.
15. Add a reviewer disposition that explicitly records “reference unavailable; collect more evidence.”
16. Add release-gate tests requiring the latest human-review receipt when designated-reference review is pending.
17. Execute real PostgreSQL proof if a DSN/runtime appears; otherwise rerun and refresh exact blockers.
18. Generate a new Trusted Spine only after A1/A2/A3 expose one exact shared candidate identity.
19. Re-fetch main/A1/A2/A3 and reject any ledger bound to previous Round 48 content hashes.
20. Run exactly two micro simulations, two macro simulations, one growth audit, full gates, explicit commit/push, SHA equality, and clean-tree verification.
