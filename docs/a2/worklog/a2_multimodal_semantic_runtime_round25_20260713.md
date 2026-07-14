# A2 multimodal semantic runtime governance — Round 25 (2026-07-13)

## Synchronization

Fresh `git fetch --all --prune` succeeded immediately before closure:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

`origin/codex/a3-commercial-growth-round4` was deleted remotely and is no longer treated as active. A1 Round 62 adds hash-bound five-modality provider receipts; A2 still validates that evidence and remains the sole release-decision authority. A3 remains a committed-decision consumer.

## Round 25 task disposition

1. Confirmed Round 24 contains exactly seven safe and five attack attempts; eleven timed out and one completed with an empty response.
2–3. Runtime governance now distinguishes HTTP completion, valid semantic completion, and empty response counts.
4. Queue telemetry is recorded when exposed and explicitly marked `not_exposed` otherwise; no queue value is invented.
5. Ollama 0.31.2 was restarted cleanly. A bounded Qwen diagnostic subsequently hung for more than seventeen minutes and was killed; no semantic result was promoted.
6. Recorded host facts: HUAWEI MDG-XX, i5-13420H, 16.89 GB RAM, Intel UHD only, and Ollama `size_vram=0`.
7–8. The hung request is negative evidence for CPU-only cancellation/backlog behavior. Cancellation receipt hashes are supported, but Ollama did not expose authoritative queue depth or a server cancellation receipt; absence remains explicit.
9. Installed candidates are `qwen3-vl:4b` and larger `llava:7b`. No genuinely smaller digest-bound model was available, so none was fabricated or promoted.
10. LLaVA remains blocked: its safe controls still have zero specificity.
11–12. Added minimum valid-semantic-output rate and maximum provider-timeout rate policies.
13. Added per-taxonomy recall/specificity Wilson intervals over valid semantic observations only.
14. Timeouts are excluded from the confusion matrix and remain independent fail-closed blockers. Completed malformed/empty output is separately counted from timeout.
15. Added a deterministic hazard-icon provenance fixture bound to artifact, extractor, and icon-detector hashes.
16. Added public-safe runtime governance persistence through the existing JSONL/offline record abstraction.
17. No authoritative Trusted Spine was generated because exact final A1/A2/A3 candidate and grades are not all final. The Round 24 candidate remains non-authoritative.
18. PostgreSQL proof remains blocked. `POSTGRES_DSN`, `psql`, and Docker are absent. `winget` offers PostgreSQL 17, but C: has only 0.5 GB free, so installation was rejected as unsafe; offline persistence remains the honest substitute.
19. Required refs were refreshed above.
20. Exact simulations, growth audit, full A2 validation, CL Gate, explicit staging, push, and three-way SHA verification close the round.

## Real multimodal operational result

Ollama is healthy at its control endpoint and reports version 0.31.2. After the prior Qwen call was force-stopped, `ollama ps` showed no loaded model and the version endpoint answered normally. This proves process recovery, not request-level cancellation. The attempted CPU-only Qwen diagnostic produced no valid semantic output in over seventeen minutes. Therefore the candidate is `BLOCK / INCOMPLETE`; latency, timeout, semantic-output, and sample gates cannot be waived.

## Exactly two microscopic simulations

1. A provider returns HTTP success with `parse_state=invalid_json`. A2 increments `invalid_output_count`, excludes the observation from recall/specificity, adds `invalid_semantic_observations_excluded`, and cannot PASS.
2. A provider times out on a visual-conflict case. A2 increments `timeout_count`, exposes the affected taxonomy, adds the independent provider-timeout blocker, and does not mislabel it as a model false negative.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 submits hash-bound image/video receipts, but the real Judge returns an empty body. A2 records evidence provenance plus a structured-output/runtime BLOCK. A3 renders that committed decision and cannot reinterpret transport success as PASS.
2. A1 submits complete evidence and all deterministic checks pass, but the A2 candidate lacks sufficient valid safe controls and PostgreSQL same-round proof. A2 emits INCOMPLETE with exact blockers. A3 consumes the versioned result; it does not recompute grades or create a release decision.

## Growth auditor

Only A2-owned files are eligible for staging. No key, raw provider response, temporary diagnostic script, private ref, or generated attack image is included. The changes reduce ambiguity between transport success, semantic success, timeout, and malformed output. The principal remaining risks are CPU-only multimodal infeasibility, missing real PostgreSQL transaction proof, insufficient valid safe/attack samples, and absence of a final matching Trusted Spine. CL means **Change List**; the repository CL Gate (`scripts/cl_guard.py`, `.github/workflows/cl-gate.yml`) must run before every commit.

## Exactly 20 Round 26 tasks

1. Add a schema-validated Round 25 runtime diagnostic receipt with only hash-safe fields.
2. Add request-start, client-kill, and server-recovery timestamps to cancellation evidence.
3. Distinguish provider timeout, client cancellation, and transport failure in runtime taxonomy.
4. Add a stale-request recovery probe with a cheap post-kill health request.
5. Add a policy threshold for maximum empty-response rate.
6. Add a policy threshold for maximum invalid-structured-output rate.
7. Add Wilson intervals for per-taxonomy false-positive and false-negative rates.
8. Add explicit zero-denominator semantics for taxonomy intervals.
9. Add safe-control and attack-control valid-sample minimums separately.
10. Add confidence-bound promotion tests for ten valid safe controls.
11. Evaluate a smaller digest-bound vision model only if disk-safe installation becomes possible.
12. Keep Qwen and LLaVA non-promotable until new exact bindings satisfy all gates.
13. Add offline deterministic icon-shape mutation fixtures.
14. Add fixture provenance rejection for changed artifact or detector hashes.
15. Add runtime-record JSONL round-trip and tamper tests.
16. Free or relocate sufficient disk space before any PostgreSQL installation.
17. Run a real PostgreSQL transaction/RLS persistence proof once a safe DSN exists.
18. Refresh main, active A1/A3, and strategy refs immediately before commit.
19. Generate a new authoritative Trusted Spine only after exact final SHAs, results, and grades exist.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, pre-commit CL Gate, push, and three-way SHA verification.
