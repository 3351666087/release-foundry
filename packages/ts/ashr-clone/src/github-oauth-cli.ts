#!/usr/bin/env node
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  GitHubOAuthError,
  GitHubOAuthHttpClient,
  exportGitHubOAuthOpenApiSpec,
  type GitHubOAuthFetch,
} from "./github-oauth.js";

export interface GitHubOAuthCliOptions {
  fetch?: GitHubOAuthFetch;
  stdout?: (text: string) => void;
}

export async function runGitHubOAuthCli(argv: readonly string[], options: GitHubOAuthCliOptions = {}): Promise<Record<string, unknown>> {
  const parsed = parseArgs(argv);
  const command = parsed.positionals[0] ?? "help";
  if (command === "help") return { usage: usage() };
  if (command === "openapi") return exportGitHubOAuthOpenApiSpec();
  const baseUrl = requiredOption(parsed.options, "base-url");
  const client = new GitHubOAuthHttpClient({ baseUrl, fetch: options.fetch });
  switch (command) {
    case "start":
      return client.start(requiredOption(parsed.options, "project-id"), {
        returnTo: optionalOption(parsed.options, "return-to"),
        login: optionalOption(parsed.options, "login"),
        allowSignup: booleanOption(parsed.options, "allow-signup"),
      }) as Promise<unknown> as Promise<Record<string, unknown>>;
    case "callback":
      return client.callback({
        state: optionalOption(parsed.options, "state"),
        code: optionalOption(parsed.options, "code"),
        error: optionalOption(parsed.options, "error"),
        errorDescription: optionalOption(parsed.options, "error-description"),
      }) as Promise<unknown> as Promise<Record<string, unknown>>;
    case "disconnect":
      return client.disconnect(
        requiredOption(parsed.options, "project-id"),
        requiredOption(parsed.options, "session-id"),
      ) as Promise<unknown> as Promise<Record<string, unknown>>;
    case "session":
      return client.session(requiredOption(parsed.options, "session-id")) as Promise<unknown> as Promise<Record<string, unknown>>;
    case "account":
      return client.account(requiredOption(parsed.options, "session-id")) as Promise<unknown> as Promise<Record<string, unknown>>;
    default:
      throw new GitHubOAuthError("unknown_command", `Unknown GitHub OAuth command: ${command}`, 400);
  }
}

interface ParsedArgs {
  positionals: string[];
  options: Record<string, string | true>;
}

function parseArgs(argv: readonly string[]): ParsedArgs {
  const positionals: string[] = [];
  const options: Record<string, string | true> = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith("--")) {
      positionals.push(item);
      continue;
    }
    const name = item.slice(2);
    const next = argv[index + 1];
    if (next !== undefined && !next.startsWith("--")) {
      options[name] = next;
      index += 1;
    } else {
      options[name] = true;
    }
  }
  return { positionals, options };
}

function requiredOption(options: Record<string, string | true>, name: string): string {
  const value = options[name];
  if (typeof value !== "string" || value === "") throw new GitHubOAuthError(`missing_${name}`, `--${name} is required`, 400);
  return value;
}

function optionalOption(options: Record<string, string | true>, name: string): string | undefined {
  const value = options[name];
  return typeof value === "string" && value !== "" ? value : undefined;
}

function booleanOption(options: Record<string, string | true>, name: string): boolean | undefined {
  const value = options[name];
  if (value === undefined) return undefined;
  if (value === true || value === "true") return true;
  if (value === "false") return false;
  throw new GitHubOAuthError("invalid_boolean", `--${name} must be true or false`, 400);
}

function usage(): string {
  return [
    "usage: node dist/github-oauth-cli.js <command> [options]",
    "commands: openapi, start, callback, disconnect, session, account",
    "start and disconnect require --project-id; callback uses only /oauth/github/callback and does not accept --flow-id.",
    "HTTP commands require --base-url and never read OAuth secrets from CLI arguments or environment variables.",
  ].join("\n");
}

if (process.argv[1] !== undefined && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  runGitHubOAuthCli(process.argv.slice(2))
    .then((result) => process.stdout.write(`${JSON.stringify(result, null, 2)}\n`))
    .catch((error) => {
      const safe = error instanceof GitHubOAuthError ? error : new GitHubOAuthError("github_oauth_cli_failed", "GitHub OAuth CLI request failed", 1);
      process.stderr.write(`${JSON.stringify(safe.toJSON())}\n`);
      process.exitCode = 1;
    });
}
