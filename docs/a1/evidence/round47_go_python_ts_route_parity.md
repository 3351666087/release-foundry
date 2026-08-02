# Round47 Go/Python/TypeScript route parity evidence

Status: public-safe generated-contract evidence

## Result

The Round47 route snapshot records the current hosted surfaces without claiming
false parity:

| Runtime | Route count |
| --- | ---: |
| Go | 56 |
| Python | 35 |
| TypeScript | 38 |

The machine-readable source of truth is
`docs/a1/evidence/go_python_ts_route_parity_snapshot.json`.

## Intentional differences

- Go owns 16 China payment and reconciliation routes covering provider
  discovery, orders, notifications, refunds, daily bills, and reconciliation
  events. Python and TypeScript register these as unsupported hosted-client
  gaps; no replacement route is asserted.
- TypeScript exposes OAuth authorization `begin` and `complete` routes.
- Python exposes OAuth session create/revoke, commercial provider
  configuration, payment mode boundary, and the commercial snapshot route.
- Health, OpenAPI aliases, API-key preflight, legacy run submission, quota
  administration, and release-gate differences remain explicit in the
  snapshot.

These differences are contract facts, not test exemptions. A Go-only route must
remain present in each hosted SDK's unsupported-gap registry until that SDK has
an implemented request/response contract.

## Generation and checks

The route snapshot is derived from:

- `packages/go/releasefoundry/server.go`
- `packages/sdk/releasefoundry/saas.py`
- `packages/ts/releasefoundry/src/saas.ts`

The TS/Python symbol and route matrix is generated at
`tests/a1/docs/a1/ts_python_gap_matrix.json`.

Validation commands:

```text
python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_ts_python_gap_matrix.py -q -p no:cacheprovider
python -B tests/a1/ts_python_parity_matrix.py --check
npm run build --prefix packages/ts/releasefoundry
npm test --prefix packages/ts/releasefoundry
```

## Evidence boundary

This evidence contains route templates, counts, source paths, and public-safe
gap reasons only. It contains no credentials, provider payloads, customer
identifiers, raw webhook bodies, or private calibration evidence.

Static route extraction proves registry and generated-evidence consistency. It
does not prove provider behavior, response-schema equivalence, OAuth lifecycle
equivalence, or live China payment execution.
