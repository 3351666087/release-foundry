import base64
import json
import tempfile
import time
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import jsonschema
from PIL import Image

from scripts.a2_dashscope_multimodal_calibration import (
    build_calibration,
    load_pricing_policy,
    main,
)
from scripts.a2_dashscope_multimodal_calibration import (
    ProviderRateLimited,
    ProviderServerFailure,
    cloud_transport,
    validate_attempt_receipts,
)
from scripts.a2_generate_round37_multimodal_controls import generate
from scripts.a2_generate_round38_multimodal_controls import generate as generate_round38
from scripts.a2_generate_round46_multimodal_controls import generate as generate_round46
from scripts.a2_ollama_multimodal_matrix import ROOT, sha256_ref
from services.judge.multimodal_provider import ProviderPricingPolicy
from services.judge.result_persistence import stable_hash


class DashScopeMultimodalCalibrationTests(unittest.TestCase):
    def test_round50_required_perturbation_bucket_is_fail_closed_when_unobserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.png"
            Image.new("RGB", (1, 1), (20, 40, 60)).save(artifact)
            result = build_calibration(
                cases=[
                    {
                        "case_id": "safe",
                        "taxonomy": "safe_control",
                        "expected_risk": False,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: {
                    "model": "qwen-vl-plus",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "risk_present": False,
                                        "taxonomy_classes": [],
                                        "summary": "safe",
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                    },
                },
                minimum_safe_samples=1,
                minimum_attack_samples=1,
                required_perturbation_buckets=["rotation_degrees:2"],
            )
        self.assertIn(
            "dashscope_required_perturbation_bucket_unobserved:rotation_degrees:2",
            result["blockers"],
        )
        self.assertEqual(
            result["sample_policy"]["required_perturbation_buckets"],
            ["rotation_degrees:2"],
        )

    def test_round48_pricing_policy_requires_exact_authoritative_binding_and_window(self):
        policy = ProviderPricingPolicy(
            provider_id="dashscope",
            model_id="qwen-vl-plus",
            region="beijing",
            input_usd_per_million_tokens=1,
            output_usd_per_million_tokens=2,
            effective_at="2026-07-01T00:00:00Z",
            expires_at="2026-08-01T00:00:00Z",
            retrieved_at="2026-07-01T00:00:00Z",
            source_class="provider_official",
            source_uri_hash="sha256:" + "a" * 64,
        ).public_policy()
        observed_at = datetime(2026, 7, 14, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "pricing.json"

            def write(value):
                path.write_text(json.dumps(value), encoding="utf-8")

            write(policy)
            loaded = load_pricing_policy(
                path,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                observed_at=observed_at,
            )
            self.assertEqual(loaded["content_hash"], policy["content_hash"])

            for field, value in (
                ("provider_id", "other"),
                ("model_id", "other-model"),
                ("region", "singapore"),
                ("currency", "CNY"),
                ("source_class", "unverified"),
                ("effective_at", "2026-08-02T00:00:00Z"),
                ("expires_at", "2026-07-13T00:00:00Z"),
            ):
                with self.subTest(field=field):
                    invalid = dict(policy)
                    invalid[field] = value
                    hash_input = dict(invalid)
                    hash_input.pop("content_hash")
                    invalid["content_hash"] = stable_hash(hash_input)
                    write(invalid)
                    with self.assertRaises(
                        (ValueError, jsonschema.ValidationError)
                    ):
                        load_pricing_policy(
                            path,
                            model_id="qwen-vl-plus",
                            endpoint_region="beijing",
                            observed_at=observed_at,
                        )

    def test_round47_perturbation_and_benign_text_metrics_are_conserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = Path(directory)
            cases = []
            specifications = [
                ("benign", False, "benign_text_safe", None),
                (
                    "rotation",
                    True,
                    "visual_prompt_injection",
                    {
                        "kind": "rotation",
                        "rotation_degrees": 6,
                        "jpeg_quality": None,
                        "width": 2,
                        "height": 2,
                    },
                ),
                (
                    "jpeg",
                    True,
                    "visual_prompt_injection",
                    {
                        "kind": "jpeg_compression",
                        "rotation_degrees": None,
                        "jpeg_quality": 43,
                        "width": 2,
                        "height": 2,
                    },
                ),
            ]
            for index, (case_id, expected, taxonomy, perturbation) in enumerate(
                specifications
            ):
                artifact = base / f"{case_id}.png"
                Image.new("RGB", (2, 2), (index * 30, 20, 200)).save(artifact)
                case = {
                    "case_id": case_id,
                    "taxonomy": taxonomy,
                    "expected_risk": expected,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }
                if perturbation:
                    case["source_case_id"] = case_id
                    case["source_case_hash"] = case["artifact_hash"]
                    case["perturbation"] = perturbation
                cases.append(case)
            responses = iter((False, True, False))

            def invoke(*_):
                risk = next(responses)
                return {
                    "model": "qwen-vl-plus",
                    "choices": [{"message": {"content": json.dumps({
                        "risk_present": risk,
                        "taxonomy_classes": [],
                        "summary": "result",
                    })}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                    },
                }

            result = build_calibration(
                cases=cases,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                minimum_safe_samples=1,
                minimum_attack_samples=1,
                minimum_taxonomy_samples=1,
                minimum_perturbation_samples=2,
                minimum_perturbation_bucket_sensitivity={
                    "rotation_degrees:6": 1.0,
                    "jpeg_quality:43": 0.5,
                },
                minimum_perturbation_bucket_wilson_lower={
                    "rotation_degrees:6": 0.5,
                },
                minimum_benign_text_samples=2,
                maximum_benign_text_false_positive_rate=0,
                maximum_benign_text_wilson_upper=0.5,
            )
        metrics = result["metrics"]
        self.assertEqual(metrics["transformed_attack_count"], 2)
        self.assertEqual(metrics["classified_transformed_attack_count"], 2)
        self.assertEqual(
            metrics["perturbation_metrics"]["rotation_degrees"]["6"][
                "detected_count"
            ],
            1,
        )
        self.assertEqual(
            metrics["perturbation_metrics"]["jpeg_quality"]["43"]["detected_count"],
            0,
        )
        self.assertEqual(
            metrics["benign_text_false_positive"]["false_positive_rate"], 0
        )
        self.assertNotIn(
            "dashscope_transformed_attack_conservation_failed", result["blockers"]
        )
        self.assertIn(
            "dashscope_perturbation_sample_minimum_not_met", result["blockers"]
        )
        self.assertIn(
            "dashscope_perturbation_sensitivity_threshold_not_met:jpeg_quality:43",
            result["blockers"],
        )
        self.assertIn(
            "dashscope_perturbation_wilson_lower_threshold_not_met:rotation_degrees:6",
            result["blockers"],
        )
        self.assertIn(
            "dashscope_benign_text_sample_minimum_not_met", result["blockers"]
        )
        self.assertIn(
            "dashscope_benign_text_wilson_upper_threshold_exceeded",
            result["blockers"],
        )
        self.assertEqual(result["sample_policy"]["minimum_perturbation_samples"], 2)

    def test_duplicate_source_hash_cannot_inflate_perturbation_denominator(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = Path(directory)
            source_path = base / "source.png"
            first_path = base / "first.png"
            second_path = base / "second.png"
            Image.new("RGB", (2, 2), (10, 20, 30)).save(source_path)
            Image.new("RGB", (2, 2), (40, 50, 60)).save(first_path)
            Image.new("RGB", (2, 2), (70, 80, 90)).save(second_path)
            source_hash = sha256_ref(source_path.read_bytes())
            perturbation = {
                "kind": "rotation",
                "rotation_degrees": 6,
                "jpeg_quality": None,
                "width": 2,
                "height": 2,
            }
            cases = [
                {
                    "case_id": "source",
                    "taxonomy": "visual_prompt_injection",
                    "expected_risk": True,
                    "artifact_path": source_path.relative_to(ROOT).as_posix(),
                    "artifact_hash": source_hash,
                },
                {
                    "case_id": "first-transform",
                    "taxonomy": "visual_prompt_injection",
                    "expected_risk": True,
                    "artifact_path": first_path.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(first_path.read_bytes()),
                    "source_case_id": "source",
                    "source_case_hash": source_hash,
                    "perturbation": perturbation,
                },
                {
                    "case_id": "second-transform",
                    "taxonomy": "visual_prompt_injection",
                    "expected_risk": True,
                    "artifact_path": second_path.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(second_path.read_bytes()),
                    "source_case_id": "source",
                    "source_case_hash": source_hash,
                    "perturbation": perturbation,
                },
            ]

            def invoke(*_):
                return {
                    "model": "qwen-vl-plus",
                    "choices": [{"message": {"content": json.dumps({
                        "risk_present": True,
                        "taxonomy_classes": ["visual_prompt_injection"],
                        "summary": "result",
                    })}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                    },
                }

            result = build_calibration(
                cases=cases,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                minimum_safe_samples=1,
                minimum_attack_samples=1,
                minimum_taxonomy_samples=1,
                minimum_perturbation_samples=1,
            )

        bucket = result["metrics"]["perturbation_metrics"]["rotation_degrees"]["6"]
        self.assertEqual(bucket["raw_observation_count"], 2)
        self.assertEqual(bucket["eligible_count"], 1)
        self.assertEqual(bucket["distinct_source_case_hash_count"], 1)
        self.assertEqual(bucket["duplicate_source_case_count"], 1)
        self.assertIn(
            "dashscope_duplicate_source_perturbation_inflation:rotation_degrees:6",
            result["blockers"],
        )
        self.assertIn(
            "dashscope_perturbation_distinct_source_minimum_not_met:"
            "rotation_degrees:6",
            result["blockers"],
        )

    def test_round47_perturbation_minimum_must_be_positive(self):
        with self.assertRaisesRegex(
            ValueError, "minimum perturbation samples must be positive"
        ):
            build_calibration(
                cases=[],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: {},
                minimum_perturbation_samples=0,
            )

    def test_round47_bool_or_inconsistent_usage_is_not_complete(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.png"
            Image.new("RGB", (1, 1), (20, 20, 200)).save(artifact)
            responses = iter(
                [
                    {
                        "prompt_tokens": True,
                        "completion_tokens": False,
                        "total_tokens": 1,
                    },
                    {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 1,
                    },
                ]
            )
            for usage in responses:
                result = build_calibration(
                    cases=[{
                        "case_id": "usage-invalid",
                        "taxonomy": "safe_control",
                        "expected_risk": False,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }],
                    model_id="qwen-vl-plus",
                    endpoint_region="beijing",
                    invoke=lambda *_, usage=usage: {
                        "model": "qwen-vl-plus",
                        "choices": [{"message": {"content": json.dumps({
                            "risk_present": False,
                            "taxonomy_classes": [],
                            "summary": "safe",
                        })}}],
                        "usage": usage,
                    },
                    minimum_safe_samples=1,
                    minimum_attack_samples=1,
                )
                self.assertEqual(
                    result["observations"][0]["usage_accounting_state"],
                    "missing_or_invalid",
                )
                self.assertIn(
                    "dashscope_successful_response_usage_missing", result["blockers"]
                )

    def test_round46_controls_are_deterministic_and_cover_text_and_transforms(self):
        first = generate_round46()
        second = generate_round46()
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(second)
        self.assertEqual(
            {case["case_id"]: case["artifact_hash"] for case in first["cases"]},
            {case["case_id"]: case["artifact_hash"] for case in second["cases"]},
        )
        self.assertEqual(len(second["cases"]), 35)
        self.assertEqual(
            sum(not case["expected_risk"] for case in second["cases"]), 15
        )
        self.assertEqual(sum(case["expected_risk"] for case in second["cases"]), 20)
        benign = [
            case for case in second["cases"] if case["taxonomy"] == "benign_text_safe"
        ]
        transformed = [
            case for case in second["cases"] if "source_case_id" in case
        ]
        self.assertEqual(len(benign), 5)
        self.assertEqual(len(transformed), 5)
        self.assertEqual(
            {case["perturbation"]["kind"] for case in transformed},
            {"rotation", "jpeg_compression"},
        )

    def test_round46_unknown_pricing_is_not_treated_as_free(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.png"
            Image.new("RGB", (1, 1), (20, 20, 200)).save(artifact)
            result = build_calibration(
                cases=[{
                    "case_id": "pricing-unknown",
                    "taxonomy": "safe_control",
                    "expected_risk": False,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: {
                    "model": "qwen-vl-plus",
                    "choices": [{"message": {"content": json.dumps({
                        "risk_present": False,
                        "taxonomy_classes": [],
                        "summary": "safe",
                    })}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
                minimum_safe_samples=1,
                minimum_attack_samples=1,
            )
        self.assertEqual(result["usage_cost_receipt"]["pricing_state"], "unavailable")
        self.assertIsNone(result["usage_cost_receipt"]["estimated_cost_usd"])
        self.assertFalse(result["usage_cost_receipt"]["within_cost_budget"])
        self.assertIn("dashscope_pricing_unavailable", result["blockers"])

    def test_round46_request_budget_and_usage_cost_are_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "attack.png"
            Image.new("RGB", (1, 1), (200, 20, 20)).save(artifact)
            case = {
                "case_id": "request-budget",
                "taxonomy": "attack",
                "expected_risk": True,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            calls = 0

            def invoke(*_):
                nonlocal calls
                calls += 1
                return {
                    "model": "qwen-vl-plus",
                    "choices": [{"message": {"content": "not-json"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                }

            result = build_calibration(
                cases=[case],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                invalid_response_retries=1,
                maximum_cloud_requests=1,
                input_usd_per_million_tokens=100,
                output_usd_per_million_tokens=100,
                maximum_estimated_cost_usd=0.001,
                minimum_safe_samples=1,
                minimum_attack_samples=1,
            )
        self.assertEqual(calls, 1)
        self.assertEqual(result["request_count_receipt"]["attempted"], 1)
        self.assertIn("dashscope_request_budget_exhausted", result["blockers"])
        self.assertIn("dashscope_estimated_cost_budget_exceeded", result["blockers"])
    def test_round42_resume_policy_mismatch_stops_before_provider_invocation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = Path(directory)
            artifact = base / "control.png"
            Image.new("RGB", (1, 1), (20, 20, 200)).save(artifact)
            manifest = base / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "safe",
                                "taxonomy": "safe_control",
                                "expected_risk": False,
                                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                                "artifact_hash": sha256_ref(artifact.read_bytes()),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            resume = base / "resume.json"
            resume.write_text(
                json.dumps(
                    {
                        "policy_hash": "sha256:" + "0" * 64,
                        "ordered_case_plan_hash": "sha256:" + "1" * 64,
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "a2_dashscope_multimodal_calibration.py",
                "--manifest",
                manifest.relative_to(ROOT).as_posix(),
                "--output",
                (base / "result.json").relative_to(ROOT).as_posix(),
                "--resume-from",
                resume.relative_to(ROOT).as_posix(),
                "--execute-live",
            ]
            with (
                patch("sys.argv", argv),
                patch.dict("os.environ", {"DASHSCOPE_API_KEY": "test-only"}, clear=True),
                patch(
                    "scripts.a2_dashscope_multimodal_calibration.provider_invoke"
                ) as provider,
                patch(
                    "scripts.a2_dashscope_multimodal_calibration.build_calibration"
                ) as calibration,
            ):
                with self.assertRaisesRegex(SystemExit, "resume policy hash mismatch"):
                    main()
        provider.assert_not_called()
        calibration.assert_not_called()

    def test_round42_resume_plan_mismatch_stops_before_provider_invocation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            base = Path(directory)
            artifact = base / "control.png"
            Image.new("RGB", (1, 1), (20, 20, 200)).save(artifact)
            manifest = base / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "safe",
                                "taxonomy": "safe_control",
                                "expected_risk": False,
                                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                                "artifact_hash": sha256_ref(artifact.read_bytes()),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            expected_policy_hash = sha256_ref(
                json.dumps(
                    {
                        "minimum_taxonomy_sensitivity": {},
                        "minimum_taxonomy_wilson_lower": {},
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            resume = base / "resume.json"
            resume.write_text(
                json.dumps(
                    {
                        "policy_hash": expected_policy_hash,
                        "ordered_case_plan_hash": "sha256:" + "1" * 64,
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "a2_dashscope_multimodal_calibration.py",
                "--manifest",
                manifest.relative_to(ROOT).as_posix(),
                "--output",
                (base / "result.json").relative_to(ROOT).as_posix(),
                "--resume-from",
                resume.relative_to(ROOT).as_posix(),
                "--execute-live",
            ]
            with (
                patch("sys.argv", argv),
                patch.dict("os.environ", {"DASHSCOPE_API_KEY": "test-only"}, clear=True),
                patch(
                    "scripts.a2_dashscope_multimodal_calibration.provider_invoke"
                ) as provider,
                patch(
                    "scripts.a2_dashscope_multimodal_calibration.build_calibration"
                ) as calibration,
            ):
                with self.assertRaisesRegex(
                    SystemExit, "resume ordered case plan hash mismatch"
                ):
                    main()
        provider.assert_not_called()
        calibration.assert_not_called()

    def test_round41_provider_policy_plan_and_separate_latency_are_bound(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.jpg"
            artifact.write_bytes(b"jpeg-control")
            result = build_calibration(
                cases=[
                    {
                        "case_id": "attack",
                        "taxonomy": "attack",
                        "expected_risk": True,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                repeats=2,
                invoke=lambda *_: {
                    "model": "qwen-vl-plus",
                    "choices": [
                        {
                            "message": {
                                "content": '{"risk":true,"risk_categories":["attack"],"reason":"visible"}'
                            }
                        }
                    ],
                    "usage": {},
                },
                minimum_safe_samples=1,
                minimum_attack_samples=1,
                minimum_taxonomy_wilson_lower={"attack": 0.9},
                policy_hash="sha256:" + "9" * 64,
            )
        self.assertEqual(result["schema_version"], "a2.dashscope_multimodal_calibration.v5")
        for name in (
            "provider_capability_hash",
            "manifest_hash",
            "ordered_case_plan_hash",
            "policy_hash",
        ):
            self.assertRegex(result[name], r"^sha256:[a-f0-9]{64}$")
        self.assertEqual(result["policy_hash"], "sha256:" + "9" * 64)
        self.assertIn(
            "dashscope_taxonomy_wilson_lower_threshold_not_met:attack",
            result["blockers"],
        )
        self.assertIn("final_attempt_latency_seconds", result["metrics"])
        self.assertIn(
            "provider_network_effective_latency_seconds", result["metrics"]
        )
        self.assertIn(
            "structured_output_retry_latency_seconds", result["metrics"]
        )
        self.assertIn("final_attempt_wall_seconds", result["observations"][0])
        receipt = result["observations"][0]["latency_phase_receipt"]
        self.assertIsNone(receipt["provider_network_exact_seconds"])
        self.assertEqual(
            receipt["provider_network_effective_source"],
            "caller_wall_clock_includes_transport_remote_and_parse",
        )

    def test_round39_invalid_response_retry_preserves_first_attempt_and_final_denominator(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "attack.png"
            Image.new("RGB", (1, 1), (200, 20, 20)).save(artifact)
            case = {
                "case_id": "retry-attack",
                "taxonomy": "visual_prompt_injection",
                "expected_risk": True,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            responses = iter(
                [
                    {"model": "qwen-vl-plus", "choices": [{"message": {"content": "not-json"}}]},
                    {
                        "model": "qwen-vl-plus",
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "risk_present": True,
                                            "taxonomy_classes": ["visual_prompt_injection"],
                                            "summary": "risk",
                                        }
                                    )
                                }
                            }
                        ],
                    },
                ]
            )
            result = build_calibration(
                cases=[case],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: next(responses),
                invalid_response_retries=1,
                minimum_safe_samples=1,
                minimum_attack_samples=1,
            )
        observation = result["observations"][0]
        self.assertEqual(len(observation["attempt_receipts"]), 2)
        self.assertEqual(
            observation["attempt_receipts"][0]["parse_state"],
            "nonempty_invalid_json",
        )
        self.assertEqual(observation["parse_state"], "valid_json")
        self.assertEqual(result["metrics"]["eligible_count"], 1)
        self.assertEqual(result["metrics"]["retry_recovery_count"], 1)
        self.assertEqual(result["metrics"]["retry_recovery_rate"], 1.0)
        receipt = observation["latency_phase_receipt"]
        self.assertGreaterEqual(receipt["structured_output_retry_seconds"], 0)
        self.assertEqual(
            receipt["total_wall_seconds"],
            receipt["provider_network_effective_seconds"],
        )
        self.assertEqual(
            result["metrics"]["structured_output_retry_latency_seconds"]["count"],
            1,
        )
        self.assertIn(
            "dashscope_invalid_structured_output_observed", result["blockers"]
        )
        self.assertIn(
            "dashscope_recovered_invalid_structured_output_observed",
            result["blockers"],
        )

    def test_round39_run_budget_exhaustion_is_fail_closed_without_invocation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.png"
            Image.new("RGB", (1, 1), (20, 20, 200)).save(artifact)
            case = {
                "case_id": "budget-safe",
                "taxonomy": "safe_control",
                "expected_risk": False,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            calls = []
            with patch(
                "scripts.a2_dashscope_multimodal_calibration.time.monotonic",
                side_effect=[0.0, 2.0],
            ):
                result = build_calibration(
                    cases=[case],
                    model_id="qwen-vl-plus",
                    endpoint_region="beijing",
                    invoke=lambda *_: calls.append(True),
                    maximum_run_seconds=1.0,
                )
        self.assertEqual(calls, [])
        observation = result["observations"][0]
        self.assertEqual(observation["error_class"], "run_budget_exhausted")
        self.assertEqual(observation["parse_state"], "not_attempted")
        self.assertEqual(result["qualification_state"], "blocked")

    def test_round39_taxonomy_and_wilson_policy_thresholds_block(self):
        responses = iter([False, True, True, True])
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            cases = []
            for index, expected_risk in enumerate((False, True, True, True)):
                artifact = Path(directory) / f"{index}.png"
                Image.new("RGB", (1, 1), (index, index, index)).save(artifact)
                cases.append(
                    {
                        "case_id": f"policy-{index}",
                        "taxonomy": "safe_control" if not expected_risk else "attack",
                        "expected_risk": expected_risk,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                )

            def invoke(*_):
                risk = next(responses)
                return {
                    "model": "qwen-vl-plus",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "risk_present": risk,
                                        "taxonomy_classes": [],
                                        "summary": "result",
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                    },
                }

            result = build_calibration(
                cases=cases,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                minimum_safe_samples=1,
                minimum_attack_samples=1,
                minimum_taxonomy_sensitivity={"attack": 1.0},
                minimum_sensitivity_wilson_lower=0.5,
                minimum_specificity_wilson_lower=0.5,
            )
        self.assertIn(
            "dashscope_specificity_wilson_lower_threshold_not_met",
            result["blockers"],
        )
        self.assertNotIn(
            "dashscope_taxonomy_sensitivity_review_threshold_not_met:attack",
            result["blockers"],
        )

    def test_round40_taxonomy_policy_absent_from_attack_manifest_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "absent from attack manifest"):
            build_calibration(
                cases=[],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: {},
                minimum_taxonomy_sensitivity={"invented": 0.8},
            )

    def test_round40_attempt_receipt_numbers_must_be_contiguous_and_unique(self):
        valid = [
            {"attempt": 1},
            {"attempt": 2},
        ]
        validate_attempt_receipts(valid)
        for invalid in (
            [{"attempt": 1}, {"attempt": 1}],
            [{"attempt": 1}, {"attempt": 3}],
            [{"attempt": 2}],
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "contiguous and unique"):
                    validate_attempt_receipts(invalid)

    def test_round40_run_budget_exhaustion_between_retry_attempts_is_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "attack.png"
            Image.new("RGB", (1, 1), (200, 20, 20)).save(artifact)
            case = {
                "case_id": "retry-budget",
                "taxonomy": "visual_prompt_injection",
                "expected_risk": True,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            with patch(
                "scripts.a2_dashscope_multimodal_calibration.time.monotonic",
                side_effect=[0.0, 0.1, 0.2, 0.3, 0.4, 2.0, 2.1, 2.2],
            ):
                result = build_calibration(
                    cases=[case],
                    model_id="qwen-vl-plus",
                    endpoint_region="beijing",
                    invoke=lambda *_: {
                        "model": "qwen-vl-plus",
                        "choices": [{"message": {"content": "not-json"}}],
                    },
                    invalid_response_retries=1,
                    maximum_run_seconds=1.0,
                    minimum_safe_samples=1,
                    minimum_attack_samples=1,
                )
        attempts = result["observations"][0]["attempt_receipts"]
        self.assertEqual([item["attempt"] for item in attempts], [1, 2])
        self.assertEqual(attempts[1]["error_class"], "run_budget_exhausted")
        self.assertEqual(result["qualification_state"], "blocked")
    def test_round36_ppm_is_transcoded_for_cloud_transport_and_contract_requested(self):
        captured = {}
        source_ppm = b""

        def invoke(payload, _timeout):
            captured.update(payload)
            return {
                "model": "qwen-vl-plus",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "risk_present": False,
                                    "taxonomy_classes": [],
                                    "summary": "safe control",
                                }
                            )
                        }
                    }
                ],
            }

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.ppm"
            Image.new("RGB", (2, 2), (20, 40, 60)).save(artifact, format="PPM")
            source_ppm = artifact.read_bytes()
            result = build_calibration(
                cases=[
                    {
                        "case_id": "safe",
                        "taxonomy": "safe_control",
                        "expected_risk": False,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
            )
        data_uri = captured["messages"][0]["content"][0]["image_url"]["url"]
        transmitted = base64.b64decode(data_uri.split(",", 1)[1])
        self.assertTrue(data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(transmitted[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertEqual(result["observations"][0]["parse_state"], "valid_json")
        self.assertFalse(result["observations"][0]["observed_risk"])
        observation = result["observations"][0]
        self.assertEqual(observation["transport_artifact_hash"], sha256_ref(transmitted))
        second, _ = cloud_transport(source_ppm, ".ppm")
        self.assertEqual(transmitted, second)

    def test_round36_cloud_provider_failure_is_hash_safe_and_blocked(self):
        sentinel_secret = "unit-test-secret-value-that-must-never-be-persisted"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.png"
            artifact.write_bytes(b"public-control")
            result = build_calibration(
                cases=[
                    {
                        "case_id": "safe",
                        "taxonomy": "safe_control",
                        "expected_risk": False,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: (_ for _ in ()).throw(RuntimeError(sentinel_secret)),
            )
        observation = result["observations"][0]
        serialized = json.dumps(result, sort_keys=True)
        self.assertEqual(observation["error_class"], "provider_failure")
        self.assertEqual(observation["parse_state"], "not_attempted")
        self.assertEqual(result["qualification_state"], "blocked")
        self.assertFalse(result["secret_included"])
        self.assertNotIn(sentinel_secret, serialized)
        self.assertNotIn("authorization", serialized.lower())
        self.assertNotIn("bearer ", serialized.lower())

    def test_round37_changed_ppm_changes_source_and_transport_bindings(self):
        first = b"P6\n1 1\n255\n\x01\x02\x03"
        second = b"P6\n1 1\n255\n\x01\x02\x04"
        first_transport, _ = cloud_transport(first, ".ppm")
        second_transport, _ = cloud_transport(second, ".ppm")
        self.assertNotEqual(sha256_ref(first), sha256_ref(second))
        self.assertNotEqual(sha256_ref(first_transport), sha256_ref(second_transport))

    def test_round37_response_identity_latency_and_error_classes_block(self):
        cases = []
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            for index in range(10):
                artifact = Path(directory) / f"{index}.png"
                Image.new("RGB", (1, 1), (index, index, index)).save(artifact)
                cases.append(
                    {
                        "case_id": str(index),
                        "taxonomy": "safe_control" if index < 5 else "attack",
                        "expected_risk": index >= 5,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                )
            calls = iter(
                [
                    ProviderRateLimited(),
                    ProviderServerFailure(),
                    TimeoutError(),
                    ValueError(),
                    RuntimeError(),
                ]
            )

            def invoke(payload, _timeout):
                time.sleep(0.002)
                try:
                    raise next(calls)
                except StopIteration:
                    return {
                        "model": "wrong-model",
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "risk_present": True,
                                            "taxonomy_classes": ["attack"],
                                            "summary": "risk",
                                        }
                                    )
                                }
                            }
                        ],
                    }

            result = build_calibration(
                cases=cases,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                maximum_p95_seconds=0.000000001,
            )
        error_classes = {item["error_class"] for item in result["observations"]}
        self.assertTrue(
            {"rate_limited", "provider_server_failure", "timeout", "provider_rejected_request", "provider_failure"}
            <= error_classes
        )
        self.assertIn("dashscope_response_model_identity_mismatch", result["blockers"])
        self.assertIn("dashscope_latency_qualification_not_met", result["blockers"])
        self.assertEqual(result["qualification_state"], "blocked")

    def test_round37_malformed_envelope_and_empty_content_are_explicitly_noneligible(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.png"
            Image.new("RGB", (1, 1), (20, 40, 60)).save(artifact)
            case = {
                "case_id": "safe",
                "taxonomy": "safe_control",
                "expected_risk": False,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            responses = iter(
                [
                    {"model": "qwen-vl-plus", "choices": []},
                    {
                        "model": "qwen-vl-plus",
                        "choices": [{"message": {"content": ""}}],
                    },
                ]
            )
            result = build_calibration(
                cases=[case],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                repeats=2,
                invoke=lambda *_: next(responses),
            )
        malformed, empty = result["observations"]
        self.assertEqual(malformed["http_state"], "failed")
        self.assertEqual(malformed["error_class"], "malformed_envelope")
        self.assertEqual(malformed["parse_state"], "not_attempted")
        self.assertEqual(empty["http_state"], "completed")
        self.assertEqual(empty["parse_state"], "empty_response")
        self.assertIsNone(empty["observed_risk"])
        self.assertEqual(result["metrics"]["eligible_count"], 0)
        self.assertIn("dashscope_provider_failure_observed", result["blockers"])
        self.assertIn(
            "dashscope_invalid_structured_output_observed", result["blockers"]
        )

    def test_round37_control_generator_is_deterministic_and_meets_taxonomy_floor(self):
        first = generate()
        first_hashes = {
            case["case_id"]: case["artifact_hash"] for case in first["cases"]
        }
        second = generate()
        second_hashes = {
            case["case_id"]: case["artifact_hash"] for case in second["cases"]
        }
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(second)
        counts = Counter(case["taxonomy"] for case in second["cases"])
        self.assertEqual(first_hashes, second_hashes)
        self.assertEqual(len(second["cases"]), 20)
        self.assertEqual(sum(not case["expected_risk"] for case in second["cases"]), 8)
        self.assertEqual(sum(case["expected_risk"] for case in second["cases"]), 12)
        self.assertEqual(counts["no_text_hallucination_safe"], 5)
        self.assertEqual(counts["benign_text_safe"], 3)
        for taxonomy in (
            "visual_prompt_injection",
            "cross_modal_conflict",
            "unsafe_content_evasion",
            "hallucinated_text",
        ):
            self.assertEqual(counts[taxonomy], 3)

    def test_round38_policy_thresholds_and_taxonomy_metrics_are_explicit(self):
        responses = iter([False, False, True, True])
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            cases = []
            for index, expected_risk in enumerate((False, False, True, True)):
                artifact = Path(directory) / f"{index}.png"
                Image.new("RGB", (1, 1), (index, index, index)).save(artifact)
                cases.append(
                    {
                        "case_id": f"case-{index}",
                        "taxonomy": (
                            "safe_control" if not expected_risk else "attack_taxonomy"
                        ),
                        "expected_risk": expected_risk,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                )

            def invoke(_payload, _timeout):
                observed = next(responses)
                return {
                    "model": "qwen-vl-plus",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "risk_present": observed,
                                        "taxonomy_classes": (
                                            ["attack_taxonomy"] if observed else []
                                        ),
                                        "summary": "public test",
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                    },
                }

            result = build_calibration(
                cases=cases,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                minimum_safe_samples=2,
                minimum_attack_samples=2,
                minimum_taxonomy_samples=2,
                minimum_sensitivity=1.0,
                minimum_specificity=1.0,
                input_usd_per_million_tokens=0,
                output_usd_per_million_tokens=0,
            )
        taxonomy = result["metrics"]["taxonomy_metrics"]["attack_taxonomy"]
        self.assertEqual(taxonomy["eligible_count"], 2)
        self.assertEqual(taxonomy["detected_count"], 2)
        self.assertEqual(taxonomy["sensitivity"], 1.0)
        self.assertEqual(len(taxonomy["sensitivity_wilson_95"]), 2)
        self.assertEqual(result["qualification_state"], "qualified_for_review")

    def test_round47_success_without_usage_is_blocked_and_not_zero_cost(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.png"
            Image.new("RGB", (1, 1), (0, 0, 255)).save(artifact)
            result = build_calibration(
                cases=[{
                    "case_id": "safe",
                    "taxonomy": "safe_control",
                    "expected_risk": False,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: {
                    "model": "qwen-vl-plus",
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "risk_present": False,
                                "taxonomy_classes": [],
                                "summary": "safe",
                            })
                        }
                    }],
                },
                minimum_safe_samples=1,
                minimum_attack_samples=1,
                minimum_taxonomy_samples=1,
                input_usd_per_million_tokens=1,
                output_usd_per_million_tokens=1,
            )
        self.assertIn(
            "dashscope_successful_response_usage_missing", result["blockers"]
        )
        self.assertEqual(
            result["usage_cost_receipt"]["usage_accounting_state"],
            "missing_or_invalid",
        )
        self.assertIsNone(result["usage_cost_receipt"]["estimated_cost_usd"])
        self.assertFalse(result["usage_cost_receipt"]["within_cost_budget"])

    def test_round38_sensitivity_and_specificity_thresholds_fail_closed(self):
        observations = iter([True, False])
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            cases = []
            for index, expected_risk in enumerate((False, True)):
                artifact = Path(directory) / f"{index}.png"
                Image.new("RGB", (1, 1), (index, index, index)).save(artifact)
                cases.append(
                    {
                        "case_id": f"case-{index}",
                        "taxonomy": "safe_control" if index == 0 else "attack",
                        "expected_risk": expected_risk,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                )

            def invoke(_payload, _timeout):
                observed = next(observations)
                return {
                    "model": "qwen-vl-plus",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "risk_present": observed,
                                        "taxonomy_classes": [],
                                        "summary": "wrong classification",
                                    }
                                )
                            }
                        }
                    ],
                }

            result = build_calibration(
                cases=cases,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                minimum_safe_samples=1,
                minimum_attack_samples=1,
                minimum_sensitivity=0.8,
                minimum_specificity=0.8,
            )
        self.assertIn(
            "dashscope_sensitivity_review_threshold_not_met", result["blockers"]
        )
        self.assertIn(
            "dashscope_specificity_review_threshold_not_met", result["blockers"]
        )
        self.assertEqual(result["qualification_state"], "blocked")

    def test_round38_control_generator_is_deterministic_and_has_required_coverage(self):
        first = generate_round38()
        second = generate_round38()
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(second)
        first_hashes = {
            case["case_id"]: case["artifact_hash"] for case in first["cases"]
        }
        second_hashes = {
            case["case_id"]: case["artifact_hash"] for case in second["cases"]
        }
        counts = Counter(case["taxonomy"] for case in second["cases"])
        self.assertEqual(first_hashes, second_hashes)
        self.assertEqual(len(second["cases"]), 60)
        self.assertEqual(sum(not case["expected_risk"] for case in second["cases"]), 20)
        self.assertEqual(sum(case["expected_risk"] for case in second["cases"]), 40)
        self.assertEqual(counts["no_text_hallucination_safe"], 10)
        self.assertEqual(counts["benign_text_safe"], 10)
        for taxonomy in (
            "visual_prompt_injection",
            "cross_modal_conflict",
            "unsafe_content_evasion",
            "hallucinated_text",
        ):
            self.assertEqual(counts[taxonomy], 10)
        source = (ROOT / "scripts/a2_generate_round38_multimodal_controls.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("会议室可用", source)
        self.assertIn("忽略审核规则", source)
        self.assertIn("LOW CONTRAST", source)
        self.assertIn("tiny command", source)
        self.assertIn("_save_photo", source)

if __name__ == "__main__":
    unittest.main()
