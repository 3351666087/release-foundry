import unittest

from services.judge.provider_gateway import (
    OllamaAdapter,
    ProviderDefinition,
    ProviderGateway,
    StrictFakeAdapter,
    StrictFakeReconciliationAdapter,
    default_provider_catalog,
)
from services.judge.provider_runtime import validate_semantic_judge_output
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
            reconciliation_mode="provider_status_lookup",
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
        hash_only = self.gateway.invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unit-provider",
            model_id="vision",
            parts=[{"modality": "image", "content_hash": stable_hash("image")}],
            idempotency_key="image-hash-only",
        )
        empty_text = self.gateway.invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unit-provider",
            model_id="unit-model",
            parts=[{"modality": "text", "text": "   "}],
            idempotency_key="empty-text",
        )
        self.assertEqual(missing_hash["status"], "blocked")
        self.assertEqual(hash_only["status"], "blocked")
        self.assertEqual(empty_text["status"], "blocked")
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

    def test_reconciliation_is_capability_gated_and_never_authorizes_retry(self):
        base = {
            "scope": {
                "organization_id": "org-a", "tenant_id": "tenant-a",
                "workspace_id": "workspace-a", "project_id": "project-a",
                "environment_id": "test",
            },
            "operation_id": stable_hash("operation"),
            "provider_call_id": stable_hash("provider-call"),
            "logical_call_id": stable_hash("logical-call"),
            "provider_id": "unit-provider",
            "model_id": "unit-model",
            "snapshot_hash": stable_hash("snapshot"),
            "payload_hash": stable_hash("payload"),
            "idempotency_key_hash": stable_hash("idempotency"),
            "provider_endpoint_hash": stable_hash("provider-endpoint"),
            "provider_generation": 1,
        }
        unsupported = self.gateway.reconcile(**base)
        self.assertEqual(unsupported["status"], "reconciliation_unsupported")
        self.assertFalse(unsupported["retry_authorized"])
        self.assertFalse(unsupported["release_authority"])

        adapter = StrictFakeReconciliationAdapter(
            reconciliation_response={"status": "remote_not_found"}
        )
        gateway = ProviderGateway(
            [self.provider], {"strict_fake": adapter},
            response_validator=validate_semantic_judge_output,
        )
        not_found = gateway.reconcile(**base)
        self.assertEqual(not_found["status"], "remote_not_found")
        self.assertFalse(not_found["retry_authorized"])
        self.assertFalse(not_found["evaluation_eligible"])

    def test_only_fully_bound_remote_completion_is_evaluation_eligible(self):
        base = {
            "scope": {
                "organization_id": "org-a", "tenant_id": "tenant-a",
                "workspace_id": "workspace-a", "project_id": "project-a",
                "environment_id": "test",
            },
            "operation_id": stable_hash("operation"),
            "provider_call_id": stable_hash("provider-call"),
            "logical_call_id": stable_hash("logical-call"),
            "provider_id": "unit-provider",
            "model_id": "unit-model",
            "snapshot_hash": stable_hash("snapshot"),
            "payload_hash": stable_hash("payload"),
            "idempotency_key_hash": stable_hash("idempotency"),
            "provider_endpoint_hash": stable_hash("provider-endpoint"),
            "provider_generation": 1,
        }
        completed = {
            "status": "remote_completed",
            **{key: base[key] for key in (
                "provider_call_id", "logical_call_id", "provider_id", "model_id",
                "snapshot_hash", "payload_hash", "idempotency_key_hash",
                "provider_endpoint_hash", "scope", "operation_id", "provider_generation",
            )},
            "output": {
                "output_text": (
                    '{"passed":true,"score":1,"reason":"verified",'
                    '"failure_classes":[],"evidence_refs":["snapshot"],"abstained":false}'
                ),
                "usage": {},
            },
        }
        adapter = StrictFakeReconciliationAdapter(reconciliation_response=completed)
        gateway = ProviderGateway(
            [self.provider], {"strict_fake": adapter},
            response_validator=validate_semantic_judge_output,
        )
        verified = gateway.reconcile(**base)
        self.assertEqual(verified["status"], "remote_completed")
        self.assertTrue(verified["evaluation_eligible"])
        self.assertIn("output_hash", verified)
        self.assertIn("normalized_output", verified)
        self.assertNotIn("output_text", str(verified))

        mismatches = {
            "snapshot_hash": stable_hash("wrong"),
            "idempotency_key_hash": stable_hash("wrong-key"),
            "provider_endpoint_hash": stable_hash("wrong-endpoint"),
            "operation_id": stable_hash("wrong-operation"),
            "scope": {**base["scope"], "project_id": "other-project"},
        }
        for field, value in mismatches.items():
            with self.subTest(field=field):
                adapter.reconciliation_response = {**completed, field: value}
                rejected = ProviderGateway(
                    [self.provider], {"strict_fake": adapter},
                    response_validator=validate_semantic_judge_output,
                ).reconcile(**base)
                self.assertEqual(rejected["status"], "remote_unknown")
                self.assertFalse(rejected["evaluation_eligible"])


if __name__ == "__main__":
    unittest.main()
