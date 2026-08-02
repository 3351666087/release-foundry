from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
GO_POSTGRES = ROOT / "packages" / "go" / "releasefoundry" / "postgres.go"
MIGRATION = ROOT / "services" / "api" / "migrations" / "004_a1_billing_webhook_fail_closed.sql"
MIGRATION_SCRIPT = ROOT / "infra" / "docker" / "postgres-migrate.sh"
COMPOSE = ROOT / "infra" / "docker" / "docker-compose.self-host.yml"


def _normalized(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip().lower()


def test_postgres_webhook_rejects_before_every_mutation_path() -> None:
    source = GO_POSTGRES.read_text(encoding="utf-8")
    start = source.index("func (repository *PostgresRepository) IngestBillingWebhook")
    end = source.index("func (repository *PostgresRepository) BillingLedger", start)
    method = source[start:end]

    reject_at = method.index("return rejectedBillingWebhookEnvelope(event), nil")
    assert method.index("event.Verified = false") < reject_at
    assert method.index("provider_specific_verification_required") < reject_at
    for mutation in (
        "BeginTx(",
        "loadIdempotentBillingWebhookReplay(",
        "requireProject(",
        "ensurePostgresBillingSaaSScope(",
        "ingestPostgresBillingProviderEvent(",
        "appendPostgresMutationEvidence(",
        "insertIdempotentBillingWebhookResponse(",
        "tx.Commit(",
    ):
        assert reject_at < method.index(mutation), mutation


def test_postgres_provider_event_helper_rejects_before_query() -> None:
    source = GO_POSTGRES.read_text(encoding="utf-8")
    start = source.index("func ingestPostgresBillingProviderEvent")
    end = source.index("func scanPostgresBillingLedgerEvent", start)
    helper = source[start:end]

    guard_at = helper.index("if !event.Verified")
    query_at = helper.index("tx.QueryRowContext")
    assert guard_at < query_at
    assert "requires trusted verification" in helper[guard_at:query_at]


def test_database_admission_trigger_rejects_unverified_provider_rows() -> None:
    sql = _normalized(MIGRATION)

    assert "if new.signature_verified is not true then" in sql
    assert "unverified billing provider event rejected before persistence" in sql
    assert (
        "create trigger billing_provider_events_require_verified_signature "
        "before insert or update of signature_verified on billing_provider_events"
    ) in sql
    assert "for each row execute function releasefoundry_reject_unverified_billing_provider_event()" in sql


def test_commercial_migrator_includes_round47_fail_closed_migration() -> None:
    script = MIGRATION_SCRIPT.read_text(encoding="utf-8")

    assert "-name '*.sql'" in script
    assert "sort" in script
    assert 'apply_migration "$migration_path"' in script
    assert "billing_provider_events_require_verified_signature" in script
    assert MIGRATION.name > "003_a1_china_mainland_payments.sql"


@pytest.mark.skipif(
    os.environ.get("RELEASEFOUNDRY_RUN_PAYMENT_DB_SECURITY_SMOKE") != "1",
    reason="set RELEASEFOUNDRY_RUN_PAYMENT_DB_SECURITY_SMOKE=1 for disposable Postgres proof",
)
@pytest.mark.docker
def test_unverified_provider_function_has_database_level_zero_side_effects() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is unavailable for the opt-in payment smoke")
    project = f"releasefoundry-round47-money-{uuid.uuid4().hex[:8]}"
    env = os.environ.copy()
    env.setdefault("RELEASEFOUNDRY_POSTGRES_AUTH_SECRET", "round47-postgres-local-only")
    env.setdefault("RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY", "round47minio")
    env.setdefault("RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY", "round47-minio-local-only-secret")
    base = [
        docker,
        "compose",
        "--project-name",
        project,
        "-f",
        str(COMPOSE),
        "--profile",
        "commercial",
    ]

    def run(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*base, *args],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )

    org_id = "10000000-0000-4000-8000-000000000047"
    workspace_id = "20000000-0000-4000-8000-000000000047"
    project_id = "30000000-0000-4000-8000-000000000047"
    scope_sql = f"""
INSERT INTO organizations (id, slug, display_name) VALUES ('{org_id}', 'round47-org', 'Round 47');
INSERT INTO workspaces (id, organization_id, slug, display_name)
VALUES ('{workspace_id}', '{org_id}', 'round47-workspace', 'Round 47');
INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
VALUES ('{project_id}', '{org_id}', '{workspace_id}', 'round47-project', 'Round 47');
"""
    rejected_sql = f"""
SELECT * FROM ingest_billing_provider_event(
  '{org_id}'::uuid,
  '{project_id}'::uuid,
  'wechat_pay',
  'test',
  'evt_round47_unverified',
  'wechat_pay.transaction.success',
  repeat('a', 64),
  false,
  'customer_public_ref',
  NULL,
  1,
  'cny',
  0,
  '{{"raw_payload_included":false}}'::jsonb
);
"""
    counts_sql = f"""
SELECT concat_ws(
  ',',
  (SELECT COUNT(*) FROM billing_provider_events WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM billing_ledger_events WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM china_payment_orders WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM china_payment_provider_notifications WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM china_payment_refunds WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM china_payment_mutation_events WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM usage_ledger WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM quota_policies WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM audit_log WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM idempotency_keys WHERE organization_id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM releasefoundry_quota_ledger WHERE tenant_id = '{org_id}'),
  (SELECT COUNT(*) FROM releasefoundry_audit_events WHERE tenant_id = '{org_id}'),
  (SELECT COUNT(*) FROM releasefoundry_idempotency_ledger WHERE tenant_id = '{org_id}'),
  (SELECT COUNT(*) FROM organizations WHERE id = '{org_id}'::uuid),
  (SELECT COUNT(*) FROM projects WHERE id = '{project_id}'::uuid)
);
"""

    try:
        migrate = run(
            [
                "up",
                "--abort-on-container-exit",
                "--exit-code-from",
                "postgres-migrate",
                "postgres-migrate",
            ],
            timeout=300,
        )
        assert migrate.returncode == 0, migrate.stdout[-12000:]

        scope = run(
            ["exec", "-T", "postgres", "psql", "-U", "releasefoundry", "-d", "releasefoundry", "-v", "ON_ERROR_STOP=1", "-c", scope_sql]
        )
        assert scope.returncode == 0, scope.stdout

        rejected = run(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "releasefoundry",
                "-d",
                "releasefoundry",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                rejected_sql,
            ]
        )
        assert rejected.returncode != 0
        assert "unverified billing provider event rejected before persistence" in rejected.stdout

        counts = run(
            ["exec", "-T", "postgres", "psql", "-U", "releasefoundry", "-d", "releasefoundry", "-At", "-c", counts_sql]
        )
        assert counts.returncode == 0, counts.stdout
        assert counts.stdout.strip() == "0,0,0,0,0,0,0,0,0,0,0,0,0,1,1"
    finally:
        run(["down", "--volumes", "--remove-orphans"], timeout=120)
