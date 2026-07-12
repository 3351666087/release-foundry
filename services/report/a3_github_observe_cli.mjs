#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildBranchProtectionRequiredCheckPlan,
  readGitHubCheckRun,
  readPrCommentReadback,
  readRequiredCheckProof
} from "./a3_github_integration.mjs";

export function parseGitHubObserveArgs(argv = []) {
  const options = {
    tokenEnvName: "GITHUB_TOKEN",
    branch: "main",
    checkConclusion: "success"
  };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    const next = () => argv[++index];
    if (item === "--repo") options.repo = next();
    else if (item === "--check-run-id") options.checkRunId = Number(next());
    else if (item === "--check-name") options.checkName = next();
    else if (item === "--check-conclusion") options.checkConclusion = next();
    else if (item === "--head-sha") options.headSha = next();
    else if (item === "--pull-number") options.pullNumber = Number(next());
    else if (item === "--comment-body-file") options.commentBodyFile = next();
    else if (item === "--comment-marker") options.commentMarker = next();
    else if (item === "--branch") options.branch = next();
    else if (item === "--required-check-name") options.requiredCheckName = next();
    else if (item === "--api-base-url") options.apiBaseUrl = next();
    else if (item === "--token-env") options.tokenEnvName = next();
    else if (item === "--output-check") options.outputCheck = next();
    else if (item === "--output-comment") options.outputComment = next();
    else if (item === "--output-required-check") options.outputRequiredCheck = next();
    else if (item === "--json") options.json = true;
    else if (item === "--help" || item === "-h") options.help = true;
    else throw new Error(`Unknown argument: ${item}`);
  }
  return options;
}

export async function observeGitHubDelivery(options = {}) {
  if (options.help) return usageReceipt();
  if (!options.repo) throw new Error("--repo is required.");
  const token = process.env[options.tokenEnvName || "GITHUB_TOKEN"];
  if (!token) throw new Error(`GitHub token is required through ${options.tokenEnvName || "GITHUB_TOKEN"}.`);
  const common = {
    repo: options.repo,
    apiBaseUrl: options.apiBaseUrl,
    token,
    tokenEnvName: options.tokenEnvName,
    dryRun: false,
    checkedAt: options.checkedAt || new Date().toISOString()
  };
  let checkReadback = {};
  if (options.checkRunId) {
    checkReadback = await readGitHubCheckRun({}, {
      ...common,
      checkRunId: options.checkRunId,
      checkName: options.checkName,
      conclusion: options.checkConclusion,
      headSha: options.headSha,
      skipOutputHash: true
    });
    checkReadback = attachCalibration(checkReadback, {
      authorityClass: checkReadback.observed?.app_slug === "github-actions"
        ? "github_actions_app"
        : "github_check_provider",
      expectedHeadSha: options.headSha
    });
  }

  let commentReadback = {};
  if (options.pullNumber && options.commentBodyFile && options.commentMarker) {
    const body = await readFile(resolve(options.commentBodyFile), "utf8");
    const plan = buildExpectedCommentPlan(options, body);
    commentReadback = await readPrCommentReadback({
      schema_version: "a3.github_pr_comment_publish_receipt.v1",
      posted: true,
      dry_run: false,
      plan
    }, {
      ...common,
      pullNumber: options.pullNumber,
      marker: options.commentMarker,
      headSha: options.headSha
    });
    commentReadback = attachCalibration(commentReadback, {
      authorityClass: "operator_oauth_calibration",
      expectedHeadSha: options.headSha
    });
  }

  const requiredPlan = buildBranchProtectionRequiredCheckPlan({
    repo: options.repo,
    branch: options.branch || "main",
    checkName: options.requiredCheckName || options.checkName || "Ashr++ Release Gate"
  });
  const requiredCheckProof = attachCalibration(await readRequiredCheckProof(requiredPlan, {
    ...common,
    branch: options.branch || "main",
    checkName: options.requiredCheckName || options.checkName || "Ashr++ Release Gate"
  }), {
    authorityClass: "repository_policy_readback",
    expectedHeadSha: options.headSha
  });

  await Promise.all([
    writeJsonOptional(options.outputCheck, checkReadback),
    writeJsonOptional(options.outputComment, commentReadback),
    writeJsonOptional(options.outputRequiredCheck, requiredCheckProof)
  ]);
  return {
    schema_version: "a3.github_delivery_observation.v1",
    observed_at: common.checkedAt,
    repo: options.repo,
    check_readback: checkReadback,
    pr_comment_readback: commentReadback,
    required_check_proof: requiredCheckProof,
    closure: {
      check_live_readback: checkReadback.readback_status === "readback_confirmed",
      pr_comment_live_readback: commentReadback.readback_status === "readback_confirmed",
      required_check_enforced: requiredCheckProof.enforced === true,
      custom_tenant_github_app_proven: false
    },
    safety: {
      token_included: false,
      token_printed: false,
      mutation_performed: false,
      raw_response_stored: false,
      secret_values_allowed: false
    }
  };
}

export async function runGitHubObserveCli(argv = process.argv.slice(2), io = {}) {
  try {
    const options = parseGitHubObserveArgs(argv);
    const result = await observeGitHubDelivery(options);
    if (options.json || options.help) {
      (io.stdout || process.stdout).write(`${JSON.stringify(result, null, 2)}\n`);
    }
    return 0;
  } catch (error) {
    const payload = {
      schema_version: "a3.github_observe_cli_error.v1",
      error: "github_observe_cli_error",
      message: sanitizeError(error.message),
      safety: { token_included: false, token_printed: false, mutation_performed: false }
    };
    (io.stderr || process.stderr).write(`${JSON.stringify(payload, null, 2)}\n`);
    return 1;
  }
}

function buildExpectedCommentPlan(options, body) {
  const [owner, repo] = String(options.repo).split("/");
  return {
    schema_version: "a3.github_pr_comment_upsert.v1",
    mode: "observe_existing_comment",
    marker: options.commentMarker,
    repo: { owner, repo },
    pull_number: Number(options.pullNumber),
    find_existing: {
      method: "GET",
      url: `${options.apiBaseUrl || "https://api.github.com"}/repos/${owner}/${repo}/issues/${Number(options.pullNumber)}/comments`,
      match: "body contains marker"
    },
    request: {
      method: "POST",
      url: `${options.apiBaseUrl || "https://api.github.com"}/repos/${owner}/${repo}/issues/${Number(options.pullNumber)}/comments`,
      body: { body }
    },
    safety: {
      observation_only: true,
      token_included: false,
      secret_values_allowed: false
    }
  };
}

function attachCalibration(receipt, options) {
  return {
    ...receipt,
    calibration: {
      live_readback: receipt.readback_status === "readback_confirmed",
      authority_class: options.authorityClass,
      expected_head_sha_alias: options.expectedHeadSha || null,
      custom_tenant_github_app_proven: false,
      observed_via_read_only_api: true
    }
  };
}

async function writeJsonOptional(path, value) {
  if (!path || !value?.schema_version) return;
  const output = resolve(path);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function usageReceipt() {
  return {
    schema_version: "a3.github_observe_cli_usage.v1",
    command: "node services/report/a3_github_observe_cli.mjs --repo owner/repo --check-run-id 123 --check-name 'A3 golden path release artifact' --head-sha <sha> --pull-number 35 --comment-body-file artifacts/pr-comment.md --comment-marker '<!-- ashr-plus-plus:release-gate:run-id -->' --branch main --required-check-name 'A3 golden path release artifact' --output-check check.json --output-comment comment.json --output-required-check required.json --json",
    token_source: "GITHUB_TOKEN environment variable only",
    mutation_mode: "disabled; this CLI performs read-only GitHub API calls"
  };
}

function sanitizeError(value = "") {
  return String(value)
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [REDACTED]")
    .replace(/gh[pousr]_[A-Za-z0-9_]+/gi, "[REDACTED_GITHUB_TOKEN]")
    .replace(/github_pat_[A-Za-z0-9_]+/gi, "[REDACTED_GITHUB_TOKEN]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
    .slice(0, 500);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  runGitHubObserveCli().then((exitCode) => {
    process.exitCode = exitCode;
  });
}
