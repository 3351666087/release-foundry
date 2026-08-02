from __future__ import annotations

import json
from typing import Any


def compare_args_structural(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Compare tool names and arguments without fuzzy or semantic scoring."""
    expected_name = expected.get("name") or expected.get("tool_name", "")
    actual_name = actual.get("name") or actual.get("tool_name", "")
    comparison: dict[str, dict[str, Any]] = {
        "matching": {},
        "different": {},
        "missing": {},
        "extra": {},
    }
    if actual_name == "NOT_CALLED" or expected_name == "NONE_EXPECTED":
        return "mismatch", comparison
    if expected_name != actual_name:
        return "mismatch", comparison

    expected_args = _arguments(expected)
    actual_args = _arguments(actual)
    for key in sorted(expected_args.keys() | actual_args.keys()):
        if key not in actual_args:
            comparison["missing"][key] = {"expected": expected_args[key]}
        elif key not in expected_args:
            comparison["extra"][key] = {"actual": actual_args[key]}
        elif expected_args[key] == actual_args[key]:
            comparison["matching"][key] = {
                "expected": expected_args[key],
                "actual": actual_args[key],
            }
        else:
            comparison["different"][key] = {
                "expected": expected_args[key],
                "actual": actual_args[key],
            }

    changed = any(comparison[name] for name in ("different", "missing", "extra"))
    return ("partial" if changed else "exact"), comparison


def _arguments(value: dict[str, Any]) -> dict[str, Any]:
    arguments = value.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    encoded = value.get("arguments_json", "{}")
    if not isinstance(encoded, str):
        return {}
    try:
        decoded = json.loads(encoded)
    except (TypeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}
