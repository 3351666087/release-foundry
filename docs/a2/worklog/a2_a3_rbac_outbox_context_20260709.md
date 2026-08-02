# A2 A3 RBAC / Event Outbox Context - 2026-07-09

## Scope

Lane: A2 Evaluation / Policy / Security

Goal: align A2 cross-lane security context with A3's latest fail-closed RBAC write-path and event outbox SaaS backbone work.

No live ReleaseFoundry API call was executed. No key file or private evidence file was read. The upstream signal came from public A3 branch docs and tests after `git fetch origin`.

## Upstream Signal

A3 branch `agent/a3-commercial-growth-round4` added:

- fail-closed RBAC enforcement around product-console write paths
- sanitized `a3.api_authz_denied.v1` denial responses
- metadata-only `releasefoundry.event_envelope.v1` event outbox rows
- idempotency behavior for report/review/admin/readback writes
- A1/A2 schema drift radar and optional consumers for A2 cross-lane security and SQL store reports

## A2 Changes

- `services/judge/cross_lane_security.py` now accepts optional A3 fail-closed RBAC and event outbox docs.
- `fixtures/a2/results/a2_cross_lane_security_context.json` records those A3 contracts as missing on this branch until the public A3 docs land locally/main.
- `fixtures/a2/results/a2_saas_control_plane_report.json` exposes the new available/ready booleans and followup IDs for A3 dashboard consumption.
- Schemas were updated for the cross-lane and SaaS control-plane contracts.
- Tests now prove ready A3 public docs unlock A2 policy implications for fail-closed write abuse cases and event outbox integrity cases.

## Merge / Product Meaning

This keeps #29 aligned with A3's current SaaS direction without merging A3 files into A2. When A3's docs reach main, A2 can immediately convert those public contracts into security scenarios and release policy checks.
