from __future__ import annotations

import json
import subprocess
import sys

import pytest

from packages.sdk.ashr_clone.account_readiness import (
    ACCOUNT_READINESS_RECEIPT_VERSION,
    PROVIDERS,
    AccountReadinessError,
    AccountReadinessReceipt,
    build_receipt_template,
    validate_account_readiness_receipt,
)


def _receipt(provider: str = "github_oauth") -> dict[str, object]:
    return {
        "schema_version": ACCOUNT_READINESS_RECEIPT_VERSION,
        "provider": provider,
        "application_id_suffix": "a1B2",
        "application_fingerprint": "sha256:" + "a" * 64,
        "environment": "sandbox",
        "redirect_uris": ["https://app.example.com/oauth/callback"] if provider.endswith("oauth") else [],
        "status": "approved",
        "observed_at": "2026-07-10T16:00:00+08:00",
        "submitted_at": "2026-07-09T10:00:00+08:00",
        "receipt_id": f"operator:{provider}:20260710",
        "operator_note": "Dashboard shows approved; identifiers are suffix/fingerprint only.",
    }


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_all_human_operator_providers_have_safe_templates(provider: str):
    template = build_receipt_template(provider)
    normalized = AccountReadinessReceipt.from_mapping(template).to_public_dict()
    assert normalized["provider"] == provider
    assert normalized["contains_secrets"] is False
    assert normalized["contains_payment_card_data"] is False
    assert normalized["contains_kyc_material"] is False


def test_receipt_normalizes_public_fields_only():
    normalized = validate_account_readiness_receipt(_receipt())
    assert normalized["application_id_suffix"] == "a1B2"
    assert normalized["redirect_uris"] == ["https://app.example.com/oauth/callback"]
    assert "client_secret" not in json.dumps(normalized)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("client_secret", "do-not-store"),
        ("access_token", "do-not-store"),
        ("private_key", "-----BEGIN " + "PRIVATE KEY-----"),
        ("otp", "123456"),
        ("cvv", "123"),
        ("kyc_document", "business-license.jpg"),
        ("id_card_number", "110101199001011234"),
        ("business_license_file", "license.pdf"),
    ],
)
def test_receipt_rejects_secret_payment_and_kyc_fields(field: str, value: str):
    payload = _receipt()
    payload[field] = value
    with pytest.raises(AccountReadinessError, match="forbidden"):
        validate_account_readiness_receipt(payload)


def test_receipt_rejects_pan_even_inside_operator_note():
    payload = _receipt()
    payload["operator_note"] = "test card 4242 4242 4242 4242"
    with pytest.raises(AccountReadinessError, match="payment-card"):
        validate_account_readiness_receipt(payload)


def test_receipt_rejects_secret_value_without_secret_field_name():
    payload = _receipt()
    payload["operator_note"] = "access_token=raw-provider-token"
    with pytest.raises(AccountReadinessError, match="sensitive value"):
        validate_account_readiness_receipt(payload)


def test_receipt_rejects_kyc_material_mentioned_in_free_text():
    payload = _receipt()
    payload["operator_note"] = "\u8425\u4e1a\u6267\u7167\u626b\u63cf\u6587\u4ef6"
    with pytest.raises(AccountReadinessError, match="sensitive value"):
        validate_account_readiness_receipt(payload)


def test_production_redirect_requires_https():
    payload = _receipt("google_oauth")
    payload["environment"] = "production"
    payload["redirect_uris"] = ["http://localhost:8080/callback"]
    with pytest.raises(AccountReadinessError, match="HTTPS"):
        validate_account_readiness_receipt(payload)


def test_sandbox_localhost_redirect_is_allowed():
    payload = _receipt("google_oauth")
    payload["redirect_uris"] = ["http://localhost:8080/callback"]
    assert validate_account_readiness_receipt(payload)["redirect_uris"] == ["http://localhost:8080/callback"]


def test_login_provider_requires_redirect_uri():
    payload = _receipt("github_oauth")
    payload["redirect_uris"] = []
    with pytest.raises(AccountReadinessError, match="at least one redirect URI"):
        validate_account_readiness_receipt(payload)


def test_cli_template_and_validate(tmp_path):
    command = [sys.executable, "-m", "packages.sdk.ashr_clone.account_readiness"]
    template = subprocess.run(
        command + ["template", "--provider", "wechat_pay", "--environment", "production"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert template.returncode == 0
    payload = json.loads(template.stdout)
    payload["application_id_suffix"] = "mch9"
    payload["observed_at"] = "2026-07-10T16:00:00+08:00"
    receipt_file = tmp_path / "receipt.json"
    receipt_file.write_text(json.dumps(payload), encoding="utf-8")

    validated = subprocess.run(
        command + ["validate", "--file", str(receipt_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["provider"] == "wechat_pay"


def test_cli_accepts_utf8_bom_from_windows_powershell(tmp_path):
    receipt_file = tmp_path / "powershell-receipt.json"
    receipt_file.write_text(json.dumps(_receipt()), encoding="utf-8-sig")
    completed = subprocess.run(
        [sys.executable, "-m", "packages.sdk.ashr_clone.account_readiness", "validate", "--file", str(receipt_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["provider"] == "github_oauth"


def test_cli_rejection_does_not_echo_secret(tmp_path):
    receipt_file = tmp_path / "unsafe.json"
    receipt_file.write_text(json.dumps({**_receipt(), "client_secret": "super-private-value"}), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "packages.sdk.ashr_clone.account_readiness", "validate", "--file", str(receipt_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "super-private-value" not in completed.stderr
    assert json.loads(completed.stderr)["status"] == "rejected"
