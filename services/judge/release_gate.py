"""Release gate report for A2 commercial readiness artifacts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .regression_replay import verify_regression_replay_artifact
from .result_persistence import stable_hash


HARD_GATES = ("C0", "C1", "C2", "C3", "C4", "C5")
A1_EVIDENCE_INDEX_REF = "docs/a1/api_calibration/real_api_evidence_index.json"
JUDGE_REGISTRY_REF = "fixtures/a2/results/a2_judge_versions.json"
OUTPUT_POLICY_BLOCKING_COUNTERS = (
    "unsafe_real_nonprivate_override",
    "private_required_but_not_private",
)
SUPPORTED_RELEASE_MODALITIES = frozenset({"text", "image"})
KNOWN_RELEASE_MODALITIES = frozenset({"text", "image", "audio", "video", "file"})
RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_REF = "docs/evidence/a2_releasefoundry_native_media_surface.json"
MODALITY_RELEASE_BOUNDARIES = {
    "text": {
        "releasefoundry_generated_artifact_state": "not_applicable",
        "releasefoundry_caller_native_submission_state": "not_applicable",
        "a2_release_qualification_state": "implemented",
        "required_disposition": "qualified_scope",
    },
    "image": {
        "releasefoundry_generated_artifact_state": "verified_non_qualifying",
        "releasefoundry_caller_native_submission_state": "provider_surface_missing",
        "a2_release_qualification_state": "implemented_requires_bound_artifact",
        "required_disposition": "qualify",
    },
    "audio": {
        "releasefoundry_generated_artifact_state": "verified_non_qualifying",
        "releasefoundry_caller_native_submission_state": "provider_surface_missing",
        "a2_release_qualification_state": "not_implemented",
        "required_disposition": "retest",
    },
    "file": {
        "releasefoundry_generated_artifact_state": "verified_non_qualifying",
        "releasefoundry_caller_native_submission_state": "provider_surface_missing",
        "a2_release_qualification_state": "not_implemented",
        "required_disposition": "retest",
    },
    "video": {
        "releasefoundry_generated_artifact_state": "provider_unverified",
        "releasefoundry_caller_native_submission_state": "provider_unverified",
        "a2_release_qualification_state": "not_implemented",
        "required_disposition": "retest_or_human_review",
    },
}
RELEASE_GATE_SOURCE_HASH_FIELDS = (
    "source_commercial_readiness_hash",
    "source_evidence_readiness_hash",
    "source_calibration_matrix_hash",
    "source_case_book_hash",
    "source_regression_replay_hash",
    "source_scenario_selection_hash",
    "source_a1_evidence_index_hash",
    "source_judge_registry_hash",
)


def build_release_gate_report(
    commercial_readiness_report: dict[str, Any],
    evidence_readiness_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    regression_replay_report: dict[str, Any] | None = None,
    scenario_selection_report: dict[str, Any] | None = None,
    a1_evidence_index: dict[str, Any] | None = None,
    modality_scope: Any = None,
    multimodal_qualification: dict[str, Any] | None = None,
    multimodal_expected_bindings: dict[str, Any] | None = None,
    judge_version_registry: dict[str, Any] | None = None,
    case_book_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert readiness evidence into a machine-readable PR/release gate."""
    source_hashes = {
        "source_commercial_readiness_hash": stable_hash(
            commercial_readiness_report
        ),
        "source_evidence_readiness_hash": stable_hash(
            evidence_readiness_report
        ),
        "source_calibration_matrix_hash": stable_hash(calibration_matrix),
        "source_case_book_hash": stable_hash(case_book_report),
        "source_regression_replay_hash": stable_hash(
            regression_replay_report
        ),
        "source_scenario_selection_hash": stable_hash(
            scenario_selection_report
        ),
        "source_a1_evidence_index_hash": stable_hash(a1_evidence_index),
        "source_judge_registry_hash": stable_hash(judge_version_registry),
    }
    judge_registry_binding, judge_registry_blockers = (
        _judge_registry_binding(judge_version_registry)
    )
    commercial_readiness_report = _as_dict(commercial_readiness_report)
    evidence_readiness_report = _as_dict(evidence_readiness_report)
    calibration_matrix = _as_dict(calibration_matrix)
    case_book_report = _as_dict(case_book_report)
    regression_replay_report = _as_dict(regression_replay_report)
    scenario_selection_report = _as_dict(scenario_selection_report)
    gate_status = commercial_readiness_report.get("gate_status")
    if not isinstance(gate_status, list):
        gate_status = []
    gates: dict[str, dict[str, Any]] = {}
    duplicate_hard_gates: set[str] = set()
    for gate in gate_status:
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("gate")
        if not isinstance(gate_id, str):
            continue
        if gate_id in HARD_GATES and gate_id in gates:
            duplicate_hard_gates.add(gate_id)
        gates[gate_id] = gate
    blocking_gates = [
        _gate_blocker(
            gate_id,
            gates.get(gate_id, {}),
            duplicate=gate_id in duplicate_hard_gates,
        )
        for gate_id in HARD_GATES
        if gate_id in duplicate_hard_gates
        or not _commercial_gate_is_met(gates.get(gate_id, {}))
    ]
    blocking_gates = [item for item in blocking_gates if item]
    evidence_blockers = _evidence_blockers(
        evidence_readiness_report,
        calibration_matrix,
        regression_replay_report,
        case_book_report,
    )
    scenario_selection_gate = _scenario_selection_gate(scenario_selection_report)
    scenario_selection_blockers = _scenario_selection_blockers(scenario_selection_gate)
    a1_output_policy_gate = build_a1_output_policy_gate(a1_evidence_index)
    output_policy_blockers = _a1_output_policy_blockers(a1_output_policy_gate)
    normalized_modality_scope, modality_scope_blockers = _normalize_modality_scope(
        modality_scope
    )
    multimodal_blockers = _multimodal_qualification_blockers(
        normalized_modality_scope,
        multimodal_qualification,
        multimodal_expected_bindings,
    )
    blockers = (
        blocking_gates
        + evidence_blockers
        + scenario_selection_blockers
        + output_policy_blockers
        + modality_scope_blockers
        + multimodal_blockers
        + judge_registry_blockers
    )
    warnings = _warnings(commercial_readiness_report, evidence_readiness_report) + _scenario_selection_warnings(
        scenario_selection_gate
    )
    decision = "block" if blockers else "warn" if warnings else "pass"
    risk_score = _risk_score(blockers, warnings)
    report = {
        "schema_version": "a2.release_gate.v1",
        "report_id": "a2_release_gate",
        "release_candidate": {
            "id": "a2_g3_commercial_default",
            "profile": "strict-commercial",
            "scope": "A2 scenario/judge/calibration evidence for agent release readiness",
        },
        "decision": decision,
        "exit_code": 2 if decision == "block" else 1 if decision == "warn" else 0,
        "risk_score": risk_score,
        "hard_gate_ids": list(HARD_GATES),
        "current_commercial_gate": commercial_readiness_report.get("current_gate", ""),
        "ready_for_commercial_gate": commercial_readiness_report.get("ready_for_commercial_gate") is True,
        "blocking_gate_count": len(blocking_gates),
        "evidence_blocker_count": len(evidence_blockers),
        "scenario_selection_blocker_count": len(scenario_selection_blockers),
        "a1_output_policy_blocker_count": len(output_policy_blockers),
        "judge_registry_blocker_count": len(judge_registry_blockers),
        "warning_count": len(warnings),
        "scenario_selection_gate": scenario_selection_gate,
        "a1_output_policy_gate": a1_output_policy_gate,
        "judge_registry_binding": judge_registry_binding,
        "judge_registry_hash": judge_registry_binding["registry_hash"],
        "blockers": blockers,
        "warnings": warnings,
        "required_evidence": _required_evidence(evidence_readiness_report),
        "pr_annotations": _pr_annotations(blockers, warnings),
        "review_workflow": {
            "required_reviewers": ["A2 owner", "A1 API/runtime owner", "A3 dashboard/report owner"],
            "required_before_unblock": [
                "reviewed ReleaseFoundry grading rows imported for all six calibration cases",
                "audited live semantic judge rows imported for all six calibration cases",
                "case book/regression replay maturity reaches mature",
                "per-project scenario selection coverage and minimums remain ready",
                "secret scan and deterministic fixture checks pass after import",
            ],
            "private_evidence_boundary": "Raw API/model payloads stay under docs/evidence/private_refs/ and are never committed.",
        },
        "machine_contract": {
            "ci_mode": "fail on decision=block",
            "blocking_fields": [
                "decision",
                "blockers",
                "required_evidence",
                "scenario_selection_gate",
                "a1_output_policy_gate",
                "judge_registry_binding",
            ],
            "stable_join_keys": ["case_id", "scenario_id", "gate"],
            "a3_consumption": "A3 may render this as a PR/release gate without reading private evidence.",
        },
        "evidence_refs": [
            "fixtures/a2/results/a2_commercial_readiness_report.json",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
            "fixtures/a2/results/a2_g3_calibration_matrix.json",
            "fixtures/a2/results/a2_regression_replay_report.json",
            "fixtures/a2/results/a2_scenario_selection_report.json",
            JUDGE_REGISTRY_REF,
            A1_EVIDENCE_INDEX_REF,
        ],
        "metadata": {
            "deterministic": True,
            "purpose": "Block unsafe agent releases until A2 replay, judge, evidence, review, and regression gates are proven.",
            "does_not_execute_live_calls": True,
        },
        **source_hashes,
    }
    if modality_scope_blockers:
        report["modality_scope"] = normalized_modality_scope
        report["modality_scope_blocker_count"] = len(modality_scope_blockers)
        report["machine_contract"]["blocking_fields"].append("modality_scope")
    if "image" in normalized_modality_scope:
        report["multimodal_qualification"] = multimodal_qualification
        report["multimodal_qualification_blocker_count"] = len(multimodal_blockers)
        report["machine_contract"]["blocking_fields"].append(
            "multimodal_qualification"
        )
    return seal_release_gate_report(report)


def _normalize_modality_scope(
    modality_scope: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    if modality_scope is None:
        return ["text"], []

    reasons: list[str] = []
    normalized: list[str] = []
    if not isinstance(modality_scope, list) or not modality_scope:
        reasons.append("modality scope must be a non-empty list of strings")
    else:
        normalized = [
            item
            for item in modality_scope
            if isinstance(item, str) and bool(item.strip())
        ]
        if len(normalized) != len(modality_scope):
            reasons.append("modality scope must contain only non-empty strings")
        duplicate_modalities = sorted({
            item for item in normalized if normalized.count(item) > 1
        })
        if duplicate_modalities:
            reasons.append(
                "modality scope contains duplicate entries: "
                + ", ".join(duplicate_modalities)
            )
        non_canonical = sorted(set(normalized) - KNOWN_RELEASE_MODALITIES)
        if non_canonical:
            reasons.append(
                "modality scope contains unknown or non-canonical entries: "
                + ", ".join(non_canonical)
            )
        unsupported = sorted(
            (set(normalized) & KNOWN_RELEASE_MODALITIES)
            - SUPPORTED_RELEASE_MODALITIES
        )
        if unsupported:
            reasons.append(
                "modality scope has no implemented qualification gate: "
                + ", ".join(unsupported)
            )
        generated_only = sorted(set(unsupported) & {"audio", "file"})
        if generated_only:
            reasons.append(
                "ReleaseFoundry generated-artifact verification does not prove caller-native "
                "input or release qualification: "
                + ", ".join(generated_only)
            )
        if "video" in unsupported:
            reasons.append(
                "ReleaseFoundry video remains provider_unverified/unreliable and requires "
                "retest or human review"
            )

    if not reasons:
        return normalized, []
    boundary_modalities = [
        item
        for item in dict.fromkeys(normalized)
        if item in KNOWN_RELEASE_MODALITIES
    ]
    evidence_refs = (
        [RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_REF]
        if any(item != "text" for item in boundary_modalities)
        else []
    )
    return normalized, [{
        "type": "multimodal_scope_gate",
        "gate": "MM0",
        "status": "blocked",
        "severity": "critical",
        "summary": (
            "Release candidate modality scope is invalid or lacks an implemented "
            "qualification gate."
        ),
        "required_action": (
            "Provide a non-empty modality list containing only modalities with "
            "implemented release qualification gates: image, text."
        ),
        "gaps": reasons,
        "modality_boundaries": [
            {
                "modality": modality,
                **MODALITY_RELEASE_BOUNDARIES[modality],
            }
            for modality in boundary_modalities
        ],
        "evidence_refs": evidence_refs,
    }]


def _multimodal_qualification_blockers(
    modality_scope: list[str],
    artifact: dict[str, Any] | None,
    expected_bindings: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if "image" not in modality_scope:
        return []
    reasons: list[str] = []
    if not isinstance(artifact, dict):
        reasons.append("multimodal qualification artifact is missing")
    else:
        if not isinstance(expected_bindings, dict) or not expected_bindings:
            reasons.append("multimodal expected bindings are missing")
        else:
            malformed_bindings = any(
                not isinstance(field, str)
                or not field.strip()
                or not isinstance(expected, str)
                or not expected
                for field, expected in expected_bindings.items()
            )
            missing_required = sorted(
                {
                    "candidate_sha",
                    "manifest_hash",
                    "review_conservation_hash",
                }
                - set(expected_bindings)
            )
            for field in missing_required:
                reasons.append(
                    f"multimodal required expected binding is missing: {field}"
                )
            if malformed_bindings:
                reasons.append("multimodal expected bindings are malformed")
            else:
                for field, expected in sorted(expected_bindings.items()):
                    if artifact.get(field) != expected:
                        reasons.append(
                            f"multimodal qualification binding mismatch: {field}"
                        )
        if artifact.get("qualification_state") != "qualified_for_review":
            reasons.append("multimodal qualification is not qualified for review")
        artifact_blockers = artifact.get("blockers")
        if not isinstance(artifact_blockers, list) or artifact_blockers:
            reasons.append("multimodal qualification contains blockers")
        if artifact.get("release_authority") is not False:
            reasons.append("multimodal qualification authority boundary is invalid")
        usage = artifact.get("usage_cost_receipt")
        if not isinstance(usage, dict) or (
            usage.get("usage_accounting_state") != "complete"
            or usage.get("pricing_state") != "configured"
            or usage.get("within_cost_budget") is not True
        ):
            reasons.append("multimodal usage or pricing qualification is incomplete")
        review_pending = artifact.get("designated_reference_review_pending", False)
        if not isinstance(review_pending, bool):
            reasons.append("multimodal designated-reference review state is malformed")
        elif review_pending:
            latest_receipt_hash = artifact.get("latest_human_review_receipt_hash")
            if not (
                isinstance(latest_receipt_hash, str)
                and len(latest_receipt_hash) == 71
                and latest_receipt_hash.startswith("sha256:")
                and all(
                    character in "0123456789abcdef"
                    for character in latest_receipt_hash[7:]
                )
            ):
                reasons.append(
                    "latest human-review receipt is missing for pending "
                    "designated-reference review"
                )
            elif not isinstance(expected_bindings, dict) or (
                expected_bindings.get("latest_human_review_receipt_hash")
                != latest_receipt_hash
            ):
                reasons.append(
                    "latest human-review receipt binding mismatch for pending "
                    "designated-reference review"
                )
    if not reasons:
        return []
    return [{
        "type": "multimodal_qualification_gate",
        "gate": "MM1",
        "status": "blocked",
        "severity": "critical",
        "summary": "Image-capable release candidate lacks passing multimodal qualification.",
        "required_action": "Provide a current, hash-bound, blocker-free multimodal qualification artifact.",
        "gaps": reasons,
        "evidence_refs": [],
    }]


def seal_release_gate_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a release report sealed over all public fields."""
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    return {**core, "artifact_hash": stable_hash(core)}


def verify_release_gate_artifact(
    report: dict[str, Any],
    *,
    commercial_readiness_report: Any = None,
    evidence_readiness_report: Any = None,
    calibration_matrix: Any = None,
    regression_replay_report: Any = None,
    case_book_report: Any = None,
    scenario_selection_report: Any = None,
    a1_evidence_index: Any = None,
    modality_scope: Any = None,
    multimodal_qualification: dict[str, Any] | None = None,
    multimodal_expected_bindings: dict[str, Any] | None = None,
    judge_version_registry: Any = None,
) -> str:
    """Verify report integrity and any supplied source-artifact bindings."""
    if not isinstance(report, dict):
        raise TypeError("release gate artifact must be an object")

    for field in (
        *RELEASE_GATE_SOURCE_HASH_FIELDS,
        "judge_registry_hash",
        "artifact_hash",
    ):
        if not _is_sha256_reference(report.get(field)):
            raise ValueError(
                f"release gate {field} must be a canonical sha256 reference"
            )

    artifact_hash = report["artifact_hash"]
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    if stable_hash(core) != artifact_hash:
        raise ValueError(
            "release gate artifact_hash does not match report content"
        )

    source_bindings = (
        (
            "source_commercial_readiness_hash",
            commercial_readiness_report,
        ),
        (
            "source_evidence_readiness_hash",
            evidence_readiness_report,
        ),
        ("source_calibration_matrix_hash", calibration_matrix),
        ("source_case_book_hash", case_book_report),
        ("source_regression_replay_hash", regression_replay_report),
        ("source_scenario_selection_hash", scenario_selection_report),
        ("source_a1_evidence_index_hash", a1_evidence_index),
        ("source_judge_registry_hash", judge_version_registry),
    )
    for field, source in source_bindings:
        if source is not None and report[field] != stable_hash(source):
            raise ValueError(
                f"release gate {field} does not match supplied source"
            )

    if judge_version_registry is not None:
        if not isinstance(judge_version_registry, dict):
            raise TypeError("judge version registry must be an object")
        registry_core = {
            key: value
            for key, value in judge_version_registry.items()
            if key != "registry_hash"
        }
        expected_registry_hash = stable_hash(registry_core)
        if judge_version_registry.get("registry_hash") != expected_registry_hash:
            raise ValueError(
                "judge version registry_hash does not match registry content"
            )
        if report["judge_registry_hash"] != expected_registry_hash:
            raise ValueError(
                "release gate judge_registry_hash does not match supplied source"
            )

    authoritative_sources = (
        commercial_readiness_report,
        evidence_readiness_report,
        calibration_matrix,
        regression_replay_report,
        case_book_report,
        scenario_selection_report,
        a1_evidence_index,
        judge_version_registry,
    )
    if all(source is not None for source in authoritative_sources):
        rebuilt = build_release_gate_report(
            commercial_readiness_report,
            evidence_readiness_report,
            calibration_matrix,
            regression_replay_report,
            scenario_selection_report,
            a1_evidence_index,
            modality_scope=modality_scope,
            multimodal_qualification=multimodal_qualification,
            multimodal_expected_bindings=multimodal_expected_bindings,
            judge_version_registry=judge_version_registry,
            case_book_report=case_book_report,
        )
        if rebuilt["artifact_hash"] != artifact_hash:
            raise ValueError(
                "release gate artifact does not match report rebuilt from supplied sources"
            )
    return artifact_hash


def _judge_registry_binding(
    registry: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = _as_dict(registry)
    registry_core = {
        key: value
        for key, value in normalized.items()
        if key != "registry_hash"
    }
    registry_hash = stable_hash(registry_core)
    gaps: list[str] = []
    if not normalized:
        gaps.append("judge version registry is missing")
    elif normalized.get("registry_hash") != registry_hash:
        gaps.append(
            "judge version registry_hash does not match registry content"
        )

    migration_policy = _as_dict(normalized.get("migration_policy"))
    if (
        normalized
        and migration_policy.get("requires_registry_hash_on_release_gate")
        is not True
    ):
        gaps.append(
            "judge version registry does not require release-gate pinning"
        )
    active_release = _as_dict(normalized.get("active_release"))
    if normalized and (
        not str(active_release.get("release_id", "")).strip()
        or not str(active_release.get("default_version", "")).strip()
    ):
        gaps.append("judge version registry active release is incomplete")

    binding = {
        "status": "verified" if not gaps else "blocked",
        "ready": not gaps,
        "registry_id": str(normalized.get("registry_id", "")),
        "registry_hash": registry_hash,
        "active_release_id": str(active_release.get("release_id", "")),
        "default_version": str(active_release.get("default_version", "")),
        "all_declared_judges_observed": (
            normalized.get("all_declared_judges_observed") is True
        ),
        "gaps": gaps,
        "evidence_refs": [JUDGE_REGISTRY_REF],
    }
    if not gaps:
        return binding, []
    return binding, [{
        "type": "judge_registry_binding_gate",
        "gate": "C6",
        "status": "blocked",
        "severity": "critical",
        "summary": (
            "Release decision is not bound to a verified local judge "
            "registry and active version."
        ),
        "required_action": (
            "Regenerate the release gate with the current verified "
            "a2_judge_versions artifact."
        ),
        "missing_count": len(gaps),
        "gaps": gaps,
        "evidence_refs": [JUDGE_REGISTRY_REF],
    }]


def _is_sha256_reference(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def normalize_release_gate_report(report: Any) -> dict[str, Any]:
    """Normalize an external release report without allowing malformed input to pass."""
    malformed_fields: list[str] = []
    if isinstance(report, dict):
        patched = deepcopy(report)
        try:
            verify_release_gate_artifact(report)
        except (TypeError, ValueError) as exc:
            malformed_fields.append(str(exc))
    else:
        patched = {}
        malformed_fields.append("release gate report must be an object")

    raw_blockers = patched.get("blockers")
    if not isinstance(raw_blockers, list):
        blockers = []
        malformed_fields.append("blockers must be a list of objects")
    else:
        blockers = [item for item in raw_blockers if isinstance(item, dict)]
        if len(blockers) != len(raw_blockers):
            malformed_fields.append("blockers must contain only objects")

    raw_warnings = patched.get("warnings")
    if not isinstance(raw_warnings, list):
        warnings = []
        malformed_fields.append("warnings must be a list of objects")
    else:
        warnings = [item for item in raw_warnings if isinstance(item, dict)]
        if len(warnings) != len(raw_warnings):
            malformed_fields.append("warnings must contain only objects")

    source_decision = patched.get("decision")
    derived_source_decision = (
        "block" if blockers else "warn" if warnings else "pass"
    )
    if source_decision not in {"pass", "warn", "block"}:
        malformed_fields.append("decision must be pass, warn, or block")
    elif source_decision != derived_source_decision:
        malformed_fields.append(
            "decision must match the supplied blockers and warnings"
        )

    release_candidate = patched.get("release_candidate")
    if release_candidate is not None and not isinstance(release_candidate, dict):
        patched["release_candidate"] = {}
        malformed_fields.append("release_candidate must be an object")

    if malformed_fields:
        blockers.append(_release_gate_report_integrity_blocker(malformed_fields))

    decision = "block" if blockers else "warn" if warnings else "pass"
    patched["blockers"] = blockers
    patched["warnings"] = warnings
    patched["decision"] = decision
    patched["exit_code"] = 2 if decision == "block" else 1 if decision == "warn" else 0
    patched["risk_score"] = _risk_score(blockers, warnings)
    patched["pr_annotations"] = _pr_annotations(blockers, warnings)
    patched["warning_count"] = len(warnings)
    return seal_release_gate_report(patched)


def apply_a1_output_policy_gate(report: Any, evidence_index: dict[str, Any] | None) -> dict[str, Any]:
    """Return a release gate report with A1 public output-policy evidence applied."""
    patched = normalize_release_gate_report(report)
    blockers = [
        item
        for item in patched["blockers"]
        if item.get("type") != "a1_output_policy_gate"
    ]
    warnings = patched["warnings"]
    gate = build_a1_output_policy_gate(evidence_index)
    output_policy_blockers = _a1_output_policy_blockers(gate)
    blockers.extend(output_policy_blockers)
    decision = "block" if blockers else "warn" if warnings else "pass"

    patched["a1_output_policy_gate"] = gate
    patched["a1_output_policy_blocker_count"] = len(output_policy_blockers)
    patched["blockers"] = blockers
    patched["warnings"] = warnings
    patched["decision"] = decision
    patched["exit_code"] = 2 if decision == "block" else 1 if decision == "warn" else 0
    patched["risk_score"] = _risk_score(blockers, warnings)
    patched["pr_annotations"] = _pr_annotations(blockers, warnings)
    patched["warning_count"] = len(warnings)
    patched["source_a1_evidence_index_hash"] = stable_hash(evidence_index)
    patched["evidence_refs"] = _append_unique_string(patched.get("evidence_refs", []), A1_EVIDENCE_INDEX_REF)
    machine_contract = patched.get("machine_contract")
    if isinstance(machine_contract, dict):
        machine_contract["blocking_fields"] = _append_unique_string(
            machine_contract.get("blocking_fields", []),
            "a1_output_policy_gate",
        )
    return seal_release_gate_report(patched)


def _release_gate_report_integrity_blocker(gaps: list[str]) -> dict[str, Any]:
    return {
        "type": "release_gate_report_integrity",
        "gate": "C6",
        "status": "blocked",
        "severity": "critical",
        "summary": "Release gate report structure is malformed.",
        "required_action": (
            "Regenerate the release gate report with object-list blockers and "
            "warnings before applying A1 output-policy evidence."
        ),
        "missing_count": len(gaps),
        "gaps": gaps,
        "evidence_refs": [],
    }


def build_a1_output_policy_gate(evidence_index: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize A1 output policy counters into a public release-gate input."""
    if not isinstance(evidence_index, dict):
        return {
            "status": "blocked",
            "ready": False,
            "source_schema_version": "",
            "label": "",
            "index_path": A1_EVIDENCE_INDEX_REF,
            "total_records": 0,
            "dangerous_counts": {key: 0 for key in OUTPUT_POLICY_BLOCKING_COUNTERS},
            "safe_counts": {},
            "gaps": ["A1 output policy evidence index is missing or malformed"],
            "evidence_refs": [],
        }

    counts = evidence_index.get("output_policy_counts")
    if not isinstance(counts, dict):
        counts = {}
    dangerous_counts: dict[str, int] = {}
    invalid_dangerous_count_fields: list[str] = []
    for key in OUTPUT_POLICY_BLOCKING_COUNTERS:
        value, valid = _strict_nonnegative_int(counts.get(key))
        dangerous_counts[key] = value
        if not valid:
            invalid_dangerous_count_fields.append(key)
    ready = not invalid_dangerous_count_fields and all(
        value == 0 for value in dangerous_counts.values()
    )
    gate = {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "source_schema_version": str(evidence_index.get("schema_version", "")),
        "label": str(evidence_index.get("label", "")),
        "index_path": A1_EVIDENCE_INDEX_REF,
        "total_records": _int_count(evidence_index.get("total_records")),
        "dangerous_counts": dangerous_counts,
        "safe_counts": {
            "private_required": _int_count(counts.get("private_required")),
            "private_file": _int_count(counts.get("private_file")),
            "stdout_full_record_blocked": _int_count(counts.get("stdout_full_record_blocked")),
            "present": _int_count(counts.get("present")),
        },
        "evidence_refs": [A1_EVIDENCE_INDEX_REF],
    }
    if invalid_dangerous_count_fields:
        gate["invalid_dangerous_count_fields"] = invalid_dangerous_count_fields
    return gate


def _scenario_selection_gate(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {
            "status": "needs_attention",
            "ready": False,
            "coverage_ready": False,
            "minimums_ready": False,
            "selection_id": "",
            "project_id": "",
            "environment": "",
            "selected_scenario_count": 0,
            "gaps": ["scenario selection evidence is missing or malformed"],
            "evidence_refs": [],
        }

    coverage = report.get("coverage_summary", {})
    if not isinstance(coverage, dict):
        coverage = {}
    minimums = report.get("minimums_summary", {})
    if not isinstance(minimums, dict):
        minimums = {}
    project = report.get("project", {})
    if not isinstance(project, dict):
        project = {}
    a3_summary = report.get("a3_consumption_summary", {})
    if not isinstance(a3_summary, dict):
        a3_summary = {}

    coverage_ready = coverage.get("coverage_ready") is True
    minimums_ready = minimums.get("minimums_ready") is True
    raw_gaps = minimums.get("gaps")
    gaps = (
        [str(gap) for gap in raw_gaps if str(gap).strip()]
        if isinstance(raw_gaps, list)
        else []
    )
    selected_scenario_count, selected_count_valid = _strict_nonnegative_int(
        report.get("selected_scenario_count")
    )
    if not coverage_ready:
        gaps.append("scenario selection coverage is not ready")
    if not selected_count_valid:
        gaps.append("selected_scenario_count must be a non-negative integer")
    ready = coverage_ready and minimums_ready and selected_count_valid
    gate = {
        "status": "ready" if ready else "needs_attention",
        "ready": ready,
        "coverage_ready": coverage_ready,
        "minimums_ready": minimums_ready,
        "selection_id": str(report.get("selection_id", "")),
        "project_id": str(project.get("project_id", "")),
        "environment": str(report.get("environment", "")),
        "selected_scenario_count": selected_scenario_count,
        "observed_minimums": minimums.get("observed", {}),
        "release_gate_inputs": a3_summary.get("release_gate_inputs", {}),
        "gaps": gaps,
        "evidence_refs": ["fixtures/a2/results/a2_scenario_selection_report.json"],
    }
    if not selected_count_valid:
        gate["invalid_count_fields"] = ["selected_scenario_count"]
    return gate


def _scenario_selection_blockers(gate: dict[str, Any]) -> list[dict[str, Any]]:
    if gate.get("status") != "needs_attention":
        return []
    return [
        {
            "type": "scenario_selection_gate",
            "gate": "S1",
            "status": str(gate.get("status", "needs_attention")),
            "severity": "high",
            "summary": "Per-project scenario selection coverage or minimums are not release-ready.",
            "required_action": "Fix scenario selection gaps before using this pack as a release gate baseline.",
            "missing_count": len(gate.get("gaps", [])),
            "evidence_refs": gate.get("evidence_refs", []),
        }
    ]


def _a1_output_policy_blockers(gate: dict[str, Any]) -> list[dict[str, Any]]:
    if gate.get("status") != "blocked":
        return []
    dangerous_counts = gate.get("dangerous_counts", {})
    if not isinstance(dangerous_counts, dict):
        dangerous_counts = {}
    invalid_fields = gate.get("invalid_dangerous_count_fields", [])
    if not isinstance(invalid_fields, list):
        invalid_fields = []
    invalid_fields = [
        str(field)
        for field in invalid_fields
        if field in OUTPUT_POLICY_BLOCKING_COUNTERS
    ]
    nonzero = {
        key: _int_count(dangerous_counts.get(key))
        for key in OUTPUT_POLICY_BLOCKING_COUNTERS
        if _int_count(dangerous_counts.get(key)) > 0
    }
    raw_gaps = gate.get("gaps")
    gaps = (
        [gap for gap in raw_gaps if isinstance(gap, str) and gap.strip()]
        if isinstance(raw_gaps, list)
        else []
    )
    blocker = {
        "type": "a1_output_policy_gate",
        "gate": "A1-OUTPUT-POLICY",
        "status": "blocked",
        "severity": "critical",
        "summary": "A1 public evidence index reports unsafe or malformed output-policy counters.",
        "required_action": "Fix output policy evidence so dangerous counters are explicit non-negative integers and private-required API records stay private before release.",
        "missing_count": max(1, sum(nonzero.values()) + len(invalid_fields)),
        "dangerous_counts": nonzero,
        "gaps": gaps,
        "evidence_refs": gate.get("evidence_refs", []),
    }
    if invalid_fields:
        blocker["invalid_dangerous_count_fields"] = invalid_fields
    return [blocker]


def _scenario_selection_warnings(gate: dict[str, Any]) -> list[dict[str, Any]]:
    if gate.get("status") != "not_evaluated":
        return []
    return [
        {
            "type": "scenario_selection_gate",
            "severity": "medium",
            "summary": "Scenario selection gate was not evaluated for this release report.",
            "count": 1,
            "evidence_refs": [],
        }
    ]


def _commercial_gate_is_met(gate: dict[str, Any]) -> bool:
    gaps, _, invalid_fields = _commercial_gate_details(gate)
    return (
        gate.get("status") == "met"
        and not gaps
        and not invalid_fields
    )


def _commercial_gate_details(
    gate: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    invalid_fields: list[str] = []
    raw_gaps = gate.get("gaps", [])
    if isinstance(raw_gaps, list):
        gaps = [
            item
            for item in raw_gaps
            if isinstance(item, str) and bool(item.strip())
        ]
        if len(gaps) != len(raw_gaps):
            invalid_fields.append("gaps")
            gaps.append("commercial gate gaps must contain only non-empty strings")
    else:
        invalid_fields.append("gaps")
        gaps = ["commercial gate gaps must be a list of strings"]

    raw_evidence_refs = gate.get("evidence_refs", [])
    if isinstance(raw_evidence_refs, list):
        evidence_refs = [
            item
            for item in raw_evidence_refs
            if isinstance(item, str) and bool(item.strip())
        ]
        if len(evidence_refs) != len(raw_evidence_refs):
            invalid_fields.append("evidence_refs")
            gaps.append(
                "commercial gate evidence_refs must contain only non-empty strings"
            )
    else:
        invalid_fields.append("evidence_refs")
        evidence_refs = []
        gaps.append("commercial gate evidence_refs must be a list of strings")
    return gaps, evidence_refs, invalid_fields


def _gate_blocker(
    gate_id: str,
    gate: dict[str, Any],
    *,
    duplicate: bool = False,
) -> dict[str, Any]:
    gaps, evidence_refs, invalid_fields = _commercial_gate_details(gate)
    if duplicate:
        gaps.insert(0, f"duplicate commercial gate entries found: {gate_id}")
        invalid_fields.insert(0, "gate_status")
    blocker = {
        "type": "commercial_gate",
        "gate": gate_id,
        "status": str(gate.get("status", "missing")),
        "severity": "high" if gate_id in {"C3", "C4", "C5"} else "critical",
        "summary": str(gate.get("name") or f"{gate_id} gate is not met"),
        "required_action": gaps[0] if gaps else f"Bring {gate_id} to met before release.",
        "gaps": gaps,
        "evidence_refs": evidence_refs,
    }
    if invalid_fields:
        blocker["invalid_fields"] = invalid_fields
    return blocker


def _evidence_blockers(
    evidence_readiness_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    regression_replay_report: dict[str, Any],
    case_book_report: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    releasefoundry_gate = _as_dict(evidence_readiness_report.get("releasefoundry_public_merge_gate"))
    releasefoundry_missing, releasefoundry_missing_valid = _strict_nonnegative_int(
        releasefoundry_gate.get("missing_reviewed_observation_count")
    )
    if (
        releasefoundry_gate.get("safe_to_mark_c3_met") is not True
        or not releasefoundry_missing_valid
    ):
        blocker = {
            "type": "evidence_gate",
            "gate": "C3",
            "status": str(releasefoundry_gate.get("status", "unknown")),
            "severity": "high",
            "summary": "ReleaseFoundry server-side grading evidence is not publicly merge-safe.",
            "required_action": str(
                releasefoundry_gate.get("blocking_reason")
                or "Import reviewed ReleaseFoundry grading rows."
            ),
            "missing_count": releasefoundry_missing if releasefoundry_missing_valid else 1,
            "evidence_refs": [releasefoundry_gate.get("public_matrix_path", "")],
        }
        if not releasefoundry_missing_valid:
            blocker["invalid_count_fields"] = [
                "missing_reviewed_observation_count"
            ]
        blockers.append(blocker)

    semantic_gate = _as_dict(
        evidence_readiness_report.get("semantic_live_merge_gate")
    )
    semantic_missing, semantic_missing_valid = _strict_nonnegative_int(
        semantic_gate.get("missing_audited_observation_count")
    )
    if (
        semantic_gate.get("safe_to_mark_c4_met") is not True
        or not semantic_missing_valid
    ):
        blocker = {
            "type": "evidence_gate",
            "gate": "C4",
            "status": str(semantic_gate.get("status", "unknown")),
            "severity": "high",
            "summary": "Audited live semantic judge evidence is not merged.",
            "required_action": str(
                semantic_gate.get("blocking_reason")
                or "Import audited semantic judge summaries with prompt/model/cost metadata."
            ),
            "missing_count": semantic_missing if semantic_missing_valid else 1,
            "evidence_refs": [semantic_gate.get("public_matrix_path", "")],
        }
        if not semantic_missing_valid:
            blocker["invalid_count_fields"] = [
                "missing_audited_observation_count"
            ]
        blockers.append(blocker)

    source_coverage = _as_dict(calibration_matrix.get("source_coverage"))
    releasefoundry_coverage = _as_dict(source_coverage.get("releasefoundry_grading"))
    source_missing, source_missing_valid = _strict_nonnegative_int(
        releasefoundry_coverage.get("missing")
    )
    if source_missing > 0 or not source_missing_valid:
        blocker = {
            "type": "calibration_gap",
            "gate": "C3",
            "status": (
                "missing_source" if source_missing_valid else "malformed_source"
            ),
            "severity": "high",
            "summary": "Calibration matrix lacks ReleaseFoundry grading rows.",
            "required_action": "Collect, review, import, and regenerate ReleaseFoundry grading observations.",
            "missing_count": source_missing if source_missing_valid else 1,
            "evidence_refs": [
                "fixtures/a2/results/a2_g3_calibration_matrix.json"
            ],
        }
        if not source_missing_valid:
            blocker["invalid_count_fields"] = [
                "source_coverage.releasefoundry_grading.missing"
            ]
        blockers.append(blocker)

    maturity = str(regression_replay_report.get("maturity_status", "missing"))
    if maturity == "mature":
        replay_integrity_gaps = []
        if not case_book_report:
            replay_integrity_gaps.append(
                "current case-book report was not supplied for mature replay verification"
            )
        else:
            try:
                verify_regression_replay_artifact(
                    regression_replay_report,
                    calibration_matrix=calibration_matrix,
                    case_book_report=case_book_report,
                )
            except Exception:
                replay_integrity_gaps.append(
                    "mature replay does not match the deterministic report rebuilt "
                    "from the current calibration matrix and case book"
                )
        if replay_integrity_gaps:
            blockers.append(
                {
                    "type": "regression_replay_integrity",
                    "gate": "C5",
                    "status": "invalid_source",
                    "severity": "critical",
                    "summary": "Regression replay maturity is not source-authoritative.",
                    "required_action": (
                        "Rebuild the replay from the current calibration matrix and "
                        "case book; do not promote C5 from a re-sealed report."
                    ),
                    "missing_count": 1,
                    "gaps": replay_integrity_gaps,
                    "evidence_refs": [
                        "fixtures/a2/results/a2_g3_calibration_matrix.json",
                        "fixtures/a2/results/a2_case_book.json",
                        "fixtures/a2/results/a2_regression_replay_report.json",
                    ],
                }
            )
    else:
        replay_gate = _as_dict(
            regression_replay_report.get("release_gate_summary")
        )
        maturity_gate = _as_dict(regression_replay_report.get("maturity_gate"))
        if "blocking_count" in replay_gate:
            replay_count_field = "release_gate_summary.blocking_count"
            raw_replay_count = replay_gate.get("blocking_count")
        else:
            replay_count_field = (
                "maturity_gate.missing_reviewed_replay_cases"
            )
            raw_replay_count = maturity_gate.get(
                "missing_reviewed_replay_cases"
            )
        replay_missing, replay_missing_valid = _strict_nonnegative_int(
            raw_replay_count
        )
        replay_refs = replay_gate.get("evidence_refs")
        if not isinstance(replay_refs, list):
            replay_refs = ["fixtures/a2/results/a2_regression_replay_report.json"]
        blocker = {
            "type": "regression_maturity",
            "gate": "C5",
            "status": maturity,
            "severity": "medium",
            "summary": "Regression replay is not mature enough to unblock release.",
            "required_action": str(
                replay_gate.get("required_action")
                or "Promote more reviewed disagreement or incident cases into replayable regressions."
            ),
            "missing_count": replay_missing if replay_missing_valid else 1,
            "evidence_refs": replay_refs,
        }
        if not replay_missing_valid:
            blocker["invalid_count_fields"] = [replay_count_field]
        blockers.append(blocker)
    return blockers


def _warnings(
    commercial_readiness_report: dict[str, Any],
    evidence_readiness_report: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings = []
    snapshot = _as_dict(commercial_readiness_report.get("evidence_snapshot"))
    semantic_review_count, semantic_review_count_valid = _strict_nonnegative_int(
        snapshot.get("semantic_score_delta_reviews", 0)
    )
    if semantic_review_count > 0 or not semantic_review_count_valid:
        warning = {
            "type": "judge_risk",
            "severity": "medium",
            "summary": "Semantic score-delta review candidates remain open.",
            "count": (
                semantic_review_count if semantic_review_count_valid else 1
            ),
            "evidence_refs": [
                "fixtures/a2/results/a2_semantic_harness_report.json"
            ],
        }
        if not semantic_review_count_valid:
            warning["invalid_count_fields"] = [
                "evidence_snapshot.semantic_score_delta_reviews"
            ]
        warnings.append(
            warning
        )
    api_evidence = _as_dict(
        evidence_readiness_report.get("a1_real_api_evidence")
    )
    quota_gate = _as_dict(api_evidence.get("real_quota_gate"))
    quota_count, quota_count_valid = _strict_nonnegative_int(
        quota_gate.get("blocked_count", 0)
    )
    if quota_gate.get("blocked") is True:
        warning = {
            "type": "quota_risk",
            "severity": "medium",
            "summary": "Real API quota gate is currently blocking mutating request calibration.",
            "count": quota_count if quota_count_valid else 1,
            "evidence_refs": [api_evidence.get("index_path", "")],
        }
        if not quota_count_valid:
            warning["invalid_count_fields"] = [
                "a1_real_api_evidence.real_quota_gate.blocked_count"
            ]
        warnings.append(
            warning
        )
    gate_validation = _as_dict(api_evidence.get("api_probe_gate_validation"))
    if gate_validation.get("release_interpretation") in {
        "mixed_gate_evidence_review_required",
        "gate_validation_or_plan_blocked",
    }:
        error_count, error_count_valid = _strict_nonnegative_int(
            gate_validation.get("error_validate_gate_count", 0)
        )
        blocked_count, blocked_count_valid = _strict_nonnegative_int(
            gate_validation.get("blocked_plan_batch_count", 0)
        )
        invalid_count_fields = []
        if not error_count_valid:
            invalid_count_fields.append(
                "a1_real_api_evidence.api_probe_gate_validation."
                "error_validate_gate_count"
            )
        if not blocked_count_valid:
            invalid_count_fields.append(
                "a1_real_api_evidence.api_probe_gate_validation."
                "blocked_plan_batch_count"
            )
        warning = {
            "type": "api_probe_gate_validation",
            "severity": "medium",
            "summary": "A1 API probe quota gate validation evidence needs review before mutating release calibration.",
            "count": (
                error_count + blocked_count
                if not invalid_count_fields
                else max(1, error_count + blocked_count)
            ),
            "evidence_refs": [
                api_evidence.get("index_path", ""),
                gate_validation.get("schema_ref", ""),
            ],
        }
        if invalid_count_fields:
            warning["invalid_count_fields"] = invalid_count_fields
        warnings.append(warning)
    return warnings


def _required_evidence(evidence_readiness_report: dict[str, Any]) -> list[dict[str, Any]]:
    releasefoundry = _as_dict(evidence_readiness_report.get("releasefoundry_grading_preflight"))
    semantic = _as_dict(
        evidence_readiness_report.get("semantic_judge_preflight")
    )
    releasefoundry_required, releasefoundry_required_valid = _strict_nonnegative_int(
        releasefoundry.get("expected_reviewed_observation_count")
    )
    releasefoundry_current, releasefoundry_current_valid = _strict_nonnegative_int(
        releasefoundry.get("current_available")
    )
    semantic_required, semantic_required_valid = _strict_nonnegative_int(
        semantic.get("expected_reviewed_observation_count")
    )
    semantic_current, semantic_current_valid = _strict_nonnegative_int(
        semantic.get("reviewed_live_observation_count")
    )
    required_evidence = [
        {
            "source": "releasefoundry_grading",
            "required_count": releasefoundry_required,
            "current_available": releasefoundry_current,
            "private_input_ref": _string_value(
                releasefoundry.get("private_input_ref")
            ),
            "collection_packet_ref": "fixtures/a2/calibration/a2_releasefoundry_grading_collection_packet.json",
            "commands": _string_list(releasefoundry.get("commands")),
        },
        {
            "source": "llm_judge",
            "required_count": semantic_required,
            "current_available": semantic_current,
            "private_input_ref": _string_value(
                semantic.get("private_input_ref")
            ),
            "collection_packet_ref": _string_value(
                semantic.get("collection_packet_ref")
            ),
            "commands": _string_list(semantic.get("commands")),
        },
    ]
    releasefoundry_invalid_fields = []
    if not releasefoundry_required_valid:
        releasefoundry_invalid_fields.append("expected_reviewed_observation_count")
    if not releasefoundry_current_valid:
        releasefoundry_invalid_fields.append("current_available")
    if releasefoundry_invalid_fields:
        required_evidence[0]["invalid_count_fields"] = releasefoundry_invalid_fields
    semantic_invalid_fields = []
    if not semantic_required_valid:
        semantic_invalid_fields.append("expected_reviewed_observation_count")
    if not semantic_current_valid:
        semantic_invalid_fields.append("reviewed_live_observation_count")
    if semantic_invalid_fields:
        required_evidence[1]["invalid_count_fields"] = semantic_invalid_fields
    return required_evidence


def _pr_annotations(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotations = []
    for item in blockers:
        annotations.append(
            {
                "level": "failure",
                "title": f"{item.get('gate', 'A2')} blocks release",
                "message": item.get("required_action", ""),
                "evidence_refs": item.get("evidence_refs", []),
            }
        )
    for item in warnings:
        annotations.append(
            {
                "level": "warning",
                "title": item.get("summary", "A2 release warning"),
                "message": item.get("summary", ""),
                "evidence_refs": item.get("evidence_refs", []),
            }
        )
    return annotations


def _risk_score(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> int:
    severity_weight = {"critical": 35, "high": 25, "medium": 12, "low": 5}
    score = 0
    for item in blockers:
        score += severity_weight.get(str(item.get("severity", "")), 10)
    for item in warnings:
        score += severity_weight.get(str(item.get("severity", "")), 5)
    return min(score, 100)


def _int_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(float(value)))
        except ValueError:
            return 0
    return 0


def _strict_nonnegative_int(value: Any) -> tuple[int, bool]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0, False
    return value, True


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _append_unique_string(values: Any, value: str) -> list[str]:
    result = [str(item) for item in values] if isinstance(values, list) else []
    if value not in result:
        result.append(value)
    return result
