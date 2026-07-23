## Round51 identity, OTP, and SMTP calibration - 2026-07-10T15:30:00Z

Baseline and peer state:

- Authoritative worktree:
  `C:\Users\33516\Documents\Ashr_a1_clean_rebase`.
- Local branch: `codex/a1-local-sdk-runner-clean`; push target:
  `origin/codex/a1-local-sdk-runner`; PR #31.
- Started from `1cb15b3e`, whose CL Gate was green.
- Fetch observed A3 branch movement only. No `origin/main` A1 peer change was
  found that needed integration.
- Five A2 result fixtures remain CRLF-only peer noise and are excluded from
  this A1 publication.

Human-subagent results:

- QQ Connect requires a business license in the user-observed enrollment flow,
  so it is classified `enterprise-only` and was not pursued.
- QQ Mail SMTP was enabled.
- `ASHR_SMTP_HOST`, `ASHR_SMTP_PORT`, `ASHR_SMTP_FROM`, and
  `ASHR_SMTP_AUTH_CODE` were confirmed present by name and length only.
- No address, authorization code, recipient, OTP, or message body was printed
  or written to evidence.

Implemented:

1. Added restricted PostgreSQL session authentication with digest-only lookup
   and live principal, credential, organization membership, and project
   membership revalidation.
2. Hardened revocation outbox task validation, lease fencing and renewal,
   bounded dependency calls, dead lettering, and public-safe metadata.
3. Added Go OTP lifecycle for email and phone binding, login, and recovery.
4. Added matching Python and TypeScript OTP contracts.
5. Expanded generated TS/Python parity to 12 identity routes and 28 stable
   error codes with zero differing fields.
6. Added an implicit TLS SMTP sender with TLS 1.2 minimum, deadline controls,
   email-only delivery, header injection prevention, and redacted errors.
7. Wired SMTP only behind explicit development-memory verification flags.
   Production still refuses memory OTP delivery and requires durable injected
   components.

Validation:

- `go test -count=1 ./...` in `packages/go/ashrclone`: passed.
- `go vet ./...` in `packages/go/ashrclone`: passed.
- `go test -count=1 ./...` in `tests/integration/go`: passed.
- Python parity and focused identity/migration tests: 60 passed.
- TypeScript build: passed.
- TypeScript full suite: 512 passed.
- Real SMTP calibration: one self-addressed message, 15-second hard timeout,
  successful in approximately 2.3 seconds. Only the outcome class and duration
  are retained.

Evidence:

- `docs/a1/evidence/round51_identity_otp_smtp_20260710.md`
- `tests/a1/docs/a1/ts_python_gap_matrix.json`

Growth-Auditor:

- The initial NO-GO included a compile failure observed before the SMTP sender
  landed. That compile blocker is resolved and the full Go tests now pass.
- The commercial NO-GO remains for production OTP: durable PostgreSQL OTP
  state, transactionally consistent receipt consumption and identity mutation,
  anti-enumeration, distributed rate limiting, durable audit, SMS delivery,
  production store interfaces, and vault-backed OAuth are still required.
- The next lane begins with PostgreSQL OTP storage and transaction boundaries,
  followed by production identity-store interfaces and abuse controls.

Publication plan:

- Run the full A1 Python suite, generated fixture checks, CL guards, diff
  hygiene, and location-only secret scan.
- Stage only reviewed A1 paths. Never stage the five A2 CRLF-only fixtures.
- Push to `origin/codex/a1-local-sdk-runner` and require PR #31 CL Gate green.

## Round42 commercial SaaS backend growth - 2026-07-09T23:55:00Z

Baseline:
- Started after PR #27 CL was green on head `9891881`: Plan/hygiene, Go, Python A1/A2, TypeScript, and CL summary passed; A3/Rust skipped by gate policy.
- A2/A3 fixture exception was closed; this round returned to A1-owned commercial backend/SDK/infra scope.
- Growth-Auditor verdict: A1 is a strong local-commercial foundation but not money-grade SaaS; next spine should be Go/Postgres/OpenAPI/object storage/billing provider paths.

Implemented:
- Added Go `WorkerDaemon` library loop for bounded lease/handle/complete/fail with optional heartbeat and public-safe failure conversion.
- Added memory-service worker audit-chain events for enqueue, lease, heartbeat, complete, and fail so worker mutations are enterprise-auditable in local and Go contract tests.
- Expanded self-host Docker commercial profile with API/worker/daemon profiles, Postgres/Redis/MinIO wiring, MinIO bucket bootstrap, healthchecks, and secret-ref-only env example.
- Added payment/OAuth commercial safety surfaces in the Python control plane and SDK: GitHub/Google OAuth provider refs, OAuth sessions, commercial provider configs, Stripe test/live mode boundary evidence, and commercial auth/payment snapshot route.
- Added TS commercial control-plane evidence kit and exported it from the TS SDK barrel.
- Closed a TS CLI parity gap by exposing `api-key-revoke` in the TS SaaS CLI and HTTP client; refreshed `tests/a1/docs/a1/ts_python_gap_matrix.json` so Python-only SaaS CLI commands are now empty.

Validation:
- `gh pr checks 27 --watch=false` before this round -> CL green.
- `go test ./...` from `packages/go/ashrclone` -> passed.
- `go test ./...` from `tests/integration/go` -> passed.
- `npm test --prefix packages/ts/ashr-clone` -> 342 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> 406 passed, 1 skipped.
- `python -B -m pytest tests/a1/test_local_self_host_smoke_compose.py tests/a1/test_ts_python_gap_matrix.py tests/a1/test_saas_sdk_client.py -q -p no:cacheprovider` -> 26 passed, 1 skipped.
- `docker compose --env-file infra/docker/self-host.env.example -f infra/docker/docker-compose.self-host.yml --profile commercial config --quiet` -> passed.

Safety and evidence:
- No desktop key file was read; no raw API key/provider secret/card data was written.
- No real Ashr API call was made in this implementation slice; Round39 paid-media quota/API gate remains the latest mutating calibration evidence, so next paid API work should first run a fresh quota/usage gate or a bounded read-only batch.
- Live Stripe/real card/merchant/OAuth account actions remain human-confirmed steps; code currently records safety contracts and ref-only configuration.

Next top A1 growth points:
1. Wire Go `WorkerDaemon` into a CLI/process entrypoint and self-host daemon command.
2. Promote Go/Postgres as canonical API backend for commercial auth/payment and worker daemon paths.
3. Add object storage upload-url/complete/read contract backed by MinIO/S3 refs.
4. Add SQL RLS/audit trigger coverage for OAuth/payment/provider config and worker daemon mutations.
5. Run purposeful official Ashr read-only small-batch plus fresh quota-gated mutating probe only after gate record is reviewed.
## Round41 CL fixture unblock - 2026-07-09T23:10:00Z

Baseline:
- Continued on `codex/a1-local-sdk-runner-clean` / PR #27 after commit `8164156` pushed.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` observed peer movement on `origin/codex/a3-commercial-growth-round4`; PR #27 still targets `codex/a1-local-sdk-runner`.
- CI failure root cause was A2 generated fixture drift after A1 real API evidence index label/count updates in Round40, not judge semantic drift.
- WSL/bash check during this round returned `/bin/bash` missing from the current WSL relay; treat Linux shell availability as an environment item to revisit before daemon/container work.

Implemented:
- Ran `python scripts/a2_regenerate_fixtures.py --write` as a CL unblock exception and refreshed the generated A2 fixture snapshot set under `fixtures/a2`.
- No secret files were read; no Ashr API call was made in this CI-unblock slice.

Validation:
- `python -B -m pytest tests/a2/test_contracts.py -q -p no:cacheprovider` -> 52 passed.
- `python -B -m pytest tests/a1/test_evidence_index.py::test_tracked_a1_public_evidence_artifacts_are_secret_safe -q -p no:cacheprovider` -> 1 passed.
- `python scripts/cl_guard.py hygiene` -> passed.
- `git diff --check` -> passed with CRLF normalization warnings only.

Next:
- Commit/push the fixture unblock, watch PR #27 checks, then return to A1 large-SaaS growth: Go runtime daemon, SQL/RLS quota ledger, TS parity, provider webhook/OAuth/login scaffolds, object storage bundle persistence, and purposeful official API calibration.
# A1 Worklog

## 2026-07-09 - Go ingress auth handle enforcement and TS/Python parity gate

Round goal:
- Fix the highest-risk SaaS boundary called out by Growth-Auditor: protected Go control-plane routes must not remain anonymous.
- Make TS-vs-Python lag visible as a public-safe matrix and guard test so TS cannot quietly drift behind Python.

Baseline / repo state:
- Branch: `codex/a1-local-sdk-runner`.
- PR #22: open, draft, mergeable, CL-green at start of this round.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` observed remote A3 branches `codex/a3-commercial-cl-gate` and `codex/a3-commercial-growth-round2`.
- Existing unrelated local changes remain excluded from A1 staging: `docs/a3/acceptance_checklist.md`, `docs/a3/worklog.md`, `recon/`, and `tools/`.

20 growth points attacked:
1. Add Go auth/scope vocabulary for local control-plane protected routes.
2. Reject raw API key material in Go HTTP bodies.
3. Reject `Authorization` header input in local Go HTTP server so secrets cannot enter local evidence paths.
4. Require `api_key_id` / `auth_key_id` handles on submit.
5. Require handles on run upload.
6. Require handles on trace ingestion.
7. Require handles on artifact manifest create/list.
8. Require handles on worker enqueue/lease/complete/fail/list.
9. Require handles on usage reads.
10. Require handles on audit-chain verification reads.
11. Reject tenant mismatch between authenticated headers and request body/query.
12. Reject API-key handle mismatch between authenticated headers and request body/query.
13. Preserve local-only public-safe behavior without storing or reading raw secrets.
14. Add Go negative auth tests for missing handle and raw key input.
15. Add Go negative auth tests for tenant/key mismatch across route families.
16. Update Go happy-path tests to carry non-secret key handles.
17. Extend TS compiled-Go-server smoke through usage and audit-chain calls.
18. Keep TS media artifact manifest parity across text/audio/file/image/video.
19. Add TS/Python parity matrix across exports, calibration, SaaS, CLI, runner/adapter/trace, and media.
20. Run real read-only official API calibration with env-only key and redacted evidence summary.

Subagent results:
- Growth-Auditor: read-only audit identified Go ingress auth as the must-fix commercial boundary; follow-up risks are hashed API-key storage, scope enforcement, quota preflight, and billing-grade usage ledger.
- TS/Python parity auditor: added `tests/a1/docs/a1/ts_python_gap_matrix.json` and `tests/a1/test_ts_python_gap_matrix.py`; verified the artifact is public-safe and actionable.
- Go auth/quota worker: added Go auth contract and protected route tests; verified `go test ./...` in `packages/go/ashrclone` and `tests/integration/go`.
- TS parity worker: strengthened `packages/ts/ashr-clone/test/go-server.test.mjs` so TS drives compiled Go usage/audit/worker protected calls with a public key handle; verified TS package tests.

Implemented / integrated files:
- `packages/go/ashrclone/auth.go`
- `packages/go/ashrclone/server.go`
- `packages/go/ashrclone/server_test.go`
- `packages/ts/ashr-clone/test/go-server.test.mjs`
- `tests/a1/docs/a1/ts_python_gap_matrix.json`
- `tests/a1/test_ts_python_gap_matrix.py`
- `docs/a1/evidence/README.md`
- `docs/a1/worklog.md`

Validation:
- `npm test --prefix packages/ts/ashr-clone` -> passed, 283 tests.
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 314 tests.
- `python -m pytest tests/a1/test_ts_python_gap_matrix.py -q` -> passed in the parity auditor subtask and in the full A1 suite.

Real API / private evidence:
- `ASHR_API_KEY` was present in the environment. The raw key was not read from disk, printed, logged, staged, or committed.
- One PowerShell heredoc attempt failed before execution because PowerShell does not support the Bash syntax used; no API call was sent by that failed command.
- Successful command: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_round_go_auth_ts_parity_readonly_20260709_115427.json`.
- Public summary: status `ok`; read steps `5`; mutating steps `0`; error steps `0`; quota blocks `0`; estimated calls `7`; response key sets observed for user/health/agents/datasets/requests families.
- Private evidence remains under ignored `docs/evidence/private_refs/` and must not be staged.

Known gaps:
- This round is handle enforcement, not full production auth. Go still needs hashed API-key storage, scope checks, key lifecycle, quota hard limits, and Postgres-backed auth/usage/audit enforcement.
- TS/Python parity is now measured, but the matrix still records Python-led calibration gaps and TS-led runtime export gaps that need closure within the next two A1 rounds.
- Official API calibration remains read-only in this round; paid mutation calibration still requires a dry-run plan, quota evidence, small batch, zero retries, and private evidence capture.

Next 20 A1 growth points:
1. Implement Go API-key lifecycle storage with hashed secrets, prefix display, revocation, last-used metadata, and project binding.
2. Add Go scope enforcement per protected route and tests for 403 wrong-scope cases.
3. Add Go quota-before-mutation preflight and tests for 429 without partial writes.
4. Add live Postgres auth/quota/audit tests gated by `A1_POSTGRES_TEST_DSN`.
5. Add SQL/PLpgSQL usage consume/refund helpers and audit read triggers.
6. Add migration checksum/version ledger.
7. Add Go audit-log listing route and TS/Python hosted client parity.
8. Add Go release evidence packet and verify routes.
9. Generate shared OpenAPI/scope manifest from Go route metadata.
10. Turn the TS/Python matrix into generated symbol/CLI/route/media diff.
11. Export or intentionally document Python equivalents for TS-led runtime surfaces.
12. Export or implement TS equivalents for Python-led calibration readiness packets.
13. Add Python SDK smoke against compiled Go server protected routes and auth-negative paths.
14. Add TS negative auth smoke against compiled Go server protected routes.
15. Add Docker Compose live smoke for Go API + Postgres + worker daemon.
16. Add Terraform/HCL hardened self-host profile and validate it in CI.
17. Extend Rust verifier to signed multi-file release/evidence bundles.
18. Run another official read-only calibration targeting error/quota/usage fields when surfaced.
19. Prepare controlled paid text mutation calibration with explicit quota gate and private evidence.
20. Only after text mutation evidence, expand paid audio/file/image/video calibration one modality at a time.

## 2026-07-09 - TS calibration/SaaS parity surge and Go API-key quota lifecycle

Goal:
- Respond to the hard constraint that TypeScript must not lag Python/A1 by moving TS from CLI-only calibration parity into public SDK import parity, and expanding TS SaaS tests across API key, quota, artifact, worker, audit, release evidence, and five-modality calibration surfaces.
- Continue the A1 commercial backend line with Go local API-key lifecycle, scope/quota enforcement, and public route parity evidence refresh.

20 growth points executed this round:
1. Exported TS calibration APIs from the SDK barrel so `parseArgs`, `runCalibration`, and `main` are importable through `@ashr-clone/sdk`.
2. Added TS calibration SDK tests for text/image/audio/file/video dry-run mutating request plans.
3. Added TS calibration parser tests for paid media opt-in modalities.
4. Added TS calibration parser tests for repeated modality ordering before deterministic summary sorting.
5. Added TS calibration SDK tests for read-only dry-run parity without auth env.
6. Added TS calibration SDK tests proving env key presence is redacted to variable names only.
7. Added TS calibration SDK tests for all five modality summaries in one public-safe manifest.
8. Added TS calibration SDK tests for real execution guardrail knobs: `--execute`, `--small-batch`, `--max-retries 0`, timeout, retry backoff, and limit.
9. Added TS parser fail-fast tests for unknown flags, positional raw secret-like inputs, and invalid modalities before key lookup.
10. Added TS SaaS scope-auth tests for `sdk:submit`, `run:upload`, `trace:ingest`, `artifact:upload`, `evidence:read`, `audit:read`, `worker_job:write`, `worker_job:read`, and `usage:read`.
11. Added TS revoked API-key fail-closed mutation coverage.
12. Added TS artifact evidence scope/listing coverage and raw-payload redaction assertion.
13. Added TS release evidence packet tamper detection coverage.
14. Added TS worker lease owner mismatch and successful owner completion coverage.
15. Added TS audit-chain verification coverage with the dedicated audit-chain schema.
16. Added TS snapshot restore coverage for API-key rate limits and audit state.
17. Updated TS/Python parity matrix generator to include official API calibration SDK import-surface parity.
18. Refreshed `tests/a1/docs/a1/ts_python_gap_matrix.json` from the generator.
19. Refreshed public Go/Python/TS route parity snapshot after Go API-key routes were added.
20. Verified Docker compose configs and WSL/Docker state for local self-host readiness.

Implemented / integrated files:
- `packages/go/ashrclone/api_error.go`
- `packages/go/ashrclone/auth.go`
- `packages/go/ashrclone/postgres.go`
- `packages/go/ashrclone/server.go`
- `packages/go/ashrclone/server_test.go`
- `packages/go/ashrclone/service.go`
- `packages/go/ashrclone/service_test.go`
- `packages/sdk/ashr_clone/calibrate.py`
- `packages/ts/ashr-clone/src/calibrate.ts`
- `packages/ts/ashr-clone/src/index.ts`
- `packages/ts/ashr-clone/src/saas.ts`
- `packages/ts/ashr-clone/test/calibrate.test.mjs`
- `packages/ts/ashr-clone/test/calibration-parity.test.mjs`
- `packages/ts/ashr-clone/test/saas.test.mjs`
- `packages/ts/ashr-clone/test/saas-money-grade-parity.test.mjs`
- `docs/a1/api_calibration/official_api_readiness_packet.json`
- `docs/a1/evidence/go_python_ts_route_parity_snapshot.json`
- `docs/a1/schemas/api_calibration_readiness_packet.schema.json`
- `tests/a1/docs/a1/ts_python_gap_matrix.json`
- `tests/a1/test_python_calibrator.py`
- `tests/a1/test_ts_python_gap_matrix.py`
- `tests/a1/ts_python_parity_matrix.py`

Validation:
- `npm test` in `packages/ts/ashr-clone` -> passed, 316 tests.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 314 tests.
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> passed, 8 tests.
- `python -B tests/a1/ts_python_parity_matrix.py --check` -> passed.
- `docker compose -f services/runner/docker-compose.a1.yml config` -> passed.
- `docker compose -f infra/docker/docker-compose.self-host.yml config` -> passed.

Environment evidence:
- Docker Desktop is available: `docker version` and `docker compose version` succeeded.
- WSL is available with the `docker-desktop` distribution running on WSL2; `wsl.exe -e /bin/sh -lc 'echo sh-ok'` succeeded.
- `/bin/bash` is not present in the current default `docker-desktop` WSL distribution. `wsl.exe --list --online` shows installable Ubuntu/Debian options, but installing a full user distro may require first-run interactive setup, so this round used PowerShell/Node/Python/Go directly and recorded the gap instead of blocking.

Real API / private evidence:
- No desktop key file was read. API key policy remains env-only.
- No raw key, bearer token, or private payload was logged, staged, or committed.
- This round focused on SDK/runtime parity and did not send mutating official API calls. The current readiness packet still marks mutating small batch as not ready without quota-gate evidence.

Peer changes / impact:
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` confirmed `origin/codex/a1-local-sdk-runner` had been restored to `989fdc36` after an accidental main merge was reverted remotely.
- Main workspace still has unrelated A3 line-ending noise in `docs/a3/**` and `fixtures/a3/**`; these must be excluded from A1 staging.
- Temporary detached worktree `C:\Users\33516\Documents\Ashr_a1_round` was created during the remote merge-risk investigation and points at the reverted accidental merge commit; it is not used for this commit.

Known gaps / next 20:
1. Push this scoped A1 round after second-pass Growth-Auditor review.
2. Install or initialize a proper WSL user distribution with bash if fully noninteractive setup is possible; otherwise document exact human first-run step.
3. Add TS parity for every remaining Python-only public export shown in the generated matrix, or explicitly mark intentional Python-only areas.
4. Add Go audit-log listing route and TS/Python hosted client parity.
5. Add Go release evidence packet and verify routes.
6. Add Python SDK smoke against compiled Go server API-key lifecycle, rate limit, and worker routes.
7. Add Go Postgres-backed API-key secret hash persistence tests.
8. Add SQL/PLpgSQL live RLS tenant-isolation tests gated by `A1_POSTGRES_TEST_DSN`.
9. Add migration checksum/version ledger.
10. Add quota consume/refund helper tests across upload, trace, artifact, and worker operations.
11. Add official read-only calibration targeting usage/quota/error response shape when surfaced.
12. Prepare controlled paid text mutation calibration only with dry-run plan, quota gate, small batch, zero retries, and private evidence path.
13. Expand paid media calibration one modality at a time after text mutation evidence: image, audio, file, video.
14. Add generated OpenAPI/scope manifest from Go route metadata.
15. Add Docker live smoke for Go API + Postgres + worker daemon.
16. Add Terraform self-host validation to the A1 gate.
17. Add Rust verifier fixture coverage against A1 release/evidence packets.
18. Add public-safety scan over generated A1 artifacts for auth/header/key markers.
19. Add quota ledger rollup fixtures for tenant/project billing views.
20. Keep A2/A3 files out of A1 commits unless explicitly unblocking CL.

Real API calibration addendum:
- Command: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_round_ts316_go_key_quota_readonly_20260709_131208.json`.
- Public summary: status `ok`; read steps `5`; mutating steps `0`; error steps `0`; quota blocks `0`; estimated calls `7`; modalities `[]`.
- Private evidence path is ignored and must not be staged: `docs/evidence/private_refs/a1_round_ts316_go_key_quota_readonly_20260709_131208.json`.
- Raw key remained env-only; no desktop key file was read.

## 2026-07-14 - Durable provider request journal and fenced recovery

Round goal:
- Add Python and TypeScript provider-call journals for non-idempotent commercial
  operations.
- Fail closed after restart, stale leases, ambiguous completion, or partial
  streaming.
- Prevent same-process duplicate TypeScript execution and stale-owner
  completion overwrite.
- Persist only bounded, public-safe five-modality evidence.

Implemented / integrated files:
- `packages/sdk/ashr_clone/provider_journal.py`
- `packages/sdk/ashr_clone/__init__.py`
- `packages/ts/ashr-clone/src/provider-request-journal.ts`
- `packages/ts/ashr-clone/src/index.ts`
- `tests/a1/test_provider_journal.py`
- `tests/a1/test_provider_journal_adversarial_round58.py`
- `packages/ts/ashr-clone/test/provider-request-journal.test.mjs`
- `packages/ts/ashr-clone/test/provider-request-journal-adversarial-round58.test.mjs`
- `tests/a1/docs/a1/ts_python_gap_matrix.json`
- `docs/a1/evidence/round58_provider_request_journal.md`

Validation:
- Focused Python provider-journal tests: `24 passed`.
- Full TypeScript SDK suite after fencing fixes: `329 passed`, no failures,
  skips, or TODO tests.
- Full Python A1 suite reached `336 passed`, `1 skipped`; the only failure was
  the expected generated TS/Python parity artifact drift caused by the new
  exports. The artifact was regenerated and its focused test passed.

Safety and recovery:
- Persisted active Python requests recover as `indeterminate`, with lease owner
  and expiry removed and restart evidence recorded.
- Stream-observed requests cannot enter automatic retry through either normal
  scheduling or reconciliation.
- TypeScript coordinates active executions per journal key, waits for the
  current owner to settle before rejecting a duplicate, and uses token identity
  so an obsolete owner cannot remove or overwrite a newer fence.
- Persisted evidence excludes raw idempotency keys, prompts, media, provider
  URLs, credentials, and lease owners.
- Python and TypeScript behavioral guarantees are aligned, but their current
  local snapshot layouts are explicitly implementation-private and not claimed
  as cross-language wire-compatible.

## 2026-07-14 - Canonical identity, OAuth security, and SDK client parity

Round goal:
- Separate registration from login across the Go authority and A3-facing
  Python/TypeScript clients.
- Establish one canonical account with explicit multi-credential binding,
  domestic email-first defaults, optional/recommended MFA, and retained
  QQ/WeChat OAuth capability surfaces.
- Add rotation-aware identity schema/RLS foundations and complete cross-language
  contract validation without exposing credentials or OAuth artifacts.

Implemented / integrated files:
- `packages/go/ashrclone/identity.go`
- `packages/go/ashrclone/identity_http.go`
- `packages/go/ashrclone/identity_oauth.go`
- `packages/go/ashrclone/identity_test.go`
- `packages/go/ashrclone/identity_http_test.go`
- `packages/go/ashrclone/identity_oauth_test.go`
- `packages/go/ashrclone/server.go`
- `packages/sdk/ashr_clone/identity_client.py`
- `packages/sdk/ashr_clone/__init__.py`
- `tests/a1/test_identity_client.py`
- `packages/ts/ashr-clone/src/identity-client.ts`
- `packages/ts/ashr-clone/src/index.ts`
- `packages/ts/ashr-clone/test/identity-client.test.mjs`
- `docs/a1/schemas/a1_control_plane_postgres_migration.sql`
- `packages/go/ashrclone/postgres.go`
- `packages/go/ashrclone/postgres_test.go`
- `tests/a1/test_a1_control_plane_postgres_migration.py`
- `tests/integration/test_a1_control_plane_identity_migration_live.py`
- `tests/a1/ts_python_parity_matrix.py`
- `tests/a1/test_ts_python_gap_matrix.py`
- `tests/a1/docs/a1/ts_python_gap_matrix.json`
- `docs/a1/evidence/go_python_ts_route_parity_snapshot.json`
- `docs/a1/evidence/round60_identity_client_oauth_parity.md`

Security / contract results:
- Registration and login use separate routes and challenge purposes.
- OAuth login and explicit link are separate; verified-email equality never
  silently links or merges canonical accounts.
- Link mode requires an authenticated session; credential binding additionally
  requires an opaque account-bound proof and explicit consent.
- QQ/WeChat capability metadata is typed while PKCE S256, one-time HMAC state,
  exact redirect allowlists, no-store responses, and authority mismatch checks
  fail closed.
- Python and TypeScript safe serialization excludes session tokens, binding
  proofs, and OAuth authorization URLs while transports can still use them.
- PostgreSQL schema/RLS foundations store only ciphertext or keyed hashes for
  delivery targets, challenge secrets, sessions, and provider subjects.

Validation:
- `python -B tests/a1/ts_python_parity_matrix.py --check` -> passed.
- Go/Python/TS route evidence test -> `8 passed`.
- Full Python A1 suite -> `343 passed`, `1 skipped`.
- Full TypeScript SDK suite -> `333 passed`, no failures/skips/TODOs.
- `go test ./...` in `packages/go/ashrclone` -> passed.
- Live PostgreSQL identity migration/RLS test -> `1 skipped` because
  `A1_POSTGRES_TEST_DSN` was not configured; no live database pass is claimed.
- `git diff --check` -> passed with line-ending warnings only.
- Go race validation remains blocked: CGO is disabled by default, and
  `CGO_ENABLED=1 go test -race ./...` cannot build because `gcc` is absent.

Known gaps:
1. The identity authority still uses in-memory runtime state; implement and wire
   the PostgreSQL identity repository.
2. Complete production delivery-target encryption and key-provider-backed
   rotation/migration, not only rotation-ready schema fields and in-memory HMAC
   lifecycle.
3. Run live PostgreSQL migration idempotency and RLS isolation with
   `A1_POSTGRES_TEST_DSN`.
4. Add database concurrency tests for one-time challenge/session/binding use and
   credential uniqueness.
5. Add compiled-Go HTTP smoke from both Python and TypeScript identity clients.
6. Install a supported C compiler and run the Go race suite.
7. Add production QQ/WeChat provider adapters while retaining current redirect,
   PKCE, state, explicit-link, and redaction guardrails.
8. Overall A1 remains in progress.

## 2026-07-09 - Worker-Evidence-API public-safe WSL/API evidence

Round goal:
- Record public-safe evidence that `Ubuntu-24.04-Ashr` is installed at `D:\WSL\Ubuntu-24.04-Ashr` and can run Bash.
- Run one purposeful official Ashr API read-only small-batch calibration using environment auth only, if available.
- Inspect the current official API readiness packet and propose next code tasks for API parity.

Implemented / integrated files:
- `docs/a1/evidence/round21_worker_evidence_api.md`
- `docs/a1/worklog.md`

Validation / command results:
- `Test-Path -LiteralPath 'D:\WSL\Ubuntu-24.04-Ashr'` -> `True`.
- `wsl.exe --list --verbose` -> `Ubuntu-24.04-Ashr` present as a WSL2 distro; initially stopped, then launched for verification.
- `wsl.exe -d Ubuntu-24.04-Ashr -- bash -lc 'echo shell=$SHELL; bash --version | sed -n "1p"; uname -srm; pwd'` -> `/bin/bash`, GNU Bash `5.2.21(1)-release`, WSL2 kernel `6.18.33.2-microsoft-standard-WSL2 x86_64`, cwd `/mnt/c/Users/33516/Documents/Ashr`.
- Environment presence check showed `ASHR_API_KEY=true`, `ASHR_LABS_API_KEY=false`, `ASHR_LABS_BASE_URL=false`; no values were printed.
- Official read-only command: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json`.
- Official read-only result: status `ok`; read steps `5`; mutating steps `0`; error steps `0`; quota blocks `0`; estimated calls `7`; modalities `[]`.
- Public-safe response key summary observed: `init` -> `features,notes,status,tenant,user`; `health-check` -> `db,message,status`; `list-agents` -> `_user,agents,status`; `list-datasets` -> `_user,datasets,next_cursor,status`; `list-requests` -> `_user,next_cursor,requests,status`.

Private evidence:
- Manifest: `docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json`.
- Observed manifest size: 5,547 bytes.
- Per-step private records referenced by the manifest remain under ignored `docs/evidence/private_refs/`.
- No desktop key file was read; raw key material and raw official API payloads were not copied into public docs.

Readiness packet findings / next code tasks:
1. Add a public-safe summary builder for private official API manifests so future A1 notes are reproducible without hand extraction.
2. Add read-only usage/quota/error-shape probing when hosted endpoints are available, with private output and public key/status summaries only.
3. Add quota-gate freshness verification for `create-request-text` before any mutating official calibration is allowed.
4. Add a tiny text mutation readiness test path requiring `--include-mutating`, explicit `--modality text`, zero retries, a private output sink, and a fresh quota-gate record.
5. Expand paid media calibration one modality at a time after reviewed text mutation evidence: image, audio, file, then video.
6. Add local parity stubs/tests for hosted API-key lifecycle, usage ledger, trace ingestion, artifact upload, release evidence, and webhooks.
7. Add public-safety regression scanning for raw payload/auth/key markers in generated A1 public docs while allowing private path references.

## 2026-07-09 - A1 Go/Python/TS audit and release evidence parity

Round goal:
- Close the A1 commercial control-plane gap for audit-log listing and release evidence packet build/verify across Go backend, Python SDK/CLI, TS/Python parity evidence, and route snapshots.
- Keep official Ashr API usage env-only and record WSL-on-D evidence for future bash/Docker work.

Implemented / integrated files:
- packages/go/ashrclone/auth.go: added evidence:read scope.
- packages/go/ashrclone/types.go: added audit-log list and release evidence packet/verification DTOs.
- packages/go/ashrclone/service.go: added audit event recording/listing, packet build/verify, stable JSON packet hashing, and filter helpers.
- packages/go/ashrclone/postgres.go: added Postgres audit-log listing and release packet build/verify over durable run/upload/trace/artifact/audit tables.
- packages/go/ashrclone/server.go: added GET /audit-log, GET /runs/{run_id}/release-evidence, POST /runs/{run_id}/release-evidence/verify, scope preflights, and manifest routes.
- packages/go/ashrclone/service_test.go and packages/go/ashrclone/server_test.go: added audit filtering, release evidence roundtrip/tamper, manifest, and scoped evidence rejection coverage.
- packages/sdk/ashr_clone/saas.py and packages/sdk/ashr_clone/saas_cli.py: added Python `audit_log` hosted route/CLI parity and release verify aliasing.
- `tests/a1/test_saas_sdk_client.py`, `tests/a1/test_ts_python_gap_matrix.py`, `tests/a1/ts_python_parity_matrix.py`, `tests/a1/docs/a1/ts_python_gap_matrix.json`: refreshed required hosted-route parity.
- docs/a1/evidence/go_python_ts_route_parity_snapshot.json: refreshed public-safe route evidence after Go audit/release routes landed.
- docs/a1/evidence/round21_worker_evidence_api.md: recorded D-drive Ubuntu WSL and official read-only API calibration evidence.

Validation / command results:
- go test ./... in packages/go/ashrclone -> passed.
- go test ./... in tests/integration/go -> passed.
- npm test in packages/ts/ashr-clone -> passed, 316 tests.
- python -B tests/a1/ts_python_parity_matrix.py --check -> passed.
- python -B -m pytest tests/a1 -q -p no:cacheprovider -> passed, 314 tests.
- docker compose -f services/runner/docker-compose.a1.yml config -> passed.
- docker compose -f infra/docker/docker-compose.self-host.yml config -> passed.
- wsl.exe -d Ubuntu-24.04-Ashr -- bash -lc "set -euo pipefail; echo WSL_BASH_OK; pwd; command -v bash; bash --version | sed -n '1p'" -> passed; distro is mounted at workspace and Bash 5.2.21 is available.

Official API / private evidence:
- Read-only small-batch official calibration was run by Worker-Evidence-API with env-only auth: python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json.
- Public-safe summary: status ok; read steps 5; mutating steps `0`; error steps `0`; quota blocks `0`; estimated calls 7.
- Private evidence remains ignored under docs/evidence/private_refs/; no desktop key file was read and no raw official payload/key was copied to public docs.

Peer changes / impact:
- PR #22 latest pushed commit 9a217f4 had green CL Gate before this round and is BEHIND main.
- Remote peer work observed: A3 PR #25 open, A3 PRs #23/#24 merged. Local A3 files still have unrelated line-ending noise and must remain excluded from A1 staging.

Known gaps / next 20:
1. Add Go GET /quota alias or intentionally document usage vs quota route vocabulary.
2. Add Go GET /runs/{run_id}/lifecycle route parity or mark Go lifecycle intentionally SDK-only.
3. Add generated Go route/scope manifest instead of a static route list.
4. Add per-route insufficient-scope tests for audit-log, usage, artifact read, worker list, release evidence, and future quota/lifecycle.
5. Add live-gated Postgres tests for release evidence packet build over durable tables.
6. Add live-gated Postgres API-key secret hash persistence tests.
7. Add live-gated SQL/RLS tenant-isolation tests for runs, artifacts, quota, audit, and worker jobs.
8. Add migration checksum/version ledger.
9. Add quota consume/refund helper tests across submit, upload, trace, artifact, release evidence, and worker operations.
10. Add billing-grade quota rollup fixtures by tenant/project/key/operation/day.
11. Add Docker live smoke for Go API + Postgres + worker daemon.
12. Add Python SDK smoke against compiled Go server for API-key lifecycle, quota, worker, audit, and release evidence.
13. Add TS generated client parity for any remaining Python-only public export or mark intentional gaps.
14. Add official read-only usage/quota/error-shape probe summaries when hosted endpoints surface them.
15. Prepare quota-gated text mutation calibration only after reviewed fresh quota gate, zero retries, and private evidence path.
16. Expand paid media calibration one modality at a time after text mutation evidence: image, audio, file, video.
17. Add public-safe manifest summarizer for private official API manifests.
18. Add Rust verifier fixture coverage against Go release evidence packets.
19. Add Terraform/self-host validation to A1 gate.
20. Keep A2/A3 files out of A1 commits unless explicitly unblocking CL.

### 2026-07-09 A1 public-safe official API manifest summary

- Added a public-safe private official API manifest summarizer in `packages/sdk/ashr_clone/calibrate.py`.
- The summarizer reads only an explicitly provided/private ignored manifest path and emits redacted summary fields: status/counts, step statuses, response key names, top-level list counts, quota-block booleans, and guardrail booleans.
- Generated tracked evidence artifact `docs/a1/evidence/official_api_readonly_manifest_summary.json` for the default private manifest path `docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json`; that ignored file is absent in this worktree, so the public artifact records `status: missing` with zero counts.
- Added Python calibrator tests covering fake raw API keys, bearer strings, auth headers, request params, private record paths, and private payload bodies to ensure they do not leak into public summaries.
- Validation: `python -B -m pytest tests/a1/test_python_calibrator.py -q -p no:cacheprovider` -> passed, 32 tests.
- No desktop key file was read. No official API calls were run in this summarizer subround.

## 2026-07-09 - A1 release evidence verifier hardening and public API summary artifact

Round goal:
- Continue PR #27 on a clean `origin/main` base while keeping A1 scope tight.
- Harden Go release evidence verification so submitted packets fail closed instead of accepting incomplete audit evidence.
- Add a repeatable public-safe official API manifest summary helper/artifact that never copies private records or raw keys into tracked docs.

Implemented / integrated files:
- `packages/go/ashrclone/service.go`: release evidence verification now requires core packet fields and `audit_verification.verified == true` before hash verification can pass.
- `packages/go/ashrclone/service_test.go`: added negative coverage for missing `audit_verification`, false audit verification, missing `packet_sha256`, missing core fields, tampered scope with recomputed hash, and tampered content/hash mismatch.
- `packages/sdk/ashr_clone/calibrate.py`: added public-safe official API private-manifest summarizer and writer helpers.
- `tests/a1/test_python_calibrator.py`: added tests proving the public summary omits raw response bodies, request parameters, auth header names/values, raw key material, and private record locations.
- `docs/a1/evidence/official_api_readonly_manifest_summary.json`: generated public-safe summary artifact. In the clean worktree the private manifest is absent, so the summary records `status=missing` with zero steps and no private values.
- `docs/a1/worklog.md`: fixed previous PowerShell escape artifacts in path/test command evidence.

Validation / command results:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `python -B -m pytest tests/a1/test_python_calibrator.py tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_ts_python_gap_matrix.py tests/a1/test_saas_sdk_client.py -q -p no:cacheprovider` -> passed, 52 tests.
- `python -B tests/a1/ts_python_parity_matrix.py --check` -> passed.
- `git diff --check` -> passed.
- `python -c "from packages.sdk.ashr_clone.calibrate import write_public_official_api_manifest_summary; ..."` -> wrote `docs/a1/evidence/official_api_readonly_manifest_summary.json` with schema `ashr.clone.public_official_api_manifest_summary.v1`, `source_private_manifest_present=false`, and `status=missing`.

PR / CI status:
- PR #27 remains open/draft and cleanly scoped to A1 files. Existing CL Gate execution has Plan/Python/Go success with A3/TS/Rust skipped by selective plan; `CL Gate summary` is still queued on GitHub `ubuntu-latest` runner, not failed.

Known gaps / next 20:
1. Re-run public manifest summary in a workspace where the ignored private official API manifest exists and commit only the redacted summary artifact.
2. Add CLI flag for writing the public official API manifest summary from `calibrate.py`.
3. Add generated Go route/scope manifest instead of static route list.
4. Add Go `GET /quota` alias or document usage/quota divergence.
5. Add Go `GET /runs/{run_id}/lifecycle` route parity.
6. Add Python SDK smoke against compiled Go server.
7. Add live Postgres release evidence build/verify tests gated by `A1_POSTGRES_TEST_DSN`.
8. Add Postgres API-key secret hash persistence tests.
9. Add RLS tenant isolation tests for quota/audit/artifact/worker tables.
10. Add migration checksum/version ledger.
11. Add quota ledger entries for audit-log and release evidence reads if commercially billable.
12. Add Rust verifier fixture coverage for Go release evidence packets.
13. Add release evidence JSON schema fixture under A1 tests.
14. Add audit-log pagination/cursor and exact action/API-key/request-id filters.
15. Add per-route auth matrix tests for missing/wrong/revoked/scopeless keys.
16. Add official read-only usage/quota/error-shape probe when hosted endpoints expose them.
17. Prepare quota-gated paid text mutation calibration with zero retries.
18. Expand paid media calibration one modality at a time: image, audio, file, video.
19. Add Terraform/self-host validation to A1 gate.
20. Convert A1 worklog/evidence entries into stricter release packet format with independent verifier result.

Post-handoff verification addendum:
- `go test ./...` in `tests/integration/go` -> passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 319 tests.
- `npm install` in `packages/ts/ashr-clone` repaired the local clean-worktree TypeScript toolchain; no package metadata changed.
- `npm test` in `packages/ts/ashr-clone` -> passed, 316 tests.
- `docker compose -f services/runner/docker-compose.a1.yml config` -> passed.
- `docker compose -f infra/docker/docker-compose.self-host.yml config` -> passed.
- `python -B tests/a1/ts_python_parity_matrix.py --check` -> passed.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_ts_python_gap_matrix.py tests/a1/test_saas_sdk_client.py -q -p no:cacheprovider` -> passed, 20 tests.
- `go test ./...` at repository root -> expected setup failure because repo root is not a Go module; reran in `packages/go/ashrclone` and passed.
- `wsl.exe -d Ubuntu-24.04-Ashr -e /bin/bash -lc 'pwd; uname -a; echo bash-ok'` -> passed; D-drive Ubuntu WSL2 distro is available for future rounds.
- `ASHR_API_KEY` is present in the process environment by length check only; no key value was read or written.

## 2026-07-09 - A1 route/scope manifest, evidence scanner, and SQL tenant isolation hardening

Round goal:
- Continue the large SaaS A1 bus after pushing PR #27 head `10de02d`.
- Push a multi-lane backend slice instead of a narrow runner-only change: Go API route/scope manifest, TS/Python client consumption, public evidence leak scanner, and SQL tenant isolation hardening.
- Keep all official API material env-only/private; no desktop key file was read and no raw private refs were staged.

Parallel growth points advanced:
1. Go route/scope manifest exposed through `/openapi.json` and `/v1/openapi.json` with `manifest_schema_version=ashr.clone.go_route_scope_manifest.v1`.
2. Go route metadata now includes method, path, route, operation, category, auth_required, scopes, and public_safe fields.
3. Go manifest keeps legacy `routes` compatibility while adding structured `route_manifest` and scope projection.
4. Go tests assert deterministic route ordering, no fixture IDs, public-safe metadata, and route-to-scope mappings.
5. Python SDK SaaS layer added hosted route scope requirements and public-safe Go manifest consumption helpers.
6. TS SDK SaaS layer added matching route scope requirements and Go manifest consumption helpers.
7. TS added route-scope manifest tests and rejects private path consumption.
8. Public route parity snapshot was refreshed so `audit-log` is shared by Python and TS instead of TS-only.
9. A1 route contract tests now validate structured Go route/scope metadata and Python consumption assertions.
10. Public evidence scanner added tracked-only scanning through `git ls-files`.
11. Scanner detects raw key-looking values, bearer/header assignments, private key blocks, and raw-payload-included markers.
12. Scanner explicitly excludes ignored `docs/evidence/private_refs/**` from public artifact checks.
13. Historical public evidence prose with synthetic token-looking literals was redacted.
14. SQL migration added `a1_current_organization_id()` based on `app.a1_organization_id` session setting.
15. SQL migration enables and forces RLS across the A1 SaaS foundation tables.
16. SQL migration adds replay-tolerant organization isolation policies for every declared table.
17. DB migrator tests parse the migration and verify RLS/session-policy coverage for all declared tables.
18. TS/Python parity matrix regenerated after route-scope consumption APIs landed.
19. D-drive Ubuntu WSL2 remains available for future Bash/Linux validation.
20. PR #27 CL after push showed Plan/hygiene pass, Go/Python pending on GitHub runner queue, and A3/TS/Rust skipped by selective plan at the time of snapshot.

Changed files in this round:
- `packages/go/ashrclone/server.go`
- `packages/go/ashrclone/server_test.go`
- `packages/sdk/ashr_clone/saas.py`
- `packages/sdk/ashr_clone/evidence.py`
- `packages/ts/ashr-clone/src/saas.ts`
- `packages/ts/ashr-clone/test/route-scope-manifest.test.mjs`
- `services/api/migrations/001_a1_large_saas_foundation.sql`
- `tests/a1/test_go_python_route_contract_evidence.py`
- `tests/a1/test_evidence_index.py`
- `tests/a1/test_db_migrator.py`
- `tests/a1/docs/a1/ts_python_gap_matrix.json`
- `docs/a1/evidence/go_python_ts_route_parity_snapshot.json`
- `docs/a1/evidence/commands.md`
- `docs/a1/evidence/round11_growth_auditor.md`

Validation / command results:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> passed, 10 tests.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_evidence_index.py tests/a1/test_db_migrator.py -q -p no:cacheprovider` -> passed, 38 tests.
- `npm test` in `packages/ts/ashr-clone` -> passed, 318 tests.
- `python -B tests/a1/ts_python_parity_matrix.py --write` refreshed the TS/Python gap matrix.
- `python -B tests/a1/ts_python_parity_matrix.py --check` -> passed.
- `python -B -m pytest tests/a1/test_ts_python_gap_matrix.py tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> passed, 11 tests.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` initially failed only because the generated TS/Python matrix was stale; after refresh the targeted gap test passed. Full suite still needs rerun before commit.

Real API / private evidence:
- `ASHR_API_KEY` remains available by environment presence/length checks only.
- No desktop key file was read, and no raw key or private hosted payload was written to code, docs, public evidence, or git diff.
- This implementation slice did not make new official API calls; next API calibration should use a dry-run plan, small read-only/private evidence capture, then redacted summary regeneration.

Next 20 A1 growth points:
1. Rerun full A1 suite after matrix refresh and scanner additions.
2. Run Docker compose A1/self-host config checks after SQL/RLS migration changes.
3. Add Go `/v1/projects/{project_id}/quota` alias or converge Python/TS quota naming.
4. Add Go `/runs/{run_id}/lifecycle` route parity or explicitly mark unsupported in route manifest.
5. Add Go `/release-gate` route or route-manifest intentional gap for TS release gate.
6. Add generated OpenAPI document from the route/scope manifest instead of static TS path mirrors.
7. Add Python SDK smoke against compiled Go server for all route/scope manifest entries.
8. Add TS SDK smoke against compiled Go server route/scope manifest entries.
9. Add live Postgres RLS tests gated by `A1_POSTGRES_TEST_DSN`.
10. Add migration checksum/version ledger and CI validation.
11. Add SQL usage rollup views for route/scope categories and billable units.
12. Add Go usage rollup worker for audit/evidence/trace/artifact operations.
13. Add MinIO/S3/R2 artifact storage abstraction and manifest hash binding.
14. Add Terraform skeleton validation for DB/object store/secret manager/service identity.
15. Add Docker healthcheck smoke using the Go route/scope manifest.
16. Add Rust verifier CLI that validates release evidence packet hashes independent of Go/Python/TS.
17. Add official API read-only field drift detector into private evidence + public summary.
18. Prepare quota-gated paid text calibration with zero retries and redacted public summary.
19. Add media modality calibration evidence for image/audio/file/video with equal priority to text.
20. Keep A2/A3 files out of A1 commits unless explicitly unblocking CL.

Post-validation addendum:
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 325 tests after TS/Python gap matrix refresh.
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `docker compose -f services/runner/docker-compose.a1.yml config` -> passed from repo root.
- `docker compose -f infra/docker/docker-compose.self-host.yml config` -> passed from repo root.
- `python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider` -> passed, 17 tests.
- `git diff --check` -> passed.
- Misrun note: `go test ./...` at repo root and repo-relative Docker/Python commands from `tests/integration/go` failed because those cwd values are not module/repo roots; each was rerun from the correct directory and passed.

Lifecycle route-scope audit fix:
- Bus-Auditor found `GET /v1/projects/{project_id}/runs/{run_id}/lifecycle` was shared by Python/TS hosted clients but absent from the new route-scope requirement maps.
- Added lifecycle to Python and TS hosted route scope requirements with `run:read`.
- Added a test that every Python/TS shared hosted route is declared in the route-scope manifest.
- Re-ran `python -B tests/a1/ts_python_parity_matrix.py --write` after the route-scope API changed.
- Validation: `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_ts_python_gap_matrix.py -q -p no:cacheprovider` -> passed, 12 tests.
- Validation: `npm test --prefix packages/ts/ashr-clone` -> passed, 318 tests.
- Validation: `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 326 tests.

## Round24 A1 lifecycle/quota parity, route drift hardening, and real API read-only calibration - 2026-07-09

Baseline / peer changes:
- Repo root: `C:/Users/33516/Documents/Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; push target remains `origin/codex/a1-local-sdk-runner` for PR #27.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` completed. PR #27 CL was green before this slice; A3 checks skipped by plan.
- Peer changes observed on A2/A3 branches and open PR #28, with no A1-owned file impact in this slice. A2/A3 files stay out of this commit.
- `docs/strategy/large-saas-a1-a2-a3-full-plan.md` was read at round start; current strategy still pushes A1 toward Go API gateway/worker, TS SDK/CLI parity, Python calibration/tooling, SQL/PLpgSQL tenant/RLS, Docker/YAML/Terraform infra, and Rust verifier/security later.

Implemented A1 growth points:
1. Go hosted API now exposes `GET /v1/projects/{project_id}/runs/{run_id}/lifecycle` with `run:lifecycle:read` scope.
2. Go hosted API now exposes `GET /v1/projects/{project_id}/quota` as the quota/usage read alias.
3. Go memory backend returns run lifecycle state without requiring Postgres.
4. Go Postgres repository can read lifecycle and tenant/project-bound run status.
5. Go hosted client `LifecycleHTTP` accepts optional auth-key options.
6. Go server tests cover lifecycle and quota alias behavior.
7. Python hosted route scope map includes shared quota route coverage.
8. TS hosted route scope map and OpenAPI exposure include shared quota route coverage.
9. Python route manifest validation now requires explicit unsupported-Go gap records for Go routes not consumed by hosted SDKs.
10. TS route manifest validation now rejects missing or stale unsupported-Go gap records.
11. Python and TS tests assert shared hosted routes cannot drift out of scope coverage silently.
12. Public Go/Python/TS route parity snapshot was refreshed.
13. TS/Python parity gap matrix was regenerated and checked after route-scope API changes.
14. Python calibrator now supports `summarize-private-manifest` for public-safe summaries of ignored private API manifests.
15. Python calibrator now supports `write-readiness-packet` for dry-run public readiness artifacts.
16. Public readiness packet records next read-only calibration targets and guardrails without raw key material.
17. Public official API summary was regenerated from a real read-only private manifest.
18. SQL/RLS migration manifest hook declares required tables, key columns, indexes, RLS force/enable state, policies, and helper functions.
19. Migration manifest tests verify the A1 large-SaaS foundation SQL shape without requiring a live DB.
20. WSL `Ubuntu-24.04-Ashr` and Docker daemon availability were checked and recorded for future Linux/self-host validation.

Real API / private evidence:
- `ASHR_API_KEY` was confirmed by environment presence only; raw values were never printed, stored in tracked files, or read from desktop key files.
- Read-only small batch command: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_official_api_readonly_20260709_155325.json`.
- Result: status `ok`, 5 read steps, 0 mutating steps, 0 errors, estimated 7 calls.
- Private raw evidence path: `docs/evidence/private_refs/a1_official_api_readonly_20260709_155325.json` (ignored, not staged).
- Public summary path: `docs/a1/evidence/official_api_readonly_manifest_summary.json`.
- Public readiness path: `docs/a1/api_calibration/official_api_readiness_packet.json`.

Validation:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `npm test --prefix packages/ts/ashr-clone` -> passed, 321 tests.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 336 tests.
- Focused Python route/calibrator/migration/parity suite -> passed, 54 tests.
- `python -B tests/a1/ts_python_parity_matrix.py --check` -> passed.
- `python scripts/cl_guard.py hygiene` -> passed.
- `git diff --check` -> passed with CRLF normalization warnings only.

Failures / notes:
- One attempted `summarize-private-manifest --input-manifest ...` command used a stale flag name and failed before reading or writing data. It was rerun correctly with `--input` and passed.
- `command -v go` inside WSL returned empty in this quick check, while Python 3 was present. Future Go-on-Linux validation should install or expose Go in `Ubuntu-24.04-Ashr` if required.
- Live Postgres migration tests remain gated by `A1_POSTGRES_TEST_DSN` / `A1_PSQL_BIN` and are not required by default.

Next 20 A1 growth points:
1. Install/validate Go inside `Ubuntu-24.04-Ashr` and run Go tests under WSL for Linux parity.
2. Add Docker Compose smoke that boots Go API plus Postgres and runs route-scope health checks.
3. Add live Postgres RLS validation with a local disposable container and `A1_POSTGRES_TEST_DSN`.
4. Add Go API key lifecycle endpoints matching TS/Python SaaS capability surface.
5. Add Go trace ingestion endpoint with media-safe envelopes for text/audio/file/image/video equally.
6. Add Go artifact upload/download manifest service with hash binding.
7. Add Go worker lease/heartbeat/dead-letter routes to match TS local control-plane parity.
8. Add Go release evidence verification route or explicit planned gap with owner/action.
9. Generate an OpenAPI artifact from the Go route-scope manifest and consume it in TS tests.
10. Add TS generated client smoke from the OpenAPI artifact.
11. Add Python generated client or route smoke against the same OpenAPI artifact.
12. Promote official API read-only calibration into a repeatable public summary index merge without leaking private payloads.
13. Prepare quota-gated text-only mutating official API calibration with dry-run plan, reviewed gate, and private output.
14. Add paid media calibration gates for image/audio/file/video after text mutation proves safe.
15. Add quota ledger rollup SQL view and Go repository method.
16. Add audit-chain tail verification across Go/Python/TS fixtures.
17. Add Terraform/HCL skeleton for Postgres/object storage/secret manager with static validation.
18. Add Rust verifier CLI for release evidence packet hashes and bind it into CI when touched.
19. Add self-host startup README that uses WSL/Docker paths and fresh setup commands.
20. Keep A1 commits scoped to A1-owned dirs and continue monitoring peer A2/A3 PRs without staging them.

Growth-Auditor follow-up:
- Auditor found lifecycle scope drift: Go required `run:lifecycle:read` while Python/TS still declared `run:read`.
- Fixed by aligning Python and TS hosted route scope requirements to `run:lifecycle:read`.
- Added `test_shared_go_python_hosted_routes_have_matching_scope_values` so shared Go/Python hosted route scope values cannot drift silently again.
- Auditor found stale README language saying the public official API summary was `missing`; updated README to match the real read-only private manifest summary (`status=ok`, 5 reads, 7 estimated calls, 0 errors).

## Round25 WSL self-host Go readiness kickoff - 2026-07-09

Baseline continuation:
- PR #27 head `ad194e48ca58aef640a4420368ca9bbf9e8017f4` has Plan/hygiene, Go, Python, and TS checks passing; A3/Rust are skipped by plan; CL summary remains queued on GitHub with no failure logs.
- Worktree was clean at round start. Peer PR #28 remains A3-owned; no A1 impact staged.

Main-thread self-host progress:
- Verified `Ubuntu-24.04-Ashr` starts from WSL and enters the current repo path.
- Installed Go in WSL via apt, resulting in `go version go1.22.2 linux/amd64`.
- Ran `go test ./...` from `/mnt/c/Users/33516/Documents/Ashr_a1_clean_rebase/packages/go/ashrclone` under WSL; result passed.
- This closes the previous WSL rough edge where Bash was available but Go was not, and gives A1 a Linux/self-host validation lane for the Go backend.

Parallel workers launched:
1. Worker-GoRuntime: Go route/runtime/OpenAPI/usage evidence slice under `packages/go/ashrclone`.
2. Worker-SQLQuota: SQL/RLS quota ledger/rollup manifest slice under `services/api/migrations`, `docs/a1/schemas`, and tests.
3. Worker-TSParity: TS SDK quickstart/client parity slice under `packages/ts/ashr-clone`.
4. Worker-APIEvidence: official API evidence workflow guard/index slice under Python SDK/evidence docs.

Next integration checkpoint:
- Wait for worker outputs, resolve conflicts, rerun Go/TS/Python/SQL focused tests, then full A1/CL hygiene before commit.

Round25 integrated results:
- Go runtime added `route_scope_docs` under the OpenAPI payload for usage/quota, lifecycle, and audit route families, including public plan-limit references for graded scenarios, observations, voice minutes, and projects.
- SQL foundation added quota meter dimensions (`runs`, `observations`, `media`, `voice_minutes`, `projects`, `storage_bytes`), `usage_rollups`, tenant/project-scoped idempotency references, rollup trigger contracts, and quota-policy audit trigger contracts.
- TS quickstart parity now reports dataset/run/submit-facing summary data, expected-vs-actual, tool calls, replay availability, and optional hosted SDK submission metadata; wrong expected tool calls now fail grading.
- API evidence readiness packet now emits `private_manifest_summary` and `private_manifest_claim_guard`, preventing public docs from claiming missing private evidence when the public-safe summary says it is present.
- WSL/Linux self-host lane now has Go installed and Go package tests passing under Ubuntu.

Round25 validation:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `npm test --prefix packages/ts/ashr-clone` -> passed, 322 tests.
- SQL/self-host focused pytest -> passed, 18 tests; 2 live DB tests skipped by env gate.
- `python -B tests/a1/ts_python_parity_matrix.py --write` refreshed the matrix after TS export growth.
- `python -B tests/a1/ts_python_parity_matrix.py --check` -> passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 340 tests.
- Docker compose configs for A1 and self-host -> passed.
- `python scripts/cl_guard.py hygiene` -> passed with zero findings.
- `git diff --check` -> passed with CRLF warnings only.

Round25 next 20 A1 growth points:
1. Run live Postgres migration/RLS tests with a disposable Docker Postgres and `A1_POSTGRES_TEST_DSN`.
2. Promote Go `route_scope_docs` into a generated JSON artifact consumed by TS/Python parity tests.
3. Add runtime quota enforcement in Go backed by SQL `usage_rollups`.
4. Add Go API key lifecycle routes to match TS/Python commercial control plane coverage.
5. Add Go trace ingestion route support for equal text/audio/file/image/video envelopes.
6. Add Go artifact storage abstraction with hash-bound manifest persistence.
7. Add Go worker job lease/heartbeat/dead-letter parity to the hosted HTTP surface if still incomplete.
8. Add OpenAPI diff guard that fails when route scopes change without TS/Python updates.
9. Wire TS quickstart hosted submitter to SaaSIngestionClient in a dependency-safe package split.
10. Add TS VM stream replay frames to quickstart summary instead of `vm_stream_count: 0`.
11. Add Python quickstart parity summary matching the new TS dataset/run/submit/tool-call shape.
12. Add official API read-only batch index merge for repeated private manifests.
13. Prepare quota-gated text-only mutating official API calibration with explicit gate record.
14. Add equal paid-media calibration plans for image/audio/file/video after text mutation proves safe.
15. Add Terraform skeleton validation for Postgres/object store/secret manager/service identity.
16. Add Rust verifier CLI for release-evidence packet hashes and audit-chain tail.
17. Add self-host Makefile or PowerShell entrypoint that boots compose and runs health checks.
18. Add customer-facing route/scope/plan-limit proof note under docs/a1.
19. Add staging guard test that fails if `docs/evidence/private_refs` ever appears in staged paths.
20. Keep A2/A3 peer branches monitored, but do not stage their files unless unblocking CL by explicit instruction.

## Round26 route docs, quota enforcement, live Postgres, mutating media calibration - 2026-07-09

Baseline and peer changes:
- Worktree: `C:\Users\33516\Documents\Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; push target remains PR #27 branch `codex/a1-local-sdk-runner`.
- Fetched all remote heads and tags. Peer movement observed: `origin/codex/a3-commercial-growth-round4` advanced and `origin/dev/g3-a2-calibration` advanced. No A2/A3 files were staged for this A1 commit.
- PR #27 remains open against `main`; PR #28 remains A3-owned.

Parallel workers and integration:
- Worker-RouteArtifact created checked-in public `docs/a1/evidence/go_route_scope_docs.json`, schema `docs/a1/schemas/go_route_scope_docs.schema.json`, Go artifact drift/public-safety tests, and Python evidence checks.
- Worker-GoQuota added in-memory Go quota enforcement for `sdk.submit`, `run.upload`, `trace.ingest`, and `artifact.manifest`, including idempotency replay and tenant/project scoping tests.
- Worker-TSPythonConsumption added Python and TypeScript consumers for legacy snapshots, Go OpenAPI `paths`, and future artifact wrappers carrying `route_scope_docs`.
- Main thread integrated worker outputs, removed public artifact wording that looked like raw request payload capture, and closed all workers.

Implemented this round:
- Promoted Go route scope docs into a public-safe artifact and JSON schema that TS/Python can consume without invoking Go.
- Added route-family and plan-limit validation in Python and TypeScript for `usage_quota`, `run_lifecycle`, and `audit` families.
- Added Go runtime quota enforcement aligned to SaaS writes and protected idempotent replay from double metering.
- Fixed live Postgres test helper so Docker-container `psql` supports `check=False`, then proved migration/helper/idempotency behavior in a disposable `postgres:16-alpine` container.
- Renamed the live migration period check constraint to avoid duplicate constraint-name collisions in real Postgres.
- Removed UTF-8 BOMs from the SQL migration and live integration test after Growth-Auditor flagged Linux/psql portability risk.
- Ran real official API calibration using env-only `ASHR_API_KEY`: read-only small batch succeeded, then mutating all-modality and per-media small batches reached official `create_request` boundaries and returned quota-blocked partial manifests.
- Added public-safe mutating evidence index at `docs/a1/evidence/official_api_mutating_calibration_index.json`, covering text/image/audio/file/video without raw payloads or key material.
- Added Python test coverage for the public mutating index.

Official API evidence:
- Read-only private manifest: `docs/evidence/private_refs/a1_official_api_readonly_20260709_172042.json` (`status=ok`, 5 read steps, 0 errors, 0 mutating steps, estimated 7 calls).
- Mutating dry-run plan: `docs/evidence/private_refs/a1_official_api_mutating_all_modalities_dryrun_20260709_172241.json` (`status=planned`, 5 mutating modalities, estimated 17 calls).
- Mutating all-modality private manifest: `docs/evidence/private_refs/a1_official_api_mutating_all_modalities_20260709_172259.json` (`status=partial`, `create-request-text`, `quota_block_count=1`).
- Per-media private manifests: `a1_official_api_mutating_image_20260709_172407.json`, `a1_official_api_mutating_audio_20260709_172414.json`, `a1_official_api_mutating_file_20260709_172421.json`, and `a1_official_api_mutating_video_20260709_172428.json`; each reached one official mutating attempt and recorded quota-blocked partial status.
- Public summaries: `docs/a1/evidence/official_api_readonly_manifest_summary.json`, `docs/a1/api_calibration/official_api_readiness_packet.json`, and `docs/a1/evidence/official_api_mutating_calibration_index.json`.
- Raw private manifests and quota gates remain ignored under `docs/evidence/private_refs/`; no raw key values were printed, stored in tracked files, or staged.

Validation:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `npm test --prefix packages/ts/ashr-clone` -> passed, 325 tests.
- `python -B tests/a1/ts_python_parity_matrix.py --write` and `--check` -> passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 347 tests.
- `python -B -m pytest tests/a1/test_python_calibrator.py tests/integration/test_a1_large_saas_migration.py tests/a1/test_a1_foundation_migration_manifest.py -q -p no:cacheprovider` -> passed, 50 tests.
- Disposable Docker Postgres live proof with `A1_POSTGRES_TEST_DSN=docker://ashr-a1-live-pg` and `A1_PSQL_DOCKER_CONTAINER=ashr-a1-live-pg` -> passed, 2 tests.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet` and `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet` -> passed.
- `python scripts/cl_guard.py hygiene` -> passed with zero findings.
- `git diff --check` -> no whitespace errors; CRLF normalization warnings only.
- WSL `Ubuntu-24.04-Ashr` and Docker daemon verified usable: Bash, Go 1.22.2, Python 3.12.3, Docker server 29.6.1.

Growth-Auditor follow-up:
- Auditor said evidence was pushable if scoped precisely, but P1 risks remained: live Postgres proof must be attached, BOMs should be removed, Go quota is still in-memory only, SQL operation-to-meter mapping is not durable, and TS/Python route consumption is validation rather than generated-client replacement.
- Main thread resolved the live proof and BOM P1s in this round. Remaining P1s are durable SQL quota enforcement, operation-to-meter mapping, generated SDK route maps, and structured live migration assertions.

Round26 next 20 A1 growth points:
1. Wire Go quota enforcement to durable Postgres `quota_policies`, `usage_ledger`, and `usage_rollups`.
2. Add SQL operation-to-meter mapping for `sdk.submit -> runs`, `trace.ingest -> observations`, `run.upload -> media/voice_minutes`, and `artifact.manifest -> storage_bytes`.
3. Add transactional SQL quota check plus ledger insert to prevent concurrent overspend.
4. Add Go repository interfaces for quota policy read, usage append, and rollup readback.
5. Add Postgres-backed Go service mode parallel to `MemoryService`.
6. Add SQL hard-vs-soft quota policy tests and audit events for denied quota decisions.
7. Add idempotency-aware SQL usage inserts so replays do not double-bill.
8. Replace live migration stdout substring checks with structured JSON assertions.
9. Add CI service-container job for live Postgres migration proof.
10. Generate OpenAPI directly from Go route manifest and publish route docs hash.
11. Generate Python/TS route-scope maps from the Go/OpenAPI artifact instead of hand-maintained maps.
12. Add Go HTTP quota-exceeded tests for submit/upload/trace/artifact endpoints.
13. Add shared public-safe quota error schema across Go, TS, and Python.
14. Add official API quota/error fixture normalization from the new mutating partial manifests.
15. Add per-modality paid media calibration retry policy that stops on first quota block but indexes response keys.
16. Add API-key lifecycle official calibration plan and protected gate for create/revoke/verify/list.
17. Add artifact manifest durable storage proof through Go API -> SQL -> SDK readback.
18. Add trace ingestion durable storage proof through Go API -> SQL -> SDK readback.
19. Add billing-grade invoice/export mock from usage rollups.
20. Add A1 push gate script that runs Go, Python A1, TS package, compose, and optional live Docker proof with pass/skip matrix.

## Round27 durable quota catalog + SDK evidence consumption - 2026-07-09

Baseline:
- Repo remains `C:\Users\33516\Documents\Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; push target remains PR #27 branch `codex/a1-local-sdk-runner`.
- `gh pr checks 27` still showed Plan/hygiene queued for run `29008613785` at baseline, with no failure logs or steps.
- Remote `origin/codex/a3-commercial-growth-round4` advanced again; A3 files were not staged.

Implemented this round:
- SQL durable quota grew from ledger-only proof to DB-native enforcement primitives: `operation_meter_mapping`, `current_quota_policy`, `check_quota_and_insert_usage`, advisory transaction lock, idempotency replay, and `quota.denied` audit event insertion.
- `usage_ledger` now has an `operation` column and operation-period index so billing/debugging can distinguish SDK submit, trace ingest, artifact storage, and worker lifecycle operations.
- Go added `quota.go` with operation catalog, canonical meter mapping, repository interfaces, and append event contracts.
- Go public quota errors now expose `code`, `operation`, canonical `meter`, `unit`, `limit`, `used`, `requested`, `remaining`, and public message for API/SDK consumers.
- Go Postgres repository gained quota usage append/readback readiness; MemoryService uses the same operation catalog.
- Python and TypeScript SDKs now consume `official_api_mutating_calibration_index.json` via public-safe loaders and reject private evidence paths.
- Added `docs/a1/schemas/official_api_mutating_calibration_index.schema.json` so official mutating text/image/audio/file/video evidence is schema-bound.
- Growth-Auditor flagged SQL/Go meter vocabulary drift as P1. Main thread fixed it immediately: Go now uses SQL canonical meters (`runs`, `media`, `observations`, `storage_bytes`) and unknown operations no longer silently become meters.
- Added cross-file static test that parses SQL `operation_meter_mapping` and Go `quota.go` so billing meter vocabulary cannot drift silently again.

Official API evidence:
- Refreshed read-only official API small batch with env-only `ASHR_API_KEY`: `docs/evidence/private_refs/a1_official_api_readonly_20260709_175938.json`, status `ok`, 5 read steps, 0 errors, estimated 7 calls.
- Regenerated public-safe summary `docs/a1/evidence/official_api_readonly_manifest_summary.json` and readiness packet `docs/a1/api_calibration/official_api_readiness_packet.json`.
- Existing mutating paid-media evidence remains represented by `docs/a1/evidence/official_api_mutating_calibration_index.json`; Python/TS now consume it as SDK contract.

Validation:
- `python -B -m pytest tests/a1/test_python_calibrator.py -q -p no:cacheprovider` -> passed, 40 tests.
- `npm run build --prefix packages/ts/ashr-clone` -> passed.
- `node --test packages/ts/ashr-clone/test/route-scope-manifest.test.mjs` -> passed, 10 tests.
- Focused SQL/schema/Python evidence suite -> passed, 82 tests before meter fix; focused migration manifest after meter fix -> passed, 10 tests.
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- Disposable Docker Postgres live migration proof -> passed, 2 tests.
- `npm test --prefix packages/ts/ashr-clone` -> passed, 327 tests.
- `python -B tests/a1/ts_python_parity_matrix.py --write` and `--check` -> passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> passed, 354 tests.
- Docker compose configs passed; `python scripts/cl_guard.py hygiene` passed with zero findings; `git diff --check` only produced CRLF normalization warnings.

Growth-Auditor follow-up:
- Resolved this round: SQL/Go meter vocabulary drift, untracked schema/Go quota files noted for commit inclusion.
- Still open P1: Go Postgres repository does not yet call `check_quota_and_insert_usage`; durable mutating paths are not proven end-to-end; live Postgres does not yet assert allowed/denied/idempotent quota function behavior; official mutating evidence freshness/digest/provenance is not enforced by SDK loaders.

Round27 next 20 A1 growth points:
1. Wire Go Postgres mutating paths to SQL `check_quota_and_insert_usage`.
2. Implement `PostgresRepository.ConfigureUsageQuota` against `quota_policies`.
3. Add live Postgres tests for allowed quota usage insert.
4. Add live Postgres tests for hard quota denial and `quota.denied` audit insertion.
5. Add live Postgres tests for idempotent replay with same idempotency key.
6. Add conflict guard for reused idempotency key with different operation/quantity/request digest.
7. Add concurrency contention test with two transactions racing the same quota policy.
8. Add durable end-to-end path: API key auth -> mutating operation -> SQL usage ledger -> quota denial -> audit log -> customer-safe 429.
9. Add OpenAPI schema components for quota policy and quota error responses.
10. Add admin API route for quota policy create/update/revoke.
11. Add Python typed quota error object and parser.
12. Add TS typed quota error object and parser.
13. Add usage rollup reconciliation test from raw `usage_ledger` to `usage_rollups` to Go `UsageSnapshot`.
14. Require nonzero artifact byte quantity when storage quota enforcement is enabled.
15. Add official mutating evidence digest fields to the public index.
16. Add freshness window validation for official mutating evidence loaders.
17. Add release-gate rule that blocks stale/missing official mutating evidence by modality.
18. Add billing export artifact from usage rollups.
19. Add self-host push gate script wrapping Go/TS/Python/compose/live Postgres optional checks.
20. Keep monitoring A2/A3 branches but stage only A1-owned files.


## Round28 durable quota runtime wiring + paid media mutating proof - 2026-07-09T10:33:59Z

Baseline:
- Repo: `C:\Users\33516\Documents\Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; PR #27 target branch `codex/a1-local-sdk-runner`.
- Fetched remote refs; peer change observed on `origin/dev/g3-a2-calibration`; no A2/A3 files staged.
- PR #27 CL Gate run `29010797860` completed green. A3 checks were skipped by CL rules, not failing.

Implemented:
- Wired Go Postgres quota paths toward commercial SQL quota enforcement. `ConfigureUsageQuota` now persists quota policy into SaaS `quota_policies` when the commercial schema exists, otherwise falls back to lightweight `ashr_usage_quota_policies` for fresh local setup.
- `appendPostgresUsageEvent` now first attempts the durable SaaS `check_quota_and_insert_usage` path for UUID tenant/project IDs, maps SQL denial to Go `QuotaExceededError`, then falls back to local quota policy plus `ashr_quota_ledger` when the SaaS migration is absent.
- Added local Postgres quota policy schema and Go static wiring test for the 12-argument `check_quota_and_insert_usage` signature.
- Fixed SQL PLpgSQL ambiguity in `check_quota_and_insert_usage` by qualifying `quota_policies.meter`.
- Added live Docker Postgres proof for allowed usage, idempotent replay without double insert, quota-denied response, and `quota.denied` audit payload.
- Updated public official mutating calibration index to include the new paid-media real attempt while keeping raw payloads and private response data under ignored private evidence.

Official API evidence:
- Real paid media mutating request was attempted with env-only `ASHR_API_KEY`, `--allow-mutate`, `--allow-media-generation`, and `--allow-non-text-inputs`.
- Dry-run/plan evidence: `docs/evidence/private_refs/a1_api_media_paid_plan_20260709_182610.json`, status `blocked`.
- Real private evidence: `docs/evidence/private_refs/a1_api_media_paid_real_20260709_182610.json`, `function=create_request`, `status=error`, `status_code=200`, `attempts=1`, duration about 2969ms.
- Public-safe observed result: official request quota blocked the write path with counters `limit=5`, `used=5`, `requested=1`, `remaining=0`. No raw response body or key material was copied to public files.
- Public index updated: `docs/a1/evidence/official_api_mutating_calibration_index.json` remains public-safe and now accepts real `error` quota records in addition to older `partial` quota-blocked manifests.

Validation:
- `go test ./...` from `packages/go/ashrclone` -> pass.
- Disposable Docker Postgres live migration: `python -B -m pytest tests/integration/test_a1_large_saas_migration_live.py -q -p no:cacheprovider` -> `3 passed`.
- `go test ./...` from `tests/integration/go` -> pass.
- `npm test --prefix packages/ts/ashr-clone` -> `327 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `354 passed`.
- Focused official mutating schema/SDK tests -> `3 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet` -> pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet` -> pass.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> no errors; one CRLF normalization warning for the public mutating index JSON.

Environment notes:
- Docker daemon is usable and successfully ran `postgres:16-alpine` for live proof.
- Windows `bash.exe` currently resolves to WSL/WindowsApps and failed with `/bin/bash` missing in this shell; Git Bash exists, but Codex `apply_patch` was not visible inside it. This did not block implementation or tests.

Growth-Auditor result:
- Auditor confirmed the main P1 was durable quota runtime wiring plus live proof. This round closes the practical Go/Postgres quota gate and live allowed/replay/deny/audit proof.
- Remaining next P1/P2 growth: successful official mutating response after request quota reset/plan change, Go HTTP route for quota policy/readback, RLS tenant isolation live proof, generated OpenAPI route map, and invoice-ready usage rollup exports.

Next 20 A1 growth points:
1. Add Go HTTP endpoints for quota policy create/read and usage rollup readback.
2. Add live Postgres RLS proof for tenant A/B isolation across usage/audit/quota tables.
3. Add API key lifecycle durability in Postgres: hashed storage, revoke, scope denial, last-used, and audit.
4. Add no-side-effect-after-quota-denial test for submit/upload/trace/artifact mutations.
5. Add SQL usage rollup materialized view for invoice-ready runs/media/observations/storage.
6. Add Go webhook delivery table and worker lifecycle for release/usage events.
7. Add OpenAPI route generation from Go route manifest.
8. Generate Python/TS clients from OpenAPI for quota and usage routes.
9. Add TS parity for new quota HTTP routes immediately after Go route addition.
10. Add Python SDK quota policy submit/read helpers.
11. Add official API successful text mutation probe once request quota is reset or plan upgraded.
12. Add official paid image/audio/file/video probes after a successful text mutation baseline.
13. Add private evidence digest/freshness checks for official mutating manifests.
14. Add public evidence packet for durable quota live Postgres proof.
15. Add CI optional live Postgres service job guarded by env flag.
16. Add self-host Docker compose profile for Go API plus Postgres plus worker.
17. Add Terraform/HCL skeleton for managed Postgres plus worker service.
18. Add Rust verifier hook for signed evidence bundle verification.
19. Add Go artifact service durable storage readback and signed manifest hash.
20. Add release gate integration that consumes durable usage/quota denial evidence.


## Round29 usage quota route parity + paid media quota boundary - 2026-07-09T10:50:14Z

Baseline:
- Repo: `C:\Users\33516\Documents\Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; PR #27 head branch remains `codex/a1-local-sdk-runner`.
- Fetched all remote branches and tags. PR #27 previous CL Gate run `29012107574` was green; A3/Rust jobs skipped by rule.
- Peer movement noted from prior auditor on `origin/codex/a3-commercial-growth-round4`; no A2/A3 files staged.

Implemented:
- Added Go HTTP quota policy routes `POST /v1/projects/{project_id}/usage/quotas` and `POST /v1/projects/{project_id}/quota/limits`, routed through the existing usage read scope and `ConfigureUsageQuota`.
- Updated Go route manifest and route scope docs so usage/quota readback and quota configuration appear in one `usage_quota` family.
- Updated Python and TypeScript hosted route-scope requirements and validators for the new quota configure routes.
- Added Go HTTP test proving quota configure route blocks a future mutation with `429 quota_exceeded` and preserves usage readback.
- Regenerated Go route-scope docs and Go/Python/TS route parity evidence snapshots.

Official API evidence:
- Environment check observed an API key only by presence/length; no secret value was printed or stored.
- Ran all-modality paid-media dry-run plan for text/image/audio/file/video; private dry-run: `docs/evidence/private_refs/a1_paid_media_all_modalities_dry_run_20260709_185014.json`; planned 17 estimated calls and 5 mutating modality steps.
- Ran real small-batch paid-media mutating calibration with explicit audited quota override; private record: `docs/evidence/private_refs/a1_paid_media_all_modalities_real_20260709_185014.json`.
- Real execution completed 5 read steps and hit the official quota boundary at first text `create_request`; result `partial`, `quota_block_count=1`, `status_code=200`, error kind `api`, quota remaining present.
- Public-safe summary written to `docs/a1/evidence/official_api_paid_media_summary_20260709_185014.json`; index updated in `docs/a1/evidence/official_api_mutating_calibration_index.json`. No raw payloads, auth header values, request parameter values, or key material are present in public evidence.

Validation:
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `go test ./...` from `tests/integration/go` -> pass.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> `20 passed`.
- `npm test --prefix packages/ts/ashr-clone` -> `327 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `354 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet` -> pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet` -> pass.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> no whitespace errors; JSON line-ending normalization warnings only.

Growth-Auditor follow-up:
- P0 remains durable Postgres API key lifecycle plus protected Go HTTP auth/quota path.
- Next commercial slice should implement durable hashed API keys, Postgres-backed preflight/rate-limit snapshot, restart durability proof, and route-level quota denial/readback/audit evidence.
- P1 remains live RLS negative proof for tenant A/B isolation and official successful mutating evidence once hosted quota resets or plan changes.


## Round30 durable Postgres API key lifecycle and preflight - 2026-07-09T11:06:30Z

Baseline:
- PR #27 commit `985f400` CL Gate completed green: Plan/hygiene, Go, Python, TS, and summary passed; A3/Rust jobs skipped by rule.
- Growth-Auditor reviewed the commercial blockers and called out Postgres API key lifecycle, Postgres-backed preflight/rate-limit snapshot, route-level submit preflight, bearer-secret future parity, RLS live negative proof, and successful official mutation after quota reset.
- No A2/A3 files were staged or modified for this slice.

Implemented:
- Replaced Go `PostgresRepository` API key placeholders with durable create/list/revoke/verify/preflight/rate-limit/snapshot methods.
- API keys are generated as one-time local test secrets, persisted only as hashes plus prefixes, and returned through existing redacted `APIKeyRecord` envelopes.
- UUID tenant/project/key IDs use the commercial `api_keys` table from `services/api` migration when present; non-UUID local handles use a new durable `ashr_api_keys` fallback table so local Go HTTP tests keep working without raw secrets.
- Added durable `ashr_api_key_rate_limits` table and rate-limit consumption path. Mutating Postgres usage writes now update API key rate-limit counters and `last_used_at`, and reject overspend with public-safe `QuotaExceededError`.
- `sdk-submit` Go HTTP route now runs server-level scope preflight before mutation while intentionally avoiding pre-mutation quota consumption so idempotent replays are not blocked or double-billed.
- Added Go static contract tests preventing `notImplemented` regressions and pinning the submit preflight semantics.

Validation:
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `go test ./...` from `tests/integration/go` -> pass.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> `20 passed`.
- `npm test --prefix packages/ts/ashr-clone` -> `327 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `354 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet` -> pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet` -> pass.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> pass.

Official API evidence:
- No new official mutating call was made in this sub-slice because Round29 already used the env-only key and proved the current hosted quota boundary at the first text write. Repeating paid media writes while quota is exhausted would only create duplicate failed evidence.
- Next official API action remains: after quota reset or plan change, run a successful text mutation baseline, then image/audio/file/video paid media one modality at a time.

Next 20 A1 growth points:
1. Add live Docker Postgres proof for API key create/list/verify/revoke/preflight/rate-limit restart durability.
2. Add Go HTTP server against Postgres live proof for protected submit, quota denial, usage readback, and audit readback.
3. Add bearer auth scheme to Go HTTP without weakening current raw-secret rejection in local handle mode.
4. Add TS/Python hosted client parity for bearer auth once Go route contract lands.
5. Add RLS live negative proof for `api_keys`, `usage_ledger`, `quota_policies`, and `audit_log` under tenant A/B session settings.
6. Add no-side-effect-after-denial tests for submit, upload, trace ingest, artifact manifest, and worker enqueue.
7. Add concurrency test for simultaneous submit requests against the same quota policy.
8. Add OpenAPI auth scheme and API key/rate-limit schemas generated from Go route manifest.
9. Generate TS/Python API clients from the OpenAPI artifact for key and quota routes.
10. Add SQL audit trigger or explicit audit event for API key revoke and rate-limit configure.
11. Add usage rollup reconciliation from rate-limit usage to invoice-ready meter rows.
12. Add self-host compose profile running Go API against Postgres repository, not memory service.
13. Add migration test for the local fallback `ashr_api_keys` table and commercial `api_keys` parity.
14. Add Go webhook delivery table/worker for key revoked/quota denied/release events.
15. Add CLI command to bootstrap tenant/project/key and print one-time secret only once.
16. Add evidence packet for durable auth/quota proof with no raw secrets.
17. Add official readonly usage/quota endpoint probe if the hosted product exposes it.
18. Add successful official mutating text baseline after quota reset.
19. Add paid image/audio/file/video probes after text success, one modality per audited batch.
20. Keep PR #27 draft until live Postgres HTTP/auth/quota evidence is present.


## Round31 live Postgres API key proof - 2026-07-09T11:22:10Z

Baseline:
- Started from clean worktree after commit `4a68408b`; PR #27 CL Gate run `29014318715` completed green across Plan/hygiene, Go, Python, TypeScript, and summary. A3/Rust checks were skipped by rule.
- Targeted Growth-Auditor P1: static durable API key implementation needed live Postgres proof.

Implemented:
- Added opt-in Go integration test `TestPostgresAPIKeyLifecycleLiveOptIn` under `tests/integration/go` gated by `A1_POSTGRES_TEST_DSN`.
- The live test migrates a fresh Postgres repository, bootstraps tenant/project/dataset, creates a durable API key, lists redacted keys, verifies the one-time secret by hash, checks scope denial, configures a normalized `sdk_submit`/`sdk.submit` rate limit, submits a run, proves rate-limit denial after one mutation, reads snapshot usage, revokes the key, and proves revoked preflight denial.
- Fixed API key rate-limit normalization so public route operation `sdk_submit` and durable mutation operation `sdk.submit` share the same Postgres counter.
- Fixed local durable key fallback consumption so non-UUID key handles do not attempt UUID casts against the commercial `api_keys` table inside an active transaction.

Live evidence:
- Disposable Docker Postgres command started `postgres:16-alpine` on local port `55433` and set `A1_POSTGRES_TEST_DSN=postgres://ashr:ashr@localhost:55433/ashr?sslmode=disable` for the test process only.
- `go test ./... -run TestPostgresAPIKeyLifecycleLiveOptIn -count=1 -v` from `tests/integration/go` -> pass.
- Container was removed after the test. No secrets or private official API payloads were involved.

Validation:
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `go test ./...` from `tests/integration/go` -> pass.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> `20 passed`.
- `npm test --prefix packages/ts/ashr-clone -- --test-name-pattern "route|Go OpenAPI|route_scope"` -> `327 passed` because the current Node test runner still executes all package tests with this invocation.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `354 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet` -> pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet` -> pass.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> pass.

Known command note:
- `go test ./...` from repo root is not a valid entrypoint because this repository contains multiple Go modules and no root `go.mod`; it reports `directory prefix . does not contain main module`. Correct Go validation is module-scoped.

Next 20 A1 growth points:
1. Add Go HTTP live test against Postgres repository, not just repository methods.
2. Add bearer auth route contract with hashed secret verification and TS/Python parity.
3. Add no-side-effect-after-denial proof for submit/upload/trace/artifact/worker routes.
4. Add RLS tenant A/B live negative proof for `api_keys`, `usage_ledger`, `quota_policies`, and `audit_log`.
5. Add restart durability proof that opens a second Postgres repository after key creation and still verifies/snapshots/revokes.
6. Add explicit audit event for API key revoke and rate-limit configure.
7. Add rate-limit concurrency test for simultaneous submit attempts.
8. Add HTTP usage readback proving API key limit and usage quota denial share public-safe schema.
9. Add OpenAPI bearer auth scheme and generated key/quota schemas.
10. Add TS hosted client methods for Go key/rate-limit routes if missing.
11. Add Python hosted client methods for Go key/rate-limit routes if missing.
12. Add self-host compose profile running Go API plus Postgres and a smoke command.
13. Add Terraform/HCL service skeleton for Go API plus managed Postgres.
14. Add billing export from usage/rate-limit counters.
15. Add webhook event for `api_key.revoked` and `quota.denied`.
16. Add private evidence digest builder for live Postgres proof.
17. Add release-gate blocker when durable auth proof is stale.
18. Re-run official mutating text once quota resets.
19. Run paid image/audio/file/video after successful text baseline.
20. Keep monitoring peer branches and avoid A2/A3 staging.


## Round32 live Postgres HTTP API key proof - 2026-07-09T11:33:20Z

Implemented:
- Extended the opt-in Go live Postgres test to start `httptest.NewServer(ashrclone.NewHTTPHandler(repository))` over a real migrated Postgres repository.
- The HTTP live test now proves `POST /bootstrap`, API key create/verify/rate-limit routes, protected `sdk-submit`, `429 quota_exceeded` response schema after one submit, and revoke route all work through the Go HTTP boundary backed by Postgres.

Live evidence:
- Disposable Docker Postgres command started `postgres:16-alpine` on local port `55434`; `A1_POSTGRES_TEST_DSN` was set only for the test process.
- `go test ./... -run 'TestPostgres.*LiveOptIn' -count=1 -v` from `tests/integration/go` -> both repository and HTTP live tests passed.

Validation:
- `go test ./...` from `tests/integration/go` without DSN -> pass with live tests skipped.
- Next before push: rerun Go package, Python A1, TS, compose, hygiene, and diff checks.

## Round33 bearer auth and admin API-key hardening - 2026-07-09T20:10:00+08:00

Baseline:
- Started from clean A1 worktree `C:\Users\33516\Documents\Ashr_a1_clean_rebase` on `codex/a1-local-sdk-runner-clean`, tracking PR #27 head `f69bc667` before this round.
- `gh pr checks 27 --watch=false`: CL Gate summary, Go SDK/integration, Python A1/A2 contracts, TypeScript SDK parity, and Plan/hygiene passed; A3/Rust skipped by path rules.
- Peer updates observed on `origin/codex/a3-commercial-growth-round4` and `origin/dev/g3-a2-calibration`; no A2/A3 files changed or staged in this worktree.
- Docker Desktop daemon is usable (`docker version` returned client/server 29.6.1). `wsl -l -v` showed `docker-desktop` and `Ubuntu-24.04-Ashr` installed but stopped; direct Codex `/bin/bash` execution failed earlier in this round, so PowerShell remained the command shell.
- Growth-Auditor read-only audit identified admin API-key route truthfulness as the highest-value next commercial hardening slice.
- TS worker implemented Bearer secret support in `packages/ts/ashr-clone` and reported `npm test -- --runInBand` -> 328 passed plus Python parity subset -> 12 passed.

Implemented:
- Go HTTP now accepts standard `Authorization bearer header <one-time-secret>` for protected routes while continuing to reject raw `api_key` material in JSON bodies.
- Bearer-only requests infer local generated key IDs from the one-time secret prefix, verify the stored hash, enforce route scope, and then run quota preflight before mutation.
- API-key admin routes now require admin/read/preflight scopes after the first bootstrap admin key. The first unauthenticated API-key create is allowed only when the project has no keys and requested scopes include `api_key:write`.
- Added Go scopes `api_key:write`, `api_key:read`, and `api_key:preflight`.
- Added Go unit tests for Bearer submit, usage readback, invalid Authorization, key mismatch, wrong-scope denial, first-admin bootstrap, and admin-protected rate-limit/preflight paths.
- Extended live Postgres HTTP proof to cover Bearer-only submit, quota denial, usage readback showing no extra side effect, admin Bearer rate-limit/revoke, and revoked Bearer denial.
- TypeScript SDK now supports `bearerApiKey` / `apiKeySecret` for protected HTTP route calls and keeps raw secret material out of request bodies.

Validation:
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `go test ./...` from `tests/integration/go` without `A1_POSTGRES_TEST_DSN` -> pass.
- Disposable Docker Postgres live proof on `127.0.0.1:55435`: `go test ./... -run 'TestPostgres.*LiveOptIn' -count=1 -v` from `tests/integration/go` -> pass.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> 20 passed.
- `npm test --prefix packages/ts/ashr-clone` -> 328 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> 354 passed.

Official API calibration:
- No new hosted mutating/paid media call was made in this sub-slice because Round29 already proved the current hosted quota boundary with env-only key at first text mutation. Next useful official action remains a successful text mutation baseline after quota reset/plan change, then image/audio/file/video paid probes in audited batches.

Commercial agenda raised this round:
1. Stripe test mode to live mode billing slice.
2. GitHub OAuth and Google OAuth login.
3. Real API key create/revoke/rate-limit/usage ledger hardening.
4. Postgres persistence for real org/project/user/session.
5. Object storage for real report/evidence bundles.
6. Long-running worker daemon for real run/trace/artifact processing.

Next 20 A1 growth points:
1. Add admin-auth route manifest parity to Go OpenAPI and public route scope docs.
2. Add Python hosted client Bearer secret support matching TS.
3. Add CLI bootstrap command that prints first admin one-time secret only once.
4. Add no-side-effect-after-denial proofs for upload, trace ingest, artifact manifest, and worker enqueue.
5. Add restart durability proof: create admin key, close repo, reopen repo, verify/list/revoke.
6. Add concurrent rate-limit race proof against Postgres.
7. Add RLS tenant A/B negative proof for `api_keys`, `usage_ledger`, `quota_policies`, and `audit_log`.
8. Add audit events for API key create/revoke/rate-limit configure and quota denied.
9. Add audit-chain verification over auth/quota events.
10. Add self-host compose profile running Go API plus Postgres plus worker daemon.
11. Add object storage abstraction and filesystem/S3-compatible test double for evidence bundles.
12. Add Go worker daemon lease loop with graceful shutdown and heartbeat.
13. Add Postgres user/session tables and OAuth identity placeholders without real provider secrets.
14. Add GitHub OAuth callback skeleton with state/nonce/session persistence.
15. Add Google OAuth callback skeleton with state/nonce/session persistence.
16. Add Stripe test-mode billing ledger schema and webhook verifier skeleton.
17. Add live-mode guardrails so live billing requires explicit env and dry-run plan.
18. Add official API successful text mutation baseline after quota reset/plan update.
19. Add paid image/audio/file/video calibration, one modality per audited batch after text success.
20. Add release evidence bundle storage/readback path wired to quota/audit.


## Round34 Python Bearer/object storage/billing readiness - 2026-07-09T12:40:07Z

Baseline and peer impact:
- Worktree: `C:/Users/33516/Documents/Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; push target remains PR #27 branch `codex/a1-local-sdk-runner`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` observed remote A3 update `codex/a3-commercial-growth-round4` only; no peer files were staged or modified by A1.
- `gh pr checks 27 --watch=false` for prior head `bac5eca3` was green: CL Gate summary, Go SDK/integration, Python A1/A2, TypeScript SDK parity, Plan/hygiene passed; A3/Rust skipped by rule.
- Growth-Auditor read-only review confirmed current A1 diff aligns with Python Bearer parity and object evidence storage first; billing is acceptable only as A1 backend contract/test-mode readiness, not live payment activation.

Implemented:
- Python SaaS SDK hosted Bearer parity: `api_key_secret` / `bearer_api_key` options send `Authorization bearer header ...` through HTTP headers only, reject ambiguous options, reject Bearer options in local mode, and keep raw `api_key=` body material blocked.
- A1 platform object storage now records and verifies public-safe release evidence bundles with packet hash, object key, storage URI, redaction flags, and tenant/project/run checks.
- Added provider-neutral billing contract module for hosted Stripe Checkout/Billing Portal and hosted WeChat Pay/Alipay plans. It supports test/live modes, live-mode ack guardrails, `secret_ref` indirection, webhook envelope hash verification, provider manifest, and raw card/raw secret rejection.
- Exported billing contract APIs from `services.api` without adding A3 UI or touching real payment providers.

Official/payment calibration:
- Consulted current official docs for Stripe API keys/authentication, Stripe payment method support for Checkout/Alipay/WeChat Pay, WeChat Pay Native `/v3/pay/transactions/native`, and Alipay trade APIs.
- No Stripe/WeChat/Alipay provider API call was made; this round intentionally stays plan-only because real payment onboarding, account verification, webhook endpoint setup, and any real-card/live charge require explicit human-controlled provider actions.
- No Ashr official mutating call was repeated in this sub-slice; previous private evidence already records a quota boundary on first text mutation, so this round avoided duplicate failed paid/media attempts.

Validation:
- `python -B -m pytest tests/a1/test_billing_provider_contract.py tests/a1/test_saas_sdk_client.py tests/a1/test_saas_platform.py tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider` -> `47 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `365 passed`.
- `npm test --prefix packages/ts/ashr-clone` -> `328 passed`.
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `go test ./...` from `tests/integration/go` -> pass.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> pass after trimming `services/api/__init__.py` EOF whitespace.
- A mistaken `go test ./...` from repository root failed with the known multi-module error `directory prefix . does not contain main module`; reran the two Go modules directly and both passed.

Next 20 A1 growth points:
1. Add billing ledger table/schema slice for checkout-created, invoice-paid, refund, cancellation, and usage meter reconciliation.
2. Add billing webhook idempotency store with duplicate provider event replay tests.
3. Add Stripe test-mode executor behind explicit env-only provider credentials, still defaulting to dry-run.
4. Add WeChat Pay API v3 request signer contract and fake-signature verifier tests.
5. Add Alipay request signer contract and fake-signature verifier tests.
6. Add Go billing API routes for plan checkout, portal plan, webhook ingest, and ledger readback.
7. Add Postgres RLS tests for billing accounts/provider events/ledger rows tenant isolation.
8. Add OpenAPI billing schemas and scope manifest entries for `billing:read`, `billing:write`, `billing:webhook`.
9. Add TS billing client parity for the Python billing contract.
10. Add CLI `ashr billing plan-checkout` dry-run command with public-safe output.
11. Add object storage backing for signed billing evidence bundle attachments.
12. Add worker job for provider webhook normalization into usage/billing ledger.
13. Add quota-to-invoice rollup proof from existing usage ledger snapshots.
14. Add tenant/project/customer lifecycle mapping with customer refs and provider account refs.
15. Add official Ashr API read-only usage/quota calibration if exposed in dashboard/API.
16. After Ashr quota reset or plan change, rerun one successful official text mutation baseline, then paid image/audio/file/video one modality at a time.
17. Add OAuth/session schema slice for GitHub/Google identity linking without secrets.
18. Add Docker compose service profile with API, Postgres, Redis/Valkey, MinIO, and worker.
19. Add Terraform/HCL skeleton for Postgres/object storage/secret refs, no real credentials.
20. Add release evidence packet link from billing ledger to run/release audit chain.


## Round35 billing ledger/idempotency and TS parity - 2026-07-09T13:01:14Z

Baseline and peer impact:
- Worktree: `C:/Users/33516/Documents/Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; PR #27 head before this round was `2fec1b74`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` observed A2 branch `origin/dev/g3-a2-calibration` advance; no A2/A3 files were modified or staged by A1.
- PR #27 check run for prior head remained queued at baseline (`Plan and hygiene` queued), so local validation stayed authoritative for this slice.
- Growth-Auditor approved the next slice as billing ledger + provider webhook idempotency + TS parity, with a strict no-live-payment/no-card/no-provider-secret boundary.

Implemented:
- Extended Python `services.api.billing` with append-only `BillingLedger`, `BillingLedgerEvent`, provider webhook replay/idempotency store, tenant/project-scoped billing accounts, usage-rollup reconciliation, and public-safe billing evidence snapshot.
- Provider webhook ingest now accepts only verified hash-only envelopes, records exactly one ledger mutation for a new provider event, returns duplicate without mutation for replay, and returns conflict without mutation when the same provider event id arrives with a different payload hash.
- Added public-safe A1 billing replay fixture `docs/a1/evidence/billing_replay_fixture_round35.json` proving accepted/duplicate replay, ledger totals, usage reconciliation, and evidence hash without raw provider payloads or secret values.
- Added TypeScript billing parity module `packages/ts/ashr-clone/src/billing.ts` and barrel export. It mirrors checkout/portal plans, Stripe/WeChat/Alipay provider normalization, live-mode guardrails, webhook envelope verification, ledger idempotency, usage reconciliation, and evidence snapshots.
- Added TS billing parity tests and refreshed `tests/a1/docs/a1/ts_python_gap_matrix.json` from the generator.
- Cleaned public evidence wording to avoid token-shaped bearer examples and unsafe secret-ref names in tracked docs/fixtures.

Official API calibration:
- Ran env-only official Ashr API small-batch read-only calibration with `ASHR_API_KEY` from environment only. Private raw record: `docs/evidence/private_refs/a1_readonly_round35_20260709_210008.json` (ignored). Public-safe summary: `docs/a1/evidence/official_api_readonly_round35_summary_20260709_210008.json`.
- Summary status: `ok`; 5 read steps succeeded; response keys included init/keep_alive/list-style fields; quota block count 0; no mutating or paid media step in this slice.
- Real payment provider execution was not run. Stripe/WeChat/Alipay remain contract/test-mode readiness only until human-owned provider onboarding, webhook endpoint setup, and explicit live payment execution plan exist.

Validation:
- `python -B -m pytest tests/a1/test_billing_provider_contract.py -q -p no:cacheprovider` -> `10 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `368 passed`.
- `npm test --prefix packages/ts/ashr-clone` -> `334 passed`.
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `go test ./...` from `tests/integration/go` -> pass.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> pass.
- Known command hygiene: two accidental root-relative/mislocated commands failed (`npm test --prefix ...` from Go module, `go test ./...` from repo root, and `python scripts/cl_guard.py hygiene` from Go integration dir). Correct module/root commands were rerun and passed.

Next 20 A1 growth points:
1. Add Postgres billing tables for billing accounts, provider events, and immutable ledger rows.
2. Add RLS tenant A/B negative proof for billing tables.
3. Add Go billing route contract for checkout plan, portal plan, webhook ingest, ledger readback.
4. Add OpenAPI billing schemas and scopes `billing:read`, `billing:write`, `billing:webhook`.
5. Add TS/Python clients for hosted billing routes once Go route contract is pinned.
6. Add worker normalizer from provider event store to ledger with retry/dead-letter semantics.
7. Add object-store sealed billing evidence bundle linked to release evidence packet.
8. Add quota-to-invoice rollup reconciliation against existing usage ledger snapshots.
9. Add refund/cancel out-of-order webhook tests.
10. Add provider event stale timestamp and signature-shape tests using fake fixtures.
11. Add WeChat Pay API v3 request signer contract with no real private key.
12. Add Alipay request signer contract with no real private key.
13. Add Stripe test-mode executor dry-run plan with explicit env-only credential probe, no charge creation.
14. Add CLI `ashr billing plan-checkout` and `ashr billing ledger` dry-run/readback commands.
15. Add Terraform/HCL skeleton for billing secret refs and webhook endpoint config, no values.
16. Add Docker compose MinIO/R2-compatible object store profile for evidence and billing artifacts.
17. Add Go self-host worker daemon linked to Postgres and object storage.
18. Add official Ashr mutating text baseline after quota reset or plan change, then paid image/audio/file/video one modality at a time.
19. Add GitHub/Google OAuth user/session schema slice with state/nonce storage and no client secrets.
20. Add commercial evidence report tying release gate, billing ledger, usage, and audit chain for enterprise review.


## Round36 durable billing ledger migration - 2026-07-09T13:16:57Z

Baseline and peer impact:
- Started after PR #27 head `f8ee9564` was pushed. GitHub CL Gate for that head passed Plan/hygiene, Go SDK/integration, Python A1/A2, and TypeScript SDK parity; summary was queued at the first check and then expected to settle.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` observed A3 branch `origin/codex/a3-commercial-growth-round4` advance; no A2/A3 files were modified or staged by A1.
- Local C: drive reached 0 bytes free during this slice. Reclaimed only regenerateable project/tool caches (`node_modules`, `dist`, `__pycache__`, `.pytest_cache`, npm logs). No source, evidence, private refs, or project-external important data was deleted.

Implemented:
- Added `services/api/migrations/002_a1_billing_ledger.sql`, a durable Postgres migration for A1 billing accounts, provider webhook replay/idempotency rows, immutable billing ledger rows, RLS policies, indexes, and helper functions.
- Added `docs/a1/schemas/a1_billing_ledger_migration_manifest.json` documenting the migration contract, supported providers/modes/currencies/events, replay semantics, and public-safety posture.
- Added `tests/a1/test_billing_ledger_migration_manifest.py` to statically verify table order, required columns/indexes/constraints, forced RLS, provider event duplicate/conflict function fragments, ledger summary fragments, and absence of raw provider payload/secret/card columns.

Commercial value:
- Moves billing from in-memory SDK contract toward a real SaaS backend substrate: tenant-scoped billing accounts, replay-safe provider event ingestion, append-only revenue/usage ledger, and SQL-level secret/payload guardrails.
- Still does not execute real payment providers or handle card data. Live payment remains blocked until provider onboarding, endpoint setup, and human-confirmed live execution plan exist.

Validation:
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py -q -p no:cacheprovider` -> `5 passed`.
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py tests/a1/test_billing_provider_contract.py tests/a1/test_evidence_index.py::test_tracked_a1_public_evidence_artifacts_are_secret_safe -q -p no:cacheprovider` -> `16 passed`.
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py tests/a1/test_billing_provider_contract.py -q -p no:cacheprovider` -> `15 passed` after local cache cleanup.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> pass.
- TS full local rerun was not possible after local cache cleanup because C: had only a few MB free and reinstalling `packages/ts/ashr-clone/node_modules` failed with `ENOSPC`. This slice does not modify TS files; PR #27 previous head TS CI was green and GitHub CI should remain the authoritative TS validation for pushed SQL/Python-only changes.

Next 20 A1 growth points:
1. Add live Postgres opt-in test applying migrations 001+002 and exercising `ingest_billing_provider_event` duplicate/conflict paths.
2. Add RLS live tenant A/B negative proof for `billing_accounts`, `billing_provider_events`, and `billing_ledger_events`.
3. Add Go repository methods for billing account upsert, provider event ingest, and ledger summary using migration 002.
4. Add Go HTTP routes for billing checkout plan, portal plan, webhook ingest, and ledger readback.
5. Add OpenAPI schemas/scopes for `billing:read`, `billing:write`, and `billing:webhook`.
6. Add Python hosted SDK methods for billing routes once route contract lands.
7. Add TS hosted client billing route wrappers after Go OpenAPI pin.
8. Add worker daemon step that normalizes provider webhook rows into ledger rows with retry/dead-letter semantics.
9. Add billing ledger evidence bundle object storage linkage.
10. Add release evidence packet reference to billing evidence snapshot hash.
11. Add refund/cancel out-of-order SQL tests.
12. Add stale timestamp and signature-shape provider event guardrails.
13. Add WeChat Pay API v3 signer contract using fake private-key ref only.
14. Add Alipay signer contract using fake app-private-key ref only.
15. Add Stripe test-mode executor dry-run plan and explicit env-only credential presence probe.
16. Add CLI billing dry-run/readback commands.
17. Add Terraform/HCL billing secret refs/webhook endpoint skeleton.
18. Move local TS dependency/cache strategy to D: or a junction so C: ENOSPC stops blocking local full TS validation.
19. Add official Ashr read-only calibration comparison against dashboard/usage copy if exposed.
20. After Ashr quota reset or plan change, run successful text mutation then paid media probes one modality at a time.


## Round37 billing migration live opt-in harness - 2026-07-09T13:25:51Z

Baseline:
- PR #27 head `91213fc8` completed green on GitHub: CL Gate summary, Plan/hygiene, Go SDK/integration, Python A1/A2 contracts, and TypeScript SDK parity passed; A3/Rust skipped by path rules.
- Local TS dependency install recovered after C: space returned to about 1.7GB; `npm_config_cache` used `D:/codex-cache/npm`.

Implemented:
- Added `tests/integration/test_a1_billing_ledger_migration_live.py`, an opt-in live Postgres test for migration 002.
- The test reuses the existing `A1_POSTGRES_TEST_DSN` / `A1_PSQL_DOCKER_CONTAINER` helper pattern, applies migrations 001+002 idempotently, seeds org/workspace/project/billing account rows, calls `ingest_billing_provider_event`, and asserts accepted/duplicate/conflict replay plus summary output.

Validation:
- `python -B -m pytest tests/integration/test_a1_billing_ledger_migration_live.py -q -p no:cacheprovider` -> `1 skipped` without DSN, as designed.
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py tests/integration/test_a1_billing_ledger_migration_live.py -q -p no:cacheprovider` -> `5 passed, 1 skipped`.
- `npm test --prefix packages/ts/ashr-clone -- --test-name-pattern billing` -> command still executes the full package suite under Node test runner; `334 passed`.
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `python scripts/cl_guard.py hygiene` from repo root -> pass, zero findings.
- `git diff --check` -> pass.
- Docker daemon check via `docker version --format ...` hung for over 60 seconds and was stopped; no Docker data was modified. Therefore the live Postgres proof remains opt-in and was not executed locally this round.

Next 20 A1 growth points:
1. Run the new billing migration live test against disposable Postgres once Docker responds or DSN is provided.
2. Add RLS live tenant A/B negative proof for billing tables.
3. Add Go Postgres repository methods for migration 002 billing ingest/readback.
4. Add Go HTTP billing routes and route manifest scopes.
5. Add OpenAPI schemas for billing route contracts.
6. Add Python hosted SDK methods for billing routes.
7. Add TS hosted SDK methods for billing routes.
8. Add billing webhook worker normalization loop with retries/dead-letter.
9. Add object storage bundle for billing evidence snapshots.
10. Link billing evidence hash into release evidence packet.
11. Add SQL stale timestamp/signature-shape guardrails.
12. Add out-of-order refund/cancel SQL tests.
13. Add WeChat fake signer contract.
14. Add Alipay fake signer contract.
15. Add Stripe test-mode credential presence probe without provider call.
16. Add CLI billing dry-run/readback commands.
17. Add Terraform/HCL billing secret ref skeleton.
18. Add self-host compose hook applying migrations 001+002.
19. Add official Ashr dashboard/API usage quota read-only comparison if exposed.
20. After Ashr quota reset/plan change, execute successful text mutation then paid media probes one modality at a time.

## Round 38 - billing route contract + payment provider readiness (2026-07-09)

Baseline and peer impact:
- Repo: `C:/Users/33516/Documents/Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; PR #27 remained draft and latest pre-round CI was green.
- Ran `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`, `git status -sb`, `gh pr list --state all --limit 20`, and `gh pr checks 27 --watch=false`.
- Peer PRs observed: A2 PR #29 draft, A3 PR #28 open. No A2/A3 files were intentionally modified.
- Growth-Auditor Hooke recommended Go/OpenAPI billing route contract for checkout plan, portal plan, webhook ingest, and ledger readback.

Implemented:
- Go billing route contract in `packages/go/ashrclone`: scopes `billing:read`, `billing:write`, `billing:webhook`; deterministic checkout/portal/webhook/ledger DTOs; memory-service behavior; HTTP routes; route manifest/scope-doc runtime coverage; Postgres backend compile-safe contract fallback.
- Python SaaS client route constants and wrappers for `billing_checkout_plan`, `billing_portal_plan`, `billing_webhook_ingest`, and `billing_ledger` using existing public-safe `services.api.billing` contracts.
- TypeScript SaaS parity: billing scopes, hosted/local billing wrappers, TS OpenAPI billing paths, Python-canonical `usage_snapshot`/`lifecycle_snapshot` envelopes.
- Public-safe payment provider readiness packet covering Stripe test/live hosted checkout/portal, hosted WeChat Pay/Alipay, real-card human-controlled test boundary, secret-reference policy, webhook hash envelopes, and evidence object path classification.
- Route parity snapshot and TS/Python gap matrix refreshed for billing routes and wrappers.
- Docker daemon smoke now skips on daemon probe timeout instead of failing the whole A1 suite when Docker Desktop/WSL networking is unhealthy.

Validation:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `npm test --prefix packages/ts/ashr-clone` -> 335 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> 378 passed, 1 skipped (Docker daemon probe timeout skip).
- Focused Python billing/route/payment tests -> 51 passed.
- Official Ashr API read-only calibration: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_readonly_billing_route_round38_20260709_215947.json` -> status ok, 5 read steps, 0 mutating steps.

Evidence:
- Public readiness: `docs/a1/payment_provider_readiness.md`, `docs/a1/evidence/payment_provider_readiness_public.json`, `docs/a1/schemas/payment_provider_readiness.schema.json`.
- Public official summary: `docs/a1/evidence/official_api_readonly_round38_summary_20260709_215947.json`.
- Private raw API record stayed under ignored `docs/evidence/private_refs/a1_readonly_billing_route_round38_20260709_215947.json`.

Known gaps / next 20 growth points:
1. Durable Postgres billing persistence behind migration 002 instead of current Go contract fallback.
2. Transactional billing webhook idempotency in Go/Postgres matching SQL duplicate/conflict semantics.
3. Go HTTP billing auth negative tests for missing/wrong scopes and wrong tenant.
4. TS router local HTTP billing route handling, not only client/OpenAPI wrappers.
5. Python CLI commands for billing plan/webhook/ledger operations.
6. Public-safe live Stripe test-mode dry-run plan that records exact human action boundary.
7. Stripe test webhook signature verification harness using secret references only.
8. WeChat Pay hosted provider adapter contract with cert/key reference schema.
9. Alipay hosted provider adapter contract with app/private-key reference schema.
10. Billing usage-rollup export from Go usage ledger into billing ledger event.
11. Object storage evidence bundle pointer for payment provider event proof.
12. Quota ledger to billing ledger reconciliation tests.
13. Worker job for billing webhook normalization and dead-letter.
14. Terraform/HCL secret-manager references for payment provider credentials.
15. Docker compose service profile for webhook receiver local smoke.
16. OAuth login foundations before live billing admin surfaces.
17. API key create/revoke/limit routes tied to billing scopes and audit events.
18. Official Ashr API small-batch calibration for billing/usage fields if public API exposes them.
19. Paid mutating Ashr API calibration remains planned but must use dry-run plan -> small batch -> bounded batch and never log raw key.
20. A1 push gate should include root-safe command matrix to avoid invalid monorepo `go test ./...` from root.
## Round39 billing provider semantic parity + paid-media API gate - 2026-07-09T14:25:00Z

Baseline:
- Continued on `codex/a1-local-sdk-runner-clean` / PR #27 after prior head `5c4bc83` was green for CL Gate summary, Plan/hygiene, Go, Python, and TypeScript.
- Recovered baseline fetch after C: space exhaustion by removing regenerateable caches only; TS dependencies were restored with npm cache on `D:/codex-cache/npm`.
- Peer branch updates observed: `origin/codex/a3-commercial-growth-round4` and `origin/dev/g3-a2-calibration`; no A2/A3 files were modified this round.
- Frontend mirror archive `C:/Users/33516/Desktop/Ashr_frontend_mirror_20260707_125507.zip` was inspected read-only. Public-safe evidence at `docs/a1/evidence/frontend_mirror_billing_usage_fields_20260709_221430.json` records API key, usage, billing status, and billing portal field markers without raw payloads or tokens.

Implemented:
- Expanded Go billing provider semantics for checkout plan, portal plan, webhook ingest, and ledger readback. Go accepts provider config/customer/price/URL/hash/signature fields and returns public-safe side-effect flags (`provider_called=false`, `real_charge_possible=false`, `raw_payload_included=false`, `secret_value_present=false`).
- Added Python SDK billing parity for richer local and hosted route payloads, including a more tolerant HTTP transport adapter shape for `(method, url, payload)` transports.
- Added shared billing SDK parity fixture and Python/TS tests that pin operation names, routes, wrapper names, required public fields, and forbidden public fragments.
- Added SQL semantic evidence/schema for migration 002 hash/reference-only provider storage, duplicate/conflict replay zero-mutation semantics, and billing ledger/provider event linkage.
- Tightened billing provider contract tests for duplicate/conflict snapshots and public-safe raw-payload/secret/card denial.

Official/API calibration:
- `ASHR_API_KEY` was present in env for this process; only presence/length was observed, raw key was not read or logged.
- Dry-run paid-media plan wrote private ignored evidence `docs/evidence/private_refs/a1_paid_media_mutating_dryrun_round39_20260709_222232.json`: 5 modalities planned, 5 read steps + 5 mutating steps, estimated 17 calls.
- Small-batch paid-media execution wrote private ignored evidence `docs/evidence/private_refs/a1_paid_media_mutating_small_batch_round39_20260709_222232.json`: 5 read steps succeeded; text mutating step returned an API/quota-blocked partial result; non-text paid media did not proceed past quota gate. Public-safe summary at `docs/a1/evidence/official_api_paid_media_round39_summary_20260709_222232.json` records only status, response keys, and quota-block flags.
- Follow-up: do not retry failing paid-media mutation blindly. Next real API growth should first create or verify a quota/usage gate record for the intended modality, then run one modality at a time.

Subagents:
- Worker-GoBillingSemantic implemented Go billing semantic parity in `packages/go/ashrclone` and verified `go test ./...` in that module.
- Worker-TSPythonBillingParity added the shared fixture and Python/TS parity tests; focused tests and package TS tests passed.
- Worker-SQLBillingEvidence added billing SQL semantic evidence/schema and static migration tests; focused tests passed.
- Bus-Auditor approved the direction with cautions: claim provider-backed plan contract, not live payment integration; revalidate TS explicitly; keep public evidence field-readiness only; run secret scan and full validation before commit.

Validation:
- `python -B -m pytest tests/a1/test_billing_sdk_parity.py tests/a1/test_billing_ledger_migration_manifest.py tests/a1/test_payment_provider_readiness_docs.py -q -p no:cacheprovider` -> `17 passed` after transport/test assertion fixes.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `384 passed, 1 skipped`.
- `npm test --prefix packages/ts/ashr-clone` with `npm_config_cache=D:/codex-cache/npm` -> `337 passed`.
- `go test ./...` from `packages/go/ashrclone` -> pass.
- `go test ./...` from `tests/integration/go` -> pass.
- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
- `git diff --check` -> pass; one CRLF normalization warning for an existing touched Python test.
- Targeted secret/payment scan found only intentional guardrail regexes and synthetic test fixtures; no raw Ashr API key, provider key, card, webhook secret, or bearer value was added.

Next 20 A1 growth points:
1. Add Stripe test-mode adapter skeleton behind env-only refs and no-live-charge gate.
2. Add WeChat Pay and Alipay hosted rail signer contracts with fake key refs only.
3. Add quota/usage gate creation/readback path so paid-media official probes can proceed one modality at a time.
4. Add Go Postgres billing repository methods for migration 002 ingest/readback.
5. Add live Postgres migration test for billing RLS and duplicate/conflict replay when Docker/DSN is responsive.
6. Add Stripe webhook signature verifier test with synthetic signatures and hash-only payload storage.
7. Add billing worker daemon that normalizes provider events into ledger events with retry/dead-letter semantics.
8. Add object-storage evidence bundle linkage for billing events and provider request summaries.
9. Add billing CLI commands for checkout plan, portal plan, webhook ingest, and ledger readback.
10. Add TypeScript generated client/OpenAPI schemas for billing DTOs beyond route shells.
11. Add OAuth login skeleton for GitHub/Google sessions without storing provider secrets.
12. Add tenant/project/user/session durable Postgres schema and RLS tests for auth boundary.
13. Add API key create/revoke/rate-limit integration around billing route scopes.
14. Add quota ledger rollup for text/audio/file/image/video as equal first-class resources.
15. Add release evidence packet references to billing SQL and official API summaries.
16. Add Terraform/HCL secret-ref and webhook endpoint skeleton.
17. Add Docker compose profile for API + worker + Postgres + object storage smoke.
18. Add Rust verifier hook for signed billing evidence bundle manifests.
19. Re-run official read-only + one successful mutating text probe after quota gate is available.
20. Only after human-controlled provider setup, add live-mode payment smoke with explicit no-card-data logging proof.

## Round40 commercial billing/control-plane growth - 2026-07-09T14:55:00Z

Baseline:
- Repo: `C:/Users/33516/Documents/Ashr_a1_clean_rebase`; branch `codex/a1-local-sdk-runner-clean`; PR #27 remained green at the start of the round.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` observed peer branch movement on `origin/dev/g3-a2-calibration` and `origin/codex/a3-commercial-growth-round4`; no A2/A3 files were staged or modified by A1.
- `origin/main` is behind the A1 branch; the broad `HEAD..origin/main` deletion-looking diff was branch history shape, not a signal to overwrite A1 files.
- Strategy reread: `docs/strategy/large-saas-a1-a2-a3-full-plan.md` continues to push Go main backend, SQL/Postgres/RLS, TypeScript SDK/OpenAPI, Docker/YAML/Terraform, and Rust verifier follow-up.

20 growth points pursued in parallel:
+1. Go Postgres billing checkout plan persistence.
+2. Go Postgres billing portal plan persistence.
+3. Go Postgres billing webhook ingest wired to migration 002 function shape.
+4. Go Postgres billing ledger readback.
+5. Billing idempotency replay/conflict handling in Go Postgres path.
+6. Python SDK local CLI billing ledger state round-trip.
+7. Python CLI billing checkout/portal/webhook/ledger commands.
+8. TypeScript CLI billing checkout/portal/webhook/ledger commands.
+9. TypeScript billing ledger state persistence.
+10. OpenAPI/route parity retained for billing routes.
+11. Stripe provider rail safety matrix.
+12. WeChat Pay provider rail safety matrix.
+13. Alipay provider rail safety matrix.
+14. Webhook header-shape and secret-ref policy without raw header values.
+15. Live/test boundary ack policy for provider rails.
+16. Self-host compose API + worker + Postgres + object evidence + billing webhook receiver scaffold.
+17. Terraform/HCL self-host secret-ref/object-store/billing webhook variables.
+18. Real API public evidence index refreshed with Round39 paid-media/quota-gate private refs while preserving historical field-map coverage.
+19. Capability matrix, commercial control-plane kit, and TS/Python gap matrix regenerated from current sources.
+20. Public evidence path hygiene fixed so generated API evidence index uses repo-relative private ref paths, not absolute Windows paths.

Subagents:
+- Runtime-GoSQL added SQL-backed Go Postgres billing methods, deterministic UUID/slug/SHA helpers, idempotency hooks, and source-wiring tests; `go test ./...` in `packages/go/ashrclone` passed.
+- SDK-CLI-OpenAPI added Python/TS CLI billing commands, local billing state persistence, TS CLI parity tests, and evidence artifact; focused Python/TS tests passed.
+- ProviderRails upgraded `services/api/billing.py` and payment readiness docs/schema/evidence for Stripe/WeChat/Alipay secret-ref, mode, allowed-method, signature-shape, and live-boundary policies; focused tests passed.
+- Infra-SelfHost expanded compose/Terraform/self-host evidence for API, worker, Postgres, object evidence, billing webhook receiver, quota ledger, artifact manifests, and secret refs; static compose/HCL tests passed.
+- Growth-Auditor gave conditional commit readiness: this is a public-safe billing contract, SDK parity, evidence, and self-host scaffold increment; do not call it live billing, payment-ready, or production self-host.

Official/API calibration:
+- No new paid mutating API retry was run this round because Round39 already produced a quota/API-blocked partial result. Repeating the same blocked mutation without a new quota-gate artifact would be noise, not evidence.
+- The public real API evidence index was regenerated by merging existing public history with current `docs/evidence/private_refs` summaries. It now includes Round39 paid-media dry-run and small-batch private refs, with quota block count preserved and paths repo-relative.
+- Response field map JSON/Markdown were regenerated from the merged evidence index.

Validation:
+- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `399 passed, 1 skipped`.
+- `npm test --prefix packages/ts/ashr-clone` -> `338 passed`.
+- `go test ./...` from `packages/go/ashrclone` -> pass.
+- `go test ./...` from `tests/integration/go` -> pass.
+- `docker compose -f services/runner/docker-compose.a1.yml config --quiet` -> pass.
+- `python scripts/cl_guard.py hygiene` -> pass, zero findings.
+- `git diff --check` -> pass with CRLF normalization warnings only.
+- `tests/a1/test_evidence_index.py::test_tracked_a1_public_evidence_artifacts_are_secret_safe` -> pass.
+- Targeted secret scan found expected synthetic tests/guardrail regexes and no tracked raw Ashr key, provider key, webhook secret, raw card, or bearer value.

Residual risk / not overclaiming:
+- No real Stripe/WeChat/Alipay provider calls were made.
+- No real card/live payment flow was executed.
+- Go Postgres billing live DSN integration was not run; current coverage is unit/source-wiring plus SQL shape and existing migration tests.
+- Compose worker remains a scaffold command, not the final production queue daemon.
+- Terraform remains a provider-neutral self-host contract scaffold, not a complete cloud deploy target.

Next 20 growth points:
+1. Add `A1_POSTGRES_TEST_DSN` integration tests for billing checkout/portal/webhook/ledger.
+2. Prove Postgres idempotent replay and idempotency conflict for billing.
+3. Prove provider event duplicate/conflict behavior against live migration 002 functions.
+4. Add cryptographic Stripe webhook verification behind secret refs.
+5. Add WeChat Pay signature verification adapter behind key refs.
+6. Add Alipay signature verification adapter behind key refs.
+7. Split plan-only billing routes from explicit provider-execute routes with live approval gate.
+8. Add private evidence flow for one Stripe test-mode Checkout object after human/provider setup.
+9. Replace compose worker test loop with a real long-running worker daemon command.
+10. Add worker integration smoke: enqueue, lease, heartbeat, complete, evidence object write.
+11. Add S3-compatible object-store adapter smoke without logging secrets.
+12. Convert Terraform scaffold into one concrete deploy target.
+13. Add migration checksum/version ledger and rollback policy.
+14. Add RLS tenant-isolation live proof for billing/quota/artifacts/audit/worker jobs.
+15. Add backup/restore evidence for Postgres and object evidence store.
+16. Add audit-chain coverage for billing plan creation and webhook ingest.
+17. Generate OpenAPI from Go route manifest as source of truth and regenerate SDK route maps.
+18. Add Python/TS/Go billing payload schema contract tests.
+19. Add enterprise runbook for secrets, ingress, webhook setup, reconciliation, incident response.
+20. Refresh readiness packet with capability maturity states: contracted, scaffolded, integration-tested, live-provider-tested.

## Round43 executable worker/object storage/API calibration - 2026-07-10T00:25:00Z

Baseline:
- Working tree used for this round: `C:/Users/33516/Documents/Ashr_a1_clean_rebase` at `a0453239` on `codex/a1-local-sdk-runner-clean`; push target remains `origin HEAD:codex/a1-local-sdk-runner` for PR #27.
- A stale sibling workspace `C:/Users/33516/Documents/Ashr` was inspected and found at old lone commit `e8310d2f` with `ahead 1, behind 71`; it was not used for staging or push to avoid reintroducing outdated diffs.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` and `gh pr list --state all --limit 20` were run before implementation. Peer branches observed: `origin/dev/g3-a2-calibration` and `origin/codex/a3-commercial-growth-round4`.
- Strategy still points A1 toward Go main backend, SQL/Postgres/RLS, TypeScript/OpenAPI parity, Docker/YAML/Terraform, object storage, worker daemon, quota, billing, and API calibration.

Round43 growth points landed:
1. Added runnable Go worker daemon CLI under `packages/go/ashrclone/cmd/ashr-worker`.
2. Worker daemon reads env aliases for tenant/project/job/lease/timing/request/API-key metadata.
3. Worker daemon emits public-safe JSON summary and never logs raw payloads or secrets.
4. Self-host worker compose now builds and runs a Go runtime image instead of the older Python replay command.
5. Added `infra/docker/Dockerfile.go-runtime` building `ashr-api` and `ashr-worker` binaries.
6. Fixed Go runtime healthcheck to verify real binaries instead of a nonexistent `ashr-api-healthcheck` command.
7. Added local filesystem object storage contract helper with tenant/project/run scoped object keys.
8. Added S3/MinIO-compatible public manifest contract using env refs only, not raw credentials.
9. Wired artifact uploads to object manifests and checksum/readback metadata in `services/api/platform.py`.
10. Wired evidence bundle storage to object manifests and verified release evidence packets before storage.
11. Added object storage tests for scoped keys, tamper detection, redaction, refs-only manifests, and evidence bundle wiring.
12. Added SQL/RLS static migration checks for protected control-plane, usage/audit, jobs/artifacts, and billing tables.
13. Added opt-in live Postgres RLS proof using a scratch `NOBYPASSRLS` role when `A1_POSTGRES_TEST_DSN` is available.
14. Ran official Ashr API read-only small-batch calibration from env key only; no key file was read and no raw key was printed.
15. Wrote private manifest under ignored `docs/evidence/private_refs/a1_readonly_api_round43_20260709_233449.json` and committed only public summary metadata.
16. Refreshed public API evidence index and response field map to include Round43 read-only field observations.
17. Updated readiness packet; mutating small batch remains not ready without a fresh mutation gate.
18. Preserved payment/live-card boundary: no Stripe/WeChat/Alipay live payment or real card operation was attempted in this round.
19. Revalidated commercial self-host compose config after Go daemon wiring.
20. Revalidated CL hygiene/commercial guards and diff check before staging.

Official API evidence:
- Env key presence was checked by the user before this round; this round consumed `ASHR_API_KEY` only through process env.
- Read-only command: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 8 --output docs/evidence/private_refs/a1_readonly_api_round43_20260709_233449.json`.
- Public summary: `docs/a1/evidence/official_api_readonly_round43_summary_20260709_233449.json`.
- Summary result: status `ok`, read steps `5`, mutating steps `0`, quota blocks `0`; observed response keys for `init`, `keep_alive`, `list_agents`, `list_datasets`, and `list_requests`.
- Public evidence index after merge: `400` records, `16` functions, historical quota block count preserved at `48`.

Validation:
- `go test ./...` from `packages/go/ashrclone` -> passed.
- `python -B -m pytest tests/a1/test_local_self_host_smoke_compose.py tests/a1/test_evidence_index.py tests/a1/test_object_storage_contract.py tests/a1/test_saas_platform.py tests/integration/test_a1_large_saas_migration.py tests/integration/test_a1_large_saas_migration_live.py -q -p no:cacheprovider` -> `48 passed, 5 skipped`.
- `docker compose --env-file infra/docker/self-host.env.example -f infra/docker/docker-compose.self-host.yml --profile commercial config --quiet` -> passed.
- `python scripts/cl_guard.py hygiene` -> passed, no findings.
- `python scripts/cl_guard.py commercial` -> passed, no blockers/advisories.
- `git diff --check` -> passed with CRLF normalization warnings only.

Residual risks / next A1 queue:
- Object storage is local-filesystem plus S3/MinIO manifest contract; no live MinIO/S3 network write was run yet.
- Go Postgres worker daemon still needs an end-to-end Postgres-backed lease/heartbeat/complete/dead-letter live smoke.
- Live Stripe/WeChat/Alipay and real card flows require human-managed provider setup and must remain behind test/live-mode gates with secret refs only.
- Next high-ROI slice: Go Postgres worker durability + object-store MinIO compose write/readback + API key quota enforcement around artifact/trace ingestion.

## Round48 trusted payment verification and Human Operator onboarding - 2026-07-10

Baseline and peer state:
- Authoritative worktree: `C:/Users/33516/Documents/Ashr_a1_clean_rebase`.
- Branch: `codex/a1-local-sdk-runner-clean`; committed baseline:
  `9393a8f3 Build China-first payment runtime and fail-closed ingestion`.
- Five modified A2 result fixtures were inspected as CRLF/stat noise and were
  excluded from the A1 commit. No A2 judge or A3 dashboard source was changed.

Round48 delivered:
1. Go payment notification ingestion now fails closed with HTTP `403` and
   `trusted_payment_verification_required`.
2. Caller-provided verification/status fields cannot mutate order or refund
   state.
3. Go internal verification artifacts are HMAC-bound and reject tampering.
4. Python and TypeScript recursively reject forbidden payment data aliases and
   sensitive values.
5. PostgreSQL migration `005` adds immutable verification artifacts, exact
   tenant/project RLS, append-only controls, recursive metadata admission, and
   provider-authoritative order/refund transitions.
6. OAuth account-ready contracts cover GitHub, Google, WeChat, and Alipay with
   exact redirect allowlists, state/nonce hashing, replay protection, issuer,
   audience, and account-binding checks.
7. OAuth providers remain disabled by default and perform no network I/O or
   secret resolution.
8. Human Operator receipt schema and CLI accept only non-sensitive account
   readiness metadata and reject secrets, tokens, authorization codes, payment
   card data, and KYC material.
9. TypeScript parity CI installs and builds the package before executing Node
   tests; the generated Python/TypeScript gap matrix was refreshed.
10. Public evidence documents the cross-layer forbidden payment-data matrix
    and exact account-holder task boundaries.

Truth flags:
- `disabled=true`
- `fail_closed=true`
- `plan_only=true`
- `real_provider_calls=false`
- `real_card_acceptance=false`
- `live_money_activation=false`

Validation:
- Focused Python after final negative-test literal hardening:
  `36 passed`.
- Full A1 Python: `840 passed, 2 skipped`.
- TypeScript after Human Operator CLI parity merge:
  `406 passed, 0 failed`.
- Go package `go test ./...` and `go vet ./...`: passed.
- Go integration `go test ./...` and `go vet ./...`: passed.
- A2 generated fixture check: all `55` generated fixtures match.
- CL hygiene and commercial guards: passed.
- Docker self-host compose config: passed; missing
  `ASHR_POSTGRES_AUTH_SECRET` warning is expected because only a secret
  reference is committed.
- `git diff --check`: passed with known A2/TS-matrix CRLF warnings only.

Failures and restrictions:
- An attempted command referenced nonexistent
  `tests/a1/test_round47_payment_postgres_live.py`; it was not repeated.
  Disposable PostgreSQL 16 migration validation was completed separately.
- Process-local HMAC is experimental evidence only. Production requires
  KMS/Vault-backed key IDs, rotation, revocation, and isolated environments.
- No live provider onboarding, payment, card acceptance, KYC, secret handling,
  or production activation is claimed.

Next queue:
1. Complete account-holder GitHub OAuth setup through the Human Operator flow.
2. Add secret-manager/KMS resolver, rotation, and revocation contracts.
3. Add provider-specific WeChat Pay API v3 and Alipay RSA2 verification
   executors after non-sensitive account readiness receipts exist.
4. Run disposable Postgres `NOBYPASSRLS` payment transition proof in CI.
5. Add transactional order/refund/ledger/quota/audit/outbox persistence.

### Round43 Bus-Auditor blocking fixes - 2026-07-10T00:55:00Z

Bus-Auditor found three blocking issues and all were fixed before commit:
- Worker daemon compose no longer exits after one bounded run and leaves a stale healthy marker. The commercial worker command now re-enters `/usr/local/bin/ashr-worker` in a loop, refreshes `/runtime/worker/heartbeat`, and the healthcheck requires a recent heartbeat file.
- Commercial self-host Postgres no longer uses `POSTGRES_HOST_AUTH_METHOD: trust`. It now uses `POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password` backed by Docker secret `ASHR_POSTGRES_AUTH_SECRET`; `self-host.env.example` contains only the secret ref, not a password value. Local `services/runner/docker-compose.a1.yml` remains a local-dev smoke fixture and is separately tested.
- Webhook deliveries no longer return a reusable concrete HMAC signature value. Public records now carry `x-ashr-signature-sha256: present`, `signature_present`, `signature_algorithm`, and a derived `signed_payload_sha256`; tests assert no `whsec_local_` or concrete header signature leaks.

Additional validation after Bus-Auditor fixes:
- `python -B -m pytest tests/a1/test_local_self_host_smoke_compose.py tests/a1/test_saas_platform.py -q -p no:cacheprovider` -> `15 passed, 1 skipped`.
- `go test ./...` from `packages/go/ashrclone` -> passed.
- `docker compose --env-file infra/docker/self-host.env.example -f infra/docker/docker-compose.self-host.yml --profile commercial config --quiet` -> passed; Docker warned that `ASHR_POSTGRES_AUTH_SECRET` is unset in the current shell, which is expected for a secret-ref compose config and must be supplied by the operator at runtime.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> `411 passed, 1 skipped`.
- `python -B -m pytest tests/integration/test_a1_large_saas_migration.py tests/integration/test_a1_large_saas_migration_live.py -q -p no:cacheprovider` -> `9 passed, 4 skipped`.
- `python scripts/cl_guard.py hygiene` -> passed, no findings.
- `python scripts/cl_guard.py commercial` -> passed, no blockers/advisories.
- `git diff --check` -> passed with CRLF normalization warnings only.

### Round43 CI fixture refresh - 2026-07-10T01:05:00Z

- GitHub Actions run `29031592365` failed only in `Python A1/A2 contracts`; Go and TypeScript were green.
- Failure cause: A1 public evidence index advanced from `a1-real-api-round40-history-plus-paid-media-gate` / `399` records to `a1-real-api-round43-readonly-refresh` / `400` records, so generated A2 reports consuming A1 evidence were stale.
- Fix: ran `python scripts/a2_regenerate_fixtures.py --write`, then staged only the four generated report files with real content diffs: `a2_commercial_readiness_report.json`, `a2_evidence_readiness_report.json`, `a2_release_gate_report.json`, and `a2_result_persistence_manifest.json`.
- Verification: `python scripts/a2_regenerate_fixtures.py --check` -> all 52 generated fixture files match; `python -B -m pytest tests/a2/test_contracts.py -q -p no:cacheprovider` -> `52 passed`.
- No A2 judge semantics or source code changed; this is generated fixture alignment required by the A1 evidence label refresh.

## Round44 worker/object/quota/API evidence hardening - 2026-07-10T00:25:00Z

Baseline:
- Working tree: `C:/Users/33516/Documents/Ashr_a1_clean_rebase`; PR #27 was green at commit `94716ce` before this round.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`, `gh pr list --state all --limit 20`, and `gh pr checks 27 --watch=false` were run before implementation.
- Peer branches observed: `origin/dev/g3-a2-calibration` and `origin/codex/a3-commercial-growth-round4`; no A3 files were touched.
- Strategy reread: A1 remains responsible for Go backend, SQL/Postgres/RLS, SDK/API client, object storage, worker, quota/billing safety, and real API calibration.

20 growth points advanced:
1. Worker daemon summary now records retrying and dead-lettered counts separately from aggregate failed count.
2. Worker daemon summary records lease seconds, max jobs, heartbeat enabled, heartbeat success count, and heartbeat error count.
3. Heartbeat loop records heartbeat success/error evidence without making heartbeat failure fatal to handler completion.
4. Worker tests cover lease -> heartbeat -> complete with usage/audit evidence.
5. Worker tests cover retry release behavior with public-safe error metadata.
6. Worker tests cover dead-letter behavior at max attempts.
7. Go redaction now blocks free-text sensitive assignments such as `password=`, `secret=`, and `token=` in provider/worker errors.
8. Go worker CLI tests cover config parsing without requiring Postgres DSN unless Postgres backend is selected.
9. Object storage manifests now include canonical SHA-256 manifest signatures.
10. Object storage tests verify signed manifest tamper detection.
11. Object storage S3-compatible manifests carry credential refs only and reject incomplete credential ref pairs.
12. Object storage has structured readback/checksum verification output.
13. Optional boto3/minio adapter status/readback support is lazy and dependency-graceful.
14. Object storage public evidence was updated to call out presigned/bearer URL non-public policy.
15. Control-plane API-key scope gates were tightened across run upload, trace ingest, artifact manifest read/write, release evidence read/verify, billing checkout/portal, and billing webhook ingest.
16. Denied auth attempts append public-safe `auth.denied` audit events.
17. Denied auth attempts append zero-unit denied usage/quota receipts before side effects.
18. New WSGI-boundary tests prove wrong/missing scopes deny mutation and do not leak bearer/API-key material.
19. Official Ashr API Round44 read-only small batch refreshed private evidence and public summary.
20. Public evidence index, field map, capability matrix, commercial kit, TS/Python gap matrix, and A2 generated reports were refreshed to the Round44 evidence label.

Subagents:
- Growth-Auditor identified the highest-ROI lane as Postgres-backed worker durability + MinIO/object-store write/readback + API-key/quota-gated ingestion.
- Worker-GoRuntime added worker summary durability fields, heartbeat stats, retry/dead-letter coverage, and Go redaction hardening; `go test ./...` passed in `packages/go/ashrclone`.
- Worker-ObjectStore added signed public manifests, signature verification, ref-only S3 credential handling, adapter status/readback contracts, and object storage tests; focused pytest passed.
- Worker-QuotaAuth added WSGI-boundary API-key scope gates and denied audit/quota receipts for ingestion/billing/evidence surfaces; focused pytest passed.

Official API evidence:
- Read-only command: `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 8 --output docs/evidence/private_refs/a1_readonly_api_round44_20260710_001500.json`.
- Public summary: `docs/a1/evidence/official_api_readonly_round44_summary_20260710_001500.json`.
- Result: status `ok`, read steps `5`, mutating steps `0`, quota blocks `0`, datasets count `3`, requests count `5`; no raw key, headers, request values, or private payloads were written to public files.
- Public evidence index after merge: `401` total records, `16` functions, historical quota block count preserved at `48`, label `a1-real-api-round44-readonly-refresh`.
- Mutating/paid API calls were not run because `mutating_small_batch_ready` remains false without a fresh quota-gate artifact.

Validation plan/results in this round:
- `python -B -m pytest tests/a1/test_object_storage_contract.py tests/a1/test_worker_quota_auth.py tests/a1/test_saas_platform.py tests/a1/test_saas_sdk_client.py tests/a1/test_saas_release_gate_endpoint.py tests/a1/test_ts_python_gap_matrix.py -q -p no:cacheprovider` -> initial stale TS/Python matrix failure, then refreshed and focused subset passed.
- `go test ./...` from `packages/go/ashrclone` -> passed.
- `python scripts/a2_regenerate_fixtures.py --check` -> all 52 generated fixture files match after Round44 evidence label refresh.

Residual risks / next A1 queue:
- Actual MinIO network PUT/HEAD/GET is still not in required CI because it needs running services; next round should add a local compose money-grade smoke if daemon/network stability allows.
- Postgres-backed worker restart/lease-expiry proof remains opt-in; next round should add a compose or `A1_POSTGRES_TEST_DSN` backed test for restart recovery.
- Billing/OAuth remain safety contracts, not live provider/account flows. Next round should add Stripe raw-body signature and OAuth PKCE/state replay tests before any live provider step.

## Round47 China-first payment runtime and fail-closed ingestion - 2026-07-10

Baseline and peer state:
- Authoritative worktree:
  `C:/Users/33516/Documents/Ashr_a1_clean_rebase`.
- Branch `codex/a1-local-sdk-runner-clean`; baseline and `origin/main` were both
  `5dbf4ee2`.
- All visible PRs were merged or closed. Peer A2/A3 branches were inspected
  read-only; no peer source was staged.
- Strategy reread confirmed A1 ownership of Go backend, SQL/Postgres/RLS,
  Python/TypeScript SDK and CLI parity, workers, billing/quota, evidence, and
  self-host runtime.

Round47 delivered:
1. China-first payment domain and reconciliation contracts in Go.
2. Postgres persistence for merchant applications, acquirer bindings, CNY/fen
   orders, notifications, refunds, bills, and reconciliation.
3. Public reconciliation HTTP receive/list/get routes with internal transitions
   absent from public clients.
4. Public billing webhook ingestion rejects caller-supplied verification before
   any database connection or transaction.
5. Migration trigger rejects unverified direct billing event writes.
6. Adversarial zero-side-effect tests cover billing, ledger, quota, audit,
   idempotency, order, refund, notification, and reconciliation records.
7. Python China-payment provider adapters and Stripe compatibility executor.
8. TypeScript China-payment, reconciliation, Stripe executor, OAuth, API-key,
   quota, trace, artifact, webhook, and hosted-client parity.
9. Go/Python/TypeScript route evidence records truthful counts:
   Go `56`, Python `35`, TypeScript `38`, with 16 unsupported
   China-payment/reconciliation gaps explicitly registered.
10. Commercial Compose migrator now runs migrations `001` through `004` before
    API and worker startup.
11. Long-running China-payment webhook, reconciliation, domestic-acquirer, and
    isolated Stripe worker profiles were added.
12. A2 cross-lane generated consumer fixture was refreshed only because the A1
    route artifact expanded from 43 to 67 routes; no A2 judge source or
    semantics changed.
13. Built-in Browser read-only calibration confirmed the Ashr public home,
    Docs entry, and Get Started link using visible DOM.
14. Growth-Auditor was recalled and closed after final review.

Validation:
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` ->
  `534 passed, 2 skipped`.
- `npm test` in `packages/ts/ashr-clone` -> `376 passed`.
- `go test ./...` and `go vet ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` and `go vet ./...` in `tests/integration/go` -> passed.
- Commercial Compose live smoke -> `1 passed`.
- `python scripts/a2_regenerate_fixtures.py --check` -> all 55 generated
  fixtures match.
- Focused A2 cross-lane/contract suite -> `67 passed`.
- `python scripts/cl_guard.py hygiene` -> passed.
- `python scripts/cl_guard.py commercial` -> passed.
- `git diff --check` -> passed with line-ending warnings only.
- Bounded secret scan reported only intentional negative-test and guardrail
  matches; no real credential or private key was found.

Browser and payment truth:
- `built_in_browser_available=true`
- `public_home_opened=true`
- `sandbox_only=true`
- `merchant_application_started=false`
- `kyc_started=false`
- `live_money_activation=false`
- `real_provider_calls=false`
- `real_card_acceptance=false`
- `plan_only=true`

Growth-Auditor disposition:
- Commit is acceptable only as disabled, fail-closed, plan-only infrastructure.
- Do not claim payment-ready, live-ready, or production-ready.
- Next round must prioritize provider-specific trusted verification artifacts,
  the cross-layer forbidden payment-data matrix, project-level RLS proof,
  entitlement persistence, and atomic order/refund/ledger/quota/audit/outbox
  transactions.

Next 20 A1 growth points:
1. Canonical forbidden payment-data matrix.
2. Python/TS/Go/SQL/HTTP/queue/trace/log/evidence enforcement.
3. Trusted internal verification artifact schema.
4. WeChat Pay API v3 verification adapter.
5. Alipay RSA2 verification adapter.
6. Domestic acquirer selection and callback certification interface.
7. Durable callback inbox and replay/conflict retention.
8. Project-level payment RLS policies.
9. `NOBYPASSRLS` live payment isolation proof.
10. Entitlement schema and lifecycle.
11. Serializable payment-state transaction.
12. Payment outbox and delivery worker.
13. Hosted URL allowlist and signed return context.
14. Opaque reference TTL/single-use/revocation rules.
15. Vault/KMS reference resolver and rotation model.
16. Sandbox/live infrastructure isolation.
17. Partial and cumulative refund controls.
18. Settlement-bill gross/fee/refund/net arithmetic.
19. Finance exception queue and immutable audit.
20. CI-grade secret scanner and payment security certification suite.
## Round48 controlled GitHub account connection - 2026-07-10

Baseline and collaboration:

- Authoritative worktree:
  `C:/Users/33516/Documents/Ashr_a1_clean_rebase`.
- Branch `codex/a1-local-sdk-runner-clean`, publishing to
  `origin/codex/a1-local-sdk-runner` and PR #31.
- Ran repository, remote, branch, PR, worklog, and diff discovery before
  finalization.
- Five peer A2 generated fixtures had CRLF-only working-tree noise. They were
  reviewed as peer-owned and explicitly excluded from edits, staging, and
  commit.
- Credential validation inspected presence, length, and equality only. No
  client ID, client secret, callback parameter, token, cookie, header, or raw
  provider response was printed or committed.

Delivered:

1. Go localhost GitHub account-connection runtime with exact project-scoped
   start, callback, connection, and disconnect lifecycle.
2. TypeScript account-connection client, CLI, OpenAPI route parity, timeout,
   abort, redaction, and adversarial coverage.
3. Python control-plane security hardening, provider adapters, route contracts,
   and PostgreSQL lifecycle migration contract.
4. Exact comma-separated GitHub granted-scope parsing with trimming,
   deduplication, missing-scope denial, and scope-escalation denial.
5. Primary verified email lookup; public output exposes only
   `email_present`, never a direct email address.
6. Public connection responses expose a provider-subject SHA-256 digest and no
   token reference.
7. Disconnect revokes the provider token before local token and connection
   deletion and fails closed on provider errors.
8. Controlled real GitHub localhost flow completed for an existing browser
   session.
9. Callback replay was denied with `invalid_oauth_state`.
10. Temporary listener and binary were removed after the proof.
11. Public-safe evidence finalized at
    `docs/a1/evidence/github_account_connection_evidence_20260710.json`.
12. OAuth security review and recovery/operator guides were corrected to match
    the implemented provider revocation and privacy behavior.

Real-provider evidence boundary:

- Environment: `localhost_development`.
- Provider: GitHub.
- Requested and granted scopes: `read:user`, `user:email`.
- Start, callback, connection, replay denial, and disconnect behaved as
  expected.
- Safe provider-subject digest:
  `d7f4c1d11d8f6560ce6c3b70a7624a23ac983ced162ee97e288995aa92c22b39`.
- Raw state, verifier, authorization code, access token, client secret,
  provider response, cookies, headers, and callback query were not retained.
- Honest capability label: controlled, existing-session, memory-backed
  localhost GitHub account connection.
- `production_ready=false`; this is not login, registration, organization
  membership, or production OAuth.

Validation before documentation convergence:

- Focused OAuth Python suite: `58 passed`.
- Full A1 Python suite: `714 passed, 2 skipped`.
- TypeScript build: passed.
- TypeScript tests: `426 passed`.
- Go `go test -count=1 ./...`: passed.
- Go `go vet ./...`: passed.
- CL hygiene: passed.
- CL commercial: passed with `0 blockers, 0 advisories`.
- `git diff --check`: passed with line-ending warnings only.

Residual risks:

- OAuth transactions, replay state, tokens, references, and connections are
  process-local memory.
- Restart can orphan an already-issued provider token.
- Reconnect replacement is not a durable revocation transaction and can leave
  a previous token active after interruption.
- Disconnect performs provider revoke first, but remote revoke plus local
  deletion is not transactionally durable.
- Shared-store, proxy, multi-instance, organization membership, production
  session, and account-takeover guarantees are not implemented.
- Migration 006 is a static PostgreSQL contract and is not wired into the Go
  runtime.

Next 20 A1 commercial growth points:

1. Wire OAuth transactions to PostgreSQL with atomic consume and TTL.
2. Persist provider connections with project-level RLS.
3. Store token references in Vault/KMS instead of process memory.
4. Add durable provider-revocation outbox and retry worker.
5. Revoke superseded provider tokens during reconnect.
6. Add multi-instance callback replay and concurrency proofs.
7. Add production reverse-proxy and trusted-host normalization.
8. Add secure session-cookie rotation and binding.
9. Add GitHub organization membership and installation policy checks.
10. Add GitHub App installation flow alongside OAuth account connection.
11. Implement Google OIDC with issuer, audience, nonce, and PKCE validation.
12. Add domestic WeChat and Alipay identity provider readiness contracts.
13. Add account-link conflict review and recovery workflow.
14. Add administrator-visible OAuth connection audit events.
15. Add per-tenant provider rate budgets and circuit breakers.
16. Add connection health, expiry, and reauthorization states.
17. Add production secret rotation without service restart.
18. Add self-host OAuth callback and external URL configuration.
19. Add SDK parity fixtures for every OAuth lifecycle state.
20. Add end-to-end account connection to tenant/project/run authorization.

## Round49 unified account boundary - 2026-07-10

Baseline and collaboration:

- Authoritative worktree:
  `C:/Users/33516/Documents/Ashr_a1_clean_rebase`.
- Branch `codex/a1-local-sdk-runner-clean`, publishing to
  `origin/codex/a1-local-sdk-runner` and PR #31.
- Repository, remote, branch, `origin/main`, peer branches, worklog, evidence,
  and current diff were inspected before finalization.
- Five peer A2 generated fixtures contain working-tree line-ending noise. They
  remain excluded from A1 edits, staging, and commit.
- The canonical model is account or principal, credential, membership, and
  session. A provider is a login credential, not a separate business account.

Delivered and verified:

1. The Go runtime shares one provider-neutral `UnifiedIdentityService` across
   GitHub and Google OAuth coordinators.
2. Controlled localhost GitHub and Google OAuth flows both resolved to the
   same canonical `local_account`.
3. The account had exactly two verified, login-capable OAuth credentials:
   GitHub and Google.
4. Membership count remained zero, proving that tenant and project
   authorization are independent from login credentials.
5. A caller-supplied mismatched account assertion returned HTTP `403` and
   failed closed.
6. Public account and credential responses passed the forbidden-material scan
   with zero hits.
7. Public-safe calibration evidence is stored at
   `docs/a1/evidence/unified_identity_same_account_localhost_20260710.json`.
8. The identity contract covers GitHub, Google, WeChat, QQ, Alipay, phone, and
   email as credentials on one backend account.
9. Account linking never implicitly merges by email or phone, provider-subject
   ownership conflicts fail closed, memberships survive unlink, and the final
   login-capable credential cannot be removed.

Evidence boundary:

- No callback URL, OAuth code, state, nonce, verifier, token, token reference,
  client secret, raw provider response, provider subject, raw email, or raw
  phone value was recorded.
- This is a localhost, process-memory-backed calibration.
- `production_ready=false`.
- Durable PostgreSQL runtime identity wiring and multi-instance uniqueness are
  not complete.
- WeChat, QQ, Alipay, phone, and email are contract and parity coverage only;
  they have not been real-provider calibrated.

Next identity growth:

1. Wire account, credential, membership, and session runtime operations to
   PostgreSQL under RLS.
2. Prove transactionally unique credential ownership across multiple API
   instances.
3. Require recent authentication for credential link and unlink operations.
4. Add durable session rotation, recovery, merge review, and revocation
   workflows without implicit contact matching.
5. Real-calibrate WeChat, QQ, Alipay, phone, and email only with official
   credentials, explicit user consent, and private evidence handling.

Validation:

- Focused unified identity, OAuth evidence, and TS/Python parity suite:
  `31 passed`.
- Full A1 Python suite: `858 passed, 2 skipped`.
- TypeScript build and suite: `493 passed`.
- Go `go test -count=1 ./...`: passed.
- Go `go vet ./...`: passed.
- CL hygiene: passed.
- CL commercial: passed with `0 blockers, 0 advisories`.
- `git diff --check`: passed with line-ending warnings only.

Growth-Auditor disposition:

- Round49 localhost unified-account boundary: `GO`.
- Commercial production identity system: `NO-GO`.
- Production blockers are PostgreSQL runtime selection, local-first durable
  credential and session invalidation, provider-revocation outbox processing,
  reconnect token supersession, multi-instance uniqueness, and separation of
  internal audit metadata from public metadata.
- These blockers are the next A1 identity P0 slice and are not represented as
  completed by the localhost calibration.

## Round50 production identity and revocation hardening - 2026-07-10

Scope and safety boundary:

- This round keeps one provider-neutral backend account or principal as the
  stable business identity.
- A credential is only a login method. A membership grants tenant or project
  authorization, and a session represents an authenticated account. Changing
  or unlinking a credential does not create, merge, or delete memberships.
- GitHub, Google, WeChat, QQ, Alipay, phone, and email are represented by the
  same credential model. Hosted OAuth execution remains limited to GitHub and
  Google; the other channels remain contract boundaries.
- Accounts are never implicitly merged because contact identifiers happen to
  match. Provider-subject ownership conflicts fail closed, and merge or
  recovery requires a separate explicit, audited workflow.
- Public identity and audit metadata now use recursive allowlist-style
  filtering and defensive copies. Normalized aliases for credential,
  callback, contact, token-reference, and revocation bookkeeping material are
  removed from public output.
- No secret, callback URL, callback query, provider identifier, contact value,
  credential material, session material, cookie, header, or raw provider
  response is recorded in this worklog.

Localhost same-account evidence:

- Controlled localhost flows verified that GitHub and Google credentials can
  resolve to the same canonical backend account.
- The proof also verified that login credentials and authorization memberships
  remain independent and that a forged account assertion is rejected.
- The evidence retained only public-safe outcome classes and counts. It did
  not retain callback or provider material.
- This is a localhost development proof. It is not evidence of production
  OAuth, multi-instance uniqueness, account recovery, or a deployed external
  secret vault.

Production startup and session resolution:

1. The Go API now defaults to the PostgreSQL identity runtime and fails closed
   when the database configuration or required identity migration set is
   unavailable.
2. The memory identity runtime is available only when the environment is
   explicitly development and memory identity is explicitly enabled.
3. PostgreSQL startup opens and pings the database and verifies identity
   migrations 007 through 010 before serving.
4. Production session lookup uses a PostgreSQL-backed resolver shared by the
   identity and OAuth HTTP boundaries.
5. Raw session bearer values are not queried or stored by the resolver.
   Incoming values are transformed with HMAC-SHA256 using a runtime key of at
   least 32 bytes, and only active, unexpired session rows are accepted.
6. Production startup refuses enabled hosted OAuth until an injected external
   opaque vault is available. It does not silently fall back to process memory
   or plaintext provider-token storage.

Durable revocation outbox:

1. Disconnect and reconnect supersession perform local state transitions and
   enqueue provider cleanup in PostgreSQL instead of making remote cleanup the
   prerequisite for local invalidation.
2. The outbox claims bounded batches with `FOR UPDATE SKIP LOCKED`, lease
   expiration, and monotonically increasing lease-generation fencing.
3. Provider revocation and opaque-vault deletion have separate durable
   checkpoints so a worker can resume safely after interruption.
4. Failures use bounded exponential backoff and transition to dead letter
   after the configured attempt limit.
5. Completion revokes the superseded opaque reference and disconnects only a
   connection still bound to that reference. A reconnect that already issued a
   newer reference is not undone by stale cleanup.
6. The worker implementation and focused unit coverage exist, but the API
   process does not yet start this worker as a long-running production service.

Validation ledger:

- `gofmt` on the changed Go files: passed.
- `go test -count=1 ./...` from `packages/go/ashrclone`: passed.
- `go vet ./...` from `packages/go/ashrclone`: passed.
- Fresh-setup smoke from the preceding pushed slice: passed with 30/30 cases,
  `max_workers=4`, trace completeness `1.0`, and no inherited `PYTHONPATH`.
- Focused Python identity, Google account-connection, revocation migration, and
  fresh-setup tests: passed. The expanded focused identity and migration ledger
  passed 89 tests.
- TypeScript build: passed.
- TypeScript full suite: passed, 495 tests. The Go-server integration test now
  supplies the explicit development-memory runtime settings without weakening
  production defaults.
- Full `tests/a1` plus `tests/a2`: passed, 1038 tests with 2 expected skips.
- TS/Python generated parity artifact check: passed after the final refresh.
- A2 fixture regeneration check: all 55 generated fixture files match.
- CL hygiene: passed with zero findings.
- CL commercial: passed with zero blockers and zero advisories.
- `git diff --check`: passed with line-ending warnings only.
- Bounded secret and forbidden-material scan over the intended staged set:
  passed with zero suspicious literal matches. The scan reported locations
  only and did not print any matched value.

Peer and generated-fixture handling:

- One A2 cross-lane generated fixture has an intentional route-count refresh
  caused by the expanded A1 route surface. It is a narrow Gate compatibility
  update and does not change A2 judge semantics.
- Five additional A2 generated fixtures show line-ending-only working-tree
  noise. They are peer-owned, have no reviewed semantic change, and must remain
  unstaged.
- Staging must remain path-explicit; bulk staging is prohibited for this
  closeout.

Honest limitations and remaining evidence gaps:

1. The production HTTP write path for accounts, credentials, memberships, and
   link or unlink operations is not fully wired to the PostgreSQL store because
   the current handler option still expects the memory service.
2. Hosted production OAuth is intentionally unavailable until an external
   opaque vault and production provider adapters are injected.
3. The revocation worker is not started, supervised, or observed as a
   long-running process by the production entry point.
4. Multi-instance PostgreSQL proofs for provider-subject uniqueness, concurrent
   final-credential unlink, restart persistence, and lease recovery remain
   pending.
5. Session rotation families, reuse detection, revoke-one, revoke-all,
   account recovery, recent-authentication enforcement, and human-reviewed
   merge workflows are not complete.
6. WeChat, QQ, Alipay, phone, and email have cross-language credential-contract
   coverage only; no real-provider or delivery-channel calibration is claimed.
7. PostgreSQL integration still needs a clean-volume migration proof under the
   restricted runtime role and an end-to-end worker proof with a real external
   opaque vault.
8. Production session resolution still needs a narrow `SECURITY DEFINER`
   bootstrap under forced RLS. The resolver must revalidate active principal,
   credential, organization membership, and project membership state rather
   than trusting only the stored session row.
9. Outbox retry must reject expired leases, malformed tasks must dead-letter
   before any provider or vault call, and slow provider calls need bounded
   deadlines plus fenced lease extension.
10. Public audit metadata still needs event-specific allowlists and value-level
    rejection. Recursive key filtering alone cannot prove that a callback URL,
    bearer-looking value, provider subject, email, or phone is absent when it
    appears under a benign key.

Publication boundary:

- A1 business and evidence files will be committed to
  `origin/codex/a1-local-sdk-runner` only.
- The reviewed `a2_cross_lane_security_context.json` route-count refresh is
  excluded from the A1 commit and must be committed separately to the A2
  branch. The five CRLF-only A2 fixture changes remain unstaged.
- Because PR #31 CI executes against the A1 branch checkout, an A2-only fixture
  commit cannot green that PR until the reviewed A2 fixture commit is merged
  or cherry-picked through the normal Gate integration path.

Planned closeout commands:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/sdk)
python -m pytest tests/a1/test_identity_revocation_outbox_migration.py tests/a1/test_python_unified_identity.py tests/a1/test_python_google_account_connection.py tests/a1/test_fresh_setup_smoke.py -q -p no:cacheprovider
Remove-Item Env:PYTHONPATH

Push-Location packages/ts/ashr-clone
npm run build
npm test
Pop-Location

python -m pytest tests/a1 tests/a2 -q -p no:cacheprovider
python scripts/a2_regenerate_fixtures.py --check
python scripts/cl_guard.py hygiene
python scripts/cl_guard.py commercial
git diff --check
```

## Round 52 Closeout: Durable Identity Verification, TS Parity, And Rust Security

Date: 2026-07-11

This round hardened the A1 identity boundary across the Go runtime,
PostgreSQL, Python SDK, TypeScript SDK, and Rust verifier. It did not modify A2
judge semantics or A3 dashboard/report behavior.

Commercially relevant capabilities delivered:

1. Go now exposes a fail-closed production identity-verification runtime that
   requires PostgreSQL transaction coordination and refuses production
   fallback to the in-memory store.
2. Migration `012_a1_identity_verification.sql` provides digest-only
   challenges, receipts, delivery outbox, abuse budgets, audit events, forced
   RLS, and narrow security-definer mutation functions.
3. Live PostgreSQL proof covers transaction rollback, retryable proof state,
   two independent connection competition, exactly one credential winner,
   idempotent replay, changed-request conflict, cross-scope rejection, and
   direct-table mutation rejection.
4. Python and TypeScript expose the same durable verification public surface:
   10 durable/security public types, 22 contract fields, 12 canonical routes,
   stable errors, opaque references, and strict public-safe payload guards.
5. TypeScript includes executable durable-store, transaction-coordinator,
   challenge/receipt parsing, HTTP client, CLI-safe output, recovery, link,
   unlink, and merge behavior rather than symbol-only parity.
6. Rust now authenticates signed evidence manifests with HMAC-SHA256,
   canonical JSON, strict schemas, constant-time comparisons, bounded validity
   windows, tenant/project scope checks, and path-extraction hardening.
7. A Go test helper race found under WSL was fixed with `atomic.Int64`; no
   remaining race was found by the expanded race suite.

Validation ledger:

- TypeScript build and full suite: `521 passed, 0 failed`.
- Generated TS/Python parity artifact: regenerated and `--check` passed.
- Full A1 Python suite: `972 passed, 2 skipped`.
- Focused verification/PostgreSQL/Python/TS/Rust contract suite:
  `82 passed`.
- Live PostgreSQL migration suite: `13 passed`; the independent-connection
  race was repeated five times with five winners, five rejected competitors,
  and zero duplicate credentials.
- Windows Go `go test -count=1 ./...`: passed for all three packages.
- Windows Go `go vet ./...`: passed.
- WSL `Ubuntu-24.04-Ashr` used Go 1.22.2, GCC 13.3.0, and
  `CGO_ENABLED=1`; full `go test -race`, shuffled ten-run race, 100-run
  identity single-use contention, and focused rollback/runtime stress passed.
- Rust `cargo fmt`, `cargo clippy -D warnings`, and all-target tests passed;
  `22 passed`.
- Fresh setup smoke: passed.
- CL hygiene and commercial guards: passed with no findings or blockers.

GCC and Rust boundary:

- GCC was exercised through WSL CGO race builds and PostgreSQL reports its
  server compiler as GCC 15.2.0.
- The Rust verifier intentionally uses pure Rust/RustCrypto for canonical JSON
  and HMAC. Adding a C FFI layer would not add a security property and would
  enlarge the native-memory and supply-chain surface.
- Windows Rust 1.96.1 is the validated Rust toolchain for this round. WSL Rust
  is not claimed because the user-space toolchain download did not complete.

Evidence:

- `docs/a1/evidence/round52_identity_verification_postgres_20260710.md`
- `docs/a1/evidence/round52_rust_identity_security_verifier_20260711.md`
- `docs/a1/identity-verification-public-surface.json`
- `tests/a1/docs/a1/ts_python_gap_matrix.json`

Peer-change boundary:

- Five `fixtures/a2/results/*.json` files contain peer-owned line-ending noise.
  They remain unstaged and are excluded from this A1 commit.
- No A2 or A3 business file is part of the Round 52 publication set.
- Staging remains explicit by reviewed A1 path; bulk staging is prohibited.

Honest remaining gaps:

1. TypeScript matches Python's SDK, typed-client, public-contract, and local
   durable behavior, but does not yet independently prove Go/PostgreSQL RLS or
   multi-process production persistence.
2. Rust verifies authenticated manifests but does not stream object-storage
   artifact bytes; the artifact service must still compare each declared
   length and SHA-256 while reading.
3. Durable replay reservation remains a PostgreSQL transaction responsibility,
   not process-local Rust state.
4. Session rotation families, refresh-token reuse detection, revoke-one,
   revoke-all, recovery-driven session invalidation, and long-running
   verification delivery workers remain next-round production work.
5. Equivalent independent-connection races for login/session creation and
   recovery are not yet proven.

Next commercial A1 mainline:

- durable verification delivery worker with lease heartbeat, fencing,
  retry/dead-letter/redrive, and opaque SMTP/SMS adapters;
- session rotation/reuse detection and scoped revocation lifecycle;
- Go ingestion integration for the Rust authenticated evidence verifier;
- streaming object-storage verification and tamper-proof audit export;
- generated OpenAPI plus Python/TypeScript clients for the production identity
  and session lifecycle.

## Round 53: Production Identity Delivery, Browser Sessions, And Streaming Evidence

Date: 2026-07-11

Round status at this ledger update: implementation, broad validation, A2-owned
fixture integration and clean commit-tree validation are complete. Two
Growth-Auditor `NO-GO` reviews found and drove closure of cross-deployment HMAC
idempotency, publication evidence and commit-tree fixture consistency. A final
publication re-review remains required before push.

Start-of-round repository and peer calibration:

- Repository: `3351666087/ashr-codex-factory`.
- Local branch: `codex/a1-local-sdk-runner-clean`.
- Publication ref: `origin/codex/a1-local-sdk-runner`, PR `#31`.
- Round base: `ac960bda`; `origin/main` was `5dbf4ee2` and remained eleven
  commits behind the A1 branch.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`,
  `git status -sb`, `gh repo view`, and `gh pr list --state all` were run.
- A2 peer branch `origin/dev/g3-a2-calibration` was inspected read-only. Its
  multimodal API evidence remains A2-owned and no judge semantic was changed.
- A3 advanced to `f33144cf` with Signal Form, bilingual dashboard, screenshot,
  and E2E changes. Those files do not overlap the A1 runtime or contracts and
  were not copied, staged, or modified.

Round growth lanes executed in parallel:

1. Durable identity verification challenge and receipt storage.
2. Transactional verification plus session issuance.
3. Access and refresh token classes with strict non-interchangeability.
4. Session issue, refresh, revoke-one, revoke-all, and recovery invalidation.
5. Refresh-family lineage and reuse detection.
6. Browser access-cookie authentication.
7. Same-origin browser refresh endpoint.
8. Deterministic refresh idempotency and response-loss replay.
9. HMAC key rotation and previous-key continuity.
10. PostgreSQL forced-RLS security-definer bootstraps.
11. Verification delivery outbox with lease fencing.
12. Long-running Go identity-delivery daemon.
13. Lease heartbeat, retry, dead-letter, and redrive behavior.
14. mTLS external vault sealing and deletion adapters.
15. Python delivery/session lifecycle public contracts.
16. TypeScript executable parity and typed package subpaths.
17. Python/TypeScript generated capability matrix.
18. Rust authenticated streaming evidence verification.
19. Official API read-only and bounded mutation calibration.
20. Frontend mirror identity/session/delivery field mapping.

Implemented A1 code and contract slices:

- `services/api/migrations/013_a1_identity_session_lifecycle.sql` adds the
  digest-only session lifecycle, refresh lineage, idempotency ledger,
  reuse-family revocation, recent-auth enforcement, recovery invalidation,
  audit events, RLS and narrowly granted functions.
- `services/api/migrations/014_a1_identity_delivery_outbox.sql` adds atomic
  challenge creation plus delivery enqueue, leased claims, heartbeat fencing,
  bounded retry, dead-letter and redrive transitions.
- `services/api/migrations/015_a1_identity_browser_session_refresh.sql` adds a
  digest-only browser refresh bootstrap. Idempotent replay now returns the
  result session's persisted access and refresh expiry instead of recomputing
  public receipt expiry from retry time.
- `packages/go/ashrclone/identity_verification*.go` and
  `production_identity_store.go` implement production verification/session
  transactions, access-cookie resolution, refresh-cookie rotation, stable
  errors and fail-closed public boundaries.
- Browser refresh requires HTTPS, an exact same-origin `Origin`, optional
  `Sec-Fetch-Site: same-origin`, an empty body, no Authorization header, both
  secure HttpOnly cookies, and a bounded `Idempotency-Key`.
- A mismatched Authorization header and access cookie fail before PostgreSQL.
  Secure-cookie authentication over plaintext transport also fails before
  PostgreSQL.
- Same old refresh plus the same idempotency key derives one deterministic
  token pair. Different-key reuse returns HTTP 409, clears both cookies and
  revokes the session family.
- Refresh derivation is pinned to the old refresh token's configured key
  version. The pair, idempotency digest and request digest therefore remain
  stable after a process restart that promotes a new active key while retaining
  the old key in `PreviousSessionKeys`. New login issuance still uses the active
  key.
- `packages/go/ashrclone/identity_delivery_*.go` and
  `cmd/ashr-identity-delivery` implement the production delivery worker,
  deadline-bounded mTLS vault client, bounded PEM reads, redacted provider
  errors, connection cleanup and supervised worker entry point.
- `packages/sdk/ashr_clone/delivery_protocol.py` and
  `session_lifecycle.py` expose strict public-safe Python contracts.
- TypeScript adds executable delivery/session lifecycle modules, capability
  and Python-parity manifests, declaration-tested package subpaths, CLI-safe
  output and 574-test full-package coverage.
- Rust verifies authenticated evidence manifests and streams object bytes from
  an already-open root. Linux uses root-FD/openat traversal hardening; Windows
  and Linux both verify length and SHA-256, reject links/non-files/path escape,
  and authenticate a mutation anchor before object access.

Official API and product calibration:

- The credential was read only from `ASHR_API_KEY`; no value was written to a
  prompt, command, repository file, public evidence or log.
- Five read-only official operations completed with HTTP 200 and zero quota
  blocks.
- One text mutation was sent with small-batch and `--max-retries 0`. Transport
  returned HTTP 200 but the result envelope was quota-blocked. It is recorded
  as a failed mutation, not a generation or billing success.
- No image/audio/file/video mutation was sent after the text control failed;
  unchanged quota evidence did not justify purposeless repeated spend.
- Both the in-app Browser controller and Chrome controller failed during local
  control-runtime asset initialization before navigation. No live dashboard
  screenshot or official UI claim is made.
- The fallback static frontend mirror contained 589 entries. Its session and
  refresh strings are treated only as static hints, not proof of an official
  Ashr account-session API.

Evidence paths:

- `docs/a1/evidence/official_api_round53_readonly_public_summary.json`
- `docs/a1/evidence/official_api_round53_text_mutating_public_summary.json`
- `docs/a1/evidence/round53_official_api_and_frontend_calibration_20260711.md`
- `docs/a1/evidence/frontend_mirror_identity_session_delivery_map_20260711.json`
- Git-ignored private records:
  `docs/evidence/private_refs/a1_readonly_api_round53_20260711.json`,
  `a1_round53_text_mutating_real_20260711.json`, and
  `a1_round53_frontend_mirror_identity_session_delivery_scan_20260711.json`.

Validation ledger, including the final cached/staged Gate:

- Focused browser refresh Go lifecycle: passed, including active key
  `v2 -> v3` restart while retaining `v2`, identical replacement cookies,
  stable persisted expiry and no reuse response.
- Windows `go test -count=1 ./...`: passed for all four packages.
- Windows `go vet ./...`: passed.
- WSL `Ubuntu-24.04-Ashr`, `CGO_ENABLED=1`, `CC=gcc`, full
  `go test -race -count=1 ./...`: passed.
- Live PostgreSQL migrations 012-015: 48 passed before the key-rotation
  follow-up. Focused browser migration tests passed again afterward and prove
  replay leaves one rotated plus one active, non-revoked family member.
- Round 53 identity security integration: 6 passed after the follow-up.
- TypeScript build plus full package suite: 574 passed, 0 failed.
- Generated Python/TypeScript parity `--check`: passed.
- Rust `cargo fmt --check`, `cargo clippy -D warnings`, Windows all-target tests
  and WSL/Linux all-target tests: passed. Windows executed 31 tests and Linux
  executed 34 tests.
- Full `tests/a1 tests/a2`: 1225 passed with 2 expected skips.
- Fresh setup smoke: 30/30 cases, `max_workers=4`, trace completeness `1.0`.
- A2 fixture regeneration: all 55 generated fixtures match after the reviewed
  cross-lane route-count refresh.
- CL hygiene: passed with zero findings.
- CL commercial: passed with zero blockers and zero advisories.
- `git diff --check`: passed with line-ending warnings only.

Failures found and closed during validation:

1. Migration 015 initially referenced a nonexistent
   `identity_sessions.access_expires_at` column. Live PostgreSQL caught it; the
   persisted column is `expires_at`, while the function output alias remains
   `access_expires_at`.
2. The generated parity test still expected eight session routes after browser
   refresh made nine. The assertion was updated; generated Python and TS route
   contracts already matched.
3. A2 cross-lane fixture check detected the intentional route-count change:
   total `82 -> 83`, tenant-scoped `69 -> 70`, intentional differences
   `71 -> 72`.
4. Growth-Auditor found that deterministic refresh initially used the process's
   active key. A restart with a new active key could turn a legitimate retry
   into family reuse revocation. Derivation and operation digests are now pinned
   to the incoming refresh's retained key version, with restart coverage.

Growth-Auditor instructions and response:

- First publication verdict: `NO-GO` until cross-key idempotency and the
  publication evidence ledger were closed.
- Required follow-up: pin derivation and operation-digest key versions; prove a
  restart replay does not revoke the family; record Browser/Chrome failures;
  explicitly stage only reviewed A1 files; run cached diff and secret gates.
- Second publication verdict: `NO-GO` until the A2-owned fixture commit was
  integrated into A1 and the final cached/commit-tree attestation was recorded.
- Final publication verdict: `GO`; the third Growth-Auditor review found zero
  blocking P0/P1 and approved the attestation commit plus explicit A1 push.

Ownership and Gate boundary:

- The reviewed A2 compatibility fixture changes only three counts and must land
  through an A2-owned integration commit, not the A1 business commit.
- Five other A2 generated fixtures are CRLF-only. `git diff
  --ignore-space-at-eol --exit-code` returned zero for each; they remain
  unstaged.
- No A3 file is modified.
- Private API and mirror evidence is ignored by `docs/evidence/.gitignore` and
  must remain outside the staged manifest.
- A1 staging must be path-explicit; `git add -A` is prohibited.

Final staged and commit-tree attestation:

- A1 implementation commit: `24f3fbc` (`76` reviewed A1 files,
  `30,681` insertions and `338` deletions).
- The cached manifest contained zero A2, A3 or private-evidence paths. After
  commit, there were zero unstaged A1 paths.
- `git diff --cached --check` passed after removing four extra EOF blank lines
  caught only when previously untracked files entered the index.
- The staged secret scan compared four configured process/user secret values
  against all 76 blobs and found zero matches. High-confidence private-key,
  provider-token and same-line bearer scans also found zero matches after an
  explicitly labelled synthetic test bearer was excluded.
- A2 owner branch commit `97141b4b` changes only the reviewed cross-lane counts
  `82 -> 83`, `69 -> 70`, and `71 -> 72`; it was pushed to
  `origin/dev/g3-a2-calibration` under the configured user identity.
- A1 integration commit `51a1d70` preserves the A2 author/message and records
  provenance from `97141b4b`. The integrated fixture blob hash exactly equals
  the A2 commit's blob hash `c51e15e184b15971193eb894829fcd92f9c0836d`.
- A clean detached worktree at `51a1d70` had no working-tree changes. In that
  actual commit tree, `tests/a1 tests/a2` passed `1225` tests with `2` expected
  skips; all `55` A2 fixtures matched; Python/TS parity passed; CL hygiene had
  zero findings; CL commercial had zero blockers and zero advisories; and
  `git diff --check` passed.
- The five peer-owned A2 CRLF-only files remain outside both A1 commits.

Post-publication CI follow-up:

- PR `#31` CL Gate run `29153584161` passed plan/hygiene, Go, TypeScript and
  Rust jobs. Its Linux Python job failed one Round 53 integration test while
  the same test passed on Windows.
- Root cause: the test copied all of `node_modules` into a clean temporary
  package. On Linux, `node_modules/.bin/tsc` is a relative symlink; default
  `shutil.copytree` dereferenced it into a regular script under `.bin`, so its
  `../lib/tsc.js` import resolved from the wrong directory. Windows npm shims
  did not expose this defect.
- Removing all temporary dependencies was insufficient because TypeScript then
  could not resolve local `@types/node`. The final fix copies `node_modules`
  while explicitly excluding `.bin`, and executes the compiler from the source
  package's real `.bin` directory.
- Post-fix validation: Windows focused clean-build test passed; all six Round 53
  integration tests passed; TypeScript passed `574/574`; parity passed; and an
  offline Linux Node 22 container reconstructed a real Linux compiler symlink,
  compiled the temporary package with local type declarations, and proved
  prebuild removed the stale-dist sentinel.
- A bounded Docker registry retry failed twice with `ECONNRESET`; the offline
  reproduction used already installed public TypeScript package contents and
  made no credentialed network call.

Next commercial A1 growth points from the first audit:

1. Enforce safe retirement windows for previous session keys.
2. Define and enforce idempotency replay retention.
3. Stabilize cookie expiry under shortened configured caps.
4. Add custom access/refresh Max-Age replay tests.
5. Centralize secure-cookie validation across every resolver.
6. Add bounded refresh query and lock timeouts.
7. Prove concurrent identical refresh retries across processes.
8. Prove concurrent different-key reuse fencing.
9. Inject response loss immediately after SQL commit.
10. Add logout and revoke-all cookie-clearing routes.
11. Add refresh-family and reuse metrics.
12. Add public-safe key-version audit fields.
13. Add migration 012-015 clean-volume and rollback runbooks.
14. Exercise PostgreSQL failover during refresh rotation.
15. Add mTLS certificate hot reload and expiry alerts.
16. Reconcile orphaned vault seals.
17. Exercise multi-instance delivery lease loss.
18. Integrate Rust streaming verification into Go ingestion.
19. Generate browser-session OpenAPI security documentation.
20. Run Python and TS clients against live Go/PostgreSQL contracts.
21. Restore browser-control assets and run a real cookie lifecycle.
22. Require changed quota evidence before another controlled mutation.
23. Produce SBOM and provenance artifacts.
24. Bind validation attestation to the published commit.

## Round 54: Multi-Instance Session Safety, Trusted Ingestion, And Deployability

Date: 2026-07-11

Round status at start: active. Round 53 is published at `c7841635`; hosted CL
Gate run `29155743153` is fully green, including Linux Python, Go, TypeScript,
Rust, plan/hygiene, and summary jobs. The long-running commercial A1 goal
remains active.

Start-of-round repository and peer calibration:

- Repository: `3351666087/ashr-codex-factory`; local branch
  `codex/a1-local-sdk-runner-clean`; publication ref
  `origin/codex/a1-local-sdk-runner`; draft PR `#31` is `CLEAN`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`,
  `git status -sb`, `gh repo view`, and `gh pr list --state all` completed.
- `origin/main` is `5dbf4ee2`; the A1 publication branch is 15 commits ahead.
- A2 advanced from `97141b4b` to `47c05e5a`. The reviewed peer impact is an
  A2-owned trusted evidence snapshot and append-only decision-ledger spine.
  A1 must supply tenant/project/run/case/scenario facts and public-safe hashes,
  while A2 remains authoritative for evaluation semantics and release decisions.
- A3 advanced from `f33144cf` to `2250254b`. The reviewed peer impact is a
  unified identity entry flow and API-reference contract request. A1 must make
  browser verification completable using a server-owned, non-secret context;
  no A3 file will be modified or staged by this round.
- Five peer-owned `fixtures/a2/results/*.json` files contain CRLF-only working
  tree noise. They remain unstaged and are excluded from every A1 manifest.
- Official-product fallback is fixed as in-app Browser, then Chrome, then the
  static frontend mirror at
  `C:\Users\33516\Desktop\Ashr_frontend_mirror_20260707_125507.zip`.
  Controller failure is evidence, not permission to guess official behavior.

Round 54 executable growth points and ownership:

1. Enforce minimum previous-session-key retention against live token lifetime.
2. Reject duplicate, active-key, and unsafe legacy key-version configurations.
3. Expose public-safe session-key retirement readiness and bounded metrics.
4. Add refresh SQL statement, transaction, and row-lock deadlines.
5. Prove identical-retry and conflicting-reuse behavior across independent DB clients.
6. Define a Go-to-Rust authenticated streaming verifier process contract.
7. Stream artifact bytes without loading the evidence bundle into memory.
8. Bind verifier input to tenant/project/run, manifest hash, mutation anchor, and size caps.
9. Fail closed on verifier timeout, malformed output, symlink/path escape, and digest mismatch.
10. Add Python browser-session login, refresh, logout, and revoke-all client surfaces.
11. Add executable TypeScript parity for the same browser-session surfaces.
12. Preserve exact replacement cookie expiry and Max-Age under custom configured caps.
13. Generate a browser-session OpenAPI security contract with stable error envelopes.
14. Add Python/TypeScript/Go route and capability drift gates.
15. Add production Kubernetes resources for API, worker, delivery, migration, and verifier.
16. Add network policies, pod security, disruption budgets, and topology spreading.
17. Add Terraform/Kubernetes configuration validation and immutable image inputs.
18. Add multi-instance Postgres/worker failover and readiness smoke coverage.
19. Add SBOM/provenance generation plus published-commit binding.
20. Add an A1 trusted evidence producer for A2 `a2.evidence_snapshot.v1` inputs.
21. Preserve equal text/image/audio/file/video modality handling in that producer.
22. Add A3 identity-contract compatibility fixtures without importing A3 business logic.
23. Run official read-only calibration and gate mutations on changed quota evidence.
24. Produce a redacted, auditable Round 54 command/test/evidence ledger.

Parallel assignment:

- Worker-Session owns points 1-5 in Go/PostgreSQL session runtime and tests.
- Worker-Verifier owns points 6-9 in Rust/Go ingestion and security tests.
- Worker-SDK owns points 10-14 in Python/TypeScript/OpenAPI parity and tests.
- Worker-Infra owns points 15-19 in deploy/runtime infrastructure and validation.
- Worker-Integration owns points 20-24 in A1 contract adapters, compatibility tests,
  and public-safe evidence, without changing A2 judge or A3 dashboard semantics.
- Growth-Auditor performs an initial money-grade boundary audit and a mandatory
  post-integration re-audit; it does not own ordinary product implementation.

Round 54 identity lifecycle closure, 2026-07-12:

- Re-read `origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
  The implementation remains aligned with its `user`/`identity` separation,
  explicit reauthentication for linking, provider-subject uniqueness, complete
  audit, and fail-closed domestic-provider requirements.
- Fixed two over-broad static assertions in
  `tests/a1/test_identity_lifecycle_receipt_postgres_migration.py`. The test
  now rejects raw email parameters/columns without rejecting safe
  `invalid_verified_email_material` error text, and recognizes that exact
  login may read the canonical principal while remaining write-free.
- Focused Python identity contract command from repository root passed:
  `29 passed in 0.34s`.
- One intermediate Python invocation was run from
  `packages/go/ashrclone` and therefore found no `tests/a1` path. This was a
  command working-directory error, not a product failure; the corrected root
  invocation passed.
- PostgreSQL integration command passed every subtest in 12.173 seconds:
  24-way exactly-once registration, unknown-login non-creation, duplicate
  registration rejection, scope mismatch without consumption, rollback and
  bounded retry, exact credential login, OAuth-first password absence, safe
  A3 projection, receipt key rotation, and ciphertext/nonce/scope/key-version
  tamper rejection.
- Official Google and GitHub documentation was used to calibrate separate
  registration, authentication, OAuth consent, explicit account linking,
  verified email establishment, optional password enrollment, recovery, and
  recommended 2FA/passkeys. Ashr clone remains intentionally stricter:
  matching email never auto-links or auto-merges accounts.
- A3 receives only safe account, credential, membership, security-posture, and
  provider-readiness projections. Email material, provider subjects, secrets,
  receipt material, encrypted proofs, and provider tokens remain private.
- WeChat, QQ, Alipay, and phone remain first-class capability entries. Without
  required business qualification or provider configuration they fail closed
  with an explicit readiness reason rather than pretending to be usable.
- Five A2-owned fixture changes remain peer-owned, read-only, and excluded from
  the A1 staging manifest.
- Mandatory Bus-Auditor spawn was retried after implementation and tests but
  failed with `agent thread limit reached`. No review result is fabricated.
  The next available agent slot must be used for the post-integration audit.

Round 54 final identity-lifecycle and parity closure, 2026-07-12:

- Registration and login remain separate executable state machines.
  Registration creates one canonical account plus one verified initial
  credential. Login authenticates only an exact credential already attached
  to that account and cannot create, infer, bind, merge, or mutate identity
  ownership.
- Domestic email registration is the preferred currently deployable entry
  route. OAuth-first registration may copy only provider-verified email,
  creates no password, and requires a later explicit password-enrollment
  action. Optional 2FA remains recommended in the public security posture.
- Matching email is never account-linking proof. GitHub, Google, email, phone,
  and future WeChat, QQ, and Alipay credentials bind only through an
  authenticated, recent-reauthenticated, explicit linking flow. Domestic
  providers remain represented in capability contracts but fail closed while
  business qualification or provider configuration is unavailable.
- The A3 projection exposes only canonical account state, credential kinds,
  membership, security posture, and provider readiness. It excludes raw or
  digested email, provider subjects, secret references and fingerprints,
  verification receipt material, encrypted proof material, and provider
  tokens.
- `python tests/a1/ts_python_parity_matrix.py --write` regenerated the parity
  matrix. The focused gap and Linux clean-build gates passed `2 passed`.
  Three Python-compatible acronym exports were completed in TypeScript:
  `IdentityLifecycleHTTPClient`, `IdentityLifecycleHTTPError`, and
  `IdentityLifecycleHTTPResponse`.
- Full A1 Python validation passed `1240 passed, 2 skipped in 300.53s`.
  TypeScript package validation and a clean rebuild passed `598/598`.
- `go test -count=1 ./...` passed all Go packages and `go vet ./...` passed.
  `cargo test` passed all Rust verifier unit, authenticated-envelope,
  authenticated-evidence-bundle, and streaming-object tests.
- PostgreSQL identity-lifecycle integration passed in 9.83 seconds, including
  24-way exactly-once registration, unknown-login non-creation, duplicate
  registration rejection, scope mismatch without receipt consumption,
  rollback and bounded transaction retry, exact credential login,
  OAuth-first password absence, safe A3 projection, key rotation, and
  ciphertext/nonce/scope/key-version tamper rejection.
- Two earlier parity follow-up commands failed only because they were launched
  from `packages/ts/ashr-clone` with repository-root-relative test paths.
  Corrected root commands passed and no product defect remained.
- Five peer-owned A2 fixture changes remain excluded from the A1 staging
  manifest. No A3-owned file was modified or staged.
- The mandatory post-integration Bus-Auditor spawn was attempted again and
  still failed with `agent thread limit reached`. This environmental limit is
  recorded without fabricating an audit result.

Round 54 hosted CI repair, 2026-07-12:

- Re-ran the repository, branch, remote, PR, peer, strategy, and worklog
  baseline before modifying files. PR `#36` had one substantive Python job
  failure: the public evidence scanner treated `tp_` fragments embedded in
  ordinary identifiers as credentials. The same over-broad matcher existed
  in Python and TypeScript.
- Tightened only the `tp_` credential matcher to require a non-identifier
  left boundary. Actual `tp_...` credential-shaped values remain blocked,
  while `http_status`, `http_test`, `trusted_proof`, and `otp_present` are
  accepted as ordinary schema identifiers.
- Added Python and TypeScript parity regressions for both the blocked token
  shape and allowed identifier fragments.
- `python -m pytest -q tests/a1/test_evidence_index.py` passed `21 passed`.
- TypeScript `npm test` passed `599 passed, 0 failed` after a clean build.
- Full `python -m pytest -q tests/a1` passed `1242 passed, 2 skipped in
  318.40s`.
- The remaining hosted Python failures are A2 generated-fixture drift caused
  by the five newly documented A1 identity routes. No judge semantic failure
  was observed. The A2 snapshot will be regenerated in an isolated A2
  worktree and committed to the A2 branch; it is excluded from this A1 commit.
- The Bus-Auditor spawn was retried before this repair and again failed with
  `agent thread limit reached`. No audit result is fabricated.
## Round 55: Production Password And MFA Lifecycle

Date: 2026-07-12

Repository baseline: clean `codex/a1-round54-publish`, tracking
`origin/codex/a1-local-sdk-runner`; draft PR `#36` remains open. Re-read the
current `origin/main` strategy and reviewed A2/A3 peer branches read-only.

Commercial enhancement score (5 is highest value; effort is cost):

| Candidate | Demo | Risk reduction | Contract impact | Effort | API evidence |
|---|---:|---:|---:|---:|---:|
| PostgreSQL password recovery/change and MFA lifecycle | 5 | 5 | 3 | 4 | 5 |
| Enterprise OIDC/SAML adapter and explicit linking | 4 | 4 | 4 | 5 | 4 |
| Full identity RBAC enforcement across API/RLS/workers | 4 | 5 | 5 | 5 | 3 |

Selected the first candidate. Registration and login are already separate
executable state machines; this round closes the post-registration security
lifecycle without allowing login to create, infer, bind, or merge an account.
Domestic email remains the preferred deployable registration credential.
WeChat/QQ/Alipay remain fail-closed capability entries until qualification and
configuration exist. A3 receives only safe posture, readiness and action state.

The mandatory Bus-Auditor slot is still unavailable because the existing agent
thread limit is reached. No audit result is fabricated; retry remains required
before publication closure.

Round 55 password/MFA executable closure, 2026-07-12:

- Registration and login remain separate state machines. Registration creates
  a canonical account and verified initial credential; login only authenticates
  an exact existing credential and cannot create, infer, link, or merge.
  Domestic email remains the preferred deployable registration route. GitHub,
  Google, phone, WeChat, QQ, and Alipay remain explicit credentials; matching
  email is never linking proof, and unqualified domestic providers fail closed.
- Added migration `018_a1_password_mfa_lifecycle.sql` for scoped, expiring,
  single-use security receipts, password enrollment/change/recovery, session
  revocation, TOTP pending/confirmation, recovery-code posture, RLS, and a
  secret-safe A3 projection. A3 receives no password, TOTP, recovery-code,
  vault-reference, digest, or receipt material.
- Real PostgreSQL 16 validation exposed and closed two compatibility hazards:
  migration 018 now drops the v016 status/posture constraints before admitting
  `pending`, and the old boolean `a1_set_account_two_factor` signature is
  preserved but fails closed so it cannot bypass TOTP possession proof.
- `python -m pytest -q tests/a1/test_password_mfa_lifecycle_migration.py`
  passed `8 passed in 15.55s`. The fixture loaded every migration from 001
  through 018 into a temporary PostgreSQL database and proved wrong-purpose
  receipt non-consumption, replay rejection, password state transitions,
  recovery-version increment, active-session revocation, TOTP pending/confirm,
  expired enrollment rejection, secret-safe projection, and 16-client
  concurrent exactly-once receipt consumption.
- Final `python -m pytest -q tests/a1` passed `1247 passed, 2 skipped in
  324.87s`. TypeScript `npm test` passed `599 passed, 0 failed`; Go `go test
  -count=1 ./...` and `go vet ./...` passed. Python and TypeScript expose equal
  `get_security_posture`, `mutate_password`, and `mutate_two_factor` methods.
- `python scripts/cl_guard.py hygiene` returned no findings. An earlier attempt
  used nonexistent `python scripts/cl_gate.py --mode hygiene`; the corrected
  repository command is recorded here so the failed invocation is not hidden.
- The new security routes remain honestly `proposed`: trusted Go mutation-ticket
  resolution and production HTTP handlers are not connected. SDK mutations send
  only mutation ticket, step-up receipt, and idempotency identifiers; no private
  credential material crosses public or A3 JSON.
- `git fetch` observed a new peer A2 head on `origin/dev/g3-a2-calibration`.
  It has no A1 contract impact and was not merged or modified. No A2 judge or A3
  dashboard business file is included in this round.
- The required Bus-Auditor retry remains blocked by the existing agent-thread
  limit. No audit output is fabricated. Next top three: connect the trusted Go
  ticket resolver and activate handlers; add explicit enterprise OIDC/SAML
  linking; enforce identity RBAC through API, worker, and PostgreSQL RLS.

## Round 56: Trusted Identity Security HTTP Boundary

Date: 2026-07-12

- Re-read `origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md` and
  preserved separate registration and login state machines. Login still cannot
  create, infer, link, or merge an account; matching email is never linking
  proof. Domestic email remains the preferred deployable registration path.
- Added an injectable Go HTTP boundary for password enrollment/change/recovery and TOTP
  enrollment/confirmation. Public bodies accept only `mutation_ticket_id`,
  `step_up_receipt_id`, and an `Idempotency-Key`-matching identifier. Password,
  OTP/TOTP, recovery-code, secret reference, digest, actor, and account fields
  are rejected before a trusted resolver or store can run.
- Tickets are resolved server-side and must match the authenticated canonical
  account, exact operation, and expiration. Public failures intentionally do
  not reveal account, ticket, receipt, or backend existence.
- Added a secret-safe security posture route and narrowed Go redaction so only
  public posture booleans/statuses survive; raw password and secret material
  remains redacted.
- The new routes remain absent from the unconditional Go route manifest until
  the PostgreSQL store and production runtime wiring are executable. This is
  deliberately contract support, not a production-availability claim.
- Go full suite passed. Two command-entry failures were environmental and are
  retained here: repository-root `go test` had no module, and Git Bash could
  not find the Codex-local `apply_patch`; corrected module-local tests passed.
- Mandatory next-round hard acceptance chain: fresh user SDK install -> wrap a
  real Agent -> invoke a local real Ollama model -> submit one run -> query the
  run, trace, tool calls, and artifact through API -> restart services -> prove
  PostgreSQL/object persistence -> fetch authenticated A2 evidence by stable
  IDs. Mock/fake model substitution is forbidden.
- Local model inventory found no Windows/WSL Ollama CLI or user model manifest,
  but Docker already contains `ollama/ollama:latest` (8.06 GB). Inspect Docker
  volumes before pulling a model; download only when no reusable model exists.
- Next top three: (1) real Ollama durable SDK-to-A2 evidence acceptance chain,
  (2) production PostgreSQL mutation-ticket issuance/consumption and HTTP store,
  (3) enterprise OIDC/SAML explicit credential binding and conflict controls.

## Round 57: Provider-Neutral Model Runtime

Date: 2026-07-12

Commercial enhancement candidates were scored before implementation:

| Candidate | Demo | Risk reduction | Contract impact | Effort | API evidence |
|---|---:|---:|---:|---:|---:|
| Python/TypeScript provider-neutral execution parity | 5 | 5 | 2 | 4 | 5 |
| Durable idempotent model request journal | 4 | 5 | 3 | 5 | 3 |
| Real five-modality model matrix | 5 | 4 | 3 | 5 | 5 |

The first candidate had the highest immediate ROI and was selected.

- Added provider-neutral Python and TypeScript execution adapters for local
  Ollama and OpenAI-compatible providers. Both implementations cover bounded
  retries, timeouts, safe errors, streaming, tool calls, usage, finish reason,
  and provider-local text/image/audio/file/video envelopes.
- Capability discovery separates protocol support from verified model
  callability. Text defaults to callable; image, audio, file, and video remain
  discovered until each exact model/request combination succeeds.
- TypeScript publishes the reusable `./provider-adapter` subpath. The complete
  TypeScript suite passed `610 passed, 0 failed` after the audit follow-up.
- Python provider, adapter, runner, and trace focused tests passed
  `56 passed in 2.33s`.
- Bounded real calibration used the actual Python and TypeScript SDK adapters
  against local Ollama `qwen2.5:1.5b`, XJTLU `gpt-5.6-sol`, and Qwen official
  `qwen-plus`. Non-stream text, streamed text, one tool call, usage, and finish
  reason passed in both languages for all three endpoints.
- Ollama truthfully returned a tool call with finish reason `stop`; XJTLU and
  Qwen returned `tool_calls`. The adapter preserves this provider difference
  instead of leaking a fabricated shared-contract rule.
- Public-safe calibration evidence is recorded at
  `docs/a1/evidence/round57_provider_neutral_runtime_calibration_20260712.md`.
  No secret value, authorization header, raw provider response, or signed URL
  was persisted.
- No A2 judge or A3 dashboard/report business semantics were modified.
- Full A1 Python validation passed `1265 passed, 2 skipped in 415.52s`.
- Audit follow-up added runtime validation of terminal capability values in
  TypeScript, empty-evidence and timezone-aware timestamp checks in both
  languages, and immutable Python capability maps. Focused Python validation
  passed `54 passed`; the complete TypeScript suite then passed `610/610`.
- Hosted one-time API key secret restoration now permits only an explicit
  `create_api_key` reveal response with a top-level non-empty string and an
  exact true display marker. Operation mismatch, missing/false markers, empty
  or non-string values, nested values, and malformed results remain redacted.
  Exact secret occurrences elsewhere in the response are scrubbed before the
  single allowed field is restored.
- The public calibration summary cannot be bound to private source records
  because no such records were persisted for the completed probes. Hashes,
  timestamps, and private paths were not fabricated; the evidence document
  records this gap explicitly.
- Bus-Auditor received the implementation, real calibration, and verification
  checkpoint and identified the follow-up items above. Final full-suite and
  packaging revalidation follows before publication.

Next top three: durable idempotent request journaling across restart; real
model-by-modality capability probes without false claims; Ollama-to-Go-to-
PostgreSQL/object-storage acceptance with stable authenticated evidence IDs.

## Round 58: Restart-Persistent Provider Dispatch And Stream Integrity

Date: 2026-07-12

Commercial enhancement candidates:

| Candidate | Demo | Risk reduction | Contract impact | Effort | API evidence |
|---|---:|---:|---:|---:|---:|
| Restart-persistent local provider journal and stream integrity | 5 | 5 | 2 | 4 | 4 |
| Real five-modality capability expansion | 5 | 4 | 3 | 5 | 5 |
| PostgreSQL multi-host provider dispatch coordinator | 4 | 5 | 4 | 5 | 3 |

The first candidate had the highest bounded ROI. It closes the most dangerous
provider failure mode: silently issuing a second paid request after dispatch
acceptance becomes uncertain.

- Added Python and TypeScript restart-persistent local JSON request journals scoped by tenant,
  project, provider, model, operation, and idempotency key. Claims carry lease
  ownership and fencing tokens. Conflicting fingerprints fail closed.
- Restarted or lease-expired in-flight work becomes `indeterminate`; timeout,
  disconnect, process loss, response loss, or any observed stream frame cannot
  trigger an automatic provider retry. Explicit reconciliation is required.
- Added the shared `ashr.clone.provider_stream.v1` protocol in Python and
  TypeScript. It records monotonic sequence numbers, content digests, a
  previous-frame digest chain, terminal state, and a final stream digest while
  persisting no raw text or media content.
- Duplicate sequence/same-content frames are idempotent. Sequence conflicts,
  gaps, out-of-order frames, post-terminal frames, missing terminal frames, and
  tampered snapshots fail closed.
- A pytest-managed real Node subprocess now validates Python stream snapshots,
  emits a TypeScript stream snapshot, and verifies it in Python. Canonical JSON
  and digest chains for `ashr.clone.provider_stream.v1` are cross-language
  compatible, including Unicode input, and raw chunk content is absent from
  both fixtures. Journal persistence is intentionally language-specific:
  `ashr.clone.provider_request_journal.python.v1` and
  `ashr.clone.provider_request_journal.typescript.v1` are not claimed to be
  mutually readable.
- TypeScript publishes `./provider-request-journal` and `./provider-stream`.
  Final `npm test` passed `623/623`; `npm pack --dry-run` passed with 111 files
  and included both JavaScript and declaration artifacts.
- Focused Python journal/stream validation passed `39 passed`. The full
  A1 Python suite passed `1320 passed, 2 skipped in 283.94s`; the earlier
  isolated wheel import anomaly did not reproduce.
- Audit follow-up binds stream snapshots to the active journal entry and fence,
  rejects stale or mismatched bindings, and requires a terminal stream proof
  before success. Python also proves exactly one same-process threaded claimant.
- TypeScript persisted-entry loading now rejects non-canonical fields,
  malformed digests, unsafe counters, invalid timestamps/evidence, incomplete
  modality or persistence capability metadata, and inconsistent
  state/lease/terminal combinations. Its in-process persistence write chain
  also recovers after a reported transient write failure instead of remaining
  permanently rejected.
- This round proves unit behavior, process-level Python/TypeScript
  interoperability, file-backed restart semantics, and content-free stream
  integrity. It does not prove PostgreSQL coordination, multi-host consensus,
  distributed locking, or provider-native idempotency.
- No real provider call was needed to prove these deterministic failure
  semantics, and no paid call was made merely to increase call volume. Round 57
  remains the real-provider evidence for Ollama, XJTLU, and Qwen.
- Remote inventory after fetch contains exactly one A1 branch:
  `origin/codex/a1-local-sdk-runner`. The local
  `codex/a1-round54-publish` worktree branch is only a staging worktree and must
  be pushed exclusively to that canonical remote ref.
- Final CL hygiene passed with zero findings. These file-backed journals remain
  explicitly single-process and restart-persistent only: they provide no
  cross-instance/process claim lock, multi-worker safety, multi-host safety, or
  proven power-loss durability.

Next top three: run a bounded real Ollama partial-stream process-loss probe;
add PostgreSQL-backed multi-worker journal coordination; expand verified
model-by-modality coverage without promoting discovery to callability.

## Round 59: CL Fresh-Checkout Repair

Date: 2026-07-12

- GitHub PR 36 run `29191539967` exposed a fresh-checkout defect in the Round
  58 cross-language stream test. The Python job did not build the ignored
  TypeScript `dist/provider-stream.js` module before importing it.
- The earlier local full-suite result was not valid fresh-setup evidence
  because a generated local `dist/` directory masked the missing build step.
- The Python CL job now installs Node 24, runs locked TypeScript dependency
  installation, and builds the SDK before Python contracts.
- The test itself also performs the build when the required generated module
  is absent, so direct pytest execution remains deterministic after locked
  TypeScript dependencies are installed.
- Added ignore protection for Python SDK `build/` and `*.egg-info/` output.
- After deleting TypeScript `dist/`, focused validation passed `10 passed`.
- The exact GitHub Python contract command passed `1515 passed, 2 skipped in
  277.89s`; `git diff --check` passed.
- Peer changes observed at round start: A3 contract-alignment and A2
  calibration remote branches advanced. They were inspected only as remote
  state and were not merged or modified.
- Bus-Auditor correctly held new feature work until PR 36 is green and then
  directs the next commercial slice toward PostgreSQL-backed multi-worker
  dispatch plus durable Ollama acceptance proof.
- Publication remains restricted to the single canonical remote branch
  `codex/a1-local-sdk-runner`; the local staging branch is not publishable.

Next top three: PostgreSQL multi-worker provider dispatch coordination with
fencing and reconciliation; durable Ollama SDK-to-run acceptance across
service restart; verified five-modality provider capability expansion.

## Round 60: PostgreSQL Provider Dispatch Coordination

Date: 2026-07-12

Commercial enhancement candidates:

| Candidate | Demo | Risk reduction | Contract impact | Effort | API evidence |
|---|---:|---:|---:|---:|---:|
| PostgreSQL provider-dispatch coordinator | 4 | 5 | 3 | 4 | 3 |
| Go provider-dispatch HTTP and cross-language clients | 5 | 4 | 3 | 4 | 4 |
| Five-modality real-provider matrix expansion | 5 | 4 | 3 | 5 | 5 |

The PostgreSQL coordinator was the highest bounded ROI because the existing
file journal could not safely coordinate several service instances.

- Added a Go provider-dispatch state machine and PostgreSQL repository with
  idempotent submit, lease claim, fencing, heartbeat, stream observation,
  terminal proof, indeterminate state, and explicit reconciliation.
- Claim runs at `READ COMMITTED`, uses `FOR UPDATE SKIP LOCKED`, retries
  PostgreSQL `40001` and `40P01` up to four attempts, honors cancellation and
  deadlines, and never retries an ambiguous commit.
- Added stable public operational errors. Driver, SQL, table, host, and
  credential detail are not returned through claim failures.
- Added transaction-local A1 organization/project scope to submit, claim,
  lease mutations, and completion replay.
- Migration 019 and the embedded Go schema now enable and force fail-closed
  RLS using `app.a1_organization_id` and `app.a1_project_id` in both `USING`
  and `WITH CHECK`.
- A real `NOSUPERUSER NOBYPASSRLS` role proves missing-scope invisibility,
  tenant/project isolation, correct-scope writes, rejected cross-scope writes,
  idempotent migration, and legacy upgrade without data loss.
- Python focused provider-dispatch and migration verification passed
  `22 passed`; Go `go test ./...` passed; TypeScript build and all `629` tests
  passed.
- The live PostgreSQL 16-client claim test passed ten consecutive repetitions.
  Each repetition had exactly one fenced winner and no claim errors.
- The PostgreSQL container was actually restarted. Durable dispatch fields
  before and after restart were identical; the public-safe record digest is
  recorded in `docs/a1/evidence/round60_provider_dispatch_postgres.md`.
- Latest remote CL before this dirty round is green at SHA `f9562494` (run
  `29191978911`). The new provider-dispatch files require a new CL after push.
- Peer changes observed: remote A2/A3 branches exist but no peer file was
  merged into or modified by this A1 round.

Next top three: publish provider-dispatch through the Go HTTP server and drive
it from Python/TypeScript; run durable local Ollama SDK-to-run acceptance;
expand verified five-modality provider capability evidence.

### Round 60 release closure

- Rebuilt `services/runner/docker-compose.a1.yml` from scratch through
  `infra/docker/Dockerfile.go-runtime`. The final container executes compiled
  `/usr/local/bin/ashr-api`; PostgreSQL was healthy, the BusyBox filesystem
  object-store placeholder was running, and `/health` reported `ready=true`,
  `backend_ready=true`, and `backend=postgres_repository_v0`.
- The Python SDK to real Go control-plane vertical test passed `1 passed`.
  The deployment scaffold acceptance contract was deliberately upgraded from
  the obsolete Python/dependency-free assumptions and passed `5/5`.
- Provider dispatch is now published through Go HTTP and represented in both
  Python and TypeScript. The previous evidence statement that HTTP publication
  remained future work was obsolete and was corrected.
- TypeScript passed `634/634`; `npm pack --dry-run` contained 114 files and
  1.7 MB unpacked. The generated TS/Python gap matrix check passed.
- Full A1 plus integration Python verification passed `1329 passed, 37
  skipped in 110.86s`. The CL A2 plus large-SaaS migration supplement passed
  `195 passed`.
- Go package and Go integration `go test -count=1 ./...` and `go vet ./...`
  passed. The live PostgreSQL dispatch claim proof passed ten consecutive
  repetitions with one fenced winner each.
- `python scripts/cl_guard.py hygiene`, `python scripts/cl_guard.py
  commercial`, `git diff --check`, and `git diff --cached --check` passed.
- A direct local `compileall` traversed ignored build products and encountered
  read-only stale `__pycache__` files because this publishing worktree has
  unusual ACLs. Source syntax was then verified without bytecode writes by
  parsing all 174 Python files with `ast.parse`.
- The Rust bundle verifier passed all suites with `CARGO_TARGET_DIR` redirected
  to a writable temporary directory. A3 passed `334/334` with `TEMP` and `TMP`
  redirected to the same writable area, and the pinned audit bundle verifier
  passed. These ACL workarounds did not change product code or release
  behavior.
- The first earlier Docker dependency download encountered a transient
  `proxy.golang.org` EOF. The later retry and final no-cache build succeeded.
  One combined command also sent a Node test to pytest and another fresh
  PowerShell process saw Docker pipe/config warnings; authoritative commands
  were rerun independently and passed.
- Peer branches `origin/codex/a3-main-contract-alignment-v2` and
  `origin/dev/g3-a2-calibration` advanced. No peer files were merged into or
  modified by this A1 round.
- Known boundary: quickstart `object-store` remains a BusyBox local filesystem
  placeholder. MinIO belongs to the separate commercial self-host Compose.
- Bus-Auditor keeps publication at NO-GO until this Round 60 snapshot is
  committed, pushed, and its new CL Gate is green.

Next top three: durable Ollama SDK-to-run acceptance across service restart;
verified five-modality provider capability expansion; production-grade
object-store acceptance for trace/artifact evidence.

### Round 60 CL publication correction

- GitHub Actions run `29197725997` evaluated commit `365d5cdf`. Plan and
  hygiene, TypeScript SDK parity, Rust verifier, and Go SDK and integration
  all passed.
- Python A1/A2 contracts reported `2 failed, 1494 passed, 50 skipped, 1056
  subtests passed`. Both failures had one publication root cause:
  `docs/a1/ts_python_gap_matrix.json` was generated by the repository-root
  parity script but omitted from the Round 60 commit.
- Regenerated the public-safe artifact with
  `python tests/a1/ts_python_parity_matrix.py --write`; its freshness check
  passed with `--check`.
- Focused reproduction of the two CL failures passed `2 passed in 6.35s`:
  `tests/a1/test_ts_python_gap_matrix.py` and
  `test_typescript_clean_build_and_typed_subpath_parity`.
- No product implementation or shared contract changed in this correction.
  Peer A2 advanced from `7e70c234` to `e7c1ff18`; no peer file was merged or
  modified.

Next: publish the generated artifact, require the new SHA's CL Gate summary
to pass, and return the result to Bus-Auditor for final GO/NO-GO.

## Round 61: PostgreSQL-Only Canonical Identity Authority

Date: 2026-07-12

Commercial enhancement candidates:

| Candidate | Demo | Risk reduction | Contract impact | Effort | API evidence |
|---|---:|---:|---:|---:|---:|
| PostgreSQL-only canonical identity reads | 4 | 5 | 2 | 3 | 2 |
| Go browser-session lifecycle parity | 4 | 4 | 3 | 4 | 2 |
| Hash-bound provider execution receipts | 5 | 5 | 3 | 4 | 5 |

- Completed the bounded PostgreSQL authority slice already in progress.
- Production Go runtime now injects `ProductionIdentityStore` explicitly and
  does not construct the process-memory unified identity service.
- Canonical account projection is read through migration 017 in a read-only
  `READ COMMITTED` transaction with local timeouts, strict decode, and
  commit-before-return.
- Invalid UUID, begin, timeout, projection, NULL/malformed JSON, and commit
  failures are covered. There is no implicit backend discovery or memory
  fallback.
- Missing authority returns stable `503 identity_store_unavailable`.
- Production readiness requires migration 017 account projection.
- Go tests and vet passed. TypeScript build, 634 tests, and package dry-run
  passed. TS/Python parity, CL hygiene, CL commercial, and diff checks passed.
- The first full Python attempt collected 1366 tests and reached roughly 39%
  without failure before Docker CLI calls hung. Docker Desktop was restarted;
  its backend reported the daemon ready, while the earlier `docker` resolution
  remained a hanging shim. Prepending
  `C:\Program Files\Docker\Docker\resources\bin` returned server `29.6.1`.
- The authoritative rerun of `python -m pytest tests/a1 tests/integration`
  completed: `1326 passed, 40 skipped in 107.51s`. This included the real Go
  server to Python SDK integration path.
- Evidence:
  `docs/a1/evidence/round61_postgres_identity_authority.md`.
- Peer state: `origin/dev/g3-a2-calibration` advanced to `6b62f978`; no peer
  file was merged or modified.
- Security deferrals: keep split password/MFA stores fail closed until a single
  transactional SQL operation can atomically consume tickets, mutate
  credentials, revoke sessions, enforce idempotency, and audit.

Required next-round top three:

1. Hash-bound provider records for XJTLU `gpt-5.6-sol`, Qwen official
   `qwen-plus`, and local Ollama with `endpoint_sha256`, `evidence_sha256`,
   invocation timestamp, and response binding.
2. Successful target-endpoint calibration for image/audio/file/video; accepted
   requests ending in `request_status=failed` remain `discovered`.
3. One authoritative A1 release receipt binding latest A1 SHA, provider
   records, PostgreSQL/RLS, concurrent claim/lease/fencing, and restart
   persistence evidence.

No secret, private prompt, raw private response, or credential-bearing endpoint
may enter public evidence.

## Round 62: Hash-Bound Provider And Release Receipts

Date: 2026-07-13

Baseline: clean `5dd6a898`; canonical publication remains `origin/codex/a1-local-sdk-runner`. Peer A2 advanced to `53e79b5e`; no peer files were merged or modified. Ollama HTTP was unavailable at round start. `apply_patch` was denied by the worktree ACL, so controlled PowerShell writes are used and verified by Git diff.

Commercial candidates (1-5): provider receipt chain 5/5/3/4/5; successful five-modality calibration 5/4/3/5/5; unified release receipt 5/5/2/3/5. All three are required as one trusted release chain. Real probes remain dry-run -> small batch -> bounded batch. Failed terminal media calls remain failed/discovered, never callable.
### Round 62 implementation and calibration closure

- Added Python, TypeScript, and Go chained provider receipts and a unified release receipt with canonical UTF-8 JSON, atomic stores, hash bindings, and failed-call capability suppression.
- Successful real execution now covers text/image/audio/file/video. Audio uses local open-source Whisper `tiny`; provider identity is explicit and is not represented as official Qwen success.
- XJTLU is confirmed callable by successful `gpt-5.6-sol` evidence and a five-model 200 matrix. Intermittent 502 and failed `gpt-image-2` routes remain accurately recorded.
- Public fixtures contain 17 chained receipts and no raw endpoint, prompt, response, request ID, key, or private evidence.
- Focused Python `12/12`, TypeScript `639/639`, Go tests/vet, and stable package dry-run (117 files) passed.
- Peer A2 advanced to `42dfff82`; no peer file was merged or modified.
- Evidence: `docs/a1/evidence/round62_provider_release_receipts.md`.- Final authoritative verification: Python A1/integration `1338 passed, 40 skipped in 93.29s`; TypeScript `639/639`; Go module tests and vet passed; TS/Python generated parity passed with zero Python-only exports; CL hygiene and commercial guards passed; public secret scan and owned-directory audit passed.
- Bus-Auditor follow-up capability was unavailable in this resumed tool surface: no subagent creation/message tool was exposed for the three listed agents. The main agent therefore executed the required goal, contract, owned-directory, peer-change, evidence, secret, toolchain, and release-gate audit locally and records this limitation rather than inventing a subagent result.
- Bus-equivalent decision: GO for commit/push, contingent on the new GitHub CL Gate becoming green. Next top three: provider-specific successful official audio calibration; XJTLU image-route protocol discovery; PostgreSQL-backed durable provider receipt ingestion and A3 retrieval API.

## Round 63: Live PostgreSQL Identity Security Lifecycle

Date: 2026-07-14

- Corrected the live integration harness to use the disposable PostgreSQL
  database's `clock_timestamp()` instead of a stale July 12 application clock.
  Strict session-expiry and ten-minute recent-auth validation were not weakened.
- Fresh-cluster setup now idempotently creates migration role `a1_runtime`,
  applies migrations 001 through 018, and converts only the generated
  password-authenticated runtime DSN from a Unix socket to `127.0.0.1` to avoid
  peer-auth mismatch.
- Replaced an invalid direct `two_factor_status='enabled'` fixture mutation
  with migration 018's authoritative password enrollment, TOTP begin, and TOTP
  confirmation operations.
- The live test proves three scoped security receipts are consumed and existing
  sessions are revoked after credential-security mutations.
- Added real `identity_account_security` RLS verification through a disposable
  `NOSUPERUSER NOBYPASSRLS` runtime role: one own row is visible and zero
  foreign rows are visible.
- Receipt signing-key rotation and fail-closed tamper rejection remain covered
  for ciphertext, nonce, tenant scope, and proof key version.
- Authoritative WSL/PostgreSQL 16.14 result:
  `PASS; ok github.com/ashr-labs/ashr/packages/go/ashrclone 6.954s`.
- Evidence:
  `docs/a1/evidence/round63_identity_lifecycle_live_postgres.md`.

Next: publish this focused regression slice, run Go race/vet plus complete
Python/TypeScript/parity/commercial gates, then implement a typed
PostgreSQL-backed `IdentitySecurityHTTPStore` that routes all password/MFA
mutations through migration 018 while keeping unsafe split-memory stores fail
closed.

## Round 64: Independent Lifecycle Receipt Lookup Keys

Date: 2026-07-14

- Separated lifecycle proof-encryption keys from keyed receipt-lookup keys.
- Added optional production lookup-key environment configuration with strict
  version, length, duplicate, JSON-shape, and no-secret-error validation.
- Preserved compatibility when no explicit lookup keyring is configured.
- Added byte clearing for active and previous lookup keys in runtime config,
  cloned keyrings, constructor failures, and keyring shutdown.
- Added live PostgreSQL proof that a completed credential-link replay survives
  retirement of the old encryption key when the stable lookup key remains.
- Added fail-closed proof that an unconsumed old-key receipt is locatable but
  cannot decrypt, does not leak internal key details, and does not consume
  proof, mutation-ticket, or step-up authorization state.
- Verification passed: full Go tests, Go vet, live PostgreSQL identity
  lifecycle integration, six atomic migration tests, and `git diff --check`.
- Published A1 commit:
  `6d4ba9c9c1c463267fa734c0589b509d46c96b0f`.
- Evidence:
  `docs/a1/evidence/round64_identity_receipt_lookup_key_rotation.md`.

Next: add an explicit legacy receipt-digest migration/retention readiness
report, then continue the typed PostgreSQL-backed password/MFA HTTP store
without weakening the current fail-closed split-store guard.

## Round 65: Canonical-Account Scoped Identity-Security Runtime

Date: 2026-07-14

- Added migration 022 principal-scoped PostgreSQL authorities for password/MFA
  posture, mutation-ticket resolution, and mutation execution.
- The A3-facing ticket resolver now requires the authenticated session's
  canonical account ID explicitly; returned ticket envelopes must match it.
- Every production security-store transaction installs transaction-local
  `app.a1_principal_id` before calling the scoped database authority.
- Revoked `a1_runtime` access to migration 018's old unscoped resolver and
  executor; only the scoped overloads remain executable by the runtime.
- Preserved the public-safe optional/recommended 2FA posture without exposing
  password/TOTP secret references, keyed digests, recovery batches, or session
  digests.
- Added Docker/PostgreSQL proof that a foreign canonical account cannot read
  posture, resolve a ticket, or execute a mutation and that every rejected
  attempt leaves the target ticket and receipt unconsumed.
- Proved own-account mutation succeeds and exact idempotent replay is stable.
- Updated readiness and the live lifecycle harness to require migrations
  001-022 and scoped runtime grants.
- Verification passed: full Go tests, live PostgreSQL lifecycle integration,
  31 focused PostgreSQL/RLS migration tests, and `git diff --check`.
- Evidence:
  `docs/a1/evidence/round65_scoped_identity_security_runtime.md`.

Next: publish this scoped authority, add explicit legacy receipt-digest
migration/retention readiness, then continue cross-language identity-security
client parity and production key-rotation drills.

## Round 66: Lifecycle Receipt Lookup-Key Retirement Readiness

Date: 2026-07-14

- Added migration 023 with explicit per-receipt `lookup_key_version`; existing
  rows are conservatively labeled `legacy-unversioned` because raw opaque
  receipt IDs are intentionally unavailable for re-keying.
- New receipt issuance requires an explicit nonlegacy lookup-key version, and
  the old nine-argument runtime authority is revoked.
- Added an aggregate-only, pinned-search-path PostgreSQL retirement preflight
  that exposes safe version labels, counts, a live-receipt deadline, and
  readiness booleans without exposing digests, proof material, replay payloads,
  or key bytes.
- Active, invalid, and unconfigured key retirement requests fail before any
  database query.
- Retirement remains blocked by unexpired unconsumed receipts, completed exact
  replay rows, legacy-unversioned rows, or rows outside the retained key set.
- Closed a live rotation bug by deriving credential-link idempotency, request,
  event, subject, and email fingerprints with the lookup key that actually
  matched the locked receipt rather than blindly using the new active key.
- Docker/PostgreSQL proves lookup-v1 rows are explicitly versioned, lookup-v2
  plus retained lookup-v1 preserves exact replay, and the retirement preflight
  blocks both a pending live receipt and a completed replay row.
- Verification passed: focused Go identity/lookup/credential-link tests,
  14 migration tests, full Go module tests, Go vet, command API tests, and the
  full live PostgreSQL identity lifecycle integration.
- Evidence:
  `docs/a1/evidence/round66_lifecycle_receipt_lookup_readiness.md`.

Next: define bounded credential-link replay retention and an audited purge
authority so old lookup keys can eventually retire safely, then continue
cross-language identity-security client parity.

## Round 67: Credential-Link Replay Retention and Audited Purge

Date: 2026-07-14

- Added migration 024 with an immutable 30-day replay-retention deadline for
  completed credential-link lifecycle receipts.
- Added a bounded, advisory-lock-serialized, idempotent `SECURITY DEFINER`
  purge authority using `FOR UPDATE SKIP LOCKED`.
- Added a forced-RLS durable purge audit that contains aggregate counts by safe
  lookup-key version only; direct runtime access to receipt and audit tables
  remains revoked.
- Excluded `legacy-unversioned` rows from deletion and preserved exact replay
  for the full retention window.
- Added an A3-safe typed Go purge API with HMAC-keyed request fingerprints,
  strict aggregate receipt validation, Unicode Chinese actor/reason support,
  and fail-closed readiness checks.
- Docker/PostgreSQL proves a lookup-v1 replay blocks retirement before expiry,
  purges after expiry, replays idempotently, rejects changed requests, and
  leaves no direct runtime deletion authority.
- Verification passed: 18 focused migration tests, focused and complete Go
  module tests, Go vet, live PostgreSQL lifecycle integration, and
  `git diff --check`.
- The full Python A1 suite produced `1393 passed, 2 skipped, 1 failed`; the
  isolated failure reproduces an existing test that calls migration 017's old
  binding function after migration 020 intentionally revoked it.
- Evidence:
  `docs/a1/evidence/round67_credential_link_replay_retention.md`.

Next: continue cross-language identity-security/client parity and production
lookup-key rotation drills after publishing bounded replay retention.

## Round 68: Authorized Credential-Binding Regression

Date: 2026-07-14

- Migrated the complete-suite PostgreSQL verification regression from
  migration 017's revoked direct credential-binding function to migration
  020's authorized wrapper.
- The live test now provisions a recent canonical-account session, a
  request-bound `credential_bind` step-up receipt, and a secret-free mutation
  ticket issued through the dedicated ticket authority.
- Explicitly proves `a1_runtime` can execute the authorized wrapper but cannot
  execute the old direct function.
- Injected credential insertion failure now proves atomic rollback preserves
  the verification receipt, step-up receipt, and mutation ticket for retry.
- Concurrent independently authorized requests still produce exactly one
  credential; the winner consumes its authority while the losing transaction
  leaves its own authority unconsumed.
- Exact replay, changed-request rejection, cross-scope denial, forced-RLS
  direct-mutation denial, durable outbox, and abuse-budget assertions remain
  covered.
- Verification passed: the previously failing test is green, 20 related
  PostgreSQL/RLS/authority tests pass, and the complete Python A1 suite is
  green with `1394 passed, 2 skipped`.
- Evidence:
  `docs/a1/evidence/round68_authorized_credential_binding_regression.md`.

Next: publish this authority regression, then continue production lookup-key
rotation drills and cross-language identity-security/client parity.

## Round 69: Registration/Login Session Handoff (Active Checklist)

Date: 2026-07-23

Scope: A1 only. Complete the email registration/login boundary before
continuing first-login OAuth. Never persist or log raw email addresses, OTPs,
challenge proofs, access/refresh bearers, SMTP hosts, or SMTP authorization
codes.

- [x] Continue from synchronized A1 branch
  `codex/a1-sync-publish` at `9804111916c635bbc2f4023ee5590de208e37884`;
  it exactly matches remote `codex/a1-local-sdk-runner`.
- [x] Confirm the existing Docker PostgreSQL integration container
  `ashr-oauth-pg-test` is healthy and accepting connections on its configured
  local test port.
- [x] Record this local A1 execution checklist; update each completed item
  immediately instead of relying on conversation memory.
- [x] Add a distinct `registration` verification purpose; require email and
  no pre-existing account, while keeping explicit binding account-bound and
  login non-creating.
- [x] Add migration 025 constraints and challenge issuance rules for
  accountless email registration and accountless login.
- [x] Add a single PostgreSQL transaction that creates the canonical
  principal, email credential, canonical verified email, optional/recommended
  2FA posture, organization/project memberships, and access/refresh session.
- [x] Return canonical principal and credential IDs for accountless login and
  recovery via narrow `SECURITY DEFINER` result wrappers.
- [x] Update Go PostgreSQL mutation results, principal scoping, readiness, and
  migration integration range through 025.
- [x] Add/adjust unit, SQL mock, migration, RLS, rollback, idempotency,
  duplicate-registration, canonical-account, and bearer-redaction tests.
- [x] Run the first focused Go and live PostgreSQL verification batch.
- [x] Commit and push only the first A1 registration/login transaction batch
  to remote branch `codex/a1-local-sdk-runner`.
- [x] Add canonical email registration/login HTTP begin/complete endpoints
  with browser intent, same-origin enforcement, secure HttpOnly strict cookies,
  no-store responses, and `303 /console` handoff.
  - [x] Reconfirm the clean A1-only worktree and exact remote parity at
    `030c37b5`; inspect the production HTTP/runtime wiring before editing.
  - [x] Return a browser-safe `challenge_id` plus opaque `intent_id` from the
    dedicated registration/login begin routes.
  - [x] Bind encrypted HttpOnly intent state to challenge, purpose, trusted
    tenant/project scope, normalized email, exact HTTPS origin, and expiry.
  - [x] Validate secure transport, exact same-origin, fetch metadata, strict
    JSON keys, and constant-time intent matches before durable completion.
  - [x] Issue access/refresh cookies for both registration and login, clear the
    intent cookie, and redirect with an empty `303 /console` response.
  - [x] Prove purpose isolation, replay/mismatch rejection, no secret leakage,
    and pre-mutation failure across the browser security matrix.
- [x] Run the complete A1 verification matrix and confirm no A3 files changed.
- [x] Send exactly one controlled real QQ SMTP calibration email only after
  all security tests pass; never print or commit its configuration or secrets.
- [x] Commit and push only the second A1 browser-session batch.

Next: commit and push the first transaction batch, then begin the canonical
browser registration/login session-handoff endpoints.

Progress:

- The dedicated `registration` purpose is now email-only and accountless;
  explicit `binding` and `recovery` reject a missing account, while production
  `login` remains non-creating and may resolve its canonical account from the
  verified credential.
- Docker PostgreSQL successfully rebuilt a disposable database and applied
  migrations 001-025. The existing atomic lifecycle registration regression
  and the migration-025 readiness/least-privilege additions pass against the
  live database.
- A dedicated live migration-025 test now proves that verified email
  registration atomically creates the canonical principal, credential,
  canonical email, recommended-but-disabled 2FA posture, organization/project
  memberships, and access/refresh session. It also proves that accountless
  email login resolves the same canonical account and credential.
- Duplicate registration fully rolls back without an orphan principal,
  credential, session, or consumed verification receipt; cross-project and
  cross-organization completion attempts leave the original challenge
  untouched, and the runtime role cannot directly read verification tables.
- Focused verification/readiness tests and the new Docker PostgreSQL live
  registration/login session-handoff test are green. Go build/test caches were
  moved to a disposable D-drive cache because the system drive had insufficient
  linker space; no source, Docker data, or credential material was moved.
- The complete Docker PostgreSQL identity lifecycle matrix is green across
  migrations 001-025, including replay, rollback, credential-link concurrency,
  canonical-email conflict, foreign-project rejection, and key
  rotation/tamper cases. The complete A1 package plus `ashr-api` and
  `ashr-identity-delivery` command-package tests are also green, and
  `git diff --check` reports no whitespace errors.
- The first A1-only transaction batch was committed as `ff061c39` and pushed
  to remote branch `codex/a1-local-sdk-runner`; no A3 or `apps/webapp` file was
  included.

### Immediate continuation queue (2026-07-23)

This queue is the local source of truth for the current A1 browser
registration/login closure. Check each item immediately when its evidence is
green; do not rely on chat memory.

- [x] Restore the A1-only worktree, confirm local/remote parity at `030c37b5`,
  and enumerate the uncommitted browser handoff files.
- [x] Diagnose whether valid begin responses are real verification challenges
  or anti-enumeration decoys; correct only the fake/implementation that is
  proven wrong.
- [x] Make the complete `IdentityBrowser` security matrix green, including
  registration and login `challenge_id`/`intent_id` handoff, exact-origin
  enforcement, purpose isolation, replay rejection, secret redaction, secure
  cookies, and empty `303 /console` session transfer.
- [x] Add and pass intent-expiry, production runtime `IntentKey`, and generic
  registration session-issuance regression coverage.
- [x] Run focused identity/session/readiness tests and the complete live Docker
  PostgreSQL migrations 001-025/RLS/rotation matrix.
- [x] Run complete A1 Go/cross-language tests, `git diff --check`, and verify
  that no A3 or `apps/webapp` path changed.
- [x] Commit and immediately push only this A1 browser-session batch to
  `origin/codex/a1-local-sdk-runner`.
- [x] Only after every safety test is green, send exactly one controlled QQ
  SMTP calibration message without printing, logging, or committing any real
  address, SMTP setting, authorization code, OTP, proof, or bearer; the
  provider accepted exactly one message and no retry was made.

#### Active failure-closure checklist (2026-07-23)

This checklist records the exact remaining work from the resumed task. Check
one item immediately after its focused evidence is green.

- [x] Reconfirm the independent A1 worktree/branch and classify all four
  complete-suite failures without changing A3 or `apps/webapp`.
- [x] Update the legacy live session-lifecycle tests to call migration 025's
  canonical login/recovery result wrappers, while proving the replaced direct
  wrappers remain revoked from `a1_runtime`.
- [x] Update the Round 53 source-order contract to locate the current
  `applyIdentityMutationTx` call without weakening digest-only SQL,
  post-commit bearer handoff, or bearer-redaction assertions.
- [x] Re-run the four previously failing tests and check this item immediately
  when all four are green.
- [x] Re-run all `tests/a1`, Go command packages, and the live PostgreSQL
  lifecycle/RLS/key-rotation matrix; run `git diff --check`.
- [x] Audit every changed/untracked path, commit only A1, and push only
  `HEAD:codex/a1-local-sdk-runner`.
- [x] After all tests and the A1-only push are green, send one and only one
  real QQ SMTP calibration message without exposing any secret material.

#### Single-send QQ SMTP calibration checklist (2026-07-23)

This is the crash-safe execution record for the final real-mail check. Update
each checkbox immediately; never record the address, SMTP endpoint,
authorization code, verification code, or provider response.

- [x] Reconfirm the independent A1 worktree is clean and local/remote both
  resolve to `b942ad52`.
- [x] Safely confirm the host process contains the four sender-required SMTP
  variable names without printing their values; do not inspect secret values.
- [x] Run the opt-in production SMTP sender calibration test exactly once with
  no retry and accept only its redacted success/failure result; the provider
  accepted the message once.
- [x] If accepted, mark all QQ SMTP calibration items complete and audit the
  diff for secrets, A3 paths, or `apps/webapp` paths.
- [ ] Commit only `docs/a1/worklog.md`, push only
  `HEAD:codex/a1-local-sdk-runner`, and verify local/remote parity.
