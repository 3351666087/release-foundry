# A3 Request Boundary Audit - 2026-07-12

> Round 12 local implementation evidence for malformed JSON and protected
> `OPTIONS`. This document does not claim a deployed hosted SaaS or production
> CORS boundary.

## Scope and Authority

- Strategy authority:
  `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
- A1 remains authoritative for trusted identity, browser sessions, service
  accounts, and the future deployed audit/data plane.
- A2 remains authoritative for evidence, judge output, Decision Ledger, and
  Release Decision. This round does not read, recalculate, or change A2 scores
  or release semantics.
- A3 owns route-to-permission mapping, sanitized HTTP behavior, metadata-only
  access-audit orchestration, and the OpenAPI product contract.

## Closed Gaps

Before this round, `createA3ApiHandler()` returned `204` for every `OPTIONS`
request before route matching or authorization. A protected or unknown route
therefore bypassed the access decision and produced no access audit.

Before this round, malformed JSON on a protected mutation escaped from
`JSON.parse()` into the generic error handler. The caller received `500`, and
the access-attempt audit did not carry a stable malformed-request decision.

The local implementation now:

1. Resolves a valid `Access-Control-Request-Method` to the canonical runtime
   route before answering `OPTIONS`.
2. Applies the same A1 principal, five-level tenant scope, and A3 RBAC checks
   to protected preflight requests.
3. Fails unknown or unsupported preflight targets closed with a sanitized
   `403` instead of an unconditional `204`.
4. Authenticates and authorizes hosted mutations before reading their JSON
   body.
5. Returns a fixed sanitized `400` only when a trusted, authorized request has
   malformed JSON; missing identity remains `401`, and missing permission or
   scope remains `403`.
6. Requires `application/json`, a top-level object, a bounded body, and a
   bounded read time. Failures return fixed `415`, `422`, `413`, or `408`
   responses after authentication and authorization.
7. Persists one metadata-only access decision for every hosted protected
   outcome. Raw body, identity, token, cookie, origin, path parameter, and
   client-selected source values are not persisted.

## Request State Machine

```text
request
  -> resolve transport method
  -> OPTIONS: resolve requested target method
  -> match public/protected/unregistered route
  -> protected hosted route: resolve A1 trusted principal
  -> validate five-level scope and A3 RBAC
  -> denied: persist metadata-only 401/403 audit and stop
  -> authorized mutation: read and parse JSON
  -> malformed: persist metadata-only 400 audit and stop
  -> timeout / too large / wrong media / wrong shape: persist 408/413/415/422
  -> valid body: re-check nested scope assertions
  -> persist final access decision
  -> dispatch business handler
```

This ordering prevents an unauthenticated or unauthorized hosted mutation
from entering the JSON parser. It also keeps nested body scope assertions
fail-closed after parsing.

## Behavior Matrix

| Attempt | Identity / permission | Local result | Audit |
|---|---|---:|---|
| Malformed protected POST | trusted + allowed | `400 invalid_json` | `route_access.denied` |
| Malformed protected POST | missing identity | `401 authentication_required` | `route_access.denied` |
| Malformed protected POST | trusted + denied | `403 access_denied` | `route_access.denied` |
| Slow protected POST | trusted + allowed | `408 request_timeout` | `route_access.denied` |
| Oversized protected POST | trusted + allowed | `413 payload_too_large` | `route_access.denied` |
| Non-JSON protected POST | trusted + allowed | `415 unsupported_media_type` | `route_access.denied` |
| JSON null/array/scalar | trusted + allowed | `422 invalid_json_shape` | `route_access.denied` |
| Access-audit persistence unavailable | any protected route | `503` and no handler execution | fail-closed |
| Protected OPTIONS -> POST | trusted + allowed | `204` | `route_access.allowed` |
| Protected OPTIONS -> POST | missing identity | `401` | `route_access.denied` |
| OPTIONS -> unknown route | any | `403` | `route_access.denied` |
| OPTIONS -> unsupported method | any | `403` | `route_access.denied` |
| Public health OPTIONS -> GET | not required | `204` | public health audit not required |

The response body never includes parser text, request body content, role,
permission, tenant membership, token, cookie, email, or private origin.

## Audit Shape

Persisted access events add only allowlisted metadata:

- `decision`
- `http_status`
- canonical `operation_id`
- canonical `required_permission`
- `transport_method`
- `preflight_for_method`
- `request_body_state`
- five-level scope from the trusted principal or a non-secret sentinel
- hashed request/trace/principal references
- `payload_inline=false`
- `redaction_status=metadata_only`

Authorization audit source is fixed to `hosted-access`; a query parameter
cannot choose a persisted source label.

## OpenAPI Contract

`docs/a3/openapi/a3_commercial_api.openapi.json` now includes:

- `a3.request_boundary_contract.v1`;
- a closed `SanitizedBadRequestError` schema;
- reusable sanitized `400/408/413/415/422/503` responses with
  `Cache-Control: no-store`;
- strict media type, top-level object, byte-limit, read-deadline, and
  malformed-JSON precedence contracts on every protected mutation;
- a protected `OPTIONS` policy on all 53 runtime RBAC operations.

Runtime and OpenAPI parity remains `53/53`. The contract explicitly sets
`cors_enablement_claimed=false`: this round closes route/access/audit bypasses
but does not advertise browser cross-origin support. A production gateway
still needs an explicit origin allowlist and deployed A1 identity integration.

## Evidence

- Runtime code:
  `services/report/a3_api_server.mjs` and
  `services/report/a3_route_access_control.mjs`.
- OpenAPI synchronizer:
  `services/report/a3_openapi_runtime_parity.mjs`.
- Redacted evidence:
  `fixtures/a3/p3/a3_request_boundary_audit_evidence.redacted.json`.
- Unit/contract/integration:
  `tests/a3/a3_route_access_control.test.mjs`,
  `tests/a3/a3_hosted_api_access.test.mjs`,
  `tests/a3/a3_commercial_openapi_contract.test.mjs`, and
  `tests/a3/a3_request_boundary_evidence.test.mjs`.
- HTTP E2E:
  `tests/e2e/a3-webapp-product-routes.spec.ts`.

No new screenshot was created because this is a transport boundary with no
new visual UI. The redacted behavior matrix is the visual evidence artifact;
the real proof is the executable HTTP integration and Playwright coverage.

## Capability Classification

- **Implemented:** local handler ordering, fixed sanitized errors, protected
  route matching for `OPTIONS`, metadata-only memory/SQLite-compatible audit,
  JSON media/shape/size/deadline limits, OpenAPI contract, integration tests,
  and HTTP E2E.
- **Contract supported:** A1 trusted-principal resolver, durable access-audit
  sink, and production gateway CORS/origin enforcement.
- **Production validated:** none in this round.

## Residual Risks

1. There is no deployed A1 session/service-account verifier in front of this
   local A3 handler.
2. There is no production PostgreSQL/RLS audit store or multi-instance
   transaction proof.
3. The local 1 MiB and 10 second defaults still require ingress/WAF alignment,
   load testing, route-specific limits, and slow-client socket validation.
4. Duplicate JSON keys, extreme nesting, parser fuzzing, and request-drain
   behavior still need adversarial coverage.
5. A browser-grade cross-origin flow needs an explicit, tested origin policy;
   this round intentionally does not infer one.
6. No load, proxy, WAF, or customer-VPC adversarial test has been
   completed.
