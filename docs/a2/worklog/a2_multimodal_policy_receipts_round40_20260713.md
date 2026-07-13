# A2 Round 40 ? multimodal policy, receipts, and perturbation stability

Date: 2026-07-13
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files changed. The round fetched and reviewed:

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/codex/a1-local-sdk-runner`: `23072311c80395989adaba1bd164265bd67517b1`
- `origin/codex/a3-main-contract-alignment-v2`: `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`
- `origin/dev/g3-a2-calibration`: `6ce6000aecadcc6503a819052a7fa2c8c5a69987`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

Strategy still requires provider-neutral execution, offline closure, provider failure fail-closed, A2-only release authority, and A3 consumption without recomputation. A1 Round 62 is a source-candidate receipt bound to an older baseline, while current A2 evidence and the latest A3 candidate do not share one exact candidate binding. No Trusted Spine was generated.

## Round 39 task disposition

1. Added DashScope calibration v4; v3 remains unchanged and is explicitly regression-tested.
2. Added contiguous and unique attempt-number validation.
3. Added retry recovery count/rate without changing the observation denominator.
4. Added a distinct recovered-invalid-output blocker.
5. Tested run-budget exhaustion between retry attempts.
6. Cached artifact conversion and generated fail-closed receipts for remaining uncalled cases.
7. Added CLI JSON taxonomy policy input.
8. Rejects taxonomy policy absent from the attack manifest.
9. Retained and schema-validates per-taxonomy Wilson intervals.
10. Rejects duplicate partial-journal trial keys before resume.
11. Binds partial journals to format and token-bound plan hashes.
12. Added injected crash coverage before partial completion; in-progress state survives.
13. Added an independent comparison receipt verifier and tamper test.
14. Added a real-human-review-only receipt schema distinct from test fixtures.
15. Added repeated perturbation controls derived from the two Round 37 hallucination cases.
16. Ran all 12 Round 39 controls against qwen-vl-plus and qwen-vl-max.
17. Added deterministic JPEG qualities 35/55/75 and rescaling 256/384/768 controls.
18. PostgreSQL remains blocked: no DSN, psql, or Docker. Offline persistence substitute passed.
19. Exact A1/A2/A3 candidate binding does not coexist, so no Trusted Spine was created.
20. Refs, simulations, growth audit, tests, fixtures, CL, explicit commit/push, and SHA equality are closing gates.

## Real cloud observations

On the 12 Round 39 controls, both Qwen models were BLOCKED. Each had sensitivity `0.5` and specificity `1.0`. `qwen-vl-plus` p95 was `1.413 s`; `qwen-vl-max` p95 was `1.704 s`. Their taxonomy behavior differed: plus detected unsafe-content evasion but neither hallucinated-text case; max detected cross-modal conflict and visual injection but missed both unsafe-content evasion and hallucinated-text cases. The cross-provider comparison had 8 agreements and 4 semantic disagreements.

On 12 deterministic JPEG/rescale variants of the two Round 37 hallucination cases, repeated three times, plus reached sensitivity `0.666667` with Wilson lower bound `0.503337`; max reached `0.166667` with lower bound `0.078703`. Both remained BLOCKED because the diagnostic is attack-only and below policy. Repeat-level comparison had 18 agreements and 18 semantic disagreements; aggregate comparison had 5 agreements, 5 semantic disagreements, and 2 internally unstable cases. Provider outputs remain non-authoritative.

The CLI policy-file and whole-run budget were exercised with a 0.001-second budget. The first case timed out and the remaining case received `run_budget_exhausted` / `not_attempted`; no failure became eligible or PASS.

## Microscopic simulations (exactly 2)

1. An invalid first response recovers on attempt two. One observation remains in the denominator, recovery count becomes one, both invalid-output blockers remain, and qualification stays BLOCKED.
2. A partial journal contains the same model/format/token/case/repeat key twice. Resume rejects it before a provider call; an injected crash before completion leaves the journal in progress.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete evidence bundle, but two calibrated cloud judges disagree and one is internally unstable. A2 emits BLOCK with hash-bound review receipts. A3 may render and route those receipts but cannot recompute the score or release decision.
2. A1 Round 62 identifies a source candidate, current A2 evidence binds this branch state, and A3 has a later product candidate. Because the candidate hashes do not match exactly, A2 refuses Trusted Spine generation and A3 must show incomplete provenance.

## Growth auditor

The growth auditor confirms this round closed all 20 Round 40 tasks with code, tests, real cloud evidence, or explicit blocker evidence. Growth came from stronger policy versioning, resumability, independent receipt verification, deterministic perturbation stability, and measurable provider disagreement?not from declaring either cloud model a truth source. No secret, raw provider payload, private reference, or release-authoritative claim is included. Closing still requires all A2 tests, fixture check, both CL gates, diff check, explicit staging, secret scan, commit, push, and local/tracking/remote SHA equality.

## Round 41 narrow tasks (exactly 20)

1. Add a first-class generic OpenAI-compatible multimodal adapter independent of DashScope naming.
2. Move DashScope endpoint and credential resolution behind the provider registry.
3. Add capability discovery for image MIME types, structured output, retries, and token bounds.
4. Add a provider conformance receipt schema shared by local and cloud adapters.
5. Verify the generic adapter against the current DashScope endpoint without changing calibration semantics.
6. Add a deterministic offline adapter that emits valid, invalid, timeout, and rate-limit receipts.
7. Add retry-policy classes that distinguish parse retry from transport retry.
8. Add total attempt latency and final observation latency as separate metrics.
9. Add per-taxonomy Wilson lower-bound policy thresholds, not only reporting.
10. Add policy-file schema validation and canonical policy hash binding.
11. Bind cloud evidence to manifest hash and exact ordered case-plan hash.
12. Add JPEG source/transport MIME regression coverage for generic adapters.
13. Add comparison verification JSON schema and schema validation tests.
14. Add a real-review receipt builder that cannot emit test identities.
15. Add reviewer receipt predecessor chaining and duplicate disposition rejection.
16. Add local Ollama execution for the Round 40 perturbation matrix when a runtime is available; otherwise refresh runtime blocker evidence.
17. Probe a safe local PostgreSQL installation path and run the real persistence proof if available.
18. Re-check exact A1/A2/A3 candidate bindings and generate Trusted Spine only on an exact match.
19. Re-run both Qwen models only on cases whose aggregate state was internally unstable.
20. Re-fetch refs, run exactly 2 micro and 2 macro simulations, growth audit, all A2 tests, fixtures, CL, explicit commit/push, and SHA equality.
