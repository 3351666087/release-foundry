from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "docker" / "docker-compose.self-host.yml"
ENV_EXAMPLE = ROOT / "infra" / "docker" / "self-host.env.example"


def _compose() -> dict:
    if yaml is None:
        pytest.skip("PyYAML is not installed")
    loaded = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_china_payment_compose_has_isolated_worker_lanes_and_scheduler() -> None:
    services = _compose()["services"]
    webhook = services["china-payment-webhook-worker"]
    reconciliation = services["china-payment-reconciliation-worker"]
    acquirer = services["china-bank-acquirer-worker"]
    stripe = services["stripe-payment-worker"]
    scheduler = services["china-payment-reconciliation-scheduler"]

    assert webhook["profiles"] == ["china-payments"]
    assert reconciliation["profiles"] == ["china-payments"]
    assert acquirer["profiles"] == ["china-payments"]
    assert stripe["profiles"] == ["stripe-payments"]
    assert scheduler["profiles"] == ["china-payments"]

    webhook_env = webhook["environment"]
    reconciliation_env = reconciliation["environment"]
    acquirer_env = acquirer["environment"]
    stripe_env = stripe["environment"]
    assert webhook_env["RELEASEFOUNDRY_WORKER_QUEUE"] == "china_payment_webhook_ingestion"
    assert webhook_env["RELEASEFOUNDRY_WORKER_JOB_TYPE"] == "china_payment_webhook_ingestion"
    assert webhook_env["RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY"] == "china-wallets"
    assert webhook_env["RELEASEFOUNDRY_WORKER_DEAD_LETTER_QUEUE"] == "china_payment_webhook_dead_letter"
    assert webhook_env["RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS"] == "5"
    assert webhook_env["RELEASEFOUNDRY_WORKER_RETRY_DELAYS_SECONDS"] == "5,30,120,600"

    assert reconciliation_env["RELEASEFOUNDRY_WORKER_QUEUE"] == "china_payment_bill_reconciliation"
    assert reconciliation_env["RELEASEFOUNDRY_WORKER_JOB_TYPE"] == "china_payment_bill_reconciliation"
    assert reconciliation_env["RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY"] == "china-wallets"
    assert reconciliation_env["RELEASEFOUNDRY_WORKER_DEAD_LETTER_QUEUE"] == "china_payment_reconciliation_dead_letter"
    assert reconciliation_env["RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS"] == "4"
    assert reconciliation_env["RELEASEFOUNDRY_WORKER_RETRY_DELAYS_SECONDS"] == "300,1800,7200"

    assert acquirer_env["RELEASEFOUNDRY_WORKER_QUEUE"] == "china_bank_acquirer_events"
    assert acquirer_env["RELEASEFOUNDRY_WORKER_JOB_TYPE"] == "china_bank_acquirer_events"
    assert acquirer_env["RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY"] == "china-bank-acquirer"
    assert acquirer_env["RELEASEFOUNDRY_CHINA_ACQUIRER_MODE"] == "hosted-token-reference-only"
    assert acquirer_env["RELEASEFOUNDRY_WORKER_DEAD_LETTER_QUEUE"] == "china_bank_acquirer_dead_letter"
    assert acquirer_env["RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS"] == "5"
    assert acquirer_env["RELEASEFOUNDRY_WORKER_RETRY_DELAYS_SECONDS"] == "10,60,300,1800"

    assert stripe_env["RELEASEFOUNDRY_WORKER_QUEUE"] == "stripe_payment_events"
    assert stripe_env["RELEASEFOUNDRY_WORKER_JOB_TYPE"] == "stripe_payment_events"
    assert stripe_env["RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY"] == "stripe"
    assert stripe_env["RELEASEFOUNDRY_STRIPE_ENABLED"] == "false"
    assert stripe_env["RELEASEFOUNDRY_STRIPE_CHECKOUT_MODE"] == "hosted-checkout-reference-only"
    assert stripe_env["RELEASEFOUNDRY_WORKER_DEAD_LETTER_QUEUE"] == "stripe_payment_dead_letter"
    assert stripe_env["RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS"] == "5"
    assert stripe_env["RELEASEFOUNDRY_WORKER_RETRY_DELAYS_SECONDS"] == "10,60,300,1800"

    for service in (webhook, reconciliation, acquirer, stripe):
        env = service["environment"]
        assert env["RELEASEFOUNDRY_WORKER_EVIDENCE_WRITES"] == "object-store-hash-only"
        assert env["RELEASEFOUNDRY_PAYMENT_EVIDENCE_HASH_PREFIX"].endswith("/china-payments/sha256")
        assert service["healthcheck"]["test"][-1].endswith("china-payment-worker-healthcheck.sh")

    for service in (webhook, reconciliation, acquirer):
        assert service["environment"]["RELEASEFOUNDRY_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED"] == "false"

    scheduler_env = scheduler["environment"]
    assert scheduler_env["RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC"] == "02:15"
    assert scheduler_env["RELEASEFOUNDRY_PAYMENT_RECONCILIATION_RUN_ON_START"] == "false"
    assert scheduler_env["RELEASEFOUNDRY_PAYMENT_RECONCILIATION_JOB_TYPE"] == "china_payment_bill_reconciliation"
    assert scheduler["depends_on"]["postgres-migrate"]["condition"] == "service_completed_successfully"


def test_china_payment_env_contains_reference_names_without_secret_values() -> None:
    compose = _compose()
    services = compose["services"]
    env = services["china-payment-webhook-worker"]["environment"]
    expected_refs = {
        "RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_ID_REF": "env:RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_ID",
        "RELEASEFOUNDRY_WECHAT_PAY_API_V3_KEY_REF": "env:RELEASEFOUNDRY_WECHAT_PAY_API_V3_KEY",
        "RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_PRIVATE_KEY_REF": "env:RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_PRIVATE_KEY",
        "RELEASEFOUNDRY_WECHAT_PAY_PLATFORM_CERT_REF": "env:RELEASEFOUNDRY_WECHAT_PAY_PLATFORM_CERT",
        "RELEASEFOUNDRY_ALIPAY_APP_ID_REF": "env:RELEASEFOUNDRY_ALIPAY_APP_ID",
        "RELEASEFOUNDRY_ALIPAY_APP_PRIVATE_KEY_REF": "env:RELEASEFOUNDRY_ALIPAY_APP_PRIVATE_KEY",
        "RELEASEFOUNDRY_ALIPAY_PUBLIC_KEY_REF": "env:RELEASEFOUNDRY_ALIPAY_PUBLIC_KEY",
        "RELEASEFOUNDRY_CHINA_ACQUIRER_MERCHANT_ID_REF": "env:RELEASEFOUNDRY_CHINA_ACQUIRER_MERCHANT_ID",
        "RELEASEFOUNDRY_CHINA_ACQUIRER_HOSTED_ORIGIN_REF": "env:RELEASEFOUNDRY_CHINA_ACQUIRER_HOSTED_ORIGIN",
        "RELEASEFOUNDRY_CHINA_ACQUIRER_SESSION_TOKEN_REF": "env:RELEASEFOUNDRY_CHINA_ACQUIRER_SESSION_TOKEN",
        "RELEASEFOUNDRY_CHINA_ACQUIRER_SIGNING_KEY_REF": "env:RELEASEFOUNDRY_CHINA_ACQUIRER_SIGNING_KEY",
        "RELEASEFOUNDRY_STRIPE_ACCOUNT_ID_REF": "env:RELEASEFOUNDRY_STRIPE_ACCOUNT_ID",
        "RELEASEFOUNDRY_STRIPE_SECRET_KEY_REF": "env:RELEASEFOUNDRY_STRIPE_SECRET_KEY",
        "RELEASEFOUNDRY_STRIPE_WEBHOOK_SECRET_REF": "env:RELEASEFOUNDRY_STRIPE_WEBHOOK_SECRET",
    }
    for name, reference in expected_refs.items():
        assert env[name] == reference

    example = ENV_EXAMPLE.read_text(encoding="utf-8")
    for reference in expected_refs.values():
        assert reference in example
    for secret_name in (
        "RELEASEFOUNDRY_WECHAT_PAY_API_V3_KEY",
        "RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_PRIVATE_KEY",
        "RELEASEFOUNDRY_ALIPAY_APP_PRIVATE_KEY",
        "RELEASEFOUNDRY_CHINA_ACQUIRER_SESSION_TOKEN",
        "RELEASEFOUNDRY_CHINA_ACQUIRER_SIGNING_KEY",
        "RELEASEFOUNDRY_STRIPE_SECRET_KEY",
        "RELEASEFOUNDRY_STRIPE_WEBHOOK_SECRET",
    ):
        assert f"{secret_name}=" not in example

    assert services["api"]["profiles"][-2:] == ["china-payments", "stripe-payments"]


def test_runtime_configuration_forbids_card_and_challenge_data_fields() -> None:
    text = "\n".join(
        (
            COMPOSE.read_text(encoding="utf-8"),
            ENV_EXAMPLE.read_text(encoding="utf-8"),
        )
    ).lower()
    forbidden_fields = (
        "card_number",
        "cardholder",
        "pan_ref",
        "cvv",
        "cvc",
        "expiry_month",
        "expiry_year",
        "one_time_password",
        "sms_code",
    )
    for field in forbidden_fields:
        assert field not in text
