from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from packages.sdk.ashr_clone.saas import SaaSIngestionClient


SECRET = "local-test-secret-once"


@pytest.mark.parametrize("enveloped", [False, True])
def test_explicit_api_key_reveal_preserves_one_time_secret(enveloped: bool) -> None:
    def transport(method: str, url: str, payload: Mapping[str, Any], **_: Any) -> Mapping[str, Any]:
        result = {
            "key_id": "key_test",
            "one_time_secret": SECRET,
            "one_time_secret_displayed": True,
            "nested": {"client_secret": "must-not-leak"},
        }
        if enveloped:
            return {"schema_version": "v1", "operation": "create_api_key", "result": result}
        return result

    client = SaaSIngestionClient(base_url="http://localhost", http_transport=transport)
    response = client.create_api_key(
        "tenant_test",
        "project_test",
        key_id="key_test",
        name="test",
        scopes=["run:submit"],
        reveal_secret=True,
    )

    assert response["result"]["one_time_secret"] == SECRET
    assert response["result"]["one_time_secret_displayed"] is True
    assert response["result"]["nested"]["client_secret"] == "[redacted]"


def test_api_key_secret_stays_redacted_without_explicit_reveal() -> None:
    def transport(*_: Any, **__: Any) -> Mapping[str, Any]:
        return {"one_time_secret": SECRET, "one_time_secret_displayed": True}

    client = SaaSIngestionClient(base_url="http://localhost", http_transport=transport)
    response = client.create_api_key(
        "tenant_test", "project_test", key_id="key_test", name="test", scopes=[], reveal_secret=False
    )
    assert response["result"]["one_time_secret"] == "[redacted]"


def test_other_operations_cannot_smuggle_one_time_secret() -> None:
    def transport(*_: Any, **__: Any) -> Mapping[str, Any]:
        return {"one_time_secret": SECRET, "one_time_secret_displayed": True}

    client = SaaSIngestionClient(base_url="http://localhost", http_transport=transport)
    response = client.lifecycle_snapshot("tenant_test", "project_test", "run_test")
    assert response["result"]["one_time_secret"] == "[redacted]"


@pytest.mark.parametrize(
    "result",
    [
        {"one_time_secret": SECRET},
        {"one_time_secret": SECRET, "one_time_secret_displayed": False},
        {"one_time_secret": "", "one_time_secret_displayed": True},
        {"one_time_secret": None, "one_time_secret_displayed": True},
        {"one_time_secret": 42, "one_time_secret_displayed": True},
        {"nested": {"one_time_secret": SECRET}, "one_time_secret_displayed": True},
    ],
)
def test_malformed_reveal_responses_never_restore_secret(result: Mapping[str, Any]) -> None:
    def transport(*_: Any, **__: Any) -> Mapping[str, Any]:
        return result

    client = SaaSIngestionClient(base_url="http://localhost", http_transport=transport)
    response = client.create_api_key(
        "tenant_test",
        "project_test",
        key_id="key_test",
        name="test",
        scopes=["run:submit"],
        reveal_secret=True,
    )

    assert SECRET not in repr(response)
    if "one_time_secret" in response["result"]:
        assert response["result"]["one_time_secret"] in {"[redacted]", ""}


def test_error_and_nested_fields_remain_redacted_when_secret_is_restored() -> None:
    def transport(*_: Any, **__: Any) -> Mapping[str, Any]:
        return {
            "one_time_secret": SECRET,
            "one_time_secret_displayed": True,
            "error": f"failed with {SECRET}",
            "nested": {
                "one_time_secret": SECRET,
                "authorization": f"Bearer {SECRET}",
            },
        }

    client = SaaSIngestionClient(base_url="http://localhost", http_transport=transport)
    response = client.create_api_key(
        "tenant_test",
        "project_test",
        key_id="key_test",
        name="test",
        scopes=["run:submit"],
        reveal_secret=True,
    )

    assert response["result"]["one_time_secret"] == SECRET
    assert response["result"]["nested"]["one_time_secret"] == "[redacted]"
    assert response["result"]["nested"]["authorization"] == "[redacted]"
    assert response["result"]["error"] == "failed with [redacted]"
