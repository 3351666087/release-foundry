import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { buildA3SqlMigrationPlan } from "./a3_sql_migrations.mjs";

export const A3_POSTGRES_RLS_QUALIFICATION_SCHEMA_VERSION = "a3.postgres_rls_qualification.v1";

const MIGRATION_IDS = [
  "019_self_host_sandbox_calibrations",
  "020_self_host_sandbox_scope_hardening"
];
const MIGRATION_CHAIN_ID = "019_to_020_self_host_sandbox_rls";
const PROBE_ROLE = "a3_postgres_rls_probe_7f36c2";
const PROBE_SOURCE = "a3_postgres_rls_probe";
const SCOPE_FIELDS = [
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
];
const SCOPE_A = {
  organization_id: "org-a3-pg-a",
  tenant_id: "tenant-a3-pg-a",
  workspace_id: "workspace-a3-pg-a",
  project_id: "project-a3-pg-a",
  environment_id: "staging-a3-pg-a"
};
const SCOPE_B = {
  organization_id: "org-a3-pg-b",
  tenant_id: "tenant-a3-pg-b",
  workspace_id: "workspace-a3-pg-b",
  project_id: "project-a3-pg-b",
  environment_id: "staging-a3-pg-b"
};
const LEAK_PATTERNS = [
  /Bearer\s+[A-Za-z0-9._~+/=-]+/i,
  /(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+/i,
  /\bsk-[A-Za-z0-9_-]{12,}\b/i,
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[^\s,}]+/i,
  /(?:^|["'\s])[A-Za-z]:[\\/][^\s"']+/,
  /(?:^|["'\s])\/(?:Users|home|tmp|var|opt)\/[^\s"']+/
];

export class A3PostgresRlsProbeError extends Error {
  constructor(code, message, details = []) {
    super(message);
    this.name = "A3PostgresRlsProbeError";
    this.code = code;
    this.details = details;
  }
}

export function getSelfHostSandboxPostgresMigration() {
  const statements = buildA3SqlMigrationPlan({ dialect: "postgres" }).statements;
  const migrations = MIGRATION_IDS.map((id) => statements.find((item) => item.id === id));
  if (migrations.some((item) => !item)) {
    throw new A3PostgresRlsProbeError("migration_missing", "The self-host PostgreSQL migration chain is unavailable.");
  }
  return {
    id: MIGRATION_CHAIN_ID,
    migration_ids: [...MIGRATION_IDS],
    sql: migrations.map((item) => `-- ${item.id}\n${item.sql}`).join("\n\n")
  };
}

export async function runA3PostgresRlsQualification(options = {}) {
  const observedAt = isoTimestamp(options.observedAt || new Date().toISOString());
  const targetClass = normalizeTargetClass(options.targetClass);
  const migration = getSelfHostSandboxPostgresMigration();
  const executeSql = options.executeSql || createPsqlExecutor(options);
  let cleanupCompleted = false;
  let qualification = null;
  let operationError = null;

  try {
    await requireSuccess(executeSql, "migration_apply_1", migration.sql);
    await requireSuccess(executeSql, "migration_apply_2", migration.sql);
    await requireSuccess(executeSql, "probe_setup", setupSql(observedAt));

    const metadata = parseSingleJson(await requireSuccess(executeSql, "metadata_readback", metadataSql()), "metadata_readback");
    const scopedRead = parseSingleJson(await requireSuccess(executeSql, "scoped_read", scopedReadSql()), "scoped_read");
    const missingScope = parseSingleJson(await requireSuccess(executeSql, "missing_scope_read", missingScopeReadSql()), "missing_scope_read");
    const sameScopeWrite = await requireSuccess(executeSql, "same_scope_write", sameScopeWriteSql());
    const crossScopeWrite = await executeSql({ phase: "cross_scope_write", sql: crossScopeWriteSql() });

    const crossScopeDenied = crossScopeWrite.exitCode !== 0
      && classifyPsqlStderr(crossScopeWrite.stderr) === "row_level_security_denied";
    qualification = {
      schema_version: A3_POSTGRES_RLS_QUALIFICATION_SCHEMA_VERSION,
      qualification_id: "a3-postgres-rls-20260713",
      observed_at: observedAt,
      source: PROBE_SOURCE,
      target_class: targetClass,
      status: "postgres_rls_verified",
      evidence_level: "sandbox_verified",
      database: {
        engine: "postgresql",
        server_version: safeServerVersion(metadata.server_version),
        server_version_num: integer(metadata.server_version_num),
        migration_id: MIGRATION_CHAIN_ID,
        migration_ids: [...MIGRATION_IDS],
        migration_sha256: `sha256:${sha256(migration.sql)}`,
        migration_apply_count: 2,
        migration_statement_count: MIGRATION_IDS.length,
        rls_enabled: metadata.rls_enabled === true,
        rls_forced: metadata.rls_forced === true,
        policy_count: integer(metadata.policy_count),
        runtime_role_nosuperuser: metadata.role_superuser === false,
        runtime_role_nobypassrls: metadata.role_bypassrls === false
      },
      tenant_isolation: {
        scope_levels: [...SCOPE_FIELDS],
        same_scope_read_count: integer(scopedRead.same_scope_read_count),
        cross_scope_read_count: integer(scopedRead.cross_scope_read_count),
        visible_total_for_scope_a: integer(scopedRead.visible_total),
        missing_scope_read_count: integer(missingScope.visible_total),
        same_scope_write_allowed: sameScopeWrite.stdout.includes("a3-pg-rls-write-allowed"),
        cross_scope_write_denied: crossScopeDenied
      },
      authority_boundary: {
        production_verified: false,
        target_customer_environment_verified: false,
        deployment_acceptance_mutated: false,
        release_ready_mutated: false,
        a2_decision_recomputed: false,
        a2_release_decision_authority: "A2"
      },
      safety: {
        credentials_included: false,
        dsn_included: false,
        host_included: false,
        raw_sql_output_included: false,
        child_process_shell_used: false,
        child_environment_allowlisted: true,
        cleanup_completed: false
      }
    };
  } catch (error) {
    operationError = error;
  }
  try {
    const cleanup = await executeSql({ phase: "cleanup", sql: cleanupSql() });
    cleanupCompleted = cleanup.exitCode === 0;
  } catch {
    cleanupCompleted = false;
  }
  if (typeof options.onCleanup === "function") options.onCleanup(cleanupCompleted);
  if (operationError) throw operationError;
  if (!cleanupCompleted) {
    throw new A3PostgresRlsProbeError(
      "postgres_cleanup_failed",
      "PostgreSQL qualification completed but probe cleanup did not finish."
    );
  }
  qualification.safety.cleanup_completed = true;
  return validatePostgresRlsQualification(qualification);
}

export function validatePostgresRlsQualification(value = {}) {
  const errors = [];
  if (!isRecord(value)) errors.push("qualification must be an object");
  if (value.schema_version !== A3_POSTGRES_RLS_QUALIFICATION_SCHEMA_VERSION) errors.push("unexpected schema_version");
  if (value.status !== "postgres_rls_verified") errors.push("status must be postgres_rls_verified");
  if (value.evidence_level !== "sandbox_verified") errors.push("evidence_level must remain sandbox_verified");
  if (!isIsoTimestamp(value.observed_at)) errors.push("observed_at must be an ISO timestamp");
  if (!/^sha256:[a-f0-9]{64}$/.test(String(value.database?.migration_sha256 || ""))) errors.push("migration digest is invalid");
  if (value.database?.migration_id !== MIGRATION_CHAIN_ID || value.database?.migration_apply_count !== 2) errors.push("migration 019-to-020 chain must apply twice");
  if (value.database?.migration_statement_count !== MIGRATION_IDS.length) errors.push("migration chain must contain 019 and 020");
  if (!sameStringArray(value.database?.migration_ids, MIGRATION_IDS)) errors.push("migration ids must exactly match the 019-to-020 chain");
  if (value.database?.rls_enabled !== true || value.database?.rls_forced !== true) errors.push("PostgreSQL RLS must be enabled and forced");
  if (Number(value.database?.policy_count) < 1) errors.push("at least one RLS policy is required");
  if (value.database?.runtime_role_nosuperuser !== true || value.database?.runtime_role_nobypassrls !== true) errors.push("runtime role must not bypass RLS");
  if (value.tenant_isolation?.same_scope_read_count !== 1) errors.push("same-scope read must expose exactly one row");
  if (value.tenant_isolation?.cross_scope_read_count !== 0) errors.push("cross-scope read must expose zero rows");
  if (value.tenant_isolation?.visible_total_for_scope_a !== 1) errors.push("scope A must see exactly one seeded row");
  if (value.tenant_isolation?.missing_scope_read_count !== 0) errors.push("missing scope must expose zero rows");
  if (value.tenant_isolation?.same_scope_write_allowed !== true) errors.push("same-scope write must be allowed");
  if (value.tenant_isolation?.cross_scope_write_denied !== true) errors.push("cross-scope write must be denied by RLS");
  if (!sameStringArray(value.tenant_isolation?.scope_levels, SCOPE_FIELDS)) errors.push("the exact five scope levels are required");
  for (const field of ["production_verified", "target_customer_environment_verified", "deployment_acceptance_mutated", "release_ready_mutated", "a2_decision_recomputed"]) {
    if (value.authority_boundary?.[field] !== false) errors.push(`authority_boundary.${field} must remain false`);
  }
  if (value.authority_boundary?.a2_release_decision_authority !== "A2") errors.push("A2 must remain release-decision authority");
  if (value.safety?.cleanup_completed !== true) errors.push("probe cleanup must complete");
  if (containsSensitiveValue(value)) errors.push("qualification contains sensitive or local-path material");
  if (errors.length) {
    throw new A3PostgresRlsProbeError(
      "postgres_rls_qualification_invalid",
      "PostgreSQL RLS qualification failed its public-safety contract.",
      errors
    );
  }
  return structuredClone(value);
}

export async function loadPostgresRlsQualification(path) {
  return validatePostgresRlsQualification(JSON.parse(await readFile(resolve(path), "utf8")));
}

function createPsqlExecutor(options) {
  const connection = postgresConnection(options);
  const command = options.psqlCommand || process.env.A3_PSQL_BIN || "psql";
  const timeoutMs = positiveInteger(options.timeoutMs, 20_000);
  const maxOutputBytes = positiveInteger(options.maxOutputBytes, 256 * 1024);
  return ({ phase, sql }) => runPsql(command, sql, {
    phase,
    timeoutMs,
    maxOutputBytes,
    spawnImpl: options.spawnImpl,
    env: postgresChildEnvironment(process.env, connection)
  });
}

function postgresConnection(options = {}) {
  const connection = options.connection || {};
  const result = {
    host: connection.host || process.env.A3_POSTGRES_TEST_HOST || process.env.PGHOST,
    port: String(connection.port || process.env.A3_POSTGRES_TEST_PORT || process.env.PGPORT || "5432"),
    user: connection.user || process.env.A3_POSTGRES_TEST_USER || process.env.PGUSER,
    database: connection.database || process.env.A3_POSTGRES_TEST_DATABASE || process.env.PGDATABASE,
    password: connection.password || process.env.A3_POSTGRES_TEST_PASSWORD || process.env.PGPASSWORD || "",
    sslmode: connection.sslmode || process.env.A3_POSTGRES_TEST_SSLMODE || process.env.PGSSLMODE || "disable"
  };
  if (!result.host || !result.user || !result.database) {
    throw new A3PostgresRlsProbeError(
      "postgres_connection_missing",
      "PostgreSQL host, user, and database must be supplied through the test connection boundary."
    );
  }
  return result;
}

function postgresChildEnvironment(parent, connection) {
  const env = {
    PGHOST: connection.host,
    PGPORT: connection.port,
    PGUSER: connection.user,
    PGDATABASE: connection.database,
    PGSSLMODE: connection.sslmode,
    PSQLRC: "NUL"
  };
  if (connection.password) env.PGPASSWORD = connection.password;
  for (const name of ["PATH", "Path", "PATHEXT", "SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"]) {
    if (parent[name]) env[name] = parent[name];
  }
  return env;
}

function runPsql(command, sql, options) {
  const spawnImpl = options.spawnImpl || spawn;
  return new Promise((resolvePromise, reject) => {
    const child = spawnImpl(command, [
      "--no-password",
      "--no-psqlrc",
      "--quiet",
      "--tuples-only",
      "--no-align",
      "--set", "ON_ERROR_STOP=1"
    ], {
      shell: false,
      windowsHide: true,
      env: options.env,
      stdio: ["pipe", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let settled = false;
    let timedOut = false;
    let oversized = false;
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
      reject(new A3PostgresRlsProbeError("psql_unavailable", "PostgreSQL client could not start.", [{ phase: options.phase, error_class: error.name }]));
    });
    child.once("close", (exitCode) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      if (timedOut) return reject(new A3PostgresRlsProbeError("psql_timeout", "PostgreSQL probe exceeded its deadline.", [{ phase: options.phase }]));
      if (oversized) return reject(new A3PostgresRlsProbeError("psql_output_too_large", "PostgreSQL probe exceeded its output limit.", [{ phase: options.phase }]));
      resolvePromise({ exitCode: Number(exitCode ?? 1), stdout: stdout.trim(), stderr: stderr.trim() });
    });
    child.stdin.end(sql);
  });
}

async function requireSuccess(executeSql, phase, sql) {
  const result = await executeSql({ phase, sql });
  if (result.exitCode !== 0) {
    throw new A3PostgresRlsProbeError(
      "postgres_phase_failed",
      `PostgreSQL qualification phase ${phase} failed.`,
      [{ phase, stderr_class: classifyPsqlStderr(result.stderr) }]
    );
  }
  return result;
}

function setupSql(observedAt) {
  return `
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${PROBE_ROLE}') THEN
    CREATE ROLE ${PROBE_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;
GRANT ${PROBE_ROLE} TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO ${PROBE_ROLE};
GRANT SELECT, INSERT ON self_host_sandbox_calibrations TO ${PROBE_ROLE};
DELETE FROM self_host_sandbox_calibrations WHERE source = '${PROBE_SOURCE}';
INSERT INTO self_host_sandbox_calibrations (
  id, organization_id, tenant_id, workspace_id, project_id, environment_id,
  source, status, evidence_level, production_verified,
  deployment_acceptance_mutated, a2_decision_recomputed, probe_payload_sha256,
  payload, observed_at, created_at
) VALUES
  ('a3-pg-rls-a', '${SCOPE_A.organization_id}', '${SCOPE_A.tenant_id}', '${SCOPE_A.workspace_id}', '${SCOPE_A.project_id}', '${SCOPE_A.environment_id}', '${PROBE_SOURCE}', 'sandbox_verified', 'postgres_live', FALSE, FALSE, FALSE, 'sha256:${"a".repeat(64)}', '{}'::jsonb, '${observedAt}'::timestamptz, '${observedAt}'::timestamptz),
  ('a3-pg-rls-b', '${SCOPE_B.organization_id}', '${SCOPE_B.tenant_id}', '${SCOPE_B.workspace_id}', '${SCOPE_B.project_id}', '${SCOPE_B.environment_id}', '${PROBE_SOURCE}', 'sandbox_verified', 'postgres_live', FALSE, FALSE, FALSE, 'sha256:${"b".repeat(64)}', '{}'::jsonb, '${observedAt}'::timestamptz, '${observedAt}'::timestamptz)
ON CONFLICT (organization_id, tenant_id, workspace_id, project_id, environment_id, id) DO NOTHING;`;
}

function metadataSql() {
  return `
SELECT json_build_object(
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num')::integer,
  'rls_enabled', c.relrowsecurity,
  'rls_forced', c.relforcerowsecurity,
  'policy_count', (SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = 'self_host_sandbox_calibrations'),
  'role_superuser', r.rolsuper,
  'role_bypassrls', r.rolbypassrls
)::text
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles r ON r.rolname = '${PROBE_ROLE}'
WHERE n.nspname = 'public' AND c.relname = 'self_host_sandbox_calibrations';`;
}

function scopeSettingsSql() {
  return `
SET app.a3_organization_id = '${SCOPE_A.organization_id}';
SET app.a3_tenant_id = '${SCOPE_A.tenant_id}';
SET app.a3_workspace_id = '${SCOPE_A.workspace_id}';
SET app.a3_project_id = '${SCOPE_A.project_id}';
SET app.a3_environment_id = '${SCOPE_A.environment_id}';`;
}

function scopedReadSql() {
  return `
SET ROLE ${PROBE_ROLE};
${scopeSettingsSql()}
SELECT json_build_object(
  'visible_total', count(*),
  'same_scope_read_count', count(*) FILTER (WHERE organization_id = '${SCOPE_A.organization_id}'),
  'cross_scope_read_count', count(*) FILTER (WHERE organization_id = '${SCOPE_B.organization_id}')
)::text
FROM self_host_sandbox_calibrations;
RESET ROLE;`;
}

function missingScopeReadSql() {
  return `
SET ROLE ${PROBE_ROLE};
SELECT json_build_object('visible_total', count(*))::text FROM self_host_sandbox_calibrations;
RESET ROLE;`;
}

function sameScopeWriteSql() {
  return `
SET ROLE ${PROBE_ROLE};
${scopeSettingsSql()}
INSERT INTO self_host_sandbox_calibrations (
  id, organization_id, tenant_id, workspace_id, project_id, environment_id,
  source, status, evidence_level, production_verified,
  deployment_acceptance_mutated, a2_decision_recomputed, probe_payload_sha256,
  payload, observed_at, created_at
) VALUES (
  'a3-pg-rls-write-allowed', '${SCOPE_A.organization_id}', '${SCOPE_A.tenant_id}', '${SCOPE_A.workspace_id}', '${SCOPE_A.project_id}', '${SCOPE_A.environment_id}',
  '${PROBE_SOURCE}', 'sandbox_verified', 'postgres_live', FALSE, FALSE, FALSE,
  'sha256:${"c".repeat(64)}', '{}'::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
) RETURNING id;
RESET ROLE;`;
}

function crossScopeWriteSql() {
  return `
SET ROLE ${PROBE_ROLE};
${scopeSettingsSql()}
INSERT INTO self_host_sandbox_calibrations (
  id, organization_id, tenant_id, workspace_id, project_id, environment_id,
  source, status, evidence_level, production_verified,
  deployment_acceptance_mutated, a2_decision_recomputed, probe_payload_sha256,
  payload, observed_at, created_at
) VALUES (
  'a3-pg-rls-write-denied', '${SCOPE_B.organization_id}', '${SCOPE_B.tenant_id}', '${SCOPE_B.workspace_id}', '${SCOPE_B.project_id}', '${SCOPE_B.environment_id}',
  '${PROBE_SOURCE}', 'sandbox_verified', 'postgres_live', FALSE, FALSE, FALSE,
  'sha256:${"d".repeat(64)}', '{}'::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);`;
}

function cleanupSql() {
  return `
RESET ROLE;
DELETE FROM self_host_sandbox_calibrations WHERE source = '${PROBE_SOURCE}';
DROP OWNED BY ${PROBE_ROLE};
REVOKE ${PROBE_ROLE} FROM CURRENT_USER;
DROP ROLE IF EXISTS ${PROBE_ROLE};`;
}

function parseSingleJson(result, phase) {
  const lines = String(result.stdout || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  try {
    return JSON.parse(lines.at(-1) || "");
  } catch {
    throw new A3PostgresRlsProbeError("postgres_output_invalid", `PostgreSQL phase ${phase} returned invalid JSON.`, [{ phase }]);
  }
}

function classifyPsqlStderr(value = "") {
  if (/row-level security/i.test(value)) return "row_level_security_denied";
  if (/password authentication|no password supplied/i.test(value)) return "authentication_failed";
  if (/permission denied|must be superuser|must have createrole/i.test(value)) return "permission_denied";
  if (/could not connect|connection refused|no response/i.test(value)) return "connection_failed";
  if (!value) return "empty";
  return "postgres_error";
}

function containsSensitiveValue(value) {
  const serialized = JSON.stringify(value);
  return LEAK_PATTERNS.some((pattern) => pattern.test(serialized));
}

function normalizeTargetClass(value) {
  const targetClass = String(value || "local_ephemeral_postgres");
  if (!["local_ephemeral_postgres", "staging_postgres", "customer_vpc_postgres"].includes(targetClass)) {
    throw new A3PostgresRlsProbeError("target_class_invalid", "Unsupported PostgreSQL target class.");
  }
  return targetClass;
}

function safeServerVersion(value) {
  const match = String(value || "").match(/^[0-9]+(?:\.[0-9]+){0,2}/);
  return match?.[0] || "unknown";
}

function isoTimestamp(value) {
  if (!isIsoTimestamp(value)) throw new A3PostgresRlsProbeError("observed_at_invalid", "observed_at must be an ISO timestamp.");
  return value;
}

function isIsoTimestamp(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) && /(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(value);
}

function integer(value) {
  const result = Number(value);
  return Number.isInteger(result) ? result : 0;
}

function positiveInteger(value, fallback) {
  const result = Number(value ?? fallback);
  return Number.isInteger(result) && result > 0 ? result : fallback;
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sameStringArray(value, expected) {
  return Array.isArray(value)
    && value.length === expected.length
    && expected.every((item, index) => value[index] === item);
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}
