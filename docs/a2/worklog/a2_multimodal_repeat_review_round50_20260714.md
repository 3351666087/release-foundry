# A2 Round 50 — source-complete repeats, local timeout evidence, and review binding

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`
A2 base: `1553562bdd1505f4bf7f17a6252c88a9faea6638`

## Scope and upstream review

Only A2-owned files are changed. The final pre-gate fetch reviewed:

- main: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- A1 active branch: `23072311c80395989adaba1bd164265bd67517b1`
- A2 tracking branch: `1553562bdd1505f4bf7f17a6252c88a9faea6638`
- A3 active branch: `cf29d9f0d054ad51b9727b7782e16a8167f6eeae`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

A3 advanced by two commits and now implements a bounded multimodal disagreement
queue plus reviewer-assignment leases. Its reviewed contract requires upstream
and queue-receipt `release_authority=false` and does not recompute A2's release
decision. This is directionally aligned with A2. It still expects
`a3-golden-20260712-002`, while A1 exposes `round62-source-candidate` through a
receipt whose SHA does not match the current A1 ref. A2 therefore still has no
exact shared candidate identity and did not generate a Trusted Spine.

## Round 50 task disposition

1. Added two distinct-source attacks for rotation 2 degrees.
2. Added two distinct-source attacks for rotation 6 degrees.
3. Added two distinct-source attacks for JPEG quality 53.
4. Added one distinct-source attack for JPEG quality 60.
5. Removed the duplicated historical 10-degree source from the Round 50 manifest and replaced its coverage with a distinct source.
6. Established a 74-case source-hash-complete Round 50 manifest.
7. Ran two independently bounded real DashScope repeats.
8. Added source-unit paired deterministic bootstrap comparison without pooling raw repeats.
9. Retained `dashscope_pricing_unavailable`; no Singapore USD price or self-converted CNY price was represented as authoritative Beijing pricing.
10. Split latency evidence into effective provider-network, structured-output retry, final-attempt, and total-wall receipts.
11. Exercised one real invalid-structured-output retry that remained ineligible and blocking.
12. Added five distinct-source `cross_modal_conflict` attacks.
13. Added five distinct-source `visual_prompt_injection` attacks.
14. Added five visually diverse no-text safe controls.
15. Produced a real cloud/cloud/local comparison with no provider designated as truth.
16. Made review-conservation hash a mandatory image release expected binding.
17. Re-probed PostgreSQL; the runtime remains absent, so the 39-test/163-subtest offline substitute was refreshed.
18. Added a strict A1/A2/A3 shared-candidate identity schema and semantic verifier.
19. Refused Trusted Spine generation because candidate IDs, SHAs, decision/grades bindings, real PostgreSQL proof, calibration, and pending review do not align.
20. Re-fetched active refs and completed exactly two microscopic simulations, two macroscopic simulations, one growth audit, and the required pre-commit gates.

## Real DashScope repeat evidence

The Windows CurrentUser `DASHSCOPE_API_KEY` was reused through the environment.
Its value was not printed, copied into evidence, deleted, overwritten, or
committed.

Both 74-case runs used `dashscope/qwen-vl-plus` in the Beijing region with the
same manifest, ordered case plan, policy, prompt, output schema, and provider
capability bindings. Both remain `blocked`.

| Metric | Run A | Run B |
|---|---:|---:|
| requests attempted | 74 | 75 |
| eligible observations | 74 | 73 |
| sensitivity | 0.5556 | 0.5660 |
| specificity | 0.9500 | 0.9500 |
| balanced accuracy | 0.7528 | 0.7580 |
| total-wall median | 2.376s | 1.865s |
| total-wall p95 | 6.512s | 3.234s |
| total-wall max | 32.331s | 10.352s |
| total tokens | 13,215 | 14,052 |

Run B made one additional request because an invalid structured output was
retried. The retry did not recover a valid observation. The artifact retains
`dashscope_invalid_structured_output_observed`, excludes the invalid source unit
from eligibility, and remains blocked.

All required perturbation buckets are now present with at least three distinct
source hashes. That closes the coverage defect but does not create robustness:
rotation 2, 5, and 6 degrees each measured only 0.3333 sensitivity; JPEG quality
53 also measured 0.3333. Both runs measured `cross_modal_conflict` sensitivity
at 0.35 and `visual_prompt_injection` sensitivity at 0.625. One of five
benign-text controls was a false positive in each run, so the Wilson upper
bound remains blocking.

The paired source-unit comparison uses `perturbation bucket +
source_case_hash` as the experimental unit. It matched 28 units and measured a
zero sensitivity delta, but one Run A source unit was missing from Run B after
the unrecovered invalid output. It therefore records
`source_repeat_units_missing_from_repeat` and is not promotion eligible.

## Real local Qwen3-VL evidence

The installed local model was bound as:

`qwen3-vl:4b=sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683`

The 15-case reviewed subset attempted 15 calls. Every call reached the
40-second per-case timeout, for 599.682 seconds of accumulated case wall time.
There were zero completed or eligible trials. This is retained as real
fail-closed capability/latency evidence, not as a quality score and not as
ground truth.

The cloud/cloud/local comparison contains 72 cloud agreements with local
unavailable, one cloud semantic disagreement, and one unavailable case. The
semantic disagreement produced one queue receipt. No human reviewer was
fabricated: review conservation is verified with one pending and zero reviewed
receipts.

## PostgreSQL and persistence

`POSTGRES_DSN`, `psql`, and Docker are absent. Same-round real PostgreSQL proof
is blocked by those three exact facts. The offline substitute passed:

- `39 passed, 163 subtests passed`
- file synchronization and atomic JSONL replacement
- manifest reopen verification
- replay rollback/fork detection
- SQL-store contract coverage

No claim of same-round PostgreSQL parity is made.

## Microscopic simulations (exactly 2)

1. A DashScope response is syntactically invalid on its first attempt and remains invalid after the one authorized retry. A2 counts both requests, records retry wall time separately, excludes the case from quality denominators, emits the invalid-output blocker, and cannot return PASS.
2. Two repeat artifacts share every top-level binding, but one perturbation/source-hash unit is absent after provider-invalid output. A2 refuses to pool the remaining raw repeats, emits `source_repeat_units_missing_from_repeat`, and prevents bootstrap stability from being interpreted as promotion evidence.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 supplies a complete image evidence bundle under one exact candidate ID. A2 verifies artifact/source hashes, invokes the real judge, validates structured output, applies policy, binds review conservation, and emits PASS/BLOCK/INCOMPLETE. A3 may lease and display A2 disagreement receipts but cannot recompute or override the A2 decision.
2. A1 names `round62-source-candidate` with a stale receipt SHA, A2 has no shared candidate ID, A3 names `a3-golden-20260712-002`, cloud calibration is blocked, one human review remains pending, and real PostgreSQL proof is absent. The shared-candidate verifier and Trusted Spine recheck fail closed; A3 must preserve the blocked state.

## Growth audit (exactly 1)

Round 50 closes the source-diversity gaps and replaces local-model assumptions
with measured timeout evidence. It also adds reusable semantic enforcement for
one shared A1/A2/A3 candidate and makes review-conservation provenance mandatory
for image release bindings. The audit rejects overclaiming: two nearly equal
cloud scores do not prove repeatability when a source unit is missing; 95%
specificity does not erase weak attack sensitivity; an installed local model
is not a usable judge when every bounded call times out; an A3 review UI is not
release authority; offline durability tests are not a real PostgreSQL proof.

Verification:

- focused Round 50 suite: `39 passed, 10 subtests passed`
- release binding and shared-candidate suite: `17 passed`
- Round 50 evidence suite: `5 passed`
- full A2 suite: `624 passed, 1163 subtests passed`
- persistence substitute: `39 passed, 163 subtests passed`
- generated fixtures: all `56` matched
- CL hygiene: passed with zero findings
- CL commercial: passed with zero blockers and zero advisories
- changed-file secret scan: passed with zero findings

## Round 51 narrow tasks (exactly 20)

1. Diagnose whether `qwen3-vl:4b` timeouts originate in model warm-up, image preprocessing, token generation, or Ollama transport.
2. Run one bounded single-case cold/warm Qwen3-VL latency probe with phase receipts.
3. Test a lower `num_predict` Qwen3-VL profile without weakening structured-output validation.
4. Test Ollama JSON-schema mode for Qwen3-VL and retain fail-closed evidence if unsupported.
5. Run the same 15-case subset against `llava:7b` under the current bounded runtime contract.
6. Compare Qwen3-VL and LLaVA availability without designating either model as truth.
7. Add a third real DashScope source-complete repeat with an independently bounded request budget.
8. Require all source units across all retained repeats before producing a promotion-eligible stability interval.
9. Add bootstrap intervals for specificity and benign-text false-positive rate at source-unit granularity.
10. Add taxonomy-level paired bootstrap intervals for `cross_modal_conflict` and `visual_prompt_injection`.
11. Expand no-text safe controls by five distinct visual styles.
12. Expand benign visible-text safe controls by five distinct source hashes.
13. Add five adversarial image-text conflicts whose visible text is safety guidance rather than an attack.
14. Add an explicit maximum false-positive count policy for small reviewed control sets.
15. Add a machine-readable review collection schema instead of relying on an untyped empty receipt collection.
16. Exercise a real human-review receipt when a reviewer is available; otherwise retain the queue as pending.
17. Add release-gate regression proving a mismatched review-conservation hash blocks an otherwise qualified image candidate.
18. Re-probe PostgreSQL and run a real proof if DSN/client/runtime becomes available; otherwise refresh the exact blocker receipt.
19. Re-fetch A1/A2/A3 and validate any newly exposed candidate identity through the shared-candidate verifier before Trusted Spine generation.
20. Run exactly two micro simulations, two macro simulations, one growth audit, full A2 tests, fixture regeneration, both CL gates, secret scan, explicit commit/push, SHA equality, and clean-tree verification.
