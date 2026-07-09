from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services/api/migrations/001_a1_large_saas_foundation.sql"


def _dsn() -> str:
    value = os.environ.get("A1_POSTGRES_TEST_DSN", "").strip()
    if not value:
        pytest.skip("set A1_POSTGRES_TEST_DSN to run the live Postgres migration smoke")
    return value


def _psql(
    dsn: str,
    sql: str | None = None,
    *,
    file: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    docker_container = os.environ.get("A1_PSQL_DOCKER_CONTAINER", "").strip()
    if docker_container:
        command = ["docker", "exec", "-i", docker_container, "psql", "-U", "ashr", "-d", "ashr", "-v", "ON_ERROR_STOP=1"]
        input_sql = file.read_text(encoding="utf-8-sig") if file is not None else (sql or "")
        command.extend(["-f", "-"])
        return subprocess.run(command, cwd=ROOT, input=input_sql, text=True, capture_output=True, check=check)

    command = [os.environ.get("A1_PSQL_BIN", "psql"), dsn, "-v", "ON_ERROR_STOP=1"]
    if file is not None:
        command.extend(["-f", str(file)])
    else:
        command.extend(["-c", sql or ""])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=check)


def test_a1_foundation_migration_applies_and_helpers_execute_on_postgres() -> None:
    dsn = _dsn()
    _psql(dsn, file=MIGRATION)
    _psql(dsn, file=MIGRATION)

    smoke_sql = """
    INSERT INTO organizations (id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000101', 'org-live-a1', 'Org Live A1')
      ON CONFLICT DO NOTHING;
    INSERT INTO workspaces (id, organization_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000101', 'ws-live-a1', 'Workspace Live A1')
      ON CONFLICT DO NOTHING;
    INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102', 'proj-live-a1', 'Project Live A1')
      ON CONFLICT DO NOTHING;
    SELECT idempotency_key, fingerprint
      FROM ensure_idempotency_fingerprint(
        '00000000-0000-0000-0000-000000000101',
        '00000000-0000-0000-0000-000000000103',
        'idem-live-a1', 'POST', '/v1/runs', 'fp-live-a1'
      );
    INSERT INTO usage_ledger (id, organization_id, project_id, meter, quantity, unit, source_type, source_id, period_start, period_end)
      VALUES ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000103', 'runs', 2, 'runs', 'run', 'run-live-a1', '2026-07-08T00:00:00Z', '2026-07-09T00:00:00Z')
      ON CONFLICT DO NOTHING;
    INSERT INTO jobs (id, organization_id, project_id, job_type, status, priority, dedupe_key, payload)
      VALUES ('00000000-0000-0000-0000-000000000106', '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000103', 'run.dispatch', 'queued', 10, 'job-live-a1', '{"run_id":"00000000-0000-0000-0000-000000000103"}'::jsonb)
      ON CONFLICT DO NOTHING;
    INSERT INTO jobs (id, organization_id, project_id, job_type, status, priority, dedupe_key, payload)
      VALUES ('00000000-0000-0000-0000-000000000107', '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000103', 'run.dispatch', 'queued', 99, 'job-live-a1', '{}'::jsonb)
      ON CONFLICT DO NOTHING;
    SELECT count(*) AS deduped_jobs
      FROM jobs
     WHERE organization_id = '00000000-0000-0000-0000-000000000101'
       AND project_id = '00000000-0000-0000-0000-000000000103'
       AND job_type = 'run.dispatch'
       AND dedupe_key = 'job-live-a1';
    SELECT total_quantity, ledger_entries
      FROM rollup_usage(
        '00000000-0000-0000-0000-000000000101',
        '00000000-0000-0000-0000-000000000103',
        'runs', '2026-07-08T00:00:00Z', '2026-07-10T00:00:00Z'
      );
    INSERT INTO audit_log (id, organization_id, project_id, actor_type, action, resource_type, resource_id, entry_hash)
      VALUES ('00000000-0000-0000-0000-000000000105', '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000103', 'system', 'migration.smoke', 'project', '00000000-0000-0000-0000-000000000103', 'hash-live-a1')
      ON CONFLICT DO NOTHING;
    SELECT audit_chain_tail('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000103');
    """
    result = _psql(dsn, smoke_sql)
    assert "idem-live-a1" in result.stdout
    assert "fp-live-a1" in result.stdout
    assert "2.000000" in result.stdout
    assert "deduped_jobs" in result.stdout
    assert "1" in result.stdout
    assert "hash-live-a1" in result.stdout


def test_a1_foundation_forced_rls_denies_cross_tenant_reads_and_writes_live_opt_in() -> None:
    dsn = _dsn()
    _psql(dsn, file=MIGRATION)

    role_sql = """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_rls_auditor_live') THEN
        CREATE ROLE a1_rls_auditor_live NOLOGIN NOSUPERUSER NOBYPASSRLS;
      END IF;
    END $$;
    GRANT a1_rls_auditor_live TO CURRENT_USER;
    GRANT USAGE ON SCHEMA public TO a1_rls_auditor_live;
    GRANT SELECT, INSERT ON organizations, workspaces, projects, usage_ledger, audit_log TO a1_rls_auditor_live;
    """
    role_setup = _psql(dsn, role_sql, check=False)
    if role_setup.returncode != 0:
        pytest.skip(f"live RLS role setup requires CREATE ROLE/GRANT privileges: {role_setup.stderr}")

    setup_sql = """
    INSERT INTO organizations (id, slug, display_name)
      VALUES
        ('00000000-0000-0000-0000-000000000401', 'org-live-a1-rls-a', 'Org Live A1 RLS A'),
        ('00000000-0000-0000-0000-000000000501', 'org-live-a1-rls-b', 'Org Live A1 RLS B')
      ON CONFLICT DO NOTHING;
    INSERT INTO workspaces (id, organization_id, slug, display_name)
      VALUES
        ('00000000-0000-0000-0000-000000000402', '00000000-0000-0000-0000-000000000401', 'ws-live-a1-rls-a', 'Workspace Live A1 RLS A'),
        ('00000000-0000-0000-0000-000000000502', '00000000-0000-0000-0000-000000000501', 'ws-live-a1-rls-b', 'Workspace Live A1 RLS B')
      ON CONFLICT DO NOTHING;
    INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
      VALUES
        ('00000000-0000-0000-0000-000000000403', '00000000-0000-0000-0000-000000000401', '00000000-0000-0000-0000-000000000402', 'proj-live-a1-rls-a', 'Project Live A1 RLS A'),
        ('00000000-0000-0000-0000-000000000503', '00000000-0000-0000-0000-000000000501', '00000000-0000-0000-0000-000000000502', 'proj-live-a1-rls-b', 'Project Live A1 RLS B')
      ON CONFLICT DO NOTHING;
    INSERT INTO usage_ledger (id, organization_id, project_id, meter, quantity, unit, source_type, source_id, period_start, period_end)
      VALUES
        ('00000000-0000-0000-0000-000000000404', '00000000-0000-0000-0000-000000000401', '00000000-0000-0000-0000-000000000403', 'runs', 1, 'runs', 'run', 'rls-a', '2026-07-09T00:00:00Z', '2026-07-10T00:00:00Z'),
        ('00000000-0000-0000-0000-000000000504', '00000000-0000-0000-0000-000000000501', '00000000-0000-0000-0000-000000000503', 'runs', 1, 'runs', 'run', 'rls-b', '2026-07-09T00:00:00Z', '2026-07-10T00:00:00Z')
      ON CONFLICT DO NOTHING;
    INSERT INTO audit_log (id, organization_id, project_id, actor_type, action, resource_type, resource_id, entry_hash)
      VALUES
        ('00000000-0000-0000-0000-000000000405', '00000000-0000-0000-0000-000000000401', '00000000-0000-0000-0000-000000000403', 'system', 'rls.probe', 'project', '00000000-0000-0000-0000-000000000403', 'hash-live-a1-rls-a'),
        ('00000000-0000-0000-0000-000000000505', '00000000-0000-0000-0000-000000000501', '00000000-0000-0000-0000-000000000503', 'system', 'rls.probe', 'project', '00000000-0000-0000-0000-000000000503', 'hash-live-a1-rls-b')
      ON CONFLICT DO NOTHING;
    """
    _psql(dsn, setup_sql)

    read_probe = """
    SET ROLE a1_rls_auditor_live;
    SELECT set_config('app.a1_organization_id', '00000000-0000-0000-0000-000000000401', false);
    SELECT 'organizations_visible_for_a=' || count(*) FROM organizations;
    SELECT 'workspaces_visible_for_a=' || count(*) FROM workspaces;
    SELECT 'usage_visible_for_a=' || count(*) FROM usage_ledger;
    SELECT 'audit_visible_for_a=' || count(*) FROM audit_log;
    SELECT 'org_b_visible_from_a=' || count(*) FROM organizations WHERE id = '00000000-0000-0000-0000-000000000501';
    SELECT 'workspace_b_visible_from_a=' || count(*) FROM workspaces WHERE organization_id = '00000000-0000-0000-0000-000000000501';
    SELECT 'usage_b_visible_from_a=' || count(*) FROM usage_ledger WHERE organization_id = '00000000-0000-0000-0000-000000000501';
    SELECT 'audit_b_visible_from_a=' || count(*) FROM audit_log WHERE organization_id = '00000000-0000-0000-0000-000000000501';
    RESET ROLE;
    """
    reads = _psql(dsn, read_probe)
    assert "organizations_visible_for_a=1" in reads.stdout
    assert "workspaces_visible_for_a=1" in reads.stdout
    assert "usage_visible_for_a=1" in reads.stdout
    assert "audit_visible_for_a=1" in reads.stdout
    assert "org_b_visible_from_a=0" in reads.stdout
    assert "workspace_b_visible_from_a=0" in reads.stdout
    assert "usage_b_visible_from_a=0" in reads.stdout
    assert "audit_b_visible_from_a=0" in reads.stdout

    write_probe = """
    SET ROLE a1_rls_auditor_live;
    SELECT set_config('app.a1_organization_id', '00000000-0000-0000-0000-000000000401', false);
    INSERT INTO organizations (id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000601', 'org-live-a1-rls-denied', 'Org Live A1 RLS Denied');
    """
    denied = _psql(dsn, write_probe, check=False)
    assert denied.returncode != 0
    assert "row-level security" in (denied.stderr + denied.stdout).lower()


def test_a1_foundation_idempotency_conflict_is_live_opt_in() -> None:
    dsn = _dsn()
    _psql(dsn, file=MIGRATION)

    setup_sql = """
    INSERT INTO organizations (id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000201', 'org-live-a1-conflict', 'Org Live A1 Conflict')
      ON CONFLICT DO NOTHING;
    INSERT INTO workspaces (id, organization_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000201', 'ws-live-a1-conflict', 'Workspace Live A1 Conflict')
      ON CONFLICT DO NOTHING;
    INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000203', '00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000202', 'proj-live-a1-conflict', 'Project Live A1 Conflict')
      ON CONFLICT DO NOTHING;
    SELECT idempotency_key
      FROM ensure_idempotency_fingerprint(
        '00000000-0000-0000-0000-000000000201',
        '00000000-0000-0000-0000-000000000203',
        'idem-live-a1-conflict', 'POST', '/v1/runs', 'fp-live-a1-original'
      );
    """
    _psql(dsn, setup_sql)

    conflict_sql = """
    SELECT idempotency_key
      FROM ensure_idempotency_fingerprint(
        '00000000-0000-0000-0000-000000000201',
        '00000000-0000-0000-0000-000000000203',
        'idem-live-a1-conflict', 'POST', '/v1/runs', 'fp-live-a1-different'
      );
    """
    result = _psql(dsn, conflict_sql, check=False)

    assert result.returncode != 0
    assert "idempotency" in result.stderr
    assert "fingerprint conflict" in result.stderr


def test_a1_check_quota_and_insert_usage_allowed_replay_denied_and_audited_live_opt_in() -> None:
    dsn = _dsn()
    _psql(dsn, file=MIGRATION)

    setup_sql = """
    INSERT INTO organizations (id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000301', 'org-live-a1-quota', 'Org Live A1 Quota')
      ON CONFLICT DO NOTHING;
    INSERT INTO workspaces (id, organization_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000302', '00000000-0000-0000-0000-000000000301', 'ws-live-a1-quota', 'Workspace Live A1 Quota')
      ON CONFLICT DO NOTHING;
    INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000000303', '00000000-0000-0000-0000-000000000301', '00000000-0000-0000-0000-000000000302', 'proj-live-a1-quota', 'Project Live A1 Quota')
      ON CONFLICT DO NOTHING;
    INSERT INTO quota_policies (id, organization_id, project_id, meter, period, limit_quantity, enforcement_mode, status, effective_from, metadata)
      VALUES ('00000000-0000-0000-0000-000000000304', '00000000-0000-0000-0000-000000000301', '00000000-0000-0000-0000-000000000303', 'runs', 'day', 1, 'hard', 'active', '2026-07-01T00:00:00Z', '{"source":"a1-live-test"}'::jsonb)
      ON CONFLICT (organization_id, project_id, meter, period)
      DO UPDATE SET limit_quantity = EXCLUDED.limit_quantity, enforcement_mode = EXCLUDED.enforcement_mode, status = EXCLUDED.status, effective_from = EXCLUDED.effective_from, metadata = EXCLUDED.metadata;
    INSERT INTO idempotency_keys (id, organization_id, project_id, idempotency_key, request_method, request_path, fingerprint)
      VALUES ('00000000-0000-0000-0000-000000000305', '00000000-0000-0000-0000-000000000301', '00000000-0000-0000-0000-000000000303', 'quota-live-a1-allowed', 'POST', '/v1/runs', 'fp-quota-live-a1-allowed')
      ON CONFLICT (organization_id, project_id, idempotency_key) DO NOTHING;
    """
    _psql(dsn, setup_sql)

    allowed_sql = """
    SELECT allowed, idempotent_replay, operation, meter, quantity::int, denial_reason
      FROM check_quota_and_insert_usage(
        '00000000-0000-0000-0000-000000000301',
        '00000000-0000-0000-0000-000000000303',
        'sdk.submit',
        1,
        '00000000-0000-0000-0000-000000000302',
        NULL,
        '00000000-0000-0000-0000-000000000305',
        'api',
        'run-live-a1-quota-allowed',
        '2026-07-09T00:00:00Z',
        '{"request_id":"req-live-a1-quota-allowed"}'::jsonb,
        '00000000-0000-0000-0000-000000000306'
      );
    SELECT count(*) AS usage_rows_after_allowed
      FROM usage_ledger
     WHERE organization_id = '00000000-0000-0000-0000-000000000301'
       AND project_id = '00000000-0000-0000-0000-000000000303'
       AND operation = 'sdk.submit';
    """
    allowed = _psql(dsn, allowed_sql)
    assert " t " in allowed.stdout
    assert " f " in allowed.stdout
    assert "sdk.submit" in allowed.stdout
    assert "runs" in allowed.stdout
    assert "usage_rows_after_allowed" in allowed.stdout
    assert "1" in allowed.stdout

    replay_sql = """
    SELECT allowed, idempotent_replay, operation, meter, quantity::int, denial_reason
      FROM check_quota_and_insert_usage(
        '00000000-0000-0000-0000-000000000301',
        '00000000-0000-0000-0000-000000000303',
        'sdk.submit',
        1,
        '00000000-0000-0000-0000-000000000302',
        NULL,
        '00000000-0000-0000-0000-000000000305',
        'api',
        'run-live-a1-quota-allowed',
        '2026-07-09T00:00:00Z',
        '{"request_id":"req-live-a1-quota-replay"}'::jsonb,
        '00000000-0000-0000-0000-000000000307'
      );
    SELECT count(*) AS usage_rows_after_replay
      FROM usage_ledger
     WHERE organization_id = '00000000-0000-0000-0000-000000000301'
       AND project_id = '00000000-0000-0000-0000-000000000303'
       AND operation = 'sdk.submit';
    """
    replay = _psql(dsn, replay_sql)
    assert " t " in replay.stdout
    assert "usage_rows_after_replay" in replay.stdout
    assert "1" in replay.stdout

    denied_sql = """
    SELECT allowed, idempotent_replay, operation, meter, quantity::int, denial_reason
      FROM check_quota_and_insert_usage(
        '00000000-0000-0000-0000-000000000301',
        '00000000-0000-0000-0000-000000000303',
        'sdk.submit',
        1,
        '00000000-0000-0000-0000-000000000302',
        NULL,
        NULL,
        'api',
        'run-live-a1-quota-denied',
        '2026-07-09T00:00:00Z',
        '{"request_id":"req-live-a1-quota-denied"}'::jsonb,
        '00000000-0000-0000-0000-000000000308'
      );
    SELECT action, payload->>'operation' AS operation, payload->>'meter' AS meter
      FROM audit_log
     WHERE organization_id = '00000000-0000-0000-0000-000000000301'
       AND project_id = '00000000-0000-0000-0000-000000000303'
       AND action = 'quota.denied';
    SELECT count(*) AS usage_rows_after_denied
      FROM usage_ledger
     WHERE organization_id = '00000000-0000-0000-0000-000000000301'
       AND project_id = '00000000-0000-0000-0000-000000000303'
       AND operation = 'sdk.submit';
    """
    denied = _psql(dsn, denied_sql)
    assert " f " in denied.stdout
    assert "quota_exceeded" in denied.stdout
    assert "quota.denied" in denied.stdout
    assert "sdk.submit" in denied.stdout
    assert "runs" in denied.stdout
    assert "usage_rows_after_denied" in denied.stdout
    assert "1" in denied.stdout
