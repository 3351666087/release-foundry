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
REVIEWED_LIVE_METADATA_FIELDS = [
    "prompt_template_id",
    "prompt_hash",
    "response_hash",
    "review_status",
    "sdk_language",
]


def build_semantic_harness_report(
    calibration_matrix: dict[str, Any],
    sdk_parity_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe the audited LLM judge path without pretending live calls happened."""
    cases = [_harness_case(case) for case in calibration_matrix.get("cases", [])]
    sdk_languages = _sdk_languages(sdk_parity_report)
    live_review = _live_review_summary(calibration_matrix)
    live_model_evidence_available = bool(live_review["complete"])
    risk_assessment = _risk_assessment(cases, live_model_evidence_available)
    readiness_checks = {
        "has_prompt_contract": True,
        "has_output_schema": True,
        "has_cost_policy": True,
        "has_redaction_policy": True,
        "has_false_positive_tracking": bool(risk_assessment.get("tracking_ready")),
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
        "reviewed_live_observation_count": live_review["reviewed_count"],
        "missing_reviewed_live_observation_count": live_review["missing_count"],
        "reviewed_live_sdk_languages": live_review["sdk_languages"],
        "reviewed_live_required_metadata_fields": REVIEWED_LIVE_METADATA_FIELDS,
        "reviewed_live_evidence_gaps": live_review["gaps"],
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
        "risk_assessment": risk_assessment,
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
    expected = _summary_result(case.get("expected", {}))
    local = _summary_result(sources.get("local_judge", {}))
    llm = sources.get("llm_judge", {})
    offline_reference = _summary_result(llm) if llm.get("available") else {"available": False}
    risk_flags = _semantic_risk_flags(expected, local, offline_reference)
    return {
        "case_id": case.get("case_id", ""),
        "scenario_id": case.get("scenario_id", ""),
        "fixture_ref": case.get("fixture_ref", ""),
        "calibration_focus": case.get("calibration_focus", []),
        "expected": expected,
        "local_judge": local,
        "offline_reference": offline_reference,
        "sdk_input_paths": {
            "python": _semantic_prompt_path("python"),
            "typescript": _semantic_prompt_path("typescript"),
        },
        "semantic_prompt_fields": PROMPT_FIELDS,
        "risk_flags": risk_flags,
        "audit_target": {
            "required_live_source": "llm_judge",
            "required_provider_status": "not offline_reference",
            "raw_evidence": "private",
        },
    }


def _risk_assessment(cases: list[dict[str, Any]], live_model_evidence_available: bool) -> dict[str, Any]:
    risk_cases = []
    for case in cases:
        flags = case.get("risk_flags", [])
        if not flags:
            continue
        local = case.get("local_judge", {})
        offline = case.get("offline_reference", {})
        score_delta = _score_delta(local, offline)
        risk_case = {
            "case_id": case.get("case_id", ""),
            "scenario_id": case.get("scenario_id", ""),
            "risk_flags": flags,
            "expected_failure_class": case.get("expected", {}).get("primary_failure_class", ""),
            "local_failure_class": local.get("primary_failure_class", ""),
            "offline_reference_failure_class": offline.get("primary_failure_class", ""),
        }
        if score_delta is not None:
            risk_case["score_delta"] = score_delta
        risk_cases.append(risk_case)

    def count(flag: str) -> int:
        return sum(1 for case in cases if flag in case.get("risk_flags", []))

    return {
        "status": "audited_live_risk_register"
        if live_model_evidence_available
        else "offline_reference_risk_register",
        "tracking_ready": True,
        "basis": "offline_reference" if not live_model_evidence_available else "audited_live_model_evidence",
        "case_count": len(cases),
        "false_positive_candidate_count": count("false_positive_candidate"),
        "false_negative_candidate_count": count("false_negative_candidate"),
        "failure_class_drift_candidate_count": count("failure_class_drift_candidate"),
        "score_delta_review_count": count("score_delta_review"),
        "low_confidence_reference_count": count("low_confidence_reference"),
        "risk_case_count": len(risk_cases),
        "risk_cases": risk_cases,
        "interpretation": (
            "These are review candidates, not model quality rates, until audited live semantic judge evidence "
            "replaces offline references."
        ),
    }


def _semantic_risk_flags(
    expected: dict[str, Any],
    local: dict[str, Any],
    offline_reference: dict[str, Any],
) -> list[str]:
    if offline_reference.get("available") is False or offline_reference.get("passed") is None:
        return ["missing_semantic_reference"]

    flags = []
    expected_passed = expected.get("passed")
    offline_passed = offline_reference.get("passed")
    expected_class = expected.get("primary_failure_class")
    offline_class = offline_reference.get("primary_failure_class")
    if expected_passed is False and offline_passed is True:
        flags.append("false_positive_candidate")
    if expected_passed is True and offline_passed is False:
        flags.append("false_negative_candidate")
    if (
        expected_passed == offline_passed
        and expected_class
        and offline_class
        and expected_class != offline_class
    ):
        flags.append("failure_class_drift_candidate")

    score_delta = _score_delta(local, offline_reference)
    if score_delta is not None and score_delta >= 20:
        flags.append("score_delta_review")
    confidence = offline_reference.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.75:
        flags.append("low_confidence_reference")
    return flags


def _score_delta(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    left_score = left.get("score")
    right_score = right.get("score")
    if not isinstance(left_score, (int, float)) or not isinstance(right_score, (int, float)):
        return None
    return round(abs(float(left_score) - float(right_score)), 2)


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
    return bool(_live_review_summary(calibration_matrix)["complete"])


def _live_review_summary(calibration_matrix: dict[str, Any]) -> dict[str, Any]:
    cases = list(calibration_matrix.get("cases", []))
    reviewed_sources = []
    sdk_languages = set()
    for case in cases:
        source = case.get("sources", {}).get("llm_judge", {})
        if _is_reviewed_live_semantic_source(source):
            reviewed_sources.append(source)
            sdk_language = source.get("metadata", {}).get("sdk_language")
            if sdk_language:
                sdk_languages.add(str(sdk_language))

    required_languages = set(REQUIRED_SDK_LANGUAGES)
    missing_count = max(0, len(cases) - len(reviewed_sources))
    missing_languages = sorted(required_languages - sdk_languages)
    gaps = []
    if missing_count:
        gaps.append(f"Import {missing_count} more audited live semantic judge observation(s).")
    if missing_languages:
        gaps.append(f"Add audited semantic judge evidence for SDK language(s): {', '.join(missing_languages)}.")
    return {
        "complete": bool(cases) and missing_count == 0 and not missing_languages,
        "reviewed_count": len(reviewed_sources),
        "missing_count": missing_count,
        "sdk_languages": sorted(sdk_languages),
        "gaps": gaps,
    }


def _is_reviewed_live_semantic_source(source: dict[str, Any]) -> bool:
    if source.get("available") is not True or source.get("status") != "available":
        return False
    provider = str(source.get("provider", "")).strip().lower()
    if provider in {"", "offline_reference", "offline reference judge samples"}:
        return False
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    if any(not str(metadata.get(field, "")).strip() for field in REVIEWED_LIVE_METADATA_FIELDS):
        return False
    cost = source.get("cost") if isinstance(source.get("cost"), dict) else {}
    return (
        int(cost.get("prompt_tokens", 0)) > 0
        and int(cost.get("completion_tokens", 0)) > 0
        and float(cost.get("estimated_usd", 0.0)) > 0
    )
