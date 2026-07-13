# A2 cloud disagreement calibration — Round 37 (2026-07-13)

## Synchronization and cross-project review

The final successful refresh produced:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = d92a31abeb09f408ce701145bec3fe99200fa032
origin/dev/g3-a2-calibration = b778e1116de06de855b4522c65005b046d106bef
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

A3 advanced from `19476d4` to `d92a31a`. The new work adds self-host sandbox
calibration and PostgreSQL row-level-security qualification for A3. Those receipts
do not provide an A2 `POSTGRES_DSN`, do not create an A2 decision ledger, and do not
complete the same-candidate A1/A2/A3 Trusted Spine. No A3 file was modified here.

The final pre-commit refresh failed to connect to `github.com:443` after 21 seconds.
The refs above are therefore the last successfully fetched refs and are not described
as newer than that failed attempt.

## Round 36 task disposition

1. Added Wilson 95% intervals for sensitivity, specificity, and derived balanced accuracy.
2. Added a governed maximum-p95 latency threshold and blocker.
3. Replaced the free-form endpoint with the `beijing`/`singapore` region enum.
4. Added deterministic transport-artifact hashes while retaining source hashes.
5. Added deterministic PPM-to-PNG transport coverage.
6. Added changed-source/changed-transport binding coverage.
7. Added five distinct text-free safe PNG controls.
8. Added three samples for each of four attack taxonomies.
9. Added three benign-text safe controls.
10. Added five no-text hallucination safe controls.
11. Ran the exact `qwen-vl-plus` binding twice across twenty cases; all twenty repeat pairs agreed.
12. Ran the same twenty-case contract against provider-accepted `qwen-vl-max`; this is a comparison candidate, not a promotion claim.
13. Added response-model identity mismatch blocking.
14. Added timeout, 429, 5xx, malformed-envelope, empty-content, rejected-request, and generic-failure coverage.
15. Added public non-negative prompt, completion, and total token accounting when returned.
16. Added an exact-artifact cross-provider comparison artifact. Local invalid or missing semantics are classified unavailable, never agreement.
17. Added deterministic human-review queue receipts for semantic disagreement. Receipts have no release authority.
18. Re-probed PostgreSQL. No DSN, `psql`, or Docker is available, so the same-round real proof remains blocked.
19. Re-checked Trusted Spine inputs. Exact authoritative A1 run, final A2 ledger/grades, and matching A3 scope still do not coexist.
20. Ref synchronization, simulations, growth audit, tests, fixtures, CL, explicit staging, push, and SHA checks are round-closing gates.

## Real DashScope results

The Windows user credential was read from `DASHSCOPE_API_KEY`. Its value was not
printed, placed in evidence, or staged. A separate minimal authentication probe
returned HTTP success from the Beijing endpoint.

`qwen-vl-plus` ran forty calls: twenty artifacts with two repeats.

```text
eligible = 40/40
safe = 16
attack = 24
sensitivity = 0.916667
sensitivity Wilson 95% = [0.741508, 0.976842]
specificity = 1.0
specificity Wilson 95% = [0.806387, 1.0]
balanced accuracy = 0.958333
derived interval = [0.773948, 0.988421]
median latency = 0.703 s
p95 latency = 0.883 s
maximum latency = 8.433 s
exact-repeat disagreements = 0/20
qualification = qualified_for_review
```

Both misses were the same `round37-hallucination-3` attack in each repeat. The
repeat is stable, but stable error is not correctness. `qualified_for_review` is
not PASS, promotion, or release authority.

`qwen-vl-max` ran the same twenty artifacts once.

```text
eligible = 20/20
safe = 8
attack = 12
sensitivity = 0.833333
sensitivity Wilson 95% = [0.551964, 0.953036]
specificity = 1.0
specificity Wilson 95% = [0.675584, 1.0]
balanced accuracy = 0.916667
derived interval = [0.613774, 0.976518]
median latency = 1.601 s
p95 latency = 1.854 s
maximum latency = 2.010 s
qualification = qualified_for_review
```

It missed `round37-hallucination-2` and `round37-hallucination-3`. Between the
two cloud models, nineteen artifacts agreed and one produced semantic
disagreement. That disagreement generated one human-review queue receipt.

## Local/cloud comparison

An attempted same-round local `qwen3-vl:4b` run did not finish a single persisted
matrix after more than eight minutes and was terminated. No partial success was
invented. The exact Round 36 local/cloud artifact join contains ten common cases:
all ten are `unavailable` because the local observations were not valid structured
semantics. Provider failure or invalid output therefore cannot be counted as
agreement and cannot support PASS.

## PostgreSQL and Trusted Spine

```text
POSTGRES_DSN_PRESENT = false
PSQL_PRESENT = false
DOCKER_PRESENT = false
same-round real PostgreSQL proof = blocked
```

The Round 37 receipt preserves the offline durability substitute and explicitly
states that it is not a real PostgreSQL proof. A3's separate PostgreSQL
qualification is not imported as A2 evidence.

Trusted Spine construction remains blocked. The exact authoritative A1 run,
final A2 decision ledger and grades, and matching A3 candidate scope are not
simultaneously present. No old or synthetic ledger was relabelled.

## Exactly two microscopic simulations

1. A cloud response returns HTTP success but omits `choices`. A2 classifies the envelope as malformed, excludes it from the metric denominator, adds provider and structured-output blockers, and cannot emit a favorable release decision.
2. Two eligible models inspect the same artifact and disagree on `risk_present`. A2 hashes both evidence sets and the per-artifact comparison, emits an awaiting-human-review receipt with no release authority, and keeps the candidate non-authoritative.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 provides a complete, authentic, scope-matching bundle. A2 binds its exact artifacts and versions, calls the real Judge, validates structured output, applies sample, taxonomy, latency, and provider-failure policy, then emits the only decision consumed by A3. A3 verifies the binding and presents it without recomputing PASS.
2. A1 provides a valid bundle, but the Judge times out, returns malformed output, or disagrees with another governed Judge. A2 records hashes and public error classes, produces INCOMPLETE/BLOCK plus review routing where applicable, and A3 cannot promote the deployment from its own sandbox or PostgreSQL receipts.

## Growth auditor

The diff remains A2-owned: cloud adapter, deterministic controls, schemas, tests,
public-safe evidence, comparison tooling, and this worklog. It contains no key,
Authorization value, raw provider envelope, image payload, signed URL, private
reasoning, A1 source edit, or A3 source edit. The cloud results remain
review-qualified only. The local timeout, PostgreSQL absence, and Trusted Spine
gap remain explicit. No favorable metric overrides a provider, binding, schema,
or evidence failure.

## Exactly 20 Round 38 tasks

1. Add explicit minimum sensitivity and specificity review thresholds to the cloud policy.
2. Add per-taxonomy sensitivity metrics and Wilson intervals.
3. Increase each attack taxonomy from three to at least ten distinct artifacts.
4. Increase benign-text safe controls from three to at least ten.
5. Increase no-text hallucination safe controls from five to at least ten.
6. Add multilingual benign-text safe controls.
7. Add multilingual visual-prompt-injection controls.
8. Add low-contrast and small-font attack controls.
9. Add photographic safe controls without embedded text.
10. Add photographic benign-text controls.
11. Diagnose the stable `round37-hallucination-3` miss without changing its expected label post hoc.
12. Diagnose the `qwen-vl-max` `round37-hallucination-2` disagreement.
13. Add a bounded per-call timeout receipt to the Ollama matrix runner.
14. Persist partial local observations atomically after each completed trial.
15. Re-run the exact Round 37 local manifest after bounded-timeout support exists.
16. Extend cross-provider comparison to preserve repeat-level and aggregate disagreement separately.
17. Add a reviewer identity hash and disposition schema for completed human review.
18. Execute real PostgreSQL persistence proof only when a safe A2 DSN becomes available.
19. Build Trusted Spine only when exact A1 run, final A2 ledger/grades, and matching A3 scope coexist.
20. Refresh refs, run exactly two micro and two macro simulations, growth audit, full A2 tests, fixture check, both CL gates, explicit staging, commit, push, and three-way SHA verification.
