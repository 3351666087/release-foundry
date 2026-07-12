# A2 multimodal output governance — Round 22 (2026-07-13)

## Synchronization

`git fetch --all --prune` succeeded. The exact reviewed refs are:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 8685a9cf0bbbdd045e7775eff536f235235f6cc6
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

A1 added restart-safe/provider-neutral dispatch work and generated TypeScript parity evidence. A3 added live GitHub readbacks. Neither changes A2's authority boundary: A1 supplies evidence, A2 commits the decision, and A3 displays exact committed provenance without recomputing specificity or release state.

## Disposition of the prior 20 tasks

1. Added a strict Round 21 Qwen fixture schema.
2. Validated the Round 21 fixture against it.
3. Captured raw Ollama envelope and response hashes in the Round 22 fixture.
4. Added a provider-independent structured-output failure taxonomy.
5. Retried Qwen using `think=false` and a `/no_think` prompt binding.
6. Retried without Ollama `format=json`; valid JSON returned.
7. Added an explicit maximum repair count.
8. Preserved distinct original/repaired hashes and tested count exhaustion.
9. Added OCR RSS peak sampling.
10. Canonicalized token records independently of token order.
11. Constrained all Wilson interval schema values to `[0,1]`.
12. Retained the sample-size-aware Wilson lower-bound promotion test.
13. Added prompt lineage schema and maximum depth.
14. Persisted prompt supersession through the public-safe result record path.
15. Added a superseded BLOCK A2/A3 consumption fixture.
16. Rejected A3-supplied `specificity` and `recomputed_specificity`.
17. Rechecked PostgreSQL; `POSTGRES_DSN`, `psql`, and Docker are absent. Focused and full offline persistence tests are the substitute, not a PostgreSQL proof.
18. Refreshed and reviewed main, A1, A3, and strategy refs.
19. Simulated replay of old OCR boxes with changed text; the combined OCR binding hash changes.
20. Simulated HTTP/provider completion plus malformed empty output; it remains BLOCK.

## Real Qwen output-mode probe

Binding:

```text
model = qwen3-vl:4b
model digest = sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
prompt hash = sha256:1d99f31b951714e39315faffec69f605ffd7ddb5771575fc08465d55365c8165
seed = 11
temperature = 0
thinking = false
```

With `format=json`, all three calls completed with `done_reason=stop` but empty responses. They took 98.280–108.546 seconds. Without `format=json`, all three returned parseable JSON and classified the safe controls as `safety_risk=none`, but took 40.406–50.540 seconds. The plain-mode safe-control point specificity is `1.0`, but the sample is too small and every request exceeds the 30-second policy. The binding remains BLOCK; recovered syntax does not establish calibration or release authority.

Evidence:

```text
fixtures/a2/calibration/qwen3_vl_4b_round22_output_mode_observations.json
```

## Microscopic simulations

### Micro 1 — old boxes, new text

A1 replays a canonical token-box set while changing OCR text from `SAFE REPORT` to `ATTACK REPORT`. The order-independent token-box hash remains stable, but the combined `ocr_binding_hash` changes because it binds text hash and box hash. A2 rejects any claim that the old OCR observation is identical.

### Micro 2 — fast provider status, malformed payload

The provider returns HTTP success and `done_reason=stop`, but the response is empty. The failure classifier emits `empty_response`, hashes the raw bytes, sets qualification to BLOCK, requires review, and grants no release authority. Transport success cannot become semantic success.

## A1/A2/A3 macroscopic simulations

### Macro 1 — superseded prompt BLOCK

A1 provides evidence evaluated under an older prompt. A2 records BLOCK and a prompt supersession edge with bounded lineage depth. A3 displays the exact committed BLOCK and hash. Any A3 `specificity` field or recomputed release field is rejected.

### Macro 2 — OCR replay plus local-model latency

A1 supplies evidence whose OCR boxes match an older observation but whose text changed. A2 detects the changed combined binding and invokes the local Qwen observation path. Qwen returns valid plain JSON but exceeds latency and sample-size policy, so A2 commits BLOCK/INCOMPLETE rather than PASS. A3 consumes only that committed state.

## Growth auditor

All 20 prior tasks have code, schema, fixture, test, environment, synchronization, or real-model evidence. Only A2-owned paths are changed. The latest candidate still lacks:

- a calibrated low-latency multimodal binding;
- sufficient safe/attack/taxonomy sample sizes;
- a same-candidate real PostgreSQL persistence proof;
- a new authoritative Trusted Spine/Decision Ledger binding the eventual latest A1/A2/A3 SHAs and grades.

Commit, push, and three-way SHA equality are mandatory before this round is closed.

## Exactly 20 narrow tasks for Round 23

1. Add a strict schema for the Round 22 Qwen output-mode fixture.
2. Validate exactly three JSON-mode and three plain-mode observations.
3. Add a latency percentile summary for each output mode.
4. Add a timeout ceiling independent of provider HTTP status.
5. Add a maximum generated-token policy for local multimodal judges.
6. Record Ollama thinking-token metadata when the protocol exposes it.
7. Test Qwen plain mode on at least three attack controls.
8. Calculate recall and specificity from one shared Qwen prompt binding.
9. Add a minimum ten-safe-control promotion fixture.
10. Add a minimum per-attack-taxonomy promotion fixture.
11. Add a hallucinated-text disagreement reason code.
12. Bind OCR text presence to visual-model `contains_text` disagreement.
13. Add a human-review packet for OCR/vision text disagreement.
14. Add OCR peak-sample count and sampling interval fields.
15. Reject non-finite OCR confidence values.
16. Persist structured-output failure receipts as hash-only result records.
17. Add a Trusted Spine candidate manifest template for exact A1/A2/A3 SHAs.
18. Reject stale Trusted Spine manifests against the current A2 decision hash.
19. Recheck PostgreSQL and run the offline substitute if still absent.
20. Refresh and review main, A1, A3, and strategy refs before Round 23 commit.
