# A3 UI Action Security Preflight Contract

Schema: `a3.ui_action_security_preflight.v1`

## Purpose

`preflightA3UiAction` is a fail-closed, metadata-only security boundary for reviewer decisions and hosted report UI actions. It returns a decision for a later server-side executor. It does not persist a review, create or revoke a report, render an export, call a cloud provider, or record usage itself.

This contract is additive. Existing A1 authentication/RBAC enforcement, A1 tenant isolation, A1 audit/usage persistence, and A2 evidence/redaction verification remain authoritative at execution time.

## Supported actions

| Action | Required permissions | Audit event | Usage meter |
|---|---|---|---|
| `reviewer.approve` | `release:approve` | `approval.recorded` | `review_decisions` |
| `reviewer.deny` | `release:review` | `denial.recorded` | `review_decisions` |
| `reviewer.waiver` | `release:review` | `waiver.requested` | `review_decisions` |
| `hosted_report.create` | `reports:create`, `reports:share` | `report.share_link_created` | `report_creations` |
| `hosted_report.revoke` | `reports:revoke` | `report.share_link_revoked` | `report_revocations` |
| `hosted_report.export` | `reports:create` | `report.export_requested` | `report_exports` |

Permissions are checked twice: each permission must be present in `actor.permissions` and must belong to `actor.role` in the current `A3_RBAC_ROLES` contract. A client cannot grant itself a permission by adding a string to the request.

## Input contract

The preflight input contains:

- `action`: one supported action.
- `auth`: `authenticated: true`, `auth_state: hosted_session`, and the bound scope.
- `session`: `state: active`, an opaque `session_ref` (never a cookie or token), and the bound scope.
- `scope`: explicit `organization_id`, `tenant_id`, `workspace_id`, `project_id`, and `environment_id`.
- `actor`: role, explicit permissions, SHA-256 `actor_hash`, and the bound scope.
- `payload`: action metadata. Raw credentials, PII, signed URLs, and secrets are prohibited.
- `evidence.a1` and `evidence.a2`: non-empty arrays of `{ ref, sha256 }`; raw evidence is prohibited.
- `audit_envelope`: `releasefoundry.event_envelope.v1`, safe `request_ref` and `trace_ref`, optional safe `event_ref`/`resource_ref`, and `payload_inline` other than `true`.

All four scope bindings (request, auth, session, and actor) must be complete and exactly equal. Local defaults are intentionally not accepted for hosted UI mutations.

## Fail-closed rules

`allowed` is false when any blocker exists. Blockers use stable category codes and field paths without rejected values. Blocking conditions include:

- unknown action, missing hosted authentication, inactive/expired session, or missing session reference;
- incomplete scope, missing scope binding, or any scope mismatch;
- invalid role, absent permissions, or insufficient role-bound permission;
- missing/invalid A1 or A2 evidence references;
- missing/invalid metadata-only audit envelope;
- raw token/cookie/authorization, email, signed URL, API key, password, private key, or secret material anywhere in the input.

Secret references and SHA-256 hashes are allowed only in fields ending in `_ref`, `_hash`, or `sha256`. Sensitive `_ref` values must be explicit scheme-based indirections such as `vault:reports/export-key`; a raw value renamed as a reference still fails closed. Sensitive hashes must be 64-character SHA-256 hex digests. Every reference remains subject to the restricted character and length policy.

## Output contract

The result contains `allowed`, sanitized `blockers`, `required_permissions`, `audit_event_skeleton`, `usage_meter_intent`, `redaction_summary`, and `execution_boundary`.

The audit skeleton is metadata-only. Its variable values are scope/resource/session/request/trace refs or SHA-256 hashes; it never contains the input payload, actor identity, email, credential, signed URL, or raw evidence. When sensitive material is detected, `payload_hash` binds only the action's safe metadata and detected categories, not the rejected raw value, so the decision cannot be used as a secret-confirmation oracle. The usage intent is advisory and states whether a downstream executor may record usage after accepting the action. Blocked attempts use `do_not_record_blocked_action` in this intent; an independent security audit pipeline may still record the sanitized denial envelope.

`execution_boundary` always reports:

```json
{
  "decision_only": true,
  "executor_invoked": false,
  "persistence_write_performed": false,
  "cloud_write_performed": false
}
```

## A1/A2 handoff

A1 must revalidate the hosted session, role/permission, tenant scope, idempotency, audit envelope, and usage intent in the API gateway/server-side executor before any mutation. A1 owns durable audit and usage writes. A2 must verify referenced release/evidence hashes, policy state, waiver constraints, export redaction, and abuse cases. A successful UI preflight is necessary but never sufficient authorization for a cloud write.

## Residual risks

- Pattern scanning cannot prove that every opaque string is harmless. Executors must resolve only allowlisted ref schemes and keep secret values outside UI payloads.
- This module does not verify revocation, session freshness beyond an optional expiry timestamp, evidence existence, hash provenance, or current release state; those require authoritative A1/A2 services.
- `hosted_report.export` reuses the current additive `reports:create` permission because the RBAC contract has no `reports:export` permission. A future RBAC version should introduce a dedicated export permission if export access diverges from report creation.
