from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "026_a1_oauth_first_login_session_handoff.sql"
)


def _sql() -> str:
    assert MIGRATION.is_file(), f"missing migration: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _function_body() -> str:
    sql = _normalized()
    start = sql.index(
        "create or replace function "
        "a1_complete_oauth_first_login_with_refresh("
    )
    return sql[start : sql.index("revoke all on function", start)]


def _operation_table() -> str:
    sql = _normalized()
    start = sql.index(
        "create table if not exists oauth_first_login_operations ("
    )
    return sql[start : sql.index(");", start)]


def test_migration_is_atomic_additive_and_follows_email_handoff() -> None:
    sql = _normalized()
    assert MIGRATION.name > "025_a1_email_registration_session_handoff.sql"
    assert sql.startswith(
        "-- atomic oauth first-login to canonical account and browser session handoff."
    )
    assert sql.startswith("-- atomic oauth")
    assert sql.index("begin;") < sql.index(
        "create table if not exists oauth_first_login_operations"
    )
    assert sql.strip().endswith("commit;")


def test_public_authority_signature_is_digest_and_reference_only() -> None:
    function = _function_body()
    signature = (
        "create or replace function "
        "a1_complete_oauth_first_login_with_refresh( "
        "p_organization_id uuid, p_project_id uuid, p_provider text, "
        "p_subject_digest text, p_email_digest text, p_opaque_ref text, "
        "p_opaque_ref_digest text, p_binding_digest text, "
        "p_session_digest text, p_refresh_digest text, "
        "p_rotation_family_digest text, p_access_expires_at timestamptz, "
        "p_refresh_expires_at timestamptz, p_idempotency_digest text, "
        "p_request_digest text, p_display_label text, "
        "p_metadata jsonb default '{}'::jsonb )"
    )
    assert signature in function
    assert (
        "returns table ( session_id uuid, principal_id uuid, "
        "credential_id uuid, connection_id uuid, token_ref_id uuid, "
        "created boolean )"
    ) in function

    forbidden_parameters = (
        "p_subject text",
        "p_email text",
        "p_access_token",
        "p_refresh_token",
        "p_id_token",
        "p_authorization_code",
        "p_code_verifier",
        "p_state",
        "p_nonce",
        "p_bearer",
        "p_principal_id",
        "p_account_id",
        "p_runtime_session_id",
        "p_provider_environment",
    )
    for fragment in forbidden_parameters:
        assert fragment not in function

    for parameter in (
        "p_subject_digest",
        "p_email_digest",
        "p_opaque_ref_digest",
        "p_binding_digest",
        "p_session_digest",
        "p_refresh_digest",
        "p_rotation_family_digest",
        "p_idempotency_digest",
        "p_request_digest",
    ):
        assert f"a1_identity_digest_valid({parameter})" in function
    assert "a1_oauth_reference_only(p_opaque_ref)" in function
    assert "a1_identity_public_metadata(p_metadata)" in function
    assert "a1_oauth_public_metadata(p_metadata)" in function


def test_operation_ledger_is_scoped_digest_only_and_replay_safe() -> None:
    table = _operation_table()
    required = (
        "organization_id uuid not null",
        "project_id uuid not null",
        "provider text not null",
        "subject_digest text not null",
        "idempotency_digest text not null",
        "request_digest text not null",
        "principal_id uuid",
        "credential_id uuid",
        "connection_id uuid",
        "token_ref_id uuid",
        "session_id uuid",
        "account_created boolean",
        "status text not null default 'processing'",
        "unique ( organization_id, project_id, provider, idempotency_digest )",
        "foreign key (organization_id, project_id)",
        "status = 'completed'",
    )
    for fragment in required:
        assert fragment in table

    forbidden_columns = (
        " email ",
        " subject ",
        " access_token ",
        " refresh_token ",
        " id_token ",
        " authorization_code ",
        " code_verifier ",
        " bearer ",
        " cookie ",
        " state ",
        " nonce ",
        " opaque_ref ",
    )
    for fragment in forbidden_columns:
        assert fragment not in f" {table} "

    function = _function_body()
    assert "on conflict (" in function
    assert "for update" in function
    assert "operation.request_digest <> p_request_digest" in function
    assert "operation.subject_digest <> p_subject_digest" in function
    assert "if operation.status = 'completed' then" in function
    assert "return query select" in function
    assert "raise exception 'idempotency_conflict'" in function


def test_authority_is_fixed_search_path_scope_bound_and_minimally_granted() -> None:
    sql = _normalized()
    function = _function_body()
    assert "language plpgsql security definer" in function
    assert "set search_path = pg_catalog, public, pg_temp" in function
    assert "a1_assert_role_nobypassrls(session_user)" in function
    assert "p_organization_id is distinct from a1_current_organization_id()" in function
    assert "p_project_id is distinct from a1_current_project_id()" in function
    assert "organization.status = 'active'" in function
    assert "project.status = 'active'" in function
    assert "p_provider not in ('google', 'github')" in function
    assert "'production'" in function

    signature = (
        "uuid,uuid,text,text,text,text,text,text,text,text,text,"
        "timestamptz,timestamptz,text,text,text,jsonb"
    )
    compact = re.sub(r"\s+", "", sql)
    assert (
        "revoke all on function "
        "a1_complete_oauth_first_login_with_refresh("
        f"{signature}) from public;"
    ).replace(" ", "") in compact
    assert (
        "grant execute on function "
        "a1_complete_oauth_first_login_with_refresh("
        f"{signature}) to a1_runtime;"
    ).replace(" ", "") in compact
    assert "grant insert on identity_principals to a1_runtime" not in sql
    assert "grant update on identity_credentials to a1_runtime" not in sql
    assert "grant insert on oauth_token_opaque_refs to a1_runtime" not in sql


def test_unknown_subject_creation_and_known_subject_login_are_separate() -> None:
    function = _function_body()
    lookup = function.index("from identity_credentials as credential_row")
    known = function.index("if found then", lookup)
    unknown = function.index("else", known)
    branch_end = function.index("end if;", unknown)
    known_branch = function[known:unknown]
    unknown_branch = function[unknown:branch_end]

    assert "pg_advisory_xact_lock(" in function[:lookup]
    assert "p_provider" in function[:lookup]
    assert "p_subject_digest" in function[:lookup]
    assert "provider_environment = 'production'" in function[lookup:known]
    assert "for update" in function[lookup:known]

    assert "principal.status <> 'active'" in known_branch
    assert "credential.status <> 'active'" in known_branch
    assert "not credential.login_enabled" in known_branch
    assert "identity_organization_memberships" in known_branch
    assert "identity_project_memberships" in known_branch
    assert "organization_membership.status = 'active'" in known_branch
    assert "project_membership.status = 'active'" in known_branch
    assert "insert into identity_principals" not in known_branch
    assert "insert into identity_organization_memberships" not in known_branch
    assert "insert into identity_project_memberships" not in known_branch
    assert "v_created := false" in known_branch

    assert "insert into identity_principals" in unknown_branch
    assert "insert into identity_credentials" in unknown_branch
    assert "insert into identity_organization_memberships" in unknown_branch
    assert "insert into identity_project_memberships" in unknown_branch
    assert "v_created := true" in unknown_branch


def test_verified_email_is_conflict_evidence_never_an_account_merge_key() -> None:
    function = _function_body()
    assert "from identity_account_emails" in function
    assert "normalized_email_digest = p_email_digest" in function
    assert "principal_id = v_principal_id" in function
    assert function.count("for update") >= 4
    assert "raise exception 'canonical_email_conflict'" in function
    assert "insert into identity_account_emails" in function
    assert "insert into identity_account_security" in function
    assert "a1_merge_identity_accounts" not in function
    assert "merged_into_principal_id" not in function
    assert "where normalized_email_digest = p_email_digest" not in (
        function[
            : function.index("from identity_credentials as credential_row")
        ]
    )


def test_session_connection_and_audit_complete_inside_one_authority() -> None:
    function = _function_body()
    principal = function.index("insert into identity_principals")
    credential = function.index("insert into identity_credentials")
    org_membership = function.index(
        "insert into identity_organization_memberships"
    )
    project_membership = function.index(
        "insert into identity_project_memberships"
    )
    token_ref = function.index("insert into oauth_token_opaque_refs")
    session = function.index("a1_issue_identity_session_with_refresh(")
    connection = function.index("insert into oauth_account_connections")
    audit = function.index("'identity.oauth.first_login.completed'")
    completion = function.index(
        "update oauth_first_login_operations", audit
    )
    assert principal < credential < org_membership < project_membership
    assert token_ref < session < connection < audit < completion
    assert "set_config('app.a1_principal_id'" in function
    assert "'aal1'" in function
    assert "p_session_digest" in function
    assert "p_refresh_digest" in function
    assert "p_rotation_family_digest" in function
    assert "account_id" in function
    assert "p_subject_digest" in function
    assert "provider_login" in function
    assert "'[redacted]'" in function
    assert "p_opaque_ref" not in function[audit:completion]
    assert "p_email_digest" not in function[audit:completion]
    assert "p_subject_digest" not in function[audit:completion]
