from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/a1/evidence/unified_identity_contract_20260710.json"
GOOGLE_EVIDENCE = (
    ROOT / "docs/a1/evidence/google_oauth_localhost_evidence_20260710.json"
)
GITHUB_EVIDENCE = (
    ROOT / "docs/a1/evidence/github_account_connection_evidence_20260710.json"
)
SAME_ACCOUNT_EVIDENCE = (
    ROOT
    / "docs/a1/evidence/unified_identity_same_account_localhost_20260710.json"
)
OAUTH_LIFECYCLE_SQL = ROOT / "services/api/migrations/006_a1_oauth_lifecycle.sql"
OAUTH_RUNTIME_SQL = ROOT / "services/api/migrations/007_a1_oauth_runtime_store.sql"
GO_OAUTH = ROOT / "packages/go/ashrclone/oauth_provider.go"
GO_OAUTH_HTTP = ROOT / "packages/go/ashrclone/oauth_provider_http.go"
GO_GITHUB_HTTP = ROOT / "packages/go/ashrclone/oauth_github_http.go"
GO_SERVER = ROOT / "packages/go/ashrclone/server.go"
GO_UNIFIED_HTTP = ROOT / "packages/go/ashrclone/unified_identity_http.go"
GO_UNIFIED_HTTP_TEST = (
    ROOT / "packages/go/ashrclone/unified_identity_http_test.go"
)
GO_OAUTH_UNIFIED_TEST = (
    ROOT / "packages/go/ashrclone/oauth_unified_identity_test.go"
)

IDENTITY_KINDS = frozenset(
    {"github", "google", "wechat", "qq", "alipay", "phone", "email"}
)
CALIBRATED_PROVIDERS = frozenset({"github", "google"})
UNCALIBRATED_PROVIDERS = IDENTITY_KINDS - CALIBRATED_PROVIDERS
PUBLIC_IDENTITY_KEYS = frozenset(
    {
        "schema_version",
        "credential_id",
        "account_id",
        "kind",
        "status",
        "verified",
        "connected_at",
        "disconnected_at",
        "display_label",
    }
)
FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "phone",
        "phone_number",
        "email",
        "email_address",
        "provider_subject",
        "subject",
        "subject_digest",
        "provider_subject_sha256",
        "identifier_sha256",
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "token_ref",
        "authorization_code",
        "code",
        "code_verifier",
        "client_secret",
        "state",
        "nonce",
    }
)


class IdentityConflict(ValueError):
    pass


class LastCredentialRemoval(ValueError):
    pass


@dataclass(frozen=True)
class Credential:
    credential_id: str
    account_id: str
    kind: str
    private_lookup_digest: str
    verified: bool = True
    status: str = "active"

    def public_dto(self) -> dict[str, Any]:
        return {
            "schema_version": "ashr.unified_identity.v1",
            "credential_id": self.credential_id,
            "account_id": self.account_id,
            "kind": self.kind,
            "status": self.status,
            "verified": self.verified,
            "connected_at": "2026-07-10T00:00:00Z",
            "disconnected_at": None,
            "display_label": f"{self.kind} credential",
        }


@dataclass(frozen=True)
class Membership:
    membership_id: str
    account_id: str
    tenant_id: str
    project_id: str | None
    role: str


@dataclass
class UnifiedIdentityRegistry:
    credentials: dict[str, Credential] = field(default_factory=dict)
    lookup_index: dict[tuple[str, str], str] = field(default_factory=dict)
    memberships: dict[str, Membership] = field(default_factory=dict)

    def bind(
        self,
        *,
        credential_id: str,
        account_id: str,
        kind: str,
        private_lookup_digest: str,
        verified: bool = True,
    ) -> Credential:
        normalized_kind = kind.strip().lower()
        if normalized_kind not in IDENTITY_KINDS:
            raise ValueError("unsupported identity kind")
        lookup_key = (normalized_kind, private_lookup_digest)
        owner = self.lookup_index.get(lookup_key)
        if owner is not None and owner != account_id:
            raise IdentityConflict("credential is already bound to another account")
        if credential_id in self.credentials:
            raise IdentityConflict("credential id already exists")
        credential = Credential(
            credential_id=credential_id,
            account_id=account_id,
            kind=normalized_kind,
            private_lookup_digest=private_lookup_digest,
            verified=verified,
        )
        self.credentials[credential_id] = credential
        self.lookup_index[lookup_key] = account_id
        return credential

    def authenticate(self, *, kind: str, private_lookup_digest: str) -> str:
        owner = self.lookup_index.get((kind.strip().lower(), private_lookup_digest))
        if owner is None:
            raise IdentityConflict("credential is not linked")
        credential = next(
            item
            for item in self.credentials.values()
            if item.account_id == owner
            and item.kind == kind.strip().lower()
            and item.private_lookup_digest == private_lookup_digest
        )
        if not credential.verified or credential.status != "active":
            raise IdentityConflict("credential is not verified and active")
        return owner

    def unbind(self, *, account_id: str, credential_id: str) -> None:
        credential = self.credentials[credential_id]
        if credential.account_id != account_id:
            raise IdentityConflict("credential does not belong to authenticated account")
        active = [
            item
            for item in self.credentials.values()
            if item.account_id == account_id and item.status == "active"
        ]
        if len(active) <= 1:
            raise LastCredentialRemoval(
                "cannot remove the final sign-in credential from an active account"
            )
        self.credentials[credential_id] = Credential(
            credential_id=credential.credential_id,
            account_id=credential.account_id,
            kind=credential.kind,
            private_lookup_digest=credential.private_lookup_digest,
            verified=credential.verified,
            status="disconnected",
        )

    def add_membership(
        self,
        *,
        membership_id: str,
        account_id: str,
        tenant_id: str,
        project_id: str | None,
        role: str,
    ) -> None:
        self.memberships[membership_id] = Membership(
            membership_id=membership_id,
            account_id=account_id,
            tenant_id=tenant_id,
            project_id=project_id,
            role=role,
        )


def _digest(label: str) -> str:
    # Deterministic non-secret test lookup keys; public DTOs never expose them.
    return (label.encode("utf-8").hex() * 64)[:64]


def _assert_public_identity_safe(payload: Any) -> None:
    if isinstance(payload, dict):
        keys = {str(key).lower() for key in payload}
        assert not keys.intersection(FORBIDDEN_PUBLIC_KEYS)
        for value in payload.values():
            _assert_public_identity_safe(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_public_identity_safe(value)


def _registry_with_all_identity_kinds() -> UnifiedIdentityRegistry:
    registry = UnifiedIdentityRegistry()
    for index, kind in enumerate(sorted(IDENTITY_KINDS), start=1):
        registry.bind(
            credential_id=f"credential_{index}",
            account_id="account_primary",
            kind=kind,
            private_lookup_digest=_digest(f"{kind}-primary"),
        )
    return registry


def test_one_internal_account_can_bind_every_required_identity_kind() -> None:
    registry = _registry_with_all_identity_kinds()

    linked = {
        credential.kind
        for credential in registry.credentials.values()
        if credential.account_id == "account_primary"
        and credential.status == "active"
    }

    assert linked == IDENTITY_KINDS
    assert {item.account_id for item in registry.credentials.values()} == {
        "account_primary"
    }


@pytest.mark.parametrize("kind", sorted(IDENTITY_KINDS))
def test_cross_account_credential_takeover_is_rejected(kind: str) -> None:
    registry = UnifiedIdentityRegistry()
    lookup = _digest(f"{kind}-stable-provider-lookup")
    registry.bind(
        credential_id="credential_original",
        account_id="account_original",
        kind=kind,
        private_lookup_digest=lookup,
    )

    with pytest.raises(IdentityConflict, match="another account"):
        registry.bind(
            credential_id="credential_attacker",
            account_id="account_attacker",
            kind=kind,
            private_lookup_digest=lookup,
        )

    assert registry.lookup_index[(kind, lookup)] == "account_original"
    assert "credential_attacker" not in registry.credentials


def test_matching_email_claims_do_not_implicitly_merge_accounts() -> None:
    registry = UnifiedIdentityRegistry()
    normalized_email_lookup = _digest("normalized-shared-email")
    registry.bind(
        credential_id="credential_email_original",
        account_id="account_original",
        kind="email",
        private_lookup_digest=normalized_email_lookup,
    )

    with pytest.raises(IdentityConflict, match="another account"):
        registry.bind(
            credential_id="credential_email_claim",
            account_id="account_other",
            kind="email",
            private_lookup_digest=normalized_email_lookup,
        )

    registry.bind(
        credential_id="credential_email_distinct",
        account_id="account_other",
        kind="email",
        private_lookup_digest=_digest("different-normalized-email"),
    )
    assert {
        item.account_id for item in registry.credentials.values()
    } == {"account_original", "account_other"}


def test_unverified_credential_cannot_authenticate() -> None:
    registry = UnifiedIdentityRegistry()
    lookup = _digest("unverified-email")
    registry.bind(
        credential_id="credential_unverified",
        account_id="account_primary",
        kind="email",
        private_lookup_digest=lookup,
        verified=False,
    )

    with pytest.raises(IdentityConflict, match="not verified"):
        registry.authenticate(kind="email", private_lookup_digest=lookup)


def test_final_sign_in_credential_cannot_be_unbound() -> None:
    registry = UnifiedIdentityRegistry()
    registry.bind(
        credential_id="credential_only",
        account_id="account_primary",
        kind="email",
        private_lookup_digest=_digest("only-credential"),
    )

    before = copy.deepcopy(registry.credentials)
    with pytest.raises(LastCredentialRemoval, match="final sign-in credential"):
        registry.unbind(
            account_id="account_primary",
            credential_id="credential_only",
        )

    assert registry.credentials == before


def test_non_final_credential_can_be_unbound_without_orphaning_account() -> None:
    registry = UnifiedIdentityRegistry()
    registry.bind(
        credential_id="credential_email",
        account_id="account_primary",
        kind="email",
        private_lookup_digest=_digest("primary-email"),
    )
    registry.bind(
        credential_id="credential_google",
        account_id="account_primary",
        kind="google",
        private_lookup_digest=_digest("primary-google"),
    )

    registry.unbind(
        account_id="account_primary",
        credential_id="credential_google",
    )

    assert registry.credentials["credential_google"].status == "disconnected"
    assert registry.credentials["credential_email"].status == "active"


def test_identity_credentials_and_memberships_have_separate_lifecycles() -> None:
    registry = _registry_with_all_identity_kinds()
    registry.add_membership(
        membership_id="membership_owner",
        account_id="account_primary",
        tenant_id="tenant_one",
        project_id=None,
        role="owner",
    )
    registry.add_membership(
        membership_id="membership_viewer",
        account_id="account_primary",
        tenant_id="tenant_two",
        project_id="project_two",
        role="viewer",
    )

    memberships_before = copy.deepcopy(registry.memberships)
    registry.unbind(
        account_id="account_primary",
        credential_id="credential_1",
    )

    assert registry.memberships == memberships_before
    assert {
        membership.tenant_id for membership in registry.memberships.values()
    } == {"tenant_one", "tenant_two"}
    assert all(
        membership.account_id == "account_primary"
        for membership in registry.memberships.values()
    )


def test_public_identity_dtos_are_allowlisted_and_private_lookup_data_is_absent() -> None:
    registry = _registry_with_all_identity_kinds()
    payload = [credential.public_dto() for credential in registry.credentials.values()]

    for item in payload:
        assert set(item) == PUBLIC_IDENTITY_KEYS
    _assert_public_identity_safe(payload)

    serialized = json.dumps(payload, sort_keys=True)
    for credential in registry.credentials.values():
        assert credential.private_lookup_digest not in serialized


def test_existing_postgres_schema_rejects_provider_subject_takeover() -> None:
    lifecycle_sql = OAUTH_LIFECYCLE_SQL.read_text(encoding="utf-8")
    runtime_sql = OAUTH_RUNTIME_SQL.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS external_identities" in lifecycle_sql
    assert "external_identities_provider_subject_key" in lifecycle_sql
    assert (
        "UNIQUE (organization_id, project_id, provider, environment, subject_digest)"
        in lifecycle_sql
    )
    assert "external_identities_user_provider_key" in lifecycle_sql
    assert "CREATE TABLE IF NOT EXISTS oauth_account_connections" in runtime_sql
    assert "oauth_account_connections_subject_key" in runtime_sql
    assert (
        "UNIQUE (organization_id, project_id, provider, provider_subject_digest)"
        in runtime_sql
    )


def test_existing_go_public_connection_dto_hides_raw_identity_and_tokens() -> None:
    source = GO_OAUTH.read_text(encoding="utf-8")
    struct_start = source.index("type OAuthConnection struct")
    struct_end = source.index("type OAuthConnectionStore interface")
    dto = source[struct_start:struct_end]

    assert re.search(r'AccountID\s+string\s+`json:"account_id"`', dto)
    assert 'json:"provider_subject_sha256"' not in dto
    assert 'json:"subject_digest"' not in dto
    assert 'json:"identifier_sha256"' not in dto
    assert re.search(r'Email\s+string\s+`json:"-"`', dto)
    for field_name in ("TokenRef", "TenantID", "ProjectID", "SessionID", "UserID"):
        assert re.search(rf'{field_name}\s+string\s+`json:"-"`', dto)


def test_oauth_http_routes_do_not_trust_caller_supplied_account_id() -> None:
    provider_http = GO_OAUTH_HTTP.read_text(encoding="utf-8")
    github_http = GO_GITHUB_HTTP.read_text(encoding="utf-8")

    forbidden = (
        'accountID := firstNonEmpty('
        'request.URL.Query().Get("account_id"), '
        'stringValue(body, "account_id"))'
    )
    assert forbidden not in provider_http
    assert forbidden not in github_http
    assert "ResolveOAuthSession" in GO_OAUTH.read_text(encoding="utf-8")


def test_unified_identity_acceptance_tests_cover_required_security_boundaries() -> None:
    unified_http = GO_UNIFIED_HTTP_TEST.read_text(encoding="utf-8")
    oauth_http = GO_OAUTH_UNIFIED_TEST.read_text(encoding="utf-8")
    combined = unified_http + oauth_http

    for marker in (
        "LinksGitHubAndGoogleToOneAccount",
        "RejectsCrossAccountCredentialClaim",
        "UnlinkPreservesMembershipAndFinalLogin",
        "RejectsCallerSuppliedAccountTakeover",
        "RejectsCrossAccountProviderSubjectConflict",
        "PublicResponsesContainNoSubjectTokenOrDigest",
    ):
        assert marker in combined


def test_server_runtime_exposes_provider_neutral_unified_identity_boundary() -> None:
    server = GO_SERVER.read_text(encoding="utf-8")
    unified_http = GO_UNIFIED_HTTP.read_text(encoding="utf-8")
    route_contract = server + unified_http

    assert "UnifiedIdentity" in server
    for route_fragment in (
        "handleUnifiedIdentityAccount",
        'parts[0] == "credentials"',
        'parts[0] == "memberships"',
        'parts[2] == "link"',
        'parts[2] == "unlink"',
    ):
        assert route_fragment in route_contract


def test_unified_identity_evidence_is_public_safe_and_honest_about_calibration() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    serialized = json.dumps(evidence, sort_keys=True).lower()

    assert evidence["schema_version"] == "ashr.unified_identity.contract.v1"
    assert evidence["public_safe"] is True
    assert evidence["contains_secret_values"] is False
    assert set(evidence["required_identity_kinds"]) == IDENTITY_KINDS
    assert set(evidence["real_provider_calibration"]["completed"]) == {
        "github",
        "google",
    }
    assert set(evidence["real_provider_calibration"]["not_completed"]) == {
        "wechat",
        "qq",
        "alipay",
        "phone",
        "email",
    }
    assert evidence["real_provider_calibration"]["claims_real_calibration_for_pending"] is False
    assert evidence["security_controls"]["cross_account_takeover"] == "reject"
    assert evidence["security_controls"]["last_credential_unlink"] == "reject"
    assert evidence["security_controls"]["membership_identity_coupling"] == "forbidden"
    assert evidence["security_controls"]["caller_supplied_account_id"] == "reject"
    assert evidence["security_controls"]["public_subject_digest"] == "forbidden"
    assert evidence["acceptance_status"]["oauth_runtime_unified_account_wiring"] == (
        "implemented_and_real_localhost_calibrated"
    )
    assert evidence["acceptance_status"]["production_readiness"] == "not_completed"

    calibration = evidence["verification_20260710"][
        "localhost_same_account_calibration"
    ]
    assert calibration["credential_count"] == 2
    assert set(calibration["providers"]) == {"github", "google"}
    assert calibration["membership_count"] == 0
    assert calibration["forged_account_status_code"] == 403
    assert calibration["public_response_secret_scan"] == "passed"

    assert "@" not in serialized
    assert "ya29." not in serialized
    assert "ghp_" not in serialized
    assert "gho_" not in serialized
    assert "client_secret=" not in serialized
    assert "access_token=" not in serialized
    assert "refresh_token=" not in serialized
    assert "authorization_code=" not in serialized
    assert "callback?" not in serialized


@pytest.mark.parametrize(
    "path",
    (EVIDENCE, GOOGLE_EVIDENCE, GITHUB_EVIDENCE, SAME_ACCOUNT_EVIDENCE),
    ids=("contract", "google", "github", "same_account"),
)
def test_public_identity_evidence_contains_no_stable_identifier_or_secret_value(
    path: Path,
) -> None:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(evidence, sort_keys=True)
    lower = serialized.lower()

    assert evidence["public_safe"] is True
    assert evidence["contains_secret_values"] is False
    assert not re.search(r"\b[a-f0-9]{64}\b", lower)
    assert not re.search(
        r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",
        lower,
        flags=re.IGNORECASE,
    )
    for marker in (
        "access_token=",
        "refresh_token=",
        "id_token=",
        "authorization_code=",
        "client_secret=",
        "code_verifier=",
        "state=",
        "nonce=",
        "gho_",
        "ghp_",
        "ya29.",
    ):
        assert marker not in lower

    sensitive_value_keys = {
        "email",
        "email_address",
        "phone",
        "phone_number",
        "provider_subject",
        "provider_subject_sha256",
        "subject",
        "subject_digest",
        "identifier_sha256",
        "safe_identity_digest_or_suffix",
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "token_ref",
        "authorization_code",
        "code_verifier",
        "client_secret",
        "state",
        "nonce",
    }

    def assert_sensitive_fields_are_boolean_only(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).lower()
                if normalized in sensitive_value_keys:
                    pytest.fail(f"{path} contains forbidden public field {key!r}")
                if normalized.endswith(
                    (
                        "_present",
                        "_recorded",
                        "_exposed",
                        "_completed",
                    )
                ) and any(
                    marker in normalized
                    for marker in (
                        "subject",
                        "digest",
                        "phone",
                        "email",
                        "token",
                        "code",
                        "state",
                        "verifier",
                        "secret",
                    )
                ):
                    assert isinstance(nested, bool), (path, key, nested)
                assert_sensitive_fields_are_boolean_only(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_sensitive_fields_are_boolean_only(nested)

    assert_sensitive_fields_are_boolean_only(evidence)


def test_same_account_localhost_evidence_proves_one_canonical_account() -> None:
    evidence = json.loads(SAME_ACCOUNT_EVIDENCE.read_text(encoding="utf-8"))
    account = evidence["canonical_account"]
    checks = {
        item["check"]: item
        for item in evidence["runtime_checks"]
    }

    assert evidence["schema_version"] == (
        "ashr.unified_identity.same_account_localhost.v1"
    )
    assert evidence["public_safe"] is True
    assert evidence["contains_secret_values"] is False
    assert evidence["production_ready"] is False
    assert evidence["backend_mode"] == "local_memory"
    assert evidence["ashr_api_used"] is False
    assert account["credential_count"] == 2
    assert set(account["providers"]) == {"github", "google"}
    assert account["credential_kinds"] == ["oauth"]
    assert account["all_credentials_verified"] is True
    assert account["all_credentials_can_login"] is True
    assert account["membership_count"] == 0
    assert checks["caller_supplied_account_mismatch"] == {
        "check": "caller_supplied_account_mismatch",
        "status_code": 403,
        "failed_closed": True,
    }
    assert checks["public_response_forbidden_material_scan"]["status"] == "passed"
    assert checks["public_response_forbidden_material_scan"]["forbidden_key_hits"] == 0


def test_evidence_records_known_implementation_gaps_without_overclaiming() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    gaps = set(evidence["known_implementation_gaps"])

    assert {
        "memory_store_subject_uniqueness_is_not_multi_instance",
        "china_identity_providers_not_real_calibrated",
        "phone_and_email_verification_not_real_calibrated",
    }.issubset(gaps)
    assert evidence["production_ready"] is False
