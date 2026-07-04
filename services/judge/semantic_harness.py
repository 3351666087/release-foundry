"""Semantic judge harness planning evidence for A2 calibration."""

from __future__ import annotations

from typing import Any

from .schemas import CANONICAL_FAILURE_CLASSES


REQUIRED_SDK_LANGUAGES = ["python", "typescript"]
PROMPT_FIELDS = [
    "scenario_id",
    "scenario_family",
    "user_request",
    "toolPolicy",
    "expectedBehaviors",
    "failure_taxonomy",
    "agent_final_response",
    "agent_tool_calls",
    "observed_tool_results",
]
OUTPUT_FIELDS = [
    "passed",
    "primary_failure_class",
    "score",
    "confidence",
    "rationale",
    "evidence_refs",
]


def build_semantic_harness_report(
    calibration_matrix: dict[str, Any],
    sdk_parity_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe the audited LLM judge path without pretending live calls happened."""
    cases = [_harness_case(case) for case in calibration_matrix.get("cases", [])]
    sdk_languages = _sdk_languages(sdk_parity_report)
    live_model_evidence_available = _live_model_evidence_available(calibration_matrix)
    readiness_checks = {
        "has_prompt_contract": True,
        "has_output_schema": True,
        "has_cost_policy": True,
        "has_redaction_policy": True,
        "covers_calibration_cases": len(cases) == int(calibration_matrix.get("case_count", 0)) and bool(cases),
        "covers_python_and_typescript": set(REQUIRED_SDK_LANGUAGES).issubset(sdk_languages),
        "has_official_sdk_chain_map": set(REQUIRED_SDK_LANGUAGES).issubset(
            {chain.get("language") for chain in _official_sdk_chains(sdk_parity_report)}
        ),
        "live_model_evidence_available": live_model_evidence_available,
    }
    audit_ready_checks = {
        key: value for key, value in readiness_checks.items() if key != "live_model_evidence_available"
    }

    return {
        "schema_version": "a2.semantic_harness.v1",
        "harness_id": "a2_g3_semantic_judge_harness",
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "case_count": len(cases),
        "status": "offline_reference_only" if not live_model_evidence_available else "audited_live_model_evidence",
        "harness_ready": all(audit_ready_checks.values()),
        "live_model_evidence_available": live_model_evidence_available,
        "source_matrix": {
            "required_languages": REQUIRED_SDK_LANGUAGES,
            "covered_languages": sorted(sdk_languages),
            "sdk_parity_passed": bool((sdk_parity_report or {}).get("parity_passed")),
            "language_contracts": _language_contracts(sdk_parity_report),
            "official_sdk_chains": _official_sdk_chains(sdk_parity_report),
            "official_docs_refs": {
                "python": "https://ashr.io/docs/python-sdk/overview",
                "typescript": "https://ashr.io/docs/typescript-sdk/overview",
            },
        },
        "prompt_contract": _prompt_contract(),
        "output_schema": _output_schema(),
        "model_policy": _model_policy(live_model_evidence_available),
        "cost_policy": _cost_policy(),
        "redaction_policy": _redaction_policy(),
        "readiness_checks": readiness_checks,
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "purpose": "Prepare C4 semantic judge audits for both Python and TypeScript SDK-result chains.",
            "private_evidence_boundary": "Raw prompts, raw responses, API keys, and reviewer notes stay outside committed fixtures.",
        },
    }


def _sdk_languages(sdk_parity_report: dict[str, Any] | None) -> set[str]:
    if not sdk_parity_report:
        return set()
    return set(sdk_parity_report.get("passed_languages", []))


def _language_contracts(sdk_parity_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    contracts = []
    for contract in (sdk_parity_report or {}).get("source_contracts", []):
        language = str(contract.get("language", ""))
        contracts.append(
            {
                "language": language,
                "sdk_path": contract.get("sdk_path", ""),
                "runner_shape": contract.get("runner_shape", ""),
                "semantic_prompt_path": _semantic_prompt_path(language),
            }
        )
    if contracts:
        return contracts
    return [
        {
            "language": "python",
            "sdk_path": "packages/sdk/ashr_clone/adapter.py",
            "runner_shape": "AgentTurn -> A2 normalize_run_input",
            "semantic_prompt_path": _semantic_prompt_path("python"),
        },
        {
            "language": "typescript",
            "sdk_path": "packages/ts/ashr-clone/src/index.ts",
            "runner_shape": "CaseResult.agent_output -> A2 normalize_run_input",
            "semantic_prompt_path": _semantic_prompt_path("typescript"),
        },
    ]


def _official_sdk_chains(sdk_parity_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    chains = (sdk_parity_report or {}).get("official_sdk_chains", [])
    if chains:
        return [dict(chain) for chain in chains if isinstance(chain, dict)]
    return [
        {
            "language": "python",
            "docs_url": "https://ashr.io/docs/python-sdk/overview",
            "runner_entrypoint": "EvalRunner.from_dataset(client, dataset_id=...)",
            "run_and_deploy_entrypoint": "runner.run_and_deploy(agent, client, dataset_id=...)",
            "a2_consumed_shape": "AgentTurn or AgentResult.to_dict()",
        },
        {
            "language": "typescript",
            "docs_url": "https://ashr.io/docs/typescript-sdk/overview",
            "runner_entrypoint": "await EvalRunner.fromDataset(client, datasetId)",
            "run_and_deploy_entrypoint": "await runner.runAndDeploy(agent, client, datasetId)",
            "a2_consumed_shape": "CaseResult.agent_output",
        },
    ]


def _semantic_prompt_path(language: str) -> str:
    if language == "typescript":
        return "CaseResult.agent_output.text/tool_calls -> semantic prompt fields"
    return "AgentTurn.text/tool_calls -> semantic prompt fields"


def _prompt_contract() -> dict[str, Any]:
    return {
        "template_id": "a2_semantic_judge_prompt_v1",
        "template_status": "ready_for_audited_model_calls",
        "input_fields": PROMPT_FIELDS,
        "instruction_summary": (
            "Compare the agent's final response and tool trace against the scenario contract, "
            "then return only the structured output schema."
        ),
        "grounding_order": [
            "scenario toolPolicy",
            "expectedBehaviors",
            "observed tool calls and tool results",
            "final response",
            "canonical failure taxonomy",
        ],
        "tie_breakers": [
            "Prefer tool-contract failures over vague semantic failures when the trace proves the issue.",
            "Use missing_clarification when a safe answer requires a targeted user question.",
            "Mark hallucinated_tool_result when the final answer invents facts not present in tool output.",
        ],
    }


def _output_schema() -> dict[str, Any]:
    return {
        "schema_version": "a2.semantic_judge_output.v1",
        "required_fields": OUTPUT_FIELDS,
        "failure_class_enum": ["none"] + sorted(CANONICAL_FAILURE_CLASSES),
        "score_scale": "0-100",
        "confidence_scale": "0-1",
        "evidence_refs_required": True,
    }


def _model_policy(live_model_evidence_available: bool) -> dict[str, Any]:
    return {
        "current_status": "audited_live_model_evidence"
        if live_model_evidence_available
        else "offline_reference_only",
        "required_for_c4_met": [
            "provider",
            "model",
            "prompt_template_id",
            "prompt_hash",
            "response_hash",
            "reviewer",
            "review_status",
        ],
        "raw_payload_policy": "Keep raw prompt/response payloads in private evidence only; commit hashes and summaries.",
        "minimum_model_matrix": [
            "one primary semantic judge model",
            "one spot-check fallback or reviewer adjudication path for disagreements",
        ],
    }


def _cost_policy() -> dict[str, Any]:
    return {
        "required_fields": ["prompt_tokens", "completion_tokens", "estimated_usd"],
        "aggregation": "per case and per provider/model batch",
        "zero_cost_rule": "Zero estimated_usd is allowed only for local deterministic judges, not live semantic judges.",
    }


def _redaction_policy() -> dict[str, Any]:
    return {
        "secret_patterns": ["tp_* API keys", "Bearer tokens", "email addresses", "raw private payloads"],
        "public_fixture_rule": "Commit only reviewed summaries, cost numbers, hashes, and fixture references.",
        "private_path": "docs/evidence/private_refs/",
    }


def _harness_case(case: dict[str, Any]) -> dict[str, Any]:
    sources = case.get("sources", {})
    local = sources.get("local_judge", {})
    llm = sources.get("llm_judge", {})
    return {
        "case_id": case.get("case_id", ""),
        "scenario_id": case.get("scenario_id", ""),
        "fixture_ref": case.get("fixture_ref", ""),
        "calibration_focus": case.get("calibration_focus", []),
        "expected": _summary_result(case.get("expected", {})),
        "local_judge": _summary_result(local),
        "offline_reference": _summary_result(llm) if llm.get("available") else {"available": False},
        "sdk_input_paths": {
            "python": _semantic_prompt_path("python"),
            "typescript": _semantic_prompt_path("typescript"),
        },
        "semantic_prompt_fields": PROMPT_FIELDS,
        "audit_target": {
            "required_live_source": "llm_judge",
            "required_provider_status": "not offline_reference",
            "raw_evidence": "private",
        },
    }


def _summary_result(result: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "passed": result.get("passed"),
        "primary_failure_class": result.get("primary_failure_class", ""),
    }
    if result.get("score") is not None:
        summary["score"] = result.get("score")
    if result.get("confidence") is not None:
        summary["confidence"] = result.get("confidence")
    if result.get("provider") is not None:
        summary["provider"] = result.get("provider")
    if result.get("model") is not None:
        summary["model"] = result.get("model")
    if result.get("evidence_ref") is not None:
        summary["evidence_ref"] = result.get("evidence_ref")
    return summary


def _live_model_evidence_available(calibration_matrix: dict[str, Any]) -> bool:
    llm_sources = [
        case.get("sources", {}).get("llm_judge", {})
        for case in calibration_matrix.get("cases", [])
        if case.get("sources", {}).get("llm_judge", {}).get("available")
    ]
    return bool(llm_sources) and all(source.get("provider") != "offline_reference" for source in llm_sources)
