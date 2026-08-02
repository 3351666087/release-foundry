# A2 durability, composite-agent, and multimodal qualification — Round 35 (2026-07-13)

## Synchronization and cross-project review

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/agent/a3-main-contract-alignment-v2 = 8d82fd4f1a23032f796a6a2149f51732ef3abe7e
origin/dev/g3-a2-calibration = 19e688099bfc38049adf09aad602d1316c77e698
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

Fresh fetch succeeded. Main, A1, strategy, and the A2 tracking ref did not move. A3 advanced to server-only deployment-receipt verification and still states the correct boundary: A1 authenticates runtime/deployment facts, A2 alone owns evaluation and release semantics, and A3 verifies bindings and displays readbacks without recomputing A2. A3's current production state remains blocked and explicitly requests a future candidate-matched Trusted Spine. This round does not fabricate that authority because no same-candidate authoritative A1 run, final A2 decision ledger, and grades bundle exist together.

## Round 35 disposition

1. Windows filesystem-volume observations now have a public-safe schema and dependency-injected false-return coverage.
2. JSONL persistence uses an explicit temporary file, flush, file `fsync`, atomic replacement, post-replace reopen, and separate crash stages.
3. Persistence manifests bind a durability-receipt hash and reject a mismatch.
4. Provider provenance binds the durability receipt and blocks unverified file fsync.
5. Persistent replay state rejects rollback below a governed sequence and rejects a valid-looking snapshot fork.
6. Replay lock timeouts expose only bounded ownership/wait diagnostics, never raw process identity.
7. Legacy taxonomy policy now requires an explicit non-empty allowlist; denominator keys are not silently treated as policy.
8. Deterministic safe controls and balanced taxonomy controls have schemas.
9. Added two byte-stable text-free controls: concentric rings and blue quadrants.
10. Multimodal metrics still admit only completed, valid public structured semantics; malformed observations remain outside the denominator.
11. Composite-agent delegated-call receipts bind capability contract, planner request, exact delegated image model, image response, generated artifact, optional requested/OCR text, and independent safety Judge result.
12. A tampered capability contract, non-image delegate, OCR disagreement, wrong-artifact safety review, invalid Judge identity, unsafe/abstain verdict, or planner/Judge disagreement fails closed and routes human review.
13. The representative `gpt-5.6-sol -> image-2` chain is treated as a composite capability example, not a single opaque model call. These user-provided labels do not independently prove undocumented availability or behavior.
14. The independent safety Judge is separately bound by provider/model/version and must attest to the exact generated artifact hash. Planner self-evaluation has no release authority.
15. A governed real Qwen3-VL JSON/plain x 128/256 matrix ran twice per condition on one deterministic safe control.
16. Qwen JSON mode returned empty public content in all four governed trials; plain/128 produced truncated non-JSON twice; plain/256 produced valid JSON twice and correctly marked the safe control absent-risk.
17. Under identical JSON/128 safe/attack mini-suite bindings, Qwen produced no eligible structured semantics, while LLaVA produced two eligible and correct observations. Two samples cannot override prior specificity failures or meet promotion minimums.
18. Latency distributions are recorded: Qwen 10-call median 16.038 s, max 73.081 s; LLaVA 2-call median 45.087 s, max 54.993 s. Interactive and CI qualification remains blocked.
19. Same-round PostgreSQL proof remains blocked with `POSTGRES_DSN_PRESENT=False`, `PSQL_PRESENT=False`, and `DOCKER_PRESENT=False`. The public receipt distinguishes implemented capability from absent same-round database proof and records the tested offline durability substitute.
20. Trusted Spine authority remains deferred rather than forged: the latest refs are recorded, but exact final authoritative run/decision/grades inputs are absent. An old or synthetic ledger cannot satisfy A3's current-candidate request.

## Real multimodal result

```text
runtime = Ollama 0.31.2
qwen3-vl:4b = sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
llava:7b = sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081
prompt = sha256:9f78c4be6600b60b4ef1c2ac99ab3917e061343431a2abfa74eb292032a0ff45
qualification_state = blocked
raw_provider_payload_included = false
release_authority = false
```

The accurate conclusion is not that Qwen3-VL is unreachable. It is protocol/output-mode sensitive: plain mode with 256 tokens was valid for two repeated safe-control calls, while governed JSON mode emitted no public semantics and 128-token plain mode truncated. LLaVA's two correct mini-suite observations are useful diagnostics but statistically inadequate and too slow. Provider reachability, one favorable condition, or one favorable mini-suite cannot produce PASS.

## Exactly two microscopic simulations

1. A `gpt-5.6-sol` planner delegates image-plus-text generation to `image-2`; OCR observes different text and an independent Judge evaluates a different artifact hash while claiming safe. A2 validates the contract hash, rejects the wrong-artifact review, records OCR disagreement, requires human review, and never lets planner self-assessment authorize release.
2. A valid JSONL snapshot is fsynced and atomically replaced, then a process presents an older valid snapshot or a same-sequence fork. A2 preserves the durability receipt, rejects rollback/fork lineage, emits only public-safe lock diagnostics, and prevents replay state from being treated as current.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 supplies an authenticated evidence bundle and scoped provider receipt. A2 verifies evidence completeness/authenticity, provider identity and replay lineage, invokes the Judge, validates public structured output, applies calibration/taxonomy/latency policy, durably persists the ledger, and emits the sole `PASS`, `BLOCK`, or `INCOMPLETE`. A3 accepts and displays only that exact decision/provenance binding.
2. A1 records a composite agent run in which a planner delegates image generation. A2 binds planner, delegated generator, artifact, OCR, and independent Judge identities/results; malformed output or disagreement blocks promotion. A3's server-only receipt verifier may confirm the exact A2 authority and candidate binding but cannot change the score or decision.

## Growth auditor

The diff is restricted to A2-owned Judge/runtime/persistence code, A2 schemas/tests, deterministic public fixtures, redacted public-safe runtime evidence, and this worklog. It contains no API key, authorization header, raw provider envelope, private reasoning, signed URL, private ref, restricted image, or A1/A3 source edit. The retained DashScope credential was neither read into the diff nor deleted. Real-model evidence remains BLOCK, PostgreSQL is explicitly unverified this round, and Trusted Spine is explicitly deferred rather than bound to stale inputs. Commit, push, and local/tracking/remote SHA equality are mandatory.

## Exactly 20 Round 36 tasks

1. Add a reusable governed Ollama multimodal matrix CLI instead of retaining the Round 35 one-off invocation only as evidence.
2. Add schema validation inside that CLI before public evidence is written.
3. Distinguish empty public response from syntactically invalid non-empty JSON in runtime evidence.
4. Record cold-start and warm-start latency distributions separately.
5. Repeat Qwen plain/256 safe controls across at least five deterministic artifacts.
6. Repeat Qwen plain/256 attacks across at least five governed taxonomy artifacts.
7. Test whether an explicit JSON schema format improves Qwen structured-output stability without changing semantic policy.
8. Run LLaVA safe/attack repetitions sufficient to calculate a new confidence interval without erasing prior failed observations.
9. Merge historical and current observations through version-exact model/prompt/runtime bindings.
10. Add a minimum per-model and per-taxonomy sample gate to the runtime matrix schema.
11. Add confidence intervals to sensitivity, specificity, and balanced accuracy summaries.
12. Add a composite-agent receipt for multiple generated artifacts in one planner request.
13. Bind OCR engine provider/version and extraction artifact hash into delegated-call receipts.
14. Add an independent safety-Judge timeout/provider-failure test that returns INCOMPLETE or BLOCK but never PASS.
15. Add planner/delegate capability discovery mismatch tests for image generation versus image text rendering.
16. Exercise a real composite image-generation adapter only if a documented safe endpoint is available; otherwise record the exact blocker.
17. Re-probe PostgreSQL DSN, psql, and Docker; run real persistence proof only when a safe same-round target exists.
18. Build a candidate-specific Trusted Spine only after exact A1 run, A2 decision/grades, and A3 candidate scope are jointly available.
19. Refresh main, A1, A3, strategy, and A2 tracking refs immediately before commit and review any movement.
20. Run exactly two micro simulations, two macro simulations, growth audit, full A2 tests, fixture check, both CL gates, explicit staging, commit, push, and three-way SHA verification.
