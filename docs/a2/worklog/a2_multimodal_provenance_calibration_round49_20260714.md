# A2 Round 49 — multimodal provenance, review conservation, and real calibration

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`
A2 base: `564d4b0ac905e73022fd444adbb1dfbbdf441e3b`

## Scope and upstream review

Only A2-owned files are changed. The final fetch reviewed:

- main: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- A1 active branch: `23072311c80395989adaba1bd164265bd67517b1`
- A2 tracking branch: `564d4b0ac905e73022fd444adbb1dfbbdf441e3b`
- A3 active branch: `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

The A1 receipt still names `round62-source-candidate` but binds an older SHA. A2 still has no exact shared candidate ID. A3 still names `a3-golden-20260712-002`. These are not one release identity, so A2 did not generate a Trusted Spine or authoritative Decision Ledger.

## Round 49 task disposition

1. Ran the expanded 50-case manifest against the real DashScope `qwen-vl-plus` endpoint under a 50-request and 600-second ceiling.
2. Added a public-safe aggregate containing every rotation/JPEG bucket without provider text, raw request IDs, signed URLs, or secrets.
3. Added deterministic bootstrap comparison code with 95% intervals. Actual Round 47 versus Round 49 execution is honestly blocked because retained Round 47 observations predate perturbation and source-hash metadata.
4. Added a minimum of three distinct source-case hashes per perturbation bucket.
5. Deduplicated perturbation denominators by source-case hash and added duplicate-source inflation blockers.
6. Added cancellation stages distinguishing pre-invoke expiry, in-flight local worker termination, and detached caller wait.
7. Added a real descendant-process termination test for the Ollama worker tree.
8. Bounded provider reads to fixed-size chunks and rejected overflow before unbounded assembly.
9. Brotli remains fail-closed as `response_encoding_unsupported` because no explicitly advertised bounded decoder is present.
10. Added precedence-bound hashing for OpenAI-compatible request-ID headers without retaining raw header values.
11. Added DashScope envelope request-ID hashing after header precedence, again without retaining raw IDs.
12. Bound four-way comparisons to prompt, output-schema, and provider-capability hashes.
13. Added partial-journal resume, final-over-partial precedence, and duplicate-key rejection.
14. Added queue/review conservation across semantic disagreement and designated-reference-unavailable cases.
15. Added the exact reviewer disposition `reference unavailable; collect more evidence`.
16. Required the latest human-review receipt hash when designated-reference review remains pending.
17. Re-probed PostgreSQL. DSN, `psql`, and Docker are absent; the 39-test/163-subtest offline persistence substitute passed.
18. Refused Trusted Spine generation because A1/A2/A3 do not expose one exact shared candidate identity.
19. Re-fetched main/A1/A2/A3 and added stale A1 SHA, A3 SHA, grades hash, A2 SHA, and decision hash rejection.
20. Completed exactly two microscopic simulations, two macroscopic simulations, one growth audit, the full A2 suite, fixtures, both CL gates, and pre-commit hygiene.

## Real DashScope calibration

The Windows CurrentUser `DASHSCOPE_API_KEY` was reused through the environment. Its value was not printed, written into source, copied into evidence, deleted, or overwritten.

The real 50-case run produced 49 completed requests, one failed request, and 48 eligible observations. It remains `blocked`.

- sensitivity: `0.6364`, Wilson 95% interval `[0.4662, 0.7781]`
- specificity: `0.9333`, Wilson 95% interval `[0.7018, 0.9881]`
- balanced accuracy: `0.7848`, interval `[0.5840, 0.8831]`
- latency: median `2.585s`, p95 `10.373s`, max `17.184s`
- usage: 9,119 total tokens with complete accounting
- pricing: unavailable; no zero-cost assumption was made

The run is blocked by invalid structured output, a provider failure, p95 latency, sensitivity, insufficient distinct sources in several buckets, duplicate-source inflation at 10-degree rotation, aggregate perturbation sample coverage, and unavailable authoritative pricing.

Bucket observations are source-hash deduplicated:

| Bucket | Raw | Distinct sources | Eligible | Detected | Sensitivity |
|---|---:|---:|---:|---:|---:|
| rotation 2° | 1 | 1 | 1 | 0 | 0.0000 |
| rotation 5° | 3 | 3 | 3 | 1 | 0.3333 |
| rotation 6° | 1 | 1 | 1 | 0 | 0.0000 |
| rotation 10° | 4 | 3 | 3 | 2 | 0.6667 |
| JPEG 40 | 3 | 3 | 3 | 3 | 1.0000 |
| JPEG 53 | 1 | 1 | 1 | 1 | 1.0000 |
| JPEG 60 | 2 | 2 | 2 | 1 | 0.5000 |
| JPEG 80 | 3 | 3 | 3 | 2 | 0.6667 |

Connectivity and nontrivial accuracy do not equal promotion. Provider failure cannot become PASS, and the wide bucket intervals prohibit strong robustness claims.

## PostgreSQL and persistence

`POSTGRES_DSN`, `psql`, and Docker were all absent in this round. Therefore:

- same-round real PostgreSQL proof: blocked
- offline substitute: `39 passed, 163 subtests passed`
- PostgreSQL parity claim: not made

The offline subset covers JSONL atomic replacement, file synchronization behavior, manifest reopen verification, replay rollback/fork detection, and the human-review store.

## Microscopic simulations (exactly 2)

1. A bounded OpenAI-compatible response exceeds the configured limit while streaming chunks. A2 reads at most the limit plus one byte, emits `response_body_too_large`, records no raw body or raw request ID, excludes the observation, and cannot return PASS.
2. Four-way comparison resumes from a partial journal containing an already completed provider/case/repeat key. The final observation wins when valid; duplicate partial keys are rejected; missing capability bindings fail closed; pending designated-reference review requires the latest human-review receipt hash.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete evidence bundle for an image candidate. A2 verifies integrity, scope, source hashes, prompt/schema/capability identity, invokes a real judge, validates structured output, applies calibration and policy, and emits PASS/BLOCK/INCOMPLETE. A timeout, provider failure, malformed output, missing pricing, or stale binding cannot become PASS. A3 consumes A2's decision and provenance without recomputing it.
2. A1 names `round62-source-candidate` with a stale receipt SHA, A2 has no shared candidate ID, A3 names `a3-golden-20260712-002`, the real multimodal run is blocked, and same-round PostgreSQL proof is absent. A2 refuses the Trusted Spine and Decision Ledger. A3 must display the blocked/incomplete provenance rather than reuse an older ledger.

## Growth audit (exactly 1)

The growth audit confirms measurable progress in provenance and false-promotion resistance: source-hash deduplication, bounded reads, request-ID hashing, worker-tree termination evidence, capability-bound four-way comparison, partial resume, review conservation, latest-review binding, and stale Trusted Spine rejection all have executable tests. The real DashScope run also replaces speculation with measured quality and latency. The audit rejects overclaiming: one real provider is not truth, 100% in a three-sample bucket is not robustness, a completed HTTP request is not valid structured evidence, offline persistence is not PostgreSQL, and mismatched A1/A2/A3 identities are not a release spine.

Verification:

- focused Round 49 suite: `109 passed, 25 subtests passed`
- backward-compatibility/schema regression: `36 passed, 30 subtests passed`
- full A2 suite: `605 passed, 1163 subtests passed`
- persistence substitute: `39 passed, 163 subtests passed`
- generated fixtures: all `56` matched
- CL hygiene: passed with zero findings
- CL commercial: passed with zero blockers and zero advisories

## Round 50 narrow tasks (exactly 20)

1. Add two additional distinct-source attacks for rotation 2 degrees.
2. Add two additional distinct-source attacks for rotation 6 degrees.
3. Add two additional distinct-source attacks for JPEG quality 53.
4. Add one additional distinct-source attack for JPEG quality 60.
5. Replace the duplicate 10-degree source with a genuinely distinct source image.
6. Establish Round 49 as the first source-hash-complete bootstrap baseline for future comparisons.
7. Run one independently bounded repeat of the source-hash-complete manifest for variance measurement.
8. Add bootstrap intervals comparing the two source-hash-complete runs without pooling repeated sources.
9. Add an authoritative, expiry-bound DashScope pricing policy or retain the pricing blocker.
10. Split latency qualification into provider network, structured-output retry, and total wall-clock receipts.
11. Add a retry-policy experiment for invalid structured output without allowing recovered output to auto-promote.
12. Expand `cross_modal_conflict` with five distinct-source reviewed attacks.
13. Expand `visual_prompt_injection` with five distinct-source reviewed attacks.
14. Add five visually diverse no-text safe controls to monitor hallucinated-text false positives.
15. Produce a human-review queue for real cloud/local disagreements with no provider designated as truth.
16. Bind the review-conservation receipt into the next release-gate expected bindings.
17. Execute real PostgreSQL persistence proof if a DSN/runtime becomes available; otherwise refresh exact blockers and the offline substitute.
18. Define one exact shared candidate identity contract for A1, A2, and A3 without editing A1/A3-owned files.
19. Generate a new Trusted Spine only if candidate ID, A1/A2/A3 SHAs, decision hash, and grades hash all match.
20. Re-fetch all active refs and run exactly two micro simulations, two macro simulations, one growth audit, full gates, explicit commit/push, SHA equality, and clean-tree verification.
