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
