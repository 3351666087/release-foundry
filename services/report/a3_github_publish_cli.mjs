#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  publishGitHubCheckRun,
  publishPrCommentUpsert
} from "./a3_github_integration.mjs";

export function parseGitHubPublishArgs(argv = []) {
  const args = {
    dryRun: true,
    tokenEnvName: "GITHUB_TOKEN"
  };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    const next = () => argv[++index];
    if (item === "--gate") args.gate = next();
    else if (item === "--repo") args.repo = next();
    else if (item === "--head-sha") args.headSha = next();
    else if (item === "--details-url") args.detailsUrl = next();
    else if (item === "--check-run-id") args.checkRunId = Number(next());
    else if (item === "--pr-comment") args.prComment = true;
    else if (item === "--pull-number") args.pullNumber = Number(next());
    else if (item === "--api-base-url") args.apiBaseUrl = next();
    else if (item === "--token-env") args.tokenEnvName = next();
    else if (item === "--output-receipt") args.outputReceipt = next();
    else if (item === "--live") args.dryRun = false;
    else if (item === "--dry-run") args.dryRun = true;
    else if (item === "--json") args.json = true;
    else if (item === "--help" || item === "-h") args.help = true;
    else throw new Error(`Unknown argument: ${item}`);
  }
  return args;
}

export async function buildGitHubPublishCliReceipt(options = {}) {
  if (options.help) {
    return usageReceipt();
  }
  if (options.dryRun === false) {
    throw new Error("Direct live GitHub CLI publishing is disabled. Use the hosted A3 API with server-verified A1 identity, A2 release authority, and a tenant-bound GitHub installation.");
  }
  if (!options.gate) {
    throw new Error("--gate is required.");
  }
  if (!options.repo) {
    throw new Error("--repo is required.");
  }
  if (options.prComment && (!Number.isInteger(Number(options.pullNumber)) || Number(options.pullNumber) <= 0)) {
    throw new Error("--pull-number is required when --pr-comment is used.");
  }
  if (!options.prComment && !options.headSha) {
    throw new Error("--head-sha is required.");
  }
  const gatePayload = JSON.parse(await readFile(resolve(options.gate), "utf8"));
  if (options.prComment) {
    return publishPrCommentUpsert(gatePayload, {
      repo: options.repo,
      pullNumber: options.pullNumber,
      apiBaseUrl: options.apiBaseUrl,
      tokenEnvName: options.tokenEnvName,
      dryRun: options.dryRun
    });
  }
  return publishGitHubCheckRun(gatePayload, {
    repo: options.repo,
    headSha: options.headSha,
    detailsUrl: options.detailsUrl,
    checkRunId: options.checkRunId,
    apiBaseUrl: options.apiBaseUrl,
    tokenEnvName: options.tokenEnvName,
    dryRun: options.dryRun
  });
}

export async function runGitHubPublishCli(argv = process.argv.slice(2), io = {}) {
  try {
    const args = parseGitHubPublishArgs(argv);
    const receipt = await buildGitHubPublishCliReceipt(args);
    const body = `${JSON.stringify(receipt, null, 2)}\n`;
    if (args.outputReceipt) {
      const outputPath = resolve(args.outputReceipt);
      await mkdir(dirname(outputPath), { recursive: true });
      await writeFile(outputPath, body, "utf8");
    }
    if (args.json || !args.outputReceipt || args.help) {
      (io.stdout || process.stdout).write(body);
    }
    return receipt.status === "failed" ? 1 : 0;
  } catch (error) {
    const payload = {
      schema_version: "a3.github_publish_cli_error.v1",
      error: "github_publish_cli_error",
      message: sanitizeCliError(error.message),
      safety: {
        token_included: false,
        secret_values_allowed: false
      }
    };
    (io.stderr || process.stderr).write(`${JSON.stringify(payload, null, 2)}\n`);
    return 1;
  }
}

function usageReceipt() {
  return {
    schema_version: "a3.github_publish_cli_usage.v1",
    command: "node services/report/a3_github_publish_cli.mjs --gate artifacts/releasefoundry-gate.json --repo owner/repo --head-sha <sha> --output-receipt artifacts/releasefoundry-github-check-receipt.json",
    pr_comment_command: "node services/report/a3_github_publish_cli.mjs --gate artifacts/releasefoundry-gate.json --repo owner/repo --pull-number <number> --pr-comment --output-receipt artifacts/releasefoundry-pr-comment-receipt.json",
    default_mode: "dry-run",
    live_mode: "Disabled in this CLI. Live writes must use the hosted trusted-worker path.",
    safety: {
      prints_token: false,
      commits_token: false,
      default_posts_to_github: false,
      direct_live_publish_allowed: false
    }
  };
}

function sanitizeCliError(message = "") {
  return String(message)
    .replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [REDACTED]")
    .replace(/gh[pousr]_[A-Za-z0-9_]+/g, "[REDACTED_GITHUB_TOKEN]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
    .slice(0, 500);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  runGitHubPublishCli().then((exitCode) => {
    process.exitCode = exitCode;
  });
}
