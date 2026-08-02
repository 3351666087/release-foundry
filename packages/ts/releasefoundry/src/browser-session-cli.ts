#!/usr/bin/env node

import {
  BrowserSessionError,
  browserSessionCapabilityManifest,
  browserSessionOpenApiDocument,
  buildBrowserCookieReplacement,
} from "./browser-session.js";

type Command = "capabilities" | "openapi" | "cookie-contract";

interface ParsedArgs {
  command: Command;
  issuedAt?: string;
  accessExpiresAt?: string;
  refreshExpiresAt?: string;
  accessCapSeconds?: number;
  refreshCapSeconds?: number;
  replayedAt?: string;
}

function usage(): string {
  return [
    "Usage:",
    "  releasefoundry-browser-session capabilities",
    "  releasefoundry-browser-session openapi",
    "  releasefoundry-browser-session cookie-contract --issued-at <iso> --access-expires-at <iso> --refresh-expires-at <iso> [--access-cap-seconds <n>] [--refresh-cap-seconds <n>] [--replayed-at <iso>]",
  ].join("\n");
}

function parseArgs(argv: readonly string[]): ParsedArgs {
  const command = argv[0];
  if (command !== "capabilities" && command !== "openapi" && command !== "cookie-contract") {
    throw new BrowserSessionError("browser_session_invalid_request");
  }
  const parsed: ParsedArgs = { command };
  const stringFlags: Readonly<Record<string, keyof ParsedArgs>> = {
    "--issued-at": "issuedAt",
    "--access-expires-at": "accessExpiresAt",
    "--refresh-expires-at": "refreshExpiresAt",
    "--replayed-at": "replayedAt",
  };
  const numberFlags: Readonly<Record<string, keyof ParsedArgs>> = {
    "--access-cap-seconds": "accessCapSeconds",
    "--refresh-cap-seconds": "refreshCapSeconds",
  };
  for (let index = 1; index < argv.length; index += 2) {
    const flag = argv[index];
    const value = argv[index + 1];
    if (flag === undefined || value === undefined || !flag.startsWith("--") || value.startsWith("--")) {
      throw new BrowserSessionError("browser_session_invalid_request");
    }
    const stringKey = stringFlags[flag];
    const numberKey = numberFlags[flag];
    if (stringKey !== undefined) {
      (parsed as unknown as Record<string, unknown>)[stringKey] = value;
    } else if (numberKey !== undefined && /^\d+$/u.test(value)) {
      (parsed as unknown as Record<string, unknown>)[numberKey] = Number(value);
    } else {
      throw new BrowserSessionError("browser_session_invalid_request");
    }
  }
  return parsed;
}

export function main(argv: readonly string[] = process.argv.slice(2)): number {
  try {
    if (argv.includes("--help") || argv.includes("-h")) {
      process.stdout.write(`${usage()}\n`);
      return 0;
    }
    const args = parseArgs(argv);
    let output: unknown;
    if (args.command === "capabilities") {
      output = browserSessionCapabilityManifest();
    } else if (args.command === "openapi") {
      output = browserSessionOpenApiDocument();
    } else {
      if (args.issuedAt === undefined || args.accessExpiresAt === undefined || args.refreshExpiresAt === undefined) {
        throw new BrowserSessionError("browser_session_invalid_request");
      }
      let replacement = buildBrowserCookieReplacement({
        issuedAt: args.issuedAt,
        accessExpiresAt: args.accessExpiresAt,
        refreshExpiresAt: args.refreshExpiresAt,
        accessCapSeconds: args.accessCapSeconds,
        refreshCapSeconds: args.refreshCapSeconds,
      });
      if (args.replayedAt !== undefined) replacement = replacement.replay(args.replayedAt);
      output = replacement.toJSON();
    }
    process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
    return 0;
  } catch (error) {
    const safe = error instanceof BrowserSessionError
      ? error.toJSON()
      : new BrowserSessionError("browser_session_transport_failed").toJSON();
    process.stderr.write(`${JSON.stringify(safe)}\n`);
    return 2;
  }
}

if (process.argv[1]?.endsWith("browser-session-cli.js")) process.exitCode = main();
