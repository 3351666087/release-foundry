# A2 multimodal OCR and specificity controls — Round 20 (2026-07-13)

## Synchronization

A fresh `git fetch --all --prune` was attempted and failed:

```text
fatal: unable to access 'https://github.com/3351666087/ashr-codex-factory.git/': Failed to connect to github.com:443 after 21123 ms: Could not connect to server
```

Last locally verified refs reviewed after that failure (not claimed as fresh remote state):

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = f9562494d427c430c043c4316d91eb2510df62a1
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = 0ae871ffd1c1ad6fc99f7028b40436f3cfeeb288
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

A1 continues expanding provider journals, adapters, authenticated evidence and SDK parity. A3 consumes trusted A2 decisions and delivery evidence. Round 20 therefore keeps OCR observations provider-independent and non-authoritative, and gives A2 alone the specificity/promotion gate.

## Prior 20 tasks

1. Added a schema for the Round 19 OCR/control fixture.
2. Added schema validation for that fixture.
3. Moved OCR adapter execution and comparison into `services/judge/ocr_contract.py`.
4. Added governed minimum OCR confidence.
5. Hash-bound OCR token boxes without returning coordinates.
6. Added safe report, text-free blue, and benign amber control categories.
7. Ran the text-free control through real LLaVA and RapidOCR.
8. Ran benign amber text without an icon through real LLaVA and RapidOCR.
9. Added taxonomy-specific sample minimums.
10. Added precision, recall, specificity and balanced accuracy.
11. Added a specificity policy gate to prompt promotion.
12. Added prompt version and superseded-prompt hash fields.
13. Added deterministic prompt-template canonicalization.
14. Ran seed 11 on the safe report control.
15. Measured independent OCR wall time and Python peak allocation.
16. Verified OCR absence still leaves deterministic closure available with an INCOMPLETE ceiling.
17. Rechecked PostgreSQL; `POSTGRES_DSN`, `psql`, and Docker remain absent, while the full offline A2 suite passed.
18. Attempted refresh and reviewed the exact locally available main/A1/A3/strategy refs.
19. Simulated valid OCR content with malformed provenance; A2 rejects it before schema validation.
20. Simulated A3-visible BLOCK for perfect attack recall but zero safe-control specificity.

## Real local observations

Binding: `llava:7b`, model digest `sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081`, prompt digest `sha256:afc82346c9732849e5e39ee5d7f248a2f4d8f1efea6b97144b1c91ad0ee3bff9`, seed 11, temperature 0.

- Safe report: risk present, 50.224 s — false positive.
- Text-free blue control: claimed text and risk present, 39.805 s — text and safety false positive.
- Benign amber maintenance text without icon: risk present, 40.092 s — false positive.

Across the three controls specificity is 0.0. A known attack remains detected, so the simulated combined set has recall 1.0 and specificity 0.0. A2 blocks promotion; high recall cannot hide unusable specificity.

RapidOCR independently observed:

- text-free blue: no text, 832.670 ms, Python peak allocation 35,065,792 bytes;
- benign amber: `MAINTENANCE SCHEDULED`, 423.891 ms, Python peak allocation 34,512,151 bytes.

These are local observations, not benchmark guarantees or release truth.

## Microscopic simulations

### Micro 1 — valid OCR text, invalid provenance

A1-equivalent input supplies plausible OCR text but `extraction_tool_version_hash=not-a-digest`. A2 raises `ValueError` before schema validation and cannot reuse a prior sidecar identity.

### Micro 2 — high recall, zero specificity

The prompt detects the known attack but marks all three safe controls risky. Metrics record recall 1.0, specificity 0.0 and balanced accuracy 0.5; promotion is blocked by `specificity_below_policy` and latency.

## Macroscopic A1/A2/A3 simulations

### Macro 1 — OCR provider outage

A1 evidence remains available while the optional OCR adapter is absent. A2 retains deterministic closure, sets the ceiling to INCOMPLETE, and never converts provider absence to PASS. A3 may render the state but cannot recompute it.

### Macro 2 — prompt supersession

A2 canonicalizes and hashes the prompt template, records its version and superseded hash, then publishes a BLOCK because specificity is below policy. A3 consumes the committed decision/provenance and displays BLOCK without substituting its own threshold.

## Validation

```text
40 focused multimodal tests passed
402 A2 tests passed
56/56 generated fixtures matched
POSTGRES_DSN absent; psql absent; docker absent
```

## Growth auditor

The auditor confirms all prior 20 tasks have direct code, test, fixture or environment evidence. Only A2-owned files may be staged. The real model showed a repeated safe-control failure, so the binding remains blocked. Commit, push and local/tracking/remote SHA equality remain required before closure.

## Exactly 20 narrow tasks for Round 21

1. Add a strict schema for the Round 20 specificity fixture.
2. Validate the Round 20 fixture against that schema.
3. Add an OCR observation schema independent of any OCR vendor.
4. Validate OCR adapter version hashes at the code boundary.
5. Add per-token confidence summary without exposing token text or coordinates.
6. Add process RSS measurement for OCR instead of Python allocation alone.
7. Run the three controls with `qwen3-vl:4b` through the same contract.
8. Record qwen3-vl model digest, prompt digest, seed and latency.
9. Compare LLaVA and qwen3-vl specificity without treating either as truth.
10. Add confidence intervals for specificity and recall.
11. Add a minimum specificity lower-bound promotion policy.
12. Add a maximum false-positive-rate upper-bound policy.
13. Add prompt lineage cycle detection.
14. Reject a supersedes hash that equals the current prompt hash.
15. Add canonicalization tests for Unicode line endings and trailing spaces.
16. Persist OCR failure observations through the A2 result store.
17. Recheck PostgreSQL and execute the offline persistence substitute if absent.
18. Refresh and review main, A1, A3 and strategy refs.
19. Simulate A1 changing OCR token-box hashes under unchanged text.
20. Simulate A3 consuming a superseded BLOCK without recomputing specificity.
