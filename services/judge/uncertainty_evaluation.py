"""Executable uncertainty-routing facade for local and external evaluation."""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from .bundle_evaluation import evaluate_a1_bundle
from .evaluation_trust_policy import normalize_evaluation_trust_policy
from .provider_gateway import ProviderGateway
from .release_gate import (
    RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_REF,
    MODALITY_RELEASE_BOUNDARIES,
    _multimodal_qualification_blockers,
)
from .result_persistence import stable_hash
from .uncertainty_router import build_uncertainty_route


SCHEMA_VERSION = "a2.uncertainty_evaluation.v1"


def evaluate_with_uncertainty_routing(
    request: dict[str, Any],
    *,
    label: dict[str, Any],
    calibration_report: dict[str, Any] | None,
    releasefoundry_available: bool,
    releasefoundry_mutation_authorized: bool = False,
    gateway: ProviderGateway | None = None,
    key_resolver: Callable[[str], bytes] | None = None,
    now_unix_ms: int | None = None,
    persistence_connection: sqlite3.Connection | None = None,
    quality_trust_policy: dict[str, Any] | None = None,
    evidence_complete: bool = True,
    out_of_scope: bool = False,
    historical_critical_regression: bool = False,
    novel_failure_type: bool = False,
    multimodal_qualification: dict[str, Any] | None = None,
    multimodal_expected_bindings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve locally, query a configured teacher once, or preserve uncertainty.

    This facade does not replace :func:`evaluate_a1_bundle`. It adds an explicit
    routing and mutation-authorization layer in front of that strict Provider
    path. ``ProviderGateway`` is a generic model transport, not the ReleaseFoundry testing
    API. Its result may record teacher consensus or conflict, but it may not be
    promoted to an official ReleaseFoundry comparison without a verified ReleaseFoundry receipt.
    """
    if not isinstance(request, dict):
        raise ValueError("request_must_be_object")
    if not isinstance(releasefoundry_available, bool):
        raise ValueError("releasefoundry_available_must_be_boolean")
    if not isinstance(releasefoundry_mutation_authorized, bool):
        raise ValueError("releasefoundry_mutation_authorized_must_be_boolean")

    release_modalities = _release_modalities(label)
    video_provider_unverified = "video" in release_modalities
    external_teacher_route_eligible = releasefoundry_available and not video_provider_unverified
    official_releasefoundry_adapter_configured = False
    effective_releasefoundry_available = (
        external_teacher_route_eligible and official_releasefoundry_adapter_configured
    )
    route_arguments = {
        "label": label,
        "calibration_report": calibration_report,
        "releasefoundry_available": external_teacher_route_eligible,
        "evidence_complete": evidence_complete,
        "out_of_scope": out_of_scope,
        "historical_critical_regression": historical_critical_regression,
        "novel_failure_type": novel_failure_type,
    }
    initial_route = build_uncertainty_route(**route_arguments)
    _verify_case_binding(request, initial_route)
    request_fingerprint = _request_fingerprint(request)
    media_gate = _media_release_gate(
        release_modalities,
        multimodal_qualification=multimodal_qualification,
        multimodal_expected_bindings=multimodal_expected_bindings,
    )

    final_route = initial_route
    teacher_evaluation = None
    execution_status = _skipped_status(
        initial_route,
        releasefoundry_available=releasefoundry_available,
        video_provider_unverified=video_provider_unverified,
    )
    provider_call_attempted = False

    if initial_route["decision"]["next_destination"] == "releasefoundry_teacher":
        if not releasefoundry_mutation_authorized:
            execution_status = "awaiting_external_mutation_authorization"
        elif gateway is None or key_resolver is None or now_unix_ms is None:
            execution_status = "teacher_runtime_not_configured"
            final_route = build_uncertainty_route(
                **{**route_arguments, "releasefoundry_available": False}
            )
        else:
            provider_call_attempted = True
            try:
                teacher_evaluation = evaluate_a1_bundle(
                    request,
                    gateway=gateway,
                    key_resolver=key_resolver,
                    now_unix_ms=now_unix_ms,
                    persistence_connection=persistence_connection,
                    quality_trust_policy=normalize_evaluation_trust_policy(
                        quality_trust_policy
                    ),
                )
            except Exception:
                execution_status = "teacher_execution_failed"
                final_route = build_uncertainty_route(
                    **{**route_arguments, "releasefoundry_available": False}
                )
            else:
                teacher_state = _teacher_state(label, teacher_evaluation)
                if teacher_state is None:
                    execution_status = "teacher_result_unusable"
                    final_route = build_uncertainty_route(
                        **{**route_arguments, "releasefoundry_available": False}
                    )
                else:
                    execution_status = "teacher_result_observed"
                    final_route = build_uncertainty_route(
                        **{**route_arguments, "releasefoundry_available": False},
                        teacher_state=teacher_state,
                    )

    decision = _decision(final_route, media_gate)
    teacher_summary = _teacher_summary(
        teacher_evaluation,
        request=request,
        gateway=gateway,
    )
    core = {
        "schema_version": SCHEMA_VERSION,
        "case_id": initial_route["case_id"],
        "label_hash": initial_route["label_hash"],
        "request_fingerprint": request_fingerprint,
        "initial_route": initial_route,
        "final_route": final_route,
        "media_release_gate": media_gate,
        "teacher_evaluation": teacher_summary,
        "execution": {
            "status": execution_status,
            "releasefoundry_declared_available": releasefoundry_available,
            "releasefoundry_effectively_available": effective_releasefoundry_available,
            "external_teacher_route_eligible": external_teacher_route_eligible,
            "generic_teacher_configured": (
                gateway is not None
                and key_resolver is not None
                and now_unix_ms is not None
            ),
            "official_releasefoundry_adapter_configured": official_releasefoundry_adapter_configured,
            "official_releasefoundry_receipt_observed": False,
            "releasefoundry_mutation_authorized": releasefoundry_mutation_authorized,
            "provider_call_attempted": provider_call_attempted,
            "provider_called": bool(
                teacher_summary and teacher_summary["provider_called"]
            ),
            "facade_retry_count": 0,
        },
        "decision": decision,
        "metadata": {
            "public_safe": True,
            "raw_request_included": False,
            "raw_provider_payload_included": False,
            "secrets_included": False,
            "releasefoundry_output_is_human_gold": False,
            "generic_provider_output_is_releasefoundry_receipt": False,
            "generated_media_proves_caller_native_submission": False,
            "video_provider_state": (
                "provider_unverified" if video_provider_unverified else "not_in_scope"
            ),
        },
    }
    return {**core, "evaluation_hash": stable_hash(core)}


def _verify_case_binding(
    request: dict[str, Any],
    route: dict[str, Any],
) -> None:
    request_case_id = request.get("case_id")
    if not isinstance(request_case_id, str) or not request_case_id:
        raise ValueError("request_case_id_missing")
    if request_case_id != route["case_id"]:
        raise ValueError("label_request_case_id_mismatch")


def _request_fingerprint(request: dict[str, Any]) -> str:
    bundle = request.get("authenticated_evidence_bundle")
    identity = {
        "scope": {
            key: request.get(key)
            for key in (
                "organization_id",
                "tenant_id",
                "workspace_id",
                "project_id",
                "environment_id",
            )
        },
        "run_id": request.get("run_id"),
        "case_id": request.get("case_id"),
        "scenario_id": request.get("scenario_id"),
        "provider_id": request.get("provider_id"),
        "model_id": request.get("model_id"),
        "policy_version": request.get("policy_version"),
        "bundle_digest": stable_hash(bundle) if isinstance(bundle, dict) else "",
    }
    return stable_hash(identity)


def _release_modalities(label: dict[str, Any]) -> list[str]:
    evidence = label.get("evidence_locations")
    if not isinstance(evidence, list):
        return ["text"]
    mapped: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        modality = item.get("modality")
        if modality == "document":
            modality = "file"
        elif modality == "tool":
            modality = "text"
        if modality in MODALITY_RELEASE_BOUNDARIES and modality not in mapped:
            mapped.append(modality)
    return mapped or ["text"]


def _media_release_gate(
    modalities: list[str],
    *,
    multimodal_qualification: dict[str, Any] | None,
    multimodal_expected_bindings: dict[str, Any] | None,
) -> dict[str, Any]:
    gaps: list[str] = []
    if "image" in modalities:
        for blocker in _multimodal_qualification_blockers(
            modalities,
            multimodal_qualification,
            multimodal_expected_bindings,
        ):
            gaps.extend(str(item) for item in blocker.get("gaps", []) if item)
    generated_only = sorted(set(modalities) & {"audio", "file"})
    if generated_only:
        gaps.append(
            "ReleaseFoundry generated-artifact verification does not prove caller-native "
            "input or release qualification: "
            + ", ".join(generated_only)
        )
    if "video" in modalities:
        gaps.append(
            "ReleaseFoundry video remains provider_unverified/unreliable and requires "
            "retest or human review"
        )
    qualified = not gaps
    return {
        "modalities": modalities,
        "qualified": qualified,
        "gaps": gaps,
        "modality_boundaries": [
            {"modality": modality, **MODALITY_RELEASE_BOUNDARIES[modality]}
            for modality in modalities
        ],
        "evidence_refs": (
            [RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_REF]
            if any(modality != "text" for modality in modalities)
            else []
        ),
        "automatic_release_allowed": qualified,
    }


def _skipped_status(
    route: dict[str, Any],
    *,
    releasefoundry_available: bool,
    video_provider_unverified: bool,
) -> str:
    destination = route["decision"]["next_destination"]
    if destination == "local_judge":
        return "resolved_by_local_judge"
    if video_provider_unverified:
        return "video_provider_unverified"
    if not releasefoundry_available:
        return "releasefoundry_unavailable"
    return "human_review_required"


def _teacher_state(
    label: dict[str, Any],
    evaluation: dict[str, Any],
) -> str | None:
    if evaluation.get("provider_called") is not True:
        return None
    if evaluation.get("evidence_complete") is not True:
        return None
    judge = evaluation.get("judge")
    if not isinstance(judge, dict) or judge.get("outcome") not in {"pass", "fail"}:
        return None
    passed = judge.get("passed")
    if not isinstance(passed, bool):
        return None
    release_gate = evaluation.get("release_gate")
    if not isinstance(release_gate, dict):
        return None
    blockers = {
        str(item)
        for item in release_gate.get("blocking_reasons", [])
        if item
    }
    judge_failures = {
        str(item)
        for item in judge.get("failure_classes", [])
        if item
    }
    if blockers - judge_failures:
        return None
    return "consensus" if passed is label["passed"] else "conflict"


def _teacher_summary(
    evaluation: dict[str, Any] | None,
    *,
    request: dict[str, Any],
    gateway: ProviderGateway | None,
) -> dict[str, Any] | None:
    if not isinstance(evaluation, dict):
        return None
    judge = evaluation.get("judge")
    if not isinstance(judge, dict):
        judge = {}
    provider_id = str(
        evaluation.get("provider_provenance", {}).get("provider_id")
        or request.get("provider_id")
        or ""
    )
    provider = gateway.providers.get(provider_id) if gateway is not None else None
    return {
        "schema_version": evaluation.get("schema_version", ""),
        "decision": evaluation.get("decision", "INCOMPLETE"),
        "provider_called": evaluation.get("provider_called") is True,
        "evidence_complete": evaluation.get("evidence_complete") is True,
        "source": {
            "provider_id": provider_id,
            "model_id": str(
                evaluation.get("provider_provenance", {}).get("model_id")
                or request.get("model_id")
                or ""
            ),
            "protocol": provider.protocol if provider is not None else "",
            "teacher_authority": "generic_provider",
            "transport_mode": "provider_gateway",
            # The current release-decision path submits the Judge prompt and
            # authorized derived evidence as text parts. It does not submit the
            # caller's original image, audio, file, or video bytes.
            "submitted_modalities": ["text"],
            "caller_native_media_submitted": False,
            "official_releasefoundry_receipt_observed": False,
        },
        "judge": {
            "passed": judge.get("passed") if isinstance(judge.get("passed"), bool) else None,
            "outcome": judge.get("outcome", "unknown"),
            "score": judge.get("score", 0),
            "failure_classes": list(judge.get("failure_classes", [])),
        },
        "request_fingerprint": evaluation.get("request_fingerprint", ""),
        "decision_record_hash": evaluation.get("decision_record_hash", ""),
    }


def _decision(
    route: dict[str, Any],
    media_gate: dict[str, Any],
) -> dict[str, Any]:
    route_decision = route["decision"]
    resolution_state = route_decision["resolution_state"]
    next_destination = route_decision["next_destination"]
    release_action = route_decision["release_recommendation"]
    if not media_gate["qualified"]:
        resolution_state = "uncertain"
        if "video" in media_gate["modalities"]:
            next_destination = "human_review"
            if release_action != "block":
                release_action = "human_review"
        elif release_action not in {"block", "human_review", "retest"}:
            release_action = "retest"
    automatic_release_allowed = bool(
        route_decision["automatic_release_allowed"]
        and media_gate["qualified"]
        and release_action == "allow"
    )
    return {
        "resolution_state": resolution_state,
        "next_destination": next_destination,
        "release_action": release_action,
        "automatic_release_allowed": automatic_release_allowed,
        "release_ready": automatic_release_allowed,
        "human_review_required": (
            release_action == "human_review"
            or route_decision["human_review_required"]
        ),
        "label_hash": route["label_hash"],
        "route_hash": route["route_hash"],
    }
