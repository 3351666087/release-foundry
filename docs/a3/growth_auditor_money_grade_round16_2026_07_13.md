# A3 Growth Auditor Round 16: Deployment Receipt Workflow

- Date: 2026-07-13
- Mode: fail-closed commercial audit
- Scope: receipt intake, review, RBAC, persistence, audit, API, UI, and production boundary

## Result

Round 15 points 13 and 14 are now materially implemented: A3 can accept typed receipt
metadata, reject unsafe payloads, record reviewer acknowledgement/rejection, enforce
optimistic concurrency, persist state, and expose a usable inbox. This improves enterprise
operability but does not close any of the nine external production blockers.

## 24 Ranked Growth Points

| # | Next improvement | Priority | Owner | Required evidence |
|---:|---|---|---|---|
| 1 | Generate an A2 Trusted Spine for the exact rc.2 candidate, run, and scope | blocker | A2 | evidence snapshot, ledger record, head hash, scope receipt |
| 2 | Add a server-only authoritative receipt verifier transition | blocker | A1/A3 | verifier identity, signed readback, immutable audit event |
| 3 | Prove A1 hosted identity in staging/VPC | blocker | A1 | deployment identity, issuer/audience, version, health |
| 4 | Run PostgreSQL migrations and live RLS allow/deny probes | blocker | A1/A3 | DB identity, migration digest, cross-tenant denial, same-tenant allow |
| 5 | Exercise durable queue retry, dead-letter, and lease recovery | blocker | A1 | queue identity, worker version, recovery receipt |
| 6 | Store and read back the Audit Bundle from immutable object storage | blocker | A1/A3 | object version, digest, retention, scope, readback |
| 7 | Attach staging/VPC image, config, migration, health, and network receipts | blocker | A1/A3 | deployment probe packet |
| 8 | Rehearse upgrade, injected failure, rollback, backup, and restore | blocker | A1/A3 | operation IDs, durations, final health receipt |
| 9 | Install and prove a tenant-bound GitHub App | blocker | A1/A3 | installation alias, app slug, permissions, repository binding |
| 10 | Enforce the required Check on main | blocker | maintainer | branch-policy readback and failing merge denial |
| 11 | Bind authoritative readback to the submitted receipt SHA-256 | high | A1/A3 | hash match, verifier class, readback ID |
| 12 | Add receipt expiry and stale-evidence policy | high | A3/A2 | policy version, deterministic stale classification |
| 13 | Add supersession selection in the UI | medium | A3 | old/new receipt chain and audit history |
| 14 | Add owner-specific queue filters and assignment | medium | A3 | owner, assignee hash, due state, tenant scope |
| 15 | Add receipt pagination and server-side query for large programs | medium | A1/A3 | 10k receipt performance result |
| 16 | Replace the mobile four-column table with a compact triage list | medium | A3 | 390px task-completion evidence |
| 17 | Add object-reference retention and legal-hold status | high | A1/A3 | retention class and immutable policy readback |
| 18 | Add malware/content-type scan receipts for uploaded evidence | high | A1/A2 | scanner version, result hash, quarantine state |
| 19 | Add webhook signature and replay protection for verifier callbacks | high | A1/A3 | signature validation, delivery ID, replay denial |
| 20 | Add notification subscriptions for receipt submit/reject/stale events | medium | A1/A3 | connector ref, delivery receipt, outbox linkage |
| 21 | Add receipt inbox metrics to usage and billing read models | low | A1/A3 | metered event count without billing mutation |
| 22 | Add exportable receipt index to the next Audit Bundle | high | A3 | manifest entry, content hash, verifier coverage |
| 23 | Add Postgres concurrency tests for simultaneous reviewers | high | A1/A3 | row lock or compare-and-swap 409 evidence |
| 24 | Run a customer-role usability acceptance on the complete Delivery route | medium | Product/A3 | task time, error rate, comprehension, audit export feedback |

## Security And Commercial Boundary

- No raw evidence, API key, token, cookie, email, signed URL, or local path is stored.
- Browser roles and tenant selectors are not authority in hosted mode.
- Acknowledgement is not external verification.
- A3 does not recompute A2 score, pass/fail, failure class, Decision, or Release Ready.
- The candidate remains `integrity_invalid`; the Draft PR must not be presented as a
  production-ready Release.
