"""Public-safe C4 collection packet for semantic judge audits."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .calibration import (
    DEFAULT_CALIBRATION_OBSERVATIONS,
    build_calibration_matrix,
    load_run_fixtures_by_case,
)
from .coverage import DEFAULT_RUN_FIXTURES
from .runner import DEFAULT_SCENARIO_PACK, load_scenario_pack
from .sdk_parity import build_sdk_parity_report
from .semantic_harness import (
    OUTPUT_FIELDS,
    PROMPT_FIELDS,
    REQUIRED_SDK_LANGUAGES,
    REVIEWED_LIVE_METADATA_FIELDS,
    build_semantic_harness_report,
)


DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET = Path("fixtures/a2/calibration/a2_semantic_judge_collection_packet.json")
SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"releasefoundry_live_[A-Za-z0-9_\-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


def build_semantic_judge_collection_packet(
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    run_dir: str | Path = DEFAULT_RUN_FIXTURES,
    observations_path: str | Path = DEFAULT_CALIBRATION_OBSERVATIONS,
) -> dict[str, Any]:
    """Build the public-safe packet that tells reviewers exactly what C4 must collect."""
    pack = load_scenario_pack(pack_path)
    scenarios = {scenario["id"]: scenario for scenario in pack["scenarios"]}
    fixtures_by_case = load_run_fixtures_by_case(run_dir)
    calibration_matrix = build_calibration_matrix(
        pack_path=pack_path,
        run_dir=run_dir,
        observations_path=observations_path,
    )
    sdk_parity = build_sdk_parity_report(pack_path=pack_path)
    harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
    language_by_case = _sdk_language_allocation(harness.get("cases", []))

    cases = []
    for case in harness.get("cases", []):
        case_id = str(case["case_id"])
        fixture = fixtures_by_case[case_id]
        scenario = scenarios[fixture["scenario_id"]]
        language = language_by_case[case_id]
        run = fixture.get("run", fixture)
        prompt_material = _prompt_material(scenario, case, run)
        prompt_hash = _hash12(prompt_material)
        cases.append(
            {
                "audit_case_id": f"semantic-{language}-{case_id}",
                "case_id": case_id,
                "scenario_id": fixture["scenario_id"],
                "scenario_title": scenario.get("title", ""),
                "scenario_family": scenario.get("family", ""),
                "fixture_ref": case.get("fixture_ref", ""),
                "calibration_focus": case.get("calibration_focus", []),
                "sdk_language": language,
                "sdk_input_path": case.get("sdk_input_paths", {}).get(language, ""),
                "prompt_template_id": harness["prompt_contract"]["template_id"],
                "prompt_input_fields": list(PROMPT_FIELDS),
                "prompt_material_sha256_12": prompt_hash,
                "prompt_public_summary": _prompt_public_summary(run),
                "expected": case.get("expected", {}),
                "local_judge": case.get("local_judge", {}),
                "offline_reference": case.get("offline_reference", {}),
                "risk_flags": case.get("risk_flags", []),
                "required_output_fields": list(OUTPUT_FIELDS),
                "required_metadata_fields": list(REVIEWED_LIVE_METADATA_FIELDS),
                "private_submission_hint": {
                    "raw_prompt_source": str(case.get("fixture_ref", "")),
                    "raw_payload_policy": "Build raw prompts/responses only under docs/evidence/private_refs/.",
                    "public_packet_contains_raw_prompt": False,
                    "public_packet_contains_raw_response": False,
                },
            }
        )

    allocation_counts = dict(sorted(Counter(case["sdk_language"] for case in cases).items()))
    readiness_checks = {
        "semantic_harness_ready": bool(harness.get("harness_ready")),
        "covers_calibration_cases": len(cases) == int(calibration_matrix.get("case_count", 0)) and bool(cases),
        "covers_python_and_typescript": set(REQUIRED_SDK_LANGUAGES).issubset(allocation_counts),
        "all_cases_have_prompt_hash": all(case["prompt_material_sha256_12"] for case in cases),
        "all_cases_have_fixture_ref": all(case["fixture_ref"] for case in cases),
        "all_cases_have_sdk_input_path": all(case["sdk_input_path"] for case in cases),
        "public_packet_omits_raw_prompt_and_response": True,
    }
    return {
        "schema_version": "a2.semantic_judge_collection_packet.v1",
        "packet_id": "a2_c4_semantic_judge_collection_packet",
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "scenario_pack": _display_path(pack_path),
        "calibration_observations_ref": _display_path(observations_path),
        "semantic_harness_ref": "fixtures/a2/results/a2_semantic_harness_report.json",
        "status": "ready_for_private_collection" if all(readiness_checks.values()) else "incomplete",
        "case_count": len(cases),
        "target_observation_count": len(cases),
        "readiness_checks": readiness_checks,
        "sdk_language_plan": {
            "required_languages": list(REQUIRED_SDK_LANGUAGES),
            "allocation_counts": allocation_counts,
            "assignment_rule": "Balance Python and TypeScript while forcing media/tool-output grounding coverage onto TypeScript.",
            "typescript_media_case_present": any(
                case["sdk_language"] == "typescript" and "media" in case.get("calibration_focus", [])
                for case in cases
            ),
        },
        "semantic_judge_contract": {
            "prompt_template_id": harness["prompt_contract"]["template_id"],
            "prompt_input_fields": list(PROMPT_FIELDS),
            "required_output_fields": list(OUTPUT_FIELDS),
            "required_metadata_fields": list(REVIEWED_LIVE_METADATA_FIELDS),
            "cost_fields": ["prompt_tokens", "completion_tokens", "estimated_usd"],
            "review_status_required": "reviewed",
            "source_for_merge": "llm_judge",
            "importer": "scripts/a2_import_semantic_judge.py",
            "merge_command_source": "scripts/a2_merge_calibration_observations.py --source llm_judge",
        },
        "private_evidence_policy": {
            "raw_private_path": "docs/evidence/private_refs/",
            "never_commit": [
                "API keys",
                "raw semantic judge prompts",
                "raw semantic judge responses",
                "reviewer notes with account or user data",
                "provider request/response payloads",
            ],
            "public_packet_fields": [
                "case ids",
                "SDK language allocation",
                "prompt template id",
                "prompt material hashes",
                "local/offline judge summaries",
                "required output and metadata fields",
            ],
        },
        "recommended_commands": [
            "python scripts/a2_import_semantic_judge.py --input docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --evidence-ref docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --output docs/evidence/private_refs/a2_semantic_judge_import.review.json",
            "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_semantic_judge_import.review.json --source llm_judge --min-count 6 --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
            "python -B scripts/a2_regenerate_fixtures.py --write",
        ],
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "purpose": "Prepare the exact six public-safe C4 semantic judge cases for private audited model-call collection.",
            "does_not_claim_c4_met": True,
        },
    }


def _sdk_language_allocation(cases: list[dict[str, Any]]) -> dict[str, str]:
    allocation: dict[str, str] = {}
    counts = Counter()
    for case in cases:
        case_id = str(case.get("case_id", ""))
        focus = set(str(item) for item in case.get("calibration_focus", []))
        if "media" in focus:
            language = "typescript"
        else:
            language = min(REQUIRED_SDK_LANGUAGES, key=lambda item: (counts[item], item))
        allocation[case_id] = language
        counts[language] += 1
    return allocation


def _prompt_material(scenario: dict[str, Any], case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": scenario.get("id", ""),
        "scenario_family": scenario.get("family", ""),
        "user_request": scenario.get("userTask", ""),
        "toolPolicy": scenario.get("toolPolicy", {}),
        "expectedBehaviors": scenario.get("expectedBehaviors", []),
        "failure_taxonomy": sorted(str(item) for item in scenario.get("failureSignals", [])),
        "agent_final_response": run.get("final_response") or run.get("text") or "",
        "agent_tool_calls": run.get("tool_calls") if isinstance(run.get("tool_calls"), list) else [],
        "observed_tool_results": _observed_tool_results(run),
        "expected": case.get("expected", {}),
    }


def _prompt_public_summary(run: dict[str, Any]) -> dict[str, Any]:
    tool_calls = run.get("tool_calls") if isinstance(run.get("tool_calls"), list) else []
    final_response = str(run.get("final_response") or run.get("text") or "")
    prompt_text = json.dumps(
        {
            "final_response": final_response,
            "tool_calls": tool_calls,
            "observed_tool_results": _observed_tool_results(run),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return {
        "tool_call_count": len(tool_calls),
        "tool_names": [str(call.get("tool") or call.get("name") or "") for call in tool_calls if isinstance(call, dict)],
        "tool_argument_keys": sorted(
            {
                str(key)
                for call in tool_calls
                if isinstance(call, dict)
                for key in _tool_args(call).keys()
            }
        ),
        "observed_tool_result_keys": sorted(_observed_tool_results(run)),
        "final_response_sha256_12": hashlib.sha256(final_response.encode("utf-8")).hexdigest()[:12]
        if final_response
        else "",
        "final_response_char_count": len(final_response),
        "contains_secret_like_text": _contains_secret_like(prompt_text),
        "public_packet_contains_raw_prompt": False,
        "public_packet_contains_raw_response": False,
    }


def _observed_tool_results(run: dict[str, Any]) -> dict[str, Any]:
    tool_results = run.get("tool_results")
    if isinstance(tool_results, dict):
        return tool_results
    if isinstance(tool_results, list):
        return {str(index): item for index, item in enumerate(tool_results)}
    return {}


def _tool_args(call: dict[str, Any]) -> dict[str, Any]:
    for key in ("args", "arguments"):
        value = call.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _hash12(value: dict[str, Any]) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _contains_secret_like(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_LIKE_PATTERNS)


def _display_path(path: str | Path) -> str:
    resolved = Path(path)
    try:
        return resolved.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return resolved.as_posix()
