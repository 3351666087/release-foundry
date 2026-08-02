import hashlib
import hmac
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error

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
    OpenAICompatibleAdapter,
    ProviderAuthenticationFailed,
    RetryPolicy,
    TenantProviderPolicy,
    build_local_smoke_evidence,
    build_composite_agent_capability_contract,
    build_composite_agent_delegated_batch_receipt,
    build_composite_agent_delegated_call_receipt,
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
    def test_round34_composite_agent_image_generation_is_delegation_bound(self):
        contract = build_composite_agent_capability_contract(
            agent_model={
                "provider_id": "internal-agent",
                "model_id": "gpt-5.6-sol",
                "model_version": "observed-version",
            },
            delegated_models=[
                {
                    "provider_id": "internal-image",
                    "model_id": "image-2",
                    "model_version": "observed-version",
                    "role": "image_generator",
                    "capabilities": ["image_generation", "image_text_rendering"],
                }
            ],
            capabilities=[
                "text_reasoning",
                "image_generation",
                "image_text_rendering",
            ],
        )
        self.assertEqual(contract["qualification_state"], "declared")
        self.assertTrue(
            contract["evaluation_requirements"]["text_rendering_requires_ocr_comparison"]
        )
        self.assertFalse(
            contract["evaluation_requirements"]["self_evaluation_has_release_authority"]
        )
        self.assert_schema(contract, "composite_agent_capability_contract.schema.json")
        missing = build_composite_agent_capability_contract(
            agent_model={
                "provider_id": "internal-agent",
                "model_id": "gpt-5.6-sol",
                "model_version": "observed-version",
            },
            delegated_models=[],
            capabilities=["image_generation"],
        )
        self.assertIn("composite_agent_image_generator_missing", missing["blockers"])
        self.assert_schema(missing, "composite_agent_capability_contract.schema.json")

    def test_round36_composite_agent_text_rendering_capability_mismatch_blocks(self):
        contract = build_composite_agent_capability_contract(
            agent_model={
                "provider_id": "internal-agent",
                "model_id": "gpt-5.6-sol",
                "model_version": "observed-version",
            },
            delegated_models=[
                {
                    "provider_id": "internal-image",
                    "model_id": "image-2",
                    "model_version": "observed-version",
                    "role": "image_generator",
                    "capabilities": ["image_generation"],
                }
            ],
            capabilities=[
                "text_reasoning",
                "image_generation",
                "image_text_rendering",
            ],
        )
        self.assertEqual(contract["qualification_state"], "blocked")
        self.assertIn(
            "composite_agent_image_text_renderer_missing", contract["blockers"]
        )
        self.assertNotIn("composite_agent_image_generator_missing", contract["blockers"])
        self.assert_schema(contract, "composite_agent_capability_contract.schema.json")

    def test_round35_composite_delegated_receipt_routes_disagreement_to_review(self):
        delegated_model = {
            "provider_id": "internal-image",
            "model_id": "image-2",
            "model_version": "observed-version",
        }
        contract = build_composite_agent_capability_contract(
            agent_model={
                "provider_id": "internal-agent",
                "model_id": "gpt-5.6-sol",
                "model_version": "observed-version",
            },
            delegated_models=[
                {
                    **delegated_model,
                    "role": "image_generator",
                    "capabilities": ["image_generation", "image_text_rendering"],
                }
            ],
            capabilities=["text_reasoning", "image_generation", "image_text_rendering"],
        )
        receipt = build_composite_agent_delegated_call_receipt(
            capability_contract=contract,
            planner_request_hash=stable_hash("request"),
            delegated_model=delegated_model,
            image_model_response_hash=stable_hash("response"),
            generated_artifact_hash=stable_hash("artifact"),
            requested_text_hash=stable_hash("requested"),
            ocr_observed_text_hash=stable_hash("observed"),
            ocr_engine={
                "provider_id": "local-ocr",
                "model_id": "ocr-engine",
                "model_version": "observed-version",
            },
            ocr_extraction_artifact_hash=stable_hash("ocr-extraction"),
            planner_safety_claim="safe",
            safety_judge_result={
                "provider_id": "independent-local",
                "model_id": "safety-judge",
                "model_version": "observed-version",
                "evaluated_artifact_hash": stable_hash("artifact"),
                "status": "unsafe",
                "release_authority": False,
            },
        )
        self.assertEqual(receipt["qualification_state"], "blocked")
        self.assertTrue(receipt["human_review_required"])
        self.assertIn("composite_agent_ocr_disagreement", receipt["blockers"])
        self.assertIn("composite_agent_safety_judge_unsafe", receipt["blockers"])
        self.assertIn("composite_agent_safety_disagreement", receipt["blockers"])
        self.assert_schema(
            receipt, "composite_agent_delegated_call_receipt.schema.json"
        )

    def test_round36_composite_judge_provider_failure_is_incomplete(self):
        delegated_model = {
            "provider_id": "internal-image",
            "model_id": "image-2",
            "model_version": "observed-version",
        }
        contract = build_composite_agent_capability_contract(
            agent_model={
                "provider_id": "internal-agent",
                "model_id": "gpt-5.6-sol",
                "model_version": "observed-version",
            },
            delegated_models=[
                {
                    **delegated_model,
                    "role": "image_generator",
                    "capabilities": ["image_generation"],
                }
            ],
            capabilities=["text_reasoning", "image_generation"],
        )
        receipt = build_composite_agent_delegated_call_receipt(
            capability_contract=contract,
            planner_request_hash=stable_hash("request"),
            delegated_model=delegated_model,
            image_model_response_hash=stable_hash("response"),
            generated_artifact_hash=stable_hash("artifact"),
            planner_safety_claim="safe",
            safety_judge_result={
                "provider_id": "independent-local",
                "model_id": "safety-judge",
                "model_version": "observed-version",
                "evaluated_artifact_hash": stable_hash("artifact"),
                "status": "provider_failure",
                "release_authority": False,
            },
        )
        self.assertEqual(receipt["qualification_state"], "incomplete")
        self.assertIn(
            "composite_agent_safety_judge_provider_failure", receipt["blockers"]
        )
        self.assertNotEqual(receipt["qualification_state"], "review_available")
        self.assert_schema(
            receipt, "composite_agent_delegated_call_receipt.schema.json"
        )

    def test_round36_composite_batch_binds_multiple_artifacts_and_ocr_engine(self):
        delegated_model = {
            "provider_id": "internal-image",
            "model_id": "image-2",
            "model_version": "observed-version",
        }
        contract = build_composite_agent_capability_contract(
            agent_model={
                "provider_id": "internal-agent",
                "model_id": "gpt-5.6-sol",
                "model_version": "observed-version",
            },
            delegated_models=[
                {
                    **delegated_model,
                    "role": "image_generator",
                    "capabilities": ["image_generation", "image_text_rendering"],
                }
            ],
            capabilities=["text_reasoning", "image_generation", "image_text_rendering"],
        )
        artifact_calls = []
        for index in range(2):
            artifact_hash = stable_hash(f"artifact-{index}")
            artifact_calls.append(
                {
                    "delegated_model": delegated_model,
                    "image_model_response_hash": stable_hash(f"response-{index}"),
                    "generated_artifact_hash": artifact_hash,
                    "requested_text_hash": stable_hash(f"text-{index}"),
                    "ocr_observed_text_hash": stable_hash(f"text-{index}"),
                    "ocr_engine": {
                        "provider_id": "local-ocr",
                        "model_id": "ocr-engine",
                        "model_version": "observed-version",
                    },
                    "ocr_extraction_artifact_hash": stable_hash(
                        f"ocr-extraction-{index}"
                    ),
                    "safety_judge_result": {
                        "provider_id": "independent-local",
                        "model_id": "safety-judge",
                        "model_version": "observed-version",
                        "evaluated_artifact_hash": artifact_hash,
                        "status": "safe",
                        "release_authority": False,
                    },
                }
            )
        receipt = build_composite_agent_delegated_batch_receipt(
            capability_contract=contract,
            planner_request_hash=stable_hash("request"),
            artifact_calls=artifact_calls,
        )
        self.assertEqual(receipt["artifact_count"], 2)
        self.assertEqual(receipt["qualification_state"], "review_available")
        self.assertEqual(len(set(receipt["artifact_receipt_hashes"])), 2)
        self.assert_schema(
            receipt, "composite_agent_delegated_batch_receipt.schema.json"
        )

    def test_round35_composite_delegated_receipt_rejects_tampered_contract_and_wrong_artifact_review(self):
        delegated_model = {
            "provider_id": "internal-image",
            "model_id": "image-2",
            "model_version": "observed-version",
        }
        contract = build_composite_agent_capability_contract(
            agent_model={
                "provider_id": "internal-agent",
                "model_id": "gpt-5.6-sol",
                "model_version": "observed-version",
            },
            delegated_models=[
                {
                    **delegated_model,
                    "role": "image_generator",
                    "capabilities": ["image_generation"],
                }
            ],
            capabilities=["text_reasoning", "image_generation"],
        )
        receipt = build_composite_agent_delegated_call_receipt(
            capability_contract={**contract, "capabilities": ["text_reasoning"]},
            planner_request_hash=stable_hash("request"),
            delegated_model=delegated_model,
            image_model_response_hash=stable_hash("response"),
            generated_artifact_hash=stable_hash("artifact"),
            safety_judge_result={
                "provider_id": "independent-local",
                "model_id": "safety-judge",
                "model_version": "observed-version",
                "evaluated_artifact_hash": stable_hash("different-artifact"),
                "status": "safe",
                "release_authority": False,
            },
        )
        self.assertEqual(receipt["qualification_state"], "blocked")
        self.assertIn("composite_agent_capability_contract_invalid", receipt["blockers"])
        self.assertIn(
            "composite_agent_independent_safety_judge_invalid", receipt["blockers"]
        )
        self.assertEqual(
            receipt["safety_judge_model"]["model_id"], "safety-judge"
        )
        self.assert_schema(
            receipt, "composite_agent_delegated_call_receipt.schema.json"
        )

    def test_round35_provider_handoff_binds_verified_durability_receipt(self):
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
            "attempts": [],
        }
        receipt = {
            "file_write_state": "completed",
            "file_fsync_state": "verified",
            "atomic_replace_state": "verified",
            "post_replace_reopen_state": "verified",
            "parent_directory_flush_state": "unavailable",
        }
        ready = build_provider_provenance_handoff(
            tenant_scope=scope,
            snapshot=snapshot(),
            provider_result=result,
            semantic_output={"validated": True},
            bundle_verification={
                "manifest_authenticated": True,
                "authenticated_bundle_digest": digest(b"bundle"),
            },
            durability_receipt=receipt,
        )
        self.assertEqual(ready["durability_receipt_hash"], stable_hash(receipt))
        self.assert_schema(ready, "provider_provenance_handoff.schema.json")

        blocked = build_provider_provenance_handoff(
            tenant_scope=scope,
            snapshot=snapshot(),
            provider_result=result,
            semantic_output={"validated": True},
            bundle_verification={
                "manifest_authenticated": True,
                "authenticated_bundle_digest": digest(b"bundle"),
            },
            durability_receipt={**receipt, "file_fsync_state": "not_exposed"},
        )
        self.assertIn(
            "result_persistence_file_fsync_unverified", blocked["blockers"]
        )

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

    def test_openai_compatible_multimodal_data_url_and_strict_json_output(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps(
                    {
                        "id": "request-1",
                        "choices": [{"message": {"content": json.dumps({
                            "passed": False,
                            "score": 0.2,
                            "reason": "visible mismatch",
                            "failure_classes": ["visual"],
                            "evidence_refs": ["image-1"],
                            "abstained": False,
                        })}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 8},
                    }
                ).encode()

        resolver = EnvironmentCredentialResolver({"secret://provider/default": "runtime-only"})
        adapter = OpenAICompatibleAdapter(resolver)
        with patch("services.judge.provider_runtime.request.urlopen", return_value=Response()) as urlopen:
            result = adapter.invoke(
                {
                    "credential_ref": "secret://provider/default",
                    "model_id": "vision",
                    "base_url": "https://provider.invalid/v1",
                },
                {"parts": [
                    {"modality": "text", "text": "judge"},
                    {"modality": "image", "data": "data:image/png;base64,AAAA"},
                ]},
                10,
            )
        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(
            sent["messages"][0]["content"][1]["image_url"]["url"],
            "data:image/png;base64,AAAA",
        )
        validated = validate_semantic_judge_output(result["output_text"])
        self.assertFalse(validated["passed"])

    def test_openai_compatible_401_and_403_are_terminal_authentication_failures(self):
        resolver = EnvironmentCredentialResolver({"secret://provider/default": "runtime-only"})
        adapter = OpenAICompatibleAdapter(resolver)
        for status in (401, 403):
            failure = error.HTTPError("https://provider.invalid", status, "denied", {}, None)
            with patch("services.judge.provider_runtime.request.urlopen", side_effect=failure):
                with self.assertRaises(ProviderAuthenticationFailed):
                    adapter.invoke(
                        {
                            "credential_ref": "secret://provider/default",
                            "model_id": "vision",
                            "base_url": "https://provider.invalid/v1",
                        },
                        {"parts": [{"modality": "text", "text": "judge"}]},
                        10,
                    )

    def test_openai_compatible_governs_model_options_before_network(self):
        resolver = EnvironmentCredentialResolver({"secret://provider/default": "runtime-only"})
        adapter = OpenAICompatibleAdapter(resolver)
        with patch("services.judge.provider_runtime.request.urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "unsupported OpenAI-compatible model options"):
                adapter.invoke(
                    {
                        "credential_ref": "secret://provider/default",
                        "model_id": "vision",
                        "base_url": "https://provider.invalid/v1",
                        "options": {"credential_ref": "not-an-option"},
                    },
                    {"parts": [{"modality": "text", "text": "judge"}]},
                    10,
                )
        urlopen.assert_not_called()

        for options in ({"temperature": 3}, {"top_p": 0}, {"max_tokens": 0}, {"seed": True}):
            with patch("services.judge.provider_runtime.request.urlopen") as urlopen:
                with self.assertRaisesRegex(ValueError, "invalid OpenAI-compatible model option values"):
                    adapter.invoke(
                        {
                            "credential_ref": "secret://provider/default",
                            "model_id": "vision",
                            "base_url": "https://provider.invalid/v1",
                            "options": options,
                        },
                        {"parts": [{"modality": "text", "text": "judge"}]},
                        10,
                    )
            urlopen.assert_not_called()

    def test_openai_compatible_missing_choices_or_content_is_empty_public_output(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps(self.payload).encode()

        resolver = EnvironmentCredentialResolver({"secret://provider/default": "runtime-only"})
        adapter = OpenAICompatibleAdapter(resolver)
        for payload in ({}, {"choices": [{}]}, {"choices": [{"message": {"content": ""}}]}):
            with patch("services.judge.provider_runtime.request.urlopen", return_value=Response(payload)):
                with self.assertRaisesRegex(ValueError, "message content is empty"):
                    adapter.invoke(
                        {
                            "credential_ref": "secret://provider/default",
                            "model_id": "vision",
                            "base_url": "https://provider.invalid/v1",
                        },
                        {"parts": [{"modality": "text", "text": "judge"}]},
                        10,
                    )

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
            credential_rotation_marker="hmac-sha256:" + "b" * 64,
        )
        self.assertFalse(evidence["raw_payload_included"])
        self.assertFalse(evidence["secret_included"])
        self.assertEqual(evidence["capability_state"], "callable")
        self.assertEqual(evidence["calibration_state"], "uncalibrated")
        self.assertEqual(evidence["model_digest"], "sha256:" + "a" * 64)
        self.assertEqual(evidence["credential_rotation_marker"], "hmac-sha256:" + "b" * 64)
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

        invalid = build_local_smoke_evidence(
            modality="text", model_id="vision", provider_result={"status": "invalid_response"},
            content_hashes=[],
        )
        self.assertEqual(invalid["capability_state"], "protocol_reachable")
        self.assertEqual(invalid["calibration_state"], "uncalibrated")
        unavailable = build_local_smoke_evidence(
            modality="text", model_id="vision", provider_result={"status": "provider_unavailable"},
            content_hashes=[],
        )
        self.assertEqual(unavailable["capability_state"], "unavailable")
        self.assertEqual(unavailable["calibration_state"], "uncalibrated")
        for item in (evidence, timed_out, invalid, unavailable):
            self.assert_schema(item, "local_provider_smoke.schema.json")

    def test_local_smoke_rejects_noncanonical_hashes(self):
        with self.assertRaises(ValueError):
            build_local_smoke_evidence(
                modality="image", model_id="vision", provider_result={"status": "completed"},
                content_hashes=["SHA256:not-canonical"],
            )
        with self.assertRaises(ValueError):
            build_local_smoke_evidence(
                modality="text", model_id="vision", provider_result={"status": "completed"},
                content_hashes=[], model_digest="not-a-digest",
            )
        with self.assertRaises(ValueError):
            build_local_smoke_evidence(
                modality="text",
                model_id="vision",
                provider_result={"status": "completed"},
                content_hashes=[],
                credential_rotation_marker="secret-value",
            )


if __name__ == "__main__":
    unittest.main()
