#!/usr/bin/env node

import {
  ACCOUNT_READINESS_ENVIRONMENTS,
  ACCOUNT_READINESS_PROVIDERS,
  AccountReadinessError,
  build_receipt_template,
  load_account_readiness_receipt,
} from "./account-readiness.js";

interface ParsedArgs {
  command: "template" | "validate";
  provider?: string;
  environment?: string;
  file?: string;
}

function usage(): string {
  return [
    "Usage:",
    "  releasefoundry-account-readiness template --provider <provider> [--environment sandbox|production]",
    "  releasefoundry-account-readiness validate --file <receipt.json>",
    `Providers: ${ACCOUNT_READINESS_PROVIDERS.join(", ")}`,
  ].join("\n");
}

function parseArgs(argv: string[]): ParsedArgs {
  const command = argv[0];
  if (command !== "template" && command !== "validate") {
    throw new AccountReadinessError("command must be template or validate");
  }
  const parsed: ParsedArgs = { command };
  for (let index = 1; index < argv.length; index += 1) {
    const flag = argv[index];
    const value = argv[index + 1];
    if (!flag?.startsWith("--") || value === undefined || value.startsWith("--")) {
      throw new AccountReadinessError("each option requires a value");
    }
    if (flag === "--provider") {
      parsed.provider = value;
    } else if (flag === "--environment") {
      parsed.environment = value;
    } else if (flag === "--file") {
      parsed.file = value;
    } else {
      throw new AccountReadinessError("unsupported option");
    }
    index += 1;
  }
  return parsed;
}

export function main(argv: string[] = process.argv.slice(2)): number {
  try {
    if (argv.includes("--help") || argv.includes("-h")) {
      process.stdout.write(`${usage()}\n`);
      return 0;
    }
    const args = parseArgs(argv);
    let output;
    if (args.command === "template") {
      if (args.provider === undefined) {
        throw new AccountReadinessError("--provider is required");
      }
      const environment = args.environment ?? "sandbox";
      if (!ACCOUNT_READINESS_ENVIRONMENTS.includes(environment as "sandbox" | "production")) {
        throw new AccountReadinessError("environment must be sandbox or production");
      }
      output = build_receipt_template(args.provider, environment);
    } else {
      if (args.file === undefined) {
        throw new AccountReadinessError("--file is required");
      }
      output = load_account_readiness_receipt(args.file);
    }
    process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
    return 0;
  } catch (error) {
    const message = error instanceof AccountReadinessError ? error.message : "account-readiness operation failed";
    process.stderr.write(`${JSON.stringify({ status: "rejected", error: message })}\n`);
    return 2;
  }
}

if (process.argv[1]?.endsWith("account-readiness-cli.js")) {
  process.exitCode = main();
}
