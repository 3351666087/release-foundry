import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import { A3GoldenPathDemoAgent } from "../../services/report/a3_golden_path_demo_agent.mjs";
import { loadA3SourceSnapshot } from "../../services/report/a3_store.mjs";

test("A3 Golden Agent keeps direct answers tool-free", async () => {
  const result = await new A3GoldenPathDemoAgent().respond(
    "Rewrite this sentence to sound warmer, in one sentence: 'Your request was denied because it is incomplete.'"
  );

  assert.equal(result.text, "We would be happy to review your request once the missing information is complete.");
  assert.deepEqual(result.tool_calls, []);
  assert.equal(result.metadata.network_used, false);
  assert.equal(result.metadata.read_only, true);
});

test("A3 Golden Agent grounds the official price in a web.search tool result", async () => {
  const result = await new A3GoldenPathDemoAgent().respond(
    "What is the current listed price of the Acme MiniDock on its official product page?"
  );

  assert.match(result.text, /\$79/);
  assert.match(result.text, /https:\/\/acme\.example\/products\/minidock/);
  assert.deepEqual(result.tool_calls.map((call) => call.name), ["web.search"]);
  assert.equal(result.tool_calls[0].output.source_kind, "official_product_page");
  assert.equal(result.tool_calls[0].output.price, "$79");
});

test("A3 Golden Agent executes and grounds the ordered media pipeline", async () => {
  const result = await new A3GoldenPathDemoAgent().respond(
    "Use the dashboard media asset and classifier output to identify the red critical service."
  );

  assert.deepEqual(result.tool_calls.map((call) => call.name), [
    "media.fetch",
    "image.view",
    "media.classify",
  ]);
  assert.equal(result.tool_calls[0].arguments.asset_id, "dashboard-alert-001");
  assert.equal(result.tool_calls[1].arguments.path, "fixtures/a2/images/dashboard-alert.png");
  assert.ok(result.tool_calls[1].output.width > 0);
  assert.ok(result.tool_calls[1].output.height > 0);
  assert.match(result.tool_calls[1].output.content_hash_sha256, /^sha256:[a-f0-9]{64}$/);
  assert.deepEqual(result.tool_calls[2].output.grounded_facts, ["Billing", "critical", "red"]);
  assert.match(result.text, /Billing/);
  assert.doesNotMatch(result.text.toLowerCase(), /payments/);
});

test("A3 Golden Agent fails closed when required evidence is unavailable", async () => {
  const emptyRoot = await mkdtemp(join(tmpdir(), "a3-golden-agent-"));
  const agent = new A3GoldenPathDemoAgent({ rootDir: emptyRoot });

  await assert.rejects(
    agent.respond("What is the current listed price of the Acme MiniDock on its official product page?"),
    /ENOENT/
  );
});

test("A3 Golden Agent rejects prompts outside the versioned case set", async () => {
  await assert.rejects(
    new A3GoldenPathDemoAgent().respond("Perform an unrelated destructive action."),
    /refuses prompts outside/
  );
});

test("the rc.2 A1 run and unchanged A2 Judge preserve the passing tool evidence", async () => {
  const run = await loadJson("fixtures/a3/golden-path/rc2/a3_new_run_result.redacted.json");
  const response = await loadJson("fixtures/a3/golden-path/rc2/a2_new_run_judge_response.redacted.json");
  const grades = response.result;

  assert.equal(run.schema_version, "ashr.clone.run_result.v1");
  assert.equal(run.run_id, "a3-golden-20260712-002");
  assert.equal(run.total_cases, 3);
  assert.equal(run.passed, 3);
  assert.equal(run.failed, 0);
  assert.equal(run.errored, 0);
  assert.equal(run.trace_completeness, 1);
  assert.equal(run.aggregate_metrics.total_tool_calls, 4);
  assert.deepEqual(
    run.cases.find((item) => item.scenario_id === "A2-S004").agent_output.tool_calls.map((call) => call.name),
    ["web.search"]
  );
  assert.deepEqual(
    run.cases.find((item) => item.scenario_id === "A2-S031").agent_output.tool_calls.map((call) => call.name),
    ["media.fetch", "image.view", "media.classify"]
  );

  assert.equal(response.ok, true);
  assert.equal(grades.schema_version, "a2.judge_service.run_response.v1");
  assert.equal(grades.total_cases, 3);
  assert.equal(grades.passed, 3);
  assert.equal(grades.failed, 0);
  assert.equal(grades.run_summary.pass_rate, 100);
  assert.deepEqual(grades.run_summary.primary_failure_class_counts, { none: 3 });
  assert.ok(grades.case_results.every((item) => item.passed === true));
  assert.ok(grades.case_results.every((item) => item.primary_failure_class === "none"));
  assert.ok(grades.case_results.every((item) => item.score === 100));
});

async function loadJson(path) {
  return JSON.parse(await readFile(resolve(path), "utf8"));
}

test("the rc.2 dashboard source exposes passing A1/A2 evidence without inventing release authority", async () => {
  const snapshot = await loadA3SourceSnapshot("a3-golden-path-rc2");

  assert.equal(snapshot.source, "a3-golden-path-rc2");
  assert.equal(snapshot.summary.totalCases, 3);
  assert.equal(snapshot.summary.passed, 3);
  assert.equal(snapshot.summary.failed, 0);
  assert.equal(snapshot.summary.passRate, 100);
  assert.equal(snapshot.releaseArtifactManifest.release.version, "0.2.0-rc.2");
  assert.equal(snapshot.releaseArtifactManifest.release.git_sha_alias, "c8420813ed6cb94535bd108b30bd97663b906bdb");
  assert.equal(snapshot.releaseArtifactManifest.release.ci_tested_sha_alias, "746ecbe959a9c8781e8e1fc7d2520a50fd92785b");
  assert.equal(snapshot.deliveryGoldenPath.status, "blocked_by_a2");
  assert.equal(snapshot.deliveryGoldenPath.production_ready, false);
  assert.equal(snapshot.deliveryGoldenPath.progress.passed, 5);
});

test("the rc.2 Gate keeps a passing local quality gate blocked by A2 authority", async () => {
  const gate = await loadJson("fixtures/a3/golden-path/rc2/gate-report.json");
  const comment = await readFile(resolve("fixtures/a3/golden-path/rc2/pr-comment.md"), "utf8");

  assert.equal(gate.local_quality_gate.decision, "approve_release");
  assert.equal(gate.release_gate.decision, "block_release");
  assert.equal(gate.release_gate.pr_gate.blocks_merge, true);
  assert.equal(gate.release_workflow.reviewer_workflow.state, "blocked_by_a2");
  assert.equal(gate.release_workflow.reviewer_workflow.sign_off_risk.can_sign_off, false);
  assert.equal(gate.github_check_run.conclusion, "failure");
  assert.match(comment, /Decision: \*\*Block release\*\*/);
  assert.match(comment, /Authority: \*\*A2 Decision Ledger\*\*/);
  assert.match(comment, /Candidate SHA: `c8420813ed6cb94535bd108b30bd97663b906bdb`/);
  assert.doesNotMatch(comment, /Merge may proceed/);
});
