import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import {
  loadPostgresRlsQualification,
  validatePostgresRlsQualification
} from "./a3_postgres_rls_probe.mjs";

export const A3_SELF_HOST_SANDBOX_SCHEMA_VERSION = "a3.self_host_sandbox_calibration.v1";
export const A3_A1_SANDBOX_PROBE_SCHEMA_VERSION = "a3.a1_self_host_sandbox_probe.v1";

const REQUIRED_CHECK_IDS = new Set([
  "a1_control_plane_health",
  "a1_worker_retry_dead_letter",
  "a1_worker_expired_lease_recovery",
  "a1_local_object_storage_integrity"
]);

const REQUIRED_SCOPE_FIELDS = [
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
];

const VALUE_LEAK_PATTERNS = [
  { kind: "authorization", regex: /Bearer\s+[A-Za-z0-9._~+/=-]+/i },
  { kind: "github_token", regex: /(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+/i },
  { kind: "api_key", regex: /\bsk-[A-Za-z0-9_-]{12,}\b/i },
  { kind: "email", regex: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i },
  { kind: "signed_url", regex: /(?:X-Amz-Signature|X-Goog-Signature|Signature=)[A-Za-z0-9%._~-]+/i },
  { kind: "cookie", regex: /(?:^|[;\s])(?:session|cookie|csrf|xsrf)=[^;\s]+/i },
  { kind: "absolute_windows_path", regex: /(?:^|["'\s])[A-Za-z]:[\\/][^\s"']+/ },
  { kind: "absolute_unix_path", regex: /(?:^|["'\s])\/(?:Users|home|tmp|var|opt)\/[^\s"']+/ },
  { kind: "file_url", regex: /file:\/\//i }
];

const FORBIDDEN_KEY_PATTERN = /^(?:authorization|cookie|set_cookie|access_token|refresh_token|id_token|session_token|password|private_key|client_secret|api_key|signed_url|presigned_url|email)$/i;

export class A3SelfHostSandboxError extends Error {
  constructor(code, message, details = []) {
    super(message);
    this.name = "A3SelfHostSandboxError";
    this.code = code;
    this.details = details;
  }
}

export async function runA1SelfHostSandboxProbe(options = {}) {
  const repoRoot = resolve(options.repoRoot || process.cwd());
  const timeoutMs = positiveInteger(options.timeoutMs, 20_000);
  const maxOutputBytes = positiveInteger(options.maxOutputBytes, 256 * 1024);
  const python = options.pythonCommand || process.env.A3_PYTHON_COMMAND || "python";
  const args = ["-m", "services.report.a3_a1_sandbox_probe"];
  if (options.observedAt) args.push("--observed-at", String(options.observedAt));

  const result = await runChildProcess(python, args, {
    cwd: repoRoot,
    timeoutMs,
    maxOutputBytes,
    spawnImpl: options.spawnImpl
  });
  if (result.exitCode !== 0) {
    throw new A3SelfHostSandboxError(
      "probe_process_failed",
      "A1 self-host sandbox probe exited without a valid calibration result.",
      [{ exit_code: result.exitCode, stderr_class: classifyProbeStderr(result.stderr) }]
    );
  }

  let probe;
  try {
    probe = JSON.parse(result.stdout);
  } catch {
    throw new A3SelfHostSandboxError(
      "probe_output_invalid_json",
      "A1 self-host sandbox probe returned invalid JSON."
    );
  }
  return buildSelfHostSandboxCalibration(probe);
}

export function buildSelfHostSandboxCalibration(probe = {}) {
  const validated = validateA1SelfHostSandboxProbe(probe);
  const probePayloadSha256 = sha256(stableJson(validated));
  return {
    schema_version: A3_SELF_HOST_SANDBOX_SCHEMA_VERSION,
    calibration_id: validated.calibration_id,
    observed_at: validated.observed_at,
    source: "a1_local_runtime_probe",
    source_lane: "A1",
    product_owner: "A3",
    status: validated.status,
    tenant_scope: structuredClone(validated.tenant_scope),
    summary: structuredClone(validated.summary),
    checks: structuredClone(validated.checks),
    production_gaps: structuredClone(validated.production_gaps),
    authority_boundary: structuredClone(validated.authority_boundary),
    evidence_integrity: {
      algorithm: "sha256",
      probe_payload_sha256: `sha256:${probePayloadSha256}`,
      source_schema_version: validated.schema_version,
      validated: true
    },
    safety: {
      ...structuredClone(validated.safety),
      child_process_environment_allowlisted: true,
      stdout_size_limited: true,
      execution_timeout_enforced: true,
      output_schema_validated: true,
      production_verified: false,
      deployment_acceptance_mutated: false,
      a2_decision_recomputed: false
    }
  };
}

export function attachPostgresRlsQualification(calibration, qualification) {
  const validatedCalibration = validateSelfHostSandboxCalibration(calibration);
  const validatedQualification = validatePostgresRlsQualification(qualification);
  const postgresQualificationSha256 = `sha256:${sha256(stableJson(validatedQualification))}`;
  const combinedPayloadSha256 = `sha256:${sha256(stableJson({
    calibration_id: validatedCalibration.calibration_id,
    probe_payload_sha256: validatedCalibration.evidence_integrity.probe_payload_sha256,
    postgres_qualification: validatedQualification
  }))}`;
  return validateSelfHostSandboxCalibration({
    ...validatedCalibration,
    postgres_qualification: validatedQualification,
    evidence_integrity: {
      ...validatedCalibration.evidence_integrity,
      postgres_qualification_sha256: postgresQualificationSha256,
      combined_payload_sha256: combinedPayloadSha256
    }
  });
}

export async function attachPostgresRlsQualificationFromFile(calibration, path) {
  return attachPostgresRlsQualification(calibration, await loadPostgresRlsQualification(path));
}

export function validateA1SelfHostSandboxProbe(probe = {}) {
  const errors = [];
  if (!isRecord(probe)) errors.push("probe must be an object");
  if (probe.schema_version !== A3_A1_SANDBOX_PROBE_SCHEMA_VERSION) errors.push("unexpected probe schema_version");
  if (!/^a1-local-self-host-[0-9]{8}$/.test(String(probe.calibration_id || ""))) errors.push("invalid calibration_id");
  if (!isIsoTimestamp(probe.observed_at)) errors.push("observed_at must be an ISO timestamp");
  if (!["sandbox_verified", "sandbox_failed"].includes(probe.status)) errors.push("invalid sandbox status");
  if (probe.external_api_used !== false) errors.push("external_api_used must be false");
  if (probe.source_lane !== "A1" || probe.probe_owner !== "A3") errors.push("lane ownership must remain A1 -> A3");

  const scope = isRecord(probe.tenant_scope) ? probe.tenant_scope : {};
  for (const field of REQUIRED_SCOPE_FIELDS) {
    if (typeof scope[field] !== "string" || !scope[field]) errors.push(`tenant_scope.${field} is required`);
  }

  const checks = Array.isArray(probe.checks) ? probe.checks : [];
  const checkIds = new Set(checks.map((item) => item?.id));
  if (checks.length !== REQUIRED_CHECK_IDS.size) errors.push("probe must contain exactly four A1 checks");
  for (const id of REQUIRED_CHECK_IDS) {
    if (!checkIds.has(id)) errors.push(`missing check ${id}`);
  }
  for (const check of checks) {
    if (!isRecord(check)) {
      errors.push("check must be an object");
      continue;
    }
    if (!["passed", "failed"].includes(check.status)) errors.push(`invalid status for ${check.id || "unknown_check"}`);
    if (check.production_proof !== false) errors.push(`${check.id || "unknown_check"} must not claim production proof`);
    if (!["sandbox_verified", "sandbox_failed"].includes(check.evidence_level)) errors.push(`invalid evidence level for ${check.id || "unknown_check"}`);
  }

  const summary = isRecord(probe.summary) ? probe.summary : {};
  const passed = checks.filter((item) => item?.status === "passed").length;
  const failed = checks.filter((item) => item?.status === "failed").length;
  if (summary.total_checks !== checks.length || summary.passed !== passed || summary.failed !== failed) {
    errors.push("summary does not match check results");
  }
  if (probe.status === "sandbox_verified" && failed !== 0) errors.push("sandbox_verified cannot contain failed checks");

  const gaps = Array.isArray(probe.production_gaps) ? probe.production_gaps : [];
  if (gaps.length < 4) errors.push("production gaps must remain explicit");
  if (gaps.some((item) => item?.status !== "not_run")) errors.push("production gaps must remain not_run");

  const authority = isRecord(probe.authority_boundary) ? probe.authority_boundary : {};
  for (const field of ["production_verified", "deployment_acceptance_mutated", "release_ready_mutated", "a2_decision_recomputed"]) {
    if (authority[field] !== false) errors.push(`authority_boundary.${field} must be false`);
  }
  if (authority.a2_release_decision_authority !== "A2") errors.push("A2 must remain release-decision authority");

  const safety = isRecord(probe.safety) ? probe.safety : {};
  if (safety.local_only !== true) errors.push("safety.local_only must be true");
  for (const field of ["raw_payload_included", "credential_material_included", "absolute_local_path_included", "external_network_used", "releasefoundry_api_used"]) {
    if (safety[field] !== false) errors.push(`safety.${field} must be false`);
  }

  const leaks = findSelfHostSandboxLeaks(probe);
  if (leaks.length) errors.push(...leaks.map((item) => `${item.kind} at ${item.path}`));
  if (errors.length) {
    throw new A3SelfHostSandboxError(
      "probe_contract_invalid",
      "A1 self-host sandbox probe failed the A3 public-safety contract.",
      errors
    );
  }
  return structuredClone(probe);
}

export function validateSelfHostSandboxCalibration(calibration = {}) {
  const errors = [];
  if (!isRecord(calibration)) errors.push("calibration must be an object");
  if (calibration.schema_version !== A3_SELF_HOST_SANDBOX_SCHEMA_VERSION) errors.push("unexpected calibration schema_version");
  if (!["sandbox_verified", "sandbox_failed"].includes(calibration.status)) errors.push("invalid calibration status");
  if (!isRecord(calibration.evidence_integrity) || calibration.evidence_integrity.validated !== true) errors.push("validated evidence integrity is required");
  if (!/^sha256:[a-f0-9]{64}$/.test(String(calibration.evidence_integrity?.probe_payload_sha256 || ""))) errors.push("probe payload digest is invalid");
  if (calibration.authority_boundary?.production_verified !== false) errors.push("production_verified must remain false");
  if (calibration.authority_boundary?.deployment_acceptance_mutated !== false) errors.push("deployment acceptance must remain unchanged");
  if (calibration.authority_boundary?.a2_decision_recomputed !== false) errors.push("A2 decision must not be recomputed");
  if (calibration.safety?.production_verified !== false) errors.push("safety.production_verified must remain false");
  if (calibration.postgres_qualification !== undefined) {
    try {
      validatePostgresRlsQualification(calibration.postgres_qualification);
    } catch {
      errors.push("postgres_qualification is invalid");
    }
    const expectedPostgresSha256 = `sha256:${sha256(stableJson(calibration.postgres_qualification))}`;
    if (calibration.evidence_integrity?.postgres_qualification_sha256 !== expectedPostgresSha256) {
      errors.push("postgres qualification digest does not match the attached evidence");
    }
    const expectedCombinedSha256 = `sha256:${sha256(stableJson({
      calibration_id: calibration.calibration_id,
      probe_payload_sha256: calibration.evidence_integrity?.probe_payload_sha256,
      postgres_qualification: calibration.postgres_qualification
    }))}`;
    if (calibration.evidence_integrity?.combined_payload_sha256 !== expectedCombinedSha256) {
      errors.push("combined calibration digest does not match the attached evidence");
    }
  }
  const leaks = findSelfHostSandboxLeaks(calibration);
  if (leaks.length) errors.push(...leaks.map((item) => `${item.kind} at ${item.path}`));
  if (errors.length) {
    throw new A3SelfHostSandboxError(
      "calibration_contract_invalid",
      "Self-host sandbox calibration failed validation.",
      errors
    );
  }
  return structuredClone(calibration);
}

export async function loadSelfHostSandboxCalibration(path) {
  const payload = JSON.parse(await readFile(resolve(path), "utf8"));
  return validateSelfHostSandboxCalibration(payload);
}

export function findSelfHostSandboxLeaks(value, path = "$") {
  const findings = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => findings.push(...findSelfHostSandboxLeaks(item, `${path}[${index}]`)));
    return findings;
  }
  if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      const itemPath = `${path}.${key}`;
      if (FORBIDDEN_KEY_PATTERN.test(key)) findings.push({ kind: "sensitive_key", path: itemPath });
      findings.push(...findSelfHostSandboxLeaks(item, itemPath));
    }
    return findings;
  }
  if (typeof value !== "string") return findings;
  for (const pattern of VALUE_LEAK_PATTERNS) {
    if (pattern.regex.test(value)) findings.push({ kind: pattern.kind, path });
  }
  return findings;
}

async function runChildProcess(command, args, options) {
  const spawnImpl = options.spawnImpl || spawn;
  return new Promise((resolvePromise, reject) => {
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let settled = false;
    let timedOut = false;
    let oversized = false;
    const child = spawnImpl(command, args, {
      cwd: options.cwd,
      shell: false,
      windowsHide: true,
      env: publicSafeChildEnvironment(process.env)
    });
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, options.timeoutMs);

    const collect = (kind, chunk) => {
      const text = String(chunk);
      outputBytes += Buffer.byteLength(text);
      if (outputBytes > options.maxOutputBytes) {
        oversized = true;
        child.kill();
        return;
      }
      if (kind === "stdout") stdout += text;
      else stderr += text;
    };
    child.stdout?.on("data", (chunk) => collect("stdout", chunk));
    child.stderr?.on("data", (chunk) => collect("stderr", chunk));
    child.once("error", (error) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      reject(new A3SelfHostSandboxError("probe_process_unavailable", "A1 sandbox probe process could not start.", [{ error_class: error.name }]));
    });
    child.once("close", (exitCode) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      if (timedOut) return reject(new A3SelfHostSandboxError("probe_timeout", "A1 sandbox probe exceeded its execution deadline."));
      if (oversized) return reject(new A3SelfHostSandboxError("probe_output_too_large", "A1 sandbox probe exceeded its output limit."));
      resolvePromise({ exitCode: Number(exitCode ?? 1), stdout: stdout.trim(), stderr: stderr.trim() });
    });
  });
}

function publicSafeChildEnvironment(env = {}) {
  const next = { PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1" };
  for (const name of ["PATH", "Path", "PATHEXT", "SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"]) {
    if (env[name]) next[name] = env[name];
  }
  return next;
}

function classifyProbeStderr(value = "") {
  if (!value) return "empty";
  if (/ModuleNotFoundError/.test(value)) return "module_unavailable";
  if (/PermissionError|EACCES/i.test(value)) return "permission_denied";
  return "probe_runtime_error";
}

function positiveInteger(value, fallback) {
  const number = Number(value ?? fallback);
  return Number.isInteger(number) && number > 0 ? number : fallback;
}

function isIsoTimestamp(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) && /(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(value);
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) return value.map(sortForStableJson);
  if (isRecord(value)) {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, sortForStableJson(item)])
    );
  }
  return value;
}
