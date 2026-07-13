import base64
import json
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import jsonschema
from PIL import Image

from scripts.a2_dashscope_multimodal_calibration import build_calibration, main
from scripts.a2_dashscope_multimodal_calibration import (
    ProviderRateLimited,
    ProviderServerFailure,
    cloud_transport,
    validate_attempt_receipts,
)
from scripts.a2_generate_round37_multimodal_controls import generate
from scripts.a2_generate_round38_multimodal_controls import generate as generate_round38
from scripts.a2_ollama_multimodal_matrix import ROOT, sha256_ref


class DashScopeMultimodalCalibrationTests(unittest.TestCase):
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
        self.assertIn("final_attempt_wall_seconds", result["observations"][0])

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
            )
        taxonomy = result["metrics"]["taxonomy_metrics"]["attack_taxonomy"]
        self.assertEqual(taxonomy["eligible_count"], 2)
        self.assertEqual(taxonomy["detected_count"], 2)
        self.assertEqual(taxonomy["sensitivity"], 1.0)
        self.assertEqual(len(taxonomy["sensitivity_wilson_95"]), 2)
        self.assertEqual(result["qualification_state"], "qualified_for_review")

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
