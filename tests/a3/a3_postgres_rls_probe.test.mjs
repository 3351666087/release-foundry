import assert from "node:assert/strict";
import { test } from "node:test";

import {
  A3PostgresRlsProbeError,
  getSelfHostSandboxPostgresMigration,
  runA3PostgresRlsQualification,
  validatePostgresRlsQualification
} from "../../services/report/a3_postgres_rls_probe.mjs";
import { parsePostgresRlsProbeArgs } from "../../services/report/a3_postgres_rls_probe_cli.mjs";
import { buildA3SqlMigrationPlan } from "../../services/report/a3_sql_migrations.mjs";

const observedAt = "2026-07-13T10:00:00.000Z";

test("migration 019 remains stable and migration 020 adds five-level forced PostgreSQL RLS", () => {
  const migration = getSelfHostSandboxPostgresMigration();
  const postgresPlan = buildA3SqlMigrationPlan({ dialect: "postgres" });
  const sqlitePlan = buildA3SqlMigrationPlan({ dialect: "sqlite" });
  const migration019 = postgresPlan.statements.find((item) => item.id === "019_self_host_sandbox_calibrations");
  const migration020 = postgresPlan.statements.find((item) => item.id === "020_self_host_sandbox_scope_hardening");
  const sqlite020 = sqlitePlan.statements.find((item) => item.id === migration020.id);

  assert.match(migration019.sql, /id TEXT PRIMARY KEY/);
  assert.doesNotMatch(migration019.sql, /ROW LEVEL SECURITY|CREATE POLICY/);
  assert.match(migration020.sql, /PRIMARY KEY \(organization_id, tenant_id, workspace_id, project_id, environment_id, id\)/);
  assert.match(migration020.sql, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration020.sql, /FORCE ROW LEVEL SECURITY/);
  assert.match(migration020.sql, /CREATE POLICY self_host_sandbox_scope_isolation/);
  for (const field of ["organization", "tenant", "workspace", "project", "environment"]) {
    assert.match(migration020.sql, new RegExp(`current_setting\\('app\\.a3_${field}_id'`));
  }
  assert.deepEqual(migration.migration_ids, ["019_self_host_sandbox_calibrations", "020_self_host_sandbox_scope_hardening"]);
  assert.match(sqlite020.sql, /idx_self_host_sandbox_scope_identity/);
  assert.doesNotMatch(sqlite020.sql, /ROW LEVEL SECURITY|CREATE POLICY|current_setting/);
  assert.equal(buildA3SqlMigrationPlan({ dialect: "postgres" }).tenancy_columns.includes("environment_id"), true);
});

test("PostgreSQL qualification applies migration twice and proves allow/deny behavior", async () => {
  const phases = [];
  let cleanupCompleted = false;
  const qualification = await runA3PostgresRlsQualification({
    observedAt,
    executeSql: async ({ phase, sql }) => {
      phases.push({ phase, sql });
      if (phase === "metadata_readback") return success(JSON.stringify({
        server_version: "17.9",
        server_version_num: 170009,
        rls_enabled: true,
        rls_forced: true,
        policy_count: 1,
        role_superuser: false,
        role_bypassrls: false
      }));
      if (phase === "scoped_read") return success(JSON.stringify({
        visible_total: 1,
        same_scope_read_count: 1,
        cross_scope_read_count: 0
      }));
      if (phase === "missing_scope_read") return success(JSON.stringify({ visible_total: 0 }));
      if (phase === "same_scope_write") return success("a3-pg-rls-write-allowed");
      if (phase === "cross_scope_write") return { exitCode: 1, stdout: "", stderr: "new row violates row-level security policy" };
      return success("");
    },
    onCleanup: (value) => { cleanupCompleted = value; }
  });

  assert.deepEqual(phases.map((item) => item.phase), [
    "migration_apply_1",
    "migration_apply_2",
    "probe_setup",
    "metadata_readback",
    "scoped_read",
    "missing_scope_read",
    "same_scope_write",
    "cross_scope_write",
    "cleanup"
  ]);
  assert.equal(phases[0].sql, phases[1].sql);
  assert.equal(qualification.status, "postgres_rls_verified");
  assert.equal(qualification.database.migration_apply_count, 2);
  assert.equal(qualification.database.migration_statement_count, 2);
  assert.deepEqual(qualification.database.migration_ids, ["019_self_host_sandbox_calibrations", "020_self_host_sandbox_scope_hardening"]);
  assert.equal(qualification.database.rls_forced, true);
  assert.equal(qualification.tenant_isolation.same_scope_read_count, 1);
  assert.equal(qualification.tenant_isolation.cross_scope_read_count, 0);
  assert.equal(qualification.tenant_isolation.missing_scope_read_count, 0);
  assert.equal(qualification.tenant_isolation.same_scope_write_allowed, true);
  assert.equal(qualification.tenant_isolation.cross_scope_write_denied, true);
  assert.equal(qualification.authority_boundary.production_verified, false);
  assert.equal(qualification.authority_boundary.a2_decision_recomputed, false);
  assert.equal(qualification.safety.cleanup_completed, true);
  assert.equal(cleanupCompleted, true);
  assert.doesNotMatch(JSON.stringify(qualification), /password|postgresql:\/\/|127\.0\.0\.1|[A-Za-z]:\\/i);
});

test("PostgreSQL qualification fails closed on RLS bypass or production overclaim", async () => {
  const qualification = await runA3PostgresRlsQualification({
    observedAt,
    executeSql: fakeSuccessfulExecutor()
  });
  const bypass = structuredClone(qualification);
  bypass.database.runtime_role_nobypassrls = false;
  assert.throws(
    () => validatePostgresRlsQualification(bypass),
    (error) => error instanceof A3PostgresRlsProbeError && error.code === "postgres_rls_qualification_invalid"
  );

  const overclaim = structuredClone(qualification);
  overclaim.authority_boundary.production_verified = true;
  assert.throws(() => validatePostgresRlsQualification(overclaim), A3PostgresRlsProbeError);

  const expandedMigrationChain = structuredClone(qualification);
  expandedMigrationChain.database.migration_ids.push("019_self_host_sandbox_calibrations");
  assert.throws(() => validatePostgresRlsQualification(expandedMigrationChain), A3PostgresRlsProbeError);

  const reorderedScope = structuredClone(qualification);
  reorderedScope.tenant_isolation.scope_levels.reverse();
  assert.throws(() => validatePostgresRlsQualification(reorderedScope), A3PostgresRlsProbeError);
});

test("PostgreSQL probe CLI accepts no password or DSN command-line argument", () => {
  assert.deepEqual(parsePostgresRlsProbeArgs([
    "--psql", "psql",
    "--host", "localhost",
    "--port", "55432",
    "--user", "postgres",
    "--database", "postgres",
    "--target-class", "local_ephemeral_postgres",
    "--observed-at", observedAt,
    "--output", "qualification.json"
  ]), {
    connection: { host: "localhost", port: "55432", user: "postgres", database: "postgres" },
    psqlCommand: "psql",
    targetClass: "local_ephemeral_postgres",
    observedAt,
    output: "qualification.json"
  });
  assert.throws(() => parsePostgresRlsProbeArgs(["--password", "unsafe"]), /Unknown argument/);
  assert.throws(() => parsePostgresRlsProbeArgs(["--dsn", "unsafe"]), /Unknown argument/);
});

test("live PostgreSQL 17 qualification is opt-in and returns only sanitized evidence", {
  skip: process.env.A3_POSTGRES_LIVE !== "1"
}, async () => {
  const qualification = await runA3PostgresRlsQualification({
    observedAt,
    psqlCommand: process.env.A3_PSQL_BIN,
    connection: {
      host: process.env.A3_POSTGRES_TEST_HOST,
      port: process.env.A3_POSTGRES_TEST_PORT,
      user: process.env.A3_POSTGRES_TEST_USER,
      database: process.env.A3_POSTGRES_TEST_DATABASE,
      password: process.env.A3_POSTGRES_TEST_PASSWORD || "",
      sslmode: process.env.A3_POSTGRES_TEST_SSLMODE || "disable"
    }
  });
  assert.equal(qualification.database.server_version.startsWith("17."), true);
  assert.equal(qualification.database.rls_enabled, true);
  assert.equal(qualification.database.rls_forced, true);
  assert.equal(qualification.tenant_isolation.cross_scope_write_denied, true);
  assert.equal(qualification.authority_boundary.production_verified, false);
});

function fakeSuccessfulExecutor() {
  return async ({ phase }) => {
    if (phase === "metadata_readback") return success(JSON.stringify({
      server_version: "17.9",
      server_version_num: 170009,
      rls_enabled: true,
      rls_forced: true,
      policy_count: 1,
      role_superuser: false,
      role_bypassrls: false
    }));
    if (phase === "scoped_read") return success(JSON.stringify({
      visible_total: 1,
      same_scope_read_count: 1,
      cross_scope_read_count: 0
    }));
    if (phase === "missing_scope_read") return success(JSON.stringify({ visible_total: 0 }));
    if (phase === "same_scope_write") return success("a3-pg-rls-write-allowed");
    if (phase === "cross_scope_write") return { exitCode: 1, stdout: "", stderr: "row-level security policy" };
    return success("");
  };
}

function success(stdout) {
  return { exitCode: 0, stdout, stderr: "" };
}
