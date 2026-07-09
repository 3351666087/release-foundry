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
