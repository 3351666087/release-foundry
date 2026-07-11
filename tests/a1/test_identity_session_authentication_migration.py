from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "011_a1_identity_session_authentication.sql"
)


def _sql() -> str:
    return re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8")).lower()


def test_authentication_function_is_digest_only_and_privilege_narrow() -> None:
    sql = _sql()
    assert "a1_authenticate_identity_session_digest( p_session_digest text )" in sql
    assert "security definer" in sql
    assert "set search_path = pg_catalog, public" in sql
    assert "a1_assert_role_nobypassrls(session_user)" in sql
    assert "revoke all on function a1_authenticate_identity_session_digest(text) from public" in sql
    assert "grant execute on function a1_authenticate_identity_session_digest(text) to a1_runtime" in sql
    signature = sql.split("returns table", 1)[0]
    assert "token" not in signature
    assert "principal_id" not in signature
    assert "organization_id" not in signature
    assert "project_id" not in signature


def test_authentication_function_revalidates_current_identity_state() -> None:
    sql = _sql()
    required = [
        "a1_identity_digest_valid(p_session_digest)",
        "identity_session.session_digest = p_session_digest",
        "identity_session.status = 'active'",
        "identity_session.expires_at > clock_timestamp()",
        "principal.status = 'active'",
        "credential.id = identity_session.credential_id",
        "credential.principal_id = identity_session.principal_id",
        "credential.status = 'active'",
        "credential.login_enabled",
        "organization_membership.status = 'active'",
        "project_membership.status = 'active'",
        "project_membership.organization_membership_id = organization_membership.id",
        "identity_session.organization_id is null",
        "identity_session.project_id is null",
        "identity_session.organization_id is not null",
        "identity_session.project_id is not null",
    ]
    for fragment in required:
        assert fragment in sql
