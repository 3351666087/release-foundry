# A3 Auth/RBAC Boundary Contract - 2026-07-09

ANCHOR: A3_AUTH_RBAC_BOUNDARY_CONTRACT

## Goal

Move A3 one step closer to the commercial SaaS strategy bus without claiming
that real hosted login is finished.

This round adds a metadata-only Auth/RBAC boundary that lets A3 answer:

- Who is the redacted actor?
- Which organization/tenant/workspace/project is being accessed?
- Which role and permissions are attached?
- Which A3 operation is allowed, denied, plan-only, or blocked until hosted auth?
- Which metadata-only audit event would be emitted?

## What Changed

- Added `services/report/a3_auth_rbac_boundary.mjs`.
- Added local A3 API routes:
  - `GET /api/a3/auth/context`
  - `GET /api/a3/auth/rbac-policy`
  - `POST /api/a3/auth/authorize`
- Added Auth/RBAC boundary state to SaaS Admin Console output.
- Added Auth/RBAC boundary rendering to the dashboard SaaS Admin panel.
- Added Auth/RBAC boundary evidence to SaaS Admin report export.
- Added `auth_rbac_boundary` to Artifact Registry and security audit packets.
- Added SQL contract tables:
  - `auth_contexts`
  - `rbac_policy_snapshots`
  - `authz_decisions`
- Updated the A3 OpenAPI artifact with Auth/RBAC boundary routes and schemas.
- Added `tests/a3/a3_auth_rbac_boundary.test.mjs`.

## What This Is Not

This is not real production authentication.

It does not create users, sessions, cookies, OAuth flows, API keys, team invites,
or public Trust publishing. Those remain blocked until A1 provides hosted auth,
server-side RBAC, durable audit, and secret-safe credential handling.

## A1/A2 Compatibility

A1 remains source of truth for:

- hosted auth middleware
- session validation
- service-account validation
- API key backend
- tenant isolation
- durable audit and usage ledgers

A2 remains source of truth for:

- security verification
- abuse cases
- release policy
- redaction and verifier correctness

A3 only displays and checks product-workflow permissions. It does not mutate A1
runner/auth/storage behavior or A2 judge/release semantics.

## Safety

- Raw actor identity is redacted.
- Actor identity is represented as `actor_hash`.
- API keys, tokens, cookies, emails, and real account values are not stored or
  returned.
- Hosted mutations such as API-key rotation, team invite, and Trust publishing
  remain blocked without hosted auth.
- Authz decisions include metadata-only `ashr.event_envelope.v1` audit records.

## Current Status

This is a contract spine, not a finished auth product.

It closes the immediate A3 gap where the dashboard could show admin/team/API-key
surfaces but could not explain the actor context and RBAC decision shape behind
those surfaces.

## Next Work

1. Bind all mutation-like A3 receipts to `ashr.event_envelope.v1`.
2. Add typed client generation from OpenAPI once the A3 webapp migrates further
   toward TypeScript/React.
3. Re-run denied-state tests with real hosted auth/RBAC once A1 provides it.
