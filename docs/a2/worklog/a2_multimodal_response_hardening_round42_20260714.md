# A2 Round 42 ? multimodal response hardening

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files changed. This round fetched and reviewed:

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a1-local-sdk-runner`: `23072311c80395989adaba1bd164265bd67517b1`
- `origin/agent/a3-main-contract-alignment-v2`: `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`
- A2 round base: `4632755c8a7fffdd362b28064c1c3b449b5bf6d1`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

The contract remains unchanged: A1 supplies evidence, A2 validates it and owns the only release decision, and A3 consumes the decision and provenance without recomputation. Provider output is fallible evidence, never truth. Provider failure, timeout, malformed envelopes, empty structured content, and invalid semantics remain ineligible and cannot become PASS.

## Round 42 task disposition

1. Added one provider-neutral parsed-response contract shared by OpenAI-compatible and Ollama adapters.
2. Separated Ollama `thinking` from `response`; thinking is hash-traceable but never enters verdict parsing.
3. Added a structured-output parse recovery path bounded to one retry.
4. Added explicit timeout, malformed/empty envelope, and thinking-only fail-closed tests.
5. Added source-evidence hashes to new provider conformance receipts.
6. Added predecessor receipt and sequence chaining while retaining historical v1 evidence compatibility.
7. Added resume rejection when a DashScope policy hash differs.
8. Added ordered case-plan mismatch rejection before provider construction or invocation.
9. Enforced minimum per-taxonomy sample gates already represented by the matrix policy.
10. Reported specificity confidence intervals when eligible safe controls exist; unavailable observations do not enter the denominator.
11. Reused five deterministic no-text safe controls in the Round 36 manifest.
12. Reused five attacks spanning visual prompt injection, cross-modal conflict, unsafe-content evasion, and hallucinated-text taxonomies.
13. Ran the ten-case bounded matrix on real local `qwen3-vl:4b`.
14. Ran the identical bounded matrix on real local `llava:7b`.
15. Built a cross-provider comparison without assigning either model truth status.
16. Added a review-chain verification command for contiguous sequence, predecessor, duplicate receipt, and duplicate disposition checks.
17. Added a temporary PostgreSQL DSN launcher that places the DSN only in the child environment and never prints or persists it.
18. Re-probed PostgreSQL prerequisites; no DSN, `psql`, or Docker was available, so real same-round proof remains blocked and the 29-test offline durability substitute passed.
19. Rechecked exact A1/A2/A3 binding and emitted a blocker receipt; no Trusted Spine was generated.
20. Re-fetched refs and performed the required simulations, audit, regression, fixture, CL, diff, secret, staging, push, and SHA gates as the closing sequence.

## Parsed-response and conformance behavior

`ParsedMultimodalResponse` records independent content and thinking hashes, presence, parse source, and envelope state. Only `content_text` is passed to structured JSON and semantic validation. A valid-looking JSON object in thinking with empty content therefore stays `empty_response`, retries at most once, remains `observed_risk=null`, and is ineligible.

New conformance receipts can bind sorted, unique source evidence hashes and can form a predecessor chain. The v1 JSON schemas keep these additions optional solely so committed Round 41 v1 receipts remain valid; current builders and Round 42 tests require the new fields on newly generated receipts.

DashScope v5 resume preflight derives the current policy hash and ordered case-plan hash before creating the provider invocation closure. Either mismatch terminates with zero provider calls. V5 and runtime-matrix v2 additions are likewise schema-compatible with historical evidence while current output tests require the stronger fields.

## Real local multimodal observations

Both runs used Ollama `0.31.2`, ten cases, one repeat, `json_schema`, `num_predict=128`, and a 20-second request bound.

- `qwen3-vl:4b`, digest `sha256:9c60bdd691c1897bbfe5ddbc67336848e18c346b7ee2ab8541b135f208e5bb38`: zero eligible observations; eight timeouts and two provider failures; p95 `20.049 s`; BLOCKED.
- `llava:7b`, digest `sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081`: zero eligible observations; eight timeouts and two provider failures; p95 `20.209 s`; BLOCKED.

Every trial has `observed_risk=null`, and no raw provider payload is retained. The comparison has ten repeat-level and ten aggregate-level `unavailable` results, zero semantic disagreements, and no human-review receipt because neither side produced a semantic observation. This is runtime unavailability, not evidence that any image is safe or risky.

## PostgreSQL and Trusted Spine

The round found no process/user `POSTGRES_DSN`, `psql`, or Docker runtime. The same-round real PostgreSQL proof remains explicitly BLOCKED. The temporary launcher is ready for a future user-supplied DSN, but the current 29-test substitute verifies JSONL atomic replacement, fsync behavior, reopen/manifest verification, and replay/rollback/fork detection only; it is not presented as a real PostgreSQL proof.

A1 current ref is `23072311...`, while the reviewed A1 receipt binds `round62-source-candidate` to `5dd6a898...`. A2 has no exact shared candidate ID, and A3 requests `a3-golden-20260712-002` at `8bcbd3a...`. These identifiers do not bind one candidate, so Trusted Spine generation is forbidden.

The real DashScope key was read only from the Windows user environment when needed. It was not echoed, deleted, copied into evidence, or committed.

## Microscopic simulations (exactly 2)

1. Ollama returns `thinking={"risk_present": false}` and empty `response` twice. A2 hashes thinking for diagnostics, retries exactly once, parses no verdict, keeps `observed_risk=null`, and blocks promotion.
2. A resumed cloud run supplies a stale policy hash or ordered plan hash. Preflight terminates before provider closure construction and before any network call, so stale-version evidence cannot be silently appended to a new run.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete ten-image evidence bundle. Both local judges are unavailable and produce no eligible semantic observations. A2 emits BLOCK/INCOMPLETE diagnostics rather than PASS; A3 may display the decision and blockers but cannot reinterpret provider failure as approval.
2. A1 evidence is individually hash-traceable, A2 code is versioned, and A3 has a named deployment candidate, but their candidate IDs and SHAs do not identify one shared build. A2 refuses Trusted Spine generation, and A3 must show incomplete provenance rather than reuse an older ledger.

## Growth auditor

The growth auditor confirms all 20 Round 42 tasks have a code change, test, real public-safe evidence artifact, or explicit external blocker. Growth is measurable in response parsing, retry bounds, resume safety, conformance/review chaining, comparative diagnostics, and credential-safe proof launch. It does not claim model quality from unavailable outputs, does not count provider names as capability, and does not replace the absent PostgreSQL or candidate-binding proofs with optimistic language.

Closing verification:

- Focused hardening: `37 passed`, `3 subtests passed` before evidence-schema additions.
- Historical compatibility regression: `42 passed`, `14 subtests passed`.
- A2 full suite: `533 passed`, `1127 subtests passed`.
- PostgreSQL offline substitute: `29 passed`, `163 subtests passed`.
- Generated fixtures: all 56 matched. CL hygiene and CL commercial: passed. Diff check, secret scan, explicit staging, push, SHA equality, and clean tree are final mechanical gates.

## Round 43 narrow tasks (exactly 20)

1. Add a schema for multimodal review-chain verification output.
2. Add CLI tests for verified and rejected review-chain exit codes.
3. Classify Ollama HTTP 4xx, 5xx, connection reset, and timeout separately without retaining response bodies.
4. Record an error-class hash-safe transport receipt for each Ollama attempt.
5. Add a bounded plain-JSON fallback probe after native `json_schema` failure without permitting fallback output to auto-promote.
6. Measure cold-start and warm-start latency in separate local qualification gates.
7. Add one-process model serialization to prevent concurrent local runs from creating misleading timeout evidence.
8. Add an Ollama health and loaded-model preflight receipt bound to version and model digest.
9. Re-run five safe and five attack controls on Qwen after serialization/preflight changes.
10. Re-run the identical controls on LLaVA after serialization/preflight changes.
11. Add at least five more safe no-text controls with distinct visual distributions.
12. Add at least five attacks covering OCR-confusable and low-contrast injection cases.
13. Require minimum eligible samples before any sensitivity, specificity, or balanced-accuracy claim is displayed.
14. Add Wilson interval assertions for every taxonomy with eligible observations.
15. Run a bounded real DashScope comparison only if the environment key remains available, with no secret persistence.
16. Add comparison lineage linking each comparison to exact final matrix hashes and partial-journal hashes.
17. Add a PostgreSQL launcher dry-run mode that reports only command/test selection, never the DSN.
18. Execute real PostgreSQL persistence proof if a temporary DSN becomes available; otherwise refresh exact blocker evidence and offline substitute.
19. Recheck exact A1/A2/A3 candidate binding and generate no Trusted Spine unless all candidate identifiers and SHAs match.
20. Re-fetch all refs and run exactly two micro simulations, two macro simulations, one growth audit, full tests, fixtures, both CL gates, explicit commit/push, SHA equality, and clean-tree verification.
