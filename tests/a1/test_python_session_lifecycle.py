from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping
from urllib.parse import urlparse

import pytest

from releasefoundry.session_lifecycle import (
    SESSION_LIFECYCLE_ERROR_CODES,
    SESSION_LIFECYCLE_SCHEMA_VERSION,
    RecentAuthDTO,
    SessionAccessToken,
    SessionAccessTokenDigest,
    SessionDTO,
    SessionLifecycleClient,
    SessionLifecycleError,
    SessionLifecycleStore,
    SessionRefreshToken,
    SessionRefreshTokenDigest,
    SessionRotationFamilyDigest,
    SessionTokenPair,
    SessionTokenPairReceipt,
    assert_public_session_payload,
    browser_session_refresh_route,
    session_collection_route,
    session_lifecycle_contract_manifest,
    session_recent_auth_route,
    session_recovery_invalidation_route,
    session_refresh_route,
    session_revoke_all_route,
    session_revoke_route,
)


NOW = datetime(2026, 7, 11, 4, 0, tzinfo=timezone.utc)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _store() -> SessionLifecycleStore:
    return SessionLifecycleStore(clock=lambda: NOW)


def _issue(
    store: SessionLifecycleStore,
    label: str = "primary",
    *,
    tenant_id: str = "tenant_main",
    project_id: str = "project_main",
    account_id: str = "account_main",
    authenticated_at: datetime = NOW,
    assurance_level: str = "aal1",
    access_lifetime: timedelta = timedelta(minutes=10),
    refresh_lifetime: timedelta = timedelta(hours=8),
    idempotency_key: str | None = None,
) -> SessionDTO:
    return store.issue_session(
        tenant_id,
        project_id,
        account_id,
        access_token_digest=_digest(f"access:{label}:0"),
        refresh_token_digest=_digest(f"refresh:{label}:0"),
        rotation_family_digest=_digest(f"family:{label}"),
        access_expires_at=NOW + access_lifetime,
        refresh_expires_at=NOW + refresh_lifetime,
        authenticated_at=authenticated_at,
        assurance_level=assurance_level,
        session_id=f"session_{label}",
        rotation_family_id=f"family_{label}",
        idempotency_key=idempotency_key or f"issue_{label}",
        now=NOW,
    )


def _refresh(
    store: SessionLifecycleStore,
    label: str = "primary",
    *,
    generation: int = 0,
    next_generation: int = 1,
    tenant_id: str = "tenant_main",
    project_id: str = "project_main",
    account_id: str = "account_main",
    idempotency_key: str | None = None,
    now: datetime = NOW + timedelta(minutes=1),
    access_expires_at: datetime | None = None,
    refresh_expires_at: datetime | None = None,
) -> SessionDTO:
    return store.refresh_session(
        tenant_id,
        project_id,
        account_id,
        current_refresh_token_digest=_digest(f"refresh:{label}:{generation}"),
        new_access_token_digest=_digest(f"access:{label}:{next_generation}"),
        new_refresh_token_digest=_digest(f"refresh:{label}:{next_generation}"),
        access_expires_at=access_expires_at or now + timedelta(minutes=10),
        refresh_expires_at=refresh_expires_at,
        idempotency_key=idempotency_key or f"refresh_{label}_{generation}",
        now=now,
    )


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in snapshot.items() if key != "integrity"}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_manifest_is_stable_public_safe_and_parity_ready() -> None:
    manifest = session_lifecycle_contract_manifest()

    assert manifest == {
        "schema_version": SESSION_LIFECYCLE_SCHEMA_VERSION,
        "statuses": ["active", "rotated", "revoked", "expired"],
        "stable_error_codes": list(SESSION_LIFECYCLE_ERROR_CODES),
        "routes": [
            {
                "operation": "session_issue",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions",
            },
            {
                "operation": "session_authenticate",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/authenticate",
            },
            {
                "operation": "session_list",
                "method": "GET",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions",
            },
            {
                "operation": "session_refresh",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/refresh",
            },
            {
                "operation": "browser_session_refresh",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh",
            },
            {
                "operation": "session_revoke",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/{session_id}/revoke",
            },
            {
                "operation": "session_revoke_all",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/revoke-all",
            },
            {
                "operation": "session_recent_auth",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/{session_id}/recent-auth",
            },
            {
                "operation": "session_recovery_invalidate",
                "method": "POST",
                "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/recovery-invalidate",
            },
        ],
        "invariants": {
            "tenant_project_account_isolation": True,
            "one_active_generation_per_rotation_family": True,
            "refresh_rotation_is_atomic": True,
            "reused_refresh_revokes_active_family": True,
            "revoke_one_is_scoped": True,
            "revoke_all_is_scoped": True,
            "recent_auth_uses_original_authentication_time": True,
            "recovery_invalidates_active_sessions": True,
            "snapshots_are_digest_only": True,
            "public_dto_excludes_token_digests": True,
            "access_refresh_token_classes_are_distinct": True,
            "session_token_receipts_are_one_time": True,
            "refresh_bearer_never_authenticates_as_access": True,
            "public_serialization_redacts_bearers": True,
        },
        "digest_only": True,
        "rotation": True,
        "reuse_detection": True,
        "revocation": True,
        "recent_auth": True,
        "recovery": True,
    }
    assert_public_session_payload(manifest)


def test_typed_tokens_derive_non_interchangeable_digests_for_the_store() -> None:
    store = _store()
    pair = SessionTokenPair(
        SessionAccessToken("access.primary.opaque-bearer"),
        SessionRefreshToken("refresh.primary.opaque-bearer"),
    )
    family_digest = SessionRotationFamilyDigest.from_material(
        "rotation.primary.opaque-material"
    )
    issued = store.issue_session(
        "tenant_main",
        "project_main",
        "account_main",
        access_token_digest=pair.access_digest(),
        refresh_token_digest=pair.refresh_digest(),
        rotation_family_digest=family_digest,
        access_expires_at=NOW + timedelta(minutes=10),
        refresh_expires_at=NOW + timedelta(hours=8),
        session_id="session_typed",
        rotation_family_id="family_typed",
        idempotency_key="issue_typed",
        now=NOW,
    )

    authenticated = store.authenticate_access(
        "tenant_main",
        "project_main",
        "account_main",
        access_token_digest=pair.access_digest(),
        now=NOW,
    )
    assert authenticated == issued
    with pytest.raises(SessionLifecycleError) as wrong_access:
        store.authenticate_access(
            "tenant_main",
            "project_main",
            "account_main",
            access_token_digest=pair.refresh_digest(),
            now=NOW,
        )
    assert wrong_access.value.code == "session_invalid_request"
    with pytest.raises(SessionLifecycleError) as wrong_refresh:
        store.refresh_session(
            "tenant_main",
            "project_main",
            "account_main",
            current_refresh_token_digest=pair.access_digest(),
            new_access_token_digest=SessionAccessTokenDigest(_digest("next-access")),
            new_refresh_token_digest=SessionRefreshTokenDigest(
                _digest("next-refresh")
            ),
            access_expires_at=NOW + timedelta(minutes=11),
            idempotency_key="wrong_refresh_class",
            now=NOW + timedelta(minutes=1),
        )
    assert wrong_refresh.value.code == "session_invalid_request"
    assert store.get_session(
        "tenant_main", "project_main", "account_main", "session_typed", now=NOW
    ).status == "active"


def test_token_pair_receipt_is_one_use_and_public_serialization_is_redacted() -> None:
    access_value = "access.receipt.private-bearer"
    refresh_value = "refresh.receipt.private-bearer"
    pair = SessionTokenPair(
        SessionAccessToken(access_value), SessionRefreshToken(refresh_value)
    )
    receipt = SessionTokenPairReceipt(
        session_id="session_receipt",
        key_version="session_hmac_v3",
        access_expires_at=NOW + timedelta(minutes=10),
        refresh_expires_at=NOW + timedelta(hours=8),
        token_pair=pair,
        now=NOW,
    )

    public_json = json.dumps(receipt.to_public_dict(), sort_keys=True)
    safe_text = repr(receipt) + repr(pair) + public_json
    assert access_value not in safe_text
    assert refresh_value not in safe_text
    assert pair.access_digest().for_storage() not in safe_text
    assert pair.refresh_digest().for_storage() not in safe_text
    assert receipt.to_public_dict()["access_token_present"] is True
    assert receipt.to_public_dict()["refresh_token_present"] is True

    transferred = receipt.take_token_pair()
    assert receipt.to_public_dict()["access_token_present"] is False
    assert receipt.to_public_dict()["refresh_token_present"] is False
    with pytest.raises(SessionLifecycleError):
        receipt.take_token_pair()
    assert transferred.take_access_token() == access_value
    with pytest.raises(SessionLifecycleError):
        transferred.take_access_token()
    assert transferred.to_public_dict() == {
        "access_token_present": False,
        "refresh_token_present": True,
    }
    assert transferred.take_refresh_token() == refresh_value
    assert transferred.to_public_dict() == {
        "access_token_present": False,
        "refresh_token_present": False,
    }


def test_token_objects_and_digests_never_serialize_raw_material() -> None:
    access_value = "access.serialization.private-bearer"
    refresh_value = "refresh.serialization.private-bearer"
    access = SessionAccessToken(access_value)
    refresh = SessionRefreshToken(refresh_value)
    access_digest = access.digest()
    refresh_digest = refresh.digest()

    safe = json.dumps(
        {
            "access": access.to_public_dict(),
            "refresh": refresh.to_public_dict(),
            "access_digest": access_digest.to_public_dict(),
            "refresh_digest": refresh_digest.to_public_dict(),
        },
        sort_keys=True,
    )
    rendered = " ".join(
        (repr(access), repr(refresh), repr(access_digest), repr(refresh_digest), safe)
    )
    assert access_value not in rendered
    assert refresh_value not in rendered
    assert access_digest.for_storage() not in rendered
    assert refresh_digest.for_storage() not in rendered
    assert_public_session_payload(json.loads(safe))


def test_token_receipt_rejects_invalid_or_expired_lifetimes_without_consuming() -> None:
    pair = SessionTokenPair(
        SessionAccessToken("access.expiry.private-bearer"),
        SessionRefreshToken("refresh.expiry.private-bearer"),
    )
    with pytest.raises(SessionLifecycleError):
        SessionTokenPairReceipt(
            session_id="session_expiry",
            key_version="session_hmac_v3",
            access_expires_at=NOW + timedelta(minutes=10),
            refresh_expires_at=NOW + timedelta(minutes=10),
            token_pair=pair,
            now=NOW,
        )
    with pytest.raises(SessionLifecycleError):
        SessionTokenPairReceipt(
            session_id="session_expiry",
            key_version="session_hmac_v3",
            access_expires_at=NOW,
            refresh_expires_at=NOW + timedelta(hours=1),
            token_pair=pair,
            now=NOW,
        )
    assert pair.to_public_dict() == {
        "access_token_present": True,
        "refresh_token_present": True,
    }
    pair.discard()


def test_issue_stores_digests_but_public_dto_exposes_only_presence_markers() -> None:
    store = _store()
    session = _issue(store)

    assert session.generation == 0
    assert session.status == "active"
    assert session.access_token_present is True
    assert session.refresh_token_present is True
    public_payload = session.to_dict()
    for forbidden in (
        "access_token_digest",
        "refresh_token_digest",
        "rotation_family_digest",
    ):
        assert forbidden not in public_payload
    snapshot_json = json.dumps(store.snapshot_state(), sort_keys=True)
    assert _digest("access:primary:0") in snapshot_json
    assert repr(store).find(_digest("access:primary:0")) == -1


def test_invalid_digest_is_rejected_without_echoing_caller_value() -> None:
    store = _store()
    caller_value = "not_a_sha256_digest"

    with pytest.raises(SessionLifecycleError) as captured:
        store.issue_session(
            "tenant_main",
            "project_main",
            "account_main",
            access_token_digest=caller_value,
            refresh_token_digest=_digest("refresh"),
            rotation_family_digest=_digest("family"),
            access_expires_at=NOW + timedelta(minutes=5),
            refresh_expires_at=NOW + timedelta(hours=1),
            idempotency_key="issue_invalid",
        )

    assert captured.value.code == "session_invalid_request"
    assert caller_value not in str(captured.value)
    assert store.list_sessions("tenant_main", "project_main", "account_main") == ()


def test_issue_replay_with_same_idempotency_key_returns_original_session() -> None:
    store = _store()
    first = _issue(store, idempotency_key="same_issue")
    second = _issue(store, idempotency_key="same_issue")

    assert second == first
    assert len(store.list_sessions("tenant_main", "project_main", "account_main")) == 1


def test_issue_idempotency_key_conflict_fails_without_second_session() -> None:
    store = _store()
    _issue(store, "first", idempotency_key="shared_issue_key")

    with pytest.raises(SessionLifecycleError) as captured:
        _issue(store, "second", idempotency_key="shared_issue_key")

    assert captured.value.code == "session_digest_conflict"
    sessions = store.list_sessions("tenant_main", "project_main", "account_main")
    assert [item.session_id for item in sessions] == ["session_first"]


def test_token_digest_collision_is_global_even_across_scopes() -> None:
    store = _store()
    _issue(store, "first")

    with pytest.raises(SessionLifecycleError) as captured:
        store.issue_session(
            "tenant_other",
            "project_other",
            "account_other",
            access_token_digest=_digest("access:first:0"),
            refresh_token_digest=_digest("refresh:other:0"),
            rotation_family_digest=_digest("family:other"),
            access_expires_at=NOW + timedelta(minutes=10),
            refresh_expires_at=NOW + timedelta(hours=1),
            session_id="session_other",
            rotation_family_id="family_other",
            idempotency_key="issue_other",
            now=NOW,
        )

    assert captured.value.code == "session_digest_conflict"
    assert store.list_sessions("tenant_other", "project_other", "account_other") == ()


def test_refresh_rotates_one_generation_and_preserves_session_family_and_auth_time() -> None:
    store = _store()
    issued = _issue(store, authenticated_at=NOW - timedelta(minutes=2))
    rotated = _refresh(store)

    assert rotated.session_id == issued.session_id
    assert rotated.rotation_family_id == issued.rotation_family_id
    assert rotated.generation == 1
    assert rotated.authenticated_at == issued.authenticated_at
    assert rotated.last_rotated_at == "2026-07-11T04:01:00.000000Z"
    snapshot = store.snapshot_state()
    generations = snapshot["families"][0]["generations"]
    assert [item["generation"] for item in generations] == [0, 1]
    assert [item["status"] for item in generations] == ["rotated", "active"]
    assert generations[0]["rotated_at"] == "2026-07-11T04:01:00.000000Z"


def test_same_refresh_idempotency_replay_does_not_trigger_reuse_detection() -> None:
    store = _store()
    _issue(store)
    first = _refresh(store, idempotency_key="same_refresh")
    second = _refresh(store, idempotency_key="same_refresh")

    assert second == first
    assert second.status == "active"
    assert len(store.snapshot_state()["families"][0]["generations"]) == 2


def test_old_refresh_reuse_revokes_every_generation_in_the_family() -> None:
    store = _store()
    _issue(store)
    current = _refresh(store)

    with pytest.raises(SessionLifecycleError) as captured:
        _refresh(
            store,
            generation=0,
            next_generation=2,
            idempotency_key="attacker_reuse",
            now=NOW + timedelta(minutes=2),
        )

    assert captured.value.code == "session_refresh_reused"
    revoked = store.get_session(
        "tenant_main", "project_main", "account_main", current.session_id
    )
    assert revoked.status == "revoked"
    assert revoked.revoke_reason_code == "refresh_reuse_detected"
    assert all(
        generation["status"] == "revoked"
        and generation["revoke_reason_code"] == "refresh_reuse_detected"
        for generation in store.snapshot_state()["families"][0]["generations"]
    )
    with pytest.raises(SessionLifecycleError) as access_failure:
        store.authenticate_access(
            "tenant_main",
            "project_main",
            "account_main",
            access_token_digest=_digest("access:primary:1"),
            now=NOW + timedelta(minutes=2),
        )
    assert access_failure.value.code == "session_refresh_reused"


def test_cross_scope_refresh_probe_does_not_revoke_the_matching_family() -> None:
    store = _store()
    _issue(store)
    current = _refresh(store)

    with pytest.raises(SessionLifecycleError) as captured:
        _refresh(
            store,
            generation=0,
            next_generation=2,
            tenant_id="tenant_other",
            project_id="project_other",
            account_id="account_other",
            idempotency_key="cross_scope_probe",
            now=NOW + timedelta(minutes=2),
        )

    assert captured.value.code == "session_scope_mismatch"
    assert store.get_session(
        "tenant_main", "project_main", "account_main", current.session_id
    ).status == "active"


def test_access_expiry_boundary_blocks_access_but_still_allows_refresh() -> None:
    store = _store()
    _issue(store, access_lifetime=timedelta(minutes=5))
    boundary = NOW + timedelta(minutes=5)

    with pytest.raises(SessionLifecycleError) as captured:
        store.authenticate_access(
            "tenant_main",
            "project_main",
            "account_main",
            access_token_digest=_digest("access:primary:0"),
            now=boundary,
        )
    assert captured.value.code == "session_expired"
    assert _refresh(store, now=boundary).generation == 1


def test_refresh_expiry_boundary_is_closed_and_marks_session_expired() -> None:
    store = _store()
    _issue(
        store,
        access_lifetime=timedelta(minutes=5),
        refresh_lifetime=timedelta(minutes=20),
    )

    with pytest.raises(SessionLifecycleError) as captured:
        _refresh(store, now=NOW + timedelta(minutes=20))

    assert captured.value.code == "session_expired"
    assert store.get_session(
        "tenant_main",
        "project_main",
        "account_main",
        "session_primary",
        now=NOW + timedelta(minutes=20),
    ).status == "expired"


def test_refresh_cannot_extend_absolute_family_lifetime() -> None:
    store = _store()
    _issue(store, refresh_lifetime=timedelta(hours=1))

    with pytest.raises(SessionLifecycleError, match="cannot extend"):
        _refresh(
            store,
            refresh_expires_at=NOW + timedelta(hours=2),
        )
    assert store.get_session(
        "tenant_main", "project_main", "account_main", "session_primary"
    ).generation == 0


def test_revoke_one_revokes_one_family_and_is_state_and_key_idempotent() -> None:
    store = _store()
    _issue(store, "first")
    _issue(store, "second")
    first = store.revoke_session(
        "tenant_main",
        "project_main",
        "account_main",
        "session_first",
        idempotency_key="revoke_first",
        now=NOW + timedelta(minutes=1),
    )
    replay = store.revoke_session(
        "tenant_main",
        "project_main",
        "account_main",
        "session_first",
        idempotency_key="revoke_first",
        now=NOW + timedelta(minutes=2),
    )
    repeated = store.revoke_session(
        "tenant_main",
        "project_main",
        "account_main",
        "session_first",
        idempotency_key="revoke_first_again",
        now=NOW + timedelta(minutes=2),
    )

    assert first == replay
    assert first.revoked_count == 1
    assert repeated.revoked_count == 0
    assert store.get_session(
        "tenant_main", "project_main", "account_main", "session_second"
    ).status == "active"


def test_revoke_all_isolated_by_tenant_project_and_account() -> None:
    store = _store()
    _issue(store, "target_one")
    _issue(store, "target_two")
    _issue(store, "other_account", account_id="account_other")
    _issue(store, "other_project", project_id="project_other")
    _issue(store, "other_tenant", tenant_id="tenant_other")

    result = store.revoke_all_sessions(
        "tenant_main",
        "project_main",
        "account_main",
        idempotency_key="revoke_all_target",
        now=NOW + timedelta(minutes=1),
    )

    assert result.revoked_count == 2
    assert set(result.revoked_session_ids) == {
        "session_target_one",
        "session_target_two",
    }
    for tenant, project, account, session_id in (
        ("tenant_main", "project_main", "account_other", "session_other_account"),
        ("tenant_main", "project_other", "account_main", "session_other_project"),
        ("tenant_other", "project_main", "account_main", "session_other_tenant"),
    ):
        assert store.get_session(tenant, project, account, session_id).status == "active"


def test_recent_auth_accepts_exact_boundary_and_rejects_one_microsecond_later() -> None:
    store = _store()
    session = _issue(store)
    boundary = NOW + timedelta(minutes=5)

    recent = store.assert_recent_auth(
        "tenant_main",
        "project_main",
        "account_main",
        session.session_id,
        max_age_seconds=300,
        now=boundary,
    )
    assert isinstance(recent, RecentAuthDTO)
    assert recent.recent is True
    assert recent.valid_until == "2026-07-11T04:05:00.000000Z"

    with pytest.raises(SessionLifecycleError) as captured:
        store.assert_recent_auth(
            "tenant_main",
            "project_main",
            "account_main",
            session.session_id,
            max_age_seconds=300,
            now=boundary + timedelta(microseconds=1),
        )
    assert captured.value.code == "session_recent_auth_required"


def test_recent_auth_requires_assurance_and_refresh_does_not_make_auth_recent() -> None:
    store = _store()
    session = _issue(store, authenticated_at=NOW - timedelta(minutes=30))
    refreshed = _refresh(store)
    assert refreshed.authenticated_at == session.authenticated_at

    with pytest.raises(SessionLifecycleError) as stale:
        store.assert_recent_auth(
            "tenant_main",
            "project_main",
            "account_main",
            session.session_id,
            max_age_seconds=300,
            now=NOW + timedelta(minutes=1),
        )
    assert stale.value.code == "session_recent_auth_required"

    fresh_store = _store()
    aal1 = _issue(fresh_store, "aal1")
    with pytest.raises(SessionLifecycleError) as assurance:
        fresh_store.assert_recent_auth(
            "tenant_main",
            "project_main",
            "account_main",
            aal1.session_id,
            max_age_seconds=300,
            minimum_assurance_level="aal2",
            now=NOW,
        )
    assert assurance.value.code == "session_recent_auth_required"


def test_recovery_invalidation_is_scoped_idempotent_and_conflict_checked() -> None:
    store = _store()
    _issue(store, "target")
    _issue(store, "other", account_id="account_other")
    first = store.invalidate_for_recovery(
        "tenant_main",
        "project_main",
        "account_main",
        "recovery_one",
        idempotency_key="recovery_invalidate",
        now=NOW + timedelta(minutes=1),
    )
    replay = store.invalidate_for_recovery(
        "tenant_main",
        "project_main",
        "account_main",
        "recovery_one",
        idempotency_key="recovery_invalidate",
        now=NOW + timedelta(minutes=2),
    )

    assert first == replay
    assert first.reason_code == "account_recovery"
    assert first.revoked_session_ids == ("session_target",)
    assert store.get_session(
        "tenant_main", "project_main", "account_other", "session_other"
    ).status == "active"
    with pytest.raises(SessionLifecycleError) as conflict:
        store.invalidate_for_recovery(
            "tenant_main",
            "project_main",
            "account_main",
            "recovery_two",
            idempotency_key="recovery_invalidate",
            now=NOW + timedelta(minutes=2),
        )
    assert conflict.value.code == "session_digest_conflict"


def test_snapshot_restore_preserves_rotation_tombstones_and_idempotency() -> None:
    store = _store()
    _issue(store, idempotency_key="issue_replay_after_restore")
    rotated = _refresh(store, idempotency_key="refresh_replay_after_restore")
    snapshot = store.snapshot_state()
    restored = SessionLifecycleStore.from_snapshot(snapshot, clock=lambda: NOW)

    assert restored.get_session(
        "tenant_main", "project_main", "account_main", rotated.session_id
    ) == rotated
    assert _issue(
        restored, idempotency_key="issue_replay_after_restore"
    ).session_id == rotated.session_id
    assert _refresh(
        restored, idempotency_key="refresh_replay_after_restore"
    ) == rotated

    with pytest.raises(SessionLifecycleError) as reuse:
        _refresh(
            restored,
            generation=0,
            next_generation=2,
            idempotency_key="reuse_after_restore",
            now=NOW + timedelta(minutes=2),
        )
    assert reuse.value.code == "session_refresh_reused"


def test_restore_rejects_integrity_tampering_atomically() -> None:
    store = _store()
    original = _issue(store)
    tampered = deepcopy(store.snapshot_state())
    tampered["families"][0]["generations"][0]["generation"] = 7

    with pytest.raises(SessionLifecycleError) as captured:
        store.restore_state(tampered)

    assert captured.value.code == "session_invalid_request"
    assert store.get_session(
        "tenant_main", "project_main", "account_main", original.session_id
    ) == original


def test_restore_rejects_structurally_invalid_but_rehashed_snapshot() -> None:
    store = _store()
    _issue(store)
    tampered = deepcopy(store.snapshot_state())
    tampered["families"][0]["generations"][0]["status"] = "rotated"
    tampered["integrity"]["payload_sha256"] = _snapshot_digest(tampered)

    with pytest.raises(SessionLifecycleError) as captured:
        SessionLifecycleStore.from_snapshot(tampered, clock=lambda: NOW)

    assert captured.value.code == "session_invalid_request"


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "access_token",
        "accessTokenDigest",
        "refresh-token",
        "refreshTokenDigest",
        "rotationFamilyDigest",
        "Authorization",
        "clientSecret",
        "session_token",
    ],
)
def test_public_guard_rejects_recursive_secret_and_digest_aliases(
    forbidden_key: str,
) -> None:
    with pytest.raises(SessionLifecycleError) as captured:
        assert_public_session_payload(
            {"safe": [{"nested": {forbidden_key: "synthetic_value"}}]}
        )
    assert captured.value.code == "session_invalid_request"


def test_public_guard_rejects_credential_shaped_values_under_safe_keys() -> None:
    credential_value = "Bearer " + ".".join(["a" * 16, "b" * 16, "c" * 12])
    with pytest.raises(SessionLifecycleError) as captured:
        assert_public_session_payload({"message": credential_value})
    assert captured.value.code == "session_invalid_request"
    assert credential_value not in str(captured.value)


def test_public_dto_rejects_unknown_fields_and_inconsistent_revocation() -> None:
    payload = _issue(_store()).to_dict()
    with pytest.raises(SessionLifecycleError, match="fields"):
        SessionDTO.from_public_response({**payload, "metadata": {"safe": True}})
    with pytest.raises(SessionLifecycleError, match="revocation metadata"):
        SessionDTO.from_public_response(
            {**payload, "status": "revoked"}
        )


def test_route_builders_encode_every_scope_segment_and_use_manifest_paths() -> None:
    collection = session_collection_route("project/one", "account?one")
    assert collection == (
        "/v1/projects/project%2Fone/accounts/account%3Fone/sessions"
    )
    assert session_refresh_route("p", "a").endswith("/sessions/refresh")
    assert browser_session_refresh_route("p", "a").endswith(
        "/browser-sessions/refresh"
    )
    assert session_revoke_route("p", "a", "session/one").endswith(
        "/session%2Fone/revoke"
    )
    assert session_revoke_all_route("p", "a").endswith("/revoke-all")
    assert session_recent_auth_route("p", "a", "s").endswith("/s/recent-auth")
    assert session_recovery_invalidation_route("p", "a").endswith(
        "/recovery-invalidate"
    )


def test_typed_client_uses_routes_without_putting_credentials_in_payloads() -> None:
    public_session = _issue(_store()).to_dict()
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def transport(
        method: str, url: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        path = urlparse(url).path
        calls.append((method, path, dict(payload)))
        if path.endswith("/refresh"):
            return {"result": {**public_session, "generation": 1}}
        if path.endswith("/recent-auth"):
            return {
                "result": {
                    "schema_version": SESSION_LIFECYCLE_SCHEMA_VERSION,
                    "tenant_id": "tenant_main",
                    "project_id": "project_main",
                    "account_id": "account_main",
                    "session_id": "session_primary",
                    "assurance_level": "aal1",
                    "authenticated_at": "2026-07-11T04:00:00Z",
                    "valid_until": "2026-07-11T04:05:00Z",
                    "recent": True,
                }
            }
        return {"sessions": [public_session]}

    client = SessionLifecycleClient("https://api.example.invalid/", transport=transport)
    assert len(client.list_sessions("tenant_main", "project_main", "account_main")) == 1
    assert client.refresh_session(
        "tenant_main",
        "project_main",
        "account_main",
        "session_primary",
        idempotency_key="client_refresh",
    ).generation == 1
    assert client.assert_recent_auth(
        "tenant_main",
        "project_main",
        "account_main",
        "session_primary",
        max_age_seconds=300,
    ).recent is True
    serialized_calls = json.dumps(calls, sort_keys=True)
    for forbidden in (
        "access_token",
        "refresh_token",
        "token_digest",
        "authorization",
        "cookie",
    ):
        assert forbidden not in serialized_calls.lower()
    assert calls[1] == (
        "POST",
        "/v1/projects/project_main/accounts/account_main/sessions/refresh",
        {
            "tenant_id": "tenant_main",
            "session_id": "session_primary",
            "idempotency_key": "client_refresh",
        },
    )


def test_typed_client_issue_authenticate_and_rotate_send_digests_only() -> None:
    public_session = _issue(_store()).to_dict()
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def transport(
        method: str, url: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        calls.append((method, urlparse(url).path, dict(payload)))
        return {"result": {**public_session, "generation": len(calls) - 1}}

    client = SessionLifecycleClient(
        "https://api.example.invalid", transport=transport
    )
    client.issue_session(
        "tenant_main",
        "project_main",
        "account_main",
        access_token_digest=_digest("client_access_0"),
        refresh_token_digest=_digest("client_refresh_0"),
        rotation_family_digest=_digest("client_family"),
        access_expires_at=NOW + timedelta(minutes=5),
        refresh_expires_at=NOW + timedelta(hours=1),
    )
    client.authenticate_access_token(
        "tenant_main",
        "project_main",
        "account_main",
        access_token_digest=_digest("client_access_0"),
    )
    client.rotate_refresh_token(
        "tenant_main",
        "project_main",
        "account_main",
        refresh_token_digest=_digest("client_refresh_0"),
        next_access_token_digest=_digest("client_access_1"),
        next_refresh_token_digest=_digest("client_refresh_1"),
        access_expires_at=NOW + timedelta(minutes=10),
        refresh_expires_at=NOW + timedelta(hours=2),
    )

    assert [call[1] for call in calls] == [
        "/v1/projects/project_main/accounts/account_main/sessions",
        "/v1/projects/project_main/accounts/account_main/sessions/authenticate",
        "/v1/projects/project_main/accounts/account_main/sessions/refresh",
    ]
    assert calls[0][2]["access_token_digest"] == _digest("client_access_0")
    assert calls[2][2]["next_refresh_token_digest"] == _digest("client_refresh_1")
    assert all("access_token" not in payload for _, _, payload in calls)
    assert all("refresh_token" not in payload for _, _, payload in calls)


def test_client_rejects_secret_response_and_sanitizes_transport_failure() -> None:
    client = SessionLifecycleClient(
        "https://api.example.invalid",
        transport=lambda *_args: {
            "result": {"nested": {"refreshToken": "synthetic_value"}}
        },
    )
    with pytest.raises(SessionLifecycleError) as secret:
        client.get_session(
            "tenant_main", "project_main", "account_main", "session_primary"
        )
    assert secret.value.code == "session_invalid_request"

    failure_value = "Bearer " + "private.transport.value"

    def failing_transport(*_args: Any) -> Mapping[str, Any]:
        raise RuntimeError(failure_value)

    failing_client = SessionLifecycleClient(
        "https://api.example.invalid", transport=failing_transport
    )
    with pytest.raises(SessionLifecycleError) as transport_failure:
        failing_client.get_session(
            "tenant_main", "project_main", "account_main", "session_primary"
        )
    assert transport_failure.value.code == "session_store_failed"
    assert failure_value not in str(transport_failure.value)


def test_client_preserves_stable_error_code_and_redacts_bare_digest_detail() -> None:
    private_digest = _digest("private_server_detail")
    client = SessionLifecycleClient(
        "https://api.example.invalid",
        transport=lambda *_args: {
            "error": {
                "code": "session_refresh_reused",
                "message": f"refresh reuse detail {private_digest}",
                "retryable": False,
            }
        },
    )

    with pytest.raises(SessionLifecycleError) as captured:
        client.refresh_session(
            "tenant_main",
            "project_main",
            "account_main",
            "session_primary",
            idempotency_key="client_error",
        )
    assert captured.value.code == "session_refresh_reused"
    assert private_digest not in str(captured.value)
