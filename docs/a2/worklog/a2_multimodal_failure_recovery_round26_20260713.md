# A2 multimodal failure taxonomy and recovery evidence — Round 26 (2026-07-13)

## Synchronization

Fresh `git fetch --all --prune` succeeded immediately before closure:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/agent/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

A1's five-modality receipts strengthen provenance inputs but do not transfer release authority. A3 remains a consumer of committed A2 decisions and may not recompute them.

## Round 26 task disposition

1. Added a schema-validated, hash-safe Round 25 Qwen runtime diagnostic receipt.
2. Bound request start, client termination, and observed server recovery timestamps.
3. Split provider timeout, client cancellation, and transport failure counts and blockers.
4. Bound post-termination Ollama health as observed recovery; this proves service health, not server-side request cancellation.
5–6. Added maximum empty-response and invalid-structured-output rates.
7. Added taxonomy false-positive and false-negative Wilson intervals.
8. Added explicit recall/specificity denominators; zero denominators yield `[0.0, 0.0]` rather than invented confidence.
9. Added independent minimum valid safe-control and attack-control gates.
10. Added tests proving ten-safe/five-attack policy cannot be satisfied by one valid sample each.
11. No smaller model was installed: C: free space fell to 0.24 GB, making installation unsafe.
12. Qwen and LLaVA remain non-promotable.
13. Added rotated, low-contrast, and safe icon mutation fixtures.
14. Detector-version mutation changes the bound fixture hash and cannot be treated as the same provenance.
15. Added JSONL exact-byte, ordered-record-hash, round-trip, and tamper verification.
16. Disk remains the environmental blocker; no unsafe cleanup or installation was attempted.
17. PostgreSQL transaction/RLS proof remains absent because no safe DSN/tooling exists.
18. Required refs were refreshed above.
19. Authoritative Trusted Spine remains deferred until exact final cross-project SHAs, results, and grades exist.
20. Simulations, growth audit, complete tests, CL Gate, explicit A2 staging, push, and three-way SHA verification close the round.

## Real environment evidence

Ollama 0.31.2 is healthy, `/api/version` responds, and `ollama ps` is empty. The prior Qwen request produced no semantic output before the client was killed. Later health proves recovery only; it does not prove an authoritative server cancellation receipt. C: has 0.24 GB free, so PostgreSQL and additional model installation remain unsafe.

## Exactly two microscopic simulations

1. Five observations contain one timeout, one client cancellation, one transport failure, one empty response, and one invalid JSON response. A2 emits separate counts and blockers; none can be collapsed into HTTP success or PASS.
2. A JSONL runtime record is written and its manifest verifies. One byte-equivalent semantic mutation changes both file and record hashes; verification returns BLOCK with exact mismatch reasons.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 submits complete hash-bound video evidence. The Judge client is killed before semantic output. A2 emits INCOMPLETE with client-cancellation and sample blockers. A3 displays that decision without substituting its own inference.
2. A1 submits complete image evidence and deterministic icon checks detect a hazard. A cloud or local model returns safe. A2 records disagreement and BLOCK pending review. A3 consumes the committed provenance and cannot turn model confidence into release authority.

## Growth auditor

The staged set must contain only A2-owned schemas, fixtures, judge modules, tests, and this worklog. No credentials, raw prompts, raw provider responses, private refs, or temporary diagnostics are eligible. Failures are now transport- and semantics-specific; confidence intervals expose denominators; persistence detects tampering. Remaining release blockers are lack of valid calibrated samples, CPU-only local model viability, real PostgreSQL proof, safe disk capacity, and a matching final Trusted Spine. CL Gate is mandatory before commit.

## Exactly 20 Round 27 tasks

1. Add a canonical runtime observation schema shared by all provider adapters.
2. Reject unknown `http_state` values instead of classifying them implicitly.
3. Separate connection failure, HTTP error, and response-body read failure.
4. Add server-side cancellation acknowledgement when a provider exposes it.
5. Add recovery-latency policy from client termination to healthy probe.
6. Add JSONL manifest schema and validation tests.
7. Add append-only JSONL chain hashes across batches.
8. Add truncated-last-line recovery and fail-closed tests.
9. Add taxonomy Wilson interval policy thresholds.
10. Add minimum positive and negative denominator gates per taxonomy.
11. Add exact ten-safe/five-attack synthetic promotion boundary fixture.
12. Add a regression proving one invalid safe control blocks that boundary.
13. Add icon provenance schema for mutation fixtures.
14. Add artifact-hash mismatch rejection to mutation evaluation.
15. Add provider/model/runtime binding to the runtime diagnostic schema.
16. Relocate caches or request safe disk cleanup before new installations.
17. Run PostgreSQL transaction/RLS proof only after safe capacity and DSN exist.
18. Refresh main, active A1/A3, and strategy immediately before commit.
19. Generate authoritative Trusted Spine only after exact final SHAs and grades exist.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, pre-commit CL Gate, push, and three-way SHA verification.
