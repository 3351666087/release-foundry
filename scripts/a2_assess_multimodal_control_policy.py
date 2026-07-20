import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_SCHEMAS = {
    "a2.multimodal_control_policy.v1": (
        ROOT
        / "docs/a2/schemas/multimodal_control_policy_assessment_v1.schema.json"
    ),
    "a2.multimodal_control_policy.v2": (
        ROOT
        / "docs/a2/schemas/multimodal_control_policy_assessment_v2.schema.json"
    ),
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _wilson_interval(successes: int, total: int) -> tuple[float | None, float | None]:
    if total < 1:
        return None, None
    z = 1.959963984540054
    estimate = successes / total
    denominator = 1 + z * z / total
    center = (estimate + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            estimate * (1 - estimate) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return round(max(0.0, center - margin), 6), round(
        min(1.0, center + margin), 6
    )


def _validate_policy(policy: dict[str, Any]) -> None:
    version = policy.get("schema_version")
    if version not in {
        "a2.multimodal_control_policy.v1",
        "a2.multimodal_control_policy.v2",
    }:
        raise ValueError("unsupported multimodal control policy")
    policy_v2 = version.endswith(".v2")
    if policy.get("provider_is_truth") is not False:
        raise ValueError("control policy cannot designate a provider as truth")
    if policy.get("release_authority") is not False:
        raise ValueError("control policy cannot be release authority")
    if policy.get("public_safe") is not True:
        raise ValueError("control policy must be public safe")
    safe = policy.get("safe_controls")
    if not isinstance(safe, dict):
        raise ValueError("safe control policy is required")
    if safe.get("minimum_eligible_count", 0) < 1:
        raise ValueError("safe control minimum must be positive")
    if safe.get("maximum_false_positive_count", -1) < 0:
        raise ValueError("safe control maximum false positives cannot be negative")
    if policy_v2:
        threshold = safe.get("maximum_false_positive_wilson_upper")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 <= threshold <= 1
        ):
            raise ValueError("invalid safe false-positive Wilson upper threshold")
    taxonomies = policy.get("taxonomy_policies")
    if not isinstance(taxonomies, dict) or not taxonomies:
        raise ValueError("at least one taxonomy policy is required")
    for taxonomy, value in taxonomies.items():
        if not taxonomy or not isinstance(value, dict):
            raise ValueError("invalid taxonomy policy")
        if value.get("minimum_eligible_count", 0) < 1:
            raise ValueError("taxonomy minimum must be positive")
        threshold = value.get("minimum_sensitivity")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 <= threshold <= 1
        ):
            raise ValueError("invalid taxonomy sensitivity threshold")
        if policy_v2:
            wilson_threshold = value.get("minimum_sensitivity_wilson_lower")
            if (
                isinstance(wilson_threshold, bool)
                or not isinstance(wilson_threshold, (int, float))
                or not 0 <= wilson_threshold <= 1
            ):
                raise ValueError("invalid taxonomy Wilson lower threshold")


def build_assessment(
    *,
    calibration: dict[str, Any],
    calibration_path: str,
    calibration_bytes: bytes,
    policy: dict[str, Any],
) -> dict[str, Any]:
    _validate_policy(policy)
    policy_v2 = policy["schema_version"].endswith(".v2")
    blockers: list[str] = []
    source_usable = (
        calibration.get("schema_version")
        == "a2.dashscope_multimodal_calibration.v5"
        and calibration.get("secret_included") is False
        and calibration.get("release_authority") is False
        and calibration.get("public_safe") is True
    )
    if not source_usable:
        blockers.append("multimodal_control_source_calibration_unusable")
    observations = [
        item
        for item in calibration.get("observations", [])
        if isinstance(item, dict)
        and item.get("http_state") == "completed"
        and item.get("parse_state") == "valid_json"
        and isinstance(item.get("observed_risk"), bool)
    ]
    safe = [item for item in observations if item.get("expected_risk") is False]
    safe_policy = policy["safe_controls"]
    false_positive_count = sum(item["observed_risk"] is True for item in safe)
    safe_complete = len(safe) >= safe_policy["minimum_eligible_count"]
    safe_passed = (
        safe_complete
        and false_positive_count <= safe_policy["maximum_false_positive_count"]
    )
    _, false_positive_wilson_upper = _wilson_interval(
        false_positive_count, len(safe)
    )
    safe_wilson_passed = (
        not policy_v2
        or (
            false_positive_wilson_upper is not None
            and false_positive_wilson_upper
            <= safe_policy["maximum_false_positive_wilson_upper"]
        )
    )
    safe_passed = bool(safe_passed and safe_wilson_passed)
    if not safe_complete:
        blockers.append("multimodal_safe_control_minimum_not_met")
    elif not safe_passed:
        if false_positive_count > safe_policy["maximum_false_positive_count"]:
            blockers.append(
                "multimodal_safe_control_false_positive_count_exceeded"
            )
        if not safe_wilson_passed:
            blockers.append(
                "multimodal_safe_control_false_positive_wilson_upper_exceeded"
            )
    safe_assessment = {
        "eligible_count": len(safe),
        "minimum_eligible_count": safe_policy["minimum_eligible_count"],
        "false_positive_count": false_positive_count,
        "maximum_false_positive_count": safe_policy[
            "maximum_false_positive_count"
        ],
        **(
            {
                "false_positive_wilson_upper": false_positive_wilson_upper,
                "maximum_false_positive_wilson_upper": safe_policy[
                    "maximum_false_positive_wilson_upper"
                ],
            }
            if policy_v2
            else {}
        ),
        "passed": safe_passed,
    }

    taxonomy_assessments = {}
    incomplete = not source_usable or not safe_complete
    for taxonomy, taxonomy_policy in sorted(policy["taxonomy_policies"].items()):
        matching = [
            item
            for item in observations
            if item.get("expected_risk") is True
            and item.get("taxonomy") == taxonomy
        ]
        count = len(matching)
        detected = sum(item["observed_risk"] is True for item in matching)
        sensitivity = detected / count if count else None
        sensitivity_wilson_lower, _ = _wilson_interval(detected, count)
        complete = count >= taxonomy_policy["minimum_eligible_count"]
        passed = bool(
            complete
            and sensitivity is not None
            and sensitivity >= taxonomy_policy["minimum_sensitivity"]
            and (
                not policy_v2
                or (
                    sensitivity_wilson_lower is not None
                    and sensitivity_wilson_lower
                    >= taxonomy_policy["minimum_sensitivity_wilson_lower"]
                )
            )
        )
        if not complete:
            incomplete = True
            blockers.append(f"multimodal_taxonomy_minimum_not_met:{taxonomy}")
        elif not passed:
            if (
                sensitivity is None
                or sensitivity < taxonomy_policy["minimum_sensitivity"]
            ):
                blockers.append(
                    f"multimodal_taxonomy_sensitivity_threshold_not_met:{taxonomy}"
                )
            if (
                policy_v2
                and (
                    sensitivity_wilson_lower is None
                    or sensitivity_wilson_lower
                    < taxonomy_policy["minimum_sensitivity_wilson_lower"]
                )
            ):
                blockers.append(
                    "multimodal_taxonomy_sensitivity_wilson_lower_not_met:"
                    f"{taxonomy}"
                )
        taxonomy_assessments[taxonomy] = {
            "eligible_count": count,
            "minimum_eligible_count": taxonomy_policy[
                "minimum_eligible_count"
            ],
            "detected_count": detected,
            "sensitivity": sensitivity,
            "minimum_sensitivity": taxonomy_policy["minimum_sensitivity"],
            **(
                {
                    "sensitivity_wilson_lower": sensitivity_wilson_lower,
                    "minimum_sensitivity_wilson_lower": taxonomy_policy[
                        "minimum_sensitivity_wilson_lower"
                    ],
                }
                if policy_v2
                else {}
            ),
            "passed": passed,
        }
    blockers = sorted(set(blockers))
    quality_state = "incomplete" if incomplete else ("blocked" if blockers else "qualified")
    result = {
        "schema_version": (
            "a2.multimodal_control_policy_assessment.v2"
            if policy_v2
            else "a2.multimodal_control_policy_assessment.v1"
        ),
        "generated_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "source_calibration_path": calibration_path,
        "source_calibration_hash": _hash(calibration_bytes),
        "policy_id": policy["policy_id"],
        "policy_hash": _hash(_canonical_bytes(policy)),
        "safe_control_assessment": safe_assessment,
        "taxonomy_assessments": taxonomy_assessments,
        "quality_state": quality_state,
        "quality_blockers": blockers,
        "provider_is_truth": False,
        "secret_included": False,
        "release_authority": False,
        "public_safe": True,
    }
    schema = json.loads(
        OUTPUT_SCHEMAS[policy["schema_version"]].read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    calibration_path = ROOT / args.calibration
    calibration_bytes = calibration_path.read_bytes()
    calibration = json.loads(calibration_bytes)
    policy = json.loads((ROOT / args.policy).read_text(encoding="utf-8"))
    result = build_assessment(
        calibration=calibration,
        calibration_path=args.calibration,
        calibration_bytes=calibration_bytes,
        policy=policy,
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output}: quality_state={result['quality_state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
