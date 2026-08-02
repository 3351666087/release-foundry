from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "services" / "runner" / "china-payment-worker-entrypoint.sh"
HEALTHCHECK = ROOT / "services" / "runner" / "china-payment-worker-healthcheck.sh"
SCHEDULER = ROOT / "infra" / "docker" / "china-payment-reconciliation-scheduler.sh"


def _shell_command(script: Path, argument: Path) -> list[str]:
    shell = shutil.which("sh")
    if shell:
        return [shell, str(script), str(argument)]
    wsl = shutil.which("wsl")
    if wsl:
        def wsl_path(path: Path) -> str:
            resolved = path.resolve()
            drive = resolved.drive.rstrip(":").lower()
            suffix = resolved.as_posix().split(":", 1)[1]
            return f"/mnt/{drive}{suffix}"

        distros = subprocess.run(
            [wsl, "--list", "--quiet"],
            text=True,
            encoding="utf-16-le",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        ).stdout.splitlines()
        script_path = wsl_path(script)
        for distro in (item.strip() for item in distros):
            if not distro or distro == "docker-desktop":
                continue
            probe = subprocess.run(
                [wsl, "-d", distro, "--exec", "/bin/sh", "-c", f"test -f '{script_path}'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if probe.returncode == 0:
                return [wsl, "-d", distro, "--exec", "/bin/sh", script_path, wsl_path(argument)]
    pytest.skip("a POSIX shell or WSL is required for the entrypoint runtime test")


def test_worker_entrypoint_fails_closed_and_never_calls_providers() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    health = HEALTHCHECK.read_text(encoding="utf-8")

    assert "china-wallets)" in text
    assert "china-bank-acquirer)" in text
    assert "stripe)" in text
    assert text.count('test "${RELEASEFOUNDRY_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED:-false}" = "false"') == 2
    assert 'test "${RELEASEFOUNDRY_CHINA_ACQUIRER_MODE:-}" = "hosted-token-reference-only"' in text
    assert 'test "${RELEASEFOUNDRY_STRIPE_CHECKOUT_MODE:-}" = "hosted-checkout-reference-only"' in text
    assert 'if test "${RELEASEFOUNDRY_STRIPE_ENABLED:-false}" != "true"; then' in text
    assert 'test "${RELEASEFOUNDRY_STRIPE_ENABLED:-false}" = "false"' in text
    assert "runtime_status=disabled" in text
    assert text.index('if test "$runtime_status" = "disabled"; then') < text.index('"$worker_binary" >')
    assert 'test "$RELEASEFOUNDRY_WORKER_QUEUE" = "$RELEASEFOUNDRY_WORKER_JOB_TYPE"' in text
    assert "object-store-hash-only" in text
    assert "evidence hash path ending in /sha256" in text
    assert '"provider_network_enabled":false' in text
    assert "curl " not in text
    assert "wget " not in text
    assert "api.mch.weixin.qq.com" not in text
    assert "openapi.alipay.com" not in text
    assert "api.stripe.com" not in text

    assert "find \"$RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH\" -mmin -2" in health
    assert "'\"status\":\"(ready|disabled)\"'" in health
    assert '\\"provider_family\\"' in health
    assert '"provider_network_enabled":false' in health

    combined = f"{text}\n{health}".lower()
    for forbidden in (
        "card_number",
        "cardholder",
        "pan_ref",
        "cvv",
        "cvc",
        "expiry_month",
        "expiry_year",
        "one_time_password",
        "sms_code",
    ):
        assert forbidden not in combined


def test_scheduler_is_daily_idempotent_and_hashes_only_bill_identity() -> None:
    text = SCHEDULER.read_text(encoding="utf-8")

    assert "date -u -d 'yesterday' +%F" in text
    assert "china-payment-reconciliation-$bill_date" in text
    assert "sha256sum" in text
    assert "ON CONFLICT (tenant_id, project_id, job_id) DO NOTHING" in text
    assert "'china-payment-daily-scheduler'" in text
    assert "RELEASEFOUNDRY_PAYMENT_RECONCILIATION_RUN_ON_START" in text
    assert "sleep 30" in text
    assert "curl " not in text
    assert "wget " not in text


def test_worker_entrypoint_rejects_non_reference_provider_configuration(tmp_path: Path) -> None:
    fake_worker = tmp_path / "worker"
    fake_worker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_worker.chmod(0o755)
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "RELEASEFOUNDRY_GO_BACKEND": "postgres",
            "RELEASEFOUNDRY_POSTGRES_DSN": "postgresql://local.invalid/releasefoundry",
            "RELEASEFOUNDRY_WORKER_QUEUE": "china_payment_webhook_ingestion",
            "RELEASEFOUNDRY_WORKER_JOB_TYPE": "china_payment_webhook_ingestion",
            "RELEASEFOUNDRY_WORKER_LANE": "payment-webhook",
            "RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY": "china-wallets",
            "RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS": "5",
            "RELEASEFOUNDRY_WORKER_RETRY_DELAYS_SECONDS": "5,30,120,600",
            "RELEASEFOUNDRY_WORKER_DEAD_LETTER_QUEUE": "china_payment_webhook_dead_letter",
            "RELEASEFOUNDRY_WORKER_EVIDENCE_WRITES": "object-store-hash-only",
            "RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH": str(runtime / "heartbeat"),
            "RELEASEFOUNDRY_WORKER_READINESS_PATH": str(runtime / "ready.json"),
            "RELEASEFOUNDRY_WORKER_SUMMARY_OUTPUT": str(runtime / "summary.json"),
            "RELEASEFOUNDRY_PAYMENT_EVIDENCE_HASH_PREFIX": "evidence/a1/self-host/china-payments/sha256",
            "RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_ID_REF": "literal-merchant-id",
            "RELEASEFOUNDRY_WECHAT_PAY_API_V3_KEY_REF": "env:RELEASEFOUNDRY_WECHAT_PAY_API_V3_KEY",
            "RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_PRIVATE_KEY_REF": "env:RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_PRIVATE_KEY",
            "RELEASEFOUNDRY_WECHAT_PAY_PLATFORM_CERT_REF": "env:RELEASEFOUNDRY_WECHAT_PAY_PLATFORM_CERT",
            "RELEASEFOUNDRY_ALIPAY_APP_ID_REF": "env:RELEASEFOUNDRY_ALIPAY_APP_ID",
            "RELEASEFOUNDRY_ALIPAY_APP_PRIVATE_KEY_REF": "env:RELEASEFOUNDRY_ALIPAY_APP_PRIVATE_KEY",
            "RELEASEFOUNDRY_ALIPAY_PUBLIC_KEY_REF": "env:RELEASEFOUNDRY_ALIPAY_PUBLIC_KEY",
            "RELEASEFOUNDRY_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED": "false",
            "RELEASEFOUNDRY_STRIPE_ENABLED": "false",
        }
    )
    env["WSLENV"] = ":".join(sorted(name for name in env if name.startswith("RELEASEFOUNDRY_")))
    result = subprocess.run(
        _shell_command(ENTRYPOINT, fake_worker),
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )

    assert result.returncode == 64
    assert "RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_ID_REF must be an env: reference" in result.stdout


def test_acquirer_contract_is_hosted_token_reference_only() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    branch = text.split("china-bank-acquirer)", 1)[1].split(";;", 1)[0]

    assert "hosted-token-reference-only" in branch
    assert "RELEASEFOUNDRY_CHINA_ACQUIRER_MERCHANT_ID_REF" in branch
    assert "RELEASEFOUNDRY_CHINA_ACQUIRER_HOSTED_ORIGIN_REF" in branch
    assert "RELEASEFOUNDRY_CHINA_ACQUIRER_SESSION_TOKEN_REF" in branch
    assert "RELEASEFOUNDRY_CHINA_ACQUIRER_SIGNING_KEY_REF" in branch
    assert branch.count("RELEASEFOUNDRY_CHINA_ACQUIRER_") == 5

    for forbidden in (
        "CARD_NUMBER",
        "CARDHOLDER",
        "PAN_REF",
        "CVV",
        "CVC",
        "EXPIRY_MONTH",
        "EXPIRY_YEAR",
        "OTP",
        "ONE_TIME_PASSWORD",
        "SMS_CODE",
    ):
        assert forbidden not in branch
