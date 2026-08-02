from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GO_PROVIDER = ROOT / "packages/go/releasefoundry/oauth_google.go"
GO_SERVICE = ROOT / "packages/go/releasefoundry/oauth_provider.go"
GO_HTTP = ROOT / "packages/go/releasefoundry/oauth_provider_http.go"
GO_SERVER = ROOT / "packages/go/releasefoundry/server.go"
PYTHON_CONTRACT = ROOT / "packages/sdk/releasefoundry/account_connection.py"
TS_CLIENT = ROOT / "packages/ts/releasefoundry/src/account-connections.ts"
EVIDENCE = (
    ROOT
    / "docs/a1/evidence/google_oauth_localhost_calibration_template.json"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    match = re.search(
        rf"{re.escape(signature)}(?P<body>.*?)(?={re.escape(next_signature)})",
        source,
        re.S,
    )
    assert match, f"function boundary not found: {signature}"
    return match.group("body")


def test_go_google_oidc_uses_exact_scopes_pkce_nonce_and_post_exchange() -> None:
    source = _read(GO_PROVIDER)

    assert 'defaultGoogleScopes = []string{"email", "openid", "profile"}' in source
    assert 'query.Set("response_type", "code")' in source
    assert 'query.Set("state", request.State)' in source
    assert 'query.Set("nonce", request.Nonce)' in source
    assert 'query.Set("code_challenge", request.CodeChallenge)' in source
    assert 'query.Set("code_challenge_method", "S256")' in source
    assert (
        'provider.newUpstreamRequest(ctx, http.MethodPost, provider.tokenURL'
        in source
    )
    assert '"code_verifier": {exchange.CodeVerifier}' in source
    assert '"grant_type": {"authorization_code"}' in source


def test_go_google_oidc_rejects_issuer_audience_nonce_and_unverified_email() -> None:
    source = _read(GO_PROVIDER)

    assert "!oauthContainsString(provider.issuers, claims.Issuer)" in source
    assert (
        "!claims.Audience.Contains(request.ClientID) || "
        "len(claims.Audience.Values()) != 1"
    ) in source
    assert "claims.Nonce != request.Nonce" in source
    assert "strings.TrimSpace(claims.Email) == \"\" || !claims.EmailVerified" in source
    assert 'header.Alg != "RS256"' in source
    assert "rsa.VerifyPKCS1v15" in source
    assert "claims.ExpiresAt" in source
    assert "claims.IssuedAt" in source
    assert "claims.NotBefore" in source


def test_go_callback_is_get_only_and_sdk_mutations_are_post() -> None:
    go_http = _read(GO_HTTP)
    python_test = _read(ROOT / "tests/a1/test_python_google_account_connection.py")
    ts_source = _read(TS_CLIENT)

    callback = _function_body(
        go_http,
        "func (server *HTTPServer) handleOAuthCallback",
        "func writeOAuthError",
    )
    assert "request.Method != http.MethodGet" in callback
    assert "http.MethodPost" not in callback

    assert '"POST",\n            "/v1/projects/project_local/oauth/google/start"' in python_test
    assert (
        '"POST",\n            "/v1/projects/project_local/oauth/google/disconnect"'
        in python_test
    )
    assert '"POST",\n      `/v1/projects/${encodeURIComponent' in ts_source
    assert '"GET",\n      `/oauth/${provider}/callback?' in ts_source


def test_go_manifest_exposes_compatibility_methods_as_reviewed_p1_surface() -> None:
    source = _read(GO_SERVER)

    compatibility_routes = {
        'goScopedRoute("GET", "/v1/projects/{project_id}/oauth/google/start"',
        'goScopedRoute("POST", "/v1/projects/{project_id}/oauth/google/start"',
        'goScopedRoute("POST", "/v1/projects/{project_id}/oauth/google/disconnect"',
        'goScopedRoute("DELETE", "/v1/projects/{project_id}/oauth/google/disconnect"',
    }
    assert all(route in source for route in compatibility_routes)
    assert (
        'goPublicRoute("GET", "/oauth/google/callback", '
        '"oauth.google.callback", "oauth")'
    ) in source
    assert 'goPublicRoute("POST", "/oauth/google/callback"' not in source


def test_go_state_is_atomically_consumed_before_session_and_provider_io() -> None:
    source = _read(GO_SERVICE)
    callback = _function_body(
        source,
        "func (service *OAuthService) Callback",
        "func (service *OAuthService) Connection",
    )

    consume = callback.index("ConsumeOAuthTransaction")
    active_session = callback.index("resolveActiveSession")
    credentials = callback.index("resolveCredentials")
    exchange = callback.index("ExchangeCode")
    identity = callback.index("ResolveIdentity")
    token_store = callback.index("PutOAuthToken")

    assert consume < active_session < credentials < exchange < identity < token_store


def test_python_and_typescript_public_contracts_fail_closed_without_token_echo() -> None:
    python_source = _read(PYTHON_CONTRACT)
    ts_source = _read(TS_CLIENT)

    for forbidden_key in (
        "authorization_code",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "token_ref",
    ):
        assert forbidden_key in python_source
    assert "_assert_public_safe(payload)" in python_source
    assert "public account connection payload must not include" in python_source

    assert "async function parseSafeJson" in ts_source
    assert "deliberately omits provider response bodies" in ts_source
    assert '"Account connection HTTP request failed"' in ts_source
    assert "payload.error" in ts_source
    assert "payload.message" not in _function_body(
        ts_source,
        "async function parseSafeJson",
        "function normalizeTimeout",
    )


def test_python_and_typescript_google_claim_policy_matches_go() -> None:
    python_source = _read(PYTHON_CONTRACT)
    ts_source = _read(TS_CLIENT)

    assert 'GOOGLE_ACCOUNT_CONNECTION_SCOPES = ("openid", "email", "profile")' in python_source
    assert 'query.get("code_challenge_method") != ["S256"]' in python_source
    assert "not query.get(\"state\") or not query.get(\"nonce\")" in python_source
    assert "GOOGLE_OIDC_ISSUERS" in python_source
    assert "oidc_audience_mismatch" in python_source
    assert "oidc_nonce_mismatch" in python_source
    assert "oauth_email_unverified" in python_source

    assert 'google: ["openid", "email", "profile"]' in ts_source
    assert 'issuerAllowlist: ["https://accounts.google.com"]' in ts_source
    assert "audienceAllowlist: options.audienceAllowlist" in ts_source
    assert "expectedNonceSha256" in ts_source
    assert "emailVerified: options.emailVerified" in ts_source


def test_localhost_calibration_evidence_is_public_safe_and_unverified() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    serialized = json.dumps(evidence, sort_keys=True).lower()

    assert evidence["schema_version"] == "releasefoundry.google_oauth_localhost.v1"
    assert evidence["public_safe"] is True
    assert evidence["contains_secret_values"] is False
    assert evidence["calibration_status"] == "pending_human_browser_run"
    assert evidence["environment"] == "localhost"
    assert evidence["provider"] == "google"
    assert all(control["status"] != "verified" for control in evidence["controls"])

    forbidden = set(evidence["forbidden_evidence_fields"])
    assert {
        "authorization_code",
        "state",
        "nonce",
        "pkce_verifier",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "token_ref",
        "cookie",
        "request_headers",
        "provider_response_body",
        "authorization_url",
        "callback_url_with_query",
    }.issubset(forbidden)
    assert "ya29." not in serialized
    assert "ghp_" not in serialized
    assert "client_secret=" not in serialized


def test_localhost_calibration_schema_has_route_replay_oidc_and_redaction_controls() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    controls = {item["control_id"]: item for item in evidence["controls"]}

    assert set(controls) == {
        "start_route_and_pkce",
        "callback_success",
        "callback_replay",
        "nonce_rejection",
        "issuer_rejection",
        "audience_rejection",
        "unverified_email_rejection",
        "provider_timeout_or_outage",
        "public_response_secret_scan",
        "disconnect_and_reconnect",
    }
    assert controls["start_route_and_pkce"]["expected_method"] == "POST"
    assert controls["callback_success"]["expected_method"] == "GET"
    assert controls["disconnect_and_reconnect"]["expected_method"] == "POST"
    assert controls["callback_replay"]["expected_status_code"] == 400
    assert controls["public_response_secret_scan"]["expected_passed"] is True
