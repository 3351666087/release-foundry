from __future__ import annotations

import hashlib
import json
from inspect import signature
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib import error, request
from urllib.parse import urlencode, urljoin, quote

from .api_client import redact_sensitive, redact_text
from .account_connection import (
    AccountConnection,
    AccountConnectionBinding,
    AccountConnectionDisconnect,
    AccountConnectionStart,
)

JsonDict = dict[str, Any]
SAAS_CLIENT_VERSION = "ashr.clone.saas_ingestion_client.v1"
BLOCKED_CONTROL_PLANE_PATH_PARTS = {".secrets", "private_refs"}

HOSTED_ROUTE_SCOPE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "GET /v1/accounts/{account_id}": ("identity:read",),
    "GET /v1/accounts/{account_id}/credentials": ("identity:read",),
    "GET /v1/accounts/{account_id}/memberships": ("identity:read",),
    "GET /v1/projects/{project_id}/api-keys": ("api_key:read",),
    "GET /v1/projects/{project_id}/api-keys/rate-limits": ("api_key:read",),
    "GET /v1/projects/{project_id}/audit-log": ("audit:read",),
    "GET /v1/projects/{project_id}/billing/ledger": ("billing:read",),
    "GET /v1/projects/{project_id}/runs/{run_id}/artifact-manifests": ("evidence:read",),
    "GET /v1/projects/{project_id}/runs/{run_id}/lifecycle": ("run:lifecycle:read",),
    "GET /v1/projects/{project_id}/runs/{run_id}/release-evidence": ("evidence:read",),
    "GET /v1/projects/{project_id}/quota": ("usage:read",),
    "GET /v1/projects/{project_id}/usage": ("usage:read",),
    "POST /v1/projects/{project_id}/quota/limits": ("usage:read",),
    "POST /v1/projects/{project_id}/usage/quotas": ("usage:read",),
    "GET /v1/projects/{project_id}/worker-jobs": ("worker_job:read",),
    "POST /v1/bootstrap": (),
    "POST /v1/projects/{project_id}/api-keys": ("api_key:write",),
    "POST /v1/projects/{project_id}/api-keys/{key_id}/rate-limit": ("api_key:write",),
    "POST /v1/projects/{project_id}/api-keys/{key_id}/revoke": ("api_key:write",),
    "POST /v1/projects/{project_id}/api-keys/{key_id}/verify": (),
    "POST /v1/projects/{project_id}/audit-chain/verify": ("audit:read",),
    "POST /v1/projects/{project_id}/billing/checkout-plan": ("billing:write",),
    "POST /v1/projects/{project_id}/billing/portal-plan": ("billing:write",),
    "POST /v1/projects/{project_id}/billing/webhooks/ingest": ("billing:webhook",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-providers/configure": ("commercial:write",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/begin": ("commercial:write",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/{flow_id}/complete": ("commercial:write",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-sessions/create": ("commercial:write",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-sessions/{session_id}/disconnect": ("commercial:write",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-sessions/{session_id}/revoke": ("commercial:write",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/payments/mode-boundary": ("commercial:write",),
    "POST /v1/projects/{project_id}/commercial-auth-payment/providers/configure": ("commercial:write",),
    "POST /v1/projects/{project_id}/runs/{run_id}/artifact-manifests": ("artifact:upload",),
    "POST /v1/projects/{project_id}/runs/{run_id}/release-evidence/verify": ("evidence:read",),
    "POST /v1/projects/{project_id}/runs/{run_id}/trace-events": ("trace:ingest",),
    "POST /v1/projects/{project_id}/runs/{run_id}/upload": ("run:upload",),
    "POST /v1/projects/{project_id}/sdk-submit": ("sdk:submit",),
    "POST /v1/projects/{project_id}/worker-jobs/enqueue": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/lease": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/complete": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/fail": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat": ("worker_job:write",),
    "POST /v1/projects/{project_id}/oauth/{provider}/start": ("oauth:connect",),
    "GET /v1/projects/{project_id}/oauth/{provider}/connection": ("oauth:read",),
    "POST /v1/projects/{project_id}/oauth/{provider}/disconnect": ("oauth:disconnect",),
    "POST /v1/projects/{project_id}/oauth/github/start": ("oauth:connect",),
    "GET /v1/projects/{project_id}/oauth/github/connection": ("oauth:read",),
    "POST /v1/projects/{project_id}/oauth/github/disconnect": ("oauth:disconnect",),
    "POST /v1/projects/{project_id}/oauth/google/start": ("oauth:connect",),
    "GET /v1/projects/{project_id}/oauth/google/connection": ("oauth:read",),
    "POST /v1/projects/{project_id}/oauth/google/disconnect": ("oauth:disconnect",),
}

MUTATING_CALIBRATION_MODALITIES = ("text", "image", "audio", "file", "video")
MUTATING_CALIBRATION_INDEX_SCHEMA_VERSION = "ashr.clone.official_api_mutating_calibration_index.v1"

UNSUPPORTED_GO_ROUTE_GAPS: dict[str, dict[str, str]] = {
    "GET /health": {
        "reason": "Go exposes a root health alias; the hosted Python client uses scoped SaaS/OpenAPI helpers instead of consuming this alias.",
        "replacement_route": "GET /healthz",
        "consumer_action": "keep unsupported until the generated Go OpenAPI marks root health aliases as public client surface",
    },
    "GET /healthz": {
        "reason": "Hosted route scope parity tracks project-scoped API calls rather than unscoped local health helpers.",
        "consumer_action": "keep unsupported as an unscoped adapter helper outside hosted route authorization",
    },
    "GET /openapi.json": {
        "reason": "Hosted route scope parity tracks project-scoped API calls rather than unscoped local OpenAPI helpers.",
        "consumer_action": "keep unsupported as an unscoped adapter helper outside hosted route authorization",
    },
    "GET /v1/healthz": {
        "reason": "Go exposes a versioned health alias that is not part of the TS/Python shared hosted ingestion surface.",
        "replacement_route": "GET /healthz",
        "consumer_action": "keep unsupported until versioned health aliases become SDK contract routes",
    },
    "GET /v1/openapi.json": {
        "reason": "Hosted route scope parity tracks project-scoped API calls rather than unscoped local OpenAPI helpers.",
        "consumer_action": "keep unsupported as an unscoped adapter helper outside hosted route authorization",
    },
    "GET /oauth/github/callback": {
        "reason": "Go exposes the canonical localhost GitHub account-connection callback; the hosted Python route client does not execute browser redirects.",
        "consumer_action": "keep explicit until the shared generated OpenAPI client models provider callbacks without exposing authorization codes",
    },
    "GET /oauth/google/callback": {
        "reason": "Go exposes the canonical localhost Google account-connection callback; the hosted Python route client does not execute browser redirects.",
        "consumer_action": "keep explicit until the shared generated OpenAPI client models provider callbacks without exposing authorization codes",
    },
    "GET /v1/projects/{project_id}/oauth/github/start": {
        "reason": "Go exposes a browser redirect alias; hosted SDKs use the provider-neutral JSON POST start contract.",
        "replacement_route": "POST /v1/projects/{project_id}/oauth/{provider}/start",
        "consumer_action": "keep explicit as a browser-only alias outside the hosted JSON client",
    },
    "GET /v1/projects/{project_id}/oauth/google/start": {
        "reason": "Go exposes a browser redirect alias; hosted SDKs use the provider-neutral JSON POST start contract.",
        "replacement_route": "POST /v1/projects/{project_id}/oauth/{provider}/start",
        "consumer_action": "keep explicit as a browser-only alias outside the hosted JSON client",
    },
    "GET /v1/projects/{project_id}/audit-chain/verify": {
        "reason": "Go has a read-style audit-chain verifier route while hosted clients consume the POST verifier contract.",
        "replacement_route": "POST /v1/projects/{project_id}/audit-chain/verify",
        "consumer_action": "keep unsupported until Go and hosted clients settle on one audit-chain verification method",
    },
    "POST /bootstrap": {
        "reason": "Go keeps a root bootstrap alias; hosted clients consume the versioned bootstrap route.",
        "replacement_route": "POST /v1/bootstrap",
        "consumer_action": "keep unsupported until root bootstrap aliases are part of generated SDK contracts",
    },
    "POST /v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh": {
        "reason": "Go owns the same-origin HttpOnly cookie refresh boundary; the hosted JSON client intentionally accepts neither raw refresh cookies nor digest payloads for this browser-only route.",
        "consumer_action": "invoke through a same-origin browser transport with credentials and Idempotency-Key; keep it outside the hosted JSON body client",
    },
    "POST /v1/projects/{project_id}/api-keys/preflight": {
        "reason": "Go advertises an API-key preflight route that TS/Python hosted clients have not implemented yet.",
        "consumer_action": "keep unsupported until preflight request and response semantics are added to both hosted SDKs",
    },
    "DELETE /v1/projects/{project_id}/oauth/github/disconnect": {
        "reason": "Go exposes an idempotent HTTP DELETE alias; hosted SDKs use the provider-neutral JSON POST disconnect contract.",
        "replacement_route": "POST /v1/projects/{project_id}/oauth/{provider}/disconnect",
        "consumer_action": "keep explicit as a method alias outside the hosted JSON client",
    },
    "DELETE /v1/projects/{project_id}/oauth/google/disconnect": {
        "reason": "Go exposes an idempotent HTTP DELETE alias; hosted SDKs use the provider-neutral JSON POST disconnect contract.",
        "replacement_route": "POST /v1/projects/{project_id}/oauth/{provider}/disconnect",
        "consumer_action": "keep explicit as a method alias outside the hosted JSON client",
    },
    "POST /v1/projects/{project_id}/runs/submit": {
        "reason": "Go keeps an older run submit shape while hosted clients submit through the SDK submission contract.",
        "replacement_route": "POST /v1/projects/{project_id}/sdk-submit",
        "consumer_action": "keep unsupported until run submit is either removed from Go or added to both hosted SDKs deliberately",
    },
}

_CHINA_PAYMENT_GO_ONLY_ROUTES = (
    "GET /v1/projects/{project_id}/billing/payments/bills",
    "GET /v1/projects/{project_id}/billing/payments/bills/{provider}/{bill_entry_id}",
    "GET /v1/projects/{project_id}/billing/payments/notifications",
    "GET /v1/projects/{project_id}/billing/payments/notifications/{provider}/{event_id}",
    "GET /v1/projects/{project_id}/billing/payments/orders",
    "GET /v1/projects/{project_id}/billing/payments/orders/{provider}/{merchant_order_id}",
    "GET /v1/projects/{project_id}/billing/payments/providers",
    "GET /v1/projects/{project_id}/billing/payments/refunds",
    "GET /v1/projects/{project_id}/billing/payments/refunds/{provider}/{merchant_refund_id}",
    "GET /v1/projects/{project_id}/billing/reconciliation/events",
    "GET /v1/projects/{project_id}/billing/reconciliation/events/{provider}/{event_id}",
    "POST /v1/projects/{project_id}/billing/payments/bills",
    "POST /v1/projects/{project_id}/billing/payments/notifications",
    "POST /v1/projects/{project_id}/billing/payments/orders",
    "POST /v1/projects/{project_id}/billing/payments/refunds",
    "POST /v1/projects/{project_id}/billing/reconciliation/events",
)
UNSUPPORTED_GO_ROUTE_GAPS.update(
    {
        route: {
            "reason": "Go owns the Round47 China payment and reconciliation runtime; Python and TypeScript hosted SDK request/response contracts are not implemented yet.",
            "consumer_action": "keep the route explicit in parity evidence until both hosted SDKs implement the provider-safe China payment contract",
        }
        for route in _CHINA_PAYMENT_GO_ONLY_ROUTES
    }
)


class SaaSClientError(RuntimeError):
    pass


class SecretInputError(SaaSClientError):
    pass


class SaaSIngestionClient:
    """SaaS ingestion client for the A1 Python SDK.

    By default the client uses the in-process ``services.api.control_plane``
    runtime. Passing ``base_url`` switches to HTTP JSON transport for a local
    hosted adapter. The client never reads API keys from environment variables
    and never accepts raw key material; callers pass public ``api_key_id``
    handles for scoped local auth checks.
    """

    def __init__(
        self,
        *,
        service: Any | None = None,
        base_url: str | None = None,
        http_transport: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        if service is not None and base_url is not None:
            raise SaaSClientError("provide either service or base_url, not both")
        self.base_url = _normalize_base_url(base_url) if base_url else None
        self._http_transport = http_transport or _post_json
        if self.base_url is None and service is None:
            service = _new_service()
        self.service = service
        self._billing_ledger = None

    @classmethod
    def from_state_file(cls, path: str | Path) -> "SaaSIngestionClient":
        _assert_public_control_plane_path(path)
        payload = load_json_file(path)
        from services.api.control_plane import control_plane_from_state_file

        client = cls(service=control_plane_from_state_file(str(path)))
        client._restore_billing_ledger_state(payload.get("billing_ledger") if isinstance(payload, Mapping) else None)
        return client

    @classmethod
    def from_base_url(
        cls,
        base_url: str,
        *,
        http_transport: Callable[..., Mapping[str, Any]] | None = None,
    ) -> "SaaSIngestionClient":
        return cls(base_url=base_url, http_transport=http_transport)

    @property
    def uses_http(self) -> bool:
        return self.base_url is not None

    def write_state(self, path: str | Path) -> str:
        if self.uses_http:
            raise SaaSClientError("state files are only supported in in-process mode")
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot_state(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(output)
        return str(output)

    def _billing_ledger_state(self) -> JsonDict:
        if self._billing_ledger is None:
            return {"ledger_events": [], "provider_events": {}, "billing_accounts": {}, "raw_payload_included": False, "secret_value_present": False}
        return {
            "ledger_events": list(self._billing_ledger.ledger_events),
            "provider_events": dict(self._billing_ledger.provider_events),
            "billing_accounts": dict(self._billing_ledger.billing_accounts),
            "raw_payload_included": False,
            "secret_value_present": False,
        }

    def _restore_billing_ledger_state(self, state: Any) -> None:
        if not isinstance(state, Mapping):
            return
        from services.api.billing import BillingLedger

        ledger = BillingLedger()
        ledger.ledger_events = [dict(item) for item in state.get("ledger_events", []) if isinstance(item, Mapping)]
        ledger.provider_events = {str(key): dict(value) for key, value in dict(state.get("provider_events") or {}).items() if isinstance(value, Mapping)}
        ledger.billing_accounts = {str(key): dict(value) for key, value in dict(state.get("billing_accounts") or {}).items() if isinstance(value, Mapping)}
        self._billing_ledger = ledger

    def snapshot_state(self) -> JsonDict:
        if self.uses_http:
            return self._request("state", {})["result"]
        from services.api.control_plane import snapshot_control_plane

        snapshot = snapshot_control_plane(self.service)
        snapshot["billing_ledger"] = self._billing_ledger_state()
        payload = {key: value for key, value in snapshot.items() if key != "integrity"}
        snapshot["integrity"] = {"payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()}
        return snapshot

    def bootstrap_project(
        self,
        *,
        tenant_name: str,
        project_name: str,
        tenant_id: str | None = None,
        project_id: str | None = None,
        dataset_id: str | None = None,
        dataset_name: str = "SDK Bootstrap Dataset",
        cases: Sequence[Mapping[str, Any]] | None = None,
    ) -> JsonDict:
        if self.uses_http:
            return self._request(
                "bootstrap_project",
                {
                    "tenant_name": tenant_name,
                    "project_name": project_name,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "dataset_name": dataset_name,
                    "cases": list(cases) if cases is not None else None,
                },
            )
        result = self.service.bootstrap_project(
            tenant_name=tenant_name,
            project_name=project_name,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if dataset_id is not None:
            case_payload = list(cases or [{"id": "sdk-bootstrap-case", "prompt": "local bootstrap", "expected": {"text": "local bootstrap"}}])
            result["dataset"] = self.service.cloud.create_dataset(
                result["tenant"]["tenant_id"],
                result["project"]["project_id"],
                name=dataset_name,
                dataset_id=dataset_id,
                cases=case_payload,
                metadata={"created_by": "ashr_clone.saas_client", "local_only": True},
            )
        return _envelope("bootstrap_project", result)

    def start_account_connection(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        account_id: str,
        expected_google_audience: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        if not self.uses_http:
            raise SaaSClientError("account connection is only supported with base_url HTTP transport")
        binding = AccountConnectionBinding(tenant_id, project_id, account_id, provider)
        auth_headers = _bearer_auth_headers(
            api_key_secret=api_key_secret, bearer_api_key=bearer_api_key
        )
        envelope = self._request(
            "start_account_connection", binding.request_payload(), headers=auth_headers
        )
        result = AccountConnectionStart.from_public_response(
            envelope["result"],
            expected_provider=binding.provider,
            expected_google_audience=expected_google_audience,
        )
        envelope["result"] = result.to_dict()
        return envelope

    def disconnect_account_connection(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        account_id: str,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        if not self.uses_http:
            raise SaaSClientError("account connection is only supported with base_url HTTP transport")
        binding = AccountConnectionBinding(tenant_id, project_id, account_id, provider)
        auth_headers = _bearer_auth_headers(
            api_key_secret=api_key_secret, bearer_api_key=bearer_api_key
        )
        envelope = self._request(
            "disconnect_account_connection", binding.request_payload(), headers=auth_headers
        )
        result = AccountConnectionDisconnect.from_public_response(
            envelope["result"], expected_provider=binding.provider
        )
        envelope["result"] = result.to_dict()
        return envelope

    def get_account_connection(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        account_id: str,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        if not self.uses_http:
            raise SaaSClientError("account connection is only supported with base_url HTTP transport")
        binding = AccountConnectionBinding(tenant_id, project_id, account_id, provider)
        auth_headers = _bearer_auth_headers(
            api_key_secret=api_key_secret, bearer_api_key=bearer_api_key
        )
        envelope = self._request(
            "get_account_connection", binding.request_payload(), headers=auth_headers
        )
        result = AccountConnection.from_public_response(
            envelope["result"], expected_provider=binding.provider
        )
        envelope["result"] = result.to_dict()
        return envelope

    def create_api_key(
        self,
        tenant_id: str,
        project_id: str,
        *,
        name: str,
        scopes: Sequence[str],
        key_id: str | None = None,
        auth_key_id: str | None = None,
        reveal_secret: bool = False,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request(
                "create_api_key",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "name": name,
                    "scopes": [str(scope) for scope in scopes],
                    "key_id": key_id,
                    "auth_key_id": auth_key_id,
                    "reveal_secret": bool(reveal_secret),
                },
                headers=auth_headers,
            )
        _reject_hosted_bearer_headers(auth_headers)
        result = self.service.create_api_key(
            tenant_id,
            project_id,
            name=name,
            scopes=[str(scope) for scope in scopes],
            key_id=key_id,
            auth_key_id=auth_key_id,
            reveal_secret=bool(reveal_secret),
        )
        return _envelope("create_api_key", result)

    def list_api_keys(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, api_key: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request("list_api_keys", {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id}, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("list_api_keys", {"api_keys": self.service.list_api_keys(tenant_id, project_id, auth_key_id=auth_key_id)})

    def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str, *, auth_key_id: str | None = None, api_key: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request("revoke_api_key", {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "auth_key_id": auth_key_id}, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("revoke_api_key", self.service.revoke_api_key(tenant_id, project_id, key_id, auth_key_id=auth_key_id))

    def verify_api_key_secret(
        self,
        tenant_id: str,
        project_id: str,
        key_id: str,
        *,
        secret: str,
        scope: str | None = None,
    ) -> JsonDict:
        if self.uses_http:
            return self._request("verify_api_key_secret", {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "secret": secret, "scope": scope})
        return _envelope("verify_api_key_secret", self.service.verify_api_key_secret(tenant_id, project_id, key_id=key_id, secret=secret, scope=scope))

    def configure_api_key_rate_limit(
        self,
        tenant_id: str,
        project_id: str,
        key_id: str,
        *,
        operation: str,
        limit: int,
        period: str = "local-window",
        auth_key_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request(
                "configure_api_key_rate_limit",
                {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "operation": operation, "limit": int(limit), "period": period, "auth_key_id": auth_key_id},
                headers=auth_headers,
            )
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope(
            "configure_api_key_rate_limit",
            self.service.configure_api_key_rate_limit(tenant_id, project_id, key_id=key_id, operation=operation, limit=int(limit), period=period, auth_key_id=auth_key_id),
        )

    def api_key_rate_limit_snapshot(self, tenant_id: str, project_id: str, *, key_id: str | None = None) -> JsonDict:
        if self.uses_http:
            return self._request("api_key_rate_limit_snapshot", {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id})
        return _envelope("api_key_rate_limit_snapshot", self.service.api_key_rate_limit_snapshot(tenant_id, project_id, key_id=key_id))

    def sdk_submit(
        self,
        tenant_id: str,
        project_id: str,
        *,
        dataset_id: str,
        agent_ref: str,
        run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request(
                "sdk_submit",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "agent_ref": agent_ref,
                    "run_id": run_id,
                    "metadata": {"client": SAAS_CLIENT_VERSION, **dict(metadata or {})},
                    "api_key_id": api_key_id,
                    "idempotency_key": idempotency_key,
                    "request_id": request_id,
                },
                headers=auth_headers,
            )
        _reject_hosted_bearer_headers(auth_headers)
        result = self.service.sdk_submit_run(
            tenant_id,
            project_id,
            dataset_id=dataset_id,
            agent_ref=agent_ref,
            run_id=run_id,
            metadata={"client": SAAS_CLIENT_VERSION, **dict(metadata or {})},
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _envelope("sdk_submit", result)

    def upload_run(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        result: Mapping[str, Any],
        *,
        upload_id: str | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request(
                "upload_run",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "result": dict(result),
                    "upload_id": upload_id,
                    "api_key_id": api_key_id,
                    "idempotency_key": idempotency_key,
                    "request_id": request_id,
                },
                headers=auth_headers,
            )
        _reject_hosted_bearer_headers(auth_headers)
        upload = self.service.upload_run_result(
            tenant_id,
            project_id,
            run_id,
            dict(result),
            upload_id=upload_id,
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _envelope("upload_run", upload)

    def ingest_trace(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        observations: Sequence[Mapping[str, Any]],
        *,
        batch_id: str | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request(
                "ingest_trace",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "observations": [dict(item) for item in observations],
                    "batch_id": batch_id,
                    "api_key_id": api_key_id,
                    "idempotency_key": idempotency_key,
                    "request_id": request_id,
                },
                headers=auth_headers,
            )
        _reject_hosted_bearer_headers(auth_headers)
        result = self.service.ingest_trace(
            tenant_id,
            project_id,
            run_id,
            [dict(item) for item in observations],
            batch_id=batch_id,
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _envelope("ingest_trace", result)

    def lifecycle_snapshot(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        if self.uses_http:
            return self._request("lifecycle_snapshot", {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id})
        return _envelope("lifecycle_snapshot", self.service.lifecycle_snapshot(tenant_id, project_id, run_id))

    def quota_snapshot(self, tenant_id: str, project_id: str) -> JsonDict:
        if self.uses_http:
            return self._request("quota_snapshot", {"tenant_id": tenant_id, "project_id": project_id})
        return _envelope("quota_snapshot", self.service.cloud.quota_snapshot(tenant_id, project_id))

    def usage_snapshot(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request("usage_snapshot", {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id}, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("usage_snapshot", self.service.usage_snapshot(tenant_id, project_id, auth_key_id=auth_key_id))

    def billing_checkout_plan(
        self,
        tenant_id: str,
        project_id: str,
        *,
        customer_ref: str,
        price: Mapping[str, Any],
        success_url: str,
        cancel_url: str,
        provider_config: Mapping[str, Any] | None = None,
        usage_rollup: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "customer_ref": customer_ref,
            "price": dict(price),
            "success_url": success_url,
            "cancel_url": cancel_url,
            "provider_config": dict(provider_config or {"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"}),
            "usage_rollup": dict(usage_rollup or {}),
            "metadata": dict(metadata or {}),
            "idempotency_key": idempotency_key,
            "auth_key_id": auth_key_id,
        }
        if self.uses_http:
            return self._request("billing_checkout_plan", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        from services.api.billing import build_checkout_session_plan

        local_payload = _drop_none({k: v for k, v in payload.items() if k != "auth_key_id"})
        return _envelope("billing_checkout_plan", build_checkout_session_plan(**local_payload))

    def configure_oauth_provider(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        client_id_ref: str,
        client_secret_ref: str,
        redirect_uris: Sequence[str],
        scopes: Sequence[str],
        config_id: str | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "provider": provider, "client_id_ref": client_id_ref, "client_secret_ref": client_secret_ref, "redirect_uris": list(redirect_uris), "scopes": list(scopes), "config_id": config_id, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("configure_oauth_provider", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("configure_oauth_provider", self.service.configure_oauth_provider(tenant_id, project_id, provider=provider, client_id_ref=client_id_ref, client_secret_ref=client_secret_ref, redirect_uris=list(redirect_uris), scopes=list(scopes), config_id=config_id, auth_key_id=auth_key_id))

    def create_oauth_session(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        subject_ref: str,
        session_id: str | None = None,
        provider_config_id: str | None = None,
        access_token_ref: str | None = None,
        refresh_token_ref: str | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "provider": provider, "subject_ref": subject_ref, "session_id": session_id, "provider_config_id": provider_config_id, "access_token_ref": access_token_ref, "refresh_token_ref": refresh_token_ref, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("create_oauth_session", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("create_oauth_session", self.service.create_oauth_session(tenant_id, project_id, provider=provider, subject_ref=subject_ref, session_id=session_id, provider_config_id=provider_config_id, access_token_ref=access_token_ref, refresh_token_ref=refresh_token_ref, auth_key_id=auth_key_id))

    def begin_oauth_authorization(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider_config_id: str,
        redirect_uri: str,
        code_verifier: str,
        state: str | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "provider_config_id": provider_config_id, "redirect_uri": redirect_uri, "code_verifier": code_verifier, "state": state, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("begin_oauth_authorization", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("begin_oauth_authorization", self.service.begin_oauth_authorization(tenant_id, project_id, provider_config_id=provider_config_id, redirect_uri=redirect_uri, code_verifier=code_verifier, state=state, auth_key_id=auth_key_id))

    def complete_oauth_authorization(
        self,
        tenant_id: str,
        project_id: str,
        flow_id: str,
        *,
        state: str,
        redirect_uri: str,
        authorization_code: str | None = None,
        code_verifier: str | None = None,
        subject_ref: str | None = None,
        provider_code_ref: str | None = None,
        session_id: str | None = None,
        include_emails: bool = True,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "flow_id": flow_id, "state": state, "redirect_uri": redirect_uri, "authorization_code": authorization_code, "code_verifier": code_verifier, "subject_ref": subject_ref, "provider_code_ref": provider_code_ref, "session_id": session_id, "include_emails": bool(include_emails), "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("complete_oauth_authorization", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("complete_oauth_authorization", self.service.complete_oauth_authorization(tenant_id, project_id, flow_id=flow_id, state=state, redirect_uri=redirect_uri, authorization_code=authorization_code, code_verifier=code_verifier, subject_ref=subject_ref, provider_code_ref=provider_code_ref, session_id=session_id, include_emails=include_emails, auth_key_id=auth_key_id))

    def revoke_oauth_session(self, tenant_id: str, project_id: str, session_id: str, *, auth_key_id: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "session_id": session_id, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("revoke_oauth_session", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("revoke_oauth_session", self.service.revoke_oauth_session(tenant_id, project_id, session_id, auth_key_id=auth_key_id))

    def disconnect_oauth_session(self, tenant_id: str, project_id: str, session_id: str, *, auth_key_id: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "session_id": session_id, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("disconnect_oauth_session", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("disconnect_oauth_session", self.service.disconnect_oauth_session(tenant_id, project_id, session_id, auth_key_id=auth_key_id))

    def configure_commercial_provider(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        purpose: str = "payment",
        mode: str = "test",
        secret_ref: str | None = None,
        webhook_secret_ref: str | None = None,
        account_ref: str | None = None,
        live_mode_ack: bool = False,
        allowed_payment_methods: Sequence[str] | None = None,
        config_id: str | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "provider": provider, "purpose": purpose, "mode": mode, "secret_ref": secret_ref, "webhook_secret_ref": webhook_secret_ref, "account_ref": account_ref, "live_mode_ack": bool(live_mode_ack), "allowed_payment_methods": list(allowed_payment_methods or []), "config_id": config_id, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("configure_commercial_provider", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("configure_commercial_provider", self.service.configure_commercial_provider(tenant_id, project_id, provider=provider, purpose=purpose, mode=mode, secret_ref=secret_ref, webhook_secret_ref=webhook_secret_ref, account_ref=account_ref, live_mode_ack=live_mode_ack, allowed_payment_methods=list(allowed_payment_methods or []), config_id=config_id, auth_key_id=auth_key_id))

    def record_payment_mode_boundary(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        mode: str,
        event_type: str,
        event_id_ref: str,
        payload_sha256: str,
        signature_header_present: bool,
        webhook_secret_ref: str,
        livemode: bool | None = None,
        boundary_id: str | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "provider": provider, "mode": mode, "event_type": event_type, "event_id_ref": event_id_ref, "payload_sha256": payload_sha256, "signature_header_present": bool(signature_header_present), "webhook_secret_ref": webhook_secret_ref, "livemode": livemode, "boundary_id": boundary_id, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("record_payment_mode_boundary", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("record_payment_mode_boundary", self.service.record_payment_mode_boundary(tenant_id, project_id, provider=provider, mode=mode, event_type=event_type, event_id_ref=event_id_ref, payload_sha256=payload_sha256, signature_header_present=signature_header_present, webhook_secret_ref=webhook_secret_ref, livemode=livemode, boundary_id=boundary_id, auth_key_id=auth_key_id))

    def commercial_auth_payment_snapshot(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("commercial_auth_payment_snapshot", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("commercial_auth_payment_snapshot", self.service.commercial_auth_payment_snapshot(tenant_id, project_id, auth_key_id=auth_key_id))

    def billing_portal_plan(
        self,
        tenant_id: str,
        project_id: str,
        *,
        customer_ref: str,
        return_url: str,
        provider_config: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "customer_ref": customer_ref,
            "return_url": return_url,
            "provider_config": dict(provider_config or {"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"}),
            "idempotency_key": idempotency_key,
            "auth_key_id": auth_key_id,
        }
        if self.uses_http:
            return self._request("billing_portal_plan", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        from services.api.billing import build_billing_portal_plan

        local_payload = _drop_none({k: v for k, v in payload.items() if k != "auth_key_id"})
        return _envelope("billing_portal_plan", build_billing_portal_plan(**local_payload))

    def billing_webhook_ingest(
        self,
        tenant_id: str,
        project_id: str,
        *,
        provider: str,
        mode: str,
        event_type: str,
        event_id: str,
        payload_sha256: str,
        signature_header_present: bool,
        signature_header_names: Sequence[str] | None = None,
        raw_body: bytes | str | None = None,
        stripe_signature_header: str | None = None,
        webhook_secret_resolver: Callable[[str], str] | None = None,
        provider_verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        received_at_unix: int | None = None,
        tolerance_seconds: int = 300,
        webhook_secret_ref: str | None = None,
        livemode: bool | None = None,
        customer_ref: str | None = None,
        amount_minor: int = 0,
        currency: str = "usd",
        invoice_ref: str | None = None,
        usage_units: int = 0,
        metadata: Mapping[str, Any] | None = None,
        auth_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "provider": provider,
            "mode": mode,
            "event_type": event_type,
            "event_id": event_id,
            "payload_sha256": payload_sha256,
            "signature_header_present": bool(signature_header_present),
            "signature_header_names": list(signature_header_names or []),
            "webhook_secret_ref": webhook_secret_ref,
            "livemode": livemode,
            "customer_ref": customer_ref,
            "amount_minor": int(amount_minor),
            "currency": currency,
            "invoice_ref": invoice_ref,
            "usage_units": int(usage_units),
            "metadata": dict(metadata or {}),
            "auth_key_id": auth_key_id,
        }
        if self.uses_http:
            if webhook_secret_resolver is not None or provider_verifier is not None:
                raise SecretInputError("trusted webhook verifiers are process-local and cannot be sent through public HTTP")
            if raw_body is not None or stripe_signature_header is not None:
                raise SecretInputError("raw Stripe webhook verification must be performed by the HTTP server from the original request body and headers")
            return self._request("billing_webhook_ingest", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        from services.api.billing import BillingLedger, verify_billing_webhook_envelope

        if self._billing_ledger is None:
            self._billing_ledger = BillingLedger()
        envelope_keys = {
            "tenant_id",
            "project_id",
            "provider",
            "mode",
            "event_type",
            "event_id",
            "payload_sha256",
            "signature_header_present",
            "signature_header_names",
            "webhook_secret_ref",
            "livemode",
        }
        envelope_payload = _drop_none({k: v for k, v in payload.items() if k in envelope_keys})
        envelope_payload.update(
            _drop_none(
                {
                    "raw_body": raw_body,
                    "stripe_signature_header": stripe_signature_header,
                    "webhook_secret_resolver": webhook_secret_resolver,
                    "provider_verifier": provider_verifier,
                    "received_at_unix": received_at_unix,
                    "tolerance_seconds": int(tolerance_seconds),
                }
            )
        )
        envelope_result = verify_billing_webhook_envelope(**envelope_payload)
        result = self._billing_ledger.ingest_provider_webhook(
            envelope=envelope_result,
            customer_ref=customer_ref,
            amount_minor=int(amount_minor),
            currency=currency,
            invoice_ref=invoice_ref,
            usage_units=int(usage_units),
            metadata=dict(metadata or {}),
        )
        return _envelope("billing_webhook_ingest", result)

    def billing_ledger(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request("billing_ledger", {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id}, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        from services.api.billing import BillingLedger

        if self._billing_ledger is None:
            self._billing_ledger = BillingLedger()
        return _envelope("billing_ledger", self._billing_ledger.public_ledger(tenant_id=tenant_id, project_id=project_id))

    def audit_log(
        self,
        tenant_id: str,
        project_id: str,
        *,
        auth_key_id: str | None = None,
        run_id: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        target_id: str | None = None,
        api_key_id: str | None = None,
        limit: int | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "auth_key_id": auth_key_id,
            "run_id": run_id,
            "action": action,
            "action_prefix": action_prefix,
            "target_id": target_id,
            "audit_api_key_id": api_key_id,
            "limit": limit,
        }
        if self.uses_http:
            return self._request("audit_log", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        snapshot = dict(
            self.service.audit_snapshot(
                tenant_id,
                project_id,
                auth_key_id=auth_key_id,
                action=action,
                target_id=target_id or run_id,
                api_key_id=api_key_id,
                limit=limit,
            )
        )
        snapshot.setdefault("event_count", len(snapshot.get("events", [])) if isinstance(snapshot.get("events"), list) else 0)
        return _envelope("audit_log", snapshot)

    def create_artifact_manifest(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        manifest: Mapping[str, Any],
        *,
        artifact_id: str | None = None,
        api_key_id: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "manifest": dict(manifest), "artifact_id": artifact_id, "api_key_id": api_key_id, "idempotency_key": idempotency_key, "request_id": request_id}
        if self.uses_http:
            return self._request("create_artifact_manifest", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("create_artifact_manifest", self.service.create_artifact_manifest(tenant_id, project_id, run_id, dict(manifest), artifact_id=artifact_id, api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id))

    def list_artifact_manifests(self, tenant_id: str, project_id: str, run_id: str, *, auth_key_id: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request("list_artifact_manifests", {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "auth_key_id": auth_key_id}, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("list_artifact_manifests", {"artifact_manifests": self.service.list_artifact_manifests(tenant_id, project_id, run_id, auth_key_id=auth_key_id)})

    def enqueue_worker_job(
        self,
        tenant_id: str,
        project_id: str,
        *,
        job_type: str,
        target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        api_key_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        request_payload = {"tenant_id": tenant_id, "project_id": project_id, "job_type": job_type, "target_id": target_id, "payload": dict(payload or {}), "job_id": job_id, "priority": int(priority), "max_attempts": int(max_attempts), "api_key_id": api_key_id, "idempotency_key": idempotency_key, "request_id": request_id}
        if self.uses_http:
            return self._request("enqueue_worker_job", request_payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("enqueue_worker_job", self.service.enqueue_worker_job(tenant_id, project_id, job_type=job_type, target_id=target_id, payload=dict(payload or {}), job_id=job_id, priority=int(priority), max_attempts=int(max_attempts), api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id))

    def lease_worker_job(
        self,
        tenant_id: str,
        project_id: str,
        *,
        lease_owner_id: str,
        lease_seconds: float = 300.0,
        job_type: str | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "lease_owner_id": lease_owner_id, "lease_seconds": float(lease_seconds), "job_type": job_type, "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("lease_worker_job", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("lease_worker_job", self.service.lease_worker_job(tenant_id, project_id, lease_owner_id=lease_owner_id, lease_seconds=float(lease_seconds), job_type=job_type, api_key_id=api_key_id, request_id=request_id))

    def heartbeat_worker_job(self, tenant_id: str, project_id: str, job_id: str, *, lease_owner_id: str, lease_seconds: float = 300.0, api_key_id: str | None = None, api_key: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None, request_id: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "job_id": job_id, "lease_owner_id": lease_owner_id, "lease_seconds": float(lease_seconds), "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("heartbeat_worker_job", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("heartbeat_worker_job", self.service.heartbeat_worker_job(tenant_id, project_id, job_id, lease_owner_id=lease_owner_id, lease_seconds=float(lease_seconds), api_key_id=api_key_id, request_id=request_id))

    def complete_worker_job(self, tenant_id: str, project_id: str, job_id: str, result: Mapping[str, Any] | None = None, *, lease_owner_id: str, api_key_id: str | None = None, api_key: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None, request_id: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "job_id": job_id, "result": dict(result or {}), "lease_owner_id": lease_owner_id, "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("complete_worker_job", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("complete_worker_job", self.service.complete_worker_job(tenant_id, project_id, job_id, dict(result or {}), lease_owner_id=lease_owner_id, api_key_id=api_key_id, request_id=request_id))

    def fail_worker_job(self, tenant_id: str, project_id: str, job_id: str, error_payload: Mapping[str, Any] | None = None, *, lease_owner_id: str, retry_after_seconds: float | None = None, api_key_id: str | None = None, api_key: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None, request_id: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "job_id": job_id, "error": dict(error_payload or {}), "lease_owner_id": lease_owner_id, "retry_after_seconds": retry_after_seconds, "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("fail_worker_job", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("fail_worker_job", self.service.fail_worker_job(tenant_id, project_id, job_id, dict(error_payload or {}), lease_owner_id=lease_owner_id, retry_after_seconds=retry_after_seconds, api_key_id=api_key_id, request_id=request_id))

    def list_worker_jobs(self, tenant_id: str, project_id: str, *, status: str | None = None, job_type: str | None = None, limit: int | None = None, auth_key_id: str | None = None, api_key: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "status": status, "job_type": job_type, "limit": limit, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("list_worker_jobs", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("list_worker_jobs", self.service.list_worker_jobs(tenant_id, project_id, status=status, job_type=job_type, limit=limit, auth_key_id=auth_key_id))

    def verify_audit_chain(
        self,
        tenant_id: str,
        project_id: str,
        *,
        auth_key_id: str | None = None,
        action: str | None = None,
        target_id: str | None = None,
        api_key_id: str | None = None,
        limit: int | None = None,
        request_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id, "action": action, "target_id": target_id, "audit_api_key_id": api_key_id, "limit": limit, "request_id": request_id}
        if self.uses_http:
            return self._request("verify_audit_chain", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        return _envelope("verify_audit_chain", self.service.verify_audit_chain_snapshot(tenant_id, project_id, auth_key_id=auth_key_id, action=action, target_id=target_id, api_key_id=api_key_id, limit=limit, request_id=request_id))

    def build_release_evidence_packet(self, tenant_id: str, project_id: str, run_id: str, *, auth_key_id: str | None = None, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> JsonDict:
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        if self.uses_http:
            return self._request("release_evidence", {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "auth_key_id": auth_key_id}, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        from services.api.platform import build_release_evidence_packet, usage_billing_rollup

        packet = build_release_evidence_packet(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            lifecycle=self.service.lifecycle_snapshot(tenant_id, project_id, run_id),
            artifact_manifest={"artifacts": self.service.list_artifact_manifests(tenant_id, project_id, run_id, auth_key_id=auth_key_id)},
            billing_rollup=usage_billing_rollup(list(self.service.store.usage_ledger.values()), tenant_id=tenant_id, project_id=project_id, billing_period="local"),
            audit_chain=self.service.audit_snapshot(tenant_id, project_id, auth_key_id=auth_key_id, target_id=run_id).get("chain", {}),
        )
        return _envelope("release_evidence", packet)

    def verify_release_evidence_packet(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        packet: Mapping[str, Any] | None = None,
        auth_key_id: str | None = None,
        request_id: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        bearer_api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        auth_headers = _bearer_auth_headers(api_key_secret=api_key_secret, bearer_api_key=bearer_api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "packet": dict(packet) if packet is not None else None, "auth_key_id": auth_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("verify_release_evidence_packet", payload, headers=auth_headers)
        _reject_hosted_bearer_headers(auth_headers)
        source = "submitted_packet" if packet is not None else "current_snapshot"
        if packet is None:
            packet = self.build_release_evidence_packet(tenant_id, project_id, run_id, auth_key_id=auth_key_id)["result"]
        return _envelope("verify_release_evidence_packet", {**self.service.verify_release_evidence_packet(tenant_id, project_id, dict(packet), run_id=run_id, auth_key_id=auth_key_id, request_id=request_id), "source": source})

    def _request(self, operation: str, payload: Mapping[str, Any], *, headers: Mapping[str, str] | None = None) -> JsonDict:
        if not self.base_url:  # pragma: no cover
            raise SaaSClientError("HTTP transport requested without base_url")
        method, path = _operation_route(operation, payload)
        body = _drop_none(payload)
        url = urljoin(self.base_url, path.lstrip("/"))
        if method == "GET" and body:
            url = f"{url}?{urlencode(body)}"
        response = dict(_call_http_transport(self._http_transport, method, url, {} if method == "GET" else body, headers=headers))
        if {"schema_version", "operation", "result"}.issubset(response):
            return redact_sensitive(response)
        return _remote_envelope(operation, response)


_GET_OPERATIONS = {
    "list_api_keys",
    "api_key_rate_limit_snapshot",
    "commercial_auth_payment_snapshot",
    "get_account_connection",
    "lifecycle_snapshot",
    "quota_snapshot",
    "usage_snapshot",
    "billing_ledger",
    "audit_log",
    "list_artifact_manifests",
    "list_worker_jobs",
    "release_evidence",
    "state",
}


def _operation_route(operation: str, payload: Mapping[str, Any] | None = None) -> tuple[str, str]:
    payload = payload or {}
    method = "GET" if operation in _GET_OPERATIONS else "POST"
    if operation == "bootstrap_project":
        return method, "/v1/bootstrap"
    if operation == "state":
        return method, "/v1/state"
    project_id = _required_route_value(payload, "project_id", operation)
    project_path = f"/v1/projects/{_quote_path(project_id)}"
    if operation in {"create_api_key", "list_api_keys"}:
        return method, f"{project_path}/api-keys"
    if operation in {"revoke_api_key", "verify_api_key_secret", "configure_api_key_rate_limit"}:
        key_id = _required_route_value(payload, "key_id", operation)
        suffix = {"revoke_api_key": "revoke", "verify_api_key_secret": "verify", "configure_api_key_rate_limit": "rate-limit"}[operation]
        return method, f"{project_path}/api-keys/{_quote_path(key_id)}/{suffix}"
    if operation == "api_key_rate_limit_snapshot":
        return method, f"{project_path}/api-keys/rate-limits"
    if operation == "commercial_auth_payment_snapshot":
        return method, f"{project_path}/commercial-auth-payment"
    if operation in {
        "start_account_connection",
        "get_account_connection",
        "disconnect_account_connection",
    }:
        from .account_connection import normalize_account_connection_provider

        provider = normalize_account_connection_provider(
            _required_route_value(payload, "provider", operation)
        )
        action = {
            "start_account_connection": "start",
            "get_account_connection": "connection",
            "disconnect_account_connection": "disconnect",
        }[operation]
        return method, f"{project_path}/oauth/{provider}/{action}"
    if operation in {"configure_oauth_provider", "begin_oauth_authorization", "create_oauth_session", "configure_commercial_provider", "record_payment_mode_boundary"}:
        suffix = {
            "configure_oauth_provider": "commercial-auth-payment/oauth-providers/configure",
            "begin_oauth_authorization": "commercial-auth-payment/oauth-authorizations/begin",
            "create_oauth_session": "commercial-auth-payment/oauth-sessions/create",
            "configure_commercial_provider": "commercial-auth-payment/providers/configure",
            "record_payment_mode_boundary": "commercial-auth-payment/payments/mode-boundary",
        }[operation]
        return method, f"{project_path}/{suffix}"
    if operation in {"revoke_oauth_session", "disconnect_oauth_session"}:
        session_id = _required_route_value(payload, "session_id", operation)
        action = "revoke" if operation == "revoke_oauth_session" else "disconnect"
        return method, f"{project_path}/commercial-auth-payment/oauth-sessions/{_quote_path(session_id)}/{action}"
    if operation == "complete_oauth_authorization":
        flow_id = _required_route_value(payload, "flow_id", operation)
        return method, f"{project_path}/commercial-auth-payment/oauth-authorizations/{_quote_path(flow_id)}/complete"
    if operation == "sdk_submit":
        return method, f"{project_path}/sdk-submit"
    if operation in {"upload_run", "ingest_trace", "lifecycle_snapshot", "create_artifact_manifest", "list_artifact_manifests", "release_evidence", "release_evidence_verify", "verify_release_evidence_packet"}:
        run_id = _required_route_value(payload, "run_id", operation)
        suffix = {
            "upload_run": "upload",
            "ingest_trace": "trace-events",
            "lifecycle_snapshot": "lifecycle",
            "create_artifact_manifest": "artifact-manifests",
            "list_artifact_manifests": "artifact-manifests",
            "release_evidence": "release-evidence",
            "release_evidence_verify": "release-evidence/verify",
            "verify_release_evidence_packet": "release-evidence/verify",
        }[operation]
        return method, f"{project_path}/runs/{_quote_path(run_id)}/{suffix}"
    if operation in {"quota_snapshot", "usage_snapshot"}:
        suffix = "quota" if operation == "quota_snapshot" else "usage"
        return method, f"{project_path}/{suffix}"
    if operation in {"billing_checkout_plan", "billing_portal_plan", "billing_webhook_ingest", "billing_ledger"}:
        suffix = {
            "billing_checkout_plan": "billing/checkout-plan",
            "billing_portal_plan": "billing/portal-plan",
            "billing_webhook_ingest": "billing/webhooks/ingest",
            "billing_ledger": "billing/ledger",
        }[operation]
        return method, f"{project_path}/{suffix}"
    if operation in {"enqueue_worker_job", "lease_worker_job", "list_worker_jobs"}:
        suffix = {"enqueue_worker_job": "worker-jobs/enqueue", "lease_worker_job": "worker-jobs/lease", "list_worker_jobs": "worker-jobs"}[operation]
        return method, f"{project_path}/{suffix}"
    if operation in {"heartbeat_worker_job", "complete_worker_job", "fail_worker_job"}:
        job_id = _required_route_value(payload, "job_id", operation)
        suffix = {"heartbeat_worker_job": "heartbeat", "complete_worker_job": "complete", "fail_worker_job": "fail"}[operation]
        return method, f"{project_path}/worker-jobs/{_quote_path(job_id)}/{suffix}"
    if operation == "verify_audit_chain":
        return method, f"{project_path}/audit-chain/verify"
    if operation == "audit_log":
        return method, f"{project_path}/audit-log"
    raise SaaSClientError(f"unsupported SaaS HTTP operation: {operation}")


def _required_route_value(payload: Mapping[str, Any], key: str, operation: str) -> str:
    value = str(payload.get(key) or "")
    if not value:
        raise SaaSClientError(f"{key} is required for {operation} SaaS operations")
    return value


def _quote_path(value: str) -> str:
    return quote(value, safe="")


def _normalize_base_url(base_url: str) -> str:
    value = base_url.strip()
    if not value:
        raise SaaSClientError("base_url must not be empty")
    return value.rstrip("/") + "/"


def _drop_none(payload: Mapping[str, Any]) -> JsonDict:
    return {key: value for key, value in payload.items() if value is not None}


def _call_http_transport(transport: Callable[..., Mapping[str, Any]], method: str, url: str, payload: Mapping[str, Any], *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
    request_headers = dict(headers or {})
    try:
        return transport(url, payload, method=method, headers=request_headers)
    except TypeError as exc:
        try:
            signature(transport).bind(url, payload, method=method, headers=request_headers)
        except TypeError:
            try:
                return transport(method, url, payload, headers=request_headers)
            except TypeError as positional_exc:
                try:
                    signature(transport).bind(method, url, payload, headers=request_headers)
                except TypeError:
                    pass
                else:
                    raise positional_exc
            try:
                return transport(url, payload, method=method)
            except TypeError as method_exc:
                try:
                    signature(transport).bind(url, payload, method=method)
                except TypeError:
                    try:
                        return transport(method, url, payload)
                    except TypeError as positional_no_headers_exc:
                        try:
                            signature(transport).bind(method, url, payload)
                        except TypeError:
                            return transport(url, payload)
                        else:
                            raise positional_no_headers_exc
                else:
                    raise method_exc
        else:
            raise
        raise exc


def _post_json(url: str, payload: Mapping[str, Any], *, method: str = "POST", headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
    upper_method = method.upper()
    body = None if upper_method == "GET" else json.dumps(payload, sort_keys=True).encode("utf-8")
    request_headers = {"Accept": "application/json", **dict(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=request_headers, method=upper_method)
    try:
        with request.urlopen(req, timeout=30) as resp:  # nosec - caller supplied local hosted adapter URL.
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SaaSClientError(f"HTTP {exc.code} from hosted adapter: {redact_text(detail)}") from exc
    except error.URLError as exc:
        raise SaaSClientError(f"hosted adapter request failed: {redact_text(str(exc.reason))}") from exc
    data = json.loads(raw or "{}")
    if not isinstance(data, Mapping):
        raise SaaSClientError("hosted adapter JSON response must be an object")
    return data


def _remote_envelope(operation: str, result: Mapping[str, Any]) -> JsonDict:
    return {
        "schema_version": SAAS_CLIENT_VERSION,
        "operation": operation,
        "result": redact_sensitive(result),
        "metadata": {"local_only": False, "ashr_api_used": False, "raw_auth_material_used": False, "transport": "http"},
    }


def load_json_file(path: str | Path) -> Any:
    _assert_public_control_plane_path(path)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hosted_route_scope_manifest() -> JsonDict:
    return {
        "schema_version": "ashr.clone.hosted_route_scope_manifest.v1",
        "client": "python",
        "public_safe": True,
        "source_policy": {"private_evidence_read": False, "raw_payloads_included": False, "tokens_included": False},
        "routes": [
            {"route": route, "required_scopes": list(scopes)}
            for route, scopes in sorted(HOSTED_ROUTE_SCOPE_REQUIREMENTS.items())
        ],
    }


def consume_go_route_scope_manifest(manifest: Mapping[str, Any] | str | Path) -> JsonDict:
    snapshot = load_json_file(manifest) if isinstance(manifest, (str, Path)) else dict(manifest)
    if snapshot.get("public_safe") is not True:
        raise SaaSClientError("route/scope manifest must be public_safe")
    source_policy = snapshot.get("source_policy")
    safe_source_policy = {"private_evidence_read": False, "raw_payloads_included": False, "tokens_included": False}
    if source_policy is None and snapshot.get("raw_payloads_included") is False:
        source_policy = safe_source_policy
    if source_policy != safe_source_policy:
        raise SaaSClientError("route/scope manifest has unsafe source policy")

    go_routes = {str(route) for route in snapshot.get("go_manifest_routes", [])}
    if not go_routes:
        go_routes = _go_routes_from_openapi(snapshot)
    hosted_routes = set(HOSTED_ROUTE_SCOPE_REQUIREMENTS)
    consumable_go_routes = sorted(go_routes & hosted_routes)
    unsupported_go_routes = sorted(go_routes - hosted_routes)
    route_scope_docs = _extract_go_route_scope_docs(snapshot)
    docs_consumption = _consume_go_route_scope_docs(route_scope_docs) if route_scope_docs is not None else None
    return {
        "schema_version": "ashr.clone.go_route_scope_consumption.v1",
        "client": "python",
        "public_safe": True,
        "source_policy": source_policy,
        "consumable_go_routes": consumable_go_routes,
        "unsupported_go_routes": unsupported_go_routes,
        "unsupported_go_route_gaps": _validate_unsupported_go_route_gaps(go_routes, hosted_routes),
        "client_only_routes": sorted(hosted_routes - go_routes),
        "route_scopes": [
            {"route": route, "required_scopes": list(HOSTED_ROUTE_SCOPE_REQUIREMENTS[route])}
            for route in consumable_go_routes
        ],
        "route_scope_docs": docs_consumption,
    }


def consume_official_api_mutating_calibration_index(index: Mapping[str, Any] | str | Path) -> JsonDict:
    snapshot = load_json_file(index) if isinstance(index, (str, Path)) else dict(index)
    if snapshot.get("schema_version") != MUTATING_CALIBRATION_INDEX_SCHEMA_VERSION:
        raise SaaSClientError("official API mutating calibration index schema_version drift")
    if snapshot.get("public_safe") is not True or snapshot.get("raw_payloads_included") is not False or snapshot.get("secret_values_included") is not False:
        raise SaaSClientError("official API mutating calibration index must be public-safe")
    records = snapshot.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise SaaSClientError("official API mutating calibration index records must be a list")

    by_modality: dict[str, JsonDict] = {}
    for raw_record in records:
        if not isinstance(raw_record, Mapping):
            raise SaaSClientError("official API mutating calibration index record must be an object")
        modalities = raw_record.get("summary_modalities")
        if not isinstance(modalities, Sequence) or isinstance(modalities, (str, bytes, bytearray)) or len(modalities) != 1:
            raise SaaSClientError("official API mutating calibration index record must bind one modality")
        modality = str(modalities[0])
        if modality not in MUTATING_CALIBRATION_MODALITIES:
            raise SaaSClientError(f"official API mutating calibration index has unsupported modality: {modality}")
        step_ids = [str(step) for step in raw_record.get("mutating_step_ids", []) if isinstance(step, str)]
        expected_step = f"create-request-{modality}"
        if expected_step not in step_ids:
            raise SaaSClientError(f"official API mutating calibration index missing {expected_step}")
        private_manifest = str(raw_record.get("private_manifest", ""))
        if not private_manifest.startswith("docs/evidence/private_refs/"):
            raise SaaSClientError("official API mutating calibration index record must point to ignored private evidence")
        if raw_record.get("raw_payloads_included") is not False:
            raise SaaSClientError("official API mutating calibration index record must exclude raw payloads")
        by_modality[modality] = {
            "modality": modality,
            "status": raw_record.get("status"),
            "quota_block_count": int(raw_record.get("quota_block_count", 0) or 0),
            "observed_error_kinds": sorted(str(kind) for kind in raw_record.get("observed_error_kinds", []) if isinstance(kind, str)),
            "mutating_step_ids": step_ids,
            "private_manifest": private_manifest,
            "read_steps": int(raw_record.get("read_steps", 0) or 0),
            "total_steps": int(raw_record.get("total_steps", 0) or 0),
        }

    missing = [modality for modality in MUTATING_CALIBRATION_MODALITIES if modality not in by_modality]
    if missing:
        raise SaaSClientError(f"official API mutating calibration index missing modalities: {','.join(missing)}")

    return {
        "schema_version": "ashr.clone.official_api_mutating_calibration_consumption.v1",
        "client": "python",
        "public_safe": True,
        "modalities": list(MUTATING_CALIBRATION_MODALITIES),
        "quota_blocked_modalities": [modality for modality in MUTATING_CALIBRATION_MODALITIES if by_modality[modality]["quota_block_count"] > 0],
        "records": [by_modality[modality] for modality in MUTATING_CALIBRATION_MODALITIES],
    }


def _go_routes_from_openapi(snapshot: Mapping[str, Any]) -> set[str]:
    routes: set[str] = set()
    paths = snapshot.get("paths")
    if isinstance(paths, Mapping):
        for path, path_item in paths.items():
            if not isinstance(path_item, Mapping):
                continue
            for method in ("get", "post", "put", "patch", "delete"):
                if method in path_item:
                    routes.add(f"{method.upper()} {path}")
    manifest_routes = snapshot.get("routes")
    if isinstance(manifest_routes, Sequence) and not isinstance(manifest_routes, (str, bytes, bytearray)):
        for route in manifest_routes:
            if isinstance(route, str) and " " in route:
                routes.add(route)
    return routes


def _extract_go_route_scope_docs(snapshot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("route_scope_docs", "go_route_scope_docs"):
        docs = snapshot.get(key)
        if isinstance(docs, Mapping):
            return docs
    artifact = snapshot.get("artifact")
    if isinstance(artifact, Mapping):
        return _extract_go_route_scope_docs(artifact)
    payload = snapshot.get("payload")
    if isinstance(payload, Mapping):
        return _extract_go_route_scope_docs(payload)
    return None


def _consume_go_route_scope_docs(docs: Mapping[str, Any]) -> JsonDict:
    if docs.get("schema_version") != "ashr.clone.go_route_scope_docs.v1":
        raise SaaSClientError("route_scope_docs schema_version drift")
    if docs.get("public_safe") is not True or docs.get("raw_payloads_included") is not False:
        raise SaaSClientError("route_scope_docs must be public-safe and exclude raw payloads")
    if docs.get("source") != "generated_from_go_route_manifest":
        raise SaaSClientError("route_scope_docs source drift")

    groups = {str(group.get("name")): group for group in docs.get("route_groups", []) if isinstance(group, Mapping)}
    required_groups = {"usage_quota", "run_lifecycle", "audit"}
    missing_groups = sorted(required_groups - set(groups))
    if missing_groups:
        raise SaaSClientError(f"route_scope_docs missing route families: {','.join(missing_groups)}")

    _assert_route_scope_group(groups["usage_quota"], "usage_quota", {"GET /v1/projects/{project_id}/usage", "GET /v1/projects/{project_id}/quota", "POST /v1/projects/{project_id}/usage/quotas", "POST /v1/projects/{project_id}/quota/limits"}, {"usage:read"})
    _assert_route_scope_group(groups["run_lifecycle"], "run_lifecycle", {"GET /v1/projects/{project_id}/runs/{run_id}/lifecycle"}, {"run:lifecycle:read"})
    _assert_route_scope_group(groups["audit"], "audit", {"GET /v1/projects/{project_id}/audit-log", "POST /v1/projects/{project_id}/audit-chain/verify"}, {"audit:read"})

    plan_metrics = {str(metric.get("metric")): metric for metric in docs.get("plan_metrics", []) if isinstance(metric, Mapping)}
    required_metrics = {"graded_scenarios", "observations", "voice_minutes", "projects"}
    if missing_metrics := sorted(required_metrics - set(plan_metrics)):
        raise SaaSClientError(f"route_scope_docs missing plan metrics: {','.join(missing_metrics)}")

    plan_limits = {str(plan.get("plan")): plan for plan in docs.get("plan_limits", []) if isinstance(plan, Mapping)}
    for plan_name in ("Developer", "Startup"):
        plan = plan_limits.get(plan_name)
        if plan is None:
            raise SaaSClientError(f"route_scope_docs missing plan limit docs: {plan_name}")
        limits = {str(limit.get("metric")): limit for limit in plan.get("limits", []) if isinstance(limit, Mapping)}
        if missing_limits := sorted(required_metrics - set(limits)):
            raise SaaSClientError(f"route_scope_docs missing {plan_name} limits: {','.join(missing_limits)}")

    return {
        "schema_version": docs["schema_version"],
        "source": docs["source"],
        "public_safe": True,
        "route_families": sorted(required_groups),
        "plan_metrics": sorted(plan_metrics),
        "plan_limits": sorted(plan_limits),
    }


def _assert_route_scope_group(group: Mapping[str, Any], name: str, routes: set[str], scopes: set[str]) -> None:
    group_routes = {str(route) for route in group.get("routes", [])}
    group_scopes = {str(scope) for scope in group.get("scopes", [])}
    if missing_routes := sorted(routes - group_routes):
        raise SaaSClientError(f"route_scope_docs {name} missing routes: {','.join(missing_routes)}")
    if missing_scopes := sorted(scopes - group_scopes):
        raise SaaSClientError(f"route_scope_docs {name} missing scopes: {','.join(missing_scopes)}")


def _validate_unsupported_go_route_gaps(go_routes: set[str], hosted_routes: set[str]) -> list[JsonDict]:
    unsupported_routes = sorted(go_routes - hosted_routes)
    declared_routes = set(UNSUPPORTED_GO_ROUTE_GAPS)
    missing_routes = sorted(set(unsupported_routes) - declared_routes)
    stale_routes = sorted(route for route in declared_routes if route not in go_routes or route in hosted_routes)
    if missing_routes or stale_routes:
        missing = ",".join(missing_routes) if missing_routes else "none"
        stale = ",".join(stale_routes) if stale_routes else "none"
        raise SaaSClientError(f"Go route/scope gap registry drift: missing={missing}; stale={stale}")
    return [{"route": route, **UNSUPPORTED_GO_ROUTE_GAPS[route]} for route in unsupported_routes]


def _new_service() -> Any:
    from services.api.control_plane import SaaSControlPlaneService

    return SaaSControlPlaneService()


def _envelope(operation: str, result: Mapping[str, Any]) -> JsonDict:
    payload = {
        "schema_version": SAAS_CLIENT_VERSION,
        "operation": operation,
        "result": result,
        "metadata": {"local_only": True, "ashr_api_used": False, "raw_auth_material_used": False},
    }
    return payload


def _reject_raw_api_key(api_key: str | None) -> None:
    if api_key:
        raise SecretInputError("raw API key values are not accepted; use a local api_key_id handle")


def _bearer_auth_headers(*, api_key_secret: str | None = None, bearer_api_key: str | None = None) -> dict[str, str]:
    values = [value.strip() for value in (api_key_secret, bearer_api_key) if isinstance(value, str) and value.strip()]
    if len(values) > 1:
        raise SecretInputError("provide only one hosted bearer API key option")
    if not values:
        return {}
    secret = values[0]
    token = secret[7:].strip() if secret.lower().startswith("bearer ") else secret
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _reject_hosted_bearer_headers(headers: Mapping[str, str]) -> None:
    if headers:
        raise SecretInputError("hosted bearer API keys are only supported with base_url HTTP transport")


def _assert_public_control_plane_path(path: str | Path) -> None:
    parts = {part.lower() for part in Path(path).parts}
    if parts & BLOCKED_CONTROL_PLANE_PATH_PARTS:
        raise SecretInputError("refusing to read private_refs or .secrets input paths")


def redacted_error_message(exc: BaseException) -> str:
    return redact_text(str(exc))
