# Round 45 Growth-Auditor / Money-Grade Audit

Audit date: 2026-07-10 (Asia/Shanghai)
Repository: `C:\Users\33516\Documents\ReleaseFoundry_a1_clean_rebase`
Branch: `agent/a1-local-sdk-runner-clean`
Baseline commit: `5dbf4ee2ab4c`
Verdict: **Conditional commercial foundation; not money-grade production ready.**

## 1. Audit Scope And Rules

This audit evaluates A1 against `docs/strategy/large-saas-a1-a2-a3-full-plan.md`, with emphasis on revenue-bearing and durable SaaS boundaries: payment, OAuth, worker recovery, Postgres, MinIO/object storage, API keys, quota, TypeScript parity, and the Go primary backend.

The auditor did not write ordinary business code. This document is the only auditor-owned file. Existing working-tree changes were treated as parallel work and were not modified, staged, reverted, or claimed as stable baseline capability.

The current worktree contains concurrent changes in:

- `infra/docker/Dockerfile.go-runtime`
- `infra/docker/docker-compose.self-host.yml`
- `infra/docker/self-host.env.example`
- `packages/go/releasefoundry/postgres.go`
- `packages/go/releasefoundry/postgres_test.go`
- `packages/go/releasefoundry/service.go`
- `packages/go/releasefoundry/service_test.go`
- `packages/ts/releasefoundry/src/saas.ts`
- `services/api/billing.py`
- `services/api/control_plane.py`
- `services/runner/a1_docker_healthcheck.go`
- `tests/a1/test_billing_provider_contract.py`
- `tests/a1/test_payment_oauth_safety.py`
- untracked commercial Compose, migration, MinIO, worker recovery, worker entrypoint, and Go live-test files

These changes are approximately 1,002 insertions and 73 deletions in tracked files. They are promising Round 45 candidate work, not released capability. No peer branch changes were imported. The only active peer branch observed was `origin/dev/g3-a2-calibration`, whose changes are A2 evidence-readiness work and do not alter this A1 audit.

## 2. Round Baseline

### Stable HEAD evidence

- Python SDK, adapter, runner, trace/replay, fixtures, API client, and local control-plane contracts exist.
- TypeScript SDK has broad SDK/runner/cloud/control-plane coverage; its current suite reports `342 passed`.
- Go has the primary backend vertical slice, 40 manifest routes, Postgres repository support, API-key/quota/usage/audit/worker/billing contracts, and a worker executable; `go test ./...` passes.
- Python, TypeScript, and Go expose deliberate rather than absolute route parity:
  - Go: 40 routes
  - TypeScript: 35 routes
  - Python: 29 routes
- API-key lifecycle, scopes, revocation, rate-limit buckets, idempotency, usage receipts, quota contracts, audit-chain verification, release evidence, trace ingestion, run upload, and artifact manifests have substantial local tests.
- Round 44 official ReleaseFoundry API evidence is real but read-only: 5 successful read steps, 7 estimated calls, 0 mutation steps, 0 quota blocks, 3 datasets, and 5 requests.
- Public payment readiness explicitly remains plan-only and states `provider_called: false`, `checkout_or_portal_called: false`, and `real_charge_possible: false`.
- Public object-storage evidence explicitly states that no real MinIO/S3 network call is required or performed.
- Public self-host evidence explicitly labels the runtime as a scaffold rather than a production deployment.

### Current candidate-work verification

| Check | Result | Money-grade interpretation |
| --- | --- | --- |
| Focused payment/OAuth pytest | `30 passed, 1 failed` | OAuth public snapshot leaks a durable `provider_code_ref`; auth flow is not public-safe yet |
| Full A1 pytest from prior audit pass | `418 passed, 1 failed` | Broad local confidence, but the OAuth failure remains a release blocker |
| Go `go test ./...` | pass | Go candidate worker/repository changes compile and pass unit tests |
| TypeScript `npm test` | `342 passed, 0 failed` | Strong local parity, but no production provider/runtime proof |
| Postgres integration subset | `9 passed, 5 skipped` | Live DSN behavior remains unproven in this environment |
| Commercial Compose config | fail | `worker` depends on undefined `worker-recovery-seed` under the selected `commercial` profile |
| CL hygiene/commercial guards | pass in prior audit | Secret/evidence policy is healthy, but guards do not prove runtime durability |
| `git diff --check` | pass in prior audit | Formatting check only; CRLF normalization warnings remain |

### Environment evidence

- Docker Desktop, Docker Engine 29.6.1, and Compose v5.2.0 are available.
- WSL Docker runtime is available; `Ubuntu-24.04-ReleaseFoundry` was stopped at inspection time.
- `RELEASEFOUNDRY_API_KEY` is present by length-only environment inspection. Its value was not read or logged.
- `A1_POSTGRES_TEST_DSN`, Stripe secrets, and object-storage endpoint/credential environment variables were absent during the audit.
- No official ReleaseFoundry API call and no payment-provider call was executed by this auditor.

## 3. Current Sellable Capability

The following can be sold honestly today as a **developer preview, self-host evaluation kernel, or commercial foundation**:

1. Local Python and TypeScript SDK integration for external agents.
2. Agent adapter normalization across callable/object/OpenAI-style response shapes.
3. Batch runner execution, timeout/error normalization, and replayable run fixtures.
4. Trace, observation, tool-call, and VM-stream capture with public-safe redaction.
5. Text, audio, file, image, and video request envelopes as first-class modalities.
6. Tenant/project/dataset/request/run lifecycle contracts.
7. API-key issue/verify/revoke, scope checks, rate-limit buckets, and restart-safe local snapshots.
8. Quota and usage-ledger contracts with deny-before-mutation tests.
9. Run upload, trace ingestion, artifact manifest, release evidence, and audit-chain contracts.
10. Go HTTP vertical slice with a Postgres repository option.
11. Python/TypeScript/Go route manifests and explicit unsupported-gap evidence.
12. Local worker lease, heartbeat, retry, dead-letter, and stale-owner behavior.
13. Public-safe payment plan and webhook-envelope contracts.
14. Static Docker Compose and Terraform self-host topology.
15. Read-only official ReleaseFoundry API field calibration with private raw evidence and public summaries.

The sellable claim must stop at **foundation/preview**. The repository does not yet support an honest production-ready claim for live billing, OAuth login, durable worker recovery, network object storage, production self-host operation, or a fully exercised money path.

## 4. Toy Or False-Maturity Risks

1. **Test-count theater:** 342 TypeScript tests and hundreds of Python tests are valuable, but most execute local/in-memory contracts. Counts cannot substitute for provider, database, process-restart, or network proof.
2. **Plan-only payment mistaken for billing:** checkout plans and webhook envelopes do not create sessions, move money, reconcile invoices, handle disputes, or issue refunds.
3. **OAuth-shaped data mistaken for login:** provider config and PKCE records do not prove browser redirect, callback exchange, token rotation, revoke, account linking, or provider outage handling.
4. **Postgres adapter mistaken for durable SaaS:** skipped live tests leave transaction isolation, RLS, crash recovery, migration safety, and connection failure behavior unproven.
5. **Manifest mistaken for object storage:** an S3-compatible manifest is not evidence of PUT/HEAD/GET, checksum, retention, encryption, presigning, deletion, or tenant denial.
6. **Worker loop mistaken for production worker:** a polling executable without restart/reclaim/dead-letter evidence against real Postgres is still a scaffold.
7. **Static Compose mistaken for deployability:** the current candidate Compose profile does not even render successfully for `commercial`.
8. **Reference leakage mistaken for redaction:** a vault/provider reference can still be sensitive correlation material. The current OAuth snapshot exposes `provider_code_ref`.
9. **Route-count parity mistaken for semantic parity:** Go, TS, and Python have intentional route differences and must be compared by behavior and schema, not raw counts.
10. **Quota record mistaken for enforcement:** quota is money-grade only when atomic with the durable side effect and idempotent across retries/restarts.
11. **API-key hashing mistaken for identity:** enterprise auth additionally needs actor identity, session lifecycle, RBAC, rotation, compromise response, and immutable audit attribution.
12. **Read-only ReleaseFoundry calibration mistaken for competitive parity:** Round 44 did not exercise mutation, paid media, run submission, trace upload, or quota behavior.
13. **Provider-neutral Terraform mistaken for infrastructure:** no concrete cloud target, IAM policy, secret manager, backup, restore, alerting, or rollback has been proven.
14. **Healthy endpoint mistaken for readiness:** readiness must fail closed on wrong backend, unavailable migrations, stale worker heartbeat, unavailable storage, and broken quota ledger.

## 5. P0/P1 Money-Grade Matrix

| Domain | P0 before money-grade claim | P1 after P0 |
| --- | --- | --- |
| Payment | Fix Stripe verification so timestamp and HMAC failures are independently reported; run Stripe test-mode Checkout/Portal and signed webhook reconciliation; prove idempotency, ledger posting, refund/void path, and no raw payment data | WeChat Pay and Alipay cryptographic adapters; subscription changes, proration, disputes, tax/invoice evidence, live-mode runbook and approval gate |
| OAuth | Remove `provider_code_ref` from public snapshots/audit; pass PKCE/state/replay/redirect/provider-error tests; execute GitHub and Google test login callbacks with token refs only | Account linking/unlinking, refresh/revoke, organization mapping, SSO policy, provider outage recovery, session risk controls |
| Worker | Real Postgres enqueue/lease/heartbeat/complete; kill process; reclaim expired lease; retry; dead-letter; prove evidence and usage receipts survive restart | Backpressure, fair scheduling, poison-job quarantine, autoscaling, graceful drain, SLOs, multi-region ownership |
| Postgres | Supply live DSN; apply migrations; prove RLS cross-tenant denial, transaction rollback, idempotency conflict, lease concurrency, and restart persistence | Migration checksum/rollback, PITR backup/restore, pool saturation tests, replica/read strategy, partition/retention policy |
| MinIO/object storage | Real Compose PUT/HEAD/GET/checksum; tenant-scoped key denial; fail closed when storage is unavailable; prove artifact/evidence linkage | Presigned upload/download, retention/legal hold, lifecycle cleanup, encryption/KMS refs, multipart, R2/S3 parity, backup/restore |
| API key | Persist create/reveal-once/hash/verify/revoke/rate-limit; prove revoke and rate limits survive API restart; enforce scope before side effects | Rotation overlap, last-used attribution, IP/network policy, organization policy, anomaly detection, break-glass workflow |
| Quota | Make reserve/consume/release atomic with Postgres ingestion and idempotency; prove denial before trace/artifact/run side effects and no double charge after retry | Reservations, overage pricing, billing-cycle reset, usage export, reconciliation, customer-visible metering, alerts |
| TypeScript | Add typed OAuth candidate surface tests; consume one OpenAPI source of truth; prove semantic contract parity for every shared route and every modality | Generated client release pipeline, browser/Node compatibility, ESM/CJS policy, version negotiation, deprecation tooling |
| Go | Fix commercial profile wiring; prove fail-closed readiness; complete durable worker and storage integration; make Go schemas authoritative for public API | Webhook/billing executors, observability, profiling, load/soak tests, graceful deploy, concrete cloud release service |

## 6. Executable Growth Backlog

The following are implementation-sized, evidence-bearing growth points. They are ordered by revenue risk and dependency, not by code volume.

### Payment And OAuth

1. Change Stripe verification to validate every supplied signature even when timestamp tolerance fails; return both independent failure reasons.
2. Add Stripe raw-body tests for valid, altered body, stale timestamp, multiple `v1` signatures, malformed header, wrong secret ref, and test/live secret mismatch.
3. Remove provider authorization-code references from all public OAuth flow snapshots and audit payloads; retain only a one-way digest/presence bit if required.
4. Add an OAuth public-safety scanner covering state, verifier, authorization code, access token, refresh token, and durable secret references.
5. Run begin-to-complete GitHub PKCE flow tests through the HTTP/router boundary.
6. Add state mismatch, state replay, verifier mismatch, redirect mismatch, expired flow, provider denial, and duplicate callback tests.
7. Add Google OAuth provider tests with the same contract and prove provider-specific scopes do not change the shared session envelope.
8. Add OAuth session revoke and provider-token revoke reference workflow; prove revoked sessions fail closed.
9. Introduce a Stripe test-mode executor behind an explicit provider-execute route, secret refs, approval flag, and private evidence sink.
10. Execute one smallest-scope Stripe test-mode Checkout and signed webhook flow; reconcile the provider object to the internal billing ledger.
11. Add Stripe refund/void test-mode evidence and prove the ledger reverses or offsets usage exactly once.
12. Implement WeChat Pay and Alipay webhook signature verification behind key/certificate references without storing raw notification bodies.

### Durable Runtime And Postgres

13. Fix Compose profile closure so `commercial` and `commercial-smoke` each resolve every `depends_on` service.
14. Boot Postgres, Redis, MinIO, Go API, migrations, and worker from a clean volume and capture bounded health evidence.
15. Make migration readiness fail closed when the expected schema/version/checksum is absent.
16. Enqueue a worker job through the Go API and lease it from the long-running Go worker against real Postgres.
17. Prove heartbeat extends but never shortens a lease, and rejects stale/non-owner heartbeats.
18. Kill the worker after lease acquisition, wait for expiry, restart it, and prove exactly one reclaim and completion.
19. Force handler failure through retry to dead-letter; verify sanitized error, audit event, usage receipt, and terminal row persist.
20. Run two worker processes against the same queue and prove `SKIP LOCKED`/equivalent prevents double lease.
21. Add live RLS tests for org/project/user/session/API key/quota/run/trace/artifact/worker/billing rows using a `NOBYPASSRLS` role.
22. Add transaction-failure injection showing quota, usage, audit, and target mutation commit or roll back as one commercial operation.
23. Add migration checksum ledger, forward-only policy, idempotent apply proof, and a tested rollback/restore procedure.
24. Execute Postgres backup and restore into a fresh volume; compare tenant, quota, worker, audit, and billing invariants.

### Object Storage, API Keys, And Quota

25. Execute a real MinIO PUT using a tenant/project/run-scoped key and secret refs supplied only at runtime.
26. Execute HEAD and GET; verify content length, content type, ETag/metadata policy, SHA-256, and manifest signature.
27. Tamper with stored bytes or manifest metadata and prove release evidence verification blocks.
28. Prove cross-tenant object-key reads and manifest lookups are denied at API and storage-policy layers.
29. Stop MinIO during artifact/trace processing and prove the operation fails closed or enters a recoverable pending state without issuing a false success receipt.
30. Persist API-key create/reveal-once/hash/verify/revoke/rate-limit state in Postgres and prove behavior survives API restart.
31. Add concurrent quota reservation tests so two requests cannot overspend the same final unit.
32. Prove idempotent retries return the original receipt and do not double-consume quota, write duplicate objects, or append duplicate billing usage.
33. Add reserve/commit/release semantics for long-running media/run jobs and reconcile abandoned reservations after worker crash.
34. Produce a customer-visible usage export whose totals reconcile to durable quota and billing ledger rows.

### TypeScript, Go, Operations, And Competitive Calibration

35. Generate TypeScript and Python clients from one versioned Go/OpenAPI contract and fail CI on handwritten route/schema drift.
36. Add shared golden request/response/error fixtures for every route common to Go, TypeScript, and Python.
37. Add TypeScript OAuth provider/flow/session methods, router/HTTP client/CLI coverage, and public-safety tests matching Python behavior.
38. Add text/audio/file/image/video semantic parity tests across Python, TypeScript, and Go, including quota units and artifact linkage.
39. Add Go metrics, structured logs, trace IDs, readiness dependencies, worker lag, quota denials, storage failures, and payment/OAuth counters.
40. Run Go API and worker load tests with 30-80 case runs, at least four workers, concurrent trace upload, and restart injection.
41. Turn provider-neutral Terraform into one concrete target with network policy, managed Postgres, object storage, secret manager, IAM, alarms, and rollback.
42. Add release automation that applies migration checks, boots smoke runtime, validates object/worker/payment/OAuth evidence, and publishes a signed readiness bundle.
43. Refresh official ReleaseFoundry API mutation gating and execute a bounded text mutation before paid media.
44. Execute bounded audio, file, image, and video official API probes only after fresh quota evidence; convert every observed field/error/quota difference into fixtures and tests.

## 7. Parallel Work Groups

### Group A: Payment/OAuth security

Owns points 1-12. It can proceed independently using Python contract code and tests. Its first exit condition is zero secret/reference leakage and a fully green focused suite. Provider execution remains test-mode and private-evidence only.

### Group B: Go/Postgres worker durability

Owns points 13-24. It must own Compose profile closure, migration readiness, live Postgres worker recovery, RLS, transactions, and backup/restore. It should not wait for payment/OAuth.

### Group C: MinIO/API key/quota money path

Owns points 25-34. It must connect durable API-key and quota enforcement to actual network object side effects. It should share the Compose environment with Group B but use separate tests and evidence paths.

### Group D: TypeScript/OpenAPI parity

Owns points 35-38. It can run in parallel once the Go route/schema artifact is stable for the round. It must measure semantic parity, not target a cosmetic test-count equality.

### Group E: Operations and calibration

Owns points 39-44. Observability and load work can begin immediately. Official mutation probes must wait for a fresh reviewed quota gate, then proceed dry-run -> text small batch -> paid media small batch. No secret values belong in commands, stdout, public docs, or commits.

### Merge order

1. Payment/OAuth P0 safety fixes and Compose profile closure.
2. Live Postgres/worker and MinIO smoke.
3. Durable API-key/quota atomicity.
4. Generated-client and modality parity.
5. Provider test-mode execution, load/restore evidence, and official API bounded mutation.

## 8. Acceptance Evidence

Money-grade status requires machine-readable or reproducible evidence for every item below:

1. Focused payment/OAuth suite reports zero failures and scans snapshots/audit for all forbidden state, verifier, code, token, and secret-reference material.
2. Stripe test-mode private evidence contains provider object references and hashes only; public summary proves signed webhook reconciliation, duplicate handling, and refund/void outcome.
3. GitHub and Google OAuth private evidence proves redirect/callback completion, PKCE, state replay denial, token refs only, revoke, and session denial after revoke.
4. `docker compose ... --profile commercial config --quiet` and `--profile commercial-smoke config --quiet` both pass without undefined services.
5. Clean-volume Compose boot reports Go API `backend=postgres_repository_v0`, `backend_ready=true`, `local_only=false`.
6. Migration evidence includes version, checksum, apply timestamp, clean-volume result, and mismatch fail-closed result.
7. Worker evidence records enqueue, lease owner, heartbeat, forced kill, lease expiry, reclaim owner, exactly-once terminal state, retry, and dead-letter.
8. Two-worker concurrency evidence proves no duplicate active lease or duplicate completion.
9. Live RLS evidence proves cross-tenant denial for every money-bearing table.
10. Transaction fault evidence proves target row, quota, usage, billing, and audit are atomic.
11. MinIO evidence records PUT/HEAD/GET status, object key shape, byte count, content type, expected/actual SHA-256, manifest signature result, and tenant denial.
12. API-key evidence proves one-time reveal, persisted hash verification, restart-safe revoke, restart-safe rate limit, and actor attribution.
13. Quota evidence proves concurrent final-unit contention, idempotent replay, reservation recovery, and ledger reconciliation.
14. Backup/restore evidence compares row counts and integrity hashes before and after restore.
15. OpenAPI generation evidence proves generated TypeScript/Python clients are clean and shared golden fixtures pass against Go.
16. Modality parity evidence proves text/audio/file/image/video share lifecycle, error, quota, trace, and artifact semantics.
17. Load evidence proves 30-80 cases per run, at least four workers, bounded latency/error targets, no trace loss, and trace completeness at or above 95%.
18. Observability evidence shows request ID, tenant/project-safe dimensions, worker lag, quota denial, storage error, OAuth failure, and billing webhook metrics without secret values.
19. Official ReleaseFoundry calibration public summaries expose only status, response keys, quota/error shape, and private evidence references.
20. CL hygiene/commercial guards, secret scan, full A1 tests, Go tests, TypeScript tests, integration tests, Compose smoke, and `git diff --check` all pass on the same commit.

## 9. Evidence Ledger

Primary sources used:

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- `docs/a1/worklog.md`
- `docs/a1/payment_provider_readiness.md`
- `docs/a1/evidence/payment_provider_readiness_public.json`
- `docs/a1/evidence/object_storage_contract_20260709.md`
- `docs/a1/evidence/self_host_commercial_runtime_scaffold_20260709.md`
- `docs/a1/evidence/official_api_readonly_round44_summary_20260710_001500.json`
- `docs/a1/evidence/go_python_ts_route_parity_snapshot.json`
- current Git status, diff, code, and test output

Evidence discoverability gap:

- The expected Markdown artifact `docs/a1/ts_python_gap_matrix.md` does not exist. Route parity evidence is available in JSON, but the missing human-readable index makes contract maturity harder to audit.

## 10. Commands And Results

```powershell
git status -sb
git diff --name-only
git diff --stat
git remote -v
git branch -r --contains HEAD
gh pr list --state all --limit 20
```

Result: baseline and concurrent work identified; PRs 27, 29, and 30 are merged; A2 peer branch observed and not imported.

```powershell
python -B -m pytest tests/a1/test_billing_provider_contract.py tests/a1/test_payment_oauth_safety.py -q -p no:cacheprovider
```

Result: `30 passed, 1 failed`. Failure: completed OAuth flow exposes `vault:github/code/round45` as `provider_code_ref` in the commercial auth/payment snapshot.

```powershell
go test ./...
```

Run from `packages/go/releasefoundry`. Result: pass.

```powershell
npm test --prefix packages/ts/releasefoundry
```

Result: `342 passed, 0 failed`.

```powershell
docker compose --env-file infra/docker/self-host.env.example -f infra/docker/docker-compose.self-host.yml --profile commercial config --quiet
```

Result: fail. The selected profile has `worker` depending on undefined service `worker-recovery-seed`. The shell also lacks `RELEASEFOUNDRY_POSTGRES_AUTH_SECRET`; only its environment name was observed, never a value.

Previously verified during this audit cycle:

```powershell
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B -m pytest tests/integration/test_a1_large_saas_migration.py tests/integration/test_a1_large_saas_migration_live.py tests/integration/test_a1_billing_ledger_migration_live.py -q -p no:cacheprovider
python scripts/cl_guard.py hygiene
python scripts/cl_guard.py commercial
git diff --check
```

Results: A1 `418 passed, 1 failed`; integration `9 passed, 5 skipped`; CL guards pass; diff check passes with CRLF warnings. Live Postgres skips are a P0 evidence gap, not a green production result.

## 11. Failures And Immediate Next Step

Current blockers:

1. OAuth completed-flow public snapshot leaks `provider_code_ref`.
2. Commercial Compose profile is structurally invalid because of profile-dependent `depends_on`.
3. Live Postgres tests are skipped due absent DSN.
4. No real MinIO PUT/HEAD/GET evidence exists yet.
5. Payment remains plan-only; no Stripe test-mode provider object or reconciliation evidence exists.
6. Worker restart/reclaim/dead-letter is not yet proven end-to-end against real Postgres.
7. Official API evidence remains read-only; there is no fresh mutating/paid-media calibration in this round.

Immediate next sequence:

1. Fix OAuth reference redaction and Compose profile closure, then rerun the focused suites and both Compose profiles.
2. Bring up the clean commercial smoke stack and capture Postgres worker recovery plus MinIO checksum evidence.
3. Bind API-key/quota enforcement atomically to durable run/trace/artifact side effects.
4. Add generated OpenAPI client parity and TypeScript OAuth coverage.
5. Only after those gates are green, execute Stripe test-mode and bounded official ReleaseFoundry mutation calibration with private evidence.
