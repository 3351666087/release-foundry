# A2 Mutating API Evidence Readiness - 2026-07-09

## Scope

Lane: A2 Evaluation / Policy / Security

Goal: prepare A2 to consume A1's public-safe official API mutating calibration index without treating it as reviewed server-side grading evidence.

This work did not read `ReleaseFoundry_key.txt`, did not read private evidence, did not call the live ReleaseFoundry API, and did not write secrets. The inspected A1 artifact shape came from the public GitHub branch metadata and contained redacted summary fields only.

## Upstream Signal

A1 branch `agent/a1-local-sdk-runner` added:

- `docs/a1/evidence/official_api_mutating_calibration_index.json`
- `docs/a1/evidence/go_route_scope_docs.json`
- `docs/a1/schemas/go_route_scope_docs.schema.json`

The mutating calibration index summarizes official create-request attempts by modality, status, error kind, quota block count, and private manifest reference count. It is useful for A2 quota/error-shape policy context, but it is not C3 grading evidence.

## A2 Changes

- Added optional `a1_official_api_mutating_index` to `services/judge/evidence_readiness.py`.
- Added JSON Schema contract for the summary in `docs/a2/schemas/evidence_readiness.schema.json`.
- Regenerated `fixtures/a2/results/a2_evidence_readiness_report.json`; current branch records the mutating index as missing until the A1 public artifact lands locally/main.
- Added a temp-fixture unit test proving A2 consumes a public-safe mutating index and keeps `c3_grading_ready=false`.

## Verification

Commands run:

```powershell
python -B -m py_compile services/judge/evidence_readiness.py tests/a2/test_contracts.py
python -B scripts/a2_regenerate_fixtures.py --check
python -B -m unittest discover -s tests/a2 -v
node --test tests/a3/a3_gate_cli.test.mjs
node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --strict-exit --json
```

Results:

- A2 fixture check passed, 55 files matched.
- A2 unittest passed, 145 tests.
- A3 gate CLI tests passed, 20 tests.
- A3 audit bundle verification passed.

## Next Step

When A1's mutating calibration index reaches `main` or this branch, A2 should regenerate fixtures and use the summary to drive quota-aware policy experiments and create-request abuse scenarios. C3 must remain blocked until reviewed `releasefoundry_grading` rows are imported and merged.
