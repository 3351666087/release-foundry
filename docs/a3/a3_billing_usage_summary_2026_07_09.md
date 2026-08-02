# A3 Billing Usage Summary

## Purpose

A3 now exposes a read-only billing and usage summary for customer-facing reports. It turns A1 run evidence, A2 judge evidence, and A3 hosted-report activity into a commercial snapshot without enabling billing mutations.

## Report Shape

The new `a3.billing_usage_summary.v1` object is emitted by `services/report/report_builder.mjs` and reused by `services/report/a3_usage_ledger.mjs`.

Key fields:

- `plan`: current or observed plan name, billing period, currency, included units, and overage flag.
- `quota`: used units, included units, remaining units, overage units, and read-only enforcement status.
- `billable_meter`: the primary customer-readable meter, usually `cases`.
- `billable_meters`: all billable meters with quantities and billable unit counts.
- `overage_risk`: `within_quota`, `watch`, `near_quota`, `over_quota`, or `unknown_limit`.
- `evidence_counts.a1`: run, case, trace, observation, tool-call, and media evidence counts.
- `evidence_counts.a2`: graded case, judge result, failed case, and failure-class counts.

## Meter Semantics

Default billable meters are:

- `runs`
- `cases`
- `judge_results`
- `media_evidence_cases`

A3 usage ledger can add hosted-report meters such as `shareable_reports`, `report_views`, `report_revocations`, `release_evidence_readbacks`, and `api_imports`.

Non-billable evidence meters remain visible for audit and risk review:

- `failed_cases`
- `trace_events`
- `tool_call_cases`

## Boundaries

This is not a payment integration and does not enforce quotas. Billing mutations remain disabled. The summary is safe for reports because it uses public-safe A1/A2 fixture fields, redacted usage/quota observations, and A3-local report activity.

A1 still owns the durable usage event source, quota enforcement, billing provider integration, and ledger rollups. A2 still owns judge cost/risk policy. A3 owns the user-visible plan, quota, overage-risk, and evidence-count presentation.

## Validation

Focused test command:

```sh
node --test tests/a3/report_builder.test.mjs
```

The test covers plan/quota display, billable meters, overage risk, disabled billing mutations, and A1/A2 evidence counts.
