from __future__ import annotations

import json

import pytest

from services.api.oauth_providers import (
    OAuthClientConfig,
    OAuthProviderContractError,
    OAuthReplayLedger,
    build_authorization_envelope,
    derive_pkce_s256,
    hash_oauth_nonce,
    hash_oauth_state,
    oauth_provider_contract_manifest,
    verify_callback_identity,
    verify_callback_state,
)


def _config(provider: str, *, environment: str = "sandbox", enabled: bool = False):
    issuer = {
        "github": "https://github.com",
        "google": "https://accounts.google.com",
        "wechat": "https://open.weixin.qq.com",
        "alipay": "https://openauth.alipay.com",
    }[provider]
    audience = () if provider == "github" else (f"{provider}-application-id",)
    return OAuthClientConfig(
        provider=provider,
        client_id_ref=f"env:{provider.upper()}_{environment.upper()}_CLIENT_ID_REF",
        client_secret_ref=f"vault:oauth/{environment}/{provider}/client-secret",
        redirect_uri=f"https://auth.releasefoundry.invalid/{environment}/{provider}/callback",
        redirect_allowlist=(
            f"https://auth.releasefoundry.invalid/{environment}/{provider}/callback",
        ),
        scopes=("openid", "email") if provider == "google" else ("account_identity",),
        environment=environment,
        enabled=enabled,
        issuer_allowlist=(issuer,),
        audience_allowlist=audience,
    )


def test_registry_is_four_provider_disabled_account_ready_contract():
    manifest = oauth_provider_contract_manifest()

    assert set(manifest["providers"]) == {"github", "google", "wechat", "alipay"}
    assert manifest["environments"] == ["sandbox", "live"]
    assert manifest["required_controls"] == {
        "pkce_method": "S256",
        "state_hash_only": True,
        "nonce_hash_only": True,
        "redirect_exact_allowlist": True,
        "sandbox_live_separation": True,
        "issuer_validation": True,
        "audience_validation": True,
        "subject_hash_only": True,
        "account_binding_required": True,
        "callback_replay_protection": True,
        "token_refs_only": True,
        "raw_authorization_code_allowed": False,
        "network_io_performed": False,
        "disabled_by_default": True,
    }
    assert all(
        provider["supported_environments"] == ["sandbox", "live"]
        for provider in manifest["providers"].values()
    )


@pytest.mark.parametrize("provider", ["github", "google", "wechat", "alipay"])
def test_authorization_envelope_binds_pkce_state_nonce_redirect_and_environment(provider):
    verifier = "V" * 64
    state = f"state-{provider}-account-ready-20260710"
    nonce = f"nonce-{provider}-account-ready-20260710"
    config = _config(provider)
    kwargs = {}
    if provider == "google":
        kwargs = {
            "nonce_ref": "vault:oauth/sandbox/google/nonce/attempt-1",
            "nonce_sha256": hash_oauth_nonce(nonce)["nonce_sha256"],
        }

    envelope = build_authorization_envelope(
        config=config,
        state_ref=f"vault:oauth/sandbox/{provider}/state/attempt-1",
        state_sha256=hash_oauth_state(state)["state_sha256"],
        pkce_code_challenge=derive_pkce_s256(verifier)["code_challenge"],
        **kwargs,
    )
    serialized = json.dumps(envelope, sort_keys=True)

    assert envelope["provider"] == provider
    assert envelope["environment"] == "sandbox"
    assert envelope["enabled"] is False
    assert envelope["ready"] is False
    assert envelope["redirect_allowlist"] == [
        f"https://auth.releasefoundry.invalid/sandbox/{provider}/callback"
    ]
    assert envelope["parameters"]["code_challenge_method"] == "S256"
    assert envelope["executor_contract"]["network_io_performed"] is False
    assert state not in serialized
    assert nonce not in serialized
    assert verifier not in serialized


def test_google_identity_requires_nonce_issuer_audience_account_binding_and_enablement():
    nonce = "nonce-google-account-binding-20260710"
    disabled = verify_callback_identity(
        config=_config("google"),
        issuer="https://accounts.google.com",
        audience="google-application-id",
        subject="google-subject-123",
        account_binding_ref="provider-ref:google/account/123",
        expected_account_binding_ref="provider-ref:google/account/123",
        received_nonce=nonce,
        expected_nonce_sha256=hash_oauth_nonce(nonce)["nonce_sha256"],
        email_verified=True,
    )
    accepted = verify_callback_identity(
        config=_config("google", enabled=True),
        issuer="https://accounts.google.com",
        audience=["google-application-id"],
        subject="google-subject-123",
        account_binding_ref="provider-ref:google/account/123",
        expected_account_binding_ref="provider-ref:google/account/123",
        received_nonce=nonce,
        expected_nonce_sha256=hash_oauth_nonce(nonce)["nonce_sha256"],
        email_verified=True,
    )
    rejected = verify_callback_identity(
        config=_config("google", enabled=True),
        issuer="https://issuer.invalid",
        audience="wrong-audience",
        subject="google-subject-123",
        account_binding_ref="provider-ref:google/account/attacker",
        expected_account_binding_ref="provider-ref:google/account/123",
        received_nonce="wrong-nonce-account-binding",
        expected_nonce_sha256=hash_oauth_nonce(nonce)["nonce_sha256"],
        email_verified=True,
    )

    assert disabled["accepted"] is False
    assert disabled["failure_reasons"] == ["provider_disabled"]
    assert accepted["accepted"] is True
    assert accepted["raw_subject_present"] is False
    assert accepted["raw_nonce_present"] is False
    assert rejected["accepted"] is False
    assert rejected["failure_reasons"] == [
        "issuer_mismatch",
        "audience_mismatch",
        "nonce_mismatch",
        "account_binding_mismatch",
    ]
    assert rejected["issuer"] is None
    assert rejected["account_binding_ref"] is None


def test_callback_replay_is_scoped_by_provider_and_environment():
    ledger = OAuthReplayLedger()
    state = "state-callback-replay-account-ready"
    digest = hash_oauth_state(state)["state_sha256"]
    callback = dict(
        received_state=state,
        expected_state_sha256=digest,
        authorization_code_ref="vault:oauth/codes/attempt-1",
        replay_key="callback-event-account-ready-0001",
        replay_ledger=ledger,
    )

    first = verify_callback_state(provider="wechat", environment="sandbox", **callback)
    replay = verify_callback_state(provider="wechat", environment="sandbox", **callback)
    other_environment = verify_callback_state(
        provider="wechat", environment="live", **callback
    )

    assert first["accepted"] is True
    assert replay["accepted"] is False
    assert replay["failure_reasons"] == ["callback_replay"]
    assert replay["authorization_code_ref"] is None
    assert other_environment["accepted"] is True
    assert ledger.public_snapshot() == {
        "consumed_digest_count": 2,
        "raw_replay_keys_present": False,
    }


def test_redirect_and_environment_boundaries_fail_closed():
    with pytest.raises(OAuthProviderContractError, match="redirect_allowlist"):
        OAuthClientConfig(
            **{
                **_config("alipay").__dict__,
                "redirect_allowlist": (
                    "https://auth.releasefoundry.invalid/live/alipay/callback",
                ),
            }
        ).validate()
    with pytest.raises(OAuthProviderContractError, match="localhost"):
        OAuthClientConfig(
            **{
                **_config("github").__dict__,
                "redirect_uri": "http://localhost/oauth/callback",
                "redirect_allowlist": ("http://localhost/oauth/callback",),
            }
        ).validate()
    with pytest.raises(OAuthProviderContractError, match="sandbox or live"):
        OAuthClientConfig(
            **{**_config("wechat").__dict__, "environment": "production"}
        ).validate()
