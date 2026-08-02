# A3 Trusted Read Access Contract

Date: 2026-07-12

Strategy authority: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`

Status: hosted enforcement contract, not production-completion evidence

## Current Implementation Addendum

The current A3 reference implementation now enforces exact source selection,
five-level snapshot/report matching, scope-aware report storage keys, and
strict filtering for dashboard, usage, admin, review, readback, GitHub, report,
and import aggregates. New aggregate records persist the full five-level scope.

Legacy or foreign-scope aggregate records are excluded and produce
`a3.aggregate_scope_status.v1` with `status=partial`; the Webapp renders that
state visibly and offers a retry path. A3 does not convert missing scope into
local defaults in hosted aggregate reads.

Live GitHub transport is separately gated by A2's chain-verified Decision
Ledger, Evidence Snapshot, `release_ready=true`, non-blocking decision, and
current ledger selectors. This is downstream consumption only; A3 does not
recompute Release Ready.

This remains local implementation plus contract evidence. Snapshot storage is
still keyed only by `source`, SQLite operational tables do not yet carry every
scope column, and no production PostgreSQL/RLS, deployed A1 verifier, customer
IdP, multi-instance, or VPC recovery proof exists.

## Decision

Tenant-sensitive A3 reads are protected at the hosted A3 API or same-origin
BFF boundary. A protected operation accepts either:

- an A1 browser session that has been verified server-side; or
- an A1 service-account credential that has been verified server-side.

A3 consumes the resulting immutable principal. It does not accept a browser,
mobile client, query parameter, or arbitrary proxy header as identity, tenant,
or role authority. In particular, no client-supplied `x-a3-role` or equivalent
role header is an OpenAPI security scheme.

The OpenAPI security alternatives are `A1VerifiedSession` and
`A1ServiceAccount`. They express how a request reaches the verifier. They do
not permit A3 client code to read an HttpOnly cookie or construct a trusted
principal.

## Principal Contract

Before a protected A3 handler reads tenant-owned data, trusted server-side
middleware must establish these facts:

```text
principal_kind: browser_session | service_account
principal_id: server-verified actor or service-account reference
permissions: server-resolved permission set
organization_id
tenant_id
workspace_id
project_id
environment_id
```

All five scope fields are required. Request fields may narrow a query within
the verified scope, but they cannot add membership, widen access, replace the
principal scope, or select another tenant. Resource identifiers such as
`run_id`, `case_id`, `release_id`, and `report_id` remain additional selectors.

For every protected read, A3 must:

1. Reject an absent or unverifiable A1 principal.
2. Require the operation's declared `x-rbac.permission`.
3. Match all five scope fields before reading tenant-owned rows or objects.
4. Apply object and row isolation as defense in depth.
5. Emit only metadata-safe read audit evidence.

## Denial Contract

Protected reads declare reusable `401` and `403` responses.

| Status | Contract | Disclosure rule |
|---|---|---|
| `401` | `SanitizedUnauthorizedError` | Do not reveal tenant, resource, role, permission, credential, or membership details. |
| `403` | `SanitizedForbiddenError` | Do not reveal tenant membership, resource existence, role bindings, or the missing permission. |
| `404` | Sanitized not found where applicable | A cross-tenant object lookup may use `404` instead of `403` to avoid an existence oracle. |

Both authorization error schemas are closed objects. They allow only a fixed
schema version, a generic error code, and an optional request ID. Responses
must use `Cache-Control: no-store`. Raw cookies, bearer credentials, share
tokens, customer payloads, and private evidence must never appear in an error.

## Protected Coverage

The v2 OpenAPI artifact explicitly protects 28 existing GET routes. The
focused test requires at least 20 and names every strategy surface requested
for this contract.

| Surface | Count | Existing routes | Permission |
|---|---:|---|---|
| Contract and admin security | 4 | `/api/a3/commercial-api/contract`, `/api/a3/auth/context`, `/api/a3/auth/rbac-policy`, `/api/a3/admin/console` | `audit:read`, `project:read`, or `admin:plan` |
| Dashboard, runs, case, product console | 5 | `/api/a3/dashboard`, `/api/a3/runs`, `/api/a3/runs/{runId}`, `/api/a3/cases/{caseId}`, `/api/a3/product/console` | `project:read` |
| Release evidence | 3 | `/api/a3/releases/{releaseId}/evidence-summary`, `/api/a3/releases/{releaseId}/evidence-health`, `/api/a3/a1-a2/evidence-spine` | `project:read` for summary/health; `audit:read` for the evidence spine |
| Review | 1 | `/api/a3/review/workflow` | `release:review` |
| Reports | 4 | `/api/a3/reports`, `/api/a3/reports/center`, `/api/a3/reports/{reportId}`, `/api/a3/reports/{reportId}/manifest` | `project:read` |
| Usage and billing | 3 | `/api/a3/usage/ledger`, `/api/a3/billing/readiness`, `/api/a3/billing/migration-readiness` | `usage:read` or `billing:read` |
| Live operations | 2 | `/api/a3/live-workflow/readiness`, `/api/a3/live-ops/control-plane` | `audit:read` |
| Notifications | 1 | `/api/a3/notifications/control-plane` | `notifications:read` |
| Artifacts and enterprise trust | 2 | `/api/a3/artifacts/registry`, `/api/a3/enterprise/readiness` | `audit:read` |
| Schema drift, peer calibration, outbox | 3 | `/api/a3/a1-a2/schema-drift`, `/api/a3/peer-branches/calibration`, `/api/a3/events/outbox` | `audit:read` |

Existing protected mutations also carry explicit verified-principal security,
five-level scope, RBAC, and sanitized `401`/`403` response references. Their
business semantics are unchanged by this read-contract upgrade.

## Public Exceptions

Only two reads explicitly override OpenAPI security with `security: []`.

### Health

`GET /api/a3/health` is a public operational probe. It may expose service and
readiness state, but no tenant scope, customer payload, private evidence,
identity, billing detail, or credential state.

### Share Capability

`GET /r/{shareToken}` is public by possession of an opaque capability. It is
not an authenticated product-console read and does not accept a session
principal as a substitute for the token. The server must perform digest-only
lookup and enforce expiry, revocation, download control, redaction, and view
audit. The raw token must be redacted from logs, traces, analytics, errors, and
stored audit payloads. Invalid tokens return a sanitized `404`; expired or
revoked tokens return a sanitized `410`.

## A1 Capability Non-Claim

This contract consumes a server-verified A1 principal when the hosted boundary
is deployed. It does not claim that A1 hosted login is production-complete.
A1 has a browser-session lifecycle for supported login and recovery paths, but
the previously documented initial provider sign-in and registration handoff
gaps remain outside A3 ownership. OpenAPI shape, local fixtures, and local role
simulation are not production authentication evidence.

Production readiness still requires deployed verification, revocation,
rotation, tenant isolation, durable audit, denial-path tests, and operational
evidence across the A1 and A3 boundary.

## A2 Authority

This change does not alter A2 decision semantics. A3 may display A2 evidence,
scores, failure classes, policy versions, decision-ledger hashes, and release
decisions. A3 must not recompute a score, reinterpret pass or fail, rewrite a
decision record, or infer Release Ready without a valid A2 Decision Ledger.

Schema drift and peer calibration endpoints inspect contract compatibility
only. They do not become alternate judge or release-policy authorities.

## Verification

Focused contract command:

```text
node --test tests/a3/a3_commercial_openapi_contract.test.mjs
```

Recorded result on 2026-07-12: `6 pass / 0 fail`.

## Implementation Closure Addendum

The initial contract review found resource-selection and trusted-principal
gaps after the focused OpenAPI test above. They were fixed before this round
closed.

Hosted enforcement now additionally requires:

- `trusted: true` and `authenticated: true`;
- an explicit active browser-session or service-account state;
- a valid future expiry;
- explicit effective permissions from the A1 resolver;
- an explicit actor or subject identity reference;
- a per-request resolver function. A static principal object is rejected.

The store boundary now treats the trusted five-level scope as a validation
constraint instead of a label to apply to a selected foreign resource. In
hosted mode, source lookup is exact, missing sources do not fall back to the
first snapshot, and organization, tenant, workspace, project, and environment
must all match before dashboard, run, case, report, or aggregate data is
returned. Reports use a scope-aware internal storage key so colliding public
report IDs can remain isolated.

The public share-token HTTP route takes time only from the server clock (or an
injected trusted test clock). Client query/body `viewed_at` values cannot move
an expired link back into an allowed state. Unknown hosted routes also produce
metadata-only denial audit evidence.

Runtime hosted denials now exactly use the closed OpenAPI response bodies:

```json
{"schema_version":"a3.sanitized_unauthorized.v1","error":"authentication_required"}
```

```json
{"schema_version":"a3.sanitized_forbidden.v1","error":"access_denied"}
```

Demo mode is technically limited to dry-run GitHub publication. Client flags
such as `hosted_session`, `service_account`, `allow_live`, or `dry_run=false`
cannot grant live external-mutation authority.

Final current-diff evidence after the independent bypass audit and closure:

- full A3 Node: `387 pass / 0 fail`;
- fresh-port Playwright: `33 pass / 0 fail`;
- Webapp typecheck and production build: passed;
- A1 TypeScript session lifecycle: `35 pass / 0 fail`;
- A2 trusted spine: `7 pass / 0 fail`;
- commercial/hygiene guards and `git diff --check`: passed;
- changed-file high-confidence secret scan: zero matches.

This closes the identified local reference-implementation defects. It still
does not prove a deployed A1 verifier, PostgreSQL/RLS, multi-instance audit
custody, customer IdP, or production hosted authorization.

## Trusted Mutation And Parity Addendum

The follow-up independent audit found two live-mutation bypasses and several
structural gaps. The current branch closes them locally as follows:

- direct server startup defaults to `hosted_enforced` for every environment;
- the standalone GitHub CLI cannot perform live writes and fails before token
  lookup or transport;
- hosted live GitHub publication requires a server-side A2 authority resolver,
  exact current ledger selectors, an A1 trusted worker, and an A1 tenant-bound
  GitHub installation/repository target;
- locally recomputed A2 hashes prove integrity but cannot establish A2 service
  identity or authorize a live mutation;
- exception approvals require a same-source, same-five-level-scope waiver;
- same-name sources coexist under independent five-level snapshot identities;
- SQLite stores GitHub receipts and event-outbox rows in dedicated tables;
- fixture health no longer claims database readiness;
- the Partial warning precedes empty state; and
- all `53` protected runtime RBAC routes have matching OpenAPI operations and
  permissions.

These are local executable safeguards and contracts. Live publication remains
unavailable by default because no deployed A1 principal/GitHub worker and A2
trusted-authority resolver are supplied by this repository state.
