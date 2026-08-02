# Round45 Official API Calibration

Date: 2026-07-10

## Scope

Round45 used the existing Python calibrator and readiness packet. Authentication material was available only through the `RELEASEFOUNDRY_API_KEY` environment variable. The value was never printed, copied into a command, or written to a public artifact.

The dry-run planned five read-only steps with seven estimated calls and no mutation. The bounded real batch then ran with `--execute --small-batch --max-retries 0`. All five steps returned HTTP 200, with no error step and no quota block.

Public result:

- `docs/a1/evidence/official_api_round45_public_summary.json`
- `docs/a1/api_calibration/round45_official_api_frontend_field_map.json`

Private evidence reference:

- `docs/evidence/private_refs/a1_readonly_api_round45_20260710.json`
- `docs/evidence/private_refs/a1_readonly_api_round45_20260710.<step>.json`

The private paths are references only. Their contents are intentionally excluded from tracked public documentation.

## Read-Only Findings

The official API batch observed top-level response field names for `init`, `keep_alive`, `list_agents`, `list_datasets`, and `list_requests`. It did not return a hosted usage, quota, or media object, so round45 makes no claim that frontend usage/media names are backend-verified response fields.

The public field map therefore separates:

1. `official_api_observed`: field names present in the redacted round45 API summary.
2. `frontend_mirror_static`: field names and labels found by read-only inspection of the Desktop frontend mirror ZIP.

This separation prevents static frontend implementation details from being promoted into official API response guarantees.

## Frontend Mirror

Source archive:

`C:/Users/33516/Desktop/ReleaseFoundry_frontend_mirror_20260707_125507.zip`

The archive SHA-256 matched the existing frontend mirror index:

`1d12159feb2e1133941bba05d46f24a0e38002dabdfaa29c9cadc7a63d056793`

Only ZIP entries and selected text assets were read. No archive contents were copied into tracked paths. The public fixture records field names and labels from the usage page, request creation modal, request detail drawer, and API dispatch bundle. It excludes storage values, request/response bodies, headers, account identifiers, and secrets.

## Mutation Decision

No mutating call was made.

The current readiness packet states `mutating_small_batch_ready: false` and requires a fresh reviewed plan-batch quota gate plus an explicit modality. No fresh target-bound gate was supplied for round45. Historical mutating evidence also contains quota-blocked outcomes. The correct result is therefore fail-closed, not an override.

## Reproduction

```powershell
python -B -m packages.sdk.releasefoundry.calibrate --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_readonly_api_round45_dry_run_20260710.json
python -B -m packages.sdk.releasefoundry.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_readonly_api_round45_20260710.json
python -B -m packages.sdk.releasefoundry.calibrate summarize-private-manifest --input docs/evidence/private_refs/a1_readonly_api_round45_20260710.json --output docs/a1/evidence/official_api_round45_public_summary.json
python -B -m pytest tests/a1/test_round45_official_api_calibration.py -q
```

These commands rely on environment-only authentication. Do not add a key value to command arguments, shell history, fixtures, logs, or documentation.
