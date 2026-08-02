# A3 Growth Auditor Round 18: Self-host Sandbox Operations

- Date: 2026-07-13
- Audit mode: fail-closed commercial audit
- Scope: A1 local runtime probe, Store/SQLite, API/RBAC/audit, Delivery UI, E2E

## Audit Verdict

This round adds one executable, sellable workflow: an enterprise operator can inspect a
real A1-backed local readiness receipt in the A3 console. The workflow proves local health,
worker recovery, dead-letter behavior, object readback, and tamper detection.

It remains `sandbox_verified`, not `production_verified`. The current buyer cannot yet sign
off on PostgreSQL isolation, workload identity, container provenance, VPC networking,
upgrade/rollback, or same-candidate A2 authority.

## Capability Classification

| Capability | State | Why |
|---|---|---|
| A1 local control-plane probe | implemented | executable Python and Node integration tests pass |
| Worker retry/DLQ/lease recovery | implemented in sandbox | real A1 service behavior executed locally |
| Object readback/tamper detection | implemented in sandbox | real local storage contract executed and negative-tested |
| Tenant-scoped read API and RBAC | implemented | hosted access denies viewer/cross-scope and audits decisions |
| SQLite calibration durability | implemented locally | migration 019 and restart test pass |
| PostgreSQL/RLS | contract-supported only | no target server receipt |
| Container/VPC/upgrade operations | not production verified | no target environment or operator authorization |
| A2 Release Decision | unresolved for current candidate | current integrity invalid; historical decision block |

## 24 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Run migration 019 on a real PostgreSQL instance | blocker | A1/A3 | migration digest, schema readback, rollback SQL |
| 2 | Add two-tenant RLS allow/deny tests for calibrations | blocker | A1/A3 | same-tenant 200, cross-tenant 403/zero rows |
| 3 | Run the probe in the self-host Compose stack | blocker | A1 | Compose identity, service health, network aliases |
| 4 | Bind probe output to a signed container image digest | high | A1/A3 | image digest, signature, runtime readback |
| 5 | Add SBOM and provenance verification to the panel | high | A1/A3 | SBOM hash, builder identity, verifier receipt |
| 6 | Replace local object storage with MinIO/S3-compatible custody drill | blocker | A1 | bucket scope, version, checksum, retention receipt |
| 7 | Replace in-process queue with Redis/durable queue drill | blocker | A1 | lease, retry, DLQ, restart recovery receipt |
| 8 | Add poison-message and duplicate-delivery tests | high | A1 | dedupe key, attempt chain, one final side effect |
| 9 | Add VPC ingress/egress policy readback | blocker | A1 | allowed service path and denied public egress proof |
| 10 | Bind workload identity to tenant/environment | blocker | A1 | issuer, audience, workload alias, scope readback |
| 11 | Execute a versioned upgrade from N-1 to N | blocker | A1/A3 | before/after version, migration, health, data digest |
| 12 | Trigger a failed upgrade and automatic rollback | blocker | A1/A3 | failure trigger, rollback action, recovered health |
| 13 | Run backup/PITR/restore with audit continuity | blocker | A1/A3 | backup ID, restore point, row/hash comparison |
| 14 | Build an offline install and verification packet | high | A1/A3 | image bundle, checksums, license, no-network smoke |
| 15 | Add support-bundle generation with redaction scan | high | A1/A3 | bundle manifest, secret scan, operator download audit |
| 16 | Add SLO metrics for health, lease age, retry, and DLQ | high | A1/A3 | metric scrape, alert trigger, recovery timestamp |
| 17 | Add 10k calibration pagination/query-plan test | medium | A1/A3 | p95 latency, memory, index plan, tenant isolation |
| 18 | Sign calibration payloads and verify key rotation | high | A1/A3 | signature, key ID alias, old/new key tests |
| 19 | Generate same-candidate A2 Trusted Spine | blocker | A2 | exact run/scope, snapshot, ledger head, decision |
| 20 | Rebuild one candidate-bound Release Artifact | blocker | A1/A2/A3 | Git SHA, A1 evidence, A2 ledger, A3 manifest |
| 21 | Install a tenant-bound GitHub App | blocker | A1/A3 | installation binding and Check App readback |
| 22 | Enforce main required Check and test merge denial | blocker | maintainer | branch policy and rejected failing merge |
| 23 | Run accessibility and keyboard review of deployment operations | medium | A3 | axe report, focus order, no trap, 390px evidence |
| 24 | Conduct an operator task test with a self-host buyer | high | Product/A3 | task time, comprehension, error rate, sign-off gaps |

## Highest-value Sequence

1. PostgreSQL/RLS plus durable queue/object storage turns the local proof into a realistic data plane.
2. Same-candidate A2 authority restores a trustworthy release decision.
3. Container/VPC/upgrade/rollback receipts make deployment acceptance meaningful.
4. Tenant GitHub App plus required-check enforcement closes repository governance.
5. A rebuilt, signed audit packet can then support enterprise sign-off.

## Non-negotiable Boundaries

- Sandbox evidence never raises `8/17`.
- A3 never creates or recomputes A2 score, failure class, Decision, or Release Ready.
- No fixture, page, OpenAPI schema, or local DB row is production proof by itself.
- No API key, token, cookie, email, signed URL, raw payload, or private local path enters artifacts.
- The sealed rc.2 evidence remains historical and unchanged.
