import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  findPeerBranchCalibrationLeaks,
  summarizeA3PeerBranchCalibration,
  validateA3PeerBranchCalibration
} from "../../services/report/a3_peer_branch_calibration.mjs";
import {
  buildJsonReport,
  buildMarkdownReport
} from "../../services/report/report_builder.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 peer branch calibration summarizes A1/A2 PR deltas without secrets", async () => {
  const fixture = await loadJson("../../fixtures/a3/p3/a3_peer_branch_calibration.redacted.json");
  const summary = summarizeA3PeerBranchCalibration(fixture);
  const validation = validateA3PeerBranchCalibration(fixture);

  assert.equal(summary.schema_version, "a3.peer_branch_calibration.v1");
  assert.equal(summary.available, true);
  assert.equal(summary.peer_delta_count >= 12, true);
  assert.equal(summary.growth_point_count >= 20, true);
  assert.equal(summary.blocking_delta_count >= 4, true);
  assert.equal(summary.branch_counts["origin/codex/a1-local-sdk-runner"] >= 1, true);
  assert.equal(summary.branch_counts["origin/dev/g3-a2-calibration"] >= 1, true);
  assert.equal(summary.surface_counts.billing_usage >= 1, true);
  assert.equal(summary.safety.contains_secret_values, false);
  assert.match(summary.commercial_value, /enterprise release gates/);
  assert.equal(validation.valid, true, validation.errors.join("\n"));
  assert.deepEqual(findPeerBranchCalibrationLeaks(fixture), []);
});

test("A3 reports export peer branch calibration for reviewer packets", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const fixture = await loadJson("../../fixtures/a3/p3/a3_peer_branch_calibration.redacted.json");

  const jsonArgs = Array(20).fill({});
  jsonArgs[0] = runs;
  jsonArgs[1] = grades;
  jsonArgs[19] = fixture;
  const json = buildJsonReport(...jsonArgs);
  assert.equal(json.peer_branch_calibration.schema_version, "a3.peer_branch_calibration.v1");
  assert.equal(json.peer_branch_calibration.peer_delta_count >= 12, true);
  assert.equal(json.peer_branch_calibration.safety.contains_secret_values, false);

  const markdownArgs = Array(19).fill({});
  markdownArgs[0] = runs;
  markdownArgs[1] = grades;
  markdownArgs[18] = fixture;
  const markdown = buildMarkdownReport(...markdownArgs);
  assert.match(markdown, /Peer Branch Calibration/);
  assert.match(markdown, /A1\/A2 peer delta/);
  assert.doesNotMatch(markdown, /Bearer|github_pat_|ghp_|sk-|C:\\Users/);
});

test("A3 peer branch calibration summary is idempotent for API dashboard payloads", async () => {
  const fixture = await loadJson("../../fixtures/a3/p3/a3_peer_branch_calibration.redacted.json");
  const firstSummary = summarizeA3PeerBranchCalibration(fixture);
  const secondSummary = summarizeA3PeerBranchCalibration(firstSummary);

  assert.equal(secondSummary.available, true);
  assert.equal(secondSummary.peer_delta_count, firstSummary.peer_delta_count);
  assert.equal(secondSummary.growth_point_count, firstSummary.growth_point_count);
  assert.equal(secondSummary.blocking_delta_count, firstSummary.blocking_delta_count);
  assert.equal(secondSummary.peer_branch_count, firstSummary.peer_branch_count);
  assert.equal(secondSummary.action_items.length, firstSummary.action_items.length);
  assert.equal(secondSummary.safety.contains_secret_values, false);
});
