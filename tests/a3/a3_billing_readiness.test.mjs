import assert from "node:assert/strict";
import { test } from "node:test";

import { buildA3BillingReadiness } from "../../services/report/a3_billing_readiness.mjs";
import { buildSaasAdminConsole } from "../../services/report/a3_saas_admin.mjs";
import { buildA3UsageLedger } from "../../services/report/a3_usage_ledger.mjs";

test("A3 billing readiness turns usage meters into a read-only paid-plan contract", () => {
  const runFixture = {
    runs: [{
      run_id: "run-billing",
      cases: [{
        case_id: "case-billing",
        status: "failed",
        trace_events: [{ event_type: "agent_response" }, { event_type: "tool_call" }],
        expected: { tool_calls: [{ name: "refund_order" }] },
        actual: { tool_calls: [{ name: "refund_order" }] }
      }]
    }]
  };
  const gradeFixture = {
    grade_results: [{
      case_id: "case-billing",
      passed: false,
      score: 0.4,
      primary_failure_class: "wrong_arguments",
      judge_results: [{ judge_mode: "deterministic", passed: false }]
    }]
  };
  const usageLedger = buildA3UsageLedger({ runFixture, gradeFixture }, {
    reports: [{ report_id: "a3r_billing" }],
    auditEvents: [{ event_type: "report_view" }],
    releaseEvidenceReadbacks: [{ readback_id: "rerb_billing" }],
    importReceipts: [{ receipt_id: "imp_billing" }]
  });
  const adminConsole = buildSaasAdminConsole({ runFixture, gradeFixture });
  const readiness = buildA3BillingReadiness({ usageLedger, adminConsole });

  assert.equal(readiness.schema_version, "a3.billing_readiness.v1");
  assert.equal(readiness.billing_mutations_enabled, false);
  assert.equal(readiness.provider_boundary.checkout_enabled, false);
  assert.equal(readiness.plan_readiness.recommended_next_plan, "team");
  assert.equal(readiness.a1_a2_alignment.a1_usage_source_ready, true);
  assert.equal(readiness.a1_a2_alignment.a2_judge_meter_ready, true);
  assert.equal(readiness.a1_a2_alignment.hosted_report_meter_ready, true);
  assert.equal(readiness.a1_a2_alignment.review_evidence_meter_ready, true);
  assert.ok(readiness.billable_unit_count > 0);
  assert.ok(readiness.meters.some((item) => item.meter === "judge_results" && item.invoice_category === "judge result"));
  assert.ok(readiness.invoice_preview.line_items.some((item) => item.meter === "shareable_reports"));
  assert.ok(readiness.blocked_paid_actions.some((item) => item.action === "manage_usage_limit"));
  assert.ok(readiness.required_db_contracts.includes("billing_invoices"));
  assert.ok(readiness.required_events.includes("billing.subscription_changed"));
  assert.equal(readiness.safety.real_payment_provider_called, false);
});

test("A3 billing readiness exposes quota risk without storing customer secrets", () => {
  const usageLedger = {
    schema_version: "a3.usage_ledger.v1",
    tenant_scope: { organization_id: "org-billing", project_id: "project-billing" },
    meters: [
      { meter: "runs", quantity: 9, billable: true },
      { meter: "cases", quantity: 1, billable: true },
      { meter: "judge_results", quantity: 1, billable: true }
    ]
  };
  const readiness = buildA3BillingReadiness({ usageLedger }, {
    thresholds: { runs: 10 }
  });

  assert.equal(readiness.tenant_scope.organization_id, "org-billing");
  assert.equal(readiness.quota_exposure.find((item) => item.meter === "runs").quota_state, "near_quota");
  assert.equal(readiness.provider_boundary.secret_values_required_in_ui, false);
  assert.doesNotMatch(JSON.stringify(readiness), /@|Bearer|sk-|ghp_/i);
});
