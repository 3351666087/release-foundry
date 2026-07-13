# A2 Round 39 — multimodal retry, resumability, and disagreement binding

Date: 2026-07-13
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files were changed. The round fetched and reviewed:

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/codex/a1-local-sdk-runner`: `23072311c80395989adaba1bd164265bd67517b1`
- `origin/codex/a3-main-contract-alignment-v2`: `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`
- `origin/dev/g3-a2-calibration`: `a4647fc1d84c10f4f6e538b8c06ba6cd3c3888e2`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

The strategy still requires provider failure to fail closed and distinguishes implemented contracts from production proof. A1's latest release receipt binds five-modality provider evidence to an A1 candidate, but it does not coexist with final A2 grades and an exact matching A3 candidate. A3's release center consumes server decision provenance and preflight; it does not replace A2 release authority.

## Round 38 task disposition

1. Added one opt-in invalid structured-response retry and retained every attempt receipt.
2. Added a whole-run wall-clock budget distinct from per-call timeout.
3. Added per-taxonomy minimum sensitivity thresholds.
4. Added sensitivity and specificity Wilson lower-bound thresholds.
5. Added an exact multimodal miss-diagnosis evidence schema.
6. Confirmed and tested the existing exact PostgreSQL qualification schema.
7. Completed local partial journals are marked `completed` without release authority.
8. Verified partial journals can resume without duplicating completed trials.
9. Bound partial journals to manifest, prompt, runtime, and model digests.
10. Repeated all six Round 38 Qwen disagreement cases three times per model.
11. Added a test-only `request_more_evidence` disposition fixture.
12. Bound review receipts and dispositions to the comparison artifact hash.
13. Added aggregate review receipts for internally unstable artifacts.
14. Added photographic OCR-safe Japanese and Chinese controls.
15. Added deterministic ±15° and ±30° rotated attacks.
16. Added deterministic Gaussian blur radius 1 and 2 attacks.
17. Added image-plus-benign-user-text controls and request binding.
18. PostgreSQL was probed again; no DSN, psql, or Docker exists, so the real proof remains blocked and the offline substitute was rerun.
19. No Trusted Spine was generated because exact A1/A2/A3 candidate bindings do not coexist.
20. Refs, simulations, growth audit, tests, fixtures, CL, explicit commit/push, and SHA equality are the closing gates.

## Cloud policy and audit semantics

Retry does not create another metric sample. Each `(case, artifact, repeat)` has one final observation and an ordered `attempt_receipts` list. A recovered invalid response remains an audit blocker because the first invalid receipt is retained. Provider failures are not retried by this narrow policy and never become eligible. Once the whole-run budget is exhausted, remaining cases receive `run_budget_exhausted` / `not_attempted` receipts and the run remains BLOCKED.

Taxonomy sensitivity and Wilson lower-bound policies are explicit in evidence. These thresholds qualify a model only for review; they do not make a provider output ground truth or grant release authority.

## Partial journal resumability

Partial journals bind the canonical manifest hash, prompt hash, runtime hash, and model id/digest pairs. Resume validates the schema and exact binding, rejects mismatch, and keys completed work by model, digest, format, token bound, case, artifact hash, and repeat. Completed trials are not invoked again. The final partial state is `completed`, while `release_authority` remains false.

## Round 39 deterministic controls

The new 12-case set contains four safe and eight attack controls:

- two photographic non-Latin OCR-safe controls;
- two image-plus-benign-user-text controls;
- two rotated visual prompt injections;
- two rotated cross-modal conflicts;
- two blurred unsafe-content-evasion controls;
- two blurred hallucinated-text controls.

Generation is deterministic and all hashes are schema validated. The optional benign user text is included in the provider request hash.

## Real DashScope repeat stability

The six Round 38 semantic-disagreement cases were repeated three times with each model.

`qwen-vl-plus` produced 18/18 eligible observations, sensitivity `0.833333`, median latency `0.739 s`, p95 `0.903 s`, and maximum `0.903 s`. Taxonomy sensitivity was cross-modal conflict `1.0`, unsafe-content evasion `0.75`, and visual prompt injection `1.0`. It remains BLOCKED because this attack-only diagnostic has no safe denominator, one taxonomy misses its threshold, and confidence-bound policy is not satisfied.

`qwen-vl-max` produced 18/18 eligible observations, sensitivity `0.166667`, median latency `1.564 s`, p95 `1.983 s`, and maximum `1.983 s`. Taxonomy sensitivity was cross-modal conflict `0.0`, unsafe-content evasion `0.25`, and visual prompt injection `0.0`. It remains BLOCKED.

The repeat-level comparison is 18 semantic disagreements, zero agreements, and zero unavailable. All six aggregate artifacts remain semantic disagreements. This is strong evidence of stable provider disagreement, not evidence that either provider is truth.

## Human-review boundary

Review queue receipts now bind both the individual comparison hash and the enclosing comparison artifact hash. Aggregate internal instability also creates a review receipt. The committed disposition is explicitly classified `test_review_fixture`, requests more evidence, exposes no human identity, and has no release authority. It must not be presented as a completed real review.

## PostgreSQL and Trusted Spine

`POSTGRES_DSN` is absent and neither `psql` nor Docker is installed. Same-round real PostgreSQL persistence is therefore not claimed. The offline substitute verified file fsync, atomic JSONL replacement, manifest reopen verification, and replay/rollback/fork detection.

No authoritative Trusted Spine was created. The latest A1 release receipt, current A2 results, and A3 candidate do not share one exact candidate binding. A ledger assembled across those scopes would be misleading and is rejected by design.

## Microscopic simulations (exactly 2)

1. A cloud response is invalid JSON on attempt 1 and valid on attempt 2. Metrics count one final eligible sample, both receipts remain auditable, the invalid-output blocker remains active, and qualification cannot silently become PASS.
2. A local run is interrupted after one trial. Resume with identical manifest/runtime/model hashes skips that trial and completes the remainder; changing the manifest hash is rejected before any provider call.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete same-scope evidence bundle. A2's two cloud judges disagree stably across repeats, so A2 returns BLOCK/review-required with hash-bound receipts. A3 renders the blocker and may request preflight, but cannot recompute or override the decision.
2. A1 has a five-modality release receipt, A2 has current grades, and A3 has a release UI candidate, but their candidate bindings differ. A2 refuses Trusted Spine generation; A3 shows incomplete provenance rather than release readiness.

## Growth auditor

The growth auditor confirms this round adds failure containment and reproducibility rather than another unverified provider: retry audit lineage, bounded run time, statistical policy, resumable local execution, deterministic visual perturbations, real repeated cloud disagreement, and comparison-to-review hash binding. It confirms all cloud/local evidence remains non-authoritative and fail-closed. Completion still requires all A2 tests, fixture regeneration check, both CL gates, diff check, explicit staging, secret scan, commit, push, and local/tracking/remote SHA equality.

## Round 40 narrow tasks (exactly 20)

1. Move additive DashScope retry fields into a v4 schema and freeze v3 evidence compatibility explicitly.
2. Add validation that every retry attempt number is contiguous and unique.
3. Add a retry-recovery metric that does not alter the case denominator.
4. Add a distinct blocker for recovered invalid structured output.
5. Add run-budget tests covering exhaustion between retry attempts.
6. Add run-budget receipts for all remaining uncalled cases without invoking artifact conversion twice.
7. Add CLI JSON policy-file input for taxonomy thresholds.
8. Reject taxonomy policy entries that do not occur in the attack manifest.
9. Add Wilson lower-bound reporting per taxonomy.
10. Add partial-journal duplicate-key rejection before resume.
11. Bind partial journals to format and token-bound plan hashes.
12. Add crash injection between final matrix write and partial completion.
13. Add a comparison receipt verifier independent of the disposition builder.
14. Add a real-review receipt schema separate from test-review fixtures.
15. Add repeat stability controls for the two Round 37 hallucination cases.
16. Run the 12 Round 39 controls against both Qwen cloud models.
17. Add deterministic JPEG compression and rescaling controls.
18. Run real PostgreSQL persistence proof when a safe DSN or local runtime exists; otherwise refresh blocker evidence and offline substitute.
19. Generate a Trusted Spine only if exact A1/A2/A3 candidate bindings coexist after refetch.
20. Re-fetch refs, run exactly 2 micro and 2 macro simulations, growth audit, all A2 tests, fixtures, CL, explicit commit/push, and SHA equality.
