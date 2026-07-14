import json
import gzip
import io
import socket
import unittest
from unittest.mock import patch
from urllib import error

import jsonschema

from services.judge.multimodal_provider import (
    OfflineDeterministicMultimodalAdapter,
    OpenAICompatibleMultimodalAdapter,
    ParseRetryPolicy,
    ClassifiedProviderTransportError,
    ProviderResponseDurationReceipt,
    ProviderRequestCountReceipt,
    ProviderUsageCostReceipt,
    ProviderPricingPolicy,
    ProviderCancellationHandleReceipt,
    ProviderRateLimited,
    TransportRetryPolicy,
    build_provider_conformance_receipt,
    default_multimodal_provider_registry,
    parse_ollama_response,
    parse_openai_compatible_response,
    read_bounded_json_response,
    request_provider_cancellation,
)
from services.judge.provider_runtime import EnvironmentCredentialResolver
from scripts.a2_ollama_multimodal_matrix import ROOT


class MultimodalProviderTests(unittest.TestCase):
    def test_round47_provider_cancellation_handle_contract_is_fail_closed(self):
        class Handle:
            def __init__(self, result=True):
                self.result = result
                self.calls = 0

            def cancel(self):
                self.calls += 1
                return self.result

        schema = json.loads(
            (
                ROOT
                / "docs/a2/schemas/provider_cancellation_handle_receipt.schema.json"
            ).read_text(encoding="utf-8")
        )
        supported = Handle()
        receipt = request_provider_cancellation(supported)
        self.assertEqual(supported.calls, 1)
        self.assertTrue(receipt["acknowledged"])
        self.assertFalse(receipt["remote_request_termination_proven"])
        jsonschema.Draft202012Validator(schema).validate(receipt)
        unsupported = request_provider_cancellation(None)
        self.assertEqual(unsupported["enforcement"], "unsupported")
        self.assertFalse(unsupported["acknowledged"])
        with self.assertRaisesRegex(ValueError, "requires a supported request"):
            ProviderCancellationHandleReceipt(
                requested=True,
                supported=False,
                acknowledged=True,
                enforcement="unsupported",
            )

    def test_registry_discovers_generic_capabilities_without_secret(self):
        registry = default_multimodal_provider_registry()
        capability = registry.discover("dashscope")
        self.assertEqual(capability["protocol"], "openai_compatible")
        self.assertEqual(capability["image_mime_types"], ["image/jpeg", "image/png"])
        self.assertTrue(capability["structured_output"])
        self.assertEqual(capability["retry_classes"], ["parse", "transport"])
        self.assertNotIn("credential", str(capability))

    def test_generic_adapter_preserves_jpeg_mime_and_structured_output(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, maximum_bytes=-1):
                value = b'{"model":"qwen-vl-plus","choices":[{"message":{"content":"{}"}}]}'
                return value if maximum_bytes < 0 else value[:maximum_bytes]

        registry = default_multimodal_provider_registry()
        provider = registry.require("dashscope")
        adapter = OpenAICompatibleMultimodalAdapter(
            EnvironmentCredentialResolver({provider.credential_ref: "unit-key"})
        )
        payload = {
            "model": "qwen-vl-plus",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,AA=="},
                        }
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
        }
        with patch(
            "services.judge.multimodal_provider.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            result = adapter.invoke(provider, payload, 10)
        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(
            sent["messages"][0]["content"][0]["image_url"]["url"],
            "data:image/jpeg;base64,AA==",
        )
        self.assertEqual(sent["response_format"], {"type": "json_object"})
        self.assertEqual(result["model"], "qwen-vl-plus")

    def test_round48_bounded_json_reader_rejects_oversized_truncated_and_amplified(self):
        class Response:
            def __init__(self, body, headers=None):
                self.body = body
                self.headers = headers or {}

            def getheader(self, name):
                return self.headers.get(name)

            def read(self, maximum_bytes=-1):
                return self.body if maximum_bytes < 0 else self.body[:maximum_bytes]

        oversized = Response(b'{"value":"' + b"x" * 100 + b'"}')
        with self.assertRaises(ClassifiedProviderTransportError) as observed:
            read_bounded_json_response(oversized, 32)
        self.assertEqual(observed.exception.error_class, "response_body_too_large")

        truncated = Response(b'{"value":', {"Content-Length": "100"})
        with self.assertRaises(ClassifiedProviderTransportError) as observed:
            read_bounded_json_response(truncated, 128)
        self.assertEqual(observed.exception.error_class, "response_body_truncated")

        compressed_body = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed_body, mode="wb") as compressed:
            compressed.write(b'{"value":"' + b"x" * 200 + b'"}')
        amplified = Response(
            compressed_body.getvalue(),
            {"Content-Encoding": "gzip"},
        )
        with self.assertRaises(ClassifiedProviderTransportError) as observed:
            read_bounded_json_response(amplified, 64)
        self.assertEqual(
            observed.exception.error_class,
            "response_decompression_limit_exceeded",
        )

        malformed = Response(b'{"value":')
        with self.assertRaises(ClassifiedProviderTransportError) as observed:
            read_bounded_json_response(malformed, 64)
        self.assertEqual(observed.exception.error_class, "response_json_malformed")

    def test_openai_compatible_adapter_emits_provider_neutral_transport_receipts(self):
        registry = default_multimodal_provider_registry()
        provider = registry.require("dashscope")
        adapter = OpenAICompatibleMultimodalAdapter(
            EnvironmentCredentialResolver({provider.credential_ref: "unit-key"})
        )
        cases = [
            (error.HTTPError(provider.endpoint, 401, "secret", {}, None), "authentication_error", "4xx"),
            (error.HTTPError(provider.endpoint, 429, "secret", {}, None), "rate_limited", "4xx"),
            (error.HTTPError(provider.endpoint, 503, "secret", {}, None), "http_server_error", "5xx"),
            (error.URLError(socket.timeout()), "timeout", ""),
            (error.URLError(ConnectionResetError()), "connection_reset", ""),
            (error.URLError(ConnectionRefusedError()), "connection_refused", ""),
        ]
        for failure, expected_class, expected_status in cases:
            with self.subTest(expected_class=expected_class), patch(
                "services.judge.multimodal_provider.request.urlopen",
                side_effect=failure,
            ):
                with self.assertRaises(ClassifiedProviderTransportError) as observed:
                    adapter.invoke(provider, {}, 1)
            receipt = observed.exception.receipt.public_receipt()
            self.assertEqual(observed.exception.error_class, expected_class)
            self.assertEqual(receipt["http_status_class"], expected_status)
            self.assertFalse(receipt["response_body_retained"])
            self.assertNotIn("secret", str(receipt))

    def test_shared_response_duration_receipt_prefers_provider_native_duration(self):
        native = ProviderResponseDurationReceipt(
            wall_seconds=1.25,
            provider_seconds=0.75,
            provider_source="ollama.total_duration",
        ).public_receipt()
        wall = ProviderResponseDurationReceipt(wall_seconds=1.25).public_receipt()
        self.assertEqual(native["effective_source"], "provider_native")
        self.assertEqual(native["effective_seconds"], 0.75)
        self.assertEqual(wall["effective_source"], "wall_clock")
        self.assertEqual(wall["effective_seconds"], 1.25)
        with self.assertRaisesRegex(ValueError, "present together"):
            ProviderResponseDurationReceipt(
                wall_seconds=1,
                provider_source="ollama.total_duration",
            )

    def test_round46_request_and_usage_cost_receipts_are_bounded(self):
        count = ProviderRequestCountReceipt(
            attempted=3, completed=2, failed=1, maximum_allowed=4
        ).public_receipt()
        self.assertEqual(count["attempted"], 3)
        self.assertFalse(count["budget_exhausted"])
        usage = ProviderUsageCostReceipt(
            prompt_tokens=1000,
            completion_tokens=500,
            input_usd_per_million_tokens=2,
            output_usd_per_million_tokens=4,
            maximum_estimated_cost_usd=0.01,
        ).public_receipt()
        self.assertEqual(usage["total_tokens"], 1500)
        self.assertEqual(usage["usage_accounting_state"], "complete")
        self.assertEqual(usage["pricing_state"], "configured")
        self.assertTrue(usage["within_cost_budget"])
        self.assertFalse(usage["raw_payload_included"])
        unknown = ProviderUsageCostReceipt(
            prompt_tokens=1000,
            completion_tokens=500,
            input_usd_per_million_tokens=None,
            output_usd_per_million_tokens=None,
            maximum_estimated_cost_usd=1,
        ).public_receipt()
        self.assertEqual(unknown["pricing_state"], "unavailable")
        self.assertIsNone(unknown["estimated_cost_usd"])
        self.assertFalse(unknown["within_cost_budget"])
        missing_usage = ProviderUsageCostReceipt(
            prompt_tokens=0,
            completion_tokens=0,
            input_usd_per_million_tokens=2,
            output_usd_per_million_tokens=4,
            maximum_estimated_cost_usd=1,
            usage_complete=False,
        ).public_receipt()
        self.assertEqual(
            missing_usage["usage_accounting_state"], "missing_or_invalid"
        )
        self.assertIsNone(missing_usage["estimated_cost_usd"])
        self.assertFalse(missing_usage["within_cost_budget"])
        policy = ProviderPricingPolicy(
            provider_id="unit",
            model_id="unit-model",
            input_usd_per_million_tokens=2,
            output_usd_per_million_tokens=4,
            effective_at="2026-07-14T00:00:00Z",
            retrieved_at="2026-07-14T01:00:00Z",
            source_class="unit_fixture",
            source_uri_hash="sha256:" + "a" * 64,
        ).public_policy()
        jsonschema.Draft202012Validator(
            json.loads(
                (
                    ROOT / "docs/a2/schemas/provider_pricing_policy.schema.json"
                ).read_text(encoding="utf-8")
            )
        ).validate(policy)
        bound = ProviderUsageCostReceipt(
            prompt_tokens=1000,
            completion_tokens=500,
            input_usd_per_million_tokens=2,
            output_usd_per_million_tokens=4,
            maximum_estimated_cost_usd=1,
            pricing_policy=policy,
        ).public_receipt()
        self.assertEqual(bound["pricing_policy_hash"], policy["content_hash"])
        self.assertEqual(bound["pricing_source_hash"], policy["source_uri_hash"])
        with self.assertRaisesRegex(ValueError, "must equal"):
            ProviderRequestCountReceipt(
                attempted=3, completed=1, failed=1, maximum_allowed=4
            )

    def test_offline_adapter_has_explicit_valid_invalid_timeout_rate_limit(self):
        adapter = OfflineDeterministicMultimodalAdapter(
            ["valid", "invalid", "timeout", "rate_limit"]
        )
        provider = default_multimodal_provider_registry().require(
            "offline-deterministic"
        )
        self.assertIn('"risk":false', str(adapter.invoke(provider, {}, 1)))
        self.assertIn("not-json", str(adapter.invoke(provider, {}, 1)))
        with self.assertRaises(TimeoutError):
            adapter.invoke(provider, {}, 1)
        with self.assertRaises(ProviderRateLimited):
            adapter.invoke(provider, {}, 1)

    def test_retry_classes_do_not_mix_parse_and_transport(self):
        parse = ParseRetryPolicy(max_retries=1)
        transport = TransportRetryPolicy(max_retries=1)
        self.assertTrue(parse.should_retry("nonempty_invalid_json", 0))
        self.assertFalse(parse.should_retry("timeout", 0))
        self.assertTrue(transport.should_retry("timeout", 0))
        self.assertFalse(transport.should_retry("nonempty_invalid_json", 0))
        self.assertFalse(transport.should_retry("timeout", 1))

    def test_shared_conformance_receipt_validates_for_cloud_and_local(self):
        schema = json.loads(
            (
                ROOT / "docs/a2/schemas/provider_conformance_receipt.schema.json"
            ).read_text(encoding="utf-8")
        )
        registry = default_multimodal_provider_registry()
        for provider_id in ("dashscope", "offline-deterministic", "ollama-local"):
            provider = registry.require(provider_id)
            receipt = build_provider_conformance_receipt(
                provider=provider,
                adapter_class="unit-adapter",
                checks={
                    "mime_contract": True,
                    "structured_output_contract": True,
                    "failure_fail_closed": True,
                },
                observed_states=["valid", "timeout"],
                generated_at="2026-07-14T00:00:00Z",
                source_evidence_hashes=["sha256:" + "1" * 64],
            )
            jsonschema.Draft202012Validator(schema).validate(receipt)
            self.assertFalse(receipt["release_authority"])
            self.assertFalse(receipt["secret_included"])

    def test_shared_parser_separates_content_and_thinking(self):
        local = parse_ollama_response(
            {"response": "", "thinking": "private reasoning", "done": True}
        )
        cloud = parse_openai_compatible_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"risk_present":false}',
                            "reasoning_content": "private reasoning",
                        }
                    }
                ]
            }
        )
        self.assertFalse(local.public_receipt()["content_present"])
        self.assertTrue(local.public_receipt()["thinking_present"])
        self.assertNotIn("private reasoning", str(local.public_receipt()))
        self.assertTrue(cloud.public_receipt()["content_present"])
        self.assertTrue(cloud.public_receipt()["thinking_present"])

    def test_conformance_receipt_requires_valid_predecessor_sequence(self):
        provider = default_multimodal_provider_registry().require("ollama-local")
        first = build_provider_conformance_receipt(
            provider=provider,
            adapter_class="unit",
            checks={"fail_closed": True},
            observed_states=["valid"],
            generated_at="2026-07-14T00:00:00Z",
        )
        second = build_provider_conformance_receipt(
            provider=provider,
            adapter_class="unit",
            checks={"fail_closed": True},
            observed_states=["valid"],
            generated_at="2026-07-14T00:01:00Z",
            predecessor_receipt_id=first["receipt_id"],
            sequence=2,
        )
        self.assertEqual(second["predecessor_receipt_id"], first["receipt_id"])
        with self.assertRaisesRegex(ValueError, "requires a predecessor"):
            build_provider_conformance_receipt(
                provider=provider,
                adapter_class="unit",
                checks={"fail_closed": True},
                observed_states=["valid"],
                generated_at="2026-07-14T00:02:00Z",
                sequence=2,
            )


if __name__ == "__main__":
    unittest.main()
