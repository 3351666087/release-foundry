from __future__ import annotations

import json
from pathlib import Path

from ashr_clone import (
    A3_IDENTITY_CONTRACT_SCHEMA_VERSION,
    a3_identity_contract_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/a1/schemas/a3_identity_registration_login_contract.schema.json"
PROVIDER_SCHEMA = ROOT / "docs/a1/schemas/a3_identity_provider_capabilities.schema.json"
EVIDENCE = ROOT / "docs/a1/evidence/round54_a3_identity_registration_login_contract.json"


def test_registration_and_login_are_separate_fail_closed_flows() -> None:
    contract = a3_identity_contract_manifest()
    routes = {item["operation"]: item for item in contract["routes"]}

    assert contract["schema_version"] == A3_IDENTITY_CONTRACT_SCHEMA_VERSION
    assert routes["register_start"]["path"] != routes["login_start"]["path"]
    assert routes["register_complete"]["path"] != routes["login_complete"]["path"]
    assert contract["registration"]["may_create_account"] is True
    assert contract["registration"]["verified_provider_proof_required"] is True
    assert {
        key: contract["login"][key]
        for key in (
            "may_create_account",
            "may_merge_accounts",
            "may_link_credentials",
            "existing_verified_credential_required",
            "unknown_identity_status",
            "verified_email_conflict_status",
        )
    } == {
        "may_create_account": False,
        "may_merge_accounts": False,
        "may_link_credentials": False,
        "existing_verified_credential_required": True,
        "unknown_identity_status": "failed",
        "verified_email_conflict_status": "merge_required",
    }


def test_email_is_preferred_and_domestic_qualification_status_is_explicit() -> None:
    contract = a3_identity_contract_manifest()
    providers = {item["provider"]: item for item in contract["providers"]}

    assert contract["preferred_registration_provider"] == "email"
    assert providers["email"]["preferred_registration"] is True
    assert providers["github"]["login"] == "available"
    assert providers["google"]["login"] == "available"
    for provider in ("wechat", "qq", "alipay"):
        assert providers[provider]["login"] == "unavailable"
        assert providers[provider]["requires_business_qualification"] is True


def test_a3_surface_covers_account_security_lifecycle() -> None:
    contract = a3_identity_contract_manifest()
    operations = set(contract["operations"])

    assert {
        "register_start",
        "register_complete",
        "login_start",
        "login_complete",
        "link_start",
        "link_complete",
        "unlink",
        "password_set",
        "password_change",
        "two_factor_enroll",
        "two_factor_verify",
        "two_factor_recovery_consume",
        "two_factor_recovery_rotate",
        "two_factor_disable",
    } <= operations
    assert contract["account_mutations"]["last_login_method_unlink_forbidden"] is True
    assert contract["account_mutations"]["two_factor_optional"] is True
    assert contract["account_mutations"]["two_factor_recommended"] is True
    assert contract["a3_response_envelope"]["raw_identity_values_present"] is False
    assert contract["a3_response_envelope"]["secret_values_present"] is False


def test_public_identity_and_existing_account_binding_security_are_distinct() -> None:
    contract = a3_identity_contract_manifest()
    security = contract["operation_security"]

    for public_flow in ("public_registration", "public_login"):
        profile = security[public_flow]
        assert profile["authenticated_actor_required"] is False
        assert profile["matching_authenticated_actor_required"] is False
        assert profile["recent_reauthentication_required"] is False
        assert profile["csrf_required"] is False
        assert profile["verified_assertion_required"] is True
        assert (
            profile["verified_assertion_source"]
            == "server_owned_single_use_proof_receipt"
        )
        if public_flow == "public_registration":
            assert profile["legacy_accountless_binding_http_rejected"] is True
        assert profile["route_lifecycle"] == "active"
        assert profile["client_callable"] is True

    binding = security["existing_account_binding"]
    assert binding["explicit_user_action_required"] is True
    assert binding["authenticated_actor_required"] is True
    assert binding["matching_authenticated_actor_required"] is True
    assert binding["recent_reauthentication_required"] is True
    assert binding["csrf_required"] is True
    assert binding["verified_assertion_required"] is True
    assert binding["atomic_completion_required"] is True
    assert binding["proof_receipt_consumed_with_mutation"] is True
    assert binding["mutation_ticket_consumed_with_step_up"] is True
    assert binding["activation_requires_postgres_coordinator"] is True
    assert (
        binding["go_atomic_coordinator_contract"]
        == "IdentityCredentialLinkCoordinator"
    )
    assert binding["route_lifecycle"] == "proposed"
    assert binding["client_callable"] is False


def test_evidence_separates_desired_implemented_runtime_and_gaps() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    required = {
        "desired_contract",
        "implemented_routes",
        "runtime_verified",
        "proposed_non_routable",
        "known_gaps",
    }
    assert required <= evidence.keys()
    assert evidence["implemented_routes"]["authority"].endswith(
        "GoRouteManifestEntries"
    )
    assert evidence["runtime_verified"]["status"] == "not_claimed"
    binding = evidence["operation_security"]["existing_account_binding"]
    assert binding["atomic_completion_required"] is True
    assert binding["proof_receipt_consumed_with_mutation"] is True
    assert binding["mutation_ticket_consumed_with_step_up"] is True
    assert binding["activation_requires_postgres_coordinator"] is True
    assert (
        binding["go_atomic_coordinator_contract"]
        == "IdentityCredentialLinkCoordinator"
    )
    implemented = {
        (route["method"], route["path"])
        for route in evidence["implemented_routes"]["routes"]
    }
    assert implemented == {
        ("GET", "/v1/accounts/{account_id}/security"),
        ("GET", "/v1/identity/providers"),
        ("POST", "/v1/accounts/{account_id}/password/change/begin"),
        ("POST", "/v1/accounts/{account_id}/password/enroll/begin"),
        ("POST", "/v1/accounts/{account_id}/password/recover/begin"),
        ("POST", "/v1/accounts/{account_id}/two-factor/disable"),
        ("POST", "/v1/accounts/{account_id}/two-factor/enroll/begin"),
        ("POST", "/v1/accounts/{account_id}/two-factor/enroll/confirm"),
        ("POST", "/v1/accounts/{account_id}/two-factor/recovery-codes/consume"),
        ("POST", "/v1/accounts/{account_id}/two-factor/recovery-codes/rotate"),
        ("POST", "/v1/identity/registration/start"),
        ("POST", "/v1/identity/registration/complete"),
        ("POST", "/v1/identity/login/start"),
        ("POST", "/v1/identity/login/complete"),
    }
    proposed = set(evidence["proposed_non_routable"]["operations"])
    assert not {
        "provider_status",
        "register_start",
        "register_complete",
        "login_start",
        "login_complete",
        "security_posture",
        "password_set",
        "password_change",
        "password_recover",
        "two_factor_enroll",
        "two_factor_verify",
        "two_factor_recovery_consume",
        "two_factor_recovery_rotate",
        "two_factor_disable",
    } & proposed
    assert proposed == {
        "link_start",
        "link_complete",
        "unlink",
    }
    assert evidence["proposed_non_routable"]["client_callable"] is False
    assert evidence["known_gaps"]


def test_evidence_pins_oauth_binding_password_and_two_factor_rules() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    desired = evidence["desired_contract"]

    assert desired["preferred_registration_provider"] == "email"
    assert desired["oauth_first_registration"] == {
        "canonical_email_source": "provider_verified_email_only",
        "unverified_email_ignored": True,
        "password_status": "absent",
    }
    for mutation in ("account_binding", "password_mutation"):
        assert desired[mutation]["matching_authenticated_actor_required"] is True
        assert desired[mutation]["recent_reauthentication_required"] is True
        assert desired[mutation]["csrf_required"] is True
    assert desired["account_binding"]["authenticated_actor_required"] is True
    assert desired["account_binding"]["verified_assertion_required"] is True
    assert desired["account_binding"]["route_lifecycle"] == "proposed"
    assert desired["account_binding"]["client_callable"] is False
    assert evidence["operation_security"] == a3_identity_contract_manifest()[
        "operation_security"
    ]
    assert desired["two_factor"]["optional"] is True
    assert desired["two_factor"]["recommended"] is True


def test_evidence_exposes_machine_readable_conflicts_and_domestic_gates() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    machine_contract = evidence["a3_machine_readable_contract"]
    conflicts = set(machine_contract["conflict_codes"])
    errors = set(machine_contract["error_codes"])

    assert {
        "canonical_email_conflict",
        "credential_already_linked",
        "last_login_method",
        "business_qualification_required",
    } <= conflicts
    assert not {
        "authentication_failed",
        "recent_reauthentication_required",
        "csrf_validation_failed",
        "verified_proof_replayed",
        "verified_proof_scope_mismatch",
    } & conflicts
    assert {
        "authentication_failed",
        "recent_reauthentication_required",
        "csrf_validation_failed",
        "provider_unavailable",
        "verified_proof_required",
        "verified_proof_expired",
        "verified_proof_replayed",
        "verified_proof_scope_mismatch",
    } <= errors
    for provider in ("wechat", "qq", "alipay"):
        capability = evidence["provider_capabilities"][provider]
        assert capability["enabled"] is False
        assert capability["requires_business_qualification"] is True
        assert {
            capability["registration"],
            capability["login"],
            capability["linking"],
        } == {"unavailable"}


def test_schema_and_evidence_pin_the_same_contract() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    contract = a3_identity_contract_manifest()

    assert schema["$id"].endswith("a3_identity_registration_login_contract.schema.json")
    assert set(schema["properties"]["operation"]["enum"]) == set(contract["operations"])
    assert set(schema["properties"]["status"]["enum"]) == set(contract["flow_statuses"])
    assert evidence["schema_version"] == contract["schema_version"]
    assert set(evidence["a3_machine_readable_contract"]["operations"]) == set(
        contract["operations"]
    )
    assert evidence["desired_contract"]["preferred_registration_provider"] == "email"
    assert evidence["desired_contract"]["registration_and_login_are_distinct"] is True
    assert evidence["desired_contract"]["login"]["may_create_account"] is False
    assert evidence["desired_contract"]["login"]["may_link_credentials"] is False


def test_a3_has_distinct_provider_capability_and_public_error_contracts() -> None:
    provider_schema = json.loads(PROVIDER_SCHEMA.read_text(encoding="utf-8"))
    response_schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    provider = provider_schema["properties"]["providers"]["items"]["properties"]

    assert provider_schema["$id"].endswith("a3_identity_provider_capabilities.schema.json")
    assert {
        "registration_status",
        "login_status",
        "linking_status",
        "enabled",
        "reason_code",
        "requires_business_qualification",
        "qualification_status",
    } <= provider.keys()
    error = response_schema["properties"]["error"]["oneOf"][1]
    assert set(error["required"]) == {
        "code",
        "http_status",
        "anti_enumeration",
        "retryable",
        "public_safe",
    }
    assert "authentication_failed" in error["properties"]["code"]["enum"]
    conflict_codes = (
        response_schema["properties"]["conflict"]["oneOf"][1]["properties"]["code"]["enum"]
    )
    assert "authentication_failed" not in conflict_codes
