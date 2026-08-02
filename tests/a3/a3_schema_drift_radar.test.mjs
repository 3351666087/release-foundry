import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { mkdtemp, rm } from "node:fs/promises";
import { test } from "node:test";

import {
  A3_A1_A2_INTEGRATION_ARTIFACTS,
  A3_A1_A2_SCHEMA_CONTRACTS,
  buildA1A2SchemaDriftRadar
} from "../../services/report/a3_schema_drift_radar.mjs";
import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

test("A3 schema drift radar validates current A1/A2 source contracts without embedding raw schemas", async () => {
  const radar = await buildA1A2SchemaDriftRadar();

  assert.equal(radar.schema_version, "a3.a1_a2_schema_drift_radar.v1");
  assert.equal(radar.status, "compatible");
  assert.equal(radar.contract_count, A3_A1_A2_SCHEMA_CONTRACTS.length);
  assert.equal(radar.drift_count, 0);
  assert.equal(radar.missing_count, 0);
  assert.equal(radar.safety.raw_schema_payload_embedded, false);
  assert.equal(radar.safety.schema_hashes_only, true);
  assert.match(radar.a1_a2_boundary, /does not modify A1 runner semantics or A2 judge semantics/);
  assert.equal(radar.integration_matrix.schema_version, "a3.a1_a2_integration_matrix.v1");
  assert.equal(radar.integration_matrix.status, "aligned");
  assert.equal(radar.integration_matrix.domain_count, A3_A1_A2_INTEGRATION_ARTIFACTS.length);
  assert.equal(radar.integration_matrix.aligned_domain_count, A3_A1_A2_INTEGRATION_ARTIFACTS.length);
  assert.equal(radar.integration_matrix.a1_domain_count, 4);
  assert.equal(radar.integration_matrix.a2_domain_count, 3);
  assert.equal(radar.integration_matrix.commercial_summary.china_payment_contract_ready, true);
  assert.equal(radar.integration_matrix.commercial_summary.durable_eval_store_ready, true);
  assert.equal(radar.integration_matrix.commercial_summary.scenario_candidate_count, 12);
  assert.equal(radar.integration_matrix.commercial_summary.main_scenario_pack_mutated_by_a3, false);
  assert.equal(radar.integration_matrix.safety.raw_artifact_payload_embedded, false);

  const byId = Object.fromEntries(radar.contracts.map((item) => [item.schema_contract_id, item]));
  assert.equal(byId.a1_run_result.status, "compatible");
  assert.ok(byId.a1_run_result.required_fields.includes("field_map_version"));
  assert.ok(byId.a1_trace_event.required_fields.includes("observation"));
  assert.ok(byId.a2_grade_results.required_fields.includes("grade_results"));
  assert.ok(byId.a2_release_gate.required_fields.includes("required_evidence"));
  assert.ok(radar.contracts.every((item) => /^[a-f0-9]{64}$/.test(item.content_hash)));
  assert.doesNotMatch(JSON.stringify(radar), /Bearer|Cookie|RELEASEFOUNDRY_API_KEY|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/);
});

test("A3 schema drift radar fails closed when critical A1/A2 fields disappear", async () => {
  const dir = await mkdtemp(join(tmpdir(), "a3-schema-drift-"));
  try {
    await mkdir(join(dir, "docs/a1/schemas"), { recursive: true });
    await mkdir(join(dir, "docs/a2/schemas"), { recursive: true });
    for (const contract of A3_A1_A2_SCHEMA_CONTRACTS) {
      await writeFile(join(dir, contract.path), JSON.stringify({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        title: contract.id,
        type: "object",
        required: contract.requiredFields,
        properties: Object.fromEntries(contract.requiredFields.map((field) => [field, { type: "string" }])),
        "$defs": {
          local_judge_run: { required: ["schema_version", "scenario_id", "case_id", "passed", "score", "primary_failure_class", "judge_results"] },
          grade_result: { required: ["schema_version", "scenario_id", "case_id", "judge_mode", "judge_version", "passed", "score", "max_score", "rubric_scores", "failure_analysis", "evidence", "metadata"] },
          failure_analysis: { required: ["schema_version", "primary_failure_class", "failure_classes", "severity", "summary", "details", "remediation", "safety_blocking"] },
          required_evidence: { required: ["source", "required_count", "current_available", "private_input_ref", "collection_packet_ref", "commands"] },
          pr_annotation: { required: ["level", "title", "message", "evidence_refs"] },
          failure_class: { enum: ["none", "wrong_intent", "missing_required_tool", "wrong_arguments", "unsafe_or_policy_violation"] }
        }
      }), "utf8");
    }
    await writeFile(join(dir, "docs/a1/schemas/run_result.schema.json"), JSON.stringify({
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      title: "Broken A1 RunResult",
      type: "object",
      required: ["run_id", "dataset_id"],
      properties: {
        aggregate_metrics: { properties: { schema_version: { const: "wrong.version" } } }
      }
    }), "utf8");

    const radar = await buildA1A2SchemaDriftRadar({ repoRoot: dir });
    const runResult = radar.contracts.find((item) => item.schema_contract_id === "a1_run_result");

    assert.equal(radar.status, "needs_attention");
    assert.equal(runResult.status, "drift_detected");
    assert.ok(runResult.findings.some((item) => item.code === "missing_required_field" && item.field === "trace_completeness"));
    assert.ok(runResult.findings.some((item) => item.code === "schema_const_mismatch"));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("A3 API exposes schema drift radar behind audit RBAC", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const { server, url } = await startA3ApiServer({ store, routeAccessMode: "demo_contract" });
  try {
    const denied = await fetch(`${url}/api/a3/a1-a2/schema-drift?source=mock`, {
      headers: { "x-a3-role": "viewer" }
    });
    assert.equal(denied.status, 403);
    const deniedPayload = await denied.json();
    assert.equal(deniedPayload.schema_version, "a3.api_authz_denied.v1");
    assert.equal(deniedPayload.operation, "read_schema_drift");
    assert.equal(deniedPayload.required_permission, "audit:read");

    const response = await fetch(`${url}/api/a3/a1-a2/schema-drift?source=mock`, {
      headers: { "x-a3-role": "auditor" }
    });
    assert.equal(response.status, 200);
    const radar = await response.json();
    assert.equal(radar.schema_version, "a3.a1_a2_schema_drift_radar.v1");
    assert.equal(radar.status, "compatible");
    assert.equal(radar.safety.schema_hashes_only, true);
    assert.equal(radar.integration_matrix.schema_version, "a3.a1_a2_integration_matrix.v1");
    assert.equal(radar.integration_matrix.domains.some((item) => item.integration_id === "a2_scenario_generation"), true);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
