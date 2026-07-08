import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  buildBranchProtectionRequiredCheckPlan,
  buildGitHubActionWorkflowExample,
  buildGitHubCheckRunRequest,
  buildPrCommentUpsertPlan,
  publishGitHubCheckRun,
  publishPrCommentUpsert
} from "../../services/report/a3_github_integration.mjs";
import {
  buildGitHubPublishCliReceipt,
  parseGitHubPublishArgs,
  runGitHubPublishCli
} from "../../services/report/a3_github_publish_cli.mjs";

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
  assert.match(workflow, /services\/report\/a3_github_publish_cli\.mjs/);
  assert.match(workflow, /--output-check artifacts\/ashr-check\.json/);
  assert.match(workflow, /--output-pr-comment artifacts\/ashr-pr-comment\.md/);
  assert.match(workflow, /--output-receipt artifacts\/ashr-github-check-receipt\.json/);
  assert.match(workflow, /--output-receipt artifacts\/ashr-pr-comment-receipt\.json/);
  assert.match(workflow, /--pr-comment/);
  assert.match(workflow, /--live --json/);
  assert.doesNotMatch(workflow, /gh[pousr]_[A-Za-z0-9_]+|Bearer /);
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
  const publishReceipt = await loadJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json");
  const commentReceipt = await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json");
  const requiredCheckPlan = await loadJson("../../fixtures/a3/p3/a3_github_required_check_plan.redacted.json");
  const workflow = await readFile(new URL("../../docs/a3/p3_github_action_workflow_example.yml", import.meta.url), "utf8");

  assert.equal(checkRequest.safety.token_included, false);
  assert.equal(checkRequest.body.conclusion, "failure");
  assert.equal(commentPlan.safety.secret_values_allowed, false);
  assert.equal(publishReceipt.safety.token_included, false);
  assert.equal(publishReceipt.dry_run, true);
  assert.equal(publishReceipt.posted, false);
  assert.equal(publishReceipt.request.safety.dry_run_only, true);
  assert.equal(commentReceipt.safety.token_included, false);
  assert.equal(commentReceipt.dry_run, true);
  assert.equal(commentReceipt.posted, false);
  assert.equal(requiredCheckPlan.safety.dry_run_only, true);
  assert.equal(requiredCheckPlan.check_name, "Ashr++ Release Gate");
  assert.match(commentPlan.request.body.body, /Decision: \*\*Block release\*\*/);
  assert.match(workflow, /actions\/checkout@v4/);
  assert.match(workflow, /a3_github_publish_cli\.mjs/);
  assert.match(workflow, /--output-receipt artifacts\/ashr-github-check-receipt\.json/);
  assert.match(workflow, /--output-receipt artifacts\/ashr-pr-comment-receipt\.json/);
  assert.doesNotMatch(JSON.stringify(checkRequest), /C:\/Users|Authorization|Bearer /);
  assert.doesNotMatch(JSON.stringify(commentPlan), /C:\/Users|Authorization|Bearer /);
  assert.doesNotMatch(JSON.stringify(publishReceipt), /C:\/Users|Authorization|Bearer|gh[pousr]_/);
  assert.doesNotMatch(JSON.stringify(commentReceipt), /C:\/Users|Authorization|Bearer|gh[pousr]_/);
  assert.doesNotMatch(JSON.stringify(requiredCheckPlan), /C:\/Users|Authorization|Bearer|gh[pousr]_/);
  assert.doesNotMatch(workflow, /gh[pousr]_[A-Za-z0-9_]+|Bearer /);
});

test("A3 GitHub integration publisher defaults to dry run without sending secrets", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  let called = false;
  const receipt = await publishGitHubCheckRun(payload, {
    repo: "acme/refund-agent",
    headSha: "abc123",
    detailsUrl: "https://example.invalid/a3-gate",
    fetchImpl: async () => {
      called = true;
      throw new Error("fetch should not be called in dry run");
    }
  });

  assert.equal(called, false);
  assert.equal(receipt.schema_version, "a3.github_check_publish_receipt.v1");
  assert.equal(receipt.status, "planned");
  assert.equal(receipt.dry_run, true);
  assert.equal(receipt.posted, false);
  assert.equal(receipt.request.body.conclusion, "failure");
  assert.equal(receipt.request.safety.dry_run_only, true);
  assert.equal(receipt.safety.token_included, false);
  assert.doesNotMatch(JSON.stringify(receipt), /Authorization|Bearer|ghp_|gho_/);
});

test("A3 GitHub integration publisher can post with runtime token and sanitized receipt", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  let capturedRequest = null;
  const receipt = await publishGitHubCheckRun(payload, {
    repo: "acme/refund-agent",
    headSha: "abc123",
    detailsUrl: "https://example.invalid/a3-gate",
    dryRun: false,
    token: "rt_secret",
    fetchImpl: async (url, init) => {
      capturedRequest = { url, init };
      return new Response(JSON.stringify({
        id: 9001,
        name: "Ashr++ Release Gate",
        status: "completed",
        conclusion: "failure",
        html_url: "https://github.example/checks/9001",
        details_url: "https://example.invalid/a3-gate",
        head_sha: "abc123",
        started_at: "2026-07-08T00:00:00Z",
        completed_at: "2026-07-08T00:00:01Z"
      }), {
        status: 201,
        headers: { "x-github-request-id": "abc:def:ghi" }
      });
    }
  });

  assert.equal(capturedRequest.url, "https://api.github.com/repos/acme/refund-agent/check-runs");
  assert.equal(capturedRequest.init.method, "POST");
  assert.equal(capturedRequest.init.headers.authorization, "Bearer rt_secret");
  assert.equal(receipt.status, "posted");
  assert.equal(receipt.posted, true);
  assert.equal(receipt.http_status, 201);
  assert.equal(receipt.github_request_id, "abc:def:ghi");
  assert.equal(receipt.check_run.id, 9001);
  assert.equal(receipt.check_run.conclusion, "failure");
  assert.equal(receipt.request.safety.dry_run_only, true);
  assert.equal(receipt.safety.token_included, false);
  assert.doesNotMatch(JSON.stringify(receipt), /rt_secret|Authorization|Bearer/);
});

test("A3 GitHub integration publisher sanitizes GitHub API errors", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const receipt = await publishGitHubCheckRun(payload, {
    repo: "acme/refund-agent",
    headSha: "abc123",
    dryRun: false,
    token: "rt_secret",
    fetchImpl: async () => new Response(JSON.stringify({
      message: "Bad credentials for Bearer rt_secret owned by reviewer@example.com"
    }), { status: 401 })
  });

  assert.equal(receipt.status, "failed");
  assert.equal(receipt.posted, false);
  assert.equal(receipt.http_status, 401);
  assert.match(receipt.redacted_summary, /\[REDACTED/);
  assert.doesNotMatch(JSON.stringify(receipt), /rt_secret|reviewer@example.com|Bearer rt_secret/);
});

test("A3 GitHub integration PR comment publisher defaults to dry run without fetch", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  let called = false;
  const receipt = await publishPrCommentUpsert(payload, {
    repo: "acme/refund-agent",
    pullNumber: 17,
    fetchImpl: async () => {
      called = true;
      throw new Error("fetch should not be called in PR comment dry run");
    }
  });

  assert.equal(called, false);
  assert.equal(receipt.schema_version, "a3.github_pr_comment_publish_receipt.v1");
  assert.equal(receipt.status, "planned");
  assert.equal(receipt.dry_run, true);
  assert.equal(receipt.posted, false);
  assert.equal(receipt.plan.safety.dry_run_only, true);
  assert.match(receipt.plan.request.body.body, /Decision: \*\*Block release\*\*/);
  assert.doesNotMatch(JSON.stringify(receipt), /Authorization|Bearer|gh[pousr]_/);
});

test("A3 GitHub integration PR comment publisher creates comment with sanitized receipt", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const calls = [];
  const receipt = await publishPrCommentUpsert(payload, {
    repo: "acme/refund-agent",
    pullNumber: 17,
    dryRun: false,
    token: "rt_secret",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (init.method === "GET") {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "x-github-request-id": "lookup:create" }
        });
      }
      return new Response(JSON.stringify({
        id: 2001,
        html_url: "https://github.example/acme/refund-agent/pull/17#issuecomment-2001",
        issue_url: "https://api.github.example/repos/acme/refund-agent/issues/17",
        created_at: "2026-07-08T00:00:00Z",
        updated_at: "2026-07-08T00:00:00Z",
        author_association: "MEMBER",
        body: "must not be stored in receipt"
      }), {
        status: 201,
        headers: { "x-github-request-id": "comment:create" }
      });
    }
  });

  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, "https://api.github.com/repos/acme/refund-agent/issues/17/comments");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].init.headers.authorization, "Bearer rt_secret");
  assert.equal(receipt.status, "posted");
  assert.equal(receipt.mode, "create_new_comment");
  assert.equal(receipt.posted, true);
  assert.equal(receipt.lookup.inspected_comment_count, 0);
  assert.equal(receipt.comment.id, 2001);
  assert.equal(receipt.safety.token_included, false);
  assert.doesNotMatch(JSON.stringify(receipt), /rt_secret|Authorization|Bearer|must not be stored/);
});

test("A3 GitHub integration PR comment publisher updates existing marker comment", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const marker = "<!-- ashr-plus-plus:release-gate:run_a3_generated_from_a2_g3 -->";
  const calls = [];
  const receipt = await publishPrCommentUpsert(payload, {
    repo: "acme/refund-agent",
    pullNumber: 17,
    dryRun: false,
    token: "rt_secret",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (init.method === "GET") {
        return new Response(JSON.stringify([{ id: 3001, body: `${marker}\nold body` }]), { status: 200 });
      }
      return new Response(JSON.stringify({
        id: 3001,
        html_url: "https://github.example/acme/refund-agent/pull/17#issuecomment-3001",
        updated_at: "2026-07-08T00:00:01Z"
      }), { status: 200 });
    }
  });

  assert.equal(calls.length, 2);
  assert.equal(calls[1].url, "https://api.github.com/repos/acme/refund-agent/issues/comments/3001");
  assert.equal(calls[1].init.method, "PATCH");
  assert.equal(receipt.mode, "update_existing_comment");
  assert.equal(receipt.plan.existing_comment_id, 3001);
  assert.equal(receipt.lookup.matched_existing_comment, true);
  assert.equal(receipt.comment.id, 3001);
});

test("A3 GitHub integration PR comment publisher stops on lookup errors", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const calls = [];
  const receipt = await publishPrCommentUpsert(payload, {
    repo: "acme/refund-agent",
    pullNumber: 17,
    dryRun: false,
    token: "rt_secret",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({
        message: "Bad credentials for Bearer rt_secret owned by reviewer@example.com"
      }), { status: 401 });
    }
  });

  assert.equal(calls.length, 1);
  assert.equal(receipt.mode, "lookup_failed");
  assert.equal(receipt.status, "failed");
  assert.equal(receipt.posted, false);
  assert.equal(receipt.http_status, 401);
  assert.match(receipt.redacted_summary, /\[REDACTED/);
  assert.doesNotMatch(JSON.stringify(receipt), /rt_secret|reviewer@example.com|Bearer rt_secret/);
});

test("A3 GitHub publisher rejects live mode without a runtime token", async () => {
  const payload = await loadJson("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  let called = false;
  const previousGitHubToken = process.env.GITHUB_TOKEN;
  const previousGhToken = process.env.GH_TOKEN;
  delete process.env.GITHUB_TOKEN;
  delete process.env.GH_TOKEN;
  try {
    await assert.rejects(() => publishGitHubCheckRun(payload, {
      repo: "acme/refund-agent",
      headSha: "abc123",
      dryRun: false,
      fetchImpl: async () => {
        called = true;
        return new Response("{}", { status: 201 });
      }
    }), /GitHub token is required/);
  } finally {
    if (previousGitHubToken === undefined) delete process.env.GITHUB_TOKEN;
    else process.env.GITHUB_TOKEN = previousGitHubToken;
    if (previousGhToken === undefined) delete process.env.GH_TOKEN;
    else process.env.GH_TOKEN = previousGhToken;
  }
  assert.equal(called, false);
});

test("A3 GitHub publish CLI parses safe dry-run arguments", () => {
  const args = parseGitHubPublishArgs([
    "--gate", "artifacts/ashr-gate.json",
    "--repo", "acme/refund-agent",
    "--head-sha", "abc123",
    "--details-url", "https://example.invalid/a3-gate",
    "--output-receipt", "artifacts/ashr-github-check-receipt.json",
    "--json"
  ]);

  assert.equal(args.gate, "artifacts/ashr-gate.json");
  assert.equal(args.repo, "acme/refund-agent");
  assert.equal(args.headSha, "abc123");
  assert.equal(args.dryRun, true);
  assert.equal(args.tokenEnvName, "GITHUB_TOKEN");
  assert.equal(args.json, true);
});

test("A3 GitHub publish CLI parses explicit PR comment target", () => {
  const args = parseGitHubPublishArgs([
    "--gate", "artifacts/ashr-gate.json",
    "--repo", "acme/refund-agent",
    "--pull-number", "17",
    "--pr-comment",
    "--output-receipt", "artifacts/ashr-pr-comment-receipt.json",
    "--json"
  ]);

  assert.equal(args.prComment, true);
  assert.equal(args.pullNumber, 17);
  assert.equal(args.dryRun, true);
  assert.equal(args.outputReceipt, "artifacts/ashr-pr-comment-receipt.json");
});

test("A3 GitHub publish CLI writes dry-run receipt without posting", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "a3-github-publish-"));
  const outputReceipt = join(tempDir, "receipt.json");
  try {
    const exitCode = await runGitHubPublishCli([
      "--gate", fixturePath("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json"),
      "--repo", "acme/refund-agent",
      "--head-sha", "abc123",
      "--details-url", "https://example.invalid/a3-gate",
      "--output-receipt", outputReceipt
    ], {
      stdout: { write() {} },
      stderr: { write(value) { throw new Error(value); } }
    });
    const receipt = JSON.parse(await readFile(outputReceipt, "utf8"));

    assert.equal(exitCode, 0);
    assert.equal(receipt.schema_version, "a3.github_check_publish_receipt.v1");
    assert.equal(receipt.status, "planned");
    assert.equal(receipt.dry_run, true);
    assert.equal(receipt.posted, false);
    assert.equal(receipt.request.safety.dry_run_only, true);
    assert.doesNotMatch(JSON.stringify(receipt), /Authorization|Bearer|ghp_|gho_|C:\\Users/);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 GitHub publish CLI writes PR comment dry-run receipt without head sha", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "a3-github-comment-"));
  const outputReceipt = join(tempDir, "comment-receipt.json");
  try {
    const exitCode = await runGitHubPublishCli([
      "--gate", fixturePath("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json"),
      "--repo", "acme/refund-agent",
      "--pull-number", "17",
      "--pr-comment",
      "--output-receipt", outputReceipt
    ], {
      stdout: { write() {} },
      stderr: { write(value) { throw new Error(value); } }
    });
    const receipt = JSON.parse(await readFile(outputReceipt, "utf8"));

    assert.equal(exitCode, 0);
    assert.equal(receipt.schema_version, "a3.github_pr_comment_publish_receipt.v1");
    assert.equal(receipt.status, "planned");
    assert.equal(receipt.dry_run, true);
    assert.equal(receipt.posted, false);
    assert.match(receipt.plan.request.body.body, /Decision: \*\*Block release\*\*/);
    assert.doesNotMatch(JSON.stringify(receipt), /Authorization|Bearer|gh[pousr]_|C:\\Users/);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 GitHub publish CLI requires pull number for PR comment mode", async () => {
  let stderr = "";
  const exitCode = await runGitHubPublishCli([
    "--gate", fixturePath("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json"),
    "--repo", "acme/refund-agent",
    "--pr-comment"
  ], {
    stdout: { write() {} },
    stderr: { write(value) { stderr += value; } }
  });
  const error = JSON.parse(stderr);

  assert.equal(exitCode, 1);
  assert.match(error.message, /--pull-number is required/);
  assert.equal(error.safety.token_included, false);
});

test("A3 GitHub publish CLI returns sanitized error for live mode without token", async () => {
  const previousGitHubToken = process.env.GITHUB_TOKEN;
  const previousGhToken = process.env.GH_TOKEN;
  delete process.env.GITHUB_TOKEN;
  delete process.env.GH_TOKEN;
  let stderr = "";
  try {
    const exitCode = await runGitHubPublishCli([
      "--gate", fixturePath("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json"),
      "--repo", "acme/refund-agent",
      "--head-sha", "abc123",
      "--live"
    ], {
      stdout: { write() {} },
      stderr: { write(value) { stderr += value; } }
    });
    const error = JSON.parse(stderr);
    assert.equal(exitCode, 1);
    assert.equal(error.schema_version, "a3.github_publish_cli_error.v1");
    assert.match(error.message, /GitHub token is required/);
    assert.equal(error.safety.token_included, false);
    assert.doesNotMatch(stderr, /Authorization|Bearer|ghp_|gho_/);
  } finally {
    if (previousGitHubToken === undefined) delete process.env.GITHUB_TOKEN;
    else process.env.GITHUB_TOKEN = previousGitHubToken;
    if (previousGhToken === undefined) delete process.env.GH_TOKEN;
    else process.env.GH_TOKEN = previousGhToken;
  }
});

test("A3 GitHub integration builds branch protection required-check plan only", () => {
  const plan = buildBranchProtectionRequiredCheckPlan({
    repo: "acme/refund-agent",
    branch: "main",
    existingChecks: [{ context: "ci/test", app_id: 1 }],
    existingContexts: ["legacy/status"],
    appId: 12345
  });

  assert.equal(plan.schema_version, "a3.github_required_check_plan.v1");
  assert.equal(plan.mode, "plan_required_check");
  assert.equal(plan.check_name, "Ashr++ Release Gate");
  assert.equal(plan.request.method, "PATCH");
  assert.equal(plan.request.body.strict, true);
  assert.deepEqual(plan.request.body.contexts, ["legacy/status"]);
  assert.deepEqual(plan.request.body.checks, [
    { context: "ci/test", app_id: 1 },
    { context: "Ashr++ Release Gate", app_id: 12345 }
  ]);
  assert.equal(plan.safety.dry_run_only, true);
  assert.equal(plan.safety.maintainer_approval_required, true);
  assert.doesNotMatch(JSON.stringify(plan), /Authorization|Bearer|gh[pousr]_/);
});
