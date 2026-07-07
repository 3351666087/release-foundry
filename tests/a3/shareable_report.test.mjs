import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildShareableReportPayload,
  renderShareableReportHtml
} from "../../services/report/a3_shareable_report.mjs";

test("A3 shareable report wraps release evidence in a hosted-report payload", () => {
  const runFixture = {
    runs: [{
      run_id: "run-share-smoke",
      dataset_id: "dataset-share-smoke",
      runner_id: "a1-local-runner",
      status: "completed",
      trace_completeness: 1,
      cases: [{
        case_id: "case-share-smoke",
        scenario_id: "scenario-share-smoke",
        title: "Shareable report smoke",
        status: "passed",
        expected: { final_response: "Refund approved." },
        actual: { final_response: "Refund approved." }
      }]
    }]
  };
  const gradeFixture = {
    grade_results: [{
      case_id: "case-share-smoke",
      scenario_id: "scenario-share-smoke",
      passed: true,
      score: 0.99,
      primary_failure_class: "none",
      judge_results: []
    }]
  };

  const report = buildShareableReportPayload({
    runFixture,
    gradeFixture,
    source: "unit-test"
  }, {
    createdAt: "2026-07-07T00:00:00.000Z",
    reportId: "a3r_unit_test"
  });

  assert.equal(report.schema_version, "a3.shareable_report.v1");
  assert.equal(report.report_id, "a3r_unit_test");
  assert.equal(report.share_url_path, "/reports/a3r_unit_test");
  assert.equal(report.status, "shareable");
  assert.equal(report.report_center.hosted_page_available, true);
  assert.equal(report.artifacts.length, 3);
  assert.match(report.sealed_evidence.payload_hash, /^[a-f0-9]{64}$/);

  const html = renderShareableReportHtml(report);
  assert.match(html, /<!doctype html>/);
  assert.match(html, /A3 Shareable Report|A3 Release Intelligence Report/);
  assert.match(html, /Sealed Evidence/);
  assert.match(html, /case-share-smoke/);
});

test("A3 shareable report redacts secrets before producing hosted payloads", () => {
  const runFixture = {
    runs: [{
      run_id: "run-secret-smoke",
      dataset_id: "dataset-secret-smoke",
      runner_id: "a1-local-runner",
      status: "failed",
      trace_completeness: 1,
      cases: [{
        case_id: "case-secret-smoke",
        scenario_id: "scenario-secret-smoke",
        title: "ASHR_API_KEY=secret_live_value should not leak",
        status: "failed",
        expected: { final_response: "Do not reveal credentials." },
        actual: { final_response: "Authorization: Bearer abcdefghijklmnopqrstuvwxyz" }
      }]
    }]
  };
  const gradeFixture = {
    grade_results: [{
      case_id: "case-secret-smoke",
      scenario_id: "scenario-secret-smoke",
      passed: false,
      score: 0.2,
      primary_failure_class: "unsafe_or_policy_violation",
      judge_results: []
    }]
  };

  const report = buildShareableReportPayload({ runFixture, gradeFixture }, {
    reportId: "a3r_secret_test"
  });
  const serialized = JSON.stringify(report);

  assert.doesNotMatch(serialized, /secret_live_value/);
  assert.doesNotMatch(serialized, /Bearer abcdefghijklmnopqrstuvwxyz/);
  assert.match(serialized, /\[REDACTED/);
  assert.equal(report.redaction.blocked, false);
  assert.equal(report.sealed_evidence.secret_free, true);

  const html = renderShareableReportHtml(report);
  assert.doesNotMatch(html, /secret_live_value/);
  assert.doesNotMatch(html, /Bearer abcdefghijklmnopqrstuvwxyz/);
  assert.match(html, /Sealed Evidence/);
});
