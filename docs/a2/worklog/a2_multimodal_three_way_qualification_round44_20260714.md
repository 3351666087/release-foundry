# A2 Round 44 — multimodal three-way qualification

Date: 2026-07-14  
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files changed. The round fetched and reviewed:

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/codex/a1-local-sdk-runner`: `23072311c80395989adaba1bd164265bd67517b1`
- `origin/codex/a3-main-contract-alignment-v2`: `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`
- A2 round base: `1986a285011b69273c33b0550b2de956189fc4cf`
- strategy tree: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`
- exact full-plan blob: `575b31b80981542fc96f9a9310e66a9318974abb`

A1 remains the evidence producer. A2 remains the only release-decision
authority. A3 remains a consumer and cannot recompute or upgrade an A2
decision.

## Round 44 task disposition

1. Replaced the Ollama-only transport exception with a shared,
   provider-neutral transport receipt and classified exception.
2. Added table tests for HTTP 400, 401, 404, 429, 500, 503, reset, refusal,
   and timeout.
3. Added conditional schema validation for non-empty failed-attempt error
   hashes when a transport receipt is present.
4. Added conditional schema validation forcing fallback trials to be
   non-promotion-eligible.
5. Added a bounded native object-schema capability probe before the matrix.
6. Recorded object-schema versus plain-JSON support per exact model digest.
7. Recorded Ollama total, load, prompt-evaluation, token-evaluation, and
   first-inference durations separately from wall time.
8. Added a per-model total-run budget.
9. Added deterministic, public-safe, no-network-started cancellation receipts.
10. Ran the Round 43 ten-case distribution on Qwen.
11. Ran the identical distribution on LLaVA.
12. Ran the identical distribution on DashScope under a 120-second cloud
    ceiling without echoing or persisting the credential.
13. Set the live DashScope CLI taxonomy display minimum to five eligible
    examples; local matrix promotion display also defaults to five.
14. Added local Wilson lower-bound policy fields and blockers.
15. Added an exact-hash-bound three-way comparison artifact.
16. Added review-queue receipts only when at least two eligible providers
    semantically disagree.
17. Added a public-safe operator recipe for an ephemeral PostgreSQL proof.
18. Re-probed PostgreSQL. No DSN, `psql`, or Docker was available; the
    29-test/163-subtest offline persistence substitute passed.
19. Rechecked exact A1/A2/A3 binding and correctly refused Trusted Spine
    generation.
20. Re-fetched refs and performed exactly two microscopic simulations, two
    macroscopic simulations, one growth audit, regression, fixtures, CL,
    explicit staging, commit/push, SHA, and clean-tree gates.

## Real runtime findings

Ollama `0.31.2` was bound to:

- Qwen `qwen3-vl:4b`:
  `sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683`
- LLaVA `llava:7b`:
  `sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081`

Both local runs used the same ten Round 43 controls, native `json_schema`,
`num_predict=64`, one repeat, a 120-second request bound, and a 900-second
per-model run budget.

- Qwen: 10/10 trials used the diagnostic fallback and ended with empty
  responses; promotion eligible count was zero; measured trial wall time
  summed to about 881.6 seconds. Capability probe state was `unsupported`.
  Qualification is BLOCKED.
- LLaVA: two valid JSON observations and eight invalid JSON observations;
  nine trials used fallback; only one safe observation was promotion eligible;
  measured trial wall time summed to about 596.5 seconds. Capability probe
  state was `unsupported`. Qualification is BLOCKED.
- DashScope `qwen-vl-plus`: 10/10 eligible observations, sensitivity 0.6,
  specificity 0.8, balanced accuracy 0.7, p95 0.956 seconds. Sensitivity
  Wilson lower bound was 0.230720 and specificity lower bound was 0.375528.
  Each attack taxonomy had fewer than five eligible examples. Qualification
  is BLOCKED.

The three-way comparison reports one eligible agreement, zero eligible
semantic disagreements, and nine unavailable cases. It generates zero review
queue receipts. Unavailable local observations are not disagreements.

These are provider/model observations, not truth and not a release decision.
No local or cloud model was promoted.

## Microscopic simulations (exactly 2)

1. A model exceeds its total-run budget before the next case begins. A2 emits
   `model_run_budget_exhausted`, `parse_state=not_attempted`,
   `observed_risk=null`, `promotion_eligible=false`, and a cancellation receipt
   proving that no network call started. The case cannot enter metrics.
2. A provider returns HTTP 429 with a private response body. A2 records only
   `rate_limited`, status class `4xx`, and a stable error-class hash. The body
   is not retained, and the failure cannot produce PASS.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete evidence bundle while DashScope is eligible but both
   local providers are unavailable or fallback-only. A2 may retain the cloud
   observations for calibration, but it independently checks evidence,
   policy, and failure state before producing PASS/BLOCK/INCOMPLETE. A3 can
   only consume that A2 decision.
2. A1 names `round62-source-candidate` at a receipt SHA that does not match the
   current A1 ref, A2 has no shared candidate ID, and A3 names
   `a3-golden-20260712-002`. A2 refuses to generate a Trusted Spine. A3 must
   present incomplete provenance rather than reuse an older ledger.

## PostgreSQL and Trusted Spine

The environment still has no `POSTGRES_DSN`, `psql`, or Docker. The public
recipe now permits an operator to supply a temporary DSN out of band without
printing or storing it. The current round therefore records a real PostgreSQL
proof blocker, not a PostgreSQL success claim.

The exact A1/A2/A3 IDs and SHAs remain unbound. No Trusted Spine was generated.

## Growth auditor

The auditor confirms that all 20 Round 44 tasks have implementation, tests,
real public-safe evidence, or an exact external blocker. The round improved
provider-neutral failure evidence, schema capability discovery, native latency
decomposition, bounded execution, statistical qualification, and eligible-only
cross-provider review routing. It did not count fallback as promotion data,
unavailable as disagreement, cloud accuracy as truth, an offline database test
as PostgreSQL proof, or readable but mismatched SHAs as a Trusted Spine.

## Round 45 narrow tasks (exactly 20)

1. Add the provider-neutral transport receipt to the OpenAI-compatible adapter.
2. Add identical transport receipt taxonomy tests for DashScope-compatible HTTP failures.
3. Add a shared response-duration receipt that supports provider-native and wall-clock sources.
4. Add schema invariants proving cancellation receipts occur only on failed, non-eligible trials.
5. Bind capability-probe receipts to runtime version hash and prompt/schema hashes.
6. Add a capability-probe timeout budget separate from the model matrix budget.
7. Skip unsupported native-schema full-matrix calls unless an explicit diagnostic override is set.
8. Preserve a receipt explaining every capability-based matrix skip.
9. Add a maximum local attempt count across native and fallback modes.
10. Add a per-case maximum wall-time budget below the per-model budget.
11. Add five eligible attack examples for each Round 43 attack taxonomy.
12. Add five additional no-text safe controls from distinct visual distributions.
13. Re-run Qwen on the expanded taxonomy-balanced distribution.
14. Re-run LLaVA on the identical expanded distribution.
15. Re-run DashScope on the identical distribution under a strict request/cost ceiling.
16. Add pairwise and three-way comparison cross-checks proving summary conservation.
17. Add deterministic review-receipt deduplication across repeated comparison builds.
18. Execute the ephemeral PostgreSQL recipe if an operator DSN becomes available; otherwise refresh the blocker and offline substitute.
19. Recheck exact A1/A2/A3 binding and generate no Trusted Spine unless every candidate ID and SHA matches.
20. Re-fetch refs and run exactly two micro simulations, two macro simulations, one growth audit, full tests, generated fixtures, both CL gates, secret scan, explicit commit/push, SHA equality, and clean-tree verification.
