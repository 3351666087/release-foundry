from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.parse import quote

from .api_client import redact_sensitive, redact_text

JsonDict = dict[str, Any]

PROVIDER_DISPATCH_CLIENT_VERSION = "releasefoundry.provider_dispatch.v1"
PROVIDER_DISPATCH_STATES = frozenset(
    {
        "pending",
        "claimed",
        "indeterminate",
        "reconciling",
        "completed",
        "failed",
        "cancelled",
    }
)
PROVIDER_DISPATCH_TERMINAL_STATES = frozenset(
    {"completed", "failed", "cancelled"}
)
PROVIDER_DISPATCH_RECONCILIATION_OUTCOMES = PROVIDER_DISPATCH_TERMINAL_STATES
PROVIDER_DISPATCH_ERROR_CODES = frozenset(
    {
        "provider_dispatch_conflict",
        "provider_dispatch_fence",
        "provider_dispatch_not_found",
        "provider_dispatch_cancelled",
        "provider_dispatch_deadline",
        "provider_dispatch_contention",
        "provider_dispatch_unavailable",
        "provider_dispatch_indeterminate",
        "provider_dispatch_validation",
        "provider_dispatch_transport",
    }
)
PROVIDER_DISPATCH_CAPABILITIES = {
    "authoritative_store": "postgresql",
    "transactional_claim": True,
    "skip_locked_claim": True,
    "lease_heartbeat": True,
    "monotonic_fencing_token": True,
    "request_fingerprint_conflict_detection": True,
    "terminal_stream_proof_binding": True,
    "indeterminate_reconciliation": True,
    "tenant_project_isolation": True,
    "raw_request_persisted": False,
    "raw_response_persisted": False,
    "credentials_persisted": False,
}


class ProviderDispatchTransport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None,
        headers: Mapping[str, str],
    ) -> Mapping[str, Any]: ...


class ProviderDispatchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_dispatch_transport",
        status_code: int | None = None,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if code not in PROVIDER_DISPATCH_ERROR_CODES:
            code = "provider_dispatch_transport"
        safe_message = redact_text(message)
        super().__init__(safe_message)
        self.message = safe_message
        self.code = code
        self.status_code = status_code
        self.retryable = bool(retryable)
        self.details = redact_sensitive(details or {})

    def to_dict(self) -> JsonDict:
        return {
            "code": self.code,
            "message": self.message,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "details": self.details,
        }


class ProviderDispatchConflict(ProviderDispatchError):
    pass


class ProviderDispatchFenceRejected(ProviderDispatchError):
    pass


class ProviderDispatchLeaseExpired(ProviderDispatchFenceRejected):
    """Compatibility alias: expired leases are represented by fence rejection."""


class ProviderDispatchNotFound(ProviderDispatchError):
    pass


class ProviderDispatchValidationError(ProviderDispatchError, ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderDispatchScope:
    tenant_id: str
    project_id: str

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")


@dataclass(frozen=True, slots=True)
class ProviderDispatchReservation:
    """Canonical submit request. The historical name remains source-compatible."""

    scope: ProviderDispatchScope
    provider: str
    operation: str
    request: JsonDict
    dispatch_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ProviderDispatchScope):
            raise TypeError("scope must be ProviderDispatchScope")
        _identifier(self.provider, "provider")
        _identifier(self.operation, "operation")
        _safe_mapping(self.request, "request")
        if self.dispatch_id is not None:
            _identifier(self.dispatch_id, "dispatch_id")

    def to_payload(self) -> JsonDict:
        payload: JsonDict = {
            "provider": self.provider,
            "operation": self.operation,
            "request": redact_sensitive(self.request),
        }
        if self.dispatch_id is not None:
            payload["dispatch_id"] = self.dispatch_id
        return payload


@dataclass(frozen=True, slots=True)
class ProviderDispatchEntry:
    schema_version: str
    tenant_id: str
    project_id: str
    dispatch_id: str
    provider: str
    operation: str
    request_fingerprint: str
    status: str
    attempts: int
    fencing_token: int
    lease_owner_id: str | None = None
    lease_expires_at: str | None = None
    provider_request_id: str | None = None
    stream_observed: bool = False
    stream_observed_sha256: str | None = None
    stream_observed_fencing_token: int | None = None
    stream_observed_at: str | None = None
    terminal_proof_sha256: str | None = None
    terminal_response_sha256: str | None = None
    reconciliation_reason: str | None = None
    reconciliation_attempts: int = 0
    next_reconcile_at: str | None = None
    last_error_sha256: str | None = None
    created_at: str = ""
    updated_at: str = ""
    claimed_at: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None
    raw_payload_included: bool = False

    @property
    def entry_id(self) -> str:
        return self.dispatch_id

    @property
    def state(self) -> str:
        return self.status

    @property
    def attempt_count(self) -> int:
        return self.attempts

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], *, expected_scope: ProviderDispatchScope
    ) -> "ProviderDispatchEntry":
        entry = cls(
            schema_version=_required_string(payload.get("schema_version"), "schema_version"),
            tenant_id=_identifier(payload.get("tenant_id"), "tenant_id"),
            project_id=_identifier(payload.get("project_id"), "project_id"),
            dispatch_id=_identifier(payload.get("dispatch_id"), "dispatch_id"),
            provider=_identifier(payload.get("provider"), "provider"),
            operation=_identifier(payload.get("operation"), "operation"),
            request_fingerprint=_sha256(
                payload.get("request_fingerprint"), "request_fingerprint"
            ),
            status=_state(payload.get("status")),
            attempts=_integer(payload.get("attempts"), "attempts", minimum=0),
            fencing_token=_integer(
                payload.get("fencing_token"), "fencing_token", minimum=0
            ),
            lease_owner_id=_optional_string(payload.get("lease_owner_id"), "lease_owner_id"),
            lease_expires_at=_optional_timestamp(
                payload.get("lease_expires_at"), "lease_expires_at"
            ),
            provider_request_id=_optional_string(
                payload.get("provider_request_id"), "provider_request_id"
            ),
            stream_observed=_boolean(
                payload.get("stream_observed"), "stream_observed"
            ),
            stream_observed_sha256=_optional_sha256(
                payload.get("stream_observed_sha256"), "stream_observed_sha256"
            ),
            stream_observed_fencing_token=_optional_integer(
                payload.get("stream_observed_fencing_token"),
                "stream_observed_fencing_token",
            ),
            stream_observed_at=_optional_timestamp(
                payload.get("stream_observed_at"), "stream_observed_at"
            ),
            terminal_proof_sha256=_optional_sha256(
                payload.get("terminal_proof_sha256"), "terminal_proof_sha256"
            ),
            terminal_response_sha256=_optional_sha256(
                payload.get("terminal_response_sha256"), "terminal_response_sha256"
            ),
            reconciliation_reason=_optional_string(
                payload.get("reconciliation_reason"), "reconciliation_reason"
            ),
            reconciliation_attempts=_integer(
                payload.get("reconciliation_attempts"),
                "reconciliation_attempts",
                minimum=0,
            ),
            next_reconcile_at=_optional_timestamp(
                payload.get("next_reconcile_at"), "next_reconcile_at"
            ),
            last_error_sha256=_optional_sha256(
                payload.get("last_error_sha256"), "last_error_sha256"
            ),
            created_at=_timestamp(payload.get("created_at"), "created_at"),
            updated_at=_timestamp(payload.get("updated_at"), "updated_at"),
            claimed_at=_optional_timestamp(payload.get("claimed_at"), "claimed_at"),
            completed_at=_optional_timestamp(
                payload.get("completed_at"), "completed_at"
            ),
            failed_at=_optional_timestamp(payload.get("failed_at"), "failed_at"),
            raw_payload_included=_boolean(
                payload.get("raw_payload_included"), "raw_payload_included"
            ),
        )
        _assert_scope(entry.tenant_id, entry.project_id, expected_scope)
        if entry.raw_payload_included:
            raise ProviderDispatchValidationError(
                "provider dispatch response must not include raw payloads",
                code="provider_dispatch_validation",
            )
        if entry.status in {"claimed", "reconciling"}:
            if entry.lease_owner_id is None or entry.lease_expires_at is None:
                raise ProviderDispatchValidationError(
                    "leased dispatch is missing lease metadata",
                    code="provider_dispatch_validation",
                )
        return entry


@dataclass(frozen=True, slots=True)
class ProviderDispatchClaim:
    schema_version: str
    status: str
    claimed: bool
    dispatch: ProviderDispatchEntry | None = None

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], *, expected_scope: ProviderDispatchScope
    ) -> "ProviderDispatchClaim":
        claimed = _boolean(payload.get("claimed"), "claimed")
        status = _required_string(payload.get("status"), "status")
        raw_dispatch = payload.get("dispatch")
        dispatch = None
        if raw_dispatch is not None:
            if not isinstance(raw_dispatch, Mapping):
                raise ProviderDispatchValidationError(
                    "claim dispatch must be an object",
                    code="provider_dispatch_validation",
                )
            dispatch = ProviderDispatchEntry.from_payload(
                raw_dispatch, expected_scope=expected_scope
            )
        if claimed != (dispatch is not None):
            raise ProviderDispatchValidationError(
                "claim result is internally inconsistent",
                code="provider_dispatch_validation",
            )
        return cls(
            schema_version=_required_string(
                payload.get("schema_version"), "schema_version"
            ),
            status=status,
            claimed=claimed,
            dispatch=dispatch,
        )

    @property
    def entry_id(self) -> str | None:
        return self.dispatch.dispatch_id if self.dispatch else None

    @property
    def fencing_token(self) -> int | None:
        return self.dispatch.fencing_token if self.dispatch else None


class ProviderDispatchClient:
    """Public-safe client for the canonical Go provider-dispatch HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        transport: ProviderDispatchTransport,
        api_key_id: str | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ProviderDispatchValidationError(
                "base_url must be a non-empty string",
                code="provider_dispatch_validation",
            )
        if not callable(transport):
            raise TypeError("transport must be callable")
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self.api_key_id = (
            _identifier(api_key_id, "api_key_id") if api_key_id is not None else None
        )

    def submit(
        self,
        scope: ProviderDispatchScope,
        *,
        provider: str,
        operation: str,
        request: Mapping[str, Any],
        dispatch_id: str | None = None,
    ) -> ProviderDispatchEntry:
        reservation = ProviderDispatchReservation(
            scope=scope,
            provider=provider,
            operation=operation,
            request=dict(request),
            dispatch_id=dispatch_id,
        )
        response = self._request(
            "POST", self._collection_path(scope), reservation.to_payload()
        )
        return self._dispatch_result(response, scope)

    def reserve(self, reservation: ProviderDispatchReservation) -> ProviderDispatchEntry:
        return self.submit(
            reservation.scope,
            provider=reservation.provider,
            operation=reservation.operation,
            request=reservation.request,
            dispatch_id=reservation.dispatch_id,
        )

    def claim_next(
        self,
        scope: ProviderDispatchScope,
        *,
        lease_owner_id: str | None = None,
        lease_owner: str | None = None,
        lease_seconds: int = 30,
        provider: str | None = None,
        operation: str | None = None,
    ) -> ProviderDispatchClaim:
        owner = lease_owner_id if lease_owner_id is not None else lease_owner
        payload: JsonDict = {
            "lease_owner_id": _required_string(owner, "lease_owner_id"),
            "lease_seconds": _integer(
                lease_seconds, "lease_seconds", minimum=1, maximum=86400
            ),
        }
        if provider is not None:
            payload["provider"] = _identifier(provider, "provider")
        if operation is not None:
            payload["operation"] = _identifier(operation, "operation")
        response = self._request(
            "POST", f"{self._collection_path(scope)}/claim", payload
        )
        return ProviderDispatchClaim.from_payload(
            _result(response), expected_scope=scope
        )

    def claim_reconciliation(
        self,
        scope: ProviderDispatchScope,
        *,
        lease_owner_id: str,
        lease_seconds: int = 30,
    ) -> ProviderDispatchClaim:
        response = self._request(
            "POST",
            f"{self._collection_path(scope)}/reconciliation/claim",
            {
                "lease_owner_id": _required_string(
                    lease_owner_id, "lease_owner_id"
                ),
                "lease_seconds": _integer(
                    lease_seconds, "lease_seconds", minimum=1, maximum=86400
                ),
            },
        )
        return ProviderDispatchClaim.from_payload(
            _result(response), expected_scope=scope
        )

    def heartbeat(
        self,
        scope: ProviderDispatchScope,
        dispatch_id: str,
        *,
        lease_owner_id: str | None = None,
        lease_owner: str | None = None,
        fencing_token: int,
        lease_seconds: int = 30,
    ) -> ProviderDispatchEntry:
        owner = lease_owner_id if lease_owner_id is not None else lease_owner
        return self._mutation(
            scope,
            dispatch_id,
            "heartbeat",
            _lease_payload(owner, fencing_token)
            | {
                "lease_seconds": _integer(
                    lease_seconds, "lease_seconds", minimum=1, maximum=86400
                )
            },
        )

    def observe_stream(
        self,
        scope: ProviderDispatchScope,
        dispatch_id: str,
        *,
        lease_owner_id: str,
        fencing_token: int,
        stream: Mapping[str, Any],
    ) -> ProviderDispatchEntry:
        _safe_mapping(stream, "stream")
        return self._mutation(
            scope,
            dispatch_id,
            "observe-stream",
            _lease_payload(lease_owner_id, fencing_token)
            | {"stream": redact_sensitive(stream)},
        )

    def complete(
        self,
        scope: ProviderDispatchScope,
        dispatch_id: str,
        *,
        lease_owner_id: str | None = None,
        lease_owner: str | None = None,
        fencing_token: int,
        proof: Mapping[str, Any],
        response: Mapping[str, Any],
        provider_request_id: str | None = None,
    ) -> ProviderDispatchEntry:
        owner = lease_owner_id if lease_owner_id is not None else lease_owner
        _safe_mapping(proof, "proof")
        _safe_mapping(response, "response")
        payload = _lease_payload(owner, fencing_token) | {
            "proof": redact_sensitive(proof),
            "response": redact_sensitive(response),
        }
        if provider_request_id is not None:
            payload["provider_request_id"] = _required_string(
                provider_request_id, "provider_request_id"
            )
        return self._mutation(scope, dispatch_id, "complete", payload)

    def mark_indeterminate(
        self,
        scope: ProviderDispatchScope,
        dispatch_id: str,
        *,
        lease_owner_id: str,
        fencing_token: int,
        reconciliation_reason: str,
        retry_after_seconds: int = 0,
    ) -> ProviderDispatchEntry:
        return self._mutation(
            scope,
            dispatch_id,
            "indeterminate",
            _lease_payload(lease_owner_id, fencing_token)
            | {
                "reconciliation_reason": _required_string(
                    reconciliation_reason, "reconciliation_reason"
                ),
                "retry_after_seconds": _integer(
                    retry_after_seconds, "retry_after_seconds", minimum=0
                ),
            },
        )

    def get(
        self, scope: ProviderDispatchScope, dispatch_id: str
    ) -> ProviderDispatchEntry:
        response = self._request("GET", self._entry_path(scope, dispatch_id), None)
        return self._dispatch_result(response, scope)

    def _mutation(
        self,
        scope: ProviderDispatchScope,
        dispatch_id: str,
        operation: str,
        payload: Mapping[str, Any],
    ) -> ProviderDispatchEntry:
        response = self._request(
            "POST", f"{self._entry_path(scope, dispatch_id)}/{operation}", payload
        )
        dispatch = self._dispatch_result(response, scope)
        if dispatch.dispatch_id != dispatch_id:
            raise ProviderDispatchValidationError(
                "provider dispatch response changed dispatch identity",
                code="provider_dispatch_validation",
            )
        return dispatch

    def _dispatch_result(
        self, response: Mapping[str, Any], scope: ProviderDispatchScope
    ) -> ProviderDispatchEntry:
        result = _result(response)
        raw_dispatch = result.get("dispatch") if "dispatch" in result else result
        if not isinstance(raw_dispatch, Mapping):
            raise ProviderDispatchValidationError(
                "provider dispatch result must contain dispatch",
                code="provider_dispatch_validation",
            )
        return ProviderDispatchEntry.from_payload(
            raw_dispatch, expected_scope=scope
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-ReleaseFoundry-SDK-Version": PROVIDER_DISPATCH_CLIENT_VERSION,
        }
        if self.api_key_id is not None:
            headers["X-ReleaseFoundry-Api-Key-Id"] = self.api_key_id
        try:
            response = self._transport(method, self.base_url + path, payload, headers)
        except ProviderDispatchError:
            raise
        except Exception as exc:
            raise ProviderDispatchError(
                f"provider dispatch transport failed: {redact_text(str(exc))}",
                code="provider_dispatch_transport",
                retryable=True,
            ) from exc
        if not isinstance(response, Mapping):
            raise ProviderDispatchValidationError(
                "provider dispatch response must be an object",
                code="provider_dispatch_validation",
            )
        if "error" in response:
            _raise_remote_error(response["error"])
        if response.get("status") not in {"ok", "empty"}:
            raise ProviderDispatchValidationError(
                "provider dispatch envelope status is invalid",
                code="provider_dispatch_validation",
            )
        return dict(response)

    @staticmethod
    def _collection_path(scope: ProviderDispatchScope) -> str:
        return (
            f"/v1/tenants/{quote(scope.tenant_id, safe='')}"
            f"/projects/{quote(scope.project_id, safe='')}/provider-dispatches"
        )

    @classmethod
    def _entry_path(cls, scope: ProviderDispatchScope, dispatch_id: str) -> str:
        return (
            f"{cls._collection_path(scope)}/"
            f"{quote(_identifier(dispatch_id, 'dispatch_id'), safe='')}"
        )


def provider_dispatch_capability_manifest() -> JsonDict:
    return {
        "schema_version": PROVIDER_DISPATCH_CLIENT_VERSION,
        "capabilities": dict(PROVIDER_DISPATCH_CAPABILITIES),
        "states": sorted(PROVIDER_DISPATCH_STATES),
        "error_codes": sorted(PROVIDER_DISPATCH_ERROR_CODES),
        "public_safe": True,
        "routes": [
            "submit",
            "claim",
            "heartbeat",
            "observe-stream",
            "complete",
            "indeterminate",
            "reconciliation/claim",
            "get",
        ],
    }


def _result(response: Mapping[str, Any]) -> Mapping[str, Any]:
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise ProviderDispatchValidationError(
            "provider dispatch envelope must contain result",
            code="provider_dispatch_validation",
        )
    return result


def _lease_payload(owner: Any, fencing_token: int) -> JsonDict:
    return {
        "lease_owner_id": _required_string(owner, "lease_owner_id"),
        "fencing_token": _integer(
            fencing_token, "fencing_token", minimum=1
        ),
    }


def _raise_remote_error(raw: Any) -> None:
    if not isinstance(raw, Mapping):
        raise ProviderDispatchError(
            "provider dispatch service returned an invalid error",
            code="provider_dispatch_transport",
        )
    code = raw.get("code")
    known_code = code in PROVIDER_DISPATCH_ERROR_CODES
    if not known_code:
        code = "provider_dispatch_transport"
    message = "provider dispatch request failed"
    if known_code and isinstance(raw.get("message"), str):
        message = raw["message"]
    error_type: type[ProviderDispatchError] = {
        "provider_dispatch_conflict": ProviderDispatchConflict,
        "provider_dispatch_fence": ProviderDispatchFenceRejected,
        "provider_dispatch_not_found": ProviderDispatchNotFound,
        "provider_dispatch_validation": ProviderDispatchValidationError,
    }.get(code, ProviderDispatchError)
    raise error_type(
        message,
        code=code,
        status_code=(
            raw.get("status_code")
            if isinstance(raw.get("status_code"), int)
            else None
        ),
        retryable=raw.get("retryable") is True,
        details=(
            raw.get("details") if isinstance(raw.get("details"), Mapping) else {}
        ),
    )


def _assert_scope(
    tenant_id: str, project_id: str, expected: ProviderDispatchScope
) -> None:
    if tenant_id != expected.tenant_id or project_id != expected.project_id:
        raise ProviderDispatchValidationError(
            "provider dispatch response crossed tenant/project scope",
            code="provider_dispatch_validation",
        )


def _identifier(value: Any, field_name: str) -> str:
    value = _required_string(value, field_name)
    if len(value) > 255 or any(character.isspace() for character in value):
        raise ProviderDispatchValidationError(
            f"{field_name} must be an identifier",
            code="provider_dispatch_validation",
        )
    return value


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ProviderDispatchValidationError(
            f"{field_name} must be a non-empty string",
            code="provider_dispatch_validation",
        )
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    return _required_string(value, field_name)


def _state(value: Any) -> str:
    if value not in PROVIDER_DISPATCH_STATES:
        raise ProviderDispatchValidationError(
            "provider dispatch status is invalid",
            code="provider_dispatch_validation",
        )
    return value


def _integer(
    value: Any,
    field_name: str,
    *,
    minimum: int,
    maximum: int = 9_007_199_254_740_991,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise ProviderDispatchValidationError(
            f"{field_name} must be an integer from {minimum} to {maximum}",
            code="provider_dispatch_validation",
        )
    return value


def _optional_integer(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, field_name, minimum=0)


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ProviderDispatchValidationError(
            f"{field_name} must be a boolean",
            code="provider_dispatch_validation",
        )
    return value


def _sha256(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProviderDispatchValidationError(
            f"{field_name} must be a lowercase sha256 digest",
            code="provider_dispatch_validation",
        )
    return value


def _optional_sha256(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    return _sha256(value, field_name)


def _timestamp(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or "T" not in value:
        raise ProviderDispatchValidationError(
            f"{field_name} must be an RFC3339 timestamp",
            code="provider_dispatch_validation",
        )
    return value


def _optional_timestamp(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    return _timestamp(value, field_name)


def _safe_mapping(value: Any, field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise ProviderDispatchValidationError(
            f"{field_name} must be an object",
            code="provider_dispatch_validation",
        )
    if redact_sensitive(value) != dict(value):
        raise ProviderDispatchValidationError(
            f"{field_name} must not contain secrets",
            code="provider_dispatch_validation",
        )
