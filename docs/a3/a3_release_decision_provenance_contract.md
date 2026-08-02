# A3 Release Decision Provenance Contract

## Purpose

`a3.release_decision_provenance.v1` is an additive, read-only A3 view over existing A1 and A2 evidence. It connects a release decision to the run, case, trace/tool-call, grade, score/pass/failure, review, share, usage/billing, and audit records that make the decision inspectable.

The bridge does not run an agent, grade a case, evaluate release policy, mutate storage, post a review, create a share link, or write billing/audit records. A1 runner/billing/storage semantics and A2 judge/release semantics remain authoritative and unchanged.

## Upstream contracts

The implementation reads the current repository contracts:

- A1: `docs/a1/schemas/run_result.schema.json`, `case_result.schema.json`, `observation.schema.json`, `trace_event.schema.json`, A1 billing provider/ledger code, object-storage evidence, and tenant-scoped billing SQL migration.
- A2: `docs/a2/schemas/grade_results.schema.json`, `release_gate.schema.json`, `release_policy.schema.json`, evidence readiness/security contracts, judge failure analysis, release policy/gate code, and SQL/RLS verification signals.
- A3: auth/RBAC boundary, tenant scope, security redaction guard, review workflow, shareable report, usage ledger, billing readiness, and audit archive contracts.

Required decision inputs are:

1. A1 `RunResult` with `aggregate_metrics.schema_version = releasefoundry.run_result.v1` and case trace/observation evidence.
2. A2 `a2.grade_results.v1` with `a2.local_judge_run.v1` case grades.
3. A2 `a2.release_gate.v1`.

Review, share, usage, billing, and audit records are visibility evidence. Their presence never grants release authority and their absence is represented as `available: false`; the bridge does not fabricate them.

## Output

The builder exports:

```js
buildA3ReleaseDecisionProvenance(inputs, {
  tenantScope: {
    organization_id,
    tenant_id,
    workspace_id,
    project_id,
    environment_id
  },
  auth: {
    trusted: true,
    auth_state: "hosted_session"
  },
  actor: { role, organization_id, project_id }
})
```

The result contains:

- `status`: `ready` or `blocked`.
- `release_decision`: the A2 decision only when every required check passes; otherwise fail-closed `block`.
- `upstream_release_decision`: the observed A2 value for diagnosis, never an A3 override.
- `missing_contracts` and blocking findings.
- provenance `nodes` and directed `edges`.
- tenant/auth/RBAC/usage/billing/audit/redaction governance effects.
- explicit no-mutation/no-recomputation semantics.

Node types include `run`, `case`, `trace`, `tool_call`, `grade`, `failure`, `release_decision`, and A3 visibility nodes for review, share, usage, billing, and audit. Edges include `contains`, `emits`, `records`, `graded_by`, `supports_grade`, `explains`, `informs`, `supports`, `reviews`, `exposes`, `meters`, `bills_from`, and `records`. A2 judge evidence IDs are resolved against A1 trace/tool-call nodes; dangling IDs are blocking evidence errors.

## Fail-closed rules

The bridge returns `status: blocked`, `release_decision: block`, and concrete blockers when:

- a required A1/A2 contract is absent or has the wrong version/shape;
- an A1 case has no trace or observation evidence;
- an A2 grade references an unknown A1 case;
- any supplied artifact conflicts with the requested tenant scope;
- the five-field tenant scope is incomplete;
- actor tenant matching or RBAC fails;
- sensitive material remains after redaction.

It never converts missing evidence into a pass, synthesizes upstream records, or recomputes A2 policy.

## Security and visibility

- Tenant: all reads are bound to organization, tenant, workspace, project, and environment. Supplied cross-scope evidence blocks the whole view.
- Auth/RBAC: actor organization/project must match and the default read roles are owner, admin, reviewer, or auditor. The separate `auth` input must be marked trusted by an authoritative hosted-session or service-account backend. Browser headers, query parameters, fixture metadata, and client-provided role strings are not trusted identity evidence and must leave the graph blocked.
- Usage/billing: visibility is read-only and separately identifies required `usage:read` and `billing:read` permissions. Billing remains derived from authoritative usage/billing records, not this graph.
- Audit: audit availability requires `audit:read`; a graph edge only records linkage and does not assert durable persistence.
- Redaction: the existing A3 security guard recursively redacts authorization values, API keys, tokens, secrets, email/identity fields, and signed URLs. Residual findings block output authority.

No raw secret, private evidence payload, credential, signed URL, or raw identity is required by this contract.
