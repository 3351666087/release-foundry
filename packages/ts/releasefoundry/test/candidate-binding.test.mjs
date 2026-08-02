import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  A1_CANDIDATE_BINDING_SCHEMA_VERSION,
  buildA1CandidateBinding,
} from "../dist/index.js";

const CANDIDATE_ID = "a3-golden-agent@0.2.0-rc.3";
const RELEASE_VERSION = "0.2.0-rc.3";

test("candidate binding records clean Git identity and canonical case-set hash", async () => {
  const repo = createGitRepo();
  try {
    const head = git(repo, "rev-parse", "HEAD");
    const tree = git(repo, "rev-parse", "HEAD^{tree}");
    const first = await buildA1CandidateBinding({
      candidateId: CANDIDATE_ID,
      candidateSourceCommit: head,
      evidenceReleaseVersion: RELEASE_VERSION,
      caseSet: [{ case_id: "case-1", expected: { b: 2, a: 1 } }],
      repoRoot: repo,
    });
    const reordered = await buildA1CandidateBinding({
      candidateId: CANDIDATE_ID,
      candidateSourceCommit: head,
      evidenceReleaseVersion: RELEASE_VERSION,
      caseSet: [{ expected: { a: 1, b: 2 }, case_id: "case-1" }],
      repoRoot: repo,
    });

    assert.equal(first.schema_version, A1_CANDIDATE_BINDING_SCHEMA_VERSION);
    assert.equal(first.candidate_id, CANDIDATE_ID);
    assert.equal(first.git_sha, head);
    assert.equal(first.candidate_source_commit, head);
    assert.equal(first.source_tree_clean, true);
    assert.equal(first.source_tree_sha, tree);
    assert.match(first.case_set_sha256, /^sha256:[0-9a-f]{64}$/);
    assert.equal(first.case_set_sha256, reordered.case_set_sha256);
  } finally {
    rmSync(repo, { recursive: true, force: true });
  }
});

test("candidate binding fails closed on commit mismatch and dirty source", async () => {
  const repo = createGitRepo();
  try {
    const head = git(repo, "rev-parse", "HEAD");
    await assert.rejects(
      buildA1CandidateBinding({
        candidateId: CANDIDATE_ID,
        candidateSourceCommit: "b".repeat(40),
        evidenceReleaseVersion: RELEASE_VERSION,
        caseSet: [{ case_id: "case-1" }],
        repoRoot: repo,
      }),
      /does not match repository HEAD/,
    );

    writeFileSync(join(repo, "tracked.txt"), "dirty\n", "utf8");
    await assert.rejects(
      buildA1CandidateBinding({
        candidateId: CANDIDATE_ID,
        candidateSourceCommit: head,
        evidenceReleaseVersion: RELEASE_VERSION,
        caseSet: [{ case_id: "case-1" }],
        repoRoot: repo,
      }),
      /source tree must be clean/,
    );
  } finally {
    rmSync(repo, { recursive: true, force: true });
  }
});

test("candidate binding validates candidate format, SemVer agreement, and case presence", async () => {
  const repo = createGitRepo();
  try {
    const head = git(repo, "rev-parse", "HEAD");
    await assert.rejects(
      buildA1CandidateBinding({
        candidateId: "not-a-versioned-candidate",
        candidateSourceCommit: head,
        evidenceReleaseVersion: RELEASE_VERSION,
        caseSet: [{ case_id: "case-1" }],
        repoRoot: repo,
      }),
      /<agent>@<semver>/,
    );
    await assert.rejects(
      buildA1CandidateBinding({
        candidateId: CANDIDATE_ID,
        candidateSourceCommit: head,
        evidenceReleaseVersion: "0.2.0-rc.4",
        caseSet: [{ case_id: "case-1" }],
        repoRoot: repo,
      }),
      /must match evidenceReleaseVersion/,
    );
    await assert.rejects(
      buildA1CandidateBinding({
        candidateId: CANDIDATE_ID,
        candidateSourceCommit: head,
        evidenceReleaseVersion: RELEASE_VERSION,
        caseSet: [],
        repoRoot: repo,
      }),
      /non-empty JSON array/,
    );
  } finally {
    rmSync(repo, { recursive: true, force: true });
  }
});

test("runner CLI embeds candidate binding and rejects a partial binding option set", () => {
  const repo = createGitRepo();
  try {
    const agentPath = join(repo, "agent.mjs");
    const inputPath = join(repo, "cases.json");
    const outputPath = join(repo, "run.json");
    writeFileSync(agentPath, "export default { respond(message) { return `Echo: ${message}`; } };\n", "utf8");
    writeFileSync(inputPath, JSON.stringify({ cases: [{ id: "case-1", prompt: "hello", expected: { text: "Echo: hello" } }] }), "utf8");
    git(repo, "add", "agent.mjs", "cases.json");
    git(repo, "commit", "-m", "add candidate inputs");
    const head = git(repo, "rev-parse", "HEAD");

    const baseArgs = [
      "dist/runner-cli.js",
      "--input", inputPath,
      "--output", outputPath,
      "--agent", `${agentPath}:default`,
      "--run-id", "run_candidate_cli",
    ];
    const partial = spawnSync(process.execPath, [...baseArgs, "--candidate-id", CANDIDATE_ID], {
      cwd: new URL("../", import.meta.url),
      encoding: "utf8",
    });
    assert.equal(partial.status, 1);
    assert.match(partial.stderr, /must be supplied together/);

    const child = spawnSync(process.execPath, [
      ...baseArgs,
      "--candidate-id", CANDIDATE_ID,
      "--candidate-source-commit", head,
      "--evidence-release-version", RELEASE_VERSION,
      "--repo-root", repo,
    ], {
      cwd: new URL("../", import.meta.url),
      encoding: "utf8",
    });
    assert.equal(child.status, 0, child.stderr);

    const summary = JSON.parse(child.stdout);
    const result = JSON.parse(readFileSync(outputPath, "utf8"));
    assert.equal(summary.candidate_binding.candidate_id, CANDIDATE_ID);
    assert.equal(result.metadata.candidate_binding.git_sha, head);
    assert.equal(result.metadata.candidate_binding.source_tree_clean, true);
    assert.match(result.metadata.candidate_binding.case_set_sha256, /^sha256:[0-9a-f]{64}$/);
  } finally {
    rmSync(repo, { recursive: true, force: true });
  }
});

function createGitRepo() {
  const repo = mkdtempSync(join(tmpdir(), "releasefoundry-candidate-binding-"));
  git(repo, "init", "--quiet");
  git(repo, "config", "user.email", "candidate-test@example.invalid");
  git(repo, "config", "user.name", "Candidate Test");
  writeFileSync(join(repo, "tracked.txt"), "clean\n", "utf8");
  git(repo, "add", "tracked.txt");
  git(repo, "commit", "--quiet", "-m", "initial");
  return repo;
}

function git(cwd, ...args) {
  return execFileSync("git", args, { cwd, encoding: "utf8", windowsHide: true }).trim();
}
