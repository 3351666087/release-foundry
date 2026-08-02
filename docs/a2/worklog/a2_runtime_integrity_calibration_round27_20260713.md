# A2 runtime integrity and calibration boundaries — Round 27 (2026-07-13)

## Synchronization

A fresh `git fetch --all --prune` succeeded before closure:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/agent/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

A1's five-modality receipts remain evidence inputs, not truth. A2 remains the sole release-decision authority. A3 consumes committed decisions without recomputation.

## Round 27 task disposition

1–3. Added a canonical runtime-observation schema, rejected unknown states, and separated connection, HTTP, and response-read failures.
4. The schema can carry provider cancellation acknowledgement, but no current provider supplies authoritative acknowledgement; absence remains non-PASS.
5. Added fail-closed recovery-latency evaluation; recovery does not prove request cancellation.
6–8. Added JSONL manifest schema, cross-batch chain hashes, exact record hashes, and truncated-line rejection.
9–10. Added per-taxonomy recall/specificity Wilson floors and independent positive/negative denominator gates.
11–12. Added the exact ten-safe/five-attack boundary fixture and proved one invalid safe observation blocks it.
13–14. Added mutation provenance schema and explicit artifact-hash mismatch rejection.
15. Added a hash-bound provider/model/request runtime binding to the diagnostic receipt.
16. C: remains at 0.24 GB free; no destructive cleanup was attempted. D: has 45.88 GB free, but relocation requires an explicit, reversible environment plan.
17. PostgreSQL proof remains externally blocked: `POSTGRES_DSN`, `psql`, and Docker are unavailable. Offline persistence verification is the substitute, not a PostgreSQL claim.
18. Required refs were refreshed above.
19. Trusted Spine remains deferred until exact final A1/A2/A3 SHAs, results, and grades exist.
20. Simulations, audit, full validation, CL Gate, explicit staging, push, and SHA verification close this round.

## Real environment evidence

Python and Git are available. Ollama 0.31.2 remains at `D:\ReleaseFoundry\ollama\ollama.exe`; installed multimodal candidates remain non-promotable. C: has 0.24 GB free and D: has 45.88 GB free. `psql` and Docker are absent, so installing PostgreSQL or another model on C: would be unsafe. No credential was deleted, overwritten, logged, or staged.

## Exactly two microscopic simulations

1. A runtime observation uses an unknown HTTP state. A2 rejects it before policy classification; it cannot be coerced into completed or PASS. A terminated request recovering 1,258 seconds later also violates a 60-second recovery policy, while explicitly leaving `request_cancellation_proven=false`.
2. A JSONL batch verifies against file, ordered record, previous-manifest, and chain hashes. Truncating the final line or substituting a mutation artifact hash yields deterministic blockers rather than partial acceptance.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 supplies a hash-bound multimodal bundle with ten safe controls and five attacks. One safe control has invalid semantic output. A2 excludes it, emits INCOMPLETE/BLOCK policy evidence, and A3 displays the committed decision without filling the missing sample.
2. A1 supplies complete hazard-icon evidence whose observed bytes differ from the bound artifact. A2 rejects the mutation provenance before model scoring and emits BLOCK. A3 consumes the rejection and cannot recompute a PASS from provider confidence.

## Growth auditor

The candidate contains only A2 schemas, fixtures, judge/persistence modules, tests, and this worklog. It contains no keys, private refs, temporary images, raw provider outputs, or A1/A3 code. Runtime recovery, provider output, and deterministic sidecars remain observations. The largest unresolved blockers are safe disk capacity, real PostgreSQL transaction/RLS proof, adequately powered and calibrated multimodal candidates, and a final matching Trusted Spine. CL hygiene and commercial gates are mandatory before commit.

## Exactly 20 Round 28 tasks

1. Add provider cancellation-acknowledgement conformance fixtures.
2. Distinguish acknowledgement unavailable from explicit provider rejection.
3. Bind recovery health probes to provider endpoint and runtime version hashes.
4. Add timezone-aware timestamp validation for recovery receipts.
5. Add recovery-latency percentile policy over repeated cancellations.
6. Add JSONL manifest sequence numbers and reject gaps/replays.
7. Add chain-head pinning for independently stored manifests.
8. Add atomic JSONL write/crash-recovery tests.
9. Add taxonomy configuration schema for denominator and Wilson floors.
10. Add mixed positive/negative taxonomy fixtures where both denominators matter.
11. Add confidence-interval tests at exact policy equality boundaries.
12. Expand safe controls beyond flat-color images without using provider output as labels.
13. Add artifact MIME/size binding to mutation provenance.
14. Add deterministic perceptual-transform lineage for icon mutations.
15. Add runtime environment hash inputs to diagnostic binding.
16. Produce a reversible D:-based cache/model relocation proposal without moving credentials.
17. Run PostgreSQL transaction/RLS proof only when a safe DSN and tooling exist.
18. Refresh main, active A1/A3, and strategy immediately before commit.
19. Generate Trusted Spine only after exact final SHAs, runs, and grades exist.
20. Run exactly two micro simulations, two macro simulations, growth audit, full validation, CL Gate, push, and three-way SHA verification.
