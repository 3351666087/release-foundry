"""Public-safe C3 collection packet for ReleaseFoundry server-side grading."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .calibration import DEFAULT_CALIBRATION_OBSERVATIONS, load_calibration_observations, load_run_fixtures_by_case
from .coverage import DEFAULT_RUN_FIXTURES
from .runner import DEFAULT_SCENARIO_PACK, grade_run, load_scenario_pack


DEFAULT_RELEASEFOUNDRY_GRADING_CASE_MAP = Path("fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json")
DEFAULT_RELEASEFOUNDRY_GRADING_COLLECTION_PACKET = Path("fixtures/a2/calibration/a2_releasefoundry_grading_collection_packet.json")
SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"releasefoundry_live_[A-Za-z0-9_\-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


def build_releasefoundry_grading_collection_packet(
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    run_dir: str | Path = DEFAULT_RUN_FIXTURES,
    observations_path: str | Path = DEFAULT_CALIBRATION_OBSERVATIONS,
    case_map_path: str | Path = DEFAULT_RELEASEFOUNDRY_GRADING_CASE_MAP,
) -> dict[str, Any]:
    """Build the public-safe packet that tells reviewers exactly what C3 must collect."""
    pack = load_scenario_pack(pack_path)
    scenarios = {scenario["id"]: scenario for scenario in pack["scenarios"]}
    observations_payload = load_calibration_observations(observations_path)
    fixtures_by_case = load_run_fixtures_by_case(run_dir)
    case_map = _load_case_map(case_map_path)
    raw_id_by_case = {case_id: raw_id for raw_id, case_id in case_map.items()}

    cases = []
    for case in observations_payload.get("cases", []):
        case_id = str(case["case_id"])
        fixture = fixtures_by_case[case_id]
        scenario = scenarios[fixture["scenario_id"]]
        local = grade_run(
            fixture["scenario_id"],
            fixture.get("run", fixture),
            pack_path=pack_path,
            case_id=case_id,
        )
        cases.append(
            {
                "releasefoundry_test_id": raw_id_by_case.get(case_id, ""),
                "case_id": case_id,
                "scenario_id": fixture["scenario_id"],
                "scenario_title": scenario.get("title", ""),
                "scenario_family": scenario.get("family", ""),
                "fixture_ref": str(case.get("fixture_ref", "")),
                "calibration_focus": case.get("calibration_focus", []),
                "user_task": scenario.get("userTask", ""),
                "expected_behaviors": scenario.get("expectedBehaviors", []),
                "tool_policy_summary": _tool_policy_summary(scenario.get("toolPolicy", {})),
                "expected": fixture.get("expected", {}),
                "local_judge": {
                    "passed": local["passed"],
                    "primary_failure_class": local["primary_failure_class"],
                    "score": local["score"],
                    "judge_count": len(local.get("judge_results", [])),
                    "evidence_ref": "fixtures/a2/results/a2_g3_grade_results.json",
                },
                "run_summary": _run_summary(fixture.get("run", fixture)),
                "private_submission_hint": {
                    "use_fixture_ref": str(case.get("fixture_ref", "")),
                    "raw_payload_policy": "Build private ReleaseFoundry dataset/run payloads from fixture_ref only under docs/evidence/private_refs/.",
                    "public_packet_contains_raw_outputs": False,
                },
            }
        )

    readiness_checks = {
        "case_map_covers_calibration_cases": set(raw_id_by_case) == {case["case_id"] for case in cases},
        "all_cases_have_releasefoundry_test_id": all(case["releasefoundry_test_id"] for case in cases),
        "all_cases_have_local_judge": all(case["local_judge"]["judge_count"] == 5 for case in cases),
        "all_cases_have_fixture_ref": all(case["fixture_ref"] for case in cases),
        "public_packet_omits_raw_final_response": True,
    }
    return {
        "schema_version": "a2.releasefoundry_grading_collection_packet.v1",
        "packet_id": "a2_c3_releasefoundry_grading_collection_packet",
        "dataset_id": observations_payload.get("dataset_id", "a2-g3-calibration"),
        "scenario_pack": _display_path(pack_path),
        "case_map_ref": _display_path(case_map_path),
        "calibration_observations_ref": _display_path(observations_path),
        "status": "ready_for_private_collection" if all(readiness_checks.values()) else "incomplete",
        "case_count": len(cases),
        "readiness_checks": readiness_checks,
        "releasefoundry_result_contract": {
            "run_container": "response.run or response.runs[]",
            "test_container": "run.result.tests[]",
            "raw_test_id_field": "test_id",
            "action_result_field": "action_results",
            "scanner": "scripts/a2_scan_releasefoundry_grading_evidence.py",
            "importer": "scripts/a2_import_releasefoundry_grading.py",
            "review_status_required": "reviewed",
            "reviewer_receipt_required": "sha256:<64 lowercase hex>",
            "reviewed_at_unix_ms_required": "positive integer",
        },
        "private_evidence_policy": {
            "raw_private_path": "docs/evidence/private_refs/",
            "never_commit": [
                "API keys",
                "raw ReleaseFoundry responses",
                "raw final responses from private submissions",
                "account payloads",
            ],
            "public_packet_fields": [
                "case ids",
                "ReleaseFoundry test ids",
                "tool names",
                "tool argument keys",
                "final response hash and length",
                "local judge summary",
            ],
        },
        "recommended_commands": [
            "python scripts/a2_scan_releasefoundry_grading_evidence.py --input docs/evidence/private_refs/a2_releasefoundry_get_run.redacted.json --case-map fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json",
            "python scripts/a2_import_releasefoundry_grading.py --input docs/evidence/private_refs/a2_releasefoundry_get_run.redacted.json --case-map fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json --identity-file docs/evidence/private_refs/a2_releasefoundry_dataset_identity.private.json --identity-receipt docs/evidence/a2_releasefoundry_dataset_identity_receipt.json --evidence-ref docs/evidence/private_refs/a2_releasefoundry_get_run.redacted.json --review-status reviewed --reviewer-receipt \"$A2_REVIEWER_RECEIPT\" --reviewed-at-unix-ms \"$A2_REVIEWED_AT_UNIX_MS\" --require-reviewed --require-complete --output docs/evidence/private_refs/a2_releasefoundry_grading_import.review.json",
            "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_releasefoundry_grading_import.review.json --source releasefoundry_grading --min-count 6 --require-reviewed --require-complete --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
            "python -B scripts/a2_regenerate_fixtures.py --write",
        ],
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "purpose": "Prepare the exact six public-safe C3 cases for private ReleaseFoundry server-side grading collection.",
        },
    }


def _load_case_map(path: str | Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("case map must be a JSON object")
    return {str(key): str(value) for key, value in payload.items()}


def _tool_policy_summary(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "required_tools": _policy_tools(policy.get("required", [])),
        "optional_tools": _policy_tools(policy.get("optional", [])),
        "forbidden_tools": _policy_tools(policy.get("forbidden", [])),
        "order": _policy_tools(policy.get("order", [])),
    }


def _policy_tools(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    tools = []
    for item in items:
        if isinstance(item, dict):
            tools.append(str(item.get("tool") or item.get("name") or ""))
        else:
            tools.append(str(item))
    return [tool for tool in tools if tool]


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    tool_calls = run.get("tool_calls") if isinstance(run.get("tool_calls"), list) else []
    final_response = str(run.get("final_response") or run.get("text") or "")
    run_text = json.dumps(run, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
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
        "final_response_sha256_12": hashlib.sha256(final_response.encode("utf-8")).hexdigest()[:12] if final_response else "",
        "final_response_char_count": len(final_response),
        "contains_secret_like_text": _contains_secret_like(run_text),
        "public_packet_contains_raw_final_response": False,
    }


def _tool_args(call: dict[str, Any]) -> dict[str, Any]:
    for key in ("args", "arguments"):
        value = call.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _contains_secret_like(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_LIKE_PATTERNS)


def _display_path(path: str | Path) -> str:
    resolved = Path(path)
    try:
        return resolved.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return resolved.as_posix()
