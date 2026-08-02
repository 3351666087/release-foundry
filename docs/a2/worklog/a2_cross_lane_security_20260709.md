# A2 Cross-Lane Security Context - 2026-07-09

## Scope

Lane: A2 Evaluation / Policy / Security

Goal: align A2 with the GitHub main SaaS strategy bus by adding a public-safe security context that can consume A1 route scope / RLS parity and A3 Auth/RBAC boundary contracts when those upstream artifacts reach this branch.

This work did not read private evidence, did not read key files, did not call the live ReleaseFoundry API, and did not write secrets.

## Main Strategy Alignment

Current `origin/main` strategy still positions A2 as:

- judge, policy, scenario, calibration, regression, semantic eval, security verification, privacy validation, abuse detection;
- Python-first for judge and evaluation intelligence;
- JSON Schema / OpenAPI contracts for policy and scenario artifacts;
- consumer and verifier of A1/A3 auth, tenant, RBAC, artifact, and dashboard boundaries.

The added context stays within that boundary. It does not copy A1/A3 branch files into A2. It only creates an optional, deterministic A2 contract for the security signals A2 needs before promoting abuse cases or blocking policy rules.

## Changes

- Added `services/judge/cross_lane_security.py`.
- Added `docs/a2/schemas/cross_lane_security_context.schema.json`.
- Added generated fixture `fixtures/a2/results/a2_cross_lane_security_context.json`.
- Integrated the context into `scripts/a2_regenerate_fixtures.py`.
- Integrated a summary into `fixtures/a2/results/a2_saas_control_plane_report.json`.
- Exposed A3 dashboard payload key `crossLaneSecurity`.
- Added tests in `tests/a2/test_cross_lane_security.py`.
- Extended existing SaaS control-plane and schema snapshot tests.

## Current Branch Status

After the next heartbeat pass, this branch was aligned with the public A1 route parity snapshot already present on `origin/main`:

- `docs/a1/evidence/go_python_ts_route_parity_snapshot.json`

The current A2 branch still does not yet contain:

- `docs/a3/p3_auth_rbac_boundary_2026_07_09.md`
- `docs/a3/openapi/a3_commercial_api.openapi.json`

Therefore the generated public fixture records:

- A1 route scope available and ready for A2 security context;
- A3 Auth/RBAC boundary unavailable;
- one A2 route-scope tenant-boundary followup;
- one followup waiting for the A3 Auth/RBAC public-safe contract.

When those contracts arrive from A1/A3/main, A2 will require:

- route scope plus tenant/RLS hardening signal from A1;
- A3 boundary anchor;
- A1/A2 source-of-truth dependency statements;
- A3 OpenAPI auth paths;
- actor hash, raw identity redaction, token/cookie/API key exclusion, hosted mutation blocking, and metadata-only audit semantics.

## Verification

Commands run:

```powershell
python -B -m py_compile services/judge/cross_lane_security.py services/judge/saas_control_plane.py scripts/a2_regenerate_fixtures.py tests/a2/test_cross_lane_security.py tests/a2/test_a2_saas_control_plane.py tests/a2/test_contracts.py
python -B scripts/a2_regenerate_fixtures.py --check
python -B -m unittest discover -s tests/a2 -v
node --test tests/a3/a3_gate_cli.test.mjs
node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --strict-exit --json
```

Results:

- A2 generated fixture check passed, 55 files matched.
- A2 unittest passed, 144 tests.
- A3 gate CLI tests passed, 20 tests.
- A3 audit bundle verification passed.

## Next Growth Step

Once A1/A3 route scope and Auth/RBAC files land on main or this branch, promote the ready followups into A2 scenario-generation candidates for tenant isolation, RBAC denied states, hosted mutation blocking, raw identity redaction, and metadata-only audit event enforcement.
