# A2 Real API Commercial Calibration

Date: 2026-07-06

This public note summarizes A2-supervised real Ashr API calibration. Raw manifests and per-step records are stored only under `docs/evidence/private_refs/` and must not be committed.

## Batch Summary

- Python SDK read-only calibration: `ok`, 5/5 read steps passed, 0 mutating steps.
- Python SDK mutating calibration: `partial`, read steps passed, `create-request-text` returned an API-shape error.
- TypeScript SDK read-only calibration: `ok`, 5/5 read steps passed, 0 mutating steps.
- TypeScript SDK mutating calibration: `partial`, read steps passed, `create-request-text` returned an API-shape error.
- Follow-up Python shape-fixed text calibration: `partial`, read steps passed, `create-request-text` reached the hosted request quota gate.
- Heavy refresh Python/TypeScript read-only calibration: `ok`, 10/10 read steps passed across both SDK chains.
- Heavy refresh Python/TypeScript text mutating calibration: `partial`, read steps passed, `create-request-text` reached the hosted request quota gate in both SDK chains.
- Official SDK smoke: `ok`, 6/6 read/list calls passed.

## Public-Safe Evidence

The public index at `docs/a1/api_calibration/real_api_evidence_index.json` now merges prior A1 public-safe evidence with this A2-supervised run. It records only summary fields such as function, status, status code, response keys, error kind, top-level counts, and private evidence paths.

Current public-safe index summary:

- total records: 192
- ok records: 135
- partial records: 10
- error records: 17
- create_request records: 20
- quota block count: 9
- create_request error kind observed: `api`

## A2 Interpretation

Read-only API reachability is strong across both Python and TypeScript chains. The first Python mutating attempt exposed a concrete product-shape requirement: `request.agent` is required. After the Python calibration harness was updated to emit the hosted `agent` envelope, the text mutating probe no longer failed on that shape error and instead reached the hosted request quota gate.

The TypeScript calibration chain was already using the hosted `agent` envelope and also reached the same quota gate. The heavy refresh confirmed the same current commercial behavior: both SDK chains can perform read/list calibration, and both reach the hosted request quota gate for text `create_request`. This means the remaining immediate blocker is account/request quota, not the `agent` envelope shape.

This is commercial-product evidence, not C3 server-side grading evidence. A2 should use it to tighten request-shape parity and evidence readiness, but C3 remains blocked until scanner-confirmed 6/6 A2 grading cases have reviewed `ashr_grading` observations.
