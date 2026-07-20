# A3 Growth Auditor Round 19: PostgreSQL RLS Qualification

- Date: 2026-07-13
- Audit mode: fail-closed commercial audit
- Scope: migration 019-to-020 upgrade, live PostgreSQL, five-level RLS, Store/API/UI evidence

## Audit Verdict

A3 now has executable PostgreSQL evidence instead of a SQL string and SQLite-only claim.
The migration 019-to-020 chain is idempotent, RLS is forced, an unprivileged role sees one allowed row and
zero foreign rows, cross-scope writes are denied, and missing scope fails closed.

This raises engineering confidence but not production acceptance. The run used a local
ephemeral database, not a deployed customer/VPC identity.

## Capability Classification

| Capability | State | Commercial meaning |
|---|---|---|
| Migration 019-to-020 on PostgreSQL 17.9 | live local verified | create and upgrade SQL execute on the target engine |
| Five-level RLS | live local verified | exact scope allow/deny behavior is proven |
| Missing-scope fail closed | live local verified | no accidental all-tenant read |
| Idempotent migration | live local verified | two applies complete successfully |
| Probe cleanup | live local verified | no probe row or role remains |
| Customer VPC identity | missing | local evidence cannot identify customer infrastructure |
| Backup/restore | missing | no data recovery receipt |
| Production A2 authority | missing | current candidate integrity remains invalid |

## 24 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Run the same probe on authorized staging PostgreSQL | blocker | A1/A3 | target alias, service identity, migration and RLS receipt |
| 2 | Bind the DB principal to five-level A1 tenant context | blocker | A1 | authenticated session-to-GUC binding readback |
| 3 | Add migration transaction and explicit rollback SQL | blocker | A1/A3 | failed apply, rollback, schema digest restored |
| 4 | Add TLS certificate and hostname verification | blocker | A1 | TLS mode, CA alias, expiry class, successful verification |
| 5 | Add KMS-backed credential-reference rotation | high | A1 | old/new secret-ref aliases and zero plaintext exposure |
| 6 | Prove API connection pooling resets all scope GUCs | blocker | A1 | tenant A request followed by tenant B on reused connection |
| 7 | Prove transaction-local scope cannot leak across requests | blocker | A1/A3 | post-commit missing-scope query returns zero rows |
| 8 | Add RLS policy drift hash and catalog verifier | high | A1/A3 | expected/actual policy digest and fail-closed mismatch |
| 9 | Add migration ledger with checksum and actor identity | high | A1 | immutable apply/rollback sequence |
| 10 | Execute backup, restore, and row-hash comparison | blocker | A1/A3 | backup id, restore id, before/after digest |
| 11 | Execute point-in-time recovery | blocker | A1 | recovery target, timeline, audit continuity |
| 12 | Test 10k calibration rows and index plan | high | A1/A3 | EXPLAIN plan, p95 latency, bounded memory |
| 13 | Test concurrent same-tenant writers | high | A1/A3 | conflict behavior and no duplicate digest |
| 14 | Test concurrent cross-tenant attacks | blocker | Security | zero leaked rows and denied writes |
| 15 | Add retention and legal-hold policy to calibration rows | high | A1/A3 | purge denied/allowed receipts |
| 16 | Store qualification evidence in real object custody | blocker | A1 | object version, checksum, retention, tenant scope |
| 17 | Bind database receipt to signed container digest | blocker | A1/A3 | image digest, SBOM, runtime readback |
| 18 | Run migration inside the self-host Compose stack | blocker | A1 | service identities, dependency health, network aliases |
| 19 | Run restricted-network install drill | blocker | A1/A3 | denied public egress and successful internal path |
| 20 | Execute N-1 to N upgrade through migration 020 | blocker | A1/A3 | pre/post version, health, data digest |
| 21 | Trigger failed upgrade and automatic rollback | blocker | A1/A3 | failure trigger, rollback action, restored health |
| 22 | Generate same-candidate A2 Trusted Spine | blocker | A2 | exact candidate/run/scope Decision Ledger |
| 23 | Rebuild candidate-bound Audit Bundle and Release Artifact | blocker | A1/A2/A3 | Git SHA, A1 run, A2 ledger, A3 manifest |
| 24 | Conduct operator test of the DB qualification panel | medium | Product/A3 | task completion, comprehension, error rate |

## Highest-value Sequence

1. Run the exact probe with deployed A1 identity in staging.
2. Prove connection-pool scope reset and cross-request isolation.
3. Add rollback plus backup/restore receipts.
4. Bind the result to container, VPC, and same-candidate A2 evidence.
5. Rebuild the signed release packet only after those receipts are authoritative.

## Non-negotiable Boundaries

- Local PostgreSQL evidence does not raise Deployment Acceptance `8/17`.
- A3 never creates A2 score, failure class, Decision, or Release Ready.
- CLI arguments never accept passwords or full DSNs.
- A successful public receipt requires probe cleanup.
- No host, credential, account, raw SQL output, or local path enters public artifacts.
- The sealed rc.2 bundle remains historical and unchanged.
