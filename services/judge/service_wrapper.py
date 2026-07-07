"""SaaS-style service wrapper around the deterministic A2 judges."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .calibration import build_calibration_matrix
from .regression_replay import build_regression_replay_report
from .release_policy import ReleasePolicyError, evaluate_release_policy_config
from .result_persistence import build_result_record, stable_hash
from .runner import DEFAULT_SCENARIO_PACK, grade_run
from .scenario_selection import build_project_scenario_selection


CASE_ENDPOINT = "/internal/judge/case"
RUN_ENDPOINT = "/internal/judge/run"
BATCH_ENDPOINT = "/internal/judge/batch"
RELEASE_POLICY_ENDPOINT = "/internal/release-policy/evaluate"
REGRESSION_REPLAY_ENDPOINT = "/internal/regression/replay"
CALIBRATION_EVALUATE_ENDPOINT = "/internal/calibration/evaluate"
SERVICE_VERSION = "a2-judge-service-0.1.0"
DEFAULT_RELEASE_POLICY_CONFIG = Path("fixtures/a2/config/release_policies.json")
DEFAULT_GRADE_REPORT = Path("fixtures/a2/results/a2_g3_grade_results.json")
DEFAULT_RELEASE_GATE_REPORT = Path("fixtures/a2/results/a2_release_gate_report.json")
DEFAULT_CALIBRATION_MATRIX_REPORT = Path("fixtures/a2/results/a2_g3_calibration_matrix.json")
DEFAULT_CASE_BOOK_REPORT = Path("fixtures/a2/results/a2_case_book.json")


def judge_case(
    request: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Handle the pure-function equivalent of POST /internal/judge/case."""
    scenario_id = str(request["scenario_id"])
    run = request.get("run", request)
    case_id = str(request.get("case_id") or run.get("case_id") or scenario_id)
    result = grade_run(scenario_id, run, pack_path=pack_path, case_id=case_id)
    return {
        "schema_version": "a2.judge_service.case_response.v1",
        "endpoint": f"POST {CASE_ENDPOINT}",
        "service_version": SERVICE_VERSION,
        "tenant_id": _tenant_id(request),
        "org_id": _org_id(request),
        "project_id": str(request.get("project_id", "")),
        "run_id": str(request.get("run_id", "")),
        "case_id": case_id,
        "scenario_id": scenario_id,
        "scenario_pack_ref": Path(pack_path).as_posix(),
        "judge_version": _combined_judge_version(result),
        "input_hash": stable_hash({"scenario_id": scenario_id, "case_id": case_id, "run": run}),
        "output_hash": stable_hash(result),
        "passed": bool(result.get("passed")),
        "score": float(result.get("score", 0)),
        "primary_failure_class": str(result.get("primary_failure_class", "none")),
        "failure_classes": _failure_classes(result),
        "confidence": 1.0,
        "evidence_refs": request.get("evidence_refs", []),
        "blocking_findings": _blocking_findings(result),
        "recommended_actions": _recommended_actions(result),
        "judge_result": result,
    }


def judge_batch(
    request: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Handle the pure-function equivalent of POST /internal/judge/batch."""
    case_responses = [
        judge_case(
            {
                **case,
                "tenant_id": request.get("tenant_id", case.get("tenant_id", "")),
                "org_id": _org_id({**case, **request}),
                "project_id": request.get("project_id", case.get("project_id", "")),
                "run_id": request.get("run_id", case.get("run_id", "")),
            },
            pack_path=pack_path,
        )
        for case in request.get("cases", [])
        if isinstance(case, dict)
    ]
    grade_results = [response["judge_result"] for response in case_responses]
    grade_report = {
        "schema_version": "a2.grade_results.v1",
        "report_id": str(request.get("report_id", "a2_service_batch")),
        "dataset_id": str(request.get("dataset_id", "a2-service")),
        "scenario_pack": Path(pack_path).as_posix(),
        "total_cases": len(grade_results),
        "passed": sum(1 for result in grade_results if result.get("passed")),
        "failed": sum(1 for result in grade_results if not result.get("passed")),
        "grade_results": grade_results,
    }
    return {
        "schema_version": "a2.judge_service.batch_response.v1",
        "endpoint": f"POST {BATCH_ENDPOINT}",
        "service_version": SERVICE_VERSION,
        "tenant_id": _tenant_id(request),
        "org_id": _org_id(request),
        "project_id": str(request.get("project_id", "")),
        "run_id": str(request.get("run_id", "")),
        "scenario_pack_ref": Path(pack_path).as_posix(),
        "total_cases": len(case_responses),
        "passed": grade_report["passed"],
        "failed": grade_report["failed"],
        "case_results": case_responses,
        "grade_report": grade_report,
    }


def judge_run(
    request: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Handle the pure-function equivalent of POST /internal/judge/run."""
    cases = _run_cases(request)
    if not cases:
        raise ValueError("judge run request must include cases or a single scenario_id/run payload")

    batch = judge_batch(
        {
            **request,
            "cases": cases,
            "report_id": str(request.get("report_id", request.get("run_id", "a2_service_run"))),
        },
        pack_path=pack_path,
    )
    return {
        "schema_version": "a2.judge_service.run_response.v1",
        "endpoint": f"POST {RUN_ENDPOINT}",
        "service_version": SERVICE_VERSION,
        "tenant_id": _tenant_id(request),
        "org_id": _org_id(request),
        "project_id": str(request.get("project_id", "")),
        "run_id": str(request.get("run_id", "")),
        "scenario_pack_ref": Path(pack_path).as_posix(),
        "total_cases": batch["total_cases"],
        "passed": batch["passed"],
        "failed": batch["failed"],
        "run_summary": {
            "pass_rate": round((batch["passed"] / batch["total_cases"]) * 100, 4) if batch["total_cases"] else 0.0,
            "primary_failure_class_counts": _primary_failure_class_counts(batch["grade_report"]),
            "blocking_findings_count": sum(len(case.get("blocking_findings", [])) for case in batch["case_results"]),
        },
        "grade_report": batch["grade_report"],
        "case_results": batch["case_results"],
    }


def evaluate_release_policy(
    request: dict[str, Any],
    *,
    policy_config_path: str | Path = DEFAULT_RELEASE_POLICY_CONFIG,
    grade_report_path: str | Path = DEFAULT_GRADE_REPORT,
    release_gate_path: str | Path = DEFAULT_RELEASE_GATE_REPORT,
) -> dict[str, Any]:
    """Evaluate a configurable SaaS release policy for a project/environment."""
    grade_report = request.get("grade_report") or _read_json(grade_report_path)
    policy_evaluation = evaluate_release_policy_config(
        _read_json(policy_config_path),
        project_id=str(request.get("project_id", "")),
        environment=str(request.get("environment", "dev")),
        grade_report=grade_report,
        metrics=request.get("metrics"),
        release_candidate_id=str(request.get("release_candidate_id", request.get("run_id", ""))),
        waivers=request.get("waivers") if isinstance(request.get("waivers"), list) else None,
    )
    gate_report = dict(request.get("release_gate_report") or _read_json(release_gate_path))
    gate_report["policy_evaluation"] = policy_evaluation
    gate_report["release_candidate"] = {
        **gate_report.get("release_candidate", {}),
        "id": str(request.get("release_candidate_id", gate_report.get("release_candidate", {}).get("id", ""))),
    }
    return {
        "schema_version": "a2.judge_service.release_policy_response.v1",
        "endpoint": f"POST {RELEASE_POLICY_ENDPOINT}",
        "service_version": SERVICE_VERSION,
        "tenant_id": _tenant_id(request),
        "org_id": _org_id(request),
        "project_id": str(request.get("project_id", "")),
        "run_id": str(request.get("run_id", "")),
        "environment": str(request.get("environment", "dev")),
        "policy_evaluation": policy_evaluation,
        "release_gate": gate_report,
    }


def replay_regressions(
    request: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    calibration_matrix_path: str | Path = DEFAULT_CALIBRATION_MATRIX_REPORT,
    case_book_path: str | Path = DEFAULT_CASE_BOOK_REPORT,
) -> dict[str, Any]:
    """Handle the pure-function equivalent of POST /internal/regression/replay."""
    calibration_matrix = request.get("calibration_matrix") or _read_json(calibration_matrix_path)
    case_book = request.get("case_book_report") or request.get("case_book") or _read_json(case_book_path)
    report = build_regression_replay_report(
        calibration_matrix,
        case_book,
        pack_path=pack_path,
    )
    return {
        "schema_version": "a2.judge_service.regression_replay_response.v1",
        "endpoint": f"POST {REGRESSION_REPLAY_ENDPOINT}",
        "service_version": SERVICE_VERSION,
        "tenant_id": _tenant_id(request),
        "org_id": _org_id(request),
        "project_id": str(request.get("project_id", "")),
        "run_id": str(request.get("run_id", "")),
        "replay_report": report,
    }


def evaluate_calibration(
    request: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Handle the pure-function equivalent of POST /internal/calibration/evaluate."""
    matrix = request.get("calibration_matrix")
    if not isinstance(matrix, dict):
        matrix = build_calibration_matrix(
            pack_path=Path(request.get("pack_path", pack_path)),
            run_dir=Path(request.get("run_dir", "fixtures/a2/runs")),
            observations_path=Path(
                request.get("observations_path", "fixtures/a2/calibration/a2_g3_calibration_observations.json")
            ),
        )
    return {
        "schema_version": "a2.judge_service.calibration_response.v1",
        "endpoint": f"POST {CALIBRATION_EVALUATE_ENDPOINT}",
        "service_version": SERVICE_VERSION,
        "tenant_id": _tenant_id(request),
        "org_id": _org_id(request),
        "project_id": str(request.get("project_id", "")),
        "run_id": str(request.get("run_id", "")),
        "matrix_id": str(matrix.get("matrix_id", "")),
        "case_count": int(matrix.get("case_count", 0)),
        "source_coverage": matrix.get("source_coverage", {}),
        "agreement_summary": matrix.get("agreement_summary", {}),
        "cost_ledger": matrix.get("cost_ledger", []),
        "calibration_matrix": matrix,
    }


def select_project_scenarios(
    request: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    return build_project_scenario_selection(
        project_id=str(request.get("project_id", "")),
        environment=str(request.get("environment", "prod")),
        pack_path=pack_path,
    )


def post_internal_judge_case(payload: dict[str, Any]) -> dict[str, Any]:
    result = judge_case(payload)
    return _ok_response(CASE_ENDPOINT, payload, result["judge_result"], status_code=200)


def post_internal_judge_batch(payload: dict[str, Any]) -> dict[str, Any]:
    batch = judge_batch(payload)
    return _ok_response(BATCH_ENDPOINT, payload, batch["grade_report"], status_code=200)


def post_internal_judge_run(payload: dict[str, Any]) -> dict[str, Any]:
    result = judge_run(payload)
    return _ok_response(RUN_ENDPOINT, payload, result, status_code=200)


def post_internal_release_policy_evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    response = evaluate_release_policy(payload)
    result = response["release_gate"]
    return _ok_response(RELEASE_POLICY_ENDPOINT, payload, result, status_code=200)


def post_internal_regression_replay(payload: dict[str, Any]) -> dict[str, Any]:
    response = replay_regressions(payload)
    return _ok_response(REGRESSION_REPLAY_ENDPOINT, payload, response["replay_report"], status_code=200)


def post_internal_calibration_evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    response = evaluate_calibration(payload)
    return _ok_response(CALIBRATION_EVALUATE_ENDPOINT, payload, response["calibration_matrix"], status_code=200)


def handle_internal_request(endpoint: str, payload: dict[str, Any], *, method: str = "POST") -> dict[str, Any]:
    if method.upper() != "POST":
        return _error_response(endpoint, payload, 405, "method_not_allowed", f"{method} is not supported")
    try:
        if endpoint == CASE_ENDPOINT:
            return post_internal_judge_case(payload)
        if endpoint == RUN_ENDPOINT:
            return post_internal_judge_run(payload)
        if endpoint == BATCH_ENDPOINT:
            return post_internal_judge_batch(payload)
        if endpoint == RELEASE_POLICY_ENDPOINT:
            return post_internal_release_policy_evaluate(payload)
        if endpoint == REGRESSION_REPLAY_ENDPOINT:
            return post_internal_regression_replay(payload)
        if endpoint == CALIBRATION_EVALUATE_ENDPOINT:
            return post_internal_calibration_evaluate(payload)
    except (KeyError, ReleasePolicyError, ValueError) as exc:
        return _error_response(endpoint, payload, 400, "bad_request", str(exc))
    return _error_response(endpoint, payload, 404, "route_not_found", f"Unknown internal endpoint: {endpoint}")


def build_audit_record(
    response: dict[str, Any],
    *,
    kind: str,
    request: dict[str, Any],
    policy_hash: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    return build_result_record(
        response,
        org_id=str(response.get("tenant_id") or response.get("org_id") or _tenant_id(request)),
        project_id=str(response.get("project_id", request.get("project_id", ""))),
        run_id=str(response.get("run_id", request.get("run_id", ""))),
        case_id=str(response.get("case_id", request.get("case_id", ""))),
        kind=kind,
        judge_version=str(response.get("judge_version", SERVICE_VERSION)),
        policy_hash=policy_hash,
        input_payload=request,
        evidence_refs=response.get("evidence_refs", []),
        created_at=created_at,
    )


def _ok_response(endpoint: str, payload: dict[str, Any], result: dict[str, Any], *, status_code: int) -> dict[str, Any]:
    return {
        "schema_version": "a2.internal_service_response.v1",
        "ok": True,
        "status_code": status_code,
        "endpoint": endpoint,
        "request_id": str(payload.get("request_id", "")),
        "result": result,
        "service_context": _service_context(payload),
        "metadata": _service_metadata(),
    }


def _error_response(
    endpoint: str,
    payload: dict[str, Any],
    status_code: int,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": "a2.internal_service_response.v1",
        "ok": False,
        "status_code": status_code,
        "endpoint": endpoint,
        "request_id": str(payload.get("request_id", "")),
        "error": {"code": code, "message": message},
        "service_context": _service_context(payload),
        "metadata": _service_metadata(),
    }


def _service_context(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": _tenant_id(payload),
        "org_id": _org_id(payload),
        "project_id": str(payload.get("project_id", "")),
        "run_id": str(payload.get("run_id", "")),
        "release_candidate_id": str(payload.get("release_candidate_id", "")),
    }


def _tenant_id(payload: dict[str, Any]) -> str:
    return str(payload.get("tenant_id") or payload.get("org_id") or payload.get("organization_id") or "")


def _org_id(payload: dict[str, Any]) -> str:
    return str(payload.get("org_id") or payload.get("organization_id") or payload.get("tenant_id") or "")


def _service_metadata() -> dict[str, Any]:
    return {
        "service_version": SERVICE_VERSION,
        "deterministic": True,
        "requires_network": False,
        "requires_ashr_api_key": False,
        "does_not_execute_live_calls": True,
    }


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_cases(request: dict[str, Any]) -> list[dict[str, Any]]:
    raw_cases = request.get("cases")
    if isinstance(raw_cases, list):
        return [case for case in raw_cases if isinstance(case, dict)]

    run = request.get("run")
    if isinstance(run, dict):
        for key in ("cases", "case_results"):
            nested = run.get(key)
            if isinstance(nested, list):
                return [case for case in nested if isinstance(case, dict)]

    if request.get("scenario_id"):
        return [request]
    return []


def _primary_failure_class_counts(grade_report: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in grade_report.get("grade_results", []):
        if not isinstance(result, dict):
            continue
        failure_class = str(result.get("primary_failure_class", "none"))
        counts[failure_class] = counts.get(failure_class, 0) + 1
    return dict(sorted(counts.items()))


def _combined_judge_version(result: dict[str, Any]) -> str:
    versions = sorted(
        {
            str(item.get("judge_version", ""))
            for item in result.get("judge_results", [])
            if item.get("judge_version")
        }
    )
    return "+".join(versions) if versions else SERVICE_VERSION


def _failure_classes(result: dict[str, Any]) -> list[str]:
    failures = {
        str(item.get("failure_analysis", {}).get("primary_failure_class", "none"))
        for item in result.get("judge_results", [])
    }
    failures.discard("none")
    return sorted(failures)


def _blocking_findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    if result.get("passed"):
        return []
    return [
        {
            "type": "judge_failure",
            "severity": "major",
            "scenario_id": result.get("scenario_id", ""),
            "case_id": result.get("case_id", ""),
            "primary_failure_class": result.get("primary_failure_class", "wrong_intent"),
            "summary": "Deterministic A2 judge failed this case.",
        }
    ]


def _recommended_actions(result: dict[str, Any]) -> list[str]:
    if result.get("passed"):
        return []
    actions = []
    for item in result.get("judge_results", []):
        actions.extend(item.get("failure_analysis", {}).get("remediation", []))
    return sorted({str(action) for action in actions if str(action).strip()})
