# A2 tenant trust policy and reviewer receipt — round 7

## Synchronized evidence

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a1-local-sdk-runner`: `d1578bfa13a26456b3e110fdb372f713cad99beb`
- `origin/agent/a3-commercial-growth-round4`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a3-main-contract-alignment-v2`: `d4edf48cbc7faedcadd5c6f4921d2e4fd2c04d3d`
- Strategy reviewed from `origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md`.

Fetch succeeded on 2026-07-12. A1's active delta adds identity evidence, compatibility contracts and deployment material but does not replace the authenticated evidence boundary. A3 strengthens authenticated/trusted reads, auditability and tenant isolation while continuing to consume A2 authority. The strategy still requires provider-neutral, signed, versioned, fail-closed release decisions.

## Delivered slice

- Added issuer-to-tenant authorization for quality-proof issuers.
- Added signed reviewer identity digest and review time, with stale, missing and unexpected receipt rejection.
- Persisted only reviewer digest/time; no reviewer PII or free text is retained.
- Added strict malformed Ed25519 key/signature fail-closed coverage.
- Added a versioned public-safe trust-policy schema, normalization and canonical content hash.
- Bound the trust-policy hash into request identity, recovery envelope, decision policy hash and result metadata.
- Added explicit quality-state v1→v2 recovery migration; direct legacy recovery remains rejected and legacy `reviewed` cannot be invented without a receipt.
- Added Qwen preset coverage proving the default credential boundary fails closed without exposing the bundle key.

## Previous 20-task disposition

1. Issuer-to-tenant mapping: completed and tested.
2. Malformed Ed25519 public-key length: completed and tested.
3. Malformed Ed25519 signature hex: completed and tested.
4. Reconciliation revoked proof: verifier arguments are shared by initial/reconciliation paths; dedicated remote-completion test remains open.
5. Versioned trust-policy schema: completed.
6. Content-addressed trust-policy provenance: completed and tested.
7. Explicit v1 rejection: completed by strict v2 recovery validation and legacy fixture.
8. v1→v2 migration: completed with deterministic safe defaults.
9. PostgreSQL CI parity: blocked locally; no `psql`, Docker or PostgreSQL service exists. SQLite exercises the backend-neutral serialized envelope and fencing contract.
10. Reviewer identity digest: completed.
11. Reviewer disposition time: completed and signed.
12. Stale disposition rejection: completed and tested.
13. Qwen preset coverage: completed for default environment credential behavior; production URL remains the existing preset.
14. Qwen text smoke: blocked because inherited `DASHSCOPE_API_KEY` is missing; no live call claimed.
15. Qwen vision smoke: blocked by the same missing inherited key; deterministic multimodal/OCR tests remain the substitute.
16. D-drive installer preflight: model-storage capacity preflight exists; executable-path placement verification remains open.
17. Install local runtime on D: not performed because Ollama is absent and installation provenance/relocation has not yet been automated.
18. Pull lightweight vision model: not performed; D has sufficient free space but no runtime is installed.
19. Local vision/Qwen comparison: externally blocked by both missing routes; signed disagreement receipt policy is now ready.
20. Human-reviewed receipt persistence: completed without raw PII.

## Environment and external-provider evidence

- `DASHSCOPE_API_KEY=missing`; `QWEN_API_KEY=missing`; no live Qwen request was made.
- `OLLAMA_COMMAND=missing`.
- `PSQL_COMMAND=missing`; `DOCKER_COMMAND=missing`; no PostgreSQL Windows service was discovered.
- `C:` free: 1.93 GiB; `D:` free: 58.22 GiB. No large model was placed on C.

## Verification

- Focused bundle/orchestrator tests: 65 passed.
- Full A2 suite: 313 passed.
- Generated fixtures: 56/56 matched.
- Changed Python files compiled successfully.
- `git diff --check` passed apart from informational CRLF normalization warnings.

## Microscopic simulations

**Micro A — tenant-confused issuer:** a proof is correctly signed by an allowed issuer but the trust policy authorizes that issuer only for another tenant. A2 returns BLOCK with `quality_proof_issuer_tenant_unauthorized`; the model cannot override it.

**Micro B — reviewed disagreement:** a signed `reviewed` state with a fresh reviewer digest/time may pass. Missing, stale or unexpected receipts deterministically BLOCK. Recovery retains only digest/time and remains public-safe.

## A1/A2/A3 macroscopic simulations

**Macro A — normal governed release:** A1 emits authenticated scoped evidence. A2 binds snapshot, Judge, calibration proof and versioned trust-policy hash into one replay identity, commits the unique decision, and A3 displays its provenance without recomputation.

**Macro B — policy/recovery attack:** a Provider says pass, but the issuer is unauthorized for the tenant or a legacy reviewed state lacks a receipt. A2 fails closed before release. A3 receives BLOCK and cannot synthesize Release Ready.

## Growth auditor

Only A2-owned schemas, Judge services, tests and this worklog may be staged. Staged content must exclude private refs and credentials. Completion requires local/remote SHA equality and a clean worktree.

Exactly 20 narrow next tasks:

1. Add remote-completion reconciliation coverage for a newly revoked proof.
2. Add trust-policy JSON loading to the executable bundle CLI.
3. Add trust-policy schema validation to contract tests.
4. Reject issuer-tenant entries for issuers absent from the allowlist.
5. Validate revoked proof hashes as canonical `sha256:` references during normalization.
6. Add a trust-policy hash mismatch recovery tamper test.
7. Add migrated-envelope persistence and recovery success coverage.
8. Add migrated legacy `disagree` fail-closed coverage.
9. Add reviewed receipt maximum-age boundary tests at exactly the limit.
10. Add reviewed receipt negative timestamp rejection.
11. Add an explicit reviewer pseudonymization guidance document.
12. Add Qwen preset URL assertion without making a network call.
13. Run Qwen text smoke when `DASHSCOPE_API_KEY` is inherited.
14. Run Qwen image smoke against the same immutable evidence snapshot.
15. Add executable/model-directory same-drive preflight for local runtimes.
16. Add a D-drive-only Ollama installation script with checksum verification.
17. Install the verified runtime entirely on D when the script passes preflight.
18. Pull one lightweight vision model only after confirming at least 20 GiB free.
19. Run signed local-versus-Qwen disagreement comparison when both routes exist.
20. Add PostgreSQL recovery-envelope parity to an available CI service.
