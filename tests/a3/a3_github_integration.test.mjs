import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  buildGitHubActionWorkflowExample,
  buildGitHubCheckRunRequest,
  buildPrCommentUpsertPlan
} from "../../services/report/a3_github_integration.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

function fixturePath(path) {
  return fileURLToPath(new URL(path, import.meta.url));
}

test("A3 GitHub integration builds create-check request without secrets", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const request = buildGitHubCheckRunRequest(payload, {
    repo: "acme/refund-agent",
    headSha: "abc123",
    detailsUrl: "https://example.invalid/a3-gate"
  });

  assert.equal(request.schema_version, "a3.github_check_request.v1");
  assert.equal(request.mode, "create_check_run");
  assert.equal(request.method, "POST");
  assert.equal(request.url, "https://api.github.com/repos/acme/refund-agent/check-runs");
  assert.equal(request.requires_token_scope, "checks:write");
  assert.equal(request.safety.dry_run_only, true);
  assert.equal(request.safety.token_included, false);
  assert.equal(request.body.name, "Ashr++ Release Gate");
  assert.equal(request.body.head_sha, "abc123");
  assert.equal(request.body.conclusion, "failure");
  assert.equal(request.body.details_url, "https://example.invalid/a3-gate");
  assert.equal(request.body.output.annotations.length, 5);
  assert.ok(request.body.output.annotations.every((item) => item.annotation_level === "failure"));
});

test("A3 GitHub integration builds update-check request when check id exists", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const request = buildGitHubCheckRunRequest(payload, {
    repo: "acme/refund-agent",
    headSha: "abc123",
    checkRunId: 42
  });

  assert.equal(request.mode, "update_check_run");
  assert.equal(request.method, "PATCH");
  assert.equal(request.url, "https://api.github.com/repos/acme/refund-agent/check-runs/42");
});

test("A3 GitHub integration builds PR comment create and marker-based update plans", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const createPlan = buildPrCommentUpsertPlan(payload, {
    repo: "acme/refund-agent",
    pullNumber: 17
  });

  assert.equal(createPlan.schema_version, "a3.github_pr_comment_upsert.v1");
  assert.equal(createPlan.mode, "create_new_comment");
  assert.equal(createPlan.request.method, "POST");
  assert.equal(createPlan.request.url, "https://api.github.com/repos/acme/refund-agent/issues/17/comments");
  assert.match(createPlan.request.body.body, /<!-- ashr-plus-plus:release-gate:run_a3_generated_from_a2_g3 -->/);
  assert.match(createPlan.request.body.body, /Decision: \*\*Block release\*\*/);

  const updatePlan = buildPrCommentUpsertPlan(payload, {
    repo: "acme/refund-agent",
    pullNumber: 17,
    existingComments: [{
      id: 1001,
      body: `${createPlan.marker}\nold body`
    }]
  });

  assert.equal(updatePlan.mode, "update_existing_comment");
  assert.equal(updatePlan.existing_comment_id, 1001);
  assert.equal(updatePlan.request.method, "PATCH");
  assert.equal(updatePlan.request.url, "https://api.github.com/repos/acme/refund-agent/issues/comments/1001");
});

test("A3 GitHub Action workflow example keeps the integration in docs-owned scope", () => {
  const workflow = buildGitHubActionWorkflowExample();

  assert.match(workflow, /name: Ashr\+\+ Release Gate/);
  assert.match(workflow, /checks: write/);
  assert.match(workflow, /pull-requests: write/);
  assert.match(workflow, /services\/report\/a3_gate_cli\.mjs/);
  assert.match(workflow, /--output-check artifacts\/ashr-check\.json/);
  assert.match(workflow, /--output-pr-comment artifacts\/ashr-pr-comment\.md/);
});

test("A3 GitHub integration rejects missing repo and missing head sha", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  assert.throws(() => buildGitHubCheckRunRequest(payload, {
    repo: "missing-slash",
    headSha: "abc123"
  }), /repo must be/);
  assert.throws(() => buildGitHubCheckRunRequest(payload, {
    repo: "acme/refund-agent"
  }), /headSha is required/);
  assert.throws(() => buildPrCommentUpsertPlan(payload, {
    repo: "acme/refund-agent",
    pullNumber: 0
  }), /pullNumber/);
});

test("A3 GitHub integration committed fixtures stay redacted", async () => {
  const checkRequest = await loadJson("../../fixtures/a3/p3/a3_github_check_create_request.redacted.json");
  const commentPlan = await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json");
  const workflow = await readFile(new URL("../../docs/a3/p3_github_action_workflow_example.yml", import.meta.url), "utf8");

  assert.equal(checkRequest.safety.token_included, false);
  assert.equal(checkRequest.body.conclusion, "failure");
  assert.equal(commentPlan.safety.secret_values_allowed, false);
  assert.match(commentPlan.request.body.body, /Decision: \*\*Block release\*\*/);
  assert.match(workflow, /actions\/checkout@v4/);
  assert.doesNotMatch(JSON.stringify(checkRequest), /C:\/Users|Authorization|Bearer /);
  assert.doesNotMatch(JSON.stringify(commentPlan), /C:\/Users|Authorization|Bearer /);
});
