# A3 Deployment Receipt Inbox

- Date: 2026-07-13
- Route: `/delivery/?source=a3-golden-path-rc2`
- Runtime contracts: `a3.deployment_receipt.v1`, `a3.deployment_receipt_inbox.v1`
- Current candidate posture: `integrity_invalid`, `production_ready=false`

## Purpose

The previous Deployment Handoff named nine missing receipts, but it could not accept,
review, persist, or audit them. This increment turns that static list into a candidate-bound
receipt inbox while preserving all upstream authority boundaries.

The workflow is:

```text
external owner produces evidence
  -> submit sanitized metadata + SHA-256
  -> A3 validates candidate, run, blocker, scope, and secret safety
  -> reviewer acknowledges / rejects / supersedes metadata
  -> audit event + event outbox + SQLite row
  -> external authoritative verifier still required
```

`submitted` and `acknowledged` are intake states. Neither state changes Deployment
Acceptance, A2 Release Ready, or `production_verified`.

## Contracts

`a3.deployment_receipt.v1` stores only:

- five-level tenant scope;
- candidate ID and A1 run ID;
- blocker ID, owner, evidence kind, and verifier class;
- opaque evidence reference and SHA-256;
- allowlisted selectors;
- submitted/reviewed timestamps and actor hashes;
- optimistic-concurrency version and review history.

It rejects raw secrets, tokens, cookies, emails, signed URLs, local absolute paths, unknown
selector keys, wrong candidates, wrong runs, unsupported blocker classes, and invalid hashes.

`a3.deployment_receipt_inbox.v1` joins receipts to the nine current handoff blockers. It
filters out receipts from another candidate or run and always reports
`production_verified_count=0` until a future server-only authoritative readback contract is
implemented.

## API And RBAC

| Route | Permission | Result |
|---|---|---|
| `GET /api/a3/deployment/receipts` | `deployment:read` | Candidate-bound inbox |
| `POST /api/a3/deployment/receipts` | `deployment:submit` | Metadata-only submitted receipt |
| `POST /api/a3/deployment/receipts/:receiptId/review` | `deployment:review` | Acknowledged, rejected, or superseded metadata |

Both writes require `Idempotency-Key`. Review also requires `expected_version`; stale writes
return HTTP 409. The browser sends same-origin credentials and never declares its own role,
actor, or tenant authority.

There is deliberately no browser API that can mark a receipt `production_verified`, pass a
Deployment Acceptance check, or change A2 Release Ready.

## Persistence And Audit

Migration `017_deployment_receipts` adds a five-level tenant-scoped table containing metadata
and hashes only. Memory, JSON-file, and SQLite wrappers preserve receipt state. SQLite restart
coverage proves an acknowledged receipt remains version 2 while `production_verified=0`.

Each mutation writes:

- a redacted audit event;
- an `ashr.event_envelope.v1` outbox row;
- an idempotency receipt;
- a sanitized deployment receipt record.

No raw evidence file is copied into A3 storage.

## Product Surface

The Chinese-first Delivery page now includes:

- receipt, intake, missing-slot, and production-verification counters;
- a fixed candidate/run binding summary;
- a metadata submission form with blocker-derived evidence kind and verifier class;
- nine receipt slots with latest state and version;
- acknowledge and reject actions for submitted receipts;
- loading, acknowledged, rejected, conflict, denied, and failed states;
- an explicit warning that receipt intake is not production approval.

Desktop and 390 x 844 layouts were checked with Playwright. The page has no document-level
horizontal overflow; the dense receipt table uses a local scroll container on mobile.

## A1 And A2 Alignment

- A1 remains authoritative for runtime, identity, deployment, queue, storage, and GitHub
  worker facts.
- A2 remains authoritative for score, pass/fail, failure class, release policy, Decision
  Ledger, and Release Ready.
- The A2 receipt slot requires a same-candidate Trusted Spine and immutable ledger selectors.
- A3 validates and presents receipt metadata but does not execute external verifiers or
  reinterpret A1/A2 facts.

Current rc.2 facts remain unchanged:

```text
Golden Path: 7/11
Deployment Acceptance: 8/17
Current authority: integrity_invalid
Current A2 decision: unknown
Historical sealed decision: block
Production verified receipts: 0
```

## Verification

Focused evidence completed before the final broad regression:

- seven workflow, Store, API, concurrency, safety, and SQLite restart tests;
- TypeScript typecheck and 15-page Next.js production export;
- browser submit, simulated HTTP 409, permission denial, reviewer acknowledgement, and
  unchanged 8/17 acceptance;
- desktop and mobile screenshots;
- OpenAPI runtime parity at 56/56 protected operations.

Final broad regression:

- A3 Node: 429/429 passed;
- current-main A2: 186/186 passed plus 1050 subtests;
- Next.js: TypeScript passed and 15 production pages exported;
- Playwright: 38/38 passed;
- CL hygiene and Commercial CL: passed with no findings or blockers;
- root and Next.js production dependency audits: 0 vulnerabilities;
- sealed rc.2 Audit Bundle: 15/15 artifacts and 7/7 custody events passed;
- sealed rc.2 signed archive: 16/16 entries passed;
- sealed rc.2 Release Artifact: passed with manifest hash
  `8f84c5e3d4f064ae5d042b0f8ef72f2a3fb4d7ae06eb0a7d4dea01dc113d5a2f`.

The broader A1/A2 Python command reached 1239 passes and 5 skips plus 1050 subtests. The
remaining 2 failures and 26 setup errors are environment prerequisites: Go, Cargo, and
Docker/PostgreSQL are not installed on this Windows host. No A1 source was changed, so those
environment-dependent checks are recorded honestly rather than presented as green evidence.

Screenshots:

- `docs/screenshots/a3-webapp-deployment-receipt-inbox-desktop.png`
- `docs/screenshots/a3-webapp-deployment-receipt-inbox-mobile-390x844.png`

## Remaining External Blockers

This increment creates the intake and audit workflow, not the missing production evidence.
The same nine blockers still require real receipts from A1, A2, A1/A3, or the repository
maintainer. In particular, the next authority step is a new A2 Trusted Spine for
`a3-golden-20260712-002` and the exact five-level scope.

The sealed rc.2 artifact and its signed archive were not modified. This is a post-seal A3
product/API increment, not a new Release and not production deployment proof.
