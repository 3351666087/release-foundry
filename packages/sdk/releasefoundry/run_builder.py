from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class TestBuilder:
    def __init__(self, test_id: str) -> None:
        self._test_id = test_id
        self._status = "pending"
        self._started_at: str | None = None
        self._completed_at: str | None = None
        self._action_results: list[dict[str, Any]] = []
        self._next_action_index = 0

    def start(self) -> TestBuilder:
        self._status = "running"
        self._started_at = _now()
        return self

    def add_user_text(
        self,
        text: str,
        description: str,
        action_index: int | None = None,
    ) -> TestBuilder:
        self._action_results.append(
            {
                "actor": "user",
                "action_type": "text",
                "action_index": self._resolve_index(action_index),
                "description": description,
                "text": text,
                "input_provided": True,
            }
        )
        return self

    def add_user_file(
        self,
        file_path: str,
        description: str,
        action_index: int | None = None,
    ) -> TestBuilder:
        self._action_results.append(
            {
                "actor": "user",
                "action_type": "file",
                "action_index": self._resolve_index(action_index),
                "description": description,
                "file_path": file_path,
                "input_provided": True,
            }
        )
        return self

    def add_tool_call(
        self,
        expected: dict[str, Any],
        actual: dict[str, Any],
        match_status: str,
        divergence_notes: str | None = None,
        argument_comparison: dict[str, Any] | None = None,
        action_index: int | None = None,
    ) -> TestBuilder:
        index = self._resolve_index(action_index)
        call = {
            "expected": _normalize_tool_call(expected),
            "actual": _normalize_tool_call(actual),
            "match_status": match_status,
            "divergence_notes": divergence_notes,
        }
        if argument_comparison is not None:
            call["argument_comparison"] = argument_comparison
        for action in self._action_results:
            if action.get("action_type") == "tool_call" and action.get("action_index") == index:
                action["tool_calls"].append(call)
                return self
        self._action_results.append(
            {
                "actor": "agent",
                "action_type": "tool_call",
                "action_index": index,
                "tool_calls": [call],
            }
        )
        return self

    def add_agent_response(
        self,
        expected_response: dict[str, Any],
        actual_response: dict[str, Any],
        match_status: str,
        semantic_similarity: float | None = None,
        divergence_notes: str | None = None,
        action_index: int | None = None,
    ) -> TestBuilder:
        action: dict[str, Any] = {
            "actor": "agent",
            "action_type": "text",
            "action_index": self._resolve_index(action_index),
            "expected_response": expected_response,
            "actual_response": actual_response,
            "match_status": match_status,
            "divergence_notes": divergence_notes,
        }
        if semantic_similarity is not None:
            action["semantic_similarity"] = semantic_similarity
        self._action_results.append(action)
        return self

    def complete(self, status: str = "completed") -> TestBuilder:
        self._status = status
        self._completed_at = _now()
        return self

    def build(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "test_id": self._test_id,
            "status": self._status,
            "action_results": list(self._action_results),
        }
        if self._started_at is not None:
            value["started_at"] = self._started_at
        if self._completed_at is not None:
            value["completed_at"] = self._completed_at
        return value

    def _resolve_index(self, explicit: int | None) -> int:
        if explicit is not None:
            self._next_action_index = max(self._next_action_index, explicit + 1)
            return explicit
        current = self._next_action_index
        self._next_action_index += 1
        return current


class RunBuilder:
    def __init__(self) -> None:
        self._status = "pending"
        self._started_at: str | None = None
        self._completed_at: str | None = None
        self._tests: list[TestBuilder] = []

    def start(self) -> RunBuilder:
        self._status = "running"
        self._started_at = _now()
        return self

    def add_test(self, test_id: str) -> TestBuilder:
        test = TestBuilder(test_id)
        self._tests.append(test)
        return test

    def complete(self, status: str = "completed") -> RunBuilder:
        self._status = status
        self._completed_at = _now()
        return self

    def build(self) -> dict[str, Any]:
        tests = [test.build() for test in self._tests]
        return {
            "tests": tests,
            "status": self._status,
            "started_at": self._started_at,
            "completed_at": self._completed_at,
            "aggregate_metrics": _aggregate(tests),
        }


def _normalize_tool_call(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if "tool_name" not in result and "name" in result:
        result["tool_name"] = result["name"]
    if "name" not in result and "tool_name" in result:
        result["name"] = result["tool_name"]
    if "arguments" not in result and "arguments_json" in result:
        try:
            result["arguments"] = json.loads(result["arguments_json"])
        except (TypeError, json.JSONDecodeError):
            result["arguments"] = {}
    if "arguments_json" not in result and isinstance(result.get("arguments"), dict):
        result["arguments_json"] = json.dumps(result["arguments"], sort_keys=True)
    return result


def _aggregate(tests: list[dict[str, Any]]) -> dict[str, Any]:
    similarities = [
        float(action["semantic_similarity"])
        for test in tests
        for action in test["action_results"]
        if isinstance(action.get("semantic_similarity"), (int, float))
    ]
    return {
        "total_tests": len(tests),
        "tests_passed": sum(test["status"] == "completed" for test in tests),
        "tests_failed": sum(test["status"] == "failed" for test in tests),
        "average_similarity_score": (
            round(sum(similarities) / len(similarities), 2) if similarities else None
        ),
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
