from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "008_a1_unified_identity_account.sql"
)

TABLES = (
    "identity_principals",
    "identity_credentials",
    "identity_organization_memberships",
    "identity_project_memberships",
    "identity_sessions",
    "identity_link_conflicts",
    "identity_account_merges",
    "identity_recovery_challenges",
    "identity_audit_events",
    "identity_outbox",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _table_body(table: str) -> str:
    sql = _normalized()
    start = sql.index(f"create table if not exists {table} (")
    return sql[start : sql.index(");", start)]


def _function_body(function: str, next_marker: str) -> str:
    sql = _normalized()
    start = sql.index(f"create or replace function {function}(")
    return sql[start : sql.index(next_marker, start)]


def test_migration_is_additive_and_ordered_after_oauth_runtime() -> None:
    assert MIGRATION.is_file()
    assert MIGRATION.name > "007_a1_oauth_runtime_store.sql"
    assert _normalized().startswith("-- a1 unified identity and account domain.")
    assert _normalized().strip().endswith("commit;")
    for previous in range(1, 8):
        name = f"{previous:03d}_"
        assert any(
            path.name.startswith(name) for path in MIGRATION.parent.glob("*.sql")
        )


def test_global_principal_is_separate_from_tenant_project_membership() -> None:
    principal = _table_body("identity_principals")
    credentials = _table_body("identity_credentials")
    organization_memberships = _table_body("identity_organization_memberships")
    project_memberships = _table_body("identity_project_memberships")

    assert "organization_id" not in principal
    assert "project_id" not in principal
    assert "organization_id" not in credentials
    assert "project_id" not in credentials
    assert "organization_id uuid not null" in organization_memberships
    assert "principal_id uuid not null" in organization_memberships
    assert "organization_id uuid not null" in project_memberships
    assert "project_id uuid not null" in project_memberships
    assert "principal_id uuid not null" in project_memberships
    assert (
        "unique ( organization_id, project_id, principal_id )"
        in project_memberships
    )
    assert "identity_project_memberships_scope_guard" in _normalized()
    assert (
        "project membership principal does not match organization membership"
        in _normalized()
    )


def test_credentials_cover_domestic_global_and_extensible_providers() -> None:
    credentials = _table_body("identity_credentials")
    sql = _normalized()

    for provider in ("github", "google", "wechat", "qq", "alipay", "phone", "email"):
        assert f"'{provider}'" in credentials
    assert "a1_identity_provider_valid(provider)" in credentials
    assert "provider ~ '^[a-z][a-z0-9_.-]*$'" in sql
    assert "provider not in (" in credentials
    for kind in (
        "federated",
        "phone_otp",
        "email_otp",
        "email_password",
        "passkey",
        "recovery",
        "service",
    ):
        assert f"'{kind}'" in credentials


def test_identity_identifiers_are_digest_only_and_globally_unique() -> None:
    credentials = _table_body("identity_credentials")
    sql = _normalized()

    assert "subject_digest text not null" in credentials
    assert (
        "unique ( provider, provider_environment, subject_digest )"
        in credentials
    )
    assert "a1_identity_digest_valid(subject_digest)" in credentials
    forbidden_columns = {
        "email",
        "email_address",
        "phone",
        "phone_number",
        "mobile",
        "subject",
        "provider_subject",
        "openid",
        "unionid",
        "access_token",
        "refresh_token",
        "id_token",
        "password",
        "password_hash",
        "session_token",
    }
    for table in TABLES:
        columns = {
            match.group(1)
            for match in re.finditer(
                r"(?:^|,)\s*([a-z][a-z0-9_]*)\s+[a-z]",
                _table_body(table),
            )
        }
        assert forbidden_columns.isdisjoint(columns), (table, columns)
    for sensitive_key in (
        "emailaddress",
        "phonenumber",
        "providersubject",
        "openid",
        "unionid",
        "passwordhash",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "sessiontoken",
    ):
        assert f"'{sensitive_key}'" in sql


def test_link_conflict_is_recorded_instead_of_cross_account_rebinding() -> None:
    link = _function_body(
        "a1_link_identity_credential",
        "create or replace function a1_unlink_identity_credential(",
    )

    assert "for update" in link
    assert "incumbent.principal_id <> p_principal_id" in link
    assert "insert into identity_link_conflicts" in link
    assert "'global_identity_already_linked'" in link
    assert "'identity.credential.link_conflict'" in link
    assert "return query select null::uuid, p_principal_id, 'conflict'" in link
    assert "update identity_credentials set principal_id" not in link


def test_email_matching_is_not_an_implicit_account_merge_path() -> None:
    link = _function_body(
        "a1_link_identity_credential",
        "create or replace function a1_unlink_identity_credential(",
    )
    merge = _function_body(
        "a1_merge_identity_accounts",
        "create or replace function a1_claim_identity_outbox(",
    )

    assert "subject_digest = p_subject_digest" in link
    assert "incumbent.principal_id <> p_principal_id" in link
    assert "'global_identity_already_linked'" in link
    assert "email" not in merge
    assert "requires independent approval" in merge
    assert "p_approved_by_principal_id in (" in merge
    assert "merge_request.source_principal_id" in merge
    assert "merge_request.target_principal_id" in merge


def test_unlink_protects_last_login_and_revokes_bound_sessions() -> None:
    unlink = _function_body(
        "a1_unlink_identity_credential",
        "create or replace function a1_issue_identity_session(",
    )

    assert "from identity_principals" in unlink
    assert "for update" in unlink
    assert "active_login_count <= 1" in unlink
    assert "cannot unlink the last active login credential" in unlink
    assert "using errcode = '23514'" in unlink
    assert not re.search(r"select count\(\*\).*?for share", unlink)
    assert "update identity_credentials" in unlink
    assert "secret_ref = null" in unlink
    assert "update identity_sessions" in unlink
    assert "revoke_reason_code = 'credential_unlinked'" in unlink
    assert "'identity.credential.unlinked'" in unlink


def test_account_merge_is_locked_independently_approved_and_audited() -> None:
    merge = _function_body(
        "a1_merge_identity_accounts",
        "create or replace function a1_claim_identity_outbox(",
    )

    assert "for update" in merge
    assert "order by id" in merge
    assert "requires independent approval" in merge
    session_revoke = merge.index("update identity_sessions")
    credential_move = merge.index("update identity_credentials")
    assert session_revoke < credential_move
    assert "credential_id = null" in merge[session_revoke:credential_move]
    assert "update identity_credentials" in merge
    assert "insert into identity_organization_memberships" in merge
    assert "insert into identity_project_memberships" in merge
    assert "on conflict (organization_id, principal_id) do nothing" in merge
    assert (
        "on conflict (organization_id, project_id, principal_id) do nothing"
        in merge
    )
    project_revoke = merge.index(
        "update identity_project_memberships", credential_move
    )
    organization_revoke = merge.index(
        "update identity_organization_memberships", project_revoke
    )
    assert project_revoke < organization_revoke
    assert "revoke_reason_code = 'account_merged'" in merge
    assert "merged_into_principal_id = merge_request.target_principal_id" in merge
    assert "'identity.account.merged'" in merge


def test_recovery_is_single_consume_ttl_context_bound_and_issues_aal2() -> None:
    recovery = _function_body(
        "a1_consume_identity_recovery",
        "create or replace function a1_merge_identity_accounts(",
    )
    table = _table_body("identity_recovery_challenges")

    assert "unique (challenge_digest)" in table
    assert "proof_digest text not null" in table
    assert "expires_at > requested_at" in table
    assert "request_context_digest text not null" in table
    assert "for update" in recovery
    assert "challenge.status <> 'pending'" in recovery
    assert "challenge.expires_at <= clock_timestamp()" in recovery
    assert "challenge.request_context_digest <> p_request_context_digest" in recovery
    assert "challenge.proof_digest <> p_proof_digest" in recovery
    assert "'proof_mismatch'" in recovery
    assert "'request_context_mismatch'" in recovery
    assert "'challenge_expired'" in recovery
    assert recovery.count("return null") >= 3
    assert "attempts = attempts + 1" in recovery
    assert "status = 'consumed'" in recovery
    assert "proof_digest = p_proof_digest" not in recovery
    assert "'aal2'" in recovery
    assert "'identity.recovery.consumed'" in recovery
    assert "'identity.recovery.rejected'" in recovery


def test_sessions_are_digest_only_scoped_expiring_and_membership_gated() -> None:
    sessions = _table_body("identity_sessions")
    issue = _function_body(
        "a1_issue_identity_session",
        "create or replace function a1_consume_identity_recovery(",
    )

    assert "session_digest text not null" in sessions
    assert "rotation_family_digest text not null" in sessions
    assert "unique (session_digest)" in sessions
    assert "expires_at > authenticated_at" in sessions
    assert "organization_id is null and project_id is null" in sessions
    assert "from identity_organization_memberships" in issue
    assert "active organization membership required" in issue
    assert "from identity_project_memberships" in issue
    assert "active project membership required" in issue
    assert "credential.status = 'active'" not in issue
    assert "and status = 'active'" in issue
    assert "and login_enabled" in issue
    assert "'identity.session.issued'" in issue


def test_audit_and_outbox_are_safe_append_only_and_worker_claimable() -> None:
    audit = _table_body("identity_audit_events")
    outbox = _table_body("identity_outbox")
    claim = _function_body("a1_claim_identity_outbox", "drop trigger if exists")
    sql = _normalized()

    assert "event_digest text not null" in audit
    assert "request_digest text" in audit
    assert "payload jsonb not null" in outbox
    assert "a1_identity_public_metadata(payload)" in outbox
    assert "identity_audit_events_append_only" in sql
    assert "before update or delete on identity_audit_events" in sql
    assert "for update skip locked" in claim
    assert "lease_owner_digest" in claim
    assert "make_interval(secs => p_lease_seconds)" in claim
    assert "attempts = target.attempts + 1" in claim


def test_every_identity_table_has_forced_rls_with_split_scope_policies() -> None:
    sql = _normalized()

    for table in TABLES:
        assert f"alter table {table} enable row level security" in sql
        assert f"alter table {table} force row level security" in sql
    assert "identity_principals_self_access" in sql
    assert "identity_credentials_self_access" in sql
    assert "identity_org_memberships_tenant_access" in sql
    assert "identity_project_memberships_tenant_access" in sql
    assert "identity_sessions_self_access" in sql
    assert "identity_link_conflicts_party_access" in sql
    assert "identity_account_merges_party_access" in sql
    assert "identity_recovery_challenges_self_access" in sql
    assert "identity_audit_events_scope_access" in sql
    assert "identity_outbox_scope_access" in sql
    assert sql.count("a1_current_principal_id()") >= 20
    assert sql.count("a1_current_organization_id()") >= 8
    assert sql.count("a1_current_project_id()") >= 6


def test_privileged_identity_mutations_are_not_public() -> None:
    sql = _normalized()
    functions = (
        "a1_link_identity_credential",
        "a1_unlink_identity_credential",
        "a1_issue_identity_session",
        "a1_consume_identity_recovery",
        "a1_merge_identity_accounts",
        "a1_claim_identity_outbox",
    )

    for function in functions:
        start = sql.index(f"create or replace function {function}(")
        body = sql[start : sql.index("$$;", start) + 3]
        assert "security definer" in body
        assert "set search_path = pg_catalog, public" in body
        assert "a1_assert_role_nobypassrls(session_user)" in body
        assert f"revoke all on function {function}(" in sql
        assert f"grant execute on function {function}(" in sql
    assert sql.count("to a1_runtime;") == len(functions)
