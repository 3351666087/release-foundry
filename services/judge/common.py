"""Common helpers for A2 local judges."""

from typing import Any


def get_tool_name(call: dict[str, Any]) -> str:
    return str(call.get("tool") or call.get("name") or "")


def get_tool_args(call: dict[str, Any]) -> dict[str, Any]:
    args = call.get("args")
    if isinstance(args, dict):
        return args
    arguments = call.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    return {}


def tool_matches(rule: dict[str, Any], call: dict[str, Any]) -> bool:
    rule_tool = rule.get("tool")
    return rule_tool == "*" or rule_tool == get_tool_name(call)


def args_match(rule_args: dict[str, Any] | None, call_args: dict[str, Any]) -> bool:
    if not rule_args:
        return True
    exact = rule_args.get("exact")
    if isinstance(exact, dict) and exact != call_args:
        return False
    contains = rule_args.get("contains")
    if isinstance(contains, dict):
        for key, value in contains.items():
            if call_args.get(key) != value:
                return False
    return True


def find_matching_calls(rule: dict[str, Any], calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [call for call in calls if tool_matches(rule, call)]
