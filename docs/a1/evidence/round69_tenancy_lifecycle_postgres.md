# Round 69 - PostgreSQL-Authoritative Tenancy Lifecycle

Date: 2026-07-25

## Scope

This A1 batch adds the first production PostgreSQL-authoritative lifecycle for
organizations, projects, environments, and project memberships. It freezes a
single 14-route contract across the Go runtime, Python SDK, TypeScript SDK,
generated route evidence, and A3-safe public DTOs.

The legacy in-memory tenancy bootstrap and compatibility tables are not
authorities for these routes. Production route advertisement is available
only when the production identity runtime constructs the PostgreSQL tenancy
store and passes migration/ACL/readiness validation.

## Canonical identity and authorization boundary

Every route requires a server-resolved production identity Session. The Go
HTTP boundary passes only trusted `Session.AccountID` to PostgreSQL as the
canonical account principal. `Session.ActorID`, request-body actor/account
fields, query parameters, headers, Cookies, URL membership targets, and
browser-supplied identifiers cannot select or replace the caller.

PostgreSQL enforces active organization/project membership, canonical
organization and project roles, lifecycle state, parent scope, cross-tenant
opacity, and last-owner protection. An `account_id` URL segment is only the
target of a membership mutation.

## PostgreSQL and RLS result

Migration `030_a1_tenancy_lifecycle.sql`:

- applies cleanly after migrations 001-029 on a fresh disposable database;
- extends foundation lifecycle and role constraints without adding a second
  authority;
- creates an append-only mutation-receipt boundary with enabled and forced
  RLS;
- revokes receipt-table and helper authority from `PUBLIC` and the runtime;
- grants the restricted runtime only `a1_tenancy_query` and
  `a1_tenancy_mutate`;
- binds query/mutation execution to transaction-local principal,
  organization, and project scope;
- records exact idempotency, audit, and outbox effects in the mutation
  transaction; and
- retains a fixed `SECURITY DEFINER` search path for the two runtime
  entrypoints.

The five-test live PostgreSQL suite proves exact replay without duplicate
effects, changed-payload conflict, cross-tenant opacity, last-owner rejection,
12-way concurrent exactly-once mutation, append-only receipts, forced RLS, and
the two-function ACL boundary. The Go live integration additionally proves
runtime readiness, store construction, typed public DTO parsing, and real HTTP
routing against Docker PostgreSQL.

## A3-safe HTTP and SDK contract

The Go runtime exposes exactly 14 authenticated routes for organization
create/list, project create/list/update/archive/restore, environment
create/list/disable/enable, and project-membership list/set/revoke.

Mutation requests require a validated `Idempotency-Key` header. Request and
trace identifiers are bounded correlation values, never identity evidence.
Public DTOs contain only lifecycle resource fields, safe timestamps, request
IDs, counts, and replay status. Public errors contain only schema version,
stable code, message, and request ID.

Python and TypeScript publish dedicated strict tenancy clients with the same
14 operation/method/path triples. Both clients use browser-managed,
same-origin cookie authentication, accept no Cookie/Authorization/session
token input, and reject actor/principal/session overrides, private refs,
digests, tickets, raw policy internals, and cross-scope responses.

Generated evidence reports:

```text
Go routes: 114
Python hosted routes: 35
TypeScript hosted routes: 38
Python tenancy routes: 14
TypeScript tenancy routes: 14
Go/Python/TypeScript exact tenancy routes: 14
Go-only tenancy routes: 0
Python-only tenancy routes: 0
TypeScript-only tenancy routes: 0
```

## Verification completed before closeout

```text
Live PostgreSQL tenancy migration/RLS/ACL suite: 5 passed
Focused PostgreSQL/Python/A3/generated parity group: 69 passed
Complete A1 Python suite: 1473 passed, 5 intentionally skipped
Go main module full test and vet: passed
Go standalone integration module test and vet: passed
Explicit Go live PostgreSQL tenancy integration: passed
TypeScript package build and complete test suite: 676 passed
Release suite: 33 passed
Rust fmt/clippy and complete runtime-verifier suite: 31 passed
Generated parity writer/check: passed
Go/Python/TypeScript tenancy exact parity: 14/14
CL full-plan/hygiene/commercial: passed with zero findings or blockers
git diff --check and changed-JSON parsing: passed
```

No raw tenant identity, UUID, email, phone, Cookie, Session token, OAuth
parameter, provider credential, Vault reference, database credential, or
browser storage value is included in this evidence.

## Deployment and rollback

Migration 030 is applied while route advertisement is disabled. Production
startup must fail closed unless identity plus tenancy readiness, restricted
ACLs, and forced RLS are intact. The release then proves replay, conflict,
cross-tenant opacity, last-owner, concurrency, audit/outbox, and A3-safe
responses before advertising routes.

Rollback disables route advertisement first and preserves all tenant data,
receipts, audit records, and outbox records. It must not drop migration 030
state, weaken RLS/ACLs, or introduce an in-memory fallback.
