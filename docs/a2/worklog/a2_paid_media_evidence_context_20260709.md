# A2 Paid-Media Evidence Context - 2026-07-09

## Scope

Lane: A2 Evaluation / Policy / Security

Goal: prepare A2 to consume A1's public-safe paid-media official API manifest summary as quota/error context without treating it as hosted media readiness or reviewed Ashr grading evidence.

No live Ashr API call was executed in this round. No `Ashr_key.txt` file was read. No private evidence file was read or copied. The A1 signal was inspected only as public-safe summary shape from the remote branch.

## Upstream Signal

A1 branch `codex/a1-local-sdk-runner` now exposes a public-safe paid-media summary shaped like:

- `schema_version: ashr.clone.public_official_api_manifest_summary.v1`
- `status: partial`
- `mode: small-batch`
- guardrails for small batch, quota gate, explicit mutating opt-in, private output, and `allow_paid_media`
- redacted summary fields only
- no raw key material, headers, request parameters, payload values, or step record locations

The current observed signal is valuable for policy context because it shows quota-blocked mutating create-request behavior. It is not sufficient to mark paid media generation reliable, and it is not C3 grading evidence.

## A2 Changes

- Added `a1_official_api_paid_media_summary` to `services/judge/evidence_readiness.py`.
- Added JSON Schema contract fields for paid-media guardrails, quota-blocked steps, status-code counts, and readiness interpretation.
- Regenerated `fixtures/a2/results/a2_evidence_readiness_report.json`; because the A1 public file is not present on this branch yet, the default report records the paid-media summary as missing.
- Added unit coverage with a temp public-safe summary proving A2 marks it `ready_for_a2_evidence_context=true`, `safe_for_paid_media_claims=false`, and `c3_grading_ready=false`.

## Merge / Product Meaning

A2 can now accept A1's paid-media calibration summary when it lands on main or this branch. The release policy layer can use it as quota/error-shape evidence, while C3 remains blocked until scanner-confirmed 6/6 A2 grading cases and reviewed `ashr_grading` rows are imported and merged.
