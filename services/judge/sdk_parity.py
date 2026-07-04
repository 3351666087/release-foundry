"""SDK-language parity evidence for A2 runner consumption."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runner import DEFAULT_SCENARIO_PACK, grade_run


SDK_PARITY_SCENARIO_ID = "A2-S005"
SDK_PARITY_RESPONSE = "- Launch risk is dependency timing.\n- Mitigation is owner review.\n- Next step is Friday signoff."
SDK_PARITY_TOOL_ARGS = {"path": "fixtures/a2/notes/launch-review.md"}


def build_sdk_parity_report(pack_path: str | Path = DEFAULT_SCENARIO_PACK) -> dict[str, Any]:
    """Prove A2 can consume both Python and TypeScript SDK handoff shapes."""
    cases = [
        _parity_case("python", "AgentTurn", _python_agent_turn(), pack_path),
        _parity_case("typescript", "CaseResult.agent_output", _typescript_case_result(), pack_path),
    ]
    required_languages = ["python", "typescript"]
    passed_languages = [case["language"] for case in cases if case["a2_grade"]["passed"]]
    return {
        "schema_version": "a2.sdk_parity.v1",
        "report_id": "a2_sdk_parity_report",
        "scenario_id": SDK_PARITY_SCENARIO_ID,
        "required_languages": required_languages,
        "passed_languages": passed_languages,
        "sdk_language_count": len(passed_languages),
        "parity_passed": set(passed_languages) == set(required_languages),
        "source_contracts": [
            {
                "language": "python",
                "sdk_path": "packages/sdk/ashr_clone/adapter.py",
                "schema_versions": ["ashr.clone.agent_input.v1", "ashr.clone.agent_turn.v1"],
                "runner_shape": "AgentResult.to_dict() -> A2 normalize_run_input",
            },
            {
                "language": "typescript",
                "sdk_path": "packages/ts/ashr-clone/src/index.ts",
                "schema_versions": ["ashr.clone.agent_input.v1", "ashr.clone.agent_turn.v1"],
                "runner_shape": "CaseResult.agent_output -> A2 normalize_run_input",
            },
        ],
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "official_docs_refs": [
                "https://ashr.io/docs/python-sdk/overview",
                "https://ashr.io/docs/typescript-sdk/overview",
            ],
            "purpose": "Keep the A2 judge contract aligned with both Ashr Python and TypeScript SDK entrypoints.",
        },
    }


def _parity_case(language: str, input_shape: str, run: dict[str, Any], pack_path: str | Path) -> dict[str, Any]:
    case_id = str(run.get("case_id") or f"sdk-parity-{language}")
    grade = grade_run(SDK_PARITY_SCENARIO_ID, run, pack_path=pack_path, case_id=case_id)
    return {
        "language": language,
        "case_id": case_id,
        "input_shape": input_shape,
        "runner_metadata": _runner_metadata(run),
        "a2_grade": {
            "passed": grade["passed"],
            "score": grade["score"],
            "primary_failure_class": grade["primary_failure_class"],
            "judge_count": len(grade["judge_results"]),
        },
    }


def _python_agent_turn() -> dict[str, Any]:
    return {
        "schema_version": "ashr.clone.agent_turn.v1",
        "text": SDK_PARITY_RESPONSE,
        "tool_calls": [
            {
                "name": "file.read",
                "arguments": dict(SDK_PARITY_TOOL_ARGS),
                "call_id": "sdk-parity-python-call",
            }
        ],
        "status": "ok",
        "latency_ms": 0,
        "metadata": {
            "sdk_language": "python",
            "sdk_contract": "packages/sdk/ashr_clone/adapter.py",
            "adapter_name": "A1PythonAdapter",
        },
    }


def _typescript_case_result() -> dict[str, Any]:
    return {
        "case_id": "sdk-parity-typescript-case",
        "scenario_id": SDK_PARITY_SCENARIO_ID,
        "status": "passed",
        "agent_output": {
            "schema_version": "ashr.clone.agent_turn.v1",
            "text": SDK_PARITY_RESPONSE,
            "tool_calls": [
                {
                    "name": "file.read",
                    "arguments": dict(SDK_PARITY_TOOL_ARGS),
                    "id": "sdk-parity-typescript-call",
                }
            ],
            "status": "ok",
            "latency_ms": 0,
            "metadata": {
                "sdk_language": "typescript",
                "sdk_contract": "packages/ts/ashr-clone/src/index.ts",
                "package": "@ashr-clone/sdk",
            },
        },
        "observations": [
            {"role": "user", "content": "Summarize launch review notes."},
            {
                "role": "assistant",
                "content": SDK_PARITY_RESPONSE,
                "tool_calls": [
                    {
                        "name": "file.read",
                        "arguments": dict(SDK_PARITY_TOOL_ARGS),
                        "id": "sdk-parity-typescript-call",
                    }
                ],
            },
        ],
        "expected": {},
        "metadata": {
            "sdk_language": "typescript",
            "runner_id": "ts-local-runner",
            "sdk_contract": "packages/ts/ashr-clone/src/index.ts",
        },
    }


def _runner_metadata(run: dict[str, Any]) -> dict[str, Any]:
    source = run.get("agent_output") if isinstance(run.get("agent_output"), dict) else run
    metadata = source.get("metadata", {}) if isinstance(source.get("metadata"), dict) else {}
    top_metadata = run.get("metadata", {}) if isinstance(run.get("metadata"), dict) else {}
    merged = dict(top_metadata)
    merged.update(metadata)
    return merged
