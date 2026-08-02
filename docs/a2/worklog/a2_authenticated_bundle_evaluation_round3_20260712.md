# A2 Authenticated Bundle Evaluation — 2026-07-12

## Synchronization boundary

- This task is the sole writer for `dev/g3-a2-calibration`.
- `git fetch origin --prune` failed because GitHub port 443 was unreachable. Cached refs reviewed: `origin/main=ccf6ce5`, `origin/agent/a1-local-sdk-runner=b6033ab`, `origin/agent/a3-commercial-growth-round4=ccf6ce5`, `origin/dev/g3-a2-calibration=3d071a3`.
- Cached `main/docs/strategy` continues to require A2 as the independent evaluation and release-decision authority. A1's cached active branch adds identity and authenticated-evidence contracts; A3 has no cached delta from main. No live freshness claim is made.

## Delivered vertical slice

`evaluate_a1_bundle` now exposes the required public outcome vocabulary: `PASS`, `BLOCK`, or `INCOMPLETE`.

1. Invalid authenticity, digest, scope, or bundle shape returns structured `INCOMPLETE` before a Provider call.
2. Complete evidence reaches the configured semantic Judge through Provider Gateway.
3. Provider timeout/unavailability/error or invalid Judge output returns `BLOCK`, never `PASS`.
4. Qualified image/OCR derived evidence can reach the Judge with citation grounding; unqualified derived evidence blocks before invocation.
5. Evidence snapshot, structured Judge result, findings, Provider provenance, policy version, decision hash, input fingerprint, persistence state, and replay state are public-safe outputs.
6. Same request version and idempotency key replays the committed decision without a second Provider invocation.
7. `scripts/a2_evaluate_bundle.py` supports Ollama and OpenAI-compatible endpoints. Credentials and A1 verification keys are environment-only and never accepted as command values or output.

Ollama is not installed on this host (`ollama` command not found), so this round does not claim a real local multimodal model invocation. The real adapter path exists; deterministic fake adapters validate the offline contract and fail-closed behavior.

## Microscopic simulations

### Round 1 — authenticated text decision

A valid A1 bundle is authenticated, frozen into an evidence snapshot, judged with strict JSON, persisted, and surfaced as `PASS`. Repeating the same version/key retrieves the committed record and performs no second Provider call.

### Round 2 — multimodal and failure boundaries

A production-qualified image/OCR record reaches the Judge and its disclosed citation may support `PASS`. The same record without production qualification blocks before invocation. Separately, a complete bundle whose Provider errors becomes committed `BLOCK`, while a tampered bundle becomes `INCOMPLETE` without invocation.

## Macroscopic A1/A2/A3 simulations

### Round 1 — normal release

A1 produces an authenticated, scoped bundle. A2 alone verifies, judges, applies policy, and commits the release decision. A3 receives public-safe provenance and the committed result, with `may_recompute_grade=false`.

### Round 2 — compromised or unavailable dependency

A1 bundle tamper is rejected before semantic processing. A Provider/model outage after valid ingestion cannot manufacture a pass. A3 receives no release-ready state unless A2 has committed `PASS`; neither A1 execution success nor model confidence overrides policy.

## Growth auditor

- Local commit `0a74b3a` from the previous round exists but remains ahead of cached remote because push and `ls-remote` could not reach GitHub.
- This round's commit/push status must be recorded only from actual command results.
- Scope contains only A2-owned service, schema, CLI, test, and worklog files.

## Next growth queue (exactly 20)

1. Add a JSON Schema for the bundle-evaluation response.
2. Add CLI subprocess tests for PASS, BLOCK, and INCOMPLETE exit codes.
3. Add an environment-safe OpenAI-compatible local stub integration test.
4. Install Ollama when network/package access is available and record exact version.
5. Pull one lightweight vision model and record immutable model digest.
6. Pull one higher-quality vision model only after hardware capacity preflight.
7. Run a real image Judge smoke through `a2_evaluate_bundle.py`.
8. Add Ollama model capability discovery before invocation.
9. Reject requested modalities absent from discovered model capabilities.
10. Add Provider/model version digest to request fingerprint.
11. Add calibration status to the bundle-evaluation decision contract.
12. Add golden-regression status to the decision contract.
13. Add disagreement status between deterministic and semantic Judges.
14. Require human review for configured high-risk disagreement classes.
15. Add policy-controlled score thresholds instead of model pass alone.
16. Add audio-derived evidence bundle evaluation.
17. Add PDF/file-derived evidence bundle evaluation.
18. Add video-keyframe-derived evidence bundle evaluation.
19. Add public-safe A3 report fixture for all three external outcomes.
20. Add PostgreSQL parity for the bundle-evaluation persistence path.
