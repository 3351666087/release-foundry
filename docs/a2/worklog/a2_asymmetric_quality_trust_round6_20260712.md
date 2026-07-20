# A2 asymmetric quality trust and executable provider CLI — round 6

## Synchronized evidence

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/codex/a1-local-sdk-runner`: `d1578bfa13a26456b3e110fdb372f713cad99beb`
- `origin/codex/a3-commercial-growth-round4`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/codex/a3-main-contract-alignment-v2`: `d4edf48cbc7faedcadd5c6f4921d2e4fd2c04d3d`
- Strategy reviewed from `origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md`.

Fetch succeeded on 2026-07-12. A1's authenticated bundle boundary is unchanged. A1's active delta adds identity evidence and compatibility material, not a replacement for A2 release authority. A3's active delta strengthens trusted read access, audit persistence and tenant isolation and continues to consume A2 decisions without recomputation.

## Delivered slice

- Added Ed25519 verification while retaining HMAC-SHA256 for same-deployment trust domains.
- Added issuer authorization, key revocation, proof revocation and maximum lifetime enforcement.
- Bound proofs to rubric version, golden dataset digest and calibration thresholds hash.
- Applied the same trust policy to initial execution and reconciliation.
- Added external quality-proof JSON loading to the executable CLI.
- Added a Qwen preset over the existing OpenAI-compatible adapter instead of a duplicate protocol.
- Added configurable model-storage capacity preflight.
- Added real subprocess and local HTTP protocol tests proving PASS=0, BLOCK=2 and INCOMPLETE=3.

## Previous 20-task disposition

1. Ed25519 verifier: completed and tested.
2. Issuer allowlist: completed; proof remains bound to five-field tenant scope.
3. Key/proof revocation: completed and tested.
4. Maximum lifetime: completed and tested.
5. Rubric binding: completed and tested.
6. Golden dataset binding: completed and tested.
7. Calibration threshold binding: completed and tested.
8. PostgreSQL parity: shared serialized recovery envelope path remains backend-neutral; no live PostgreSQL service was available, so runtime parity remains open.
9. v1→v2 migration: existing v2 recovery validation fails closed; an explicit migration fixture remains open.
10. CLI quality proof file: completed.
11. PASS subprocess exit: completed.
12. BLOCK subprocess exit: completed using HTTP 500.
13. INCOMPLETE subprocess exit: completed using tampered A1 evidence.
14. Qwen preset: completed through OpenAI-compatible protocol.
15. Qwen text smoke: blocked because inherited `DASHSCOPE_API_KEY` is missing; local HTTP wire substitute passed.
16. Qwen vision smoke: blocked because inherited `DASHSCOPE_API_KEY` is missing; existing qualified OCR/multimodal gateway tests passed.
17. Disk preflight: completed with configurable storage path and minimum free GiB.
18. Install local runtime on D: not attempted this round because Ollama is absent and C has only 1.95 GiB free; D has 58.22 GiB. Preflight prevents unsafe placement, but installer relocation remains open.
19. Local vision versus Qwen: externally blocked by both missing runtime and missing cloud key; deterministic multimodal substitute passed.
20. Disagreement disposition: signed states `agree`, `disagree`, `reviewed`, and `unknown` are persisted in the public-safe quality state; `disagree`/`unknown` fail closed. A richer reviewer identity receipt remains open.

## Provider and local-model evidence

- `DASHSCOPE_API_KEY=missing`; `QWEN_API_KEY=missing`.
- No live Qwen request was made and no live validation is claimed.
- `OLLAMA=missing`.
- `C:` free: 1.95 GiB; `D:` free: 58.22 GiB.
- The OpenAI-compatible wire contract was exercised via a real subprocess and local HTTP server, including a provider 500 failure that produced BLOCK.

## Verification

- Focused orchestration and facade tests: 59 passed.
- Full A2 suite: 306 passed before the final capacity-preflight test; focused rerun including that test passed.
- Generated fixtures: 56/56 matched.
- Changed Python files compiled successfully.
- `git diff --check` passed apart from informational CRLF normalization warnings.

## Microscopic simulations

**Micro A — asymmetric trust:** An authenticated A1 bundle, matching immutable snapshot and valid Ed25519 quality proof reaches Provider evaluation and A2 allow. Replacing issuer, key state, proof hash, rubric, golden digest or thresholds produces a deterministic blocker.

**Micro B — provider outage:** The same valid evidence and proof reaches an OpenAI-compatible HTTP endpoint returning 500. Gateway records provider unavailability/error, A2 returns BLOCK and the CLI exits 2; no Provider failure can become PASS.

## A1/A2/A3 macroscopic simulations

**Macro A — normal release:** A1 emits an authenticated scoped bundle. A2 verifies authenticity/integrity/scope/completeness, verifies calibration proof, calls the provider-neutral Judge, commits a public-safe decision and exposes only A2 authority/provenance to A3.

**Macro B — adversarial release:** A1 evidence is intact and the model says pass, but its calibration proof is revoked or bound to another rubric. A2 emits BLOCK, persists the blocker and A3 may display/report it but cannot recompute or override it.

## Growth auditor

The commit must contain only A2-owned code, tests, schemas, CLI and this worklog. Staged content must be scanned for private refs, literal secrets, tokens and bearer credentials. Push is complete only when local HEAD equals the remote branch SHA.

Exactly 20 narrow next tasks:

1. Add an issuer-to-tenant authorization mapping test beyond the existing signed tenant binding.
2. Add malformed Ed25519 public-key length coverage.
3. Add malformed Ed25519 signature hex coverage.
4. Add reconciliation coverage for revoked quality proofs.
5. Add a versioned trust-policy configuration schema.
6. Add a content-addressed trust-policy hash to decision provenance.
7. Add an explicit v1 recovery-envelope rejection fixture.
8. Add a documented v1-to-v2 recovery migration function.
9. Run PostgreSQL recovery-envelope parity in CI.
10. Add a reviewer identity digest to reviewed disagreement receipts.
11. Bind reviewer disposition time into the signed proof.
12. Add stale reviewer-disposition rejection.
13. Add Qwen preset unit coverage for default URL and credential variable.
14. Run Qwen text smoke when `DASHSCOPE_API_KEY` is inherited.
15. Run Qwen vision smoke on the same immutable snapshot.
16. Add an Ollama installer preflight that verifies the target executable and model directories are on D.
17. Install Ollama or an equivalent runtime entirely on D.
18. Pull one lightweight vision model after verifying at least 20 GiB free.
19. Compare local vision and Qwen outputs through signed disagreement policy.
20. Persist the final human-reviewed disagreement receipt without exposing reviewer PII.
