from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from releasefoundry.provider_evidence import (  # noqa: E402
    ProviderReceiptStore,
    build_release_receipt,
    create_provider_receipt,
    verify_provider_receipt,
    verify_release_receipt,
)


def make_receipt(previous="", status="succeeded"):
    return create_provider_receipt(
        provider="xjtlu", model="gpt-5.6-sol", endpoint="https://models.example/v1",
        invoked_at="2026-07-13T01:02:03Z", completed_at="2026-07-13T01:02:04Z",
        request_binding={"prompt_sha256": "a" * 64}, response_binding={"finish": "stop", "tokens": 7},
        evidence=b"private normalized record", capabilities=["text", "stream", "tools", "usage"],
        status=status, git_sha="5dd6a898a6771eaf67bf39246f256b579b4d2211",
        release_candidate="round62", request_id="provider-request-id",
        previous_receipt_sha256=previous,
        safe_response_shape={"finish_reason": "stop", "usage_present": True},
    )


def test_receipt_binds_endpoint_request_response_evidence_time_and_release():
    receipt = make_receipt()
    assert verify_provider_receipt(receipt.to_dict()) == receipt
    assert len(receipt.endpoint_sha256) == len(receipt.response_binding_sha256) == 64
    assert receipt.invoked_at.endswith("Z")
    assert receipt.git_sha.startswith("5dd6a898")
    public = json.dumps(receipt.to_dict())
    assert "private normalized record" not in public
    assert "provider-request-id" not in public


def test_failed_call_cannot_claim_callable_capabilities():
    receipt = make_receipt(status="failed")
    assert receipt.capabilities == ()
    tampered = receipt.to_dict() | {"capabilities": ["image"]}
    with pytest.raises(ValueError):
        verify_provider_receipt(tampered)


def test_atomic_store_verifies_chain_and_rejects_tampering(tmp_path):
    store = ProviderReceiptStore(tmp_path / "receipts.json")
    first = make_receipt()
    store.append(first)
    second = make_receipt(first.receipt_sha256)
    store.append(second)
    assert [item.receipt_sha256 for item in store.load()] == [first.receipt_sha256, second.receipt_sha256]
    value = json.loads(store.path.read_text())
    value[0]["model"] = "tampered"
    store.path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        store.load()


def test_store_rejects_forked_or_out_of_order_receipt(tmp_path):
    store = ProviderReceiptStore(tmp_path / "receipts.json")
    store.append(make_receipt())
    with pytest.raises(ValueError, match="chain"):
        store.append(make_receipt())


def test_release_receipt_binds_provider_and_operational_proofs():
    receipt = make_receipt()
    release = build_release_receipt(
        git_sha=receipt.git_sha, release_candidate="round62",
        provider_receipts=[receipt.to_dict()],
        evidence_files={
            "postgres_rls": b"rls proof",
            "claim_lease_fencing": b"fencing proof",
            "restart_persistence": b"restart proof",
        }, generated_at="2026-07-13T02:00:00+00:00",
    )
    assert verify_release_receipt(release)
    assert len(release["evidence_refs"]) == 3
    tampered = release | {"git_sha": "0" * 40}
    with pytest.raises(ValueError):
        verify_release_receipt(tampered)


@pytest.mark.parametrize("field", ["endpoint_sha256", "response_binding_sha256", "receipt_sha256"])
def test_receipt_rejects_noncanonical_digests(field):
    value = make_receipt().to_dict()
    value[field] = "A" * 64
    with pytest.raises(ValueError):
        verify_provider_receipt(value)
CROSS_LANGUAGE_RECEIPT_ID = "provider_receipt_508b1ae2db48cf590d5b"
CROSS_LANGUAGE_RECEIPT_SHA256 = "19a3750b1f6bc0ff92e19fda1d0076c06d5cb64ca3112f9cbb813fdc518eb894"


def test_cross_language_unicode_html_timezone_vector():
    receipt = create_provider_receipt(
        provider="vector", model="模型<&>", endpoint="https://models.example/v1/",
        invoked_at="2026-07-13T09:02:03+08:00", completed_at="2026-07-13T01:02:04.999Z",
        request_binding={"文本": "你好<&>", "nested": {"z": 2, "a": 1}},
        response_binding={"finish": "stop", "tokens": 7}, evidence="固定证据".encode(),
        capabilities=["usage", "text", "text"], status="succeeded",
        git_sha="5dd6a898a6771eaf67bf39246f256b579b4d2211", release_candidate="round62-vector",
        request_id="request-中文", safe_response_shape={"usage_present": True, "标签": "值<&>"},
    )
    assert receipt.receipt_id == CROSS_LANGUAGE_RECEIPT_ID
    assert receipt.receipt_sha256 == CROSS_LANGUAGE_RECEIPT_SHA256


def test_public_round62_receipt_chain_and_release_fixture_verify():
    fixtures = Path(__file__).parent / "fixtures"
    receipts = json.loads((fixtures / "round62_provider_execution_receipts.json").read_text())
    previous = ""
    for value in receipts:
        verify_provider_receipt(value, expected_previous=previous)
        previous = value["receipt_sha256"]
    release = json.loads((fixtures / "round62_a1_release_receipt.json").read_text())
    assert verify_release_receipt(release)
    assert release["provider_receipt_sha256s"] == sorted(item["receipt_sha256"] for item in receipts)


def test_public_round62_receipts_cover_all_first_class_modalities():
    receipts = json.loads((Path(__file__).parent / "fixtures" / "round62_provider_execution_receipts.json").read_text())
    succeeded = {capability for receipt in receipts if receipt["status"] == "succeeded" for capability in receipt["capabilities"]}
    assert {"text", "image", "audio", "file", "video"} <= succeeded

def test_public_round62_fixtures_are_redacted_and_endpoint_free():
    fixtures = Path(__file__).parent / "fixtures"
    documents = [json.loads((fixtures / name).read_text(encoding="utf-8")) for name in (
        "round62_provider_execution_receipts.json", "round62_a1_release_receipt.json",
    )]
    public = json.dumps(documents, ensure_ascii=False).lower()
    assert not any(token in public for token in ("https://", "api_key", "authorization", "bearer ", "sk-"))

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()), set())
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value), set())
        return set()

    assert not (keys(documents) & {"endpoint", "prompt", "request_id", "raw_request", "raw_response"})
