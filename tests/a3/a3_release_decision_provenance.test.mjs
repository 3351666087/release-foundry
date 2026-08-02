import assert from "node:assert/strict";
import { test } from "node:test";

import {
  A3_RELEASE_DECISION_PROVENANCE_SCHEMA_VERSION,
  buildA3ReleaseDecisionProvenance
} from "../../services/report/a3_release_decision_provenance.mjs";

const scope = {
  organization_id: "org-provenance",
  tenant_id: "tenant-provenance",
  workspace_id: "workspace-provenance",
  project_id: "project-provenance",
  environment_id: "production"
};
const actor = { role: "reviewer", ...scope };

test("builds a read-only A1/A2 release decision evidence graph", () => {
  const result = build(baseInputs(), { tenantScope: scope, actor });

  assert.equal(result.schema_version, A3_RELEASE_DECISION_PROVENANCE_SCHEMA_VERSION);
  assert.equal(result.status, "ready");
  assert.equal(result.release_decision, "block");
  assert.equal(result.decision_authority, "a2.release_gate.v1");
  assert.deepEqual(result.missing_contracts, []);
  assert.deepEqual(new Set(result.nodes.map((item) => item.type)), new Set([
    "run", "case", "trace", "tool_call", "grade", "failure", "release_decision",
    "review_visibility", "share_visibility", "audit_visibility", "usage_visibility", "billing_visibility"
  ]));
  assert.ok(result.edges.some((item) => item.relation === "graded_by"));
  assert.equal(result.edges.filter((item) => item.relation === "supports_grade").length, 2);
  assert.ok(result.edges.some((item) => item.relation === "informs"));
  assert.ok(result.edges.some((item) => item.relation === "bills_from"));
  assert.equal(result.semantics.a1_mutated, false);
  assert.equal(result.semantics.a2_mutated, false);
  assert.equal(result.governance.rbac.allowed, true);
});

test("fails closed when A1 RunResult is missing", () => {
  const inputs = baseInputs();
  delete inputs.a1RunResult;
  const result = build(inputs, { tenantScope: scope, actor });

  assert.equal(result.status, "blocked");
  assert.equal(result.release_decision, "block");
  assert.ok(result.missing_contracts.includes("a1.RunResult/releasefoundry.run_result.v1"));
  assert.ok(result.blockers.some((item) => item.type === "missing_contract"));
});

test("fails closed when A2 grade and release contracts are missing", () => {
  const inputs = baseInputs();
  delete inputs.a2GradeResults;
  delete inputs.a2ReleaseGate;
  const result = build(inputs, { tenantScope: scope, actor });

  assert.equal(result.status, "blocked");
  assert.equal(result.upstream_release_decision, null);
  assert.deepEqual(result.missing_contracts, ["a2.grade_results.v1", "a2.release_gate.v1"]);
});

test("blocks cross-scope provenance even when upstream gate says pass", () => {
  const inputs = baseInputs();
  inputs.a2ReleaseGate = { ...inputs.a2ReleaseGate, decision: "pass", tenant_scope: { ...scope, project_id: "project-other" } };
  const result = build(inputs, { tenantScope: scope, actor });

  assert.equal(result.status, "blocked");
  assert.equal(result.release_decision, "block");
  assert.equal(result.upstream_release_decision, "pass");
  assert.ok(result.blockers.some((item) => item.type === "scope_mismatch"));
  assert.equal(result.governance.tenant.matched, false);
});

test("fails closed for client-declared or otherwise untrusted identity context", () => {
  const result = buildA3ReleaseDecisionProvenance(baseInputs(), {
    tenantScope: scope,
    actor,
    auth: { trusted: false, auth_state: "hosted_session" }
  });

  assert.equal(result.status, "blocked");
  assert.equal(result.release_decision, "block");
  assert.equal(result.governance.auth.allowed, false);
  assert.ok(result.blockers.some((item) => item.type === "auth_untrusted"));
});

test("redacts sensitive trace, tool argument, and failure fields", () => {
  const inputs = baseInputs();
  inputs.a1RunResult.cases[0].observations[0].content = "Authorization: Bearer trace-secret-1234567890";
  inputs.a1RunResult.cases[0].observations[0].tool_calls[0].arguments = {
    api_key: "sk_live_tool_secret_1234567890",
    order_id: "order-safe"
  };
  inputs.a2GradeResults.grade_results[0].judge_results[0].failure_analysis.summary = "owner@example.com leaked a token";
  const result = build(inputs, { tenantScope: scope, actor });
  const serialized = JSON.stringify(result);

  assert.equal(result.status, "ready");
  assert.ok(result.governance.redaction.replacement_count >= 3);
  assert.match(serialized, /\[REDACTED/);
  assert.doesNotMatch(serialized, /trace-secret|sk_live_tool_secret|owner@example\.com/);
  assert.equal(result.governance.redaction.residual_finding_count, 0);
});

function build(inputs, options) {
  const snapshot = structuredClone(inputs);
  const result = buildA3ReleaseDecisionProvenance(inputs, {
    ...options,
    auth: { trusted: true, auth_state: "hosted_session" }
  });
  assert.deepEqual(inputs, snapshot, "bridge must not mutate upstream evidence");
  return result;
}

function baseInputs() {
  return {
    a1RunResult: {
      run_id: "run-provenance",
      dataset_id: "dataset-provenance",
      runner_id: "a1-runner",
      status: "completed",
      trace_completeness: 1,
      aggregate_metrics: { schema_version: "releasefoundry.run_result.v1" },
      tenant_scope: scope,
      cases: [{
        case_id: "case-provenance",
        scenario_id: "scenario-provenance",
        status: "failed",
        observations: [{
          observation_id: "observation-provenance",
          run_id: "run-provenance",
          case_id: "case-provenance",
          event_type: "tool_call",
          status: "completed",
          content: "refund_order was called",
          tool_calls: [{ id: "tool-provenance", name: "refund_order", arguments: { order_id: "order-safe" } }]
        }]
      }]
    },
    a2GradeResults: {
      schema_version: "a2.grade_results.v1",
      tenant_scope: scope,
      grade_results: [{
        schema_version: "a2.local_judge_run.v1",
        case_id: "case-provenance",
        scenario_id: "scenario-provenance",
        passed: false,
        score: 42,
        primary_failure_class: "wrong_arguments",
        judge_results: [{
          evidence: {
            trace_event_ids: ["observation-provenance"],
            tool_call_ids: ["tool-provenance"]
          },
          failure_analysis: {
            severity: "major",
            safety_blocking: false,
            summary: "The refund amount was incorrect."
          }
        }]
      }]
    },
    a2ReleaseGate: {
      schema_version: "a2.release_gate.v1",
      report_id: "release-gate-provenance",
      decision: "block",
      exit_code: 2,
      risk_score: 72,
      blockers: [{ type: "wrong_arguments" }],
      evidence_refs: ["case-provenance"],
      tenant_scope: scope
    },
    reviewWorkflow: { schema_version: "a3.review_workflow_record.v1", record_id: "review-provenance", status: "reviewed", tenant_scope: scope },
    shareableReport: { schema_version: "a3.shareable_report.v1", report_id: "share-provenance", status: "shareable", visibility: "private_link", tenant_scope: scope },
    usageLedger: { schema_version: "a3.usage_ledger.v1", ledger_id: "usage-provenance", status: "available", tenant_scope: scope },
    billingVisibility: { schema_version: "a3.billing_readiness.v1", report_id: "billing-provenance", status: "ready", tenant_scope: scope },
    audit: { schema_version: "a3.audit_archive_verification.v1", manifest_id: "audit-provenance", status: "verified", tenant_scope: scope }
  };
}
