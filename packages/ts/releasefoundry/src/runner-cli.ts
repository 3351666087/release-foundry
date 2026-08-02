#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { buildA1CandidateBinding, type A1CandidateBinding } from "./candidate-binding.js";
import { buildRunFixture, loadAgentTarget, runAgentBatch } from "./runner.js";

type CliOptions = Record<string, string | boolean | string[]>;

async function main(): Promise<number> {
  const options = parseArgs(process.argv.slice(2));
  if (options.help || options.h) {
    printHelp();
    return 0;
  }
  const inputPath = stringOption(options, "input", true);
  const outputPath = stringOption(options, "output", true);
  const agentTarget = stringOption(options, "agent", true);
  const payload = JSON.parse(await readFile(resolve(inputPath), "utf8")) as unknown;
  const cases = Array.isArray(payload) ? payload : isRecord(payload) && Array.isArray(payload.cases) ? payload.cases : undefined;
  if (!cases) {
    throw new Error("input JSON must be a case list or object with cases");
  }
  const candidateBinding = await candidateBindingOption(options, cases);
  const agent = await loadAgentTarget(agentTarget);
  const result = await runAgentBatch(agent, cases, {
    datasetId: stringOption(options, "dataset-id", false) ?? "local-dataset",
    runnerId: stringOption(options, "runner-id", false) ?? "a1-ts-local-runner",
    runId: stringOption(options, "run-id", false) ?? undefined,
    maxWorkers: numberOption(options, "max-workers", 4),
    timeoutSeconds: numberOption(options, "timeout", 30),
    inputStyle: inputStyleOption(options),
    metadata: {
      cli: "releasefoundry-runner",
      local_only: true,
      releasefoundry_api_used: false,
      ...(candidateBinding ? { candidate_binding: candidateBinding } : {}),
    },
  });
  await writeJson(outputPath, result);
  const fixtureOutput = stringOption(options, "fixture-output", false);
  if (fixtureOutput) {
    await writeJson(fixtureOutput, buildRunFixture(result, {
      metadata: {
        cli: "releasefoundry-runner",
        ...(candidateBinding ? { candidate_binding: candidateBinding } : {}),
      },
    }));
  }
  const summary = {
    status: result.status,
    run_id: result.run_id,
    total_cases: result.total_cases,
    passed: result.passed,
    failed: result.failed,
    errored: result.errored,
    timed_out: result.timed_out,
    trace_completeness: result.trace_completeness,
    max_workers: result.max_workers,
    output: resolve(outputPath),
    fixture: fixtureOutput ? resolve(fixtureOutput) : undefined,
    candidate_binding: candidateBinding
      ? {
          schema_version: candidateBinding.schema_version,
          candidate_id: candidateBinding.candidate_id,
          git_sha: candidateBinding.git_sha,
          evidence_release_version: candidateBinding.evidence_release_version,
          case_set_sha256: candidateBinding.case_set_sha256,
        }
      : undefined,
  };
  process.stdout.write(`${JSON.stringify(summary)}\n`);
  if (options["fail-on-case-failure"] && ((result.failed as number) || (result.errored as number) || (result.timed_out as number))) {
    return 1;
  }
  return 0;
}

async function candidateBindingOption(options: CliOptions, cases: unknown[]): Promise<A1CandidateBinding | undefined> {
  const requiredNames = ["candidate-id", "candidate-source-commit", "evidence-release-version"];
  const suppliedNames = requiredNames.filter((name) => options[name] !== undefined);
  const repoRootSupplied = options["repo-root"] !== undefined;
  if (suppliedNames.length === 0) {
    if (repoRootSupplied) {
      throw new Error("--repo-root requires all candidate-binding options");
    }
    return undefined;
  }
  if (suppliedNames.length !== requiredNames.length) {
    throw new Error("--candidate-id, --candidate-source-commit, and --evidence-release-version must be supplied together");
  }
  return buildA1CandidateBinding({
    candidateId: stringOption(options, "candidate-id", true),
    candidateSourceCommit: stringOption(options, "candidate-source-commit", true),
    evidenceReleaseVersion: stringOption(options, "evidence-release-version", true),
    caseSet: cases,
    repoRoot: repoRootSupplied ? stringOption(options, "repo-root", true) : undefined,
  });
}

function parseArgs(args: string[]): CliOptions {
  const options: CliOptions = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) {
      throw new Error(`unexpected argument: ${arg}`);
    }
    const name = arg.slice(2);
    const next = args[index + 1];
    if (next === undefined || next.startsWith("--")) {
      options[name] = true;
      continue;
    }
    if (options[name] === undefined) {
      options[name] = next;
    } else if (Array.isArray(options[name])) {
      (options[name] as string[]).push(next);
    } else {
      options[name] = [String(options[name]), next];
    }
    index += 1;
  }
  return options;
}

function stringOption(options: CliOptions, name: string, required: true): string;
function stringOption(options: CliOptions, name: string, required: false): string | undefined;
function stringOption(options: CliOptions, name: string, required: boolean): string | undefined {
  const value = options[name];
  if (typeof value === "string") {
    return value;
  }
  if (required) {
    throw new Error(`missing required --${name}`);
  }
  return undefined;
}

function numberOption(options: CliOptions, name: string, fallback: number): number {
  const value = options[name];
  if (value === undefined || value === true) {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`--${name} must be numeric`);
  }
  return parsed;
}

function inputStyleOption(options: CliOptions): "text" | "request" | "keyword" {
  const value = stringOption(options, "input-style", false) ?? "text";
  if (value !== "text" && value !== "request" && value !== "keyword") {
    throw new Error("--input-style must be text, request, or keyword");
  }
  return value;
}

async function writeJson(path: string, value: unknown): Promise<void> {
  const output = resolve(path);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function printHelp(): void {
  process.stdout.write(`releasefoundry-runner

Required:
  --input <cases.json>
  --output <run-result.json>
  --agent <module:export>

Options:
  --dataset-id <id>
  --runner-id <id>
  --run-id <id>
  --max-workers <n>      normalized to at least 4
  --timeout <seconds>
  --input-style <text|request|keyword>
  --fixture-output <run-fixture.json>
  --fail-on-case-failure

Candidate evidence (identity options are all-or-none and fail closed):
  --candidate-id <agent@semver>
  --candidate-source-commit <40-char-git-sha>
  --evidence-release-version <semver>
  --repo-root <clean-git-worktree>   optional; defaults to current directory
`);
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    process.stderr.write(`releasefoundry-runner error: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
