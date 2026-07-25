# A1 PostgreSQL-authoritative tenancy lifecycle contract

Status: frozen for implementation on 2026-07-25
Schema version: `ashr.clone.tenancy.v1`

This contract defines the first commercial organization, project, environment,
and project-membership lifecycle slice shared by the Go runtime, Python SDK,
TypeScript SDK, and A3. PostgreSQL foundation tables are the only authoritative
state. The legacy in-memory bootstrap surface and the `ashr_tenants` /
`ashr_projects` compatibility tables are not authorities for these routes.

## 1. Trust boundary

- Every route in this contract requires an active server-resolved identity
  Session. The canonical actor/account identifier is the trusted
  `Session.AccountID` populated by the production identity Session resolver.
  It is the canonical account principal passed to PostgreSQL and is not
  interchangeable with `Session.ActorID` or any caller-supplied identifier.
- Cookie receipt validation, expiry, rotation, and revocation remain owned by
  `IdentityHTTPSessionResolver`.
- Request bodies, URL query parameters, and headers cannot replace the
  Session-derived actor. In particular, the server rejects `actor_id`,
  `actor_principal_id`, `account_id`, `principal_id`, `session_id`,
  `session_token`, and similarly normalized aliases when they appear as an
  actor override.
- An `account_id` path segment is allowed only as the target of a project
  membership mutation. It never identifies the caller.
- Organization, project, and environment identifiers in the URL are scope
  assertions. PostgreSQL must prove the resource belongs to the asserted
  parent before returning or mutating it.
- Authentication failures are indistinguishable from revoked or expired
  Sessions. Cross-tenant and out-of-scope resource failures return a generic
  not-found response where disclosure would reveal another tenant.

## 2. Resource state machines

### Organization

An organization is created in `active` state. This slice exposes create and
list, but not suspend/delete. Creation atomically creates:

1. the organization;
2. one active default workspace named `default`;
3. an active organization `owner` membership for the actor;
4. an idempotency receipt;
5. audit and outbox records.

### Project

Allowed states are the foundation states `active`, `archived`, and `deleted`.
This slice does not expose deletion.

```text
create -> active
active -> archived
archived -> active
```

- Updating display name or slug is allowed only while active.
- Archive and restore are explicit operations, never implicit effects of
  `PATCH`.
- Replaying an already completed archive/restore with the same idempotency
  key returns the original result.

### Environment

Allowed states are `active`, `disabled`, and `deleted`. This slice does not
expose deletion.

```text
create -> active
active -> disabled
disabled -> active
```

- Environment kind is immutable after creation and is one of `development`,
  `staging`, `production`, or `sandbox`.
- Enable and disable are explicit operations.

### Project membership

Membership states are `invited`, `active`, `suspended`, and `revoked`. The
public set operation in this slice creates or replaces an **active**
membership. Revoke changes it to `revoked`; it does not hard-delete the row.
The target must have an active organization membership in the same
organization.

## 3. Canonical roles and authorization

Canonical organization roles:

```text
owner
admin
security_admin
billing_admin
project_admin
developer
reviewer
auditor
read_only_viewer
service_account
```

Canonical project roles:

```text
owner
admin
developer
reviewer
auditor
read_only_viewer
service_account
```

Existing legacy role values remain readable for migration compatibility but
new API writes accept only the canonical values above.

Minimum authorization matrix:

| Operation | Required active authority |
| --- | --- |
| create organization | any active trusted Session |
| list organizations | actor's active organization memberships |
| list scoped resources | active organization membership |
| create/update/archive/restore project | organization `owner`, `admin`, or `project_admin`; or project `owner` / `admin` where a project already exists |
| create/enable/disable environment | organization `owner`, `admin`, or `project_admin`; or project `owner`, `admin`, or `developer` |
| list project memberships | organization `owner`, `admin`, `security_admin`, or `project_admin`; or project `owner` / `admin` |
| set/revoke project membership | organization `owner`, `admin`, or `security_admin`; or project `owner` / `admin` |

ABAC rules are applied after RBAC:

- organization and project must be active for normal mutation;
- project and environment must match every parent scope in the URL;
- the target membership must be anchored to an active same-organization
  membership;
- no operation may revoke or demote the last active project owner;
- organization ownership is never inferred from project ownership;
- a service-account role does not grant authority to mutate memberships.

## 4. HTTP surface

```text
POST   /v1/organizations
GET    /v1/organizations
GET    /v1/organizations/{organization_id}/projects
POST   /v1/organizations/{organization_id}/projects
PATCH  /v1/organizations/{organization_id}/projects/{project_id}
POST   /v1/organizations/{organization_id}/projects/{project_id}/archive
POST   /v1/organizations/{organization_id}/projects/{project_id}/restore
GET    /v1/organizations/{organization_id}/projects/{project_id}/environments
POST   /v1/organizations/{organization_id}/projects/{project_id}/environments
POST   /v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/disable
POST   /v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/enable
GET    /v1/organizations/{organization_id}/projects/{project_id}/memberships
PUT    /v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}
DELETE /v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}
```

Mutation requests require `Idempotency-Key`. The value is trimmed ASCII,
8-128 characters, and must match `^[A-Za-z0-9][A-Za-z0-9._:-]*$`.

`X-Request-ID` and `X-Ashr-Trace-ID` are accepted only when they are printable
ASCII, contain no whitespace/control characters, are at most 128 characters,
and match `^[A-Za-z0-9][A-Za-z0-9._:/-]*$`. Otherwise the server generates a
request ID and omits an invalid trace ID. These headers are correlation data,
not identity or authorization evidence.

## 5. Idempotency and concurrency

- The idempotency scope is actor principal + operation + organization scope +
  key. Organization creation uses the actor principal as its pre-organization
  scope.
- The payload digest covers the canonical operation, parent identifiers, and
  normalized public input. It never includes a Cookie, Session token, secret,
  private reference, or raw OAuth value.
- First execution records `in_progress`, applies the mutation, stores the
  exact public result, then records `completed` in the same transaction.
- A replay with the same key and digest returns the stored result with
  `idempotent_replay: true` and creates no duplicate resource, membership,
  audit event, or outbox event.
- Reuse of the same scoped key with a different digest fails with HTTP `409`
  and code `tenancy_idempotency_conflict`.
- Concurrent first attempts serialize on the scoped key and produce one
  mutation effect. Locks are transaction-scoped and bounded by the runtime
  lock timeout.
- Failed transactions leave no completed receipt or partial lifecycle effect.

## 6. Audit and outbox invariants

Every successful mutation atomically emits:

- an append-only audit event containing actor principal, organization/project
  scope, action, resource type/id, request digest, request ID, optional trace
  ID, and public lifecycle metadata;
- one pending outbox event with a deterministic event digest and an A3-safe
  payload;
- the completed idempotency receipt.

Customer payloads, credentials, Cookies, tokens, OAuth state/nonce/PKCE,
delivery refs, Vault refs, internal policy documents, and plaintext
identifiers such as email/phone are forbidden in audit/outbox payloads.

## 7. A3-safe public DTOs

All DTOs include `schema_version: "ashr.clone.tenancy.v1"`.

### Organization DTO

```text
organization_id, slug, display_name, status, created_at, updated_at
```

### Project DTO

```text
organization_id, project_id, slug, display_name, status,
created_at, updated_at, archived_at
```

### Environment DTO

```text
organization_id, project_id, environment_id, name, kind, status,
created_at, updated_at, disabled_at
```

### Project membership DTO

```text
organization_id, project_id, account_id, role, status,
created_at, updated_at, activated_at, revoked_at
```

Collection envelopes expose `items` and `count`. Mutation envelopes expose
`result`, `request_id`, and `idempotent_replay`. Timestamps are RFC 3339 UTC.

Public DTOs and errors must reject or omit:

```text
actor/session overrides
session/token/cookie values
credential, OAuth, state, nonce, PKCE, proof, ticket, challenge values
secret_ref, private_ref, vault_ref, KMS/ciphertext material
request/payload/subject/event digests
raw policy/RLS/ACL internals
database role names or SQL text
email, phone, provider subject, or other login identifiers
```

## 8. Error contract

Stable public codes:

```text
tenancy_authentication_required
tenancy_invalid_request
tenancy_invalid_idempotency_key
tenancy_idempotency_conflict
tenancy_forbidden
tenancy_not_found
tenancy_state_conflict
tenancy_last_owner
tenancy_unavailable
```

Errors contain only `schema_version`, `code`, `message`, and `request_id`.
Database messages, constraint names, SQLSTATE values, and account existence
details are not exposed.

## 9. PostgreSQL and runtime requirements

- Foundation `organizations`, `workspaces`, `projects`, and `environments`
  plus identity membership tables are authoritative.
- New tenant-owned receipt data has `organization_id`, has RLS enabled and
  forced, and is inaccessible to `PUBLIC`.
- Runtime access uses restricted functions/grants and transaction-local
  principal/organization/project context. Startup fails if the PostgreSQL
  tenancy store cannot be constructed in production identity mode.
- The Go runtime does not install a memory fallback for this surface.
- Deployment applies migration 030 before enabling route advertisement.
- Rollback disables route advertisement first; it never drops tenant data
  automatically.
