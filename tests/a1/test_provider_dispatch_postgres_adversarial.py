from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "019_a1_provider_dispatch_coordination.sql"
)
POSTGRES_REPOSITORY = (
    ROOT / "packages" / "go" / "releasefoundry" / "provider_dispatch_postgres.go"
)
POSTGRES_TESTS = (
    ROOT / "packages" / "go" / "releasefoundry" / "provider_dispatch_postgres_test.go"
)


def _normalized(path: Path) -> str:
    assert path.is_file(), f"missing provider-dispatch artifact: {path}"
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()


def _method_body(source: str, method: str) -> str:
    marker = f"func (repository *PostgresRepository) {method}("
    start = source.find(marker)
    assert start >= 0, f"PostgresRepository.{method} is missing"
    next_method = source.find(
        "func (repository *PostgresRepository) ", start + len(marker)
    )
    return source[start : next_method if next_method >= 0 else len(source)]


def _run_go_provider_dispatch_tests() -> subprocess.CompletedProcess[str]:
    go = shutil.which("go")
    if go is None:
        pytest.skip("Go is unavailable for the provider-dispatch regression suite")
    return subprocess.run(
        [
            go,
            "test",
            "./...",
            "-run",
            "ProviderDispatch",
            "-count=1",
        ],
        cwd=ROOT / "packages" / "go" / "releasefoundry",
        text=True,
        capture_output=True,
        check=False,
    )


def test_fingerprint_conflict_is_scoped_and_covered_by_repository_tests() -> None:
    source = _normalized(POSTGRES_REPOSITORY)
    tests = _normalized(POSTGRES_TESTS)
    submit = _method_body(source, "SubmitProviderDispatch")

    assert "requestFingerprint, err := fingerprint(cloneMap(request))" in submit
    assert "ON CONFLICT (tenant_id, project_id, dispatch_id) DO NOTHING" in submit
    assert (
        "dispatch.RequestFingerprint != requestFingerprint "
        "|| dispatch.Provider != provider || dispatch.Operation != operation"
    ) in submit
    assert "ProviderDispatchConflictError" in submit
    assert "TestSubmitProviderDispatchFingerprintConflict" in tests


def test_stale_fence_cannot_mutate_a_reclaimed_dispatch() -> None:
    source = _normalized(POSTGRES_REPOSITORY)
    tests = _normalized(POSTGRES_TESTS)

    for method in (
        "HeartbeatProviderDispatch",
        "CompleteProviderDispatch",
        "MarkProviderDispatchIndeterminate",
    ):
        body = _method_body(source, method)
        assert re.search(
            r"lease_owner_id=\$4 AND fencing_token=\$\d+", body
        ), (
            f"{method} must bind both lease owner and monotonic fencing token"
        )
        assert re.search(r"lease_expires_at>\$\d+", body), (
            f"{method} must reject an expired lease even when its token matches"
        )

    assert "fencing_token=fencing_token+1" in source
    assert "TestStaleProviderDispatchFenceCannotHeartbeat" in tests


def test_terminal_proof_is_bound_to_stream_observed_under_active_fence() -> None:
    migration = _normalized(MIGRATION).lower()
    source = _normalized(POSTGRES_REPOSITORY)
    complete = _method_body(source, "CompleteProviderDispatch").lower()

    assert "terminal_proof_sha256" in migration
    assert "terminal_response_sha256" in migration
    assert "stream_observed" in migration, (
        "terminal completion needs persisted proof that provider output was observed"
    )
    assert "stream_observed_fencing_token" in migration, (
        "stream observation must be bound to the lease that observed it"
    )
    assert "stream_observed_fencing_token" in complete
    assert "terminal_proof_sha256" in complete


def test_indeterminate_reconciliation_is_single_winner_and_stream_safe() -> None:
    migration = _normalized(MIGRATION).lower()
    source = _normalized(POSTGRES_REPOSITORY)
    claim = _method_body(source, "claimProviderDispatch")
    reconcile_claim = _method_body(
        source, "ClaimProviderDispatchReconciliationContext"
    )
    mark = _method_body(source, "MarkProviderDispatchIndeterminate").lower()

    assert "ProviderDispatchIndeterminate" in reconcile_claim
    assert "ProviderDispatchReconciling" in reconcile_claim
    assert "FOR UPDATE SKIP LOCKED" in claim
    assert "fencing_token=fencing_token+1" in claim
    assert re.search(
        r"reconciliation_attempts=reconciliation_attempts\s*\+", claim
    )
    assert "stream_observed" in migration
    assert "stream_observed" in mark, (
        "an observed stream must prevent reconciliation from returning work to retry"
    )


def test_rls_is_fail_closed_and_isolates_tenant_and_project() -> None:
    migration = _normalized(MIGRATION).lower()

    assert "enable row level security" in migration
    assert "force row level security" in migration
    assert "app.tenant_id" not in migration
    assert "app.project_id" not in migration
    organization_scope = (
        "tenant_id=nullif("
        "current_setting('app.a1_organization_id',true),'')::uuid"
    )
    project_scope = (
        "project_id=nullif(current_setting('app.a1_project_id',true),'')::uuid"
    )
    assert migration.count(organization_scope) >= 2, (
        "an absent organization context must expose zero rows and reject writes"
    )
    assert migration.count(project_scope) >= 2, (
        "tenant isolation alone does not isolate sibling projects"
    )


def test_existing_go_provider_dispatch_suite_stays_green() -> None:
    result = _run_go_provider_dispatch_tests()
    assert result.returncode == 0, (
        "Go provider-dispatch regression suite failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
