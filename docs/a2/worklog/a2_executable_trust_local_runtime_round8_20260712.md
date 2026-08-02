# A2 executable trust policy and local runtime preflight — round 8

## Synchronized evidence

The 2026-07-12 fetch attempt failed with `Failed to connect to github.com:443 after 21059 ms`. No newer state is claimed. Last verified local refs:

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a1-local-sdk-runner`: `d1578bfa13a26456b3e110fdb372f713cad99beb`
- `origin/agent/a3-commercial-growth-round4`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a3-main-contract-alignment-v2`: `d4edf48cbc7faedcadd5c6f4921d2e4fd2c04d3d`

The cached strategy and cross-lane deltas were re-reviewed. A1 still owns authenticated evidence production, A2 remains sole release-decision authority, and A3 consumes trusted decisions without recomputation.

## Delivered slice

- Added `--trust-policy` JSON loading to the executable A1-bundle evaluator.
- Passed the normalized versioned trust policy through the public evaluation facade into orchestration.
- Rejected issuer/tenant mappings whose issuer is absent from the allowlist.
- Rejected noncanonical revoked proof hashes during policy normalization.
- Added trust-policy schema fixture validation and Qwen default endpoint/credential assertions.
- Added recovery tamper rejection for invalid trust-policy hashes.
- Added explicit migrated-envelope persistence/load success coverage.
- Preserved legacy `disagree` as review-required during migration and continued to reject legacy `reviewed` without a receipt.
- Added exact reviewer maximum-age boundary and negative-time tests.
- Added public reviewer pseudonymization guidance.
- Added local runtime executable/model path preflight and a D-drive-only checksum-verified Ollama installation script.

## Previous 20-task disposition

1. Remote-completion revoked proof: initial and reconciliation share verifier policy; a dedicated scenario remains open.
2. Trust-policy CLI loading: completed.
3. Trust-policy schema validation: completed.
4. Unknown mapped issuer rejection: completed.
5. Canonical revoked proof hashes: completed.
6. Trust-policy recovery tamper test: completed.
7. Migrated envelope persistence/load: completed.
8. Migrated legacy disagree fail-closed: completed as review-required with blocker preservation.
9. Exact age boundary: completed.
10. Negative review time: completed and BLOCKS as stale.
11. Reviewer pseudonymization guidance: completed.
12. Qwen URL assertion: completed without network.
13. Qwen text smoke: blocked; inherited `DASHSCOPE_API_KEY` is missing.
14. Qwen image smoke: blocked by the same missing inherited key.
15. Same-drive preflight: completed for executable and model paths.
16. D-drive installation script: completed with SHA-256 verification and 20 GiB capacity gate.
17. Install verified runtime: not executed because no authoritative archive URL/checksum was supplied or discovered during the network outage; unsafe unverified installation was refused.
18. Pull vision model: blocked because Ollama is absent; D has 58.22 GiB free.
19. Local/Qwen disagreement comparison: blocked because neither live route exists; signed offline disagreement policy remains tested.
20. PostgreSQL parity: blocked locally; `POSTGRES_DSN`, `psql`, Docker and PostgreSQL service are absent. SQLite remains the backend-neutral contract substitute.

## Environment evidence

- `DASHSCOPE_API_KEY=missing`; `QWEN_API_KEY=missing`; no Qwen call claimed.
- `OLLAMA=missing`; no local model call claimed.
- `POSTGRES_DSN=missing`; `PSQL=missing`; `DOCKER=missing`.
- `C:` free 2.35 GiB; `D:` free 58.22 GiB.

## Verification

- Focused bundle/orchestrator tests: 71 passed.
- Full A2 suite: 319 passed.
- Generated fixtures: 56/56 matched.
- Changed Python files compiled successfully.
- `git diff --check` passed apart from informational CRLF warnings.

## Microscopic simulations

**Micro A — CLI governed policy:** the CLI reads a strict public-safe trust-policy document. Unknown issuers, malformed revoked hashes or policy-bound proof failures cannot become PASS.

**Micro B — legacy recovery:** an old `agree` envelope may be explicitly migrated and loaded; `disagree` retains its blocker; `reviewed` without a receipt is rejected. Trust-policy hash tampering is rejected even when the envelope hash is recomputed.

## A1/A2/A3 macroscopic simulations

**Macro A — deployable private-cloud path:** A1 emits authenticated evidence; the A2 CLI loads tenant trust policy, executes a provider-neutral Judge, binds policy provenance, commits the decision and gives A3 a non-recomputable record.

**Macro B — external routes absent:** cloud credentials, local models and PostgreSQL are unavailable. Deterministic verification, strict fake/local HTTP contracts, SQLite persistence and migration tests still close the release loop; external absence never produces Release Ready.

## Growth auditor

Only A2-owned code, scripts, tests, schemas, documentation and this worklog may be staged. Staged content must exclude credentials/private refs. Completion requires local/remote SHA equality and a clean worktree.

Exactly 20 narrow next tasks:

1. Add dedicated remote-completion reconciliation coverage for proof revocation.
2. Add a CLI test that loads a valid trust-policy file end to end.
3. Add a CLI test that rejects an invalid trust-policy file before Provider invocation.
4. Bind the trust-policy hash into facade reproducibility output.
5. Add trust-policy hash to the public bundle-evaluation schema.
6. Add allowlist-empty semantics documentation and tests.
7. Validate revoked key identifiers against a bounded public-safe format.
8. Add duplicate tenant normalization coverage.
9. Add reviewer receipt future-time boundary coverage at exactly one millisecond.
10. Add tenant-salt rotation provenance guidance.
11. Add PowerShell installer static safety tests.
12. Add an installer dry-run mode that performs no download or writes.
13. Discover an authoritative Ollama Windows archive URL and checksum when network is available.
14. Run the verified D-drive installation after authoritative discovery.
15. Pull a lightweight vision model only while D remains above 20 GiB free.
16. Run a local text Judge smoke through the unified gateway.
17. Run a local image Judge smoke against the identical snapshot.
18. Run Qwen text/image smoke when inherited `DASHSCOPE_API_KEY` is present.
19. Persist a signed local-versus-Qwen disagreement receipt.
20. Run PostgreSQL recovery/fencing parity when a CI service or `POSTGRES_DSN` is available.
