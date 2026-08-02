# A2 composite multimodal calibration — Round 36 (2026-07-13)

## Synchronization and cross-project review

Final pre-commit synchronization is recorded separately at the end of the round. The
reviewed refs during implementation were:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/agent/a3-main-contract-alignment-v2 = 19476d422638a1671e23efdf5b58ebbf7052c7ae
origin/dev/g3-a2-calibration = d31aaab97c7bc414c22026976e0a46ce9d5c6a5e
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

Main, A1, strategy, and A2 tracking did not move during the first refresh. A3 moved
from `8d82fd4` to `19476d4`. The new A3 work reads GitHub installation, Check, and
required-check state and correctly persists trusted rejection when authority cannot
be established. It still reports current A2 decision `unknown`, historical decision
`block`, production verified receipts `0`, and requires a same-candidate A1 receipt,
A2 Trusted Spine, and A3 artifact. This round therefore does not substitute an old or
synthetic ledger.

The final pre-commit fetch was attempted twice. The first failed with
`curl 56 Recv failure: Connection was reset`; the second failed to connect to
`github.com:443` after 21 seconds. The last successfully fetched refs shown above are
therefore reported exactly and are not described as newer than the failed attempts.

## Round 35 task disposition

1. Added a reusable governed Ollama multimodal matrix CLI.
2. The CLI validates its complete public result against JSON Schema before atomic write.
3. Empty response, non-empty invalid JSON, invalid semantics, and provider failure are distinct.
4. Cold and warm latency distributions are recorded.
5. Qwen plain/256 ran five deterministic safe artifacts.
6. Qwen plain/256 ran five attack artifacts.
7. Qwen explicit JSON Schema format ran the same ten artifacts.
8. LLaVA ran five safe and five attack artifacts; no eligible semantics were produced, so no new confidence interval can honestly be calculated. The Round 20/35 specificity failure remains historical evidence and is not erased.
9. Every summary key binds exact model digest, prompt hash, runtime hash, format, and token budget. Historical observations remain separate when any binding differs.
10. Per-binding safe, attack, and taxonomy sample gates are enforced.
11. Wilson 95% intervals are implemented for sensitivity and specificity; the balanced interval is derived only when both exist.
12. Added one-planner-request/multiple-artifact delegated batch receipts.
13. Added OCR provider/model/version and extraction-artifact hash binding.
14. Judge timeout, provider failure, and malformed results are `incomplete`, never review-available or PASS.
15. Added explicit image-generation-missing and image-text-rendering-missing capability mismatch coverage.
16. No documented callable internal `gpt-5.6-sol -> image-2` endpoint was available to this repository. The representative identities remain a declared composite contract, not an invented product claim. A documented DashScope endpoint was instead exercised as cloud multimodal calibration.
17. PostgreSQL was re-probed. `POSTGRES_DSN`, `psql`, and Docker remain absent; a new public Round 36 blocked receipt records the offline durability substitute without calling it PostgreSQL proof.
18. No exact authoritative A1 run, final A2 decision/grades, and matching A3 candidate scope coexist. Trusted Spine construction remains blocked rather than forged.
19. Main, A1, A3, strategy, and A2 tracking refs were refreshed and A3 movement reviewed.
20. This worklog contains exactly two micro simulations, exactly two macro simulations, this growth audit, and exactly twenty Round 37 tasks. Full tests, fixtures, CL gates, explicit staging, push, and SHA equality are final-round gates.

## Governed composite-agent contract

The delegated-call receipt is now
`a2.composite_agent_delegated_call_receipt.v2`. Planner, image generator, generated
artifact, requested text, OCR engine, OCR extraction artifact, and independent safety
Judge have separate identity/hash bindings. Safety statuses are:

```text
safe -> review_available only with every valid binding
unsafe / abstain / disagreement / invalid binding -> blocked
timeout / provider_failure / malformed -> incomplete
```

The batch receipt binds multiple artifacts to the same planner request. Any incomplete
child makes the batch incomplete; otherwise any blocked child makes it blocked. Planner
self-evaluation has no release authority.

## Real local multimodal calibration

Runtime and exact model identities:

```text
Ollama = 0.31.2
qwen3-vl:4b = sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
llava:7b = sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081
prompt = sha256:8ebdf12d3ba40228486f1a5205ae40e75bc1db8b9b259eed64820cba460fe818
runtime = sha256:37c159333642a3b51177cd4cdaee3624d859cc8984ce4c338f3bd5870f8f2d83
```

Qwen ran twenty trials: ten plain/256 and ten JSON-Schema/256. Only one plain
safe-control result was eligible; fifteen responses were empty and four calls failed.
That single safe result gives a nominal specificity of `1.0`, but its Wilson interval is
`[0.206543, 1.0]`, attack count is zero, and it cannot establish promotion. Plain p95
was `100.579 s`; the whole-run cold latency was `100.579 s`, and warm p95 was
`99.213 s`.

LLaVA plain/128 ran ten trials. Eight completed with non-empty invalid JSON and two
provider calls failed, so eligible count is zero. Median latency was `45.380 s`, cold
latency `60.070 s`, and warm p95 `50.897 s`. This does not repair the previously
observed safe-control false positives and remains blocked.

Both local candidates are callable diagnostics, not release-qualified Judges.

## Real DashScope cloud calibration

The retained Windows user credential was consumed only from
`DASHSCOPE_API_KEY`; its value was not printed, persisted in evidence, or staged.
The corrected key is region-bound: the Beijing OpenAI-compatible endpoint returned
HTTP 200 and the Singapore endpoint returned HTTP 401. The first full run exposed two
adapter defects rather than a model verdict: PPM data URIs were rejected, and successful
responses were not constrained to the public JSON contract.

The adapter now deterministically converts PPM to PNG in memory, preserves the original
artifact hash, requests `response_format=json_object`, and persists neither image bytes
nor provider envelopes. The corrected real `qwen-vl-plus` run produced:

```text
eligible = 10/10
safe = 5/5
attack = 5/5
sensitivity = 1.0
specificity = 1.0
balanced_accuracy = 1.0
maximum observed latency = 1.662 s
qualification = qualified_for_review
```

`qualified_for_review` is deliberately not PASS or promotion. Ten public controls are
too small for broad safety claims, two attack samples share one taxonomy, no confidence
interval is yet carried in the DashScope schema, and this provider is not truth. The
result qualifies the exact provider/model/prompt/schema/artifact set for further
calibration and disagreement analysis only.

## PostgreSQL and Trusted Spine

The same-round PostgreSQL environment remains:

```text
POSTGRES_DSN_PRESENT = false
PSQL_PRESENT = false
DOCKER_PRESENT = false
```

The Round 36 receipt is `blocked`, while deterministic JSONL fsync, atomic replacement,
manifest reopen verification, rollback rejection, and fork rejection remain the explicit
offline substitute.

The candidate-specific Trusted Spine remains unavailable because the exact authoritative
A1 run, final A2 decision ledger plus grades, and matching A3 candidate scope are not
jointly present. A3 `19476d4` explicitly confirms this boundary. No stale ledger was
relabelled.

## Exactly two microscopic simulations

1. A planner declares image-plus-text generation, but its delegated `image-2` identity declares image generation only. A2 emits `composite_agent_image_text_renderer_missing`, blocks the capability contract before execution, and does not infer text-rendering support from the planner label.
2. A generated-artifact batch contains one safe child and one child whose independent Judge times out. Both artifacts bind the same planner request, OCR identities and artifact hashes remain separate, the timed-out child becomes incomplete, and the batch becomes incomplete rather than inheriting the safe sibling's result.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 delivers a complete, authentic, scope-matching evidence bundle. A2 binds the exact provider/model/prompt/runtime and artifact set, calls a real Judge, validates structured output, applies sample/latency/taxonomy policy, and emits the sole release decision. A3 verifies and displays that decision binding without recalculating it.
2. A1 supplies a valid run but the cloud Judge returns authorization failure or malformed semantics. A2 excludes it from the eligible denominator and emits INCOMPLETE/BLOCK, preserving hashes and public error class. A3 receives no PASS authority; its live deployment resolver may persist trusted rejection but cannot replace the missing A2 decision.

## Growth auditor

The intended diff is limited to A2-owned provider runtime, schemas, tests, deterministic
public calibration artifacts, public-safe evidence, scripts, and this worklog. It must
contain no key, bearer header, raw provider envelope, private reasoning, signed URL,
`ReleaseFoundry_key.txt`, `docs/evidence/private_refs/`, A1 source, or A3 source. Real local
failures remain blocked. The favorable DashScope ten-sample result remains
review-qualified only. PostgreSQL and Trusted Spine blockers are explicit. Submission is
valid only after full A2 tests, fixture regeneration check, both CL gates, `git
diff --check`, explicit file staging, push, and local/tracking/remote SHA equality.

## Exactly 20 Round 37 tasks

1. Add Wilson 95% intervals to DashScope sensitivity, specificity, and balanced-accuracy evidence.
2. Add a DashScope maximum-p95 latency policy and fail-closed blocker.
3. Bind the cloud endpoint region as a governed enum rather than a free-form endpoint class.
4. Add a deterministic transport-artifact hash for PPM-to-PNG conversion without persisting image bytes.
5. Add a test proving equivalent PPM bytes produce the same transmitted PNG hash.
6. Add a test proving a changed PPM changes both source and transport bindings.
7. Add at least five more text-free safe PNG controls for cloud calibration.
8. Add at least three samples for every governed attack taxonomy.
9. Add a benign-text safe taxonomy to measure visual-prompt false positives separately.
10. Add a no-text hallucination taxonomy with at least five distinct controls.
11. Repeat the exact DashScope binding enough times to measure run-to-run disagreement.
12. Compare `qwen-vl-plus` with one documented higher-quality Qwen-VL model under the same contract.
13. Add a provider/model response-identity mismatch blocker to cloud evidence.
14. Add explicit cloud timeout, HTTP 429, HTTP 5xx, malformed envelope, and empty-content tests.
15. Add cloud cost/usage metadata when the provider returns public token accounting.
16. Add a cross-provider disagreement artifact joining exact Ollama and DashScope bindings.
17. Add a governed human-review queue receipt for local/cloud disagreement.
18. Re-probe PostgreSQL and execute a real same-round persistence proof only if a safe target exists.
19. Build Trusted Spine only if exact authoritative A1 run, final A2 ledger/grades, and matching A3 scope coexist.
20. Refresh all refs, run exactly two micro and two macro simulations, growth audit, full A2 tests, fixture check, both CL gates, explicit staging, commit, push, and three-way SHA verification.
