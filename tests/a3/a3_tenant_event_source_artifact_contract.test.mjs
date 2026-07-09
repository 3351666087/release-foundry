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

test("A3 source artifacts include optional G3 A1/A2 calibration inputs when present", () => {
  const sourceArtifacts = buildA3SourceArtifacts({
    ...snapshot,
    evidenceReadiness: {
      a1_official_api_readonly_manifest: {
        schema_version: "a1.official_api_readonly_manifest.v1",
        available: true,
        read_step_count: 4,
        raw_payload_values_included: false
      },
      a1_official_api_mutating_index: {
        schema_version: "a1.official_api_mutating_index.v1",
        available: true,
        record_count: 3,
        secret_values_included: false
      },
      a1_official_api_paid_media_summary: {
        schema_version: "a1.official_api_paid_media_summary.v1",
        available: true,
        total_step_count: 2,
        safe_for_paid_media_claims: true
      }
    },
    resultPersistence: {
      schema_version: "a2.result_persistence_manifest.v1",
      record_count: 2,
      records: [
        { record_type: "judge_result", output_hash: "sha256:unit" },
        { record_type: "release_unblock_checklist", output_hash: "sha256:unit-unblock" }
      ],
      metadata: { public_safe: true }
    },
    releaseUnblockChecklist: {
      schema_version: "a2.release_unblock_checklist.v1",
      overall_status: "blocked",
      gate_items: [{ gate: "C3", blocks_release: true }]
    }
  });

  const byType = Object.fromEntries(sourceArtifacts.artifacts.map((artifact) => [artifact.artifact_type, artifact]));
  assert.equal(sourceArtifacts.source_artifact_count, 10);
  assert.equal(byType.a1_official_api_readonly_manifest.record_count, 4);
  assert.equal(byType.a1_official_api_mutating_index.record_count, 3);
  assert.equal(byType.a1_official_api_paid_media_summary.source_lane, "A1");
  assert.equal(byType.a2_result_persistence_manifest.source_lane, "A2");
  assert.equal(byType.a2_release_unblock_checklist.record_count, 1);
  assert.doesNotMatch(JSON.stringify(sourceArtifacts), /should-not-leak|Bearer|Cookie|owner@example\.com|sk-[A-Za-z0-9]/);
});
