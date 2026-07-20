#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  buildA3MultimodalReviewAssignmentPacket,
  renderA3MultimodalReviewAssignmentPacketMarkdown,
  verifyA3MultimodalReviewAssignmentPacket
} from "./a3_multimodal_review_assignment.mjs";
import { buildA3MultimodalReviewQueue } from "./a3_multimodal_review_queue.mjs";

export async function buildA3MultimodalReviewPacketFromFiles(options = {}) {
  const comparison = await readJson(options.comparison, "comparison");
  const eventFixture = await readJson(options.events, "events");
  if (eventFixture.schema_version !== "a3.multimodal_review_assignment_events_fixture.v1") {
    throw new Error("Assignment events fixture schema is unsupported.");
  }
  const queue = buildA3MultimodalReviewQueue(comparison, {
    source: options.source || eventFixture.source || "unknown",
    tenantScope: eventFixture.tenant_scope,
    sourceCommitAlias: options.sourceCommitAlias || eventFixture.source_commit_alias,
    ingestMode: eventFixture.ingest_mode || "redacted_packet_input",
    capabilityState: eventFixture.capability_state || "contract_supported_not_production_verified"
  });
  const packet = buildA3MultimodalReviewAssignmentPacket(queue, {
    events: eventFixture.events,
    now: options.now || eventFixture.observed_at,
    generatedAt: options.generatedAt || "runtime"
  });
  const verification = verifyA3MultimodalReviewAssignmentPacket(packet, {
    verifiedAt: options.verifiedAt || options.generatedAt || "runtime",
    noFail: options.noFail
  });
  if (verification.status !== "passed" && !options.noFail) {
    throw new Error("Generated multimodal review assignment packet failed integrity verification.");
  }
  return { packet, verification };
}

export async function verifyA3MultimodalReviewPacketFile(path, options = {}) {
  const packet = await readJson(path, "packet");
  return {
    packet,
    verification: verifyA3MultimodalReviewAssignmentPacket(packet, {
      verifiedAt: options.verifiedAt || "runtime",
      noFail: options.noFail
    })
  };
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) {
    process.stdout.write(helpText());
    return 0;
  }
  const result = options.verify
    ? await verifyA3MultimodalReviewPacketFile(options.verify, options)
    : await buildA3MultimodalReviewPacketFromFiles(options);
  if (options.output) await writeJson(options.output, result.packet);
  if (options.outputVerification) await writeJson(options.outputVerification, result.verification);
  const markdown = renderA3MultimodalReviewAssignmentPacketMarkdown(result.packet, result.verification);
  if (options.outputMarkdown) await writeText(options.outputMarkdown, markdown);
  process.stdout.write(options.format === "markdown"
    ? markdown
    : `${JSON.stringify(options.verify ? result.verification : result.packet, null, 2)}\n`);
  return options.noFail ? 0 : result.verification.process_exit_code;
}

function parseArgs(argv) {
  const options = { format: "json" };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (["--comparison", "--events", "--source", "--source-commit-alias", "--now", "--generated-at", "--verified-at", "--output", "--output-verification", "--output-markdown", "--verify"].includes(arg)) {
      const key = {
        "--comparison": "comparison",
        "--events": "events",
        "--source": "source",
        "--source-commit-alias": "sourceCommitAlias",
        "--now": "now",
        "--generated-at": "generatedAt",
        "--verified-at": "verifiedAt",
        "--output": "output",
        "--output-verification": "outputVerification",
        "--output-markdown": "outputMarkdown",
        "--verify": "verify"
      }[arg];
      options[key] = next;
      index += 1;
    } else if (arg === "--markdown") {
      options.format = "markdown";
    } else if (arg === "--json") {
      options.format = "json";
    } else if (arg === "--no-fail") {
      options.noFail = true;
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!options.help && !options.verify && (!options.comparison || !options.events)) {
    throw new Error("--comparison and --events are required when building a packet.");
  }
  return options;
}

function helpText() {
  return "Usage: node services/report/a3_multimodal_review_packet_cli.mjs --comparison <public-safe-comparison.json> --events <redacted-assignment-events.json> --generated-at <ISO> [--output packet.json] [--output-verification verification.json] [--output-markdown packet.md] [--json|--markdown]\n       node services/report/a3_multimodal_review_packet_cli.mjs --verify <packet.json> [--output-verification verification.json] [--json|--markdown] [--no-fail]\n";
}

async function readJson(path, label) {
  if (!path) throw new Error(`${label} path is required.`);
  return JSON.parse(await readFile(resolve(path), "utf8"));
}

async function writeJson(path, value) {
  await writeText(path, `${JSON.stringify(value, null, 2)}\n`);
}

async function writeText(path, value) {
  const target = resolve(path);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, value, "utf8");
}

const isMain = process.argv[1]
  && pathToFileURL(resolve(process.argv[1])).href === import.meta.url;
if (isMain) {
  main().then((exitCode) => {
    process.exitCode = exitCode;
  }).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
