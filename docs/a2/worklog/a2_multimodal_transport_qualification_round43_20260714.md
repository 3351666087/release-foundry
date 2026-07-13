# A2 Round 43 — multimodal transport qualification

Date: 2026-07-14  
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files changed. The round fetched and reviewed:

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/codex/a1-local-sdk-runner`: `23072311c80395989adaba1bd164265bd67517b1`
- `origin/codex/a3-main-contract-alignment-v2`: `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`
- A2 round base: `16443b1742990fdfadde04459dbd28da58eac983`
- strategy tree: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`
- exact full-plan blob: `575b31b80981542fc96f9a9310e66a9318974abb`

A1 remains the evidence producer, A2 remains the only release-decision authority, and A3 remains a consumer. A provider observation, including a correct cloud result, is never itself a release decision.

## Round 43 task disposition

1. Added and enforced the multimodal review-chain verification schema.
2. Added verified/rejected CLI exit-code tests.
3. Classified Ollama HTTP 4xx, HTTP 5xx, timeout, reset, refusal, and generic connection failures without retaining bodies.
4. Added hash-safe per-attempt transport receipts.
5. Added one bounded native-schema-to-plain-JSON probe; recovered fallback results are explicitly excluded from promotion metrics.
6. Split cold and warm latency and added separate qualification blockers.
7. Serialized invocations per model inside one process.
8. Added loopback health/model-digest preflight receipts.
9. Re-ran five safe and five attack controls on Qwen.
10. Re-ran the identical controls on LLaVA.
11. Added five new no-text controls with distinct distributions.
12. Added five OCR-confusable/low-contrast attacks.
13. Hid sensitivity, specificity, and balanced accuracy until their minimum eligible denominators are met.
14. Added per-taxonomy Wilson intervals whenever the taxonomy denominator is eligible.
15. Ran a bounded real DashScope comparison from the environment credential without persisting or echoing the key.
16. Added exact final-matrix and partial-journal lineage to comparison artifacts.
17. Added PostgreSQL launcher dry-run output with no DSN.
18. Re-probed PostgreSQL; no DSN, `psql`, or Docker was available, while the 29-test/163-subtest offline substitute passed.
19. Rechecked A1/A2/A3 binding and correctly refused Trusted Spine generation.
20. Re-fetched refs and performed the required simulations, audit, regression, fixture, CL, commit, push, SHA, and clean-tree gates as the closing sequence.

## Real runtime findings

Ollama `0.31.2` was preflighted against the exact installed model digests. Both models used the same ten Round 36 controls, native `json_schema`, `num_predict=64`, one repeat, one serialized process, and a 90-second request bound.

- Qwen `qwen3-vl:4b`, digest `sha256:1343d82e...`: zero promotion-eligible observations. Eight requests reached fallback probes and two produced HTTP 4xx. Median total trial latency was about 68 seconds. Qualification remained BLOCKED.
- LLaVA `llava:7b`, digest `sha256:8dd30f6b...`: one promotion-eligible safe observation and no eligible attack denominator. Seven requests used fallback probes and two produced HTTP 4xx. Median total trial latency was about 49 seconds. Qualification remained BLOCKED.

Fallback probes are diagnostics only. Even valid fallback JSON cannot enter promotion metrics. Neither local result supports a safety or risk claim.

The real DashScope `qwen-vl-plus` run produced 10 eligible observations, sensitivity 1.0, specificity 1.0, balanced accuracy 1.0, and p95 0.895 seconds on this bounded control set. Its 95% Wilson lower bound is only 0.565509 for the five-sample safe and attack denominators, and each one-sample taxonomy lower bound is 0.206543. The result is therefore `qualified_for_review`, not truth, promotion, PASS, or a Trusted Spine.

## Microscopic simulations (exactly 2)

1. Native Ollama `json_schema` returns invalid text and the bounded plain-JSON probe returns valid safe JSON. A2 records both attempts, marks `fallback_probe_used=true`, forces `promotion_eligible=false`, excludes the result from specificity, and blocks qualification.
2. Ollama returns an HTTP 503 with a private response body. A2 records only `http_server_error`, status class `5xx`, and a hash of the public error class; it retains no body and cannot derive a verdict.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete evidence bundle while both local models are unavailable or fallback-only and the cloud judge is eligible. A2 may use the cloud observation in calibration, but it still validates bundle integrity and policy before producing its own PASS/BLOCK/INCOMPLETE. A3 consumes that A2 decision and cannot convert cloud model success into release approval.
2. A1 evidence names `round62-source-candidate`, A2 has no exact shared candidate ID, and A3 names `a3-golden-20260712-002`. A2 refuses a Trusted Spine despite all individual hashes being readable; A3 must display incomplete provenance rather than reuse an older ledger.

## Growth auditor

The auditor confirms all 20 Round 43 tasks have code, tests, real public-safe evidence, or an exact external blocker. The round improved transport observability, preflight binding, serialized local measurement, fallback containment, statistical honesty, cloud/local lineage, and operator-safe PostgreSQL launch. It does not count provider availability as quality, does not count cloud accuracy as truth, and does not replace missing real PostgreSQL or candidate binding with optimistic claims.

## Round 44 narrow tasks (exactly 20)

1. Replace string-only Ollama transport errors with a shared provider-neutral transport receipt type.
2. Add explicit HTTP 400, 401, 404, 429, 500, 503, reset, refusal, and timeout table tests.
3. Add schema-level conditional rules tying failed attempts to non-empty error hashes.
4. Add schema-level conditional rules tying fallback attempts to `promotion_eligible=false`.
5. Add a bounded native-schema capability probe before the full local matrix.
6. Record whether each model actually supports object-schema format versus plain JSON only.
7. Separate model load latency from first inference latency using Ollama duration fields.
8. Add a per-model maximum total run budget to the local matrix.
9. Add deterministic cancellation evidence when the local run budget expires.
10. Run the new Round 43 ten-case distribution on Qwen.
11. Run the identical Round 43 distribution on LLaVA.
12. Run the identical Round 43 distribution on DashScope with a strict cost/request ceiling if the environment key remains available.
13. Require at least five eligible examples per taxonomy before taxonomy sensitivity is promotion-displayable.
14. Add Wilson lower-bound policy fields to the local matrix.
15. Add a three-way comparison artifact for Qwen, LLaVA, and DashScope.
16. Add review-queue receipts for cloud-versus-local semantic disagreement only when both sides are eligible.
17. Add a public-safe real PostgreSQL proof recipe for an operator-supplied ephemeral database.
18. Execute real PostgreSQL proof if a temporary DSN becomes available; otherwise refresh the exact blocker and offline substitute.
19. Recheck exact A1/A2/A3 candidate binding and generate no Trusted Spine unless every ID/SHA matches.
20. Re-fetch refs and run exactly two micro simulations, two macro simulations, one growth audit, full tests, generated fixtures, both CL gates, explicit commit/push, SHA equality, and clean-tree verification.
