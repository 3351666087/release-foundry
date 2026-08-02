import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_SCHEMAS = {
    "a2.local_model_runtime_promotion_policy.v1": (
        ROOT
        / "docs/a2/schemas/local_model_runtime_promotion_contract_v1.schema.json"
    ),
    "a2.local_model_runtime_promotion_policy.v2": (
        ROOT
        / "docs/a2/schemas/local_model_runtime_promotion_contract_v2.schema.json"
    ),
}
HASH_PATTERN = r"^sha256:[a-f0-9]{64}$"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _validate_policy(policy: dict[str, Any]) -> None:
    version = policy.get("schema_version")
    if version == "a2.local_model_runtime_promotion_policy.v2":
        required = {
            "schema_version",
            "policy_id",
            "required_profiles",
            "required_format_mode",
            "maximum_cold_caller_wall_seconds",
            "maximum_warm_caller_wall_seconds",
            "minimum_consecutive_successful_profiles",
            "require_valid_structured_output",
            "require_digest_binding",
            "require_provider_not_truth",
            "require_no_release_authority",
            "public_safe",
        }
    else:
        version = "a2.local_model_runtime_promotion_policy.v1"
        required = {
            "schema_version",
            "policy_id",
            "required_profiles",
            "required_format_mode",
            "maximum_warm_caller_wall_seconds",
            "require_valid_structured_output",
            "require_digest_binding",
            "require_provider_not_truth",
            "require_no_release_authority",
            "public_safe",
        }
    if set(policy) != required:
        raise ValueError("runtime promotion policy fields do not match contract")
    if policy["schema_version"] != version:
        raise ValueError("unsupported runtime promotion policy schema")
    profiles = policy["required_profiles"]
    if (
        not isinstance(profiles, list)
        or not profiles
        or any(not isinstance(item, str) or not item for item in profiles)
        or len(set(profiles)) != len(profiles)
    ):
        raise ValueError("required_profiles must contain unique non-empty names")
    if policy["required_format_mode"] != "json_schema":
        raise ValueError("runtime promotion requires json_schema format")
    limit = policy["maximum_warm_caller_wall_seconds"]
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or limit <= 0:
        raise ValueError("maximum warm latency must be positive")
    if version.endswith(".v2"):
        cold_limit = policy["maximum_cold_caller_wall_seconds"]
        if (
            isinstance(cold_limit, bool)
            or not isinstance(cold_limit, (int, float))
            or cold_limit <= 0
        ):
            raise ValueError("maximum cold latency must be positive")
        minimum_successes = policy["minimum_consecutive_successful_profiles"]
        if (
            isinstance(minimum_successes, bool)
            or not isinstance(minimum_successes, int)
            or minimum_successes < 2
        ):
            raise ValueError(
                "minimum consecutive successful profiles must be at least two"
            )
    for name in (
        "require_valid_structured_output",
        "require_digest_binding",
        "require_provider_not_truth",
        "require_no_release_authority",
        "public_safe",
    ):
        if policy[name] is not True:
            raise ValueError(f"{name} must be true")


def build_contract(
    *,
    probe: dict[str, Any],
    probe_path: str,
    probe_bytes: bytes,
    policy: dict[str, Any],
) -> dict[str, Any]:
    _validate_policy(policy)
    blockers: list[str] = []
    if probe.get("schema_version") not in {
        "a2.ollama_multimodal_latency_probe.v1",
        "a2.ollama_multimodal_latency_probe.v2",
    }:
        blockers.append("local_runtime_probe_schema_unsupported")
    model_digest = probe.get("model_digest")
    try:
        jsonschema.validate(model_digest, {"type": "string", "pattern": HASH_PATTERN})
    except jsonschema.ValidationError:
        blockers.append("local_runtime_model_digest_invalid")
        model_digest = "sha256:" + "0" * 64
    if probe.get("provider_is_truth") is not False:
        blockers.append("local_runtime_provider_truth_boundary_invalid")
    if probe.get("release_authority") is not False:
        blockers.append("local_runtime_release_authority_boundary_invalid")
    if probe.get("secret_included") is not False:
        blockers.append("local_runtime_secret_boundary_invalid")
    if probe.get("public_safe") is not True:
        blockers.append("local_runtime_public_safety_unconfirmed")

    required_profiles = policy["required_profiles"]
    policy_v2 = policy["schema_version"].endswith(".v2")
    profile_map = {
        item.get("profile"): item
        for item in probe.get("profiles", [])
        if isinstance(item, dict) and isinstance(item.get("profile"), str)
    }
    observed_profiles = []
    missing = False
    for profile_name in required_profiles:
        item = profile_map.get(profile_name)
        if item is None:
            blockers.append(f"local_runtime_required_profile_missing:{profile_name}")
            missing = True
            continue
        wall = item.get("phase_receipt", {}).get("caller_wall_seconds")
        phase = "cold" if profile_name.startswith("cold_") else "warm"
        latency_limit = (
            policy["maximum_cold_caller_wall_seconds"]
            if policy_v2 and phase == "cold"
            else policy["maximum_warm_caller_wall_seconds"]
        )
        within_latency = (
            isinstance(wall, (int, float))
            and not isinstance(wall, bool)
            and wall <= latency_limit
        )
        valid_output = (
            item.get("state") == "completed"
            and item.get("parse_state") == "valid_json"
            and item.get("format_mode") == policy["required_format_mode"]
        )
        eligible = bool(within_latency and valid_output)
        if item.get("format_mode") != policy["required_format_mode"]:
            blockers.append(f"local_runtime_required_format_mismatch:{profile_name}")
        if item.get("state") != "completed":
            blockers.append(f"local_runtime_profile_not_completed:{profile_name}")
        if item.get("parse_state") != "valid_json":
            blockers.append(f"local_runtime_structured_output_invalid:{profile_name}")
        if not within_latency:
            latency_phase = phase if policy_v2 else "warm"
            blockers.append(
                f"local_runtime_{latency_phase}_latency_limit_not_met:{profile_name}"
            )
        observed_profiles.append(
            {
                "profile": profile_name,
                "required": True,
                **(
                    {
                        "phase": phase,
                        "latency_limit_seconds": latency_limit,
                    }
                    if policy_v2
                    else {}
                ),
                "format_mode": item.get("format_mode", "plain"),
                "state": item.get("state", "failed"),
                "parse_state": item.get("parse_state", "unavailable"),
                "caller_wall_seconds": wall
                if isinstance(wall, (int, float)) and not isinstance(wall, bool)
                else None,
                "within_latency_limit": within_latency,
                "promotion_eligible": eligible,
            }
        )

    consecutive = 0
    maximum_consecutive = 0
    for item in observed_profiles:
        if item["promotion_eligible"]:
            consecutive += 1
            maximum_consecutive = max(maximum_consecutive, consecutive)
        else:
            consecutive = 0
    if (
        policy_v2
        and maximum_consecutive
        < policy["minimum_consecutive_successful_profiles"]
    ):
        blockers.append("local_runtime_consecutive_success_minimum_not_met")
    phase_states = {}
    if policy_v2:
        for phase in ("cold", "warm"):
            phase_profiles = [
                item for item in observed_profiles if item["phase"] == phase
            ]
            if not phase_profiles:
                phase_states[phase] = "not_required"
            elif all(item["promotion_eligible"] for item in phase_profiles):
                phase_states[phase] = "qualified"
            else:
                phase_states[phase] = "blocked"
    blockers = sorted(set(blockers))
    if missing:
        state = "incomplete"
    elif blockers:
        state = "blocked"
    else:
        state = "qualified"
    result = {
        "schema_version": (
            "a2.local_model_runtime_promotion_contract.v2"
            if policy_v2
            else "a2.local_model_runtime_promotion_contract.v1"
        ),
        "generated_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "policy_id": policy["policy_id"],
        "policy_hash": _hash_bytes(_canonical_bytes(policy)),
        "source_probe_path": probe_path,
        "source_probe_hash": _hash_bytes(probe_bytes),
        "model_id": str(probe.get("model_id", "unknown")),
        "model_digest": model_digest,
        "required_profiles": required_profiles,
        "observed_profiles": observed_profiles,
        **(
            {
                "minimum_consecutive_successful_profiles": policy[
                    "minimum_consecutive_successful_profiles"
                ],
                "maximum_consecutive_successful_profiles": maximum_consecutive,
                "cold_runtime_state": phase_states["cold"],
                "warm_runtime_state": phase_states["warm"],
            }
            if policy_v2
            else {}
        ),
        "runtime_promotion_state": state,
        "blockers": blockers,
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
    parser.add_argument("--probe", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    probe_path = ROOT / args.probe
    policy_path = ROOT / args.policy
    probe_bytes = probe_path.read_bytes()
    probe = json.loads(probe_bytes)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    result = build_contract(
        probe=probe,
        probe_path=args.probe,
        probe_bytes=probe_bytes,
        policy=policy,
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.output}: runtime_promotion_state="
        f"{result['runtime_promotion_state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
