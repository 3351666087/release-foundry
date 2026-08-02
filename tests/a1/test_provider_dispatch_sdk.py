from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import pytest

from packages.sdk.releasefoundry.provider_dispatch import (
    PROVIDER_DISPATCH_CLIENT_VERSION,
    PROVIDER_DISPATCH_STATES,
    ProviderDispatchClient,
    ProviderDispatchConflict,
    ProviderDispatchError,
    ProviderDispatchFenceRejected,
    ProviderDispatchReservation,
    ProviderDispatchScope,
    ProviderDispatchValidationError,
    provider_dispatch_capability_manifest,
)

SCOPE = ProviderDispatchScope("tenant_dispatch", "project_dispatch")
DIGEST = hashlib.sha256(b"dispatch").hexdigest()
NOW = "2026-07-12T12:00:00Z"


def dispatch(
    *,
    status: str = "pending",
    fencing_token: int = 0,
    lease_owner_id: str | None = None,
    stream_observed: bool = False,
) -> dict[str, Any]:
    leased = status in {"claimed", "reconciling"}
    return {
        "schema_version": PROVIDER_DISPATCH_CLIENT_VERSION,
        "tenant_id": SCOPE.tenant_id,
        "project_id": SCOPE.project_id,
        "dispatch_id": "dispatch_1",
        "provider": "openai-compatible",
        "operation": "responses.create",
        "request_fingerprint": DIGEST,
        "status": status,
        "attempts": 1 if fencing_token else 0,
        "fencing_token": fencing_token,
        "lease_owner_id": lease_owner_id,
        "lease_expires_at": NOW if leased else None,
        "provider_request_id": None,
        "stream_observed": stream_observed,
        "stream_observed_sha256": DIGEST if stream_observed else None,
        "stream_observed_fencing_token": fencing_token if stream_observed else None,
        "stream_observed_at": NOW if stream_observed else None,
        "terminal_proof_sha256": DIGEST if status == "completed" else None,
        "terminal_response_sha256": DIGEST if status == "completed" else None,
        "reconciliation_reason": "ambiguous_commit" if status == "indeterminate" else None,
        "reconciliation_attempts": 1 if status == "reconciling" else 0,
        "next_reconcile_at": NOW if status == "indeterminate" else None,
        "last_error_sha256": None,
        "created_at": NOW,
        "updated_at": NOW,
        "claimed_at": NOW if leased else None,
        "completed_at": NOW if status == "completed" else None,
        "failed_at": NOW if status == "failed" else None,
        "raw_payload_included": False,
    }


def envelope(result: Mapping[str, Any], *, status: str = "ok") -> dict[str, Any]:
    return {"operation": "provider.dispatch.test", "status": status, "result": result}


class ScriptedTransport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[
            tuple[str, str, Mapping[str, Any] | None, Mapping[str, str]]
        ] = []

    def __call__(self, method, url, payload, headers):
        self.calls.append((method, url, payload, headers))
        return self.responses.pop(0)


def client(
    responses: list[Mapping[str, Any]],
) -> tuple[ProviderDispatchClient, ScriptedTransport]:
    transport = ScriptedTransport(responses)
    return (
        ProviderDispatchClient(
            base_url="https://runtime.example.invalid/",
            transport=transport,
            api_key_id="key_public_handle",
        ),
        transport,
    )


def test_manifest_declares_one_go_wire_contract():
    manifest = provider_dispatch_capability_manifest()

    assert manifest["schema_version"] == "releasefoundry.provider_dispatch.v1"
    assert set(manifest["states"]) == PROVIDER_DISPATCH_STATES
    assert manifest["routes"] == [
        "submit",
        "claim",
        "heartbeat",
        "observe-stream",
        "complete",
        "indeterminate",
        "reconciliation/claim",
        "get",
    ]
    assert manifest["capabilities"]["authoritative_store"] == "postgresql"


def test_submit_uses_plural_collection_and_go_payload():
    sdk, transport = client([envelope(dispatch())])

    result = sdk.submit(
        SCOPE,
        provider="openai-compatible",
        operation="responses.create",
        request={"model": "local-model", "input": "hello"},
        dispatch_id="dispatch_1",
    )

    assert result.status == "pending"
    method, url, payload, headers = transport.calls[0]
    assert method == "POST"
    assert url.endswith(
        "/v1/tenants/tenant_dispatch/projects/project_dispatch/provider-dispatches"
    )
    assert payload == {
        "provider": "openai-compatible",
        "operation": "responses.create",
        "request": {"model": "local-model", "input": "hello"},
        "dispatch_id": "dispatch_1",
    }
    assert headers["X-ReleaseFoundry-SDK-Version"] == PROVIDER_DISPATCH_CLIENT_VERSION
    assert headers["X-ReleaseFoundry-Api-Key-Id"] == "key_public_handle"
    assert "Authorization" not in headers


def test_reservation_compatibility_alias_submits_canonical_payload():
    sdk, _ = client([envelope(dispatch())])
    reservation = ProviderDispatchReservation(
        scope=SCOPE,
        provider="openai-compatible",
        operation="responses.create",
        request={"model": "local-model"},
        dispatch_id="dispatch_1",
    )

    assert sdk.reserve(reservation).dispatch_id == "dispatch_1"


def test_collection_claim_and_reconciliation_claim_share_claim_shape():
    sdk, transport = client(
        [
            envelope(
                {
                    "schema_version": PROVIDER_DISPATCH_CLIENT_VERSION,
                    "status": "claimed",
                    "claimed": True,
                    "dispatch": dispatch(
                        status="claimed",
                        fencing_token=1,
                        lease_owner_id="worker_1",
                    ),
                }
            ),
            envelope(
                {
                    "schema_version": PROVIDER_DISPATCH_CLIENT_VERSION,
                    "status": "empty",
                    "claimed": False,
                },
                status="empty",
            ),
        ]
    )

    claim = sdk.claim_next(
        SCOPE,
        lease_owner_id="worker_1",
        provider="openai-compatible",
        operation="responses.create",
    )
    empty = sdk.claim_reconciliation(SCOPE, lease_owner_id="reconciler_1")

    assert claim.claimed is True
    assert claim.dispatch is not None and claim.dispatch.status == "claimed"
    assert empty.claimed is False and empty.dispatch is None
    assert transport.calls[0][1].endswith("/provider-dispatches/claim")
    assert transport.calls[1][1].endswith(
        "/provider-dispatches/reconciliation/claim"
    )


def test_lifecycle_routes_and_payloads_are_canonical():
    sdk, transport = client(
        [
            envelope(
                dispatch(
                    status="claimed",
                    fencing_token=1,
                    lease_owner_id="worker_1",
                )
            ),
            envelope(
                dispatch(
                    status="claimed",
                    fencing_token=1,
                    lease_owner_id="worker_1",
                    stream_observed=True,
                )
            ),
            envelope(dispatch(status="completed", fencing_token=1)),
            envelope(dispatch(status="indeterminate", fencing_token=1)),
            envelope(dispatch(status="indeterminate", fencing_token=1)),
        ]
    )

    sdk.heartbeat(
        SCOPE,
        "dispatch_1",
        lease_owner_id="worker_1",
        fencing_token=1,
        lease_seconds=45,
    )
    sdk.observe_stream(
        SCOPE,
        "dispatch_1",
        lease_owner_id="worker_1",
        fencing_token=1,
        stream={"digest": DIGEST, "frame_count": 2},
    )
    sdk.complete(
        SCOPE,
        "dispatch_1",
        lease_owner_id="worker_1",
        fencing_token=1,
        proof={"digest": DIGEST},
        response={"digest": DIGEST},
        provider_request_id="provider_request_1",
    )
    sdk.mark_indeterminate(
        SCOPE,
        "dispatch_1",
        lease_owner_id="worker_1",
        fencing_token=1,
        reconciliation_reason="ambiguous_commit",
        retry_after_seconds=10,
    )
    sdk.get(SCOPE, "dispatch_1")

    suffixes = [call[1].split("dispatch_1")[-1] for call in transport.calls]
    assert suffixes == [
        "/heartbeat",
        "/observe-stream",
        "/complete",
        "/indeterminate",
        "",
    ]
    assert transport.calls[0][2]["lease_owner_id"] == "worker_1"
    assert transport.calls[1][2]["stream"]["frame_count"] == 2
    assert transport.calls[2][2]["proof"] == {"digest": DIGEST}
    assert transport.calls[3][2]["reconciliation_reason"] == "ambiguous_commit"
    assert transport.calls[4][0] == "GET"


def test_response_scope_and_raw_payload_fail_closed():
    cross_scope = dispatch()
    cross_scope["tenant_id"] = "other_tenant"
    sdk, _ = client([envelope(cross_scope)])
    with pytest.raises(ProviderDispatchValidationError, match="crossed"):
        sdk.get(SCOPE, "dispatch_1")

    unsafe = dispatch()
    unsafe["raw_payload_included"] = True
    sdk, _ = client([envelope(unsafe)])
    with pytest.raises(ProviderDispatchValidationError, match="raw payload"):
        sdk.get(SCOPE, "dispatch_1")


def test_remote_errors_are_stable_typed_and_redacted():
    sdk, _ = client(
        [
            {
                "error": {
                    "code": "provider_dispatch_conflict",
                    "message": "conflict for sk-private-secret",
                    "status_code": 409,
                    "retryable": False,
                    "details": {"api_key": "sk-private-secret"},
                }
            },
            {
                "error": {
                    "code": "provider_dispatch_fence",
                    "message": "stale fence",
                    "status_code": 409,
                    "retryable": False,
                }
            },
        ]
    )

    with pytest.raises(ProviderDispatchConflict) as conflict:
        sdk.get(SCOPE, "dispatch_1")
    assert conflict.value.code == "provider_dispatch_conflict"
    assert "sk-private-secret" not in str(conflict.value)
    assert conflict.value.details["api_key"] == "[redacted]"

    with pytest.raises(ProviderDispatchFenceRejected):
        sdk.heartbeat(
            SCOPE,
            "dispatch_1",
            lease_owner_id="worker_1",
            fencing_token=1,
        )


@pytest.mark.parametrize(
    "code",
    [
        "provider_dispatch_cancelled",
        "provider_dispatch_deadline",
        "provider_dispatch_contention",
        "provider_dispatch_unavailable",
        "provider_dispatch_indeterminate",
    ],
)
def test_operational_errors_preserve_only_stable_public_codes(code):
    sdk, _ = client(
        [
            {
                "error": {
                    "code": code,
                    "message": code,
                    "retryable": code
                    in {
                        "provider_dispatch_contention",
                        "provider_dispatch_unavailable",
                    },
                }
            }
        ]
    )

    with pytest.raises(ProviderDispatchError) as exc:
        sdk.get(SCOPE, "dispatch_1")
    assert exc.value.code == code
    assert exc.value.message == code


def test_unknown_remote_and_transport_errors_never_expose_credentials():
    sdk, _ = client(
        [
            {
                "error": {
                    "code": "sql_relation_missing",
                    "message": "postgres password=private-db-password",
                }
            }
        ]
    )
    with pytest.raises(ProviderDispatchError) as remote:
        sdk.get(SCOPE, "dispatch_1")
    assert remote.value.code == "provider_dispatch_transport"
    assert "private-db-password" not in str(remote.value)

    def failing_transport(method, url, payload, headers):
        raise RuntimeError("authorization=Bearer live-provider-secret")

    sdk = ProviderDispatchClient(
        base_url="https://runtime.example.invalid",
        transport=failing_transport,
    )
    with pytest.raises(ProviderDispatchError) as local:
        sdk.get(SCOPE, "dispatch_1")
    assert local.value.code == "provider_dispatch_transport"
    assert "live-provider-secret" not in str(local.value)
    assert "[redacted]" in str(local.value)


def test_secret_bearing_submit_is_rejected_before_transport():
    sdk, transport = client([])

    with pytest.raises(ProviderDispatchValidationError, match="must not contain secrets"):
        sdk.submit(
            SCOPE,
            provider="openai-compatible",
            operation="responses.create",
            request={"api_key": "private"},
        )
    assert transport.calls == []
    assert "private" not in json.dumps(transport.calls)
