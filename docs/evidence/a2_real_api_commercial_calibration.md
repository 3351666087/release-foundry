# A2 Real API Commercial Calibration

Date: 2026-07-06

This public note summarizes A2-supervised real Ashr API calibration. Raw manifests and per-step records are stored only under `docs/evidence/private_refs/` and must not be committed.

## Batch Summary

- Python SDK read-only calibration: `ok`, 5/5 read steps passed, 0 mutating steps.
- Python SDK mutating calibration: `partial`, read steps passed, `create-request-text` returned an API-shape error.
- TypeScript SDK read-only calibration: `ok`, 5/5 read steps passed, 0 mutating steps.
- TypeScript SDK mutating calibration: `partial`, read steps passed, `create-request-text` returned an API-shape error.

## Public-Safe Evidence

The public index at `docs/a1/api_calibration/real_api_evidence_index.json` now merges prior A1 public-safe evidence with this A2-supervised run. It records only summary fields such as function, status, status code, response keys, error kind, top-level counts, and private evidence paths.

Current public-safe index summary:

- total records: 94
- ok records: 52
- partial records: 3
- error records: 10
- create_request records: 13
- quota block count: 2
- create_request error kind observed: `api`

## A2 Interpretation

Read-only API reachability is strong across both Python and TypeScript chains. The current mismatch is in mutating `create_request`: the hosted API accepts the network call path but returns a shape/API error for the tiny text calibration request in both SDK chains.

This is commercial-product evidence, not C3 server-side grading evidence. A2 should use it to tighten request-shape parity and evidence readiness, but C3 remains blocked until scanner-confirmed 6/6 A2 grading cases have reviewed `ashr_grading` observations.
