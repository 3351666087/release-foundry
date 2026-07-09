# A3 Growth Auditor Evidence - Notification Control Plane - 2026-07-09

## Scope

This evidence note audits the next A3 growth round for Slack, Microsoft Teams,
and outbound webhook notification control plane work.

Read inputs:

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- `docs/a3/p3_live_publish_review_billing_share_closeout_2026_07_09.md`
- latest section of `docs/a3/p3_worklog.md`

Safety boundary:

- Documentation-only evidence.
- No code change requested or made.
- No `.env.local` read.
- No live Ashr, GitHub, Slack, Teams, webhook, billing, or cloud call made.
- No secret, token, raw webhook URL, cookie, email, signed URL, payment value,
  or raw share token written.

## Commercial Thesis

A3 should treat Slack, Teams, and webhooks as a notification control plane, not
as one-off chat messages.

The sellable product is:

```text
Release decisions, reviewer actions, billing readiness, report lifecycle, and
audit evidence can be routed to the right enterprise channels with policy,
RBAC, retries, receipts, suppression, billing meters, and tamper-aware audit.
```

This extends the current A3 live publish, review, billing-readiness, and report
share surfaces into the places where enterprise users already work.

## New Sellable Capabilities

1. Slack notification destinations for release gates, blocked runs, approvals,
   waivers, denials, report shares, billing readiness, and audit events.
2. Microsoft Teams notification destinations for the same release and audit
   workflows.
3. Generic signed webhook destinations for customers that need SIEM, GRC,
   ticketing, incident, data warehouse, or internal workflow ingestion.
4. Notification rule builder scoped by organization, project, environment,
   release policy, event type, severity, and reviewer role.
5. Delivery receipts that prove who configured a destination, what event was
   eligible, what payload class was sent, and whether delivery succeeded.
6. Retry, backoff, dead-letter, and replay controls for failed deliveries.
7. RBAC-gated destination create, test, pause, rotate, and delete actions.
8. Redacted preview mode so admins can inspect payload shape without exposing
   raw secrets or sensitive customer trace content.
9. Audit export rows for notification configuration, delivery, failure, replay,
   suppression, and destination rotation.
10. Usage metering for `webhook_deliveries`, notification attempts, retries,
    and retained delivery receipts.

## Why This Is Not A Toy

Toy integrations send a message and stop there. A commercial control plane must
own the operational and audit lifecycle around the message.

Non-toy requirements:

- Tenant-scoped destinations with organization/project/environment ownership.
- Destination credentials stored only through A1-owned encrypted references or
  secret handles.
- Signed webhooks with timestamp, idempotency key, event id, and replay
  protection.
- RBAC checks for destination management, manual test sends, replay, pause, and
  deletion.
- Delivery records tied to `request_id`, `trace_id`, `actor_id`,
  `organization_id`, `project_id`, and source event ids.
- Sanitized payload previews that never include raw tokens, cookies, private
  prompts, raw share tokens, or payment secrets.
- Outbox-driven delivery so notifications survive process restarts and can be
  retried or dead-lettered.
- Suppression and dedupe rules to prevent alert storms during mass failures.
- Billing/usage events for deliveries and retained receipt storage.
- Evidence bundle links so customers can prove what was sent, when, why, and
  under which policy.

## Why Customers Pay

Customers pay because the notification plane sits directly on revenue-critical
and risk-critical workflows:

- Engineering leaders get release gate failures and reviewer decisions in the
  channels where teams already coordinate.
- Security and compliance teams get durable evidence that blocked releases,
  waivers, approvals, and report shares were communicated and traceable.
- Platform teams avoid building and maintaining fragile custom notification
  glue for each agent release pipeline.
- Enterprise admins can prove that human approvals, denials, waivers, and report
  access changes reached the right operational systems.
- Finance and operations can meter notification volume, retained receipts, and
  compliance exports as part of enterprise usage.

The willingness to pay comes from saved engineering time, reduced release risk,
audit readiness, and lower operational uncertainty.

## ACV, Enterprise, Self-Host, And Audit Value

ACV value:

- Notification control plane increases enterprise ACV by turning Ashr from an
  evaluation dashboard into a workflow system embedded in daily release
  operations.
- Destination count, delivery volume, retention period, replay controls, and
  audit export depth can become plan gates for team, pro, enterprise, and
  self-host enterprise tiers.
- Delivery receipt retention and compliance export are natural enterprise
  upsell features.

Enterprise value:

- Teams can enforce central policies for who receives blocked-release,
  waiver, billing, and report-share events.
- Security admins can review destination changes and delivery failures.
- Auditors can inspect sanitized evidence without asking engineering teams to
  reconstruct chat history manually.

Self-host value:

- Self-host customers often need webhooks into private SIEM, ticketing, GRC, and
  incident systems. A generic signed webhook plane is more valuable than only
  SaaS chat integrations.
- Self-host deployments need local secret references, outbound proxy controls,
  retry queues, and offline-verifiable receipts.
- Enterprise customers can keep raw operational data inside their network while
  still producing Ashr-compatible audit evidence.

Audit value:

- Every notification-relevant action can become an `audit_event` and a delivery
  receipt.
- Evidence bundles can include notification rule snapshots, delivery receipts,
  failure reasons, replay records, and redaction status.
- Auditors can verify that release decisions and human review actions were not
  silently hidden from required channels.

## A1 Dependencies

A1 remains owner of backend truth, delivery infrastructure, credentials, and
billing source events.

Required A1 dependencies:

- Postgres tables or migrations for `integrations`, `notifications`,
  `webhooks`, `webhook_deliveries`, destination secrets, and delivery attempts.
- Tenant isolation and RLS for notification destinations and delivery records.
- Encrypted secret references for Slack, Teams, and webhook credentials.
- Worker/outbox delivery service with retries, idempotency, dead-letter, replay,
  and operational health.
- Signed webhook delivery contract with timestamp, event id, payload hash, and
  replay defense.
- API gateway routes for destination management and delivery readback.
- Usage events for notification attempts, successful deliveries, retries,
  dead-letter rows, and receipt retention.
- Billing ledger integration for notification-related usage.
- Observability with structured logs that exclude raw payload secrets.
- Production persistence and backup/restore behavior for delivery evidence.

## A2 Dependencies

A2 remains owner of policy semantics, security verification, redaction, and
evidence correctness.

Required A2 dependencies:

- Policy rules for which release, review, billing, report, and security events
  are notify-worthy.
- Failure taxonomy and severity mapping for notification routing.
- Redaction verification for notification payload previews and delivery records.
- Abuse tests for webhook replay, destination poisoning, SSRF-style destination
  abuse, secret leakage, and alert flooding.
- Evidence verifier rules for notification delivery receipts.
- Security tests for signed webhook verification and timestamp windows.
- Policy checks for waiver/approval/denial notification requirements.
- Regression fixtures proving notification payloads do not leak raw customer
  content or secrets.

## A3 Responsibilities

A3 should own the product control surfaces:

- Destination settings UI for Slack, Teams, and webhooks.
- Notification rule UI for event type, severity, project, environment, reviewer
  role, and release policy filters.
- Delivery receipt views in dashboard, report center, review workflow, and admin
  audit surfaces.
- Test-send UI that uses sanitized fixtures and RBAC-gated backend routes.
- Pause/resume, rotate, delete, and replay workflows with audit confirmation.
- Billing/admin read-only views for delivery volume, failures, replay counts,
  and retention posture.
- Product copy that makes notification state operationally clear without
  claiming production delivery before A1/A2 evidence exists.

## Next-Round Growth Points

1. Define `a3.notification_control_plane.v1` fixture contract.
2. Add dashboard readiness panel for Slack, Teams, and webhook destinations.
3. Add notification rule schema for event type, severity, project, environment,
   release policy, and reviewer role.
4. Add delivery receipt summary schema with redacted payload metadata only.
5. Add destination lifecycle states: draft, active, paused, failed, disabled,
   rotated, deleted.
6. Add Slack destination readiness surface.
7. Add Teams destination readiness surface.
8. Add generic webhook readiness surface.
9. Add signed webhook contract documentation and UI readback fields.
10. Add retry/dead-letter/replay status readback for each destination.
11. Add RBAC boundary matrix for create, test, pause, replay, rotate, and delete.
12. Add audit event mapping for destination and delivery lifecycle mutations.
13. Add usage-readiness mapping for notification attempts and deliveries.
14. Add billing-readiness mapping for plan limits, destination count, delivery
    volume, retention days, and replay controls.
15. Add redacted payload preview fixture.
16. Add delivery failure taxonomy visible to admins.
17. Add notification suppression and dedupe readiness contract.
18. Add report-center linkage from delivery receipt to evidence bundle.
19. Add review-workflow linkage showing whether approval, denial, or waiver
    notification was required and delivered.
20. Add admin export surface for notification audit evidence.
21. Add self-host notes for outbound proxy, private destinations, and local
    secret references.
22. Add OpenAPI placeholders for notification destination and delivery readback.
23. Add test coverage for dashboard wiring and API-backed readiness payload.
24. Add commercial audit note separating local readiness from live Slack/Teams
    or webhook delivery.
25. Add migration-readiness checks for A1 tables and worker capabilities.

## Parallelizable Work

Can run in parallel:

- A1 can design DB tables, outbox worker, signing, retry, and usage event
  contracts while A3 designs dashboard/readiness UI against fixtures.
- A2 can build redaction, replay-abuse, SSRF, payload-leak, and verifier tests
  while A1 implements delivery mechanics.
- A3 can implement Slack, Teams, and generic webhook destination read-only
  surfaces in parallel if they share the same destination schema.
- A3 billing-readiness and audit-readiness panels can proceed before live
  delivery, as long as they are clearly labeled as readiness/readback.
- Documentation, fixtures, OpenAPI placeholders, and dashboard wiring tests can
  proceed before real credentials exist.

Should not run independently:

- Live delivery cannot be claimed until A1 owns credential storage, workers,
  idempotency, retry, and readback.
- Payload safety cannot be claimed until A2 redaction and abuse tests pass.
- Billing cannot be claimed until A1 emits durable usage events into the ledger.
- Audit-grade evidence cannot be claimed until delivery receipts join the
  evidence bundle/verifier path.

## Suggested Evidence Contract

Minimum contract fields for the next fixture:

```text
schema_version
generated_at
organization_id
project_id
environment_id
notification_destinations[]
notification_rules[]
delivery_receipts[]
delivery_failure_summary
rbac_matrix
usage_readiness
billing_readiness
audit_event_mapping
redaction_status
a1_dependencies
a2_dependencies
evidence_bundle_impact
```

Destination fields:

```text
destination_id
destination_type
display_name
scope
state
secret_ref_status
created_by_actor_hash
last_test_status
last_delivery_status
failure_reason_code
delivery_receipt_retention_days
```

Delivery receipt fields:

```text
delivery_id
event_id
event_type
destination_id
attempt_count
status
idempotency_key_hash
payload_schema_version
payload_hash
redaction_status
created_at
delivered_at
trace_id
request_id
audit_event_id
```

## Testing Evidence Placeholders

These are placeholders for the implementation round. They are intentionally not
claimed as completed by this documentation-only audit.

Planned static checks:

```text
node --check services/report/a3_notification_control_plane.mjs
node --check services/report/a3_api_server.mjs
node --check apps/dashboard/src/app.mjs
```

Planned focused tests:

```text
node --test tests/a3/a3_notification_control_plane.test.mjs
node --test tests/a3/a3_api_server.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Planned full A3 tests:

```text
node --test tests/a3/*.mjs
npm.cmd run test:e2e
```

Evidence to capture later:

- Focused Node result: TBD.
- Full A3 Node suite result: TBD.
- Playwright E2E result: TBD.
- Commercial checklist result: TBD.
- Hygiene checklist result: TBD.
- `git diff --check`: TBD.
- Secret scan / `.env.local` non-read confirmation: TBD.
- Live Slack delivery: not claimed.
- Live Teams delivery: not claimed.
- Live generic webhook delivery: not claimed.
- Billing provider mutation: not claimed.

## Auditor Position

Growth-Auditor verdict: this is a strong A3 next-round target because it sits at
the intersection of workflow, enterprise readiness, audit evidence, and usage
metering.

The commercial line is clear: customers do not pay for a chat ping. They pay for
release-critical notifications that are governed, traceable, replayable,
metered, and exportable as audit evidence.

The next implementation should avoid isolated Slack/Teams demos. It should build
one shared notification control plane contract first, then let Slack, Teams, and
generic webhooks become destination adapters under the same policy, RBAC, audit,
usage, and evidence model.

## Implementation Closeout

This note started as a growth-auditor plan. The same round then implemented the
shared A3 notification control plane contract.

Implemented evidence:

- `services/report/a3_notification_control_plane.mjs`
- `tests/a3/a3_notification_control_plane.test.mjs`
- `GET /api/a3/notifications/control-plane`
- Dashboard panel: `Notification Control Plane`
- Artifact registry entry: `notification_control_plane`
- Artifact packet: `notification_readiness_packet`
- SQL contract migration: `015_notification_control_plane`
- Commercial API contract routes:
  - `GET /v1/notification-channels`
  - `POST /v1/notifications/test`
  - `POST /v1/release-gates/{release_gate_id}/notifications`

Updated verification:

- Focused notification/live workflow/RBAC tests: 10 pass, 0 fail.
- Focused artifact/commercial contract tests: 12 pass, 0 fail.
- Full A3 Node suite: 262 pass, 0 fail.
- Playwright E2E: 10 pass, 0 fail.
- Commercial CL guard: passed.
- Hygiene CL guard: passed.
- Diff check: passed.

Still not claimed:

- No real Slack message was sent.
- No real Teams message was sent.
- No real email was sent.
- No customer webhook was called.
- No provider credential, webhook URL, token, cookie, email, payment value, or
  raw share token was written.

The current implementation is therefore a product/API/report/audit/readiness
control plane, not a live external delivery system. Live delivery remains A1
hosted-worker work, and payload correctness/security certification remains A2
verification work.
