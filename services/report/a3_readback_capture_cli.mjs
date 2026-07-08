#!/usr/bin/env node
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function parseReadbackCaptureArgs(argv = []) {
  const args = {
    dryRun: true,
    source: "mock"
  };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    const next = () => argv[++index];
    if (item === "--api-url") args.apiUrl = next();
    else if (item === "--release-id") args.releaseId = next();
    else if (item === "--readback") args.readback = next();
    else if (item === "--source") args.source = next();
    else if (item === "--organization-id") args.organizationId = next();
    else if (item === "--project-id") args.projectId = next();
    else if (item === "--actor-hash") args.actorHash = next();
    else if (item === "--idempotency-key") args.idempotencyKey = next();
    else if (item === "--output-receipt") args.outputReceipt = next();
    else if (item === "--submit") args.dryRun = false;
    else if (item === "--dry-run") args.dryRun = true;
    else if (item === "--json") args.json = true;
    else if (item === "--help" || item === "-h") args.help = true;
    else throw new Error(`Unknown argument: ${item}`);
  }
  return args;
}

export async function buildReadbackCaptureCliReceipt(options = {}, io = {}) {
  if (options.help) {
    return usageReceipt();
  }
  if (!options.apiUrl) {
    throw new Error("--api-url is required.");
  }
  if (!options.releaseId) {
    throw new Error("--release-id is required.");
  }
  if (!options.readback) {
    throw new Error("--readback is required.");
  }
  const readback = sanitizeReadback(await readJsonInput(options.readback, io));
  const endpoint = releaseReadbackEndpoint(options);
  const requestBody = sanitizeReadback({
    source: options.source || "mock",
    organization_id: options.organizationId,
    project_id: options.projectId,
    actor_hash: options.actorHash,
    readback
  });
  const request = {
    method: "POST",
    url: endpoint.toString(),
    endpoint_path: endpoint.pathname,
    source: options.source || "mock",
    release_id: options.releaseId,
    idempotency_key_present: Boolean(options.idempotencyKey),
    idempotency_key_hash: options.idempotencyKey ? sha256(options.idempotencyKey).slice(0, 16) : null,
    payload_hash: sha256(stableJson(readback)),
    readback_kind: normalizeReadbackResourceKind(readback.resource_kind || readback.resourceKind),
    readback_status: readback.readback_status || readback.enforcement_readback_status || "unknown",
    body: requestBody,
    safety: safetyBlock()
  };
  if (options.dryRun !== false) {
    return {
      schema_version: "a3.readback_capture_cli_receipt.v1",
      status: "planned",
      dry_run: true,
      submitted: false,
      request,
      api_receipt: null,
      safety: safetyBlock()
    };
  }

  const response = await (options.fetchImpl || fetch)(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(options.idempotencyKey ? { "idempotency-key": options.idempotencyKey } : {})
    },
    body: JSON.stringify(requestBody)
  });
  const apiReceipt = sanitizeReadback(await safeJsonResponse(response));
  return {
    schema_version: "a3.readback_capture_cli_receipt.v1",
    status: response.ok ? "submitted" : "failed",
    dry_run: false,
    submitted: response.ok,
    http_status: response.status,
    request: {
      ...request,
      body: {
        ...request.body,
        readback: {
          schema_version: request.body.readback?.schema_version || "unknown",
          resource_kind: request.body.readback?.resource_kind || "unknown",
          readback_status: request.body.readback?.readback_status || request.body.readback?.enforcement_readback_status || "unknown",
          payload_hash: request.body.readback?.payload_hash || request.payload_hash
        }
      }
    },
    api_receipt: apiReceipt,
    safety: safetyBlock()
  };
}

export async function runReadbackCaptureCli(argv = process.argv.slice(2), io = {}) {
  try {
    const args = parseReadbackCaptureArgs(argv);
    const receipt = await buildReadbackCaptureCliReceipt(args, io);
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
      schema_version: "a3.readback_capture_cli_error.v1",
      error: "readback_capture_cli_error",
      message: sanitizeString(error.message),
      safety: safetyBlock()
    };
    (io.stderr || process.stderr).write(`${JSON.stringify(payload, null, 2)}\n`);
    return 1;
  }
}

function releaseReadbackEndpoint(options = {}) {
  const endpoint = new URL(`/api/a3/releases/${encodeURIComponent(options.releaseId)}/readbacks`, options.apiUrl);
  endpoint.searchParams.set("source", options.source || "mock");
  return endpoint;
}

async function readJsonInput(inputPath, io = {}) {
  const text = inputPath === "-"
    ? await readStdin(io.stdin || process.stdin)
    : await readFile(resolve(inputPath), "utf8");
  return JSON.parse(text);
}

async function readStdin(stream) {
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function safeJsonResponse(response) {
  const text = await response.text();
  if (!text.trim()) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return {
      schema_version: "a3.readback_capture_http_error.v1",
      redacted_body: sanitizeString(text).slice(0, 500)
    };
  }
}

function usageReceipt() {
  return {
    schema_version: "a3.readback_capture_cli_usage.v1",
    command: "node services/report/a3_readback_capture_cli.mjs --api-url http://127.0.0.1:4173 --release-id current --readback artifacts/readback.json --submit --output-receipt artifacts/readback-capture.json",
    default_mode: "dry-run",
    submit_mode: "Add --submit to POST the sanitized readback receipt into the A3 API.",
    safety: safetyBlock()
  };
}

function sanitizeReadback(value) {
  if (value === null || value === undefined) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(sanitizeReadback);
  }
  if (typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key,
      /authorization|secret|token|cookie|email|password|key_value|api_key|access_key|private_key/i.test(key)
        && typeof item !== "boolean"
        && typeof item !== "number"
        ? "[REDACTED]"
        : sanitizeReadback(item)
    ]));
  }
  if (typeof value === "string") {
    return sanitizeString(value);
  }
  return value;
}

function normalizeReadbackResourceKind(value) {
  const kind = String(value || "unknown").toLowerCase();
  if (["check_run", "github_check"].includes(kind)) {
    return "github_check";
  }
  if (["pr_comment", "pull_request_comment"].includes(kind)) {
    return "pr_comment";
  }
  if (["required_check", "branch_protection"].includes(kind)) {
    return "required_check";
  }
  return kind;
}

function sanitizeString(value = "") {
  return String(value)
    .replace(/\b(Authorization:\s*Bearer\s+)[A-Za-z0-9._-]{8,}/gi, "$1[REDACTED]")
    .replace(/\bBearer\s+[A-Za-z0-9._-]{8,}/gi, "Bearer [REDACTED]")
    .replace(/\bCookie:\s*[^;\n]+/gi, "Cookie: [REDACTED]")
    .replace(/\bASHR(?:_LABS)?_API_KEY\s*[:=]\s*[^\s"']+/gi, "ASHR_API_KEY=[REDACTED]")
    .replace(/\b(gh[pousr]_|github_pat_|sk-|ashr_)[A-Za-z0-9._-]{8,}/gi, "[REDACTED_SECRET]")
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]");
}

function safetyBlock() {
  return {
    token_included: false,
    secret_values_allowed: false,
    raw_body_stored: false,
    real_github_mutation_performed: false,
    real_ashr_api_called: false
  };
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, sortForStableJson(item)])
    );
  }
  return value;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  runReadbackCaptureCli().then((exitCode) => {
    process.exitCode = exitCode;
  });
}
