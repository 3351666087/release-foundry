from __future__ import annotations

from copy import deepcopy
import json

import pytest

import ashr_clone
from ashr_clone.delivery_protocol import (
    IDENTITY_DELIVERY_ACCEPTANCE_STATUSES,
    IDENTITY_DELIVERY_ADMIN_ROUTES,
    IDENTITY_DELIVERY_DTO_KINDS,
    IDENTITY_DELIVERY_ERROR_CODES,
    IDENTITY_DELIVERY_FAILURE_CODES,
    IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
    IDENTITY_DELIVERY_STATUSES,
    IdentityDeliveryAcceptanceDTO,
    IdentityDeliveryProtocolError,
    IdentityDeliveryRedriveReceiptDTO,
    IdentityDeliveryRedriveRequestDTO,
    IdentityDeliveryTaskDTO,
    assert_public_identity_delivery_payload,
    canonical_identity_delivery_json,
    identity_delivery_admin_acceptances_route,
    identity_delivery_admin_collection_route,
    identity_delivery_admin_redrive_route,
    identity_delivery_admin_redrives_route,
    identity_delivery_admin_task_route,
    identity_delivery_protocol_contract_manifest,
    parse_identity_delivery_canonical_json,
    validate_identity_delivery_acceptance,
    validate_identity_delivery_redrive_receipt,
    validate_identity_delivery_redrive_request,
    validate_identity_delivery_task,
)


SCHEMA = IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION


def _task(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "task_id": "task_001",
        "tenant_id": "tenant_001",
        "project_id": "project_001",
        "challenge_id": "challenge_001",
        "channel": "email",
        "purpose": "login",
        "status": "leased",
        "attempt": 1,
        "max_attempts": 8,
        "lease_generation": 4,
        "redrive_count": 0,
        "provider_idempotency_key": "identity-delivery:challenge_001:0",
        "challenge_expires_at": "2026-07-11T05:10:00.000Z",
        "lease_expires_at": "2026-07-11T05:01:00.000Z",
        "next_attempt_at": None,
        "provider_acceptance_present": False,
        "accepted_at": None,
        "completed_at": None,
        "dead_at": None,
        "last_failure_code": None,
    }
    payload.update(overrides)
    return payload


def _acceptance(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "task_id": "task_001",
        "tenant_id": "tenant_001",
        "project_id": "project_001",
        "challenge_id": "challenge_001",
        "status": "provider_accepted",
        "attempt": 1,
        "lease_generation": 4,
        "provider_idempotency_key": "identity-delivery:challenge_001:0",
        "provider_acceptance_present": True,
        "accepted_at": "2026-07-11T05:00:10.000Z",
        "recorded_at": "2026-07-11T05:00:11.000Z",
        "failure_code": None,
    }
    payload.update(overrides)
    return payload


def _redrive_request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "task_id": "task_001",
        "tenant_id": "tenant_001",
        "project_id": "project_001",
        "expected_lease_generation": 4,
        "actor_id": "account_admin",
        "reason_code": "operator_retry",
        "request_id": "request_redrive_001",
    }
    payload.update(overrides)
    return payload


def _redrive_receipt(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "task_id": "task_001",
        "tenant_id": "tenant_001",
        "project_id": "project_001",
        "request_id": "request_redrive_001",
        "audit_id": "audit_redrive_001",
        "actor_id": "account_admin",
        "reason_code": "operator_retry",
        "status": "pending",
        "previous_lease_generation": 4,
        "lease_generation": 5,
        "previous_provider_idempotency_key": "identity-delivery:challenge_001:0",
        "provider_idempotency_key": "identity-delivery:challenge_001:1",
        "redriven_at": "2026-07-11T05:05:00.000Z",
    }
    payload.update(overrides)
    return payload


def test_delivery_protocol_manifest_routes_and_exports_are_stable() -> None:
    manifest = identity_delivery_protocol_contract_manifest()

    assert manifest["schema_version"] == SCHEMA
    assert manifest["dto_kinds"] == list(IDENTITY_DELIVERY_DTO_KINDS)
    assert manifest["statuses"] == list(IDENTITY_DELIVERY_STATUSES)
    assert manifest["acceptance_statuses"] == list(IDENTITY_DELIVERY_ACCEPTANCE_STATUSES)
    assert manifest["stable_error_codes"] == list(IDENTITY_DELIVERY_ERROR_CODES)
    assert manifest["failure_codes"] == list(IDENTITY_DELIVERY_FAILURE_CODES)
    assert manifest["routes"] == list(IDENTITY_DELIVERY_ADMIN_ROUTES)
    assert all(manifest["invariants"].values())
    assert_public_identity_delivery_payload(manifest)

    assert identity_delivery_admin_collection_route("project_001") == (
        "/v1/projects/project_001/admin/identity-deliveries"
    )
    assert identity_delivery_admin_task_route("project_001", "task_001").endswith(
        "/identity-deliveries/task_001"
    )
    assert identity_delivery_admin_acceptances_route("project_001", "task_001").endswith(
        "/task_001/acceptances"
    )
    assert identity_delivery_admin_redrive_route("project_001", "task_001").endswith(
        "/task_001/redrive"
    )
    assert identity_delivery_admin_redrives_route("project_001", "task_001").endswith(
        "/task_001/redrives"
    )
    assert ashr_clone.IdentityDeliveryTaskDTO is IdentityDeliveryTaskDTO
    assert ashr_clone.canonical_identity_delivery_json is canonical_identity_delivery_json


def test_task_dto_enforces_fencing_retry_acceptance_and_terminal_states() -> None:
    leased = validate_identity_delivery_task(_task())
    assert isinstance(leased, IdentityDeliveryTaskDTO)
    assert leased.to_dict() == _task()

    retry = validate_identity_delivery_task(
        _task(
            status="retry",
            lease_expires_at=None,
            next_attempt_at="2026-07-11T05:02:00.000Z",
            last_failure_code="provider_timeout",
        )
    )
    assert retry.provider_idempotency_key == leased.provider_idempotency_key

    accepted = validate_identity_delivery_task(
        _task(
            status="provider_accepted",
            lease_expires_at=None,
            provider_acceptance_present=True,
            accepted_at="2026-07-11T05:00:10.000Z",
        )
    )
    delivered = validate_identity_delivery_task(
        _task(
            status="delivered",
            lease_expires_at=None,
            provider_acceptance_present=True,
            accepted_at="2026-07-11T05:00:10.000Z",
            completed_at="2026-07-11T05:00:12.000Z",
        )
    )
    ambiguous = validate_identity_delivery_task(
        _task(
            status="ambiguous",
            lease_expires_at=None,
            last_failure_code="provider_result_ambiguous",
        )
    )
    dead = validate_identity_delivery_task(
        _task(
            status="dead",
            lease_expires_at=None,
            dead_at="2026-07-11T05:03:00.000Z",
            last_failure_code="attempts_exhausted",
        )
    )
    assert accepted.provider_acceptance_present is True
    assert delivered.completed_at is not None
    assert ambiguous.provider_acceptance_present is False
    assert dead.dead_at is not None

    invalid_cases = (
        _task(status="leased", lease_expires_at=None),
        _task(status="retry", lease_expires_at=None),
        _task(
            status="ambiguous",
            lease_expires_at=None,
            provider_acceptance_present=True,
            accepted_at="2026-07-11T05:00:10.000Z",
            last_failure_code="provider_result_ambiguous",
        ),
        _task(
            status="delivered",
            lease_expires_at=None,
            provider_acceptance_present=True,
            accepted_at="2026-07-11T05:00:12.000Z",
            completed_at="2026-07-11T05:00:10.000Z",
        ),
    )
    for payload in invalid_cases:
        with pytest.raises(IdentityDeliveryProtocolError) as caught:
            validate_identity_delivery_task(payload)
        assert caught.value.code == "identity_delivery_status_conflict"


def test_acceptance_dto_is_fail_closed_for_ambiguous_provider_results() -> None:
    accepted = validate_identity_delivery_acceptance(_acceptance())
    ambiguous = validate_identity_delivery_acceptance(
        _acceptance(
            status="ambiguous",
            provider_acceptance_present=False,
            accepted_at=None,
            failure_code="provider_result_ambiguous",
        )
    )

    assert isinstance(accepted, IdentityDeliveryAcceptanceDTO)
    assert ambiguous.accepted_at is None
    assert ambiguous.provider_acceptance_present is False

    with pytest.raises(IdentityDeliveryProtocolError) as caught:
        validate_identity_delivery_acceptance(
            _acceptance(status="ambiguous", failure_code="provider_result_ambiguous")
        )
    assert caught.value.code == "identity_delivery_status_conflict"


def test_redrive_requires_audited_generation_and_idempotency_rotation() -> None:
    request = validate_identity_delivery_redrive_request(_redrive_request())
    receipt = validate_identity_delivery_redrive_receipt(_redrive_receipt())

    assert isinstance(request, IdentityDeliveryRedriveRequestDTO)
    assert isinstance(receipt, IdentityDeliveryRedriveReceiptDTO)
    assert receipt.lease_generation == request.expected_lease_generation + 1
    assert receipt.provider_idempotency_key != receipt.previous_provider_idempotency_key

    with pytest.raises(IdentityDeliveryProtocolError) as generation_error:
        validate_identity_delivery_redrive_receipt(_redrive_receipt(lease_generation=6))
    assert generation_error.value.code == "identity_delivery_status_conflict"

    with pytest.raises(IdentityDeliveryProtocolError) as key_error:
        validate_identity_delivery_redrive_receipt(
            _redrive_receipt(
                provider_idempotency_key="identity-delivery:challenge_001:0"
            )
        )
    assert key_error.value.code == "identity_delivery_idempotency_conflict"


@pytest.mark.parametrize(
    ("kind", "payload", "dto_type"),
    (
        ("task", _task(), IdentityDeliveryTaskDTO),
        ("acceptance", _acceptance(), IdentityDeliveryAcceptanceDTO),
        ("redrive_request", _redrive_request(), IdentityDeliveryRedriveRequestDTO),
        ("redrive_receipt", _redrive_receipt(), IdentityDeliveryRedriveReceiptDTO),
    ),
)
def test_canonical_json_round_trips_every_delivery_dto_kind(
    kind: str, payload: dict[str, object], dto_type: type[object]
) -> None:
    canonical = canonical_identity_delivery_json(kind, payload)

    assert canonical == json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    assert isinstance(parse_identity_delivery_canonical_json(kind, canonical), dto_type)
    assert canonical_identity_delivery_json(
        kind, parse_identity_delivery_canonical_json(kind, canonical)
    ) == canonical


def test_canonical_json_rejects_whitespace_duplicates_and_unknown_fields() -> None:
    canonical = canonical_identity_delivery_json("task", _task())
    with pytest.raises(IdentityDeliveryProtocolError, match="not canonical"):
        parse_identity_delivery_canonical_json("task", canonical + "\n")

    duplicate = canonical.replace(
        '"accepted_at":null,',
        '"accepted_at":null,"accepted_at":null,',
        1,
    )
    with pytest.raises(IdentityDeliveryProtocolError, match="duplicate"):
        parse_identity_delivery_canonical_json("task", duplicate)

    unknown = _task()
    unknown["provider_name"] = "mail-relay"
    with pytest.raises(IdentityDeliveryProtocolError) as caught:
        validate_identity_delivery_task(unknown)
    assert caught.value.code == "identity_delivery_unknown_field"


@pytest.mark.parametrize(
    "payload",
    (
        {"destination": "masked"},
        {"nested": {"verification_code": "synthetic"}},
        {"nested": [{"opaque_ref": "masked"}]},
        {"metadata": "vault" + ":identity-delivery/example"},
        {"metadata": "person" + "@example.invalid"},
        {"metadata": "+8613800000000"},
        {"metadata": "Bearer " + "synthetic-token-value"},
    ),
)
def test_public_guard_rejects_raw_delivery_material_at_any_depth(
    payload: dict[str, object],
) -> None:
    with pytest.raises(IdentityDeliveryProtocolError) as caught:
        assert_public_identity_delivery_payload(payload)
    assert caught.value.code == "identity_delivery_secret_forbidden"
    assert "person@example.invalid" not in str(caught.value)
    assert "+8613800000000" not in str(caught.value)


def test_public_guard_accepts_only_presence_markers_and_operational_ids() -> None:
    public_payload = {
        "provider_acceptance_present": True,
        "provider_idempotency_key": "identity-delivery:challenge_001:0",
        "failure_code": "provider_timeout",
        "audit_id": "audit_001",
    }
    assert_public_identity_delivery_payload(public_payload)

    error = IdentityDeliveryProtocolError(
        "Bearer " + "synthetic-token-value",
        code="identity_delivery_secret_forbidden",
    )
    assert str(error) == "identity delivery payload rejected"


def test_validators_do_not_mutate_caller_payloads() -> None:
    samples = [
        (validate_identity_delivery_task, _task()),
        (validate_identity_delivery_acceptance, _acceptance()),
        (validate_identity_delivery_redrive_request, _redrive_request()),
        (validate_identity_delivery_redrive_receipt, _redrive_receipt()),
    ]
    for validator, payload in samples:
        before = deepcopy(payload)
        validator(payload)
        assert payload == before
