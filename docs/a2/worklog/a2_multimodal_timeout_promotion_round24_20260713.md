# A2 multimodal timeout and promotion governance — Round 24 (2026-07-13)

## Synchronization

Fresh `git fetch --all --prune` succeeded:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 5dd6a898a6771eaf67bf39246f256b579b4d2211
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = c3c3c9ea127e12e38a2cc2a7d05543a9fa49e9c0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

A1 PostgreSQL identity authority and A3 readback changes do not alter A2's sole release-decision authority.

## Round 23 task disposition

1–2. Added and validated a strict Round 23 schema: exactly three attempts, two completed, one timeout.
3–6. Runtime summaries now include timed-out observations, cold/warm partitions, timeout receipt hashes, and guarded completion-token throughput.
7. Added seven new safe controls, bringing attempted same-binding safe controls to ten when combined with Round 22; attempts do not count as completed calibration samples.
8. Added five attack controls spanning prompt injection, hazard icon, and visual/text conflict. Provider timeouts prevented the required completed count.
9–10. Added Wilson recall/specificity lower-bound thresholds and an unconditional required-taxonomy-timeout blocker.
11. Performed explicit warm-up. It timed out and did not improve subsequent calls.
12. Tested 224×224 inputs versus prior 640×360 controls; smaller inputs did not improve this run.
13. Checked installed local models. Only `qwen3-vl:4b` and the already-disqualified larger `llava:7b` are installed, so no unverified smaller candidate was fabricated or downloaded mid-calibration.
14. Revalidated deterministic warning-icon sidecar behavior in the focused suite.
15. Added hash-only OCR/vision disagreement persistence through the existing JSONL/record abstraction and offline tests.
16. Added Trusted Spine candidate and validation schemas.
17. Candidate generation is performed after the implementation commit so it can bind the exact A2 SHA.
18. `POSTGRES_DSN`, `psql`, and Docker remain absent. Offline persistence is the substitute, not PostgreSQL proof.
19. Required refs were refreshed above.
20. Growth audit, explicit staging, push, and three-way SHA verification close the round.

## Real Round 24 Qwen run

Binding remained fixed except for an explicit `num_predict=48` ceiling and 224×224 test images. Warm-up timed out at 75.051 s. Of twelve labeled calls, eleven timed out near 75 s. The only HTTP-completed call took 33.156 s, stopped with `done_reason=length`, emitted 48 eval tokens, and returned an empty response. Thus:

```text
completed semantic observations = 0
provider timeouts = 11/12 labeled calls
empty structured outputs = 1/12 labeled calls
promotion state = BLOCK / INCOMPLETE
```

The seven new safe attempts cannot be used to claim ten-sample specificity because none produced valid semantic output. The five attack attempts cannot establish taxonomy recall. The result is stronger negative evidence against this operational binding.

## Exactly two microscopic simulations

1. A timeout observation has no completion-token field. Runtime aggregation includes its latency and timeout receipt but does not invent zero tokens or throughput.
2. A request reaches its 48-token ceiling with `done_reason=length` and an empty response. Transport completion remains a structured-output BLOCK.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 submits complete evidence; Qwen times out on a required taxonomy. A2 records INCOMPLETE and blocks promotion even if other taxonomy point estimates are perfect. A3 displays the committed blocker without recomputation.
2. A new A2 implementation SHA exists but a Trusted Spine candidate carries the previous SHA. Candidate validation rejects it until a post-commit manifest binds the exact implementation SHA and decision/grades hashes.

## Growth auditor

Only A2-owned files changed. No credentials, raw prompts from attack images, temporary images, or private refs are committed. Real-provider evidence is deliberately negative and remains useful: warm-up, lower resolution, and token limiting did not produce a viable interactive or CI judge. PostgreSQL proof and a promotable local multimodal binding remain absent.

## Exactly 20 Round 25 tasks

1. Validate the Round 24 fixture with exact 7-safe/5-attack composition.
2. Add completed-semantic-count distinct from HTTP-completed-count.
3. Add empty-response count to runtime governance.
4. Add queue/backlog telemetry when Ollama exposes it.
5. Restart Ollama cleanly and repeat one safe/one attack diagnostic.
6. Record host CPU, RAM, and accelerator availability as public-safe metadata.
7. Test whether concurrent stale Ollama requests caused serialized timeout amplification.
8. Add a cancellation receipt proving timed-out requests are not left authoritative.
9. Evaluate one genuinely smaller multimodal model if installed/downloaded and digest-bound.
10. Keep LLaVA blocked unless a new prompt binding passes ten safe controls.
11. Add minimum valid-semantic-output rate to promotion policy.
12. Add maximum provider-timeout rate to promotion policy.
13. Add per-taxonomy Wilson bounds only over valid semantic outputs.
14. Reject metrics that encode timeout as an ordinary false negative without a separate timeout blocker.
15. Add offline deterministic hazard-icon fixture provenance.
16. Persist runtime timeout receipts through JSONL and offline SQL substitute.
17. Generate an authoritative Trusted Spine only after exact A1/A2/A3 and grades are final.
18. Recheck PostgreSQL and run transaction proof if tooling becomes available.
19. Refresh main/A1/A3/strategy refs before commit.
20. Run exact simulations, growth auditor, full validation, push, and three-way SHA verification.
