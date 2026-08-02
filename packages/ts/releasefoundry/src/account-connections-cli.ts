#!/usr/bin/env node
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  AccountConnectionError,
  AccountConnectionHttpClient,
  accountConnectionContractManifest,
  type AccountConnectionFetch,
} from "./account-connections.js";

export interface AccountConnectionCliOptions {
  fetch?: AccountConnectionFetch;
}

export async function runAccountConnectionCli(
  argv: readonly string[],
  options: AccountConnectionCliOptions = {},
): Promise<Record<string, unknown>> {
  const parsed = parseArgs(argv);
  rejectForbiddenOptions(parsed.options);
  const command = parsed.positionals[0] ?? "help";
  if (command === "help") return { usage: usage() };
  if (command === "contract") return accountConnectionContractManifest();
  const client = new AccountConnectionHttpClient({
    baseUrl: required(parsed.options, "base-url"),
    fetch: options.fetch,
  });
  const provider = required(parsed.options, "provider");
  switch (command) {
    case "start":
      return client.start({
        provider,
        projectId: required(parsed.options, "project-id"),
        tenantId: optional(parsed.options, "tenant-id"),
        accountId: optional(parsed.options, "account-id"),
        returnTo: optional(parsed.options, "return-to"),
        loginHint: optional(parsed.options, "login-hint"),
        allowSignup: optionalBoolean(parsed.options, "allow-signup"),
      }) as Promise<unknown> as Promise<Record<string, unknown>>;
    case "connection":
      return client.connection({
        provider,
        projectId: required(parsed.options, "project-id"),
        tenantId: required(parsed.options, "tenant-id"),
        accountId: required(parsed.options, "account-id"),
      }) as Promise<unknown> as Promise<Record<string, unknown>>;
    case "disconnect":
      return client.disconnect({
        provider,
        projectId: required(parsed.options, "project-id"),
        tenantId: optional(parsed.options, "tenant-id"),
        accountId: optional(parsed.options, "account-id"),
      }) as Promise<unknown> as Promise<Record<string, unknown>>;
    default:
      throw new AccountConnectionError("oauth_request_rejected", `Unknown account connection command: ${command}`);
  }
}

const FORBIDDEN_CLI_OPTIONS = new Set([
  "authorization",
  "client-id",
  "client-secret",
  "code",
  "id-token",
  "nonce",
  "refresh-token",
  "session-id",
  "state",
  "token",
]);

function rejectForbiddenOptions(options: Record<string, string | true>): void {
  const forbidden = Object.keys(options).find((name) => FORBIDDEN_CLI_OPTIONS.has(name.toLowerCase()));
  if (forbidden !== undefined) {
    throw new AccountConnectionError(
      "oauth_request_rejected",
      `--${forbidden} is not accepted by the hosted account connection CLI`,
    );
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

function required(options: Record<string, string | true>, name: string): string {
  const value = options[name];
  if (typeof value !== "string" || !value.trim()) {
    throw new AccountConnectionError("oauth_request_rejected", `--${name} is required`);
  }
  return value;
}

function optional(options: Record<string, string | true>, name: string): string | undefined {
  const value = options[name];
  return typeof value === "string" && value !== "" ? value : undefined;
}

function optionalBoolean(options: Record<string, string | true>, name: string): boolean | undefined {
  const value = options[name];
  if (value === undefined) return undefined;
  if (value === true || value === "true") return true;
  if (value === "false") return false;
  throw new AccountConnectionError("oauth_request_rejected", `--${name} must be true or false`);
}

function usage(): string {
  return [
    "usage: releasefoundry-account-connections <command> [options]",
    "commands: contract, start, connection, disconnect",
    "HTTP commands require --base-url and --provider github|google.",
    "OAuth callbacks are browser-only. The CLI never accepts codes, state, session ids, client secrets, tokens, or raw OIDC claims.",
  ].join("\n");
}

if (process.argv[1] !== undefined && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  runAccountConnectionCli(process.argv.slice(2))
    .then((result) => process.stdout.write(`${JSON.stringify(result, null, 2)}\n`))
    .catch((error) => {
      const safe = error instanceof AccountConnectionError
        ? error
        : new AccountConnectionError("oauth_request_failed", "Account connection CLI failed", 1);
      process.stderr.write(`${JSON.stringify(safe.toJSON())}\n`);
      process.exitCode = 1;
    });
}
