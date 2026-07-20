# A2 local multimodal runtime and fail-closed boundaries - Round 10 - 2026-07-12

## Scope and authority

This round changes only A2-owned files. A1 remains the authenticated evidence producer, A2 remains the sole evaluation and release-decision authority, and A3 consumes only A2 decision/provenance/review output without recomputing a grade.

## Cross-lane synchronization and review

Fetch completed successfully on 2026-07-12:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 4a8d0e99cb18676a4ab11205ef7f7ad09d8c9973
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = 45bec48e65f3ae11f0252174990365eb20e46ef6
fetch exit = 0
```

A1 advanced from `d1578bf` to `4a8d0e9` with a provider-neutral SDK runtime, calibrated text calls, multimodal input types and hosted-secret response fixes. A1 explicitly does not alter A2 Judge or A3 dashboard semantics. Its protocol adapters are useful upstream transport capability, while A2 still independently verifies authenticated evidence and owns evaluation policy.

`origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md` was reviewed again. It still requires provider-neutral A2, Ollama/OpenAI-compatible support, fail-closed provider failures, and prohibits A3 grade recomputation. Both active A3 refs were unchanged; no authority conflict was found.

## Delivered

- Rejected Boolean reviewer timestamps rather than accepting Python `bool` as an integer.
- Added revoked-key identifier boundary coverage at 1, 128, 129 characters and leading punctuation.
- Required structured INCOMPLETE facade output to validate against the public schema and carry the canonical trust-policy hash.
- Sanitized CLI JSON load failures for bundle, quality proof and trust policy; malformed content is never echoed.
- Proved a missing trust-policy file fails before Provider invocation.
- Added CLI replay proof: same database, input and normalized policy yield the same record ID and policy hash, set `idempotent_replay=true`, and make only one Provider call.
- Added remote-completion reconciliation coverage for a newly revoked proof hash; it commits neither decision nor outbox.
- Added provider-completed recovery coverage showing duplicate policy lists normalize to stable provenance and recover without a second Provider call.
- Hardened the Ollama installer so install root, model root and download staging must remain on D; dry run has no target-directory side effects and checksum failure removes the staged archive.
- Added a configurable Ollama smoke timeout while retaining bounded fail-closed status reporting.

## Prior 20-task disposition

1. **Done:** structured INCOMPLETE schema validation and trust-policy hash assertion.
2. **Done:** Boolean `reviewed_at_unix_ms` rejected.
3. **Done:** revoked key ID 1/128 boundaries accepted.
4. **Done:** 129 characters and leading punctuation rejected.
5. **Done:** CLI replay compares stable policy hash, record ID and provider call count.
6. **Done:** malformed trust-policy JSON is sanitized.
7. **Done:** missing trust-policy file fails before Provider invocation.
8. **Done:** reconciled completion honors revoked proof hashes.
9. **Done:** normalized duplicate-policy recovery is covered.
10. **Done:** installer dry run creates no target directories.
11. **Done:** non-D install root rejected.
12. **Done:** non-D model root rejected.
13. **Done:** local checksum mismatch removes the staged archive.
14. **Done:** authoritative Ollama release metadata recorded below.
15. **Done:** Ollama installed on D with checksum verification and safety threshold.
16. **Done:** `qwen3-vl:4b` pulled to D; D remains above 20 GiB.
17. **Partially done with exact evidence:** unified gateway text completed; image calls were real but timed out fail-closed at 30, 180 and 420 seconds on CPU-only execution. No false success is claimed.
18. **Blocked externally:** the user-level DashScope credential is present but the real endpoint returned HTTP 401 after restart. Offline substitute: OpenAI-compatible protocol and local Ollama tests pass.
19. **Blocked externally:** no valid Qwen cloud result exists, so no truthful local-versus-Qwen signed disagreement receipt was fabricated. Existing signed disagreement/reviewer gates remain covered.
20. **Blocked externally:** no `POSTGRES_DSN`, `psql`, or Docker. SQLite recovery/fencing/atomicity is the executable substitute.

## External runtime evidence

Official Ollama GitHub release metadata used:

```text
tag = v0.31.2
asset = ollama-windows-amd64.zip
size = 1502730186
sha256 = 6988b58d2223ae3f9d5766b46b0be614dec36524b80317159718b5adf3006f3b
```

The first download attempt staged in C `%TEMP%`; it was stopped near 817 MB because C had only about 2.2 GiB free. The partial archive was deleted. The installer was then changed to enforce D-only staging, and the checksum-verified installation succeeded:

```text
runtime = D:\Ashr\ollama\ollama.exe
client/server version = 0.31.2
model root = D:\Ashr\ollama-models
model = qwen3-vl:4b
model digest = 1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
model bytes = 3295636135
D free after model/smokes = 53.23 GiB
C free = 2.08 GiB
```

Unified Provider Gateway text smoke returned `status=completed`, a public-safe response hash, and no raw payload or secret. The generated image had SHA-256 `4f5cf36d805b1017209e9c49a344e3fb68ae79b678f42ef40340b1ba197ee69a`. Real image calls returned `status=timeout` at 30, 180 and 420 seconds; the machine reports Intel UHD graphics and the Ollama process reports zero VRAM use. This is retained as truthful capability evidence: the protocol path is reachable, but production image capability is not calibrated on this host.

After Codex restart, a secret-safe probe observed:

```text
DASHSCOPE_API_KEY user = present
DASHSCOPE_API_KEY process = missing
DashScope compatible endpoint = HTTP 401
response/error body = redacted
```

The key was never printed, read into project files, or persisted. No live Qwen success is claimed.

PostgreSQL evidence:

```text
POSTGRES_DSN process/user = missing
psql = missing
docker = missing
```

## Microscopic simulations

### Micro 1 - replay identity and policy provenance

A valid signed A1 bundle, quality proof and normalized trust policy were submitted twice through the real CLI against the same SQLite database. The first call invoked the stub HTTP Provider and committed. The second returned the same record ID and policy hash, marked idempotent replay, and produced total HTTP call count 1. Same-version input is traceable and replay does not spend or mutate provider state.

### Micro 2 - uncertain remote completion after proof revocation

A Provider call was interrupted after authorization. Reconciliation later reported remote completion, but the exact signed quality-proof hash had become revoked. A2 raised `IdempotencyConflictError` and committed zero release-decision and outbox rows. Remote completion cannot bypass current governed request identity.

## A1/A2/A3 macroscopic simulations

### Macro 1 - authenticated evidence to committed PASS

A1 emits authenticated, tenant/project-scoped evidence. A2 verifies authenticity, scope, integrity and completeness, calls a provider-neutral Judge, validates structured output and quality proof, applies policy, persists one Decision Ledger record and exposes replay provenance. A3 consumes the committed A2 decision and record hash only. A3 never recalculates score or release state.

### Macro 2 - local/cloud capability failure

A1 evidence is valid, but a local image Judge times out or the cloud credential returns 401. A2 records a non-completed Provider status and cannot produce PASS. Deterministic offline validation and persisted fail-closed behavior remain available. A3 can display the A2 blocking/review provenance but cannot convert it to release-ready.

## Validation

```text
Focused bundle/orchestrator tests: 87 passed
Full A2 suite: 335 passed
Generated fixtures: 56/56 matched
Python compilation: passed
git diff --check: passed
Unified local text smoke: completed
Unified local image smoke: timeout, correctly non-PASS
```

Only expected `jsonschema.RefResolver` deprecation warnings and Git line-ending notices appeared.

## Growth auditor

The auditor confirms A2-owned implementation, boundary tests, local runtime evidence, two microscopic simulations and two macroscopic simulations exist. The commit/push/remote-SHA check is performed after this worklog is staged. External blockers have exact evidence and executable offline substitutes; none are represented as success.

## Exactly 20 narrow tasks for Round 11

1. Add validation that `--timeout-seconds` is finite and strictly positive in the Ollama smoke CLI.
2. Add a subprocess test proving Ollama smoke timeout returns exit code 2 and public-safe JSON.
3. Add a subprocess test proving Ollama smoke completion returns exit code 0 and no raw output field.
4. Record Ollama model digest in local smoke evidence without including model files or prompts.
5. Add a capability-state record that distinguishes protocol-reachable from image-calibrated.
6. Add a fail-closed test preventing a timed-out image capability from becoming `callable`.
7. Add bounded Ollama generation options for smoke requests to reduce CPU latency.
8. Re-run the real local image smoke with bounded output and record the result.
9. Add CLI replay coverage for an equivalent policy with reordered issuer and tenant lists.
10. Add CLI replay conflict coverage for a genuinely changed revocation set.
11. Add reconciliation coverage for a proof hash revoked through a supplied normalized policy object.
12. Add recovery coverage asserting duplicate revoked-key and proof-hash lists normalize deterministically.
13. Add malformed quality-proof JSON sanitization coverage.
14. Add malformed bundle JSON sanitization coverage.
15. Add missing quality-proof file fail-before-provider coverage.
16. Add installer rejection coverage for a non-D explicit download path.
17. Add installer coverage that archive cleanup preserves an existing caller-owned local source file.
18. Re-probe DashScope only if the user-level credential changes; never expose the value or body.
19. Produce signed local-versus-Qwen disagreement evidence only after both real structured results exist.
20. Run PostgreSQL recovery/fencing parity when a real DSN or CI service becomes available; otherwise re-record exact blocker evidence.
