import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildA3EventEnvelope,
  validateA3EventEnvelope
} from "../../services/report/a3_event_envelope.mjs";
import { buildA3SourceArtifacts } from "../../services/report/a3_source_artifacts.mjs";
import {
  buildA3TenantScope,
  tenantScopeMatches,
  validateA3TenantScope
} from "../../services/report/a3_tenant_scope.mjs";

const snapshot = {
  source: "unit",
  organizationId: "org-unit",
  tenantId: "tenant-unit",
  workspaceId: "workspace-unit",
  projectId: "project-unit",
  environmentId: "staging",
  runFixture: {
    runs: [{
      run_id: "run-unit",
      cases: [{
        case_id: "case-unit",
        expected: { tool_calls: [{ name: "refund_order" }] },
        actual: { tool_calls: [] },
        trace_events: [{ event_id: "trace-unit", event_type: "tool_call" }]
      }]
    }]
  },
  gradeFixture: {
    grade_results: [{
      case_id: "case-unit",
      passed: false,
      score: 0.4,
      primary_failure_class: "missing_required_tool"
    }]
  },
  releaseEvidence: {
    schema_version: "a2.release_gate.v1",
    decision: "block",
    risk_score: 90
  }
};

test("A3 tenant scope preserves A1/A2 shared org tenant workspace project fields", () => {
  const scope = buildA3TenantScope({
    organizationId: "org-request",
    tenant_scope: {
      tenant_id: "tenant-request",
      workspace_id: "workspace-request",
      project_id: "project-request",
      environment_id: "prod"
    }
  }, snapshot);

  assert.equal(scope.schema_version, "a3.tenant_scope.v1");
  assert.equal(scope.organization_id, "org-request");
  assert.equal(scope.tenant_id, "tenant-request");
  assert.equal(scope.workspace_id, "workspace-request");
  assert.equal(scope.project_id, "project-request");
  assert.equal(scope.environment_id, "prod");
  assert.equal(validateA3TenantScope(scope).valid, true);
  assert.equal(tenantScopeMatches(scope, { tenantId: "tenant-request", projectId: "project-request" }), true);
  assert.equal(tenantScopeMatches(scope, { tenantId: "tenant-other" }), false);
});

test("A3 event envelope is metadata-only, hash based, and secret free", () => {
  const event = buildA3EventEnvelope({
    event_type: "release_gate.blocked",
    resource_type: "release_gate",
    resource_id: "gate-unit",
    tenant_scope: {
      organization_id: "org-unit",
      tenant_id: "tenant-unit",
      workspace_id: "workspace-unit",
      project_id: "project-unit"
    },
    payload: {
      schema_version: "a3.test_payload.v1",
      authorization: "Bearer should-not-leak",
      email: ["owner", "example.com"].join("@"),
      decision: "block"
    }
  });

  assert.equal(event.schema_version, "ashr.event_envelope.v1");
  assert.equal(event.event_type, "release_gate.blocked");
  assert.equal(event.tenant_id, "tenant-unit");
  assert.equal(event.workspace_id, "workspace-unit");
  assert.match(event.payload_hash, /^[a-f0-9]{64}$/);
  assert.equal(event.payload_inline, false);
  assert.equal(event.safety.raw_secret_values_allowed, false);
  assert.equal(validateA3EventEnvelope(event).valid, true);
  assert.doesNotMatch(JSON.stringify(event), /should-not-leak|owner@example.com|Bearer [A-Za-z0-9]/);
});

test("A3 source artifacts hash A1/A2 inputs without embedding raw payloads", () => {
  const sourceArtifacts = buildA3SourceArtifacts(snapshot);

  assert.equal(sourceArtifacts.schema_version, "a3.source_artifacts.v1");
  assert.equal(sourceArtifacts.source_artifact_count, 5);
  assert.equal(sourceArtifacts.tenant_scope.tenant_id, "tenant-unit");
  assert.equal(sourceArtifacts.safety.raw_payload_embedded, false);
  assert.equal(sourceArtifacts.safety.source_hashes_only, true);

  const byType = Object.fromEntries(sourceArtifacts.artifacts.map((artifact) => [artifact.artifact_type, artifact]));
  assert.equal(byType.a1_run_result.source_lane, "A1");
  assert.equal(byType.a1_trace_event_batch.source_contracts.includes("Trace"), true);
  assert.equal(byType.a1_tool_call_batch.source_contracts.includes("ToolCall"), true);
  assert.equal(byType.a2_grade_result.source_lane, "A2");
  assert.equal(byType.a2_release_gate.source_contracts.includes("ReleaseGate"), true);
  for (const artifact of sourceArtifacts.artifacts) {
    assert.match(artifact.content_hash, /^[a-f0-9]{64}$/);
    assert.equal(artifact.raw_payload_embedded, false);
    assert.equal(artifact.a3_mutates_source_semantics, false);
  }
});
