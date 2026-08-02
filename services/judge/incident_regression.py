"""Public-safe incident summaries promoted into A2 regression candidates."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .result_persistence import stable_hash
from .runner import DEFAULT_SCENARIO_PACK, grade_run, load_scenario_pack
from .schemas import CANONICAL_FAILURE_CLASSES, canonical_primary_failure_class


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INCIDENT_SUMMARY = Path("fixtures/a2/incidents/a2_prod_incident_summary.json")
DEFAULT_REPORT_ID = "a2_incident_regression_candidates"
PRIVATE_FIELD_NAMES = {
    "api_key",
    "authorization",
    "headers",
    "raw_payload",
    "raw_prompt",
    "raw_request",
    "raw_response",
    "request",
    "request_payload",
    "response",
    "response_payload",
    "secret",
    "token",
}
FORBIDDEN_TEXT_PATTERNS: dict[str, re.Pattern[str]] = {
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    "secret_key": re.compile(r"\b(?:sk-[A-Za-z0-9]{8,}|tp_[A-Za-z0-9_\-]{8,})\b"),
    "email_address": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
}
PUBLIC_FIXTURE_PREFIXES = ("fixtures/a2/runs/",)
PUBLIC_FIXTURE_ROOT = (ROOT / "fixtures/a2/runs").resolve()
PUBLIC_EVIDENCE_PREFIXES = (
    "docs/evidence/private_refs/",
    "docs/evidence/",
    "fixtures/",
    "packages/scenarios/",
)
_SHA256_REF = re.compile(r"^sha256:[a-f0-9]{64}$")


def build_incident_regression_candidate_report(
    incident_summary: dict[str, Any] | str | Path = DEFAULT_INCIDENT_SUMMARY,
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Convert redacted production incident summaries into case-book review candidates."""
    payload, source_ref = _load_incident_summary(incident_summary)
    incidents = _incident_items(payload)
    scenario_pack = load_scenario_pack(_resolve_path(pack_path))
    scenarios_by_id = {
        str(scenario.get("id", "")): scenario for scenario in scenario_pack.get("scenarios", [])
    }
    candidates = [
        _candidate_from_incident(
            incident,
            source_ref=source_ref,
            pack_path=pack_path,
            scenarios_by_id=scenarios_by_id,
            incident_safety=_public_safety(incident),
        )
        for incident in incidents
    ]
    candidates = [candidate for candidate in candidates if candidate]
    public_safety = _public_safety(payload)
    ready_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("public_safe") is True
        and candidate.get("ready_for_case_book_review") is True
    ]
    report = {
        "schema_version": "a2.incident_regression_candidates.v1",
        "report_id": DEFAULT_REPORT_ID,
        "source_incident_count": len(incidents),
        "source_incidents": [
            _source_incident_summary(incident, source_ref, _public_safety(incident))
            for incident in incidents
        ],
        "candidate_count": len(candidates),
        "ready_candidate_count": len(ready_candidates),
        "ready_for_case_book_review": bool(ready_candidates) and public_safety["safe"],
        "public_safety": public_safety,
        "candidates": candidates,
        "metadata": {
            "deterministic": True,
            "purpose": "Turn redacted production incidents into reviewer-visible A2 regression candidates.",
            "does_not_execute_live_calls": True,
            "does_not_read_private_evidence": True,
            "candidate_policy": "Candidates require case-book owner review and reviewed external evidence before C5 maturity.",
        },
    }
    return seal_incident_regression_candidate_report(report)


def seal_incident_regression_candidate_report(
    report: dict[str, Any],
) -> dict[str, Any]:
    """Bind a candidate report to its exact public content."""
    if not isinstance(report, dict):
        raise TypeError("incident candidate report must be an object")
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    return {**core, "artifact_hash": stable_hash(core)}


def verify_incident_regression_candidate_report(
    report: dict[str, Any],
) -> str:
    """Verify and return the candidate report content hash."""
    if not isinstance(report, dict):
        raise TypeError("incident candidate report must be an object")
    artifact_hash = report.get("artifact_hash")
    if not isinstance(artifact_hash, str) or not _SHA256_REF.fullmatch(artifact_hash):
        raise ValueError(
            "incident candidate report artifact_hash must be a canonical sha256 reference"
        )
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    if stable_hash(core) != artifact_hash:
        raise ValueError(
            "incident candidate report artifact_hash does not match report content"
        )
    return artifact_hash


def _candidate_from_incident(
    incident: dict[str, Any],
    *,
    source_ref: str,
    pack_path: str | Path,
    scenarios_by_id: dict[str, dict[str, Any]],
    incident_safety: dict[str, Any],
) -> dict[str, Any] | None:
    failed_case = incident.get("failed_case", {})
    if not isinstance(failed_case, dict):
        return None

    fixture_ref = _public_fixture_ref(failed_case.get("fixture_ref", ""))
    fixture = _load_fixture(fixture_ref) if fixture_ref else {}
    scenario_id = str(failed_case.get("scenario_id") or fixture.get("scenario_id", "")).strip()
    case_id = str(failed_case.get("case_id") or fixture.get("case_id", "")).strip()
    if not scenario_id or not case_id:
        return None

    grade = _grade_fixture(fixture, pack_path=pack_path) if fixture else {}
    failure_class = _failure_class(failed_case, grade)
    expected = {
        "passed": False,
        "primary_failure_class": failure_class,
    }
    scenario = scenarios_by_id.get(scenario_id, {})
    evidence_refs = _evidence_refs(incident, fixture_ref, source_ref)
    replayable_fixture = bool(fixture and fixture_ref)
    ready = bool(incident_safety["safe"] and replayable_fixture and failure_class != "none")
    incident_id = str(incident.get("incident_id", "")).strip()
    return {
        "regression_id": f"incident-regression-{_slug(incident_id or case_id)}",
        "case_id": case_id,
        "scenario_id": scenario_id,
        "fixture_ref": fixture_ref,
        "fixture_sha256": stable_hash(fixture) if fixture else "",
        "status": "candidate",
        "severity": str(incident.get("severity", "high")),
        "source": "production_incident",
        "incident_id": incident_id,
        "environment": str(incident.get("environment", "")),
        "scenario_title": str(scenario.get("title", "")),
        "scenario_family": str(scenario.get("family", "")),
        "scenario_tags": [str(tag) for tag in scenario.get("tags", [])],
        "calibration_focus": _strings(incident.get("regression_intent", {}).get("calibration_focus")),
        "expected": expected,
        "local_judge": _local_judge_summary(grade),
        "releasefoundry_grading": _missing_source("releasefoundry_grading", "releasefoundry server-side grading"),
        "semantic_or_llm_judge": _missing_source("llm_judge", "audited semantic judge"),
        "disagreement_pairs": [],
        "regression_assertion": _regression_assertion(incident, failure_class),
        "reviewer_note": _reviewer_note(incident, case_id, scenario_id, failure_class),
        "evidence_refs": evidence_refs,
        "public_safe": bool(incident_safety["safe"]),
        "ready_for_case_book_review": ready,
        "case_book_candidate": True,
        "promotion_blockers": _promotion_blockers(ready),
    }


def _load_incident_summary(
    incident_summary: dict[str, Any] | str | Path,
) -> tuple[dict[str, Any], str]:
    if isinstance(incident_summary, dict):
        return incident_summary, "inline"
    path = Path(incident_summary)
    payload = json.loads(_resolve_path(path).read_text(encoding="utf-8"))
    return payload, _display_path(path)


def _incident_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "incidents" not in payload:
        return [payload]
    incidents = payload["incidents"]
    if not isinstance(incidents, list):
        raise ValueError("incidents must be a list")
    for index, incident in enumerate(incidents):
        if not isinstance(incident, dict):
            raise ValueError(f"incidents[{index}] must be an object")
    return incidents


def _source_incident_summary(
    incident: dict[str, Any],
    source_ref: str,
    safety: dict[str, Any],
) -> dict[str, Any]:
    include_text = bool(safety["safe"])
    return {
        "incident_id": str(incident.get("incident_id", "")),
        "source_ref": source_ref,
        "environment": str(incident.get("environment", "")),
        "reported_at": str(incident.get("reported_at", "")),
        "title": str(incident.get("title", "")) if include_text else "",
        "summary": str(incident.get("summary", "")) if include_text else "",
        "public_safe": bool(safety["safe"]),
    }


def _public_safety(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, sort_keys=True)
    private_field_names = sorted(_private_field_names(payload))
    forbidden_patterns = sorted(
        name for name, pattern in FORBIDDEN_TEXT_PATTERNS.items() if pattern.search(text)
    )
    checks = {
        "declares_public_safe": _declares_public_safe(payload),
        "no_private_payload_keys": not private_field_names,
        "no_forbidden_text_patterns": not forbidden_patterns,
        "fixture_refs_are_public": _fixture_refs_are_public(payload),
        "evidence_refs_are_reference_only": _evidence_refs_are_reference_only(payload),
    }
    return {
        "safe": all(checks.values()),
        "checks": checks,
        "private_field_names": private_field_names,
        "forbidden_pattern_names": forbidden_patterns,
        "redaction_policy": {
            "commit_only": [
                "incident summaries already marked public_safe",
                "stable case_id/scenario_id/fixture_ref join keys",
                "failure class and reviewer notes",
                "references to private evidence, not private evidence contents",
            ],
            "never_commit": [
                "API keys",
                "authorization tokens",
                "raw prompts",
                "raw model responses",
                "tenant emails",
                "account payloads",
            ],
        },
    }


def _declares_public_safe(payload: dict[str, Any]) -> bool:
    incidents = _incident_items(payload)
    if not incidents:
        return False
    for incident in incidents:
        redaction = incident.get("redaction", {})
        if not isinstance(redaction, dict) or redaction.get("public_safe") is not True:
            return False
    return True


def _private_field_names(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower()
            if key_text in PRIVATE_FIELD_NAMES:
                found.add(key_text)
            found.update(_private_field_names(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_private_field_names(item))
    return found


def _fixture_refs_are_public(value: Any) -> bool:
    refs = _values_for_key(value, "fixture_ref")
    return all(_public_fixture_ref(ref) for ref in refs if str(ref).strip())


def _evidence_refs_are_reference_only(value: Any) -> bool:
    refs = _values_for_key(value, "evidence_refs") + _values_for_key(value, "private_evidence_ref")
    flat_refs: list[str] = []
    for ref in refs:
        if isinstance(ref, list):
            flat_refs.extend(str(item) for item in ref)
        else:
            flat_refs.append(str(ref))
    return all(
        bool(_public_evidence_ref(ref))
        for ref in flat_refs
        if ref.strip()
    )


def _values_for_key(value: Any, target_key: str) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) == target_key:
                values.append(nested)
            values.extend(_values_for_key(nested, target_key))
    elif isinstance(value, list):
        for item in value:
            values.extend(_values_for_key(item, target_key))
    return values


def _load_fixture(fixture_ref: str) -> dict[str, Any]:
    path = (ROOT / Path(*PurePosixPath(fixture_ref).parts)).resolve()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _public_fixture_ref(value: Any) -> str:
    normalized = _safe_repository_ref(value)
    if not normalized or not normalized.startswith(PUBLIC_FIXTURE_PREFIXES):
        return ""
    if PurePosixPath(normalized).suffix.lower() != ".json":
        return ""
    target = (ROOT / Path(*PurePosixPath(normalized).parts)).resolve()
    try:
        target.relative_to(PUBLIC_FIXTURE_ROOT)
    except ValueError:
        return ""
    return normalized


def _public_evidence_ref(value: Any) -> str:
    normalized = _safe_repository_ref(value)
    if not normalized:
        return ""
    if any(normalized.startswith(prefix) for prefix in PUBLIC_EVIDENCE_PREFIXES):
        return normalized
    return ""


def _safe_repository_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw_ref = value.strip()
    windows_path = PureWindowsPath(raw_ref)
    normalized_ref = PurePosixPath(raw_ref.replace("\\", "/"))
    if (
        normalized_ref.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in normalized_ref.parts
    ):
        return ""
    return normalized_ref.as_posix()


def _grade_fixture(fixture: dict[str, Any], *, pack_path: str | Path) -> dict[str, Any]:
    if not fixture.get("scenario_id"):
        return {}
    return grade_run(
        str(fixture["scenario_id"]),
        fixture.get("run", fixture),
        pack_path=_resolve_path(pack_path),
        case_id=fixture.get("case_id"),
    )


def _failure_class(failed_case: dict[str, Any], grade: dict[str, Any]) -> str:
    candidates = [
        str(failed_case.get("expected_primary_failure_class", "")),
        str(failed_case.get("observed_failure_class", "")),
        str(grade.get("primary_failure_class", "")),
    ]
    failures = [candidate for candidate in candidates if candidate and candidate != "none"]
    if not failures:
        return "none"
    if failures[0] in CANONICAL_FAILURE_CLASSES:
        return failures[0]
    return canonical_primary_failure_class(failures)


def _local_judge_summary(grade: dict[str, Any]) -> dict[str, Any]:
    if not grade:
        return {
            "available": False,
            "status": "missing_fixture",
            "source": "local_judge",
            "provider": "services.judge.runner.grade_run",
            "passed": None,
            "primary_failure_class": "",
            "score": None,
            "confidence": None,
            "rationale": "",
            "evidence_ref": "",
        }
    return {
        "available": True,
        "status": "available",
        "source": "local_judge",
        "provider": "services.judge.runner.grade_run",
        "passed": grade.get("passed"),
        "primary_failure_class": grade.get("primary_failure_class", ""),
        "score": grade.get("score"),
        "confidence": 1.0,
        "rationale": "Deterministic local A2 judge replay of the incident fixture.",
        "evidence_ref": "fixtures/a2/results/a2_g3_grade_results.json",
    }


def _missing_source(source: str, provider: str) -> dict[str, Any]:
    return {
        "available": False,
        "status": "missing_review",
        "source": source,
        "provider": provider,
        "passed": None,
        "primary_failure_class": "",
        "score": None,
        "confidence": None,
        "rationale": "",
        "evidence_ref": "",
    }


def _regression_assertion(incident: dict[str, Any], failure_class: str) -> str:
    intent = incident.get("regression_intent", {})
    if isinstance(intent, dict) and str(intent.get("assertion", "")).strip():
        return str(intent["assertion"])
    return f"Keep production incident failure_class={failure_class} replayable as an A2 regression candidate."


def _reviewer_note(
    incident: dict[str, Any],
    case_id: str,
    scenario_id: str,
    failure_class: str,
) -> str:
    incident_id = str(incident.get("incident_id", ""))
    return (
        f"{incident_id} maps to {case_id} / {scenario_id} with local failure_class={failure_class}. "
        "Keep it as a case-book candidate until A2 owner review and external evidence decide whether it should "
        "be promoted into the mature C5 replay set."
    )


def _evidence_refs(incident: dict[str, Any], fixture_ref: str, source_ref: str) -> list[str]:
    refs = [fixture_ref]
    if source_ref == "inline":
        refs.append(source_ref)
    else:
        refs.append(_public_evidence_ref(source_ref))
    refs.extend(
        safe_ref
        for ref in incident.get("evidence_refs", [])
        if (safe_ref := _public_evidence_ref(ref))
    )
    redaction = incident.get("redaction", {})
    if isinstance(redaction, dict) and str(redaction.get("private_evidence_ref", "")).strip():
        refs.append(_public_evidence_ref(redaction["private_evidence_ref"]))
    return sorted({ref for ref in refs if ref})


def _promotion_blockers(ready_for_review: bool) -> list[str]:
    blockers = ["needs_case_book_owner_review", "needs_reviewed_releasefoundry_or_audited_semantic_evidence"]
    if not ready_for_review:
        blockers.insert(0, "needs_public_safety_or_replayable_fixture_fix")
    return blockers


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "incident"


def _resolve_path(path: str | Path) -> Path:
    target = Path(path)
    if target.is_absolute():
        return target
    return ROOT / target


def _display_path(path: str | Path) -> str:
    target = _resolve_path(path)
    try:
        return target.relative_to(ROOT).as_posix()
    except ValueError:
        return "external_incident_summary"
