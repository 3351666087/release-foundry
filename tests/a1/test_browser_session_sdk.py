from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

import ashr_clone
import ashr_clone.browser_session as browser_session
from ashr_clone.browser_session import (
    BROWSER_SESSION_COOKIE_NAMES,
    BROWSER_SESSION_ERROR_CODES,
    BROWSER_SESSION_MODALITIES,
    BrowserHTTPResponse,
    BrowserSessionClient,
    BrowserSessionCookieJar,
    BrowserSessionError,
    browser_session_capability_manifest,
    browser_session_openapi_document,
    build_browser_cookie_replacement,
    main,
)


NOW = datetime(2026, 7, 11, 4, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


def _cookie(name: str, value: str, max_age: int) -> str:
    expires = NOW + timedelta(seconds=max_age)
    return (
        f"{name}={value}; Path=/; Expires={expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}; "
        f"Max-Age={max_age}; HttpOnly; Secure; SameSite=Strict"
    )


def _clear_cookie(name: str) -> str:
    return (
        f"{name}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT; "
        "Max-Age=-1; HttpOnly; Secure; SameSite=Strict"
    )


class ScriptedTransport:
    def __init__(self, *responses: BrowserHTTPResponse) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> BrowserHTTPResponse:
        self.calls.append((method, url, dict(headers), body))
        return self.responses.pop(0)


def _login_response(
    access_value: str = "synthetic-access-one",
    refresh_value: str = "synthetic-refresh-one",
) -> BrowserHTTPResponse:
    return BrowserHTTPResponse.create(
        200,
        headers=[
            ("Cache-Control", "no-store"),
            ("Set-Cookie", _cookie(BROWSER_SESSION_COOKIE_NAMES[0], access_value, 1800)),
            ("Set-Cookie", _cookie(BROWSER_SESSION_COOKIE_NAMES[1], refresh_value, 86400)),
        ],
        body={
            "schema_version": "ashr.clone.unified_identity.v1",
            "purpose": "login",
            "credential_created": False,
        },
    )


def test_custom_caps_and_idempotent_replay_preserve_exact_expiry() -> None:
    replacement = build_browser_cookie_replacement(
        issued_at=NOW,
        access_expires_at=NOW + timedelta(hours=6),
        refresh_expires_at=NOW + timedelta(days=60),
        access_cap_seconds=1800,
        refresh_cap_seconds=7 * 24 * 60 * 60,
    )
    replay = replacement.replay(NOW + timedelta(seconds=37))

    assert replacement.access.max_age_seconds == 1800
    assert replacement.refresh.max_age_seconds == 7 * 24 * 60 * 60
    assert replay.access.expires_at == replacement.access.expires_at
    assert replay.refresh.expires_at == replacement.refresh.expires_at
    assert replay.access.max_age_seconds == 1763
    assert replay.refresh.max_age_seconds == 7 * 24 * 60 * 60 - 37
    public = replay.to_public_dict()
    assert public["contains_credential_values"] is False
    assert [cookie["name"] for cookie in public["cookies"]] == list(
        BROWSER_SESSION_COOKIE_NAMES
    )
    assert all(cookie["secure"] and cookie["http_only"] for cookie in public["cookies"])


def test_cookie_replay_rejects_expired_or_invalid_cap() -> None:
    replacement = build_browser_cookie_replacement(
        issued_at=NOW,
        access_expires_at=NOW + timedelta(minutes=10),
        refresh_expires_at=NOW + timedelta(hours=1),
    )
    with pytest.raises(BrowserSessionError) as expired:
        replacement.replay(NOW + timedelta(minutes=10))
    assert expired.value.code == "browser_session_cookie_expired"

    with pytest.raises(BrowserSessionError) as invalid:
        build_browser_cookie_replacement(
            issued_at=NOW,
            access_expires_at=NOW + timedelta(minutes=10),
            refresh_expires_at=NOW + timedelta(hours=1),
            access_cap_seconds=0,
        )
    assert invalid.value.code == "browser_session_invalid_request"


def test_login_cookie_jar_and_receipt_never_serialize_credentials(monkeypatch) -> None:
    monkeypatch.setattr(browser_session, "_now", lambda: NOW)
    access = "synthetic-access-private"
    refresh = "synthetic-refresh-private"
    proof = "synthetic-one-time-proof"
    transport = ScriptedTransport(_login_response(access, refresh))
    client = BrowserSessionClient("https://sessions.example.test", transport=transport)

    receipt = client.complete_login(
        tenant_id="tenant_main",
        account_id="account_main",
        challenge_id="challenge_main",
        verification_code=proof,
        channel="email",
        identifier="operator@example.test",
        display_name="Operator",
    )

    method, url, headers, raw_body = transport.calls[0]
    assert method == "POST"
    assert url == "https://sessions.example.test/v1/identity-verification/verify"
    assert headers["Origin"] == "https://sessions.example.test"
    assert headers["Sec-Fetch-Site"] == "same-origin"
    assert "Cookie" not in headers
    assert json.loads(raw_body or b"{}")["code"] == proof
    assert receipt.status == "authenticated"
    assert receipt.cookie_state["cookie_count"] == 2
    assert receipt.cookie_state["access_credential_present"] is True
    assert receipt.cookie_state["refresh_credential_present"] is True

    rendered = " ".join(
        [
            repr(client.cookie_jar),
            json.dumps(client.cookie_jar.to_public_dict(), sort_keys=True),
            json.dumps(receipt.to_public_dict(), sort_keys=True),
        ]
    )
    assert access not in rendered
    assert refresh not in rendered
    assert proof not in rendered
    assert "credential_values_exposed\": false" in rendered.lower()


def test_refresh_sends_cookie_credentials_only_inside_transport_and_rotates(monkeypatch) -> None:
    monkeypatch.setattr(browser_session, "_now", lambda: NOW)
    old_access = "synthetic-access-old"
    old_refresh = "synthetic-refresh-old"
    new_access = "synthetic-access-new"
    new_refresh = "synthetic-refresh-new"
    transport = ScriptedTransport(
        _login_response(old_access, old_refresh),
        BrowserHTTPResponse.create(
            200,
            headers=[
                ("Set-Cookie", _cookie(BROWSER_SESSION_COOKIE_NAMES[0], new_access, 900)),
                ("Set-Cookie", _cookie(BROWSER_SESSION_COOKIE_NAMES[1], new_refresh, 7200)),
            ],
            body={"schema_version": "ashr.identity_session_refresh.v1", "status": "rotated"},
        ),
    )
    client = BrowserSessionClient("https://sessions.example.test", transport=transport)
    client.complete_login(
        tenant_id="tenant_main",
        account_id="account_main",
        challenge_id="challenge_main",
        verification_code="synthetic-proof",
        channel="phone",
        identifier="13800000000",
    )
    receipt = client.refresh(
        "project_main", "account_main", idempotency_key="refresh_round54_0001"
    )

    method, url, headers, body = transport.calls[1]
    assert method == "POST"
    assert url.endswith(
        "/v1/projects/project_main/accounts/account_main/browser-sessions/refresh"
    )
    assert body is None
    assert headers["Idempotency-Key"] == "refresh_round54_0001"
    assert old_access in headers["Cookie"] and old_refresh in headers["Cookie"]
    rendered = json.dumps(receipt.to_public_dict(), sort_keys=True)
    for private in (old_access, old_refresh, new_access, new_refresh):
        assert private not in rendered
    assert receipt.status == "rotated"
    assert [item.max_age_seconds for item in receipt.replacement_cookies] == [900, 7200]


def test_refresh_reuse_clears_jar_and_uses_canonical_error_not_server_message(monkeypatch) -> None:
    monkeypatch.setattr(browser_session, "_now", lambda: NOW)
    private_detail = "synthetic-private-server-detail"
    transport = ScriptedTransport(
        _login_response(),
        BrowserHTTPResponse.create(
            409,
            headers=[
                ("Set-Cookie", _clear_cookie(BROWSER_SESSION_COOKIE_NAMES[0])),
                ("Set-Cookie", _clear_cookie(BROWSER_SESSION_COOKIE_NAMES[1])),
            ],
            body={
                "status": "error",
                "error": {
                    "code": "identity_session_refresh_reused",
                    "message": private_detail,
                },
            },
        ),
    )
    client = BrowserSessionClient("https://sessions.example.test", transport=transport)
    client.complete_login(
        tenant_id="tenant_main",
        account_id="account_main",
        challenge_id="challenge_main",
        verification_code="synthetic-proof",
        channel="email",
        identifier="operator@example.test",
    )

    with pytest.raises(BrowserSessionError) as captured:
        client.refresh(
            "project_main", "account_main", idempotency_key="refresh_round54_0002"
        )
    error = captured.value
    assert error.code == "identity_session_refresh_reused"
    assert error.status == 409
    assert str(error) == "identity session refresh credential was reused"
    assert private_detail not in str(error)
    assert client.cookie_jar.to_public_dict(now=NOW)["cookie_count"] == 0
    assert private_detail not in json.dumps(error.to_public_dict(), sort_keys=True)


def test_logout_and_revoke_all_clear_local_cookie_state(monkeypatch) -> None:
    monkeypatch.setattr(browser_session, "_now", lambda: NOW)
    for operation in ("logout", "revoke_all"):
        transport = ScriptedTransport(_login_response(), BrowserHTTPResponse.create(204))
        client = BrowserSessionClient("https://sessions.example.test", transport=transport)
        client.complete_login(
            tenant_id="tenant_main",
            account_id="account_main",
            challenge_id="challenge_main",
            verification_code="synthetic-proof",
            channel="email",
            identifier="operator@example.test",
        )
        receipt = getattr(client, operation)(
            "project_main", "account_main", idempotency_key=f"{operation}_round54"
        )
        assert receipt.http_status == 204
        assert receipt.cookie_state["cookie_count"] == 0
        assert transport.calls[1][3] is None


def test_cookie_ingestion_is_atomic_when_a_later_cookie_is_invalid(monkeypatch) -> None:
    monkeypatch.setattr(browser_session, "_now", lambda: NOW)
    jar = browser_session.BrowserSessionCookieJar("https://sessions.example.test")
    response = BrowserHTTPResponse.create(
        303,
        headers=[
            ("Set-Cookie", _cookie(BROWSER_SESSION_COOKIE_NAMES[0], "access", 60)),
            (
                "Set-Cookie",
                f"{BROWSER_SESSION_COOKIE_NAMES[1]}=refresh; Path=/; "
                "Max-Age=120; SameSite=Strict",
            ),
        ],
    )

    with pytest.raises(BrowserSessionError) as captured:
        jar.ingest(response, now=NOW)

    assert captured.value.code == "browser_session_response_invalid"
    assert jar.to_public_dict(now=NOW)["cookie_count"] == 0


def test_303_redirect_is_same_origin_only(monkeypatch) -> None:
    monkeypatch.setattr(browser_session, "_now", lambda: NOW)
    safe = ScriptedTransport(
        BrowserHTTPResponse.create(
            303,
            headers=[
                ("Location", "/console?login=complete"),
                ("Set-Cookie", _cookie(BROWSER_SESSION_COOKIE_NAMES[0], "access", 60)),
                ("Set-Cookie", _cookie(BROWSER_SESSION_COOKIE_NAMES[1], "refresh", 120)),
            ],
        )
    )
    receipt = BrowserSessionClient(
        "https://sessions.example.test", transport=safe
    ).complete_login(
        tenant_id="tenant_main",
        account_id="account_main",
        challenge_id="challenge_main",
        verification_code="synthetic-proof",
        channel="email",
        identifier="operator@example.test",
    )
    assert receipt.redirect_to == "/console?login=complete"

    unsafe = ScriptedTransport(
        BrowserHTTPResponse.create(303, headers={"Location": "https://other.example.test/"})
    )
    with pytest.raises(BrowserSessionError) as captured:
        BrowserSessionClient(
            "https://sessions.example.test", transport=unsafe
        ).complete_login(
            tenant_id="tenant_main",
            account_id="account_main",
            challenge_id="challenge_main",
            verification_code="synthetic-proof",
            channel="email",
            identifier="operator@example.test",
        )
    assert captured.value.code == "browser_session_response_invalid"


def test_https_is_default_and_local_http_requires_explicit_opt_in() -> None:
    with pytest.raises(BrowserSessionError) as captured:
        BrowserSessionClient("http://localhost:8787")
    assert captured.value.code == "identity_session_secure_transport_required"
    client = BrowserSessionClient(
        "http://localhost:8787", allow_insecure_localhost=True
    )
    assert client.origin == "http://localhost:8787"
    with pytest.raises(BrowserSessionError):
        BrowserSessionClient("http://example.test", allow_insecure_localhost=True)


def test_openapi_31_security_status_headers_and_public_examples_are_complete() -> None:
    document = browser_session_openapi_document()
    assert document["openapi"] == "3.1.0"
    assert document["x-ashr-modalities"] == list(BROWSER_SESSION_MODALITIES)
    schemes = document["components"]["securitySchemes"]
    assert schemes["browserAccessCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": BROWSER_SESSION_COOKIE_NAMES[0],
        "description": "Secure HttpOnly host-only access credential.",
    }
    assert schemes["browserRefreshCookie"]["name"] == BROWSER_SESSION_COOKIE_NAMES[1]
    serialized = json.dumps(document, sort_keys=True)
    for marker in ("ashr_live_", "Bearer ", "synthetic-private", "cookie=value"):
        assert marker not in serialized

    statuses: set[str] = set()
    for path_item in document["paths"].values():
        for operation in path_item.values():
            statuses.update(operation["responses"])
            assert operation["x-ashr-modalities"] == list(BROWSER_SESSION_MODALITIES)
    assert {"303", "204", "401", "409", "429", "503"}.issubset(statuses)
    refresh = document["paths"][
        "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh"
    ]["post"]
    refs = {item["$ref"] for item in refresh["parameters"]}
    assert "#/components/parameters/IdempotencyKey" in refs
    assert refresh["security"] == [
        {"browserAccessCookie": [], "browserRefreshCookie": []}
    ]


def test_capability_manifest_marks_current_go_gaps_without_claiming_support() -> None:
    manifest = browser_session_capability_manifest()
    operations = {item["operation"]: item for item in manifest["operations"]}
    assert operations["complete_login"]["go_executable"] is True
    assert operations["refresh"]["go_executable"] is True
    assert operations["bootstrap"]["go_executable"] is False
    assert operations["logout"]["go_executable"] is False
    assert operations["revoke_all"]["go_executable"] is False
    assert manifest["modalities"] == ["text", "image", "audio", "file", "video"]
    assert manifest["stable_error_codes"] == list(BROWSER_SESSION_ERROR_CODES)


def test_root_exports_and_cli_are_public_safe(capsys) -> None:
    assert ashr_clone.BrowserSessionClient is BrowserSessionClient
    assert ashr_clone.browser_session_openapi_document is browser_session_openapi_document
    assert main(["capabilities"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == browser_session_capability_manifest()
    assert main(
        [
            "cookie-contract",
            "--issued-at",
            "2026-07-11T04:00:00Z",
            "--access-expires-at",
            "2026-07-11T06:00:00Z",
            "--refresh-expires-at",
            "2026-08-11T04:00:00Z",
            "--access-cap-seconds",
            "1800",
            "--refresh-cap-seconds",
            "604800",
            "--replayed-at",
            "2026-07-11T04:00:30Z",
        ]
    ) == 0
    contract = json.loads(capsys.readouterr().out)
    assert contract["cookies"][0]["max_age_seconds"] == 1770
    assert contract["contains_credential_values"] is False


def test_generated_openapi_fixture_matches_python_document() -> None:
    fixture = json.loads(
        (ROOT / "tests/a1/fixtures/browser_session_openapi_3_1.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture == browser_session_openapi_document()
