import json
import unittest
from unittest.mock import patch

import jsonschema

from services.judge.multimodal_provider import (
    OfflineDeterministicMultimodalAdapter,
    OpenAICompatibleMultimodalAdapter,
    ParseRetryPolicy,
    ProviderRateLimited,
    TransportRetryPolicy,
    build_provider_conformance_receipt,
    default_multimodal_provider_registry,
    parse_ollama_response,
    parse_openai_compatible_response,
)
from services.judge.provider_runtime import EnvironmentCredentialResolver
from scripts.a2_ollama_multimodal_matrix import ROOT


class MultimodalProviderTests(unittest.TestCase):
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

            def read(self):
                return b'{"model":"qwen-vl-plus","choices":[{"message":{"content":"{}"}}]}'

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
