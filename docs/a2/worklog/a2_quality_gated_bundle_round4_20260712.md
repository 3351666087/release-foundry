# A2 Quality-gated Bundle Evaluation - 2026-07-12

## Synchronization and ownership

- `git fetch origin --prune` succeeded. Reviewed exact refs: `origin/main=ccf6ce57890aaceabcb627c14d2e078674bd50ad`, `origin/codex/a1-local-sdk-runner=d1578bfa13a26456b3e110fdb372f713cad99beb`, `origin/codex/a3-commercial-growth-round4=ccf6ce57890aaceabcb627c14d2e078674bd50ad`, `origin/codex/a3-main-contract-alignment-v2=0b0e0cf1cdeeaf87c95d497dbe89b4dca948ca8e`, and `origin/dev/g3-a2-calibration=0bbec12da49f2a1ad29175527bfaba88c5c76d8b`.
- Reviewed `origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md`. A2 remains the sole evaluation and release-decision authority.
- A1's new delta adds password/MFA lifecycle and trusted identity HTTP boundaries; it does not change the authenticated evidence bundle contract used here.
- A3's active delta remains provider-neutral and consumes trusted calibration/decision state without recomputing it.
- This round changes only A2-owned service, CLI, schema, test, and worklog files.

## Delivered slice

1. Added a JSON Schema for public `PASS`, `BLOCK`, and `INCOMPLETE` bundle evaluation responses.
2. Added Ollama model discovery before CLI invocation. An undiscovered model, unsupported required modality, or unavailable discovery endpoint fails closed before Judge execution.
3. Added versioned public-safe evaluation quality state to request identity, recovery envelope, persistence validation, release gate, policy hash, and A3 consumption.
4. Calibration and golden regression must be `passed`; deterministic/semantic disagreement must be `agree` or `reviewed`; content-addressed quality evidence refs are required.
5. Missing or failed quality state cannot be overridden by a Provider/model self-reported pass.
6. Recovery persistence uses exact-key and value validation for the quality state, preserving restart and replay behavior.

Quality evidence is currently a strict content-addressed contract supplied to A2, not yet an authenticated issuer-signed proof. This round does not claim that caller-provided quality status is independently authentic.

## External model evidence

- `DASHSCOPE_API_KEY` and `QWEN_API_KEY` were absent from the current process. No live Qwen call was made.
- Hardware preflight: approximately 16 GB RAM, Intel UHD graphics, no NVIDIA GPU. This supports a small quantized local model tier, not a large local high-quality tier.
- `winget` downloaded and verified the official Ollama `0.31.2` installer hash. Installation failed with exit code `5`; the installer log states `磁盘空间不足` while copying CUDA runtime files and confirms rollback. No installed Ollama runtime or live local model result is claimed.
- Deterministic offline evaluation, Provider contract tests, replay, and fail-closed release behavior remain available without an external model.

## Microscopic simulations

### Simulation 1 - model pass without quality proof

An authenticated complete A1 bundle reaches a structured semantic Judge. The model returns a high score and `passed=true`, but calibration/golden/disagreement proof is absent. A2 returns `BLOCK`, records quality blockers, and does not expose release-ready state.

### Simulation 2 - capability mismatch and governed pass

Ollama discovery reports a text-and-image model. An audio-required bundle is rejected before invocation. Separately, a text/image bundle with passed calibration, passed golden regression, agreement evidence, valid citations, and committed persistence may produce `PASS`.

## A1/A2/A3 macroscopic simulations

### Simulation 1 - normal governed release

A1 signs a complete tenant-scoped bundle. A2 verifies it, resolves an explicitly capable model, invokes the Judge, validates structured output and citations, applies quality gates, commits the Decision Ledger, and emits public-safe provenance. A3 renders the committed A2 result with `may_recompute_grade=false`.

### Simulation 2 - dependency and quality degradation

A1 authenticity failure becomes `INCOMPLETE` before Provider invocation. Provider outage after valid evidence becomes `BLOCK`. A stale or missing calibration/golden/disagreement proof also becomes `BLOCK` even when the model output says pass. A3 cannot manufacture release readiness from any of these states.

## Growth auditor

- Pre-commit verification in this round: 297 A2 tests passed; all 56 generated fixtures matched; changed Python modules compiled; `git diff --check` passed.
- Commit, push, staged secret scan, and remote SHA verification are pending and must be recorded only from actual command output.

## Next growth queue (exactly 20)

1. Define an issuer-signed evaluation quality proof schema.
2. Verify quality proof signature, scope, expiry, and revocation before accepting `passed`.
3. Bind quality proof to Provider ID, model ID, immutable model version, prompt version, and policy version.
4. Add model artifact/version digest to the bundle request fingerprint.
5. Add a local deterministic Judge adapter to the bundle CLI.
6. Add CLI subprocess tests for successful `PASS`, `BLOCK`, and `INCOMPLETE` exit codes through a local HTTP stub.
7. Add a DashScope/Qwen preset that uses the generic OpenAI-compatible adapter without embedding credentials.
8. Run a live Qwen text Judge smoke when `DASHSCOPE_API_KEY` is inherited.
9. Run a live Qwen vision Judge smoke against a public-safe generated image.
10. Compare one lightweight and one high-quality Qwen model on the same immutable bundle.
11. Persist live calibration observations without raw Provider payloads.
12. Add deterministic-versus-Qwen disagreement analysis and human-review routing.
13. Add disk-capacity preflight for local model runtime and model pull operations.
14. Retry Ollama installation only after the preflight reports sufficient free space.
15. Pull and record the digest of one CPU-feasible vision model.
16. Run a real Ollama image Judge smoke and compare provenance with Qwen.
17. Add audio-derived evidence bundle evaluation and qualification tests.
18. Add PDF/file-derived evidence bundle evaluation and parser qualification tests.
19. Add video-keyframe-derived evidence bundle evaluation and qualification tests.
20. Add PostgreSQL parity tests for quality-gated decision persistence and replay.
