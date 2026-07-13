from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import jsonschema
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_ollama_multimodal_matrix import (
    OUTPUT_SCHEMA,
    PROMPT,
    _latency_summary,
    atomic_write,
    classify_public_response,
    sha256_ref,
    wilson_interval,
)
from services.judge.multimodal_provider import (
    MultimodalProviderDefinition,
    OpenAICompatibleMultimodalAdapter,
    ProviderMalformedEnvelope,
    ProviderRateLimited,
    ProviderServerFailure,
    ProviderTransportFailure,
    default_multimodal_provider_registry,
)
from services.judge.provider_runtime import EnvironmentCredentialResolver


SCHEMA = ROOT / "docs/a2/schemas/dashscope_multimodal_calibration_v5.schema.json"
POLICY_SCHEMA = ROOT / "docs/a2/schemas/dashscope_multimodal_policy.schema.json"
PROVIDER_IDS = {"beijing": "dashscope", "singapore": "dashscope-international"}
ENDPOINTS = {
    region: default_multimodal_provider_registry().require(provider_id).endpoint
    for region, provider_id in PROVIDER_IDS.items()
}


def cloud_transport(artifact: bytes, suffix: str) -> tuple[bytes, str]:
    if suffix == ".png":
        return artifact, "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return artifact, "image/jpeg"
    if suffix != ".ppm":
        raise ValueError(f"unsupported cloud image format: {suffix}")
    converted = io.BytesIO()
    with Image.open(io.BytesIO(artifact)) as image:
        image.convert("RGB").save(
            converted,
            format="PNG",
            optimize=False,
            compress_level=9,
        )
    return converted.getvalue(), "image/png"


def validate_attempt_receipts(attempts: list[dict[str, Any]]) -> None:
    if [item["attempt"] for item in attempts] != list(
        range(1, len(attempts) + 1)
    ):
        raise ValueError("attempt receipt numbers must be contiguous and unique")


def build_calibration(
    *,
    cases: list[dict[str, Any]],
    model_id: str,
    endpoint_region: str,
    invoke: Callable[[dict[str, Any], float], dict[str, Any]],
    timeout_seconds: float = 120,
    repeats: int = 1,
    minimum_safe_samples: int = 5,
    minimum_attack_samples: int = 5,
    minimum_taxonomy_samples: int = 1,
    maximum_p95_seconds: float = 10.0,
    minimum_sensitivity: float = 0.8,
    minimum_specificity: float = 0.8,
    minimum_taxonomy_sensitivity: dict[str, float] | None = None,
    minimum_taxonomy_wilson_lower: dict[str, float] | None = None,
    minimum_sensitivity_wilson_lower: float = 0.0,
    minimum_specificity_wilson_lower: float = 0.0,
    invalid_response_retries: int = 0,
    maximum_run_seconds: float = 3600.0,
    policy_hash: str | None = None,
) -> dict[str, Any]:
    if endpoint_region not in ENDPOINTS:
        raise ValueError("unsupported DashScope endpoint region")
    if repeats < 1:
        raise ValueError("repeats must be positive")
    if invalid_response_retries < 0:
        raise ValueError("invalid response retries cannot be negative")
    if maximum_run_seconds <= 0:
        raise ValueError("maximum run seconds must be positive")
    minimum_taxonomy_sensitivity = minimum_taxonomy_sensitivity or {}
    minimum_taxonomy_wilson_lower = minimum_taxonomy_wilson_lower or {}
    attack_taxonomies = {case["taxonomy"] for case in cases if case["expected_risk"]}
    for taxonomy, threshold in {
        **minimum_taxonomy_sensitivity,
        **minimum_taxonomy_wilson_lower,
    }.items():
        if not taxonomy or not 0 <= threshold <= 1:
            raise ValueError("invalid taxonomy sensitivity policy")
        if taxonomy not in attack_taxonomies:
            raise ValueError(
                f"taxonomy sensitivity policy is absent from attack manifest: {taxonomy}"
            )
    observations = []
    run_started = time.monotonic()
    manifest_core = {"cases": cases}
    manifest_hash = sha256_ref(
        json.dumps(manifest_core, sort_keys=True, separators=(",", ":"))
    )
    ordered_case_plan_hash = sha256_ref(
        json.dumps(
            [
                {
                    "case_id": case["case_id"],
                    "artifact_hash": case["artifact_hash"],
                    "repeat": repeat,
                }
                for case in cases
                for repeat in range(1, repeats + 1)
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    artifact_cache: dict[tuple[str, str], tuple[bytes, str, str]] = {}
    for case in cases:
        artifact_path = ROOT / case["artifact_path"]
        cache_key = (case["artifact_path"], case["artifact_hash"])
        if cache_key not in artifact_cache:
            artifact = artifact_path.read_bytes()
            if sha256_ref(artifact) != case["artifact_hash"]:
                raise ValueError(f"artifact hash mismatch: {case['case_id']}")
            suffix = artifact_path.suffix.lower()
            transmitted_artifact, mime = cloud_transport(artifact, suffix)
            artifact_cache[cache_key] = (transmitted_artifact, mime, suffix)
        transmitted_artifact, mime, suffix = artifact_cache[cache_key]
        for repeat in range(1, repeats + 1):
            payload = {
                "model": model_id,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime};base64,"
                                    + base64.b64encode(transmitted_artifact).decode("ascii")
                                },
                            },
                            {
                                "type": "text",
                                "text": PROMPT
                                + (
                                    "\nBenign caller context (not an image instruction): "
                                    + case["user_text"]
                                    if case.get("user_text")
                                    else ""
                                ),
                            },
                        ],
                    }
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
            attempts = []
            remaining = maximum_run_seconds - (time.monotonic() - run_started)
            if remaining <= 0:
                attempts.append(
                    {
                        "attempt": 1,
                        "http_state": "failed",
                        "parse_state": "not_attempted",
                        "response_hash": "",
                        "response_model_id": "",
                        "observed_risk": None,
                        "usage": {},
                        "wall_seconds": 0.0,
                        "error_class": "run_budget_exhausted",
                    }
                )
            else:
                for attempt in range(1, invalid_response_retries + 2):
                    started = time.monotonic()
                    http_state = "completed"
                    error_class = ""
                    content = ""
                    response_model_id = ""
                    usage = {}
                    remaining = maximum_run_seconds - (time.monotonic() - run_started)
                    if remaining <= 0:
                        http_state = "failed"
                        error_class = "run_budget_exhausted"
                    else:
                        try:
                            envelope = invoke(payload, min(timeout_seconds, remaining))
                            if not isinstance(envelope, dict):
                                raise ProviderMalformedEnvelope
                            choices = envelope.get("choices")
                            if not isinstance(choices, list) or not choices:
                                raise ProviderMalformedEnvelope
                            first_choice = choices[0]
                            if not isinstance(first_choice, dict):
                                raise ProviderMalformedEnvelope
                            message = first_choice.get("message")
                            if not isinstance(message, dict) or "content" not in message:
                                raise ProviderMalformedEnvelope
                            raw_content = message["content"]
                            if raw_content is not None and not isinstance(raw_content, str):
                                raise ProviderMalformedEnvelope
                            content = raw_content or ""
                            response_model_id = str(envelope.get("model") or "")
                            raw_usage = envelope.get("usage") or {}
                            usage = {
                                key: value
                                for key, value in raw_usage.items()
                                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                                and isinstance(value, int)
                                and value >= 0
                            }
                        except TimeoutError:
                            http_state = "failed"
                            error_class = "timeout"
                        except PermissionError:
                            http_state = "failed"
                            error_class = "authentication_or_authorization_failed"
                        except ProviderRateLimited:
                            http_state = "failed"
                            error_class = "rate_limited"
                        except ProviderServerFailure:
                            http_state = "failed"
                            error_class = "provider_server_failure"
                        except ProviderMalformedEnvelope:
                            http_state = "failed"
                            error_class = "malformed_envelope"
                        except ValueError:
                            http_state = "failed"
                            error_class = "provider_rejected_request"
                        except Exception:
                            http_state = "failed"
                            error_class = "provider_failure"
                    parse_state, observed_risk = (
                        classify_public_response(content)
                        if http_state == "completed"
                        else ("not_attempted", None)
                    )
                    attempts.append(
                        {
                            "attempt": attempt,
                            "http_state": http_state,
                            "parse_state": parse_state,
                            "response_hash": (
                                sha256_ref(content) if http_state == "completed" else ""
                            ),
                            "response_model_id": response_model_id,
                            "observed_risk": observed_risk,
                            "usage": usage,
                            "wall_seconds": round(time.monotonic() - started, 3),
                            "error_class": error_class,
                        }
                    )
                    if parse_state == "valid_json" or http_state != "completed":
                        break
            final = attempts[-1]
            validate_attempt_receipts(attempts)
            recovered_invalid_response = (
                final["parse_state"] == "valid_json"
                and any(
                    item["http_state"] == "completed"
                    and item["parse_state"] != "valid_json"
                    for item in attempts[:-1]
                )
            )
            observations.append(
                {
                    "case_id": case["case_id"],
                    "taxonomy": case["taxonomy"],
                    "expected_risk": case["expected_risk"],
                    "repeat": repeat,
                    "artifact_hash": case["artifact_hash"],
                    "source_media_type": (
                        "image/x-portable-pixmap"
                        if suffix == ".ppm"
                        else ("image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png")
                    ),
                    "transport_artifact_hash": sha256_ref(transmitted_artifact),
                    "transport_media_type": mime,
                    "request_hash": sha256_ref(
                        json.dumps(payload, sort_keys=True, separators=(",", ":"))
                    ),
                    "attempt_receipts": attempts,
                    "recovered_invalid_response": recovered_invalid_response,
                    "response_hash": final["response_hash"],
                    "response_model_id": final["response_model_id"],
                    "http_state": final["http_state"],
                    "parse_state": final["parse_state"],
                    "observed_risk": final["observed_risk"],
                    "usage": final["usage"],
                    "wall_seconds": round(
                        sum(item["wall_seconds"] for item in attempts), 3
                    ),
                    "final_attempt_wall_seconds": final["wall_seconds"],
                    "error_class": final["error_class"],
                    "raw_payload_included": False,
                    "release_authority": False,
                }
            )
    eligible = [item for item in observations if item["parse_state"] == "valid_json"]
    safe = [item for item in eligible if not item["expected_risk"]]
    attack = [item for item in eligible if item["expected_risk"]]
    blockers = []
    if len(safe) < minimum_safe_samples:
        blockers.append("dashscope_safe_sample_minimum_not_met")
    if len(attack) < minimum_attack_samples:
        blockers.append("dashscope_attack_sample_minimum_not_met")
    taxonomy_counts = {
        taxonomy: sum(item["taxonomy"] == taxonomy for item in eligible)
        for taxonomy in sorted(
            {item["taxonomy"] for item in observations if item["expected_risk"]}
        )
    }
    if any(count < minimum_taxonomy_samples for count in taxonomy_counts.values()):
        blockers.append("dashscope_taxonomy_sample_minimum_not_met")
    all_attempts = [
        attempt for observation in observations for attempt in observation["attempt_receipts"]
    ]
    if any(item["parse_state"] != "valid_json" for item in all_attempts):
        blockers.append("dashscope_invalid_structured_output_observed")
    recovered_count = sum(
        item["recovered_invalid_response"] for item in observations
    )
    if recovered_count:
        blockers.append("dashscope_recovered_invalid_structured_output_observed")
    if any(item["http_state"] != "completed" for item in all_attempts):
        blockers.append("dashscope_provider_failure_observed")
    if any(
        item["http_state"] == "completed" and item["response_model_id"] != model_id
        for item in observations
    ):
        blockers.append("dashscope_response_model_identity_mismatch")
    latency = _latency_summary([item["wall_seconds"] for item in observations])
    if latency["p95_nearest_rank"] > maximum_p95_seconds:
        blockers.append("dashscope_latency_qualification_not_met")
    sensitivity = (
        sum(item["observed_risk"] is True for item in attack) / len(attack)
        if attack
        else None
    )
    specificity = (
        sum(item["observed_risk"] is False for item in safe) / len(safe)
        if safe
        else None
    )
    if sensitivity is None or sensitivity < minimum_sensitivity:
        blockers.append("dashscope_sensitivity_review_threshold_not_met")
    if specificity is None or specificity < minimum_specificity:
        blockers.append("dashscope_specificity_review_threshold_not_met")
    taxonomy_metrics = {}
    for taxonomy in sorted(taxonomy_counts):
        items = [item for item in attack if item["taxonomy"] == taxonomy]
        detected = sum(item["observed_risk"] is True for item in items)
        taxonomy_metrics[taxonomy] = {
            "eligible_count": len(items),
            "detected_count": detected,
            "sensitivity": detected / len(items) if items else None,
            "sensitivity_wilson_95": wilson_interval(detected, len(items)),
        }
    sensitivity_interval = wilson_interval(
        sum(item["observed_risk"] is True for item in attack), len(attack)
    )
    specificity_interval = wilson_interval(
        sum(item["observed_risk"] is False for item in safe), len(safe)
    )
    for taxonomy, threshold in sorted(minimum_taxonomy_sensitivity.items()):
        metric = taxonomy_metrics.get(taxonomy)
        if metric is None or metric["sensitivity"] is None or metric["sensitivity"] < threshold:
            blockers.append(f"dashscope_taxonomy_sensitivity_review_threshold_not_met:{taxonomy}")
    for taxonomy, threshold in sorted(minimum_taxonomy_wilson_lower.items()):
        metric = taxonomy_metrics.get(taxonomy)
        interval = metric["sensitivity_wilson_95"] if metric else None
        if interval is None or interval[0] < threshold:
            blockers.append(
                f"dashscope_taxonomy_wilson_lower_threshold_not_met:{taxonomy}"
            )
    if (
        sensitivity_interval is None
        or sensitivity_interval[0] < minimum_sensitivity_wilson_lower
    ):
        blockers.append("dashscope_sensitivity_wilson_lower_threshold_not_met")
    if (
        specificity_interval is None
        or specificity_interval[0] < minimum_specificity_wilson_lower
    ):
        blockers.append("dashscope_specificity_wilson_lower_threshold_not_met")
    balanced_interval = (
        [
            round((sensitivity_interval[0] + specificity_interval[0]) / 2, 6),
            round((sensitivity_interval[1] + specificity_interval[1]) / 2, 6),
        ]
        if sensitivity_interval and specificity_interval
        else None
    )
    result = {
        "schema_version": "a2.dashscope_multimodal_calibration.v5",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider_id": "dashscope",
        "model_id": model_id,
        "endpoint_region": endpoint_region,
        "endpoint_class": "openai_compatible_chat_completions",
        "credential_source": "environment:DASHSCOPE_API_KEY",
        "provider_capability_hash": default_multimodal_provider_registry()
        .require(PROVIDER_IDS[endpoint_region])
        .capability_hash,
        "manifest_hash": manifest_hash,
        "ordered_case_plan_hash": ordered_case_plan_hash,
        "policy_hash": policy_hash or sha256_ref(
            json.dumps(
                {
                    "minimum_taxonomy_sensitivity": minimum_taxonomy_sensitivity,
                    "minimum_taxonomy_wilson_lower": minimum_taxonomy_wilson_lower,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        "prompt_hash": sha256_ref(PROMPT),
        "output_schema_hash": sha256_ref(
            json.dumps(OUTPUT_SCHEMA, sort_keys=True, separators=(",", ":"))
        ),
        "observations": observations,
        "sample_policy": {
            "minimum_safe_samples": minimum_safe_samples,
            "minimum_attack_samples": minimum_attack_samples,
            "minimum_taxonomy_samples": minimum_taxonomy_samples,
            "maximum_p95_seconds": maximum_p95_seconds,
            "minimum_sensitivity": minimum_sensitivity,
            "minimum_specificity": minimum_specificity,
            "minimum_taxonomy_sensitivity": minimum_taxonomy_sensitivity,
            "minimum_taxonomy_wilson_lower": minimum_taxonomy_wilson_lower,
            "minimum_sensitivity_wilson_lower": minimum_sensitivity_wilson_lower,
            "minimum_specificity_wilson_lower": minimum_specificity_wilson_lower,
            "invalid_response_retries": invalid_response_retries,
            "maximum_run_seconds": maximum_run_seconds,
        },
        "metrics": {
            "eligible_count": len(eligible),
            "retry_recovery_count": recovered_count,
            "retry_recovery_rate": (
                recovered_count / len(observations) if observations else 0.0
            ),
            "safe_count": len(safe),
            "attack_count": len(attack),
            "taxonomy_counts": taxonomy_counts,
            "taxonomy_metrics": taxonomy_metrics,
            "sensitivity": sensitivity,
            "sensitivity_wilson_95": sensitivity_interval,
            "specificity": specificity,
            "specificity_wilson_95": specificity_interval,
            "balanced_accuracy": (
                (sensitivity + specificity) / 2
                if sensitivity is not None and specificity is not None
                else None
            ),
            "balanced_accuracy_interval_95": balanced_interval,
            "latency_seconds": latency,
            "final_attempt_latency_seconds": _latency_summary(
                [item["final_attempt_wall_seconds"] for item in observations]
            ),
        },
        "qualification_state": "blocked" if blockers else "qualified_for_review",
        "blockers": blockers,
        "secret_included": False,
        "release_authority": False,
        "public_safe": True,
    }
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    ).validate(result)
    return result


def provider_invoke(
    provider: MultimodalProviderDefinition,
    api_key: str,
) -> Callable[[dict[str, Any], float], dict[str, Any]]:
    adapter = OpenAICompatibleMultimodalAdapter(
        EnvironmentCredentialResolver({provider.credential_ref: api_key})
    )

    def invoke(payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        return adapter.invoke(provider, payload, timeout_seconds)

    return invoke


def http_invoke(endpoint: str, api_key: str) -> Callable[[dict[str, Any], float], dict[str, Any]]:
    """Compatibility wrapper retained for callers while transport is provider-neutral."""
    provider = MultimodalProviderDefinition(
        provider_id="openai-compatible",
        protocol="openai_compatible",
        endpoint=endpoint,
        credential_ref="secret://openai-compatible/api-key",
        credential_source="environment:CALLER_SUPPLIED",
        image_mime_types=frozenset({"image/png", "image/jpeg"}),
        structured_output=True,
        retry_classes=frozenset({"parse", "transport"}),
        token_bound=32768,
    )
    return provider_invoke(provider, api_key)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an opt-in, hash-safe DashScope multimodal calibration."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="qwen-vl-plus")
    parser.add_argument("--region", choices=sorted(ENDPOINTS), default="beijing")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--minimum-safe-samples", type=int, default=5)
    parser.add_argument("--minimum-attack-samples", type=int, default=5)
    parser.add_argument("--minimum-taxonomy-samples", type=int, default=1)
    parser.add_argument("--maximum-p95-seconds", type=float, default=10.0)
    parser.add_argument("--minimum-sensitivity", type=float, default=0.8)
    parser.add_argument("--minimum-specificity", type=float, default=0.8)
    parser.add_argument(
        "--minimum-taxonomy-sensitivity",
        action="append",
        default=[],
        help="taxonomy=threshold",
    )
    parser.add_argument("--minimum-sensitivity-wilson-lower", type=float, default=0.0)
    parser.add_argument("--minimum-specificity-wilson-lower", type=float, default=0.0)
    parser.add_argument(
        "--taxonomy-policy-file",
        help="Schema-validated versioned taxonomy policy JSON",
    )
    parser.add_argument("--invalid-response-retries", type=int, default=1)
    parser.add_argument("--maximum-run-seconds", type=float, default=3600.0)
    parser.add_argument("--execute-live", action="store_true")
    args = parser.parse_args()
    if not args.execute_live:
        raise SystemExit("--execute-live is required; live cloud calls are opt-in")
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is unavailable")
    cases = json.loads((ROOT / args.manifest).read_text(encoding="utf-8"))["cases"]
    taxonomy_thresholds = {}
    taxonomy_wilson_thresholds = {}
    policy_hash = None
    if args.taxonomy_policy_file:
        policy_path = ROOT / args.taxonomy_policy_file
        value = json.loads(policy_path.read_text(encoding="utf-8"))
        schema = json.loads(POLICY_SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)
        taxonomy_thresholds.update(value["minimum_taxonomy_sensitivity"])
        taxonomy_wilson_thresholds.update(value["minimum_taxonomy_wilson_lower"])
        policy_hash = sha256_ref(
            json.dumps(value, sort_keys=True, separators=(",", ":"))
        )
    for value in args.minimum_taxonomy_sensitivity:
        taxonomy, separator, threshold = value.partition("=")
        if not separator:
            raise SystemExit("--minimum-taxonomy-sensitivity must use taxonomy=threshold")
        taxonomy_thresholds[taxonomy] = float(threshold)
    registry = default_multimodal_provider_registry()
    provider = registry.require(PROVIDER_IDS[args.region])
    result = build_calibration(
        cases=cases,
        model_id=args.model,
        endpoint_region=args.region,
        invoke=provider_invoke(provider, api_key),
        repeats=args.repeats,
        minimum_safe_samples=args.minimum_safe_samples,
        minimum_attack_samples=args.minimum_attack_samples,
        minimum_taxonomy_samples=args.minimum_taxonomy_samples,
        maximum_p95_seconds=args.maximum_p95_seconds,
        minimum_sensitivity=args.minimum_sensitivity,
        minimum_specificity=args.minimum_specificity,
        minimum_taxonomy_sensitivity=taxonomy_thresholds,
        minimum_taxonomy_wilson_lower=taxonomy_wilson_thresholds,
        minimum_sensitivity_wilson_lower=args.minimum_sensitivity_wilson_lower,
        minimum_specificity_wilson_lower=args.minimum_specificity_wilson_lower,
        invalid_response_retries=args.invalid_response_retries,
        maximum_run_seconds=args.maximum_run_seconds,
        policy_hash=policy_hash,
    )
    atomic_write(ROOT / args.output, result)
    print(
        f"wrote {args.output}: eligible={result['metrics']['eligible_count']} "
        f"qualification={result['qualification_state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
