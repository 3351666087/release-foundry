import unittest

from services.judge.provider_gateway import (
    OllamaAdapter,
    ProviderDefinition,
    ProviderGateway,
    StrictFakeAdapter,
    default_provider_catalog,
)
from services.judge.result_persistence import stable_hash


def snapshot(*, tenant="tenant-a", completeness="complete"):
    core = {"tenant_id": tenant, "completeness": completeness, "evidence": "unit"}
    return {**core, "snapshot_id": stable_hash(core), "snapshot_hash": stable_hash(core)}


class TimeoutAdapter:
    def invoke(self, model, payload, timeout_seconds):
        raise TimeoutError("deadline exceeded")


class A2ProviderGatewayTests(unittest.TestCase):
    def setUp(self):
        self.fake = StrictFakeAdapter({"output_text": '{"passed":true}', "usage": {"input_tokens": 4, "output_tokens": 2}})
        self.provider = ProviderDefinition(
            "unit-provider",
            "strict_fake",
            "memory://unit",
            "secret://unit/key",
            frozenset({"text", "image"}),
            frozenset({"tenant-a"}),
        )
        self.audits = []
        self.gateway = ProviderGateway(
            [self.provider],
            {"strict_fake": self.fake},
            audit_writer=self.audits.append,
        )

    def test_completed_call_is_audited_public_safe_and_idempotent(self):
        kwargs = {
            "tenant_id": "tenant-a",
            "snapshot": snapshot(),
            "provider_id": "unit-provider",
            "model_id": "unit-model",
            "parts": [{"modality": "text", "text": "grade this"}],
            "idempotency_key": "case-1",
        }
        first = self.gateway.invoke(**kwargs)
        second = self.gateway.invoke(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "completed")
        self.assertTrue(first["evaluation_eligible"])
        self.assertFalse(first["release_authority"])
        self.assertEqual(self.fake.calls, 1)
        self.assertEqual(len(self.audits), 1)
        self.assertNotIn("grade this", str(self.audits))
        self.assertFalse(first["raw_request_included"])
        self.assertFalse(first["raw_response_included"])

    def test_incomplete_or_cross_tenant_snapshot_never_calls_provider(self):
        for tenant, evidence in [
            ("tenant-a", snapshot(completeness="partial")),
            ("tenant-b", snapshot(tenant="tenant-a")),
        ]:
            result = self.gateway.invoke(
                tenant_id=tenant,
                snapshot=evidence,
                provider_id="unit-provider",
                model_id="unit-model",
                parts=[{"modality": "text", "text": "x"}],
                idempotency_key=f"{tenant}-{evidence['completeness']}",
            )
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["evaluation_eligible"])
            self.assertFalse(result["release_authority"])
        self.assertEqual(self.fake.calls, 0)

    def test_multimodal_parts_require_capability_and_content_hash(self):
        missing_hash = self.gateway.invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unit-provider",
            model_id="vision",
            parts=[{"modality": "image", "data": "base64"}],
            idempotency_key="image-no-hash",
        )
        unsupported = self.gateway.invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unit-provider",
            model_id="audio",
            parts=[{"modality": "audio", "content_hash": stable_hash("audio")}],
            idempotency_key="audio",
        )
        self.assertEqual(missing_hash["status"], "blocked")
        self.assertEqual(unsupported["status"], "unsupported")
        self.assertEqual(self.fake.calls, 0)

    def test_audit_failure_blocks_before_external_call(self):
        gateway = ProviderGateway(
            [self.provider],
            {"strict_fake": self.fake},
            audit_writer=lambda event: (_ for _ in ()).throw(RuntimeError("down")),
        )
        result = gateway.invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unit-provider",
            model_id="unit-model",
            parts=[{"modality": "text", "text": "x"}],
            idempotency_key="audit-down",
        )
        self.assertEqual(result["blockers"], ["audit_write_failed"])
        self.assertEqual(self.fake.calls, 0)

    def test_timeout_invalid_response_and_provider_error_fail_closed(self):
        cases = [
            (TimeoutAdapter(), "timeout"),
            (StrictFakeAdapter({"usage": {}}), "invalid_response"),
            (StrictFakeAdapter(failure="provider down"), "provider_error"),
        ]
        for index, (adapter, expected) in enumerate(cases):
            gateway = ProviderGateway([self.provider], {"strict_fake": adapter})
            result = gateway.invoke(
                tenant_id="tenant-a",
                snapshot=snapshot(),
                provider_id="unit-provider",
                model_id="unit-model",
                parts=[{"modality": "text", "text": "x"}],
                idempotency_key=f"failure-{index}",
            )
            self.assertEqual(result["status"], expected)
            self.assertFalse(result["evaluation_eligible"])
            self.assertFalse(result["release_authority"])
            self.assertEqual(result["attempts"][0]["status"], expected)

    def test_unknown_protocol_and_capability_selection_are_explicit(self):
        unknown = ProviderDefinition(
            "unknown-provider",
            "not_registered",
            "memory://unknown",
            "",
            frozenset({"text"}),
            frozenset({"tenant-a"}),
        )
        gateway = ProviderGateway([self.provider, unknown], {"strict_fake": self.fake})
        self.assertEqual(gateway.select(tenant_id="tenant-a", required_modalities=["image"]), ["unit-provider"])
        self.assertEqual(gateway.select(tenant_id="tenant-b", required_modalities=["text"]), [])
        result = gateway.invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unknown-provider",
            model_id="unit-model",
            parts=[{"modality": "text", "text": "x"}],
            idempotency_key="unknown-protocol",
        )
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse(result["evaluation_eligible"])
        self.assertFalse(result["release_authority"])

    def test_same_idempotency_key_with_changed_payload_or_model_is_a_new_logical_call(self):
        base = {
            "tenant_id": "tenant-a",
            "snapshot": snapshot(),
            "provider_id": "unit-provider",
            "model_id": "unit-model",
            "parts": [{"modality": "text", "text": "first"}],
            "idempotency_key": "stable-client-key",
        }
        first = self.gateway.invoke(**base)
        changed_payload = self.gateway.invoke(
            **{**base, "parts": [{"modality": "text", "text": "second"}]}
        )
        changed_model = self.gateway.invoke(**{**base, "model_id": "unit-model-v2"})
        replay = self.gateway.invoke(**base)
        self.assertEqual(first, replay)
        self.assertNotEqual(first["logical_call_id"], changed_payload["logical_call_id"])
        self.assertNotEqual(first["payload_hash"], changed_payload["payload_hash"])
        self.assertNotEqual(first["logical_call_id"], changed_model["logical_call_id"])
        self.assertEqual(self.fake.calls, 3)

    def test_catalog_supports_local_and_selective_cloud_imports(self):
        catalog = {item.provider_id: item for item in default_provider_catalog()}
        self.assertIsInstance(OllamaAdapter(), OllamaAdapter)
        self.assertTrue(catalog["ollama-local"].enabled)
        self.assertEqual(catalog["ollama-local"].data_residency, "local")
        for provider_id in ("openai", "anthropic", "google", "dashscope", "openrouter", "azure-openai"):
            self.assertFalse(catalog[provider_id].enabled)
            self.assertTrue(catalog[provider_id].credential_ref.startswith("secret://"))


if __name__ == "__main__":
    unittest.main()
