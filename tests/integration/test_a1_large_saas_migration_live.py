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


def _psql(dsn: str, sql: str | None = None, *, file: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [os.environ.get("A1_PSQL_BIN", "psql"), dsn, "-v", "ON_ERROR_STOP=1"]
    if file is not None:
        command.extend(["-f", str(file)])
    else:
        command.extend(["-c", sql or ""])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)


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
      VALUES ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000103', 'run_count', 2, 'runs', 'run', 'run-live-a1', '2026-07-08T00:00:00Z', '2026-07-09T00:00:00Z')
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
        'run_count', '2026-07-08T00:00:00Z', '2026-07-10T00:00:00Z'
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
    command = [os.environ.get("A1_PSQL_BIN", "psql"), dsn, "-v", "ON_ERROR_STOP=1", "-c", conflict_sql]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    assert result.returncode != 0
    assert "idempotency key conflict" in result.stderr
