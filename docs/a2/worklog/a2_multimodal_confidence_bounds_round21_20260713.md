# A2 multimodal confidence bounds — Round 21 (2026-07-13)

## Synchronization and prior closure

Independent `ls-remote` verified the Round 20 remote SHA before this round:

```text
6b62f978e4e8284d15efc99af76be79188c1cf3b refs/heads/dev/g3-a2-calibration
```

A fresh `git fetch --all --prune` then failed:

```text
Failed to connect to github.com:443 after 21091 ms: Could not connect to server
```

Last locally available refs reviewed, not claimed as fresh after the failed fetch:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = f9562494d427c430c043c4316d91eb2510df62a1
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = 0ae871ffd1c1ad6fc99f7028b40436f3cfeeb288
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

## Prior 20 tasks

1. Added a strict Round 20 specificity fixture schema.
2. Added schema validation for that fixture.
3. Added a vendor-independent OCR observation schema.
4. Added code-boundary validation for OCR adapter version hashes.
5. Added count/min/max/mean confidence summaries without text or coordinates.
6. Added process RSS before/after/delta measurements.
7. Ran all three controls with real `qwen3-vl:4b`.
8. Recorded model/prompt digests, seed, latency and eval counts.
9. Compared providers only where valid: Qwen empty outputs make specificity non-comparable.
10. Added Wilson intervals for recall and specificity.
11. Added a minimum specificity lower-bound promotion gate.
12. Added a maximum false-positive-rate promotion gate.
13. Added prompt lineage cycle detection.
14. Rejected self-supersession.
15. Added CR, CRLF and trailing-space canonicalization tests.
16. Persisted OCR failure as a hash-only A2 result record.
17. PostgreSQL remains absent; offline persistence and full A2 tests are the substitute.
18. Attempted refresh and reviewed exact available cross-lane refs.
19. Simulated changed token-box hashes under unchanged OCR text via hash-bound tokens.
20. Simulated A3 consuming the A2 BLOCK; no downstream specificity recomputation is authorized.

## Real qwen3-vl observation

Binding: `qwen3-vl:4b`, digest `sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683`, prompt digest `sha256:afc82346c9732849e5e39ee5d7f248a2f4d8f1efea6b97144b1c91ad0ee3bff9`, seed 11, temperature 0.

All three real calls returned HTTP-successful Ollama responses with `done_reason=stop` but an empty `response` field:

- safe report: 4.674 s, eval count 29;
- text-free blue: 4.240 s, eval count 25;
- benign amber: 4.445 s, eval count 28.

The provider is faster than the observed LLaVA calls, but the structured output is malformed. A2 records `malformed_empty_response`, blocks the binding, and marks specificity comparison `not_comparable`; speed cannot compensate for invalid output.

## Microscopic simulations

### Micro 1 — unchanged text, changed boxes

Two OCR observations may contain identical normalized text while token geometry changes. The text hash stays stable, the token-box hash changes, and A2 requires a new auditable observation without publishing coordinates.

### Micro 2 — perfect point estimate, weak lower bound

A tiny safe-control set can have specificity 1.0 while its Wilson lower bound remains below policy. A2 blocks promotion on `specificity_lower_bound_below_policy`, preventing small-sample overconfidence.

## Macroscopic A1/A2/A3 simulations

### Macro 1 — A1 OCR provider failure

A1 evidence arrives while OCR raises a provider exception. A2 persists only a redacted/hash-only failure observation, keeps deterministic closure, and returns INCOMPLETE rather than PASS. A3 renders the committed state.

### Macro 2 — superseded BLOCK

A2 detects a prompt lineage cycle or a specificity/FPR policy violation and commits BLOCK. A3 consumes the exact decision hash and provenance; it may not relabel the prompt or recompute specificity.

## Validation

```text`n41 focused multimodal tests passed`n50 focused multimodal/persistence tests passed`n404 A2 tests passed`n56/56 generated fixtures matched`nPOSTGRES_DSN absent; psql absent; docker absent`ngit diff --check passed`n```

## Growth auditor

All prior 20 tasks have code, schema, test, fixture, real-model or environment evidence. Qwen's empty output is a useful fail-closed compatibility finding, not a successful judge qualification. Only explicit A2-owned paths may be staged; commit, push and three-way SHA equality remain mandatory.

## Exactly 20 narrow tasks for Round 22

1. Add a strict schema for the Round 21 Qwen observation fixture.
2. Validate the Round 21 Qwen fixture against that schema.
3. Capture Ollama raw-response hashes for malformed structured output.
4. Add structured-output failure taxonomy shared across local models.
5. Retry Qwen with its model-specific non-thinking output option.
6. Retry Qwen without Ollama `format=json` and govern repair separately.
7. Add a maximum structured-output repair count policy.
8. Compare repaired and unrepaired output hashes.
9. Add OCR RSS peak sampling rather than before/after only.
10. Add token-box hash canonicalization independent of token ordering.
11. Add Wilson interval schemas constrained to [0,1].
12. Add sample-size-aware minimum lower-bound fixtures.
13. Add prompt lineage schema and maximum lineage depth.
14. Persist prompt supersession records through result persistence.
15. Add an A2 decision-consumption fixture for superseded BLOCK.
16. Verify A3 consumption rejects a recomputed specificity field.
17. Recheck PostgreSQL and execute the offline persistence substitute if absent.
18. Refresh and review main, A1, A3 and strategy refs.
19. Simulate A1 replaying an old OCR box hash with new text.
20. Simulate provider latency success combined with malformed output BLOCK.
