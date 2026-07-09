# Round34 Growth Auditor After Round33

Date: 2026-07-09
Repo: `C:\Users\33516\Documents\Ashr_a1_clean_rebase`
Branch/status observed: `codex/a1-local-sdk-runner-clean...origin/main [ahead 15]`, clean worktree.
Scope: A1 only. No A2/A3 files inspected for mutation, and no secrets or private evidence payloads read or printed.

## Sellable Delta Since Round33

Round33 moved A1 from "contract-heavy mock control plane" toward a real paid SaaS backend boundary:

- Durable Postgres API key lifecycle exists in Go, including create/list/revoke/verify/preflight/rate-limit/snapshot.
- API keys are one-time secret reveal plus hash/prefix persistence; public envelopes do not expose stored secret hashes.
- Go protected HTTP routes now accept standard `Authorization: Bearer <secret>` and reject raw API key material in JSON bodies.
- Route-scope checks and quota preflight now happen before mutation; live proof shows quota denial does not create extra usage side effects.
- Admin API-key routes are no longer open after first bootstrap admin key; admin/read/preflight scopes exist.
- TS SDK has Bearer secret support and Go/TS/Python route evidence remains green.
- Disposable live Postgres proof covers Bearer submit, quota denial, usage readback, admin revoke, and revoked Bearer denial.

Commercial meaning: A1 can now demonstrate a credible API-key/quota control boundary for a real customer integration, not just local fixture calls. The biggest gap has shifted from "no durable auth" to "make this deployable, cross-runtime, auditable, and evidence-storing."

## Toy Gaps Still Blocking Money-Grade A1

1. Python client parity is incomplete: Python has generic hosted Bearer handling and the Python control-plane server can parse Bearer internally, but the local SaaS ingestion Python SDK and Go-server vertical smoke still use unauthenticated/bootstrap or `api_key_id`-style calls rather than ergonomic Bearer one-time-secret flows matching TS.
2. Self-host stack is not yet the target commercial stack: `infra/docker/docker-compose.self-host.yml` currently runs a Python control-plane API and profile-gated Python replay worker. It is useful scaffolding, but not the strategy's Go API + Postgres + durable worker service.
3. Object storage is a placeholder volume/file URL, not a money-grade evidence system: compose exposes `ASHR_OBJECT_STORE_URL=file:///object-store`, but A1 lacks a concrete S3/R2/MinIO-compatible evidence bundle write/readback path wired through auth, quota, audit, and tests.
4. Auth audit is not yet complete: API-key events exist, but the next sellable proof needs explicit audit events and audit-chain verification for create/revoke/rate-limit configure/quota denied across HTTP routes.
5. Tenant isolation proof is still incomplete: live RLS/tenant A/B negative proof over API keys, usage ledger, quota policies, and audit log remains a must-have before enterprise claims.
6. Worker is not a durable daemon yet: queue/job contracts and replay worker exist, but no Go worker lease loop with heartbeat, cancellation, restart, and no-side-effect denial proof is ready as a service.
7. Official hosted mutating evidence is still quota-blocked: Round29 proved the hosted quota boundary; A1 still needs a successful text mutation baseline after quota reset/plan change.
8. OAuth/billing/session remain schema/contract-level readiness, not sellable activation: useful for roadmap and frontend mirror, but they do not yet close the current backend trust gap.

## Priority Decision For This Round

Recommended Round34 priority: **Python Bearer parity first, then self-host Go API + Postgres + worker skeleton evidence if time remains.**

Rationale:

- Python Bearer parity is the smallest high-confidence slice that converts Round33's Go/TS breakthrough into a complete customer-facing integration story: Go server, TS SDK, and Python SDK all use the same one-time-secret Bearer boundary with no raw secret in bodies.
- It should be fast and low blast-radius: add Python SDK options/CLI flags/tests and extend the Go-server Python smoke to create/bootstrap an admin key, call protected routes via Bearer, prove wrong-scope/revoked/quota denial, and preserve redaction.
- It immediately improves sellability because many agent/eval users integrate from Python first.
- Self-host Go API + Postgres + worker is the next most valuable, but it is larger and should not start until Python parity closes the obvious cross-runtime gap.
- Object storage evidence should follow after self-host route/worker shape exists; otherwise it risks becoming another file-backed artifact fixture.
- OAuth/billing/session should not be Round34 P0. They are revenue-critical later, but adding provider skeletons before the durable backend/evidence substrate is money-looking, not money-grade.

Priority ranking among the requested options:

1. Python Bearer parity.
2. Self-host Go API + Postgres + worker.
3. Object storage evidence.
4. OAuth/billing/session.

## Next 20 A1 Growth Points

1. Add Python `SaaSIngestionClient` Bearer secret option for protected HTTP routes, matching TS naming semantics as closely as Python style allows.
2. Add Python CLI `--bearer-api-key` or equivalent env-backed support, with explicit redaction and no body injection.
3. Extend `tests/integration/test_a1_go_server_python_sdk.py` to create a scoped key, call Go protected routes through `Authorization: Bearer`, and assert no raw secret leaves headers.
4. Add Python tests for invalid Bearer, wrong scope, revoked key, and quota exceeded envelopes against the Go route contract.
5. Add route parity evidence showing Go, TS, and Python all support Bearer protected calls.
6. Add restart durability proof for API key create/list/verify/revoke using reopened Postgres repositories.
7. Add concurrent Postgres rate-limit race proof so two mutators cannot overspend a one-call limit.
8. Add HTTP audit events for API key create, revoke, rate-limit configure, preflight deny, and quota deny.
9. Add audit-chain verification evidence over those auth/quota events.
10. Add live tenant A/B negative proof for `api_keys`, `usage_ledger`, `quota_policies`, and `audit_log`.
11. Add no-side-effect-after-denial proofs for upload, trace ingest, artifact manifest, worker enqueue, and worker state transitions.
12. Convert self-host compose API service from Python control plane to Go `cmd/ashr-api` with Postgres DSN wiring.
13. Add self-host smoke that boots Postgres, runs migrations, creates first admin key, submits a run via Bearer, and reads usage/audit back.
14. Add Go worker daemon lease loop with graceful shutdown, heartbeat, retry, and cancellation handling.
15. Wire self-host worker profile to the Go worker daemon and prove job completion survives service restart.
16. Replace `file:///object-store` placeholder with an object storage interface that has filesystem and S3-compatible implementations.
17. Add MinIO to self-host compose or a profile, then prove evidence bundle write/readback with checksum and redacted manifest.
18. Store release evidence bundle references in Postgres and connect them to usage/audit events.
19. Add official hosted successful text mutation baseline after quota reset or plan update, then keep paid media probes one modality per audited batch.
20. Start OAuth/session only after the above: create Postgres user/session tables plus state/nonce persistence before provider-specific callbacks; start billing only with test-mode ledger and webhook verifier guardrails.

## Round34 Done Criteria

Minimum sellable Round34:

- Python SDK/CLI can call protected Go HTTP routes with Bearer one-time secret.
- Raw secret appears only in the `Authorization` header in test transport capture and is redacted from evidence/errors/log-like outputs.
- Protected submit, readback, wrong-scope denial, quota denial/no-side-effect, and revoked denial are covered from Python against Go HTTP.
- Evidence docs/snapshots update without touching A2/A3.

Stretch sellable Round34:

- Self-host compose includes Go API + Postgres smoke, or a documented partial with command-level evidence.
- First Go worker daemon skeleton leases and heartbeats a durable job.
- Audit events for auth/quota route outcomes are visible in readback.
