import hashlib
import hmac
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from services.judge.provider_gateway import ProviderDefinition, ProviderGateway, StrictFakeAdapter
from services.judge.provider_runtime import (
    AUTHENTICATED_BUNDLE_SCHEMA_VERSION,
    BudgetManager,
    CircuitBreaker,
    EnvironmentCredentialResolver,
    ModelRecord,
    ModelRegistry,
    OllamaDiscovery,
    RetryPolicy,
    TenantProviderPolicy,
    build_local_smoke_evidence,
    build_provider_provenance_handoff,
    validate_semantic_judge_output,
    verify_authenticated_evidence_bundle,
)
from services.judge.result_persistence import stable_hash


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def signed_bundle(key=b"x" * 32, now=1_750_000_000_000):
    evidence = [
        {
            "artifact_path": "reports/run.json",
            "sha256": digest(b"report"),
            "size_bytes": 6,
            "media_type": "application/json",
        }
    ]
    bundle = {
        "schema_version": AUTHENTICATED_BUNDLE_SCHEMA_VERSION,
        "algorithm": "hmac-sha256",
        "key_id": "a1:test:v1",
        "bundle_id_digest": digest(b"bundle"),
        "tenant_digest": digest(b"tenant-a"),
        "project_digest": digest(b"project-a"),
        "evidence": evidence,
        "evidence_digest": digest(canonical(evidence)),
        "issued_at_unix_ms": now - 1000,
        "expires_at_unix_ms": now + 1000,
        "signature": "",
    }
    signing = {
        key: bundle[key]
        for key in (
            "schema_version",
            "algorithm",
            "key_id",
            "bundle_id_digest",
            "tenant_digest",
            "project_digest",
            "evidence_digest",
            "issued_at_unix_ms",
            "expires_at_unix_ms",
        )
    }
    bundle["signature"] = hmac.new(key, canonical(signing), hashlib.sha256).hexdigest()
    return bundle


def snapshot():
    core = {"tenant_id": "tenant-a", "completeness": "complete"}
    return {**core, "snapshot_id": stable_hash(core), "snapshot_hash": stable_hash(core)}


class FlakyAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, model, payload, timeout_seconds):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError
        return {
            "output_text": json.dumps(
                {
                    "passed": True,
                    "score": 0.9,
                    "reason": "grounded",
                    "failure_classes": [],
                    "evidence_refs": ["trace-1"],
                    "abstained": False,
                }
            ),
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }


class ProviderRuntimeTests(unittest.TestCase):
    @staticmethod
    def assert_schema(instance, schema_name):
        schema_path = Path(__file__).parents[2] / "docs" / "a2" / "schemas" / schema_name
        jsonschema.Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(instance)

    def test_registry_discovers_and_filters_local_multimodal_models(self):
        registry = ModelRegistry(
            [
                ModelRecord("ollama-local", "vision", "d1", frozenset({"text", "image"}), local=True),
                ModelRecord("cloud", "text", "v1", frozenset({"text"})),
                ModelRecord("cloud", "preview", "v2", frozenset({"text", "image"}), lifecycle="preview"),
            ]
        )
        selected = registry.select(required_modalities={"image"})
        self.assertEqual([item.model_id for item in selected], ["vision"])
        exported = registry.export_public()
        self.assertEqual(exported["schema_version"], "a2.model_registry.v1")
        self.assertNotIn("credential", str(exported))
        self.assert_schema(exported, "model_registry.schema.json")

        with patch(
            "services.judge.provider_runtime._json_get",
            return_value={
                "models": [
                    {"name": "qwen3-vl", "digest": "abc", "details": {"families": ["qwen3vl"]}},
                    {"name": "text-only", "digest": "def", "details": {"family": "qwen3"}},
                ]
            },
        ):
            discovered = OllamaDiscovery().discover("http://local")
            self.assertEqual(discovered[0].modalities, frozenset({"text", "image"}))
            self.assertEqual(discovered[1].modalities, frozenset({"text"}))

    def test_ollama_health_has_explicit_ready_timeout_and_unavailable_states(self):
        discovery = OllamaDiscovery()
        with patch.object(discovery, "discover", return_value=[]):
            self.assertEqual(discovery.health("http://local")["status"], "ready")
        with patch.object(discovery, "discover", side_effect=TimeoutError):
            self.assertEqual(discovery.health("http://local")["status"], "timeout")
        with patch.object(discovery, "discover", side_effect=RuntimeError):
            self.assertEqual(discovery.health("http://local")["status"], "unavailable")

    def test_credentials_policy_residency_and_payload_limits_fail_closed(self):
        resolver = EnvironmentCredentialResolver({"secret://provider/default": "runtime-only"})
        self.assertEqual(resolver.resolve("secret://provider/default"), "runtime-only")
        with self.assertRaises(ValueError):
            resolver.resolve("plain")
        policy = TenantProviderPolicy(
            frozenset({"ollama-local"}),
            frozenset({"vision"}),
            frozenset({"local"}),
            max_parts=1,
            max_total_bytes=10,
            max_part_bytes={"text": 5},
        )
        blockers = policy.authorize(
            provider_id="cloud",
            model_id="other",
            data_residency="us",
            parts=[{"modality": "text", "text": "123456"}, {"modality": "text", "text": "123456"}],
        )
        self.assertEqual(
            blockers,
            [
                "data_residency_not_allowed",
                "model_not_allowed",
                "part_count_exceeded",
                "provider_not_allowed",
                "text_part_size_exceeded",
                "total_payload_size_exceeded",
            ],
        )

    def test_budget_reservation_settlement_and_cost_ledger_are_public_safe(self):
        budget = BudgetManager(0.02, {"model": (0.5, 1.0)})
        reservation = budget.reserve("model", 10, 5)
        self.assertTrue(reservation.allowed)
        event = budget.settle(reservation, input_tokens=10, output_tokens=5, model_id="model", attempt=1)
        self.assertEqual(event["actual_cost_usd"], 0.01)
        self.assertFalse(event["raw_payload_included"])
        self.assertFalse(BudgetManager(0, {"model": (1, 1)}).reserve("model", 1, 1).allowed)

    def test_gateway_enforces_policy_retries_validates_output_and_breaks_circuit(self):
        provider = ProviderDefinition(
            "unit",
            "flaky",
            "memory://",
            "",
            frozenset({"text"}),
            frozenset({"tenant-a"}),
            data_residency="local",
        )
        policy = TenantProviderPolicy(frozenset({"unit"}), frozenset({"model"}), frozenset({"local"}))
        adapter = FlakyAdapter()
        gateway = ProviderGateway(
            [provider],
            {"flaky": adapter},
            request_authorizer=lambda context: policy.authorize(
                provider_id=context["provider"].provider_id,
                model_id=context["model_id"],
                data_residency=context["provider"].data_residency,
                parts=context["parts"],
            ),
            response_validator=validate_semantic_judge_output,
            retry_policy=RetryPolicy(max_attempts=2),
        )
        result = gateway.invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unit",
            model_id="model",
            parts=[{"modality": "text", "text": "judge"}],
            idempotency_key="retry",
        )
        self.assertEqual([item["status"] for item in result["attempts"]], ["timeout", "completed"])
        self.assertIn("structured_output_hash", result)
        self.assertFalse(result["release_authority"])

        breaker = CircuitBreaker(threshold=1, cooldown_seconds=100)
        breaker.record(False)
        blocked = ProviderGateway(
            [provider],
            {"flaky": adapter},
            circuit_breakers={"unit": breaker},
        ).invoke(
            tenant_id="tenant-a",
            snapshot=snapshot(),
            provider_id="unit",
            model_id="model",
            parts=[{"modality": "text", "text": "judge"}],
            idempotency_key="circuit",
        )
        self.assertEqual(blocked["blockers"], ["circuit_open"])

    def test_semantic_output_rejects_unknown_fields_abstain_pass_and_bad_scores(self):
        valid = {
            "passed": False,
            "score": 0.3,
            "reason": "insufficient evidence",
            "failure_classes": ["grounding"],
            "evidence_refs": ["trace-1"],
            "abstained": False,
        }
        self.assertEqual(validate_semantic_judge_output(valid), valid)
        self.assert_schema(valid, "semantic_judge_output.schema.json")
        for invalid in (
            {**valid, "extra": True},
            {**valid, "score": 2},
            {**valid, "passed": True, "abstained": True},
        ):
            with self.assertRaises(ValueError):
                validate_semantic_judge_output(invalid)

    def test_authenticated_a1_bundle_gate_rejects_tamper_scope_and_expiry(self):
        now = 1_750_000_000_000
        bundle = signed_bundle(now=now)
        verified = verify_authenticated_evidence_bundle(
            bundle,
            key_resolver=lambda key_id: b"x" * 32,
            tenant_id="tenant-a",
            project_id="project-a",
            now_unix_ms=now,
        )
        self.assertTrue(verified["manifest_authenticated"])
        tampered = {**bundle, "evidence_digest": digest(b"tampered")}
        with self.assertRaises(ValueError):
            verify_authenticated_evidence_bundle(
                tampered,
                key_resolver=lambda key_id: b"x" * 32,
                tenant_id="tenant-a",
                project_id="project-a",
                now_unix_ms=now,
            )
        with self.assertRaises(ValueError):
            verify_authenticated_evidence_bundle(
                bundle,
                key_resolver=lambda key_id: b"x" * 32,
                tenant_id="tenant-b",
                project_id="project-a",
                now_unix_ms=now,
            )
        with self.assertRaises(ValueError):
            verify_authenticated_evidence_bundle(
                bundle,
                key_resolver=lambda key_id: b"x" * 32,
                tenant_id="tenant-a",
                project_id="project-a",
                now_unix_ms=now + 5000,
            )

    def test_a3_handoff_is_five_scope_public_safe_and_never_grants_release(self):
        scope = {
            "organization_id": "org-a",
            "tenant_id": "tenant-a",
            "workspace_id": "workspace-a",
            "project_id": "project-a",
            "environment_id": "prod",
        }
        result = {
            "status": "completed",
            "logical_call_id": stable_hash("call"),
            "provider_id": "unit",
            "model_id": "model",
            "response_hash": stable_hash("response"),
            "release_authority": False,
            "blockers": [],
        }
        handoff = build_provider_provenance_handoff(
            tenant_scope=scope,
            snapshot=snapshot(),
            provider_result=result,
            semantic_output={"validated": True},
            bundle_verification={"manifest_authenticated": True, "authenticated_bundle_digest": digest(b"bundle")},
        )
        self.assertEqual(handoff["status"], "ready")
        self.assertTrue(handoff["evaluation_eligible"])
        self.assertFalse(handoff["release_authority"])
        self.assertEqual(handoff["decision_authority"], "a2.release_gate.v1")
        self.assert_schema(handoff, "provider_provenance_handoff.schema.json")
        blocked = build_provider_provenance_handoff(
            tenant_scope={**scope, "environment_id": ""},
            snapshot=snapshot(),
            provider_result={**result, "status": "timeout", "blockers": ["timeout"]},
            semantic_output=None,
            bundle_verification={"manifest_authenticated": False},
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertFalse(blocked["evaluation_eligible"])
        self.assert_schema(blocked, "provider_provenance_handoff.schema.json")

    def test_local_smoke_evidence_contains_hashes_not_payloads(self):
        evidence = build_local_smoke_evidence(
            modality="image",
            model_id="vision",
            model_digest="sha256:" + "a" * 64,
            provider_result={
                "status": "completed",
                "logical_call_id": stable_hash("call"),
                "response_hash": stable_hash("response"),
            },
            content_hashes=[stable_hash("image")],
        )
        self.assertFalse(evidence["raw_payload_included"])
        self.assertFalse(evidence["secret_included"])
        self.assertEqual(evidence["capability_state"], "callable")
        self.assertEqual(evidence["calibration_state"], "uncalibrated")
        self.assertEqual(evidence["model_digest"], "sha256:" + "a" * 64)
        self.assertNotIn("data", evidence)

        timed_out = build_local_smoke_evidence(
            modality="image",
            model_id="vision",
            model_digest="sha256:" + "a" * 64,
            provider_result={
                "status": "timeout",
                "logical_call_id": stable_hash("timeout-call"),
                "response_hash": None,
            },
            content_hashes=[stable_hash("image")],
        )
        self.assertEqual(timed_out["capability_state"], "protocol_reachable")
        self.assertNotEqual(timed_out["capability_state"], "callable")
        self.assertEqual(timed_out["calibration_state"], "uncalibrated")


if __name__ == "__main__":
    unittest.main()
