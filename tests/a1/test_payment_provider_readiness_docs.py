from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - jsonschema is optional in the light test env
    Draft202012Validator = None


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_PATH = REPO_ROOT / "docs" / "a1" / "evidence" / "payment_provider_readiness_public.json"
SCHEMA_PATH = REPO_ROOT / "docs" / "a1" / "schemas" / "payment_provider_readiness.schema.json"
DOC_PATH = REPO_ROOT / "docs" / "a1" / "payment_provider_readiness.md"
PUBLIC_FILES = (PACKET_PATH, SCHEMA_PATH, DOC_PATH)

SECRET_OR_PAYMENT_PATTERNS = [
    re.compile(r"\b(?:sk|rk|whsec)_(?:test|live)_[A-Za-z0-9]{8,}\b"),
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"\b(?:cvc|cvv)\s*[:=]", re.IGNORECASE),
    re.compile(r"provider_called\s*[:=]\s*true", re.IGNORECASE),
    re.compile(r"real_charge_possible\s*[:=]\s*true", re.IGNORECASE),
    re.compile(r"checkout_or_portal_called\s*[:=]\s*true", re.IGNORECASE),
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_payment_provider_readiness_packet_matches_schema():
    packet = _load_json(PACKET_PATH)
    schema = _load_json(SCHEMA_PATH)

    if Draft202012Validator is not None:
        Draft202012Validator(schema).validate(packet)

    assert packet["schema_version"] == "ashr.clone.a1.payment_provider_readiness.v1"
    assert packet["public_safe"] is True
    assert packet["payment_call_policy"] == {
        **packet["payment_call_policy"],
        "provider_called": False,
        "checkout_or_portal_called": False,
        "real_charge_possible": False,
        "ci_payment_calls_allowed": False,
    }


def test_payment_provider_readiness_covers_required_provider_modes_and_boundaries():
    packet = _load_json(PACKET_PATH)
    providers = {provider["provider"]: provider for provider in packet["providers"]}

    assert set(providers) == {"stripe", "wechat_pay", "alipay"}
    assert providers["stripe"]["payment_methods"] == ["card", "alipay", "wechat_pay"]
    assert providers["wechat_pay"]["payment_methods"] == ["wechat_pay"]
    assert providers["alipay"]["payment_methods"] == ["alipay"]

    for provider in providers.values():
        assert set(provider["modes"]) == {"test", "live"}
        assert provider["side_effects"]["provider_called"] is False
        assert provider["side_effects"]["real_charge_possible"] is False
        assert "human" in provider["live_readiness_boundary"].lower()
        assert provider["secret_refs"]["test"].split(":", 1)[0] in {"env", "vault", "kms", "provider-ref", "dashboard-ref"}
        assert provider["secret_refs"]["live"].split(":", 1)[0] in {"env", "vault", "kms", "provider-ref", "dashboard-ref"}


def test_payment_provider_webhook_envelopes_are_hash_only_and_referenced_private_paths():
    packet = _load_json(PACKET_PATH)
    envelopes = packet["webhook_hash_envelopes"]

    assert {envelope["provider"] for envelope in envelopes} == {"stripe", "wechat_pay", "alipay"}
    assert any(envelope["mode"] == "live" for envelope in envelopes)

    for envelope in envelopes:
        assert re.fullmatch(r"[a-f0-9]{64}", envelope["payload_sha256"])
        assert envelope["signature_header_present"] is True
        assert envelope["raw_payload_included"] is False
        assert envelope["secret_value_present"] is False
        assert envelope["webhook_secret_ref"].split(":", 1)[0] in {"env", "vault", "kms", "provider-ref", "dashboard-ref"}
        assert envelope["object_evidence_path"].startswith("docs/evidence/private_refs/payments/")


def test_payment_provider_object_evidence_paths_keep_private_refs_out_of_public_docs():
    packet = _load_json(PACKET_PATH)

    for item in packet["object_evidence_paths"]:
        path = item["path"]
        if item["allowed_in_public_repo"]:
            assert path.startswith("docs/a1/") or path.startswith("tests/a1/")
            assert item["classification"] == "public_contract"
        else:
            assert path.startswith("docs/evidence/private_refs/")
        assert item["contains_raw_provider_payload"] is False
        assert item["contains_raw_secret"] is False
        assert item["contains_card_data"] is False


def test_payment_provider_public_files_do_not_contain_raw_secrets_cards_or_live_call_markers():
    for path in PUBLIC_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_OR_PAYMENT_PATTERNS:
            assert pattern.search(text) is None, f"{path} contains forbidden public marker {pattern.pattern}"

    packet = _load_json(PACKET_PATH)
    assert packet["validation"]["forbidden_public_markers"]
    assert all("prefix" in marker or "field" in marker or "marker" in marker or "header" in marker or "key" in marker for marker in packet["validation"]["forbidden_public_markers"])


def test_real_card_testing_boundary_is_human_controlled_and_non_storing():
    packet = _load_json(PACKET_PATH)
    boundary = packet["human_real_card_testing"]

    assert boundary["allowed"] is True
    assert boundary["automation_allowed"] is False
    assert boundary["stored_card_data_allowed"] is False
    assert any("Automation must stop" in control for control in boundary["operator_controls"])
    assert any("refund" in evidence.lower() or "void" in evidence.lower() for evidence in boundary["evidence_allowed"])


def test_payment_provider_readiness_covers_commercial_auth_payment_safety_increment():
    packet = _load_json(PACKET_PATH)
    safety = packet["commercial_auth_payment_safety"]

    assert safety["local_only"] is True
    assert safety["provider_called"] is False
    assert safety["checkout_or_portal_called"] is False
    assert safety["real_charge_possible"] is False
    assert safety["secret_value_present"] is False
    assert safety["payment_provider_config"]["live_mode_ack_required"] is True
    assert safety["payment_provider_config"]["live_mode_enabled"] is False
    assert {provider["provider"] for provider in safety["oauth_providers"]} == {"github", "google"}
    assert all(provider["secret_value_present"] is False for provider in safety["oauth_providers"])
    assert {
        "oauth.provider.configure",
        "oauth.session.create",
        "oauth.session.revoke",
        "commercial.provider.configure",
        "payment.mode_boundary.record",
    } <= set(safety["api_key_linkage"]["rate_limit_operations"])
