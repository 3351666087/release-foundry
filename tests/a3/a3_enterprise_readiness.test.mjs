import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildEnterpriseReadinessReport
} from "../../services/report/a3_enterprise_readiness.mjs";

test("A3 enterprise readiness summarizes A1 and A2 evidence counts", () => {
  const runFixture = {
    schema_version: "a3.dashboard_fixture.v1",
    runs: [
      {
        run_id: "run-enterprise",
        dataset_id: "dataset-enterprise",
        runner_id: "a1-local-runner",
        status: "passed",
        trace_completeness: 1,
        cases: [
          {
            case_id: "case-a",
            status: "passed",
            expected: { tool_calls: [{ tool: "search" }] },
            actual: { tool_calls: [{ name: "search", arguments: { q: "safe" } }] },
            trace_events: [{ event_id: "case-a:trace:1" }],
            observations: [{ event_type: "agent_response" }]
          },
          {
            case_id: "case-b",
            status: "failed",
            expected: { tool_calls: [] },
            actual: { tool_calls: [] },
            trace_events: [{ event_id: "case-b:trace:1" }]
          }
        ]
      }
    ]
  };
  const gradeFixture = {
    schema_version: "a3.grade_fixture.v1",
    grade_results: [
      {
        case_id: "case-a",
        passed: true,
        score: 100,
        judge_results: [
          { judge_mode: "g1_trace_contract_judge", passed: true },
          { judge_mode: "g2_output_contract_judge", passed: true }
        ]
      },
      {
        case_id: "case-b",
        passed: false,
        score: 40,
        judge_results: [
          { judge_mode: "g1_trace_contract_judge", passed: false }
        ]
      }
    ]
  };

  const report = buildEnterpriseReadinessReport({
    runFixture,
    gradeFixture,
    adminConsole: safeAdminConsole(),
    dbContract: safeDbContract()
  });

  assert.equal(report.schema_version, "a3.enterprise_readiness.v1");
  assert.equal(report.a1_a2_compatibility_notes.a1.run_count, 1);
  assert.equal(report.a1_a2_compatibility_notes.a1.trace_case_count, 2);
  assert.equal(report.a1_a2_compatibility_notes.a1.trace_event_count, 3);
  assert.equal(report.a1_a2_compatibility_notes.a1.tool_case_count, 1);
  assert.equal(report.a1_a2_compatibility_notes.a2.grade_case_count, 2);
  assert.equal(report.a1_a2_compatibility_notes.a2.judge_result_count, 3);
  assert.equal(report.a1_a2_compatibility_notes.a2.judge_mode_count, 2);
  assert.ok(report.readiness_score > 80);
  assert.deepEqual(report.blockers, []);
  assert.ok(report.enabled_capabilities.some((item) => item.id === "a1_trace_audit" && item.evidence_count === 2));
  assert.ok(report.enabled_capabilities.some((item) => item.id === "a2_judge_ingest" && item.evidence_count === 2));
});

test("A3 enterprise readiness does not echo secrets from inputs", () => {
  const report = buildEnterpriseReadinessReport({
    runFixture: {
      schema_version: "a3.dashboard_fixture.v1",
      runs: [
        {
          run_id: "run-secret",
          status: "passed",
          cases: [
            {
              case_id: "case-secret",
              status: "passed",
              actual: {
                final_response: "Bearer abcdefghijklmnopqrstuvwxyz012345",
                tool_calls: [
                  {
                    name: "secret_probe",
                    arguments: { api_key: "sk_abcdefghijklmnopqrstuvwxyz" },
                    output: "Cookie: session=super-secret"
                  }
                ]
              },
              trace_events: [
                {
                  event_id: "case-secret:trace:1",
                  observation: { text: "github_pat_abcdefghijklmnopqrstuvwxyz123456" }
                }
              ]
            }
          ]
        }
      ]
    },
    gradeFixture: {
      schema_version: "a3.grade_fixture.v1",
      grade_results: [
        {
          case_id: "case-secret",
          passed: true,
          score: 100,
          judge_results: [
            {
              judge_mode: "g1_trace_contract_judge",
              evidence: { final_response_excerpt: "ASHR_API_KEY=live-secret-value" }
            }
          ]
        }
      ]
    },
    adminConsole: {
      ...safeAdminConsole(),
      leaked_value: "Authorization: Bearer qwertyuiopasdfghjklzxcvbnm"
    },
    dbContract: safeDbContract()
  });

  const serialized = JSON.stringify(report);
  assert.doesNotMatch(serialized, /Bearer\s+[A-Za-z0-9._~+/=-]+/);
  assert.doesNotMatch(serialized, /\bsk_[A-Za-z0-9_=-]{12,}\b/);
  assert.doesNotMatch(serialized, /\bgithub_pat_[A-Za-z0-9_=-]{12,}\b/);
  assert.doesNotMatch(serialized, /\bASHR_API_KEY\s*=/);
  assert.doesNotMatch(serialized, /Cookie:\s*session=/);
  assert.equal(report.a1_a2_compatibility_notes.a1.trace_case_count, 1);
  assert.equal(report.a1_a2_compatibility_notes.a2.judge_result_count, 1);
});

function safeAdminConsole() {
  return {
    schema_version: "a3.saas_admin_console.v1",
    actions: [{ action: "view_usage" }, { action: "download_audit_bundle" }],
    cloud_management: {
      real_mutations_enabled: false
    },
    safety: {
      secret_values_allowed: false,
      real_api_key_secrets_enabled: false,
      real_team_invites_enabled: false,
      real_billing_mutations_enabled: false,
      real_trust_publish_enabled: false
    }
  };
}

function safeDbContract() {
  return {
    schema_version: "a3.saas_db_contract.v1",
    recommended_primary_db: "postgres",
    tenant_columns_required: ["organization_id", "project_id"],
    tables: ["organizations", "projects", "runs", "cases"],
    api_surfaces: ["GET /api/a3/dashboard"]
  };
}
