import inspect
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ashr_clone.saas import SaaSIngestionClient  # noqa: E402

CONTRACT = json.loads((ROOT / "tests" / "a1" / "fixtures" / "billing_sdk_parity_contract.json").read_text(encoding="utf-8"))


def _result_keys(envelope: dict) -> set[str]:
    assert envelope["metadata"]["raw_auth_material_used"] is False
    assert envelope["metadata"]["ashr_api_used"] is False
    return set(envelope["result"].keys())


def _assert_public_safe(value: object) -> None:
    text = json.dumps(value, sort_keys=True)
    for fragment in CONTRACT["forbidden_public_fragments"]:
        assert fragment not in text


def _billing_flow(client: SaaSIngestionClient) -> dict[str, dict]:
    client.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_bill_sdk", project_id="project_bill_sdk")
    checkout = client.billing_checkout_plan(
        "tenant_bill_sdk",
        "project_bill_sdk",
        customer_ref="cus_test_123",
        price={"lookup_key": "team", "unit_amount_minor": 9900, "currency": "usd"},
        success_url="https://app.ashr-clone.invalid/billing/success",
        cancel_url="https://app.ashr-clone.invalid/billing/cancel",
        provider_config={"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"},
        metadata={"safe_note": "checkout"},
        idempotency_key="checkout_bill_sdk",
    )
    portal = client.billing_portal_plan(
        "tenant_bill_sdk",
        "project_bill_sdk",
        customer_ref="cus_test_123",
        return_url="https://app.ashr-clone.invalid/billing",
        provider_config={"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"},
        idempotency_key="portal_bill_sdk",
    )
    webhook = client.billing_webhook_ingest(
        "tenant_bill_sdk",
        "project_bill_sdk",
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_bill_sdk",
        payload_sha256="a" * 64,
        signature_header_present=True,
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
        customer_ref="cus_test_123",
        amount_minor=9900,
        currency="usd",
        invoice_ref="in_bill_sdk",
        metadata={"billing_period": "2026-07"},
    )
    ledger = client.billing_ledger("tenant_bill_sdk", "project_bill_sdk")
    return {"checkout_plan": checkout, "portal_plan": portal, "webhook_ingest": webhook, "ledger_readback": ledger}


def test_python_saas_billing_client_matches_shared_operation_contract():
    for contract in CONTRACT["operations"].values():
        assert hasattr(SaaSIngestionClient, contract["python_client_method"])
        signature = inspect.signature(getattr(SaaSIngestionClient, contract["python_client_method"]))
        assert "tenant_id" in signature.parameters
        assert "project_id" in signature.parameters
        assert "api_key_secret" in signature.parameters
        assert "bearer_api_key" in signature.parameters

    envelopes = _billing_flow(SaaSIngestionClient())
    for key, envelope in envelopes.items():
        contract = CONTRACT["operations"][key]
        assert envelope["operation"] == contract["operation"]
        assert set(contract["required_result_fields"]).issubset(_result_keys(envelope))
        _assert_public_safe(envelope)

    assert envelopes["checkout_plan"]["result"]["provider_request"]["operation"] == "checkout.sessions.create"
    assert envelopes["portal_plan"]["result"]["provider_request"]["operation"] == "billing_portal.sessions.create"
    assert envelopes["webhook_ingest"]["result"]["ingest_status"] == "accepted"
    assert envelopes["ledger_readback"]["result"]["ledger_event_count"] == 1
    assert envelopes["ledger_readback"]["result"]["totals_by_currency_minor"] == {"usd": 9900}


def test_python_saas_billing_http_routes_match_shared_contract():
    calls: list[tuple[str, str, dict, dict]] = []

    def transport(url: str, payload: dict, *, method: str, headers: dict | None = None) -> dict:
        calls.append((method, url, payload, headers or {}))
        return {"ok": True, "tenant_id": payload.get("tenant_id"), "project_id": payload.get("project_id")}

    client = SaaSIngestionClient.from_base_url("https://api.ashr-clone.invalid", http_transport=transport)
    client.billing_checkout_plan("tenant route", "project route", customer_ref="cus", price={"lookup_key": "team", "unit_amount_minor": 1000, "currency": "usd"}, success_url="https://app.ashr-clone.invalid/success", cancel_url="https://app.ashr-clone.invalid/cancel", auth_key_id="key_bill")
    client.billing_portal_plan("tenant route", "project route", customer_ref="cus", return_url="https://app.ashr-clone.invalid/billing", auth_key_id="key_bill")
    client.billing_webhook_ingest("tenant route", "project route", provider="stripe", mode="test", event_type="invoice.paid", event_id="evt", payload_sha256="b" * 64, signature_header_present=True, webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST", auth_key_id="key_bill")
    client.billing_ledger("tenant route", "project route", auth_key_id="key_bill")

    for call, contract in zip(calls, CONTRACT["operations"].values(), strict=True):
        method, url, payload, headers = call
        expected_path = contract["route"]["path"].replace("{project_id}", "project%20route")
        parsed = urlparse(url)
        assert method == contract["route"]["method"]
        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"https://api.ashr-clone.invalid{expected_path}"
        body_or_query = payload if method != "GET" else {key: values[0] for key, values in parse_qs(parsed.query).items()}
        assert body_or_query["tenant_id"] == "tenant route"
        assert body_or_query["auth_key_id"] == "key_bill"
        assert headers == {}
