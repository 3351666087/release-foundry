"""Preflight report for private ReleaseFoundry and semantic judge calibration evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from .releasefoundry_test_receipts import (
    PUBLIC_RECEIPT_SCHEMA_VERSION,
    SCORING_TERMINAL_STATUSES,
    TEST_SCORING_SIGNAL_TYPES,
    TEST_SCORING_SUMMARY_SCHEMA_VERSION,
)
from .releasefoundry_dataset_identity import (
    RECEIPT_SCHEMA_VERSION as DATASET_IDENTITY_RECEIPT_SCHEMA_VERSION,
)
from .calibration import (
    DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
    is_canonical_private_evidence_ref,
    load_semantic_collection_packet_binding,
    semantic_collection_packet_binding,
    validate_releasefoundry_run_receipt_binding,
    validate_semantic_review_receipt_binding,
)
from .result_persistence import stable_hash


DEFAULT_RELEASEFOUNDRY_CASE_MAP = Path("fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json")
DEFAULT_A1_REAL_API_EVIDENCE_INDEX = Path("docs/a1/api_calibration/real_api_evidence_index.json")
DEFAULT_A1_OFFICIAL_API_READONLY_MANIFEST = Path("docs/a1/evidence/official_api_readonly_manifest_summary.json")
DEFAULT_A1_OFFICIAL_API_MUTATING_INDEX = Path("docs/a1/evidence/official_api_mutating_calibration_index.json")
DEFAULT_A1_OFFICIAL_API_PAID_MEDIA_SUMMARY = Path(
    "docs/a1/evidence/official_api_paid_media_summary_20260709_185014.json"
)
DEFAULT_A1_PAYMENT_PROVIDER_READINESS = Path("docs/a1/evidence/payment_provider_readiness_public.json")
DEFAULT_A1_BILLING_REPLAY_FIXTURE = Path("docs/a1/evidence/billing_replay_fixture_round35.json")
DEFAULT_A1_BILLING_LEDGER_MIGRATION_MANIFEST = Path(
    "docs/a1/schemas/a1_billing_ledger_migration_manifest.json"
)
DEFAULT_A1_CHINA_PAYMENT_MIGRATION_MANIFEST = Path(
    "docs/a1/schemas/a1_china_payment_migration_manifest.json"
)
DEFAULT_A1_PAYMENT_VERIFICATION_SECURITY_SQL = Path(
    "services/api/migrations/005_a1_payment_verification_security.sql"
)
DEFAULT_A1_OAUTH_LIFECYCLE_SQL = Path("services/api/migrations/006_a1_oauth_lifecycle.sql")
DEFAULT_A1_GITHUB_ACCOUNT_CONNECTION_EVIDENCE = Path(
    "docs/a1/evidence/github_account_connection_evidence_20260710.json"
)
DEFAULT_A1_OAUTH_RUNTIME_STORE_SQL = Path("services/api/migrations/007_a1_oauth_runtime_store.sql")
DEFAULT_A1_UNIFIED_IDENTITY_SQL = Path("services/api/migrations/008_a1_unified_identity_account.sql")
DEFAULT_A1_OAUTH_IDENTITY_COORDINATOR_SQL = Path(
    "services/api/migrations/009_a1_oauth_identity_coordinator.sql"
)
DEFAULT_A1_IDENTITY_REVOCATION_OUTBOX_SQL = Path(
    "services/api/migrations/010_a1_identity_revocation_outbox.sql"
)
DEFAULT_A1_IDENTITY_SESSION_AUTHENTICATION_SQL = Path(
    "services/api/migrations/011_a1_identity_session_authentication.sql"
)
DEFAULT_A1_IDENTITY_VERIFICATION_SQL = Path("services/api/migrations/012_a1_identity_verification.sql")
DEFAULT_A1_IDENTITY_VERIFICATION_PUBLIC_SURFACE = Path("docs/a1/identity-verification-public-surface.json")
DEFAULT_A1_UNIFIED_IDENTITY_CONTRACT = Path("docs/a1/evidence/unified_identity_contract_20260710.json")
DEFAULT_A1_UNIFIED_IDENTITY_LOCALHOST_EVIDENCE = Path(
    "docs/a1/evidence/unified_identity_same_account_localhost_20260710.json"
)
DEFAULT_A1_GOOGLE_OAUTH_LOCALHOST_EVIDENCE = Path(
    "docs/a1/evidence/google_oauth_localhost_evidence_20260710.json"
)
DEFAULT_A1_BILLING_SQL_SEMANTIC_CONTRACT = Path("docs/a1/evidence/billing_sql_semantic_contract.json")
DEFAULT_A1_OBJECT_STORAGE_CONTRACT = Path("docs/a1/evidence/object_storage_contract_20260709.md")
DEFAULT_A2_REAL_API_SMOKE = Path("docs/evidence/a2_real_api_smoke.json")
DEFAULT_A2_MULTIMODAL_REAL_API_SMOKE = Path("docs/evidence/a2_multimodal_real_api_smoke.json")
DEFAULT_A2_MULTIMODAL_AUDIO_REAL_API_SMOKE = Path(
    "docs/evidence/a2_multimodal_audio_real_api_smoke.json"
)
DEFAULT_A2_MULTIMODAL_IMAGE_REAL_API_SMOKE = Path(
    "docs/evidence/a2_multimodal_image_real_api_smoke.json"
)
DEFAULT_A2_MULTIMODAL_FILE_REAL_API_SMOKE = Path(
    "docs/evidence/a2_multimodal_file_real_api_smoke.json"
)
DEFAULT_A2_RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE = Path(
    "docs/evidence/a2_releasefoundry_native_media_surface.json"
)
EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_SCHEMA_VERSION = (
    "a2.releasefoundry_native_media_surface.v1"
)
EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SDK_VERSION = "0.3.1"
EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SDK_ARTIFACT_SHA256 = (
    "c20c36f7406b569c968e20a00b4a0a32fab02e22d7db51a62a61b14069087e87"
)
EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_FINGERPRINT_SHA256 = (
    "9e91500eb8e32980046901aed7b62497c5c7b6599704a20020479dc112aba775"
)
REVIEWER_RECEIPT_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
RELEASEFOUNDRY_SERVER_SIDE_PROVIDER = "releasefoundry server-side grading"
RELEASEFOUNDRY_SERVER_SIDE_MODEL = "releasefoundry-server-side"
REQUIRED_RELEASEFOUNDRY_REVIEW_FIELDS = [
    "metadata.review_status",
    "metadata.reviewer_receipt",
    "metadata.reviewed_at_unix_ms",
    "evidence_ref",
]
REQUIRED_RELEASEFOUNDRY_TERMINAL_SCORING_FIELDS = [
    "metadata.terminal_scoring_receipt_schema_version",
    "metadata.terminal_status",
    "metadata.terminal_status_verified",
    "metadata.timestamps_verified",
    "metadata.response_evidence_verified",
    "metadata.server_grading_signal_verified",
    "metadata.terminal_scoring_verified",
    "metadata.grading_signal_types",
    "metadata.terminal_receipt_blockers",
    "metadata.run_terminal_receipt_schema_version",
    "metadata.run_terminal_receipt_sha256",
    "metadata.run_expected_test_count",
    "metadata.run_verified_test_count",
    "metadata.run_receipt_complete",
    "metadata.run_dataset_id_verified",
    "metadata.run_result_terminal_verified",
    "metadata.server_grading_lifecycle_verified",
    "metadata.exact_test_set_verified",
    "metadata.all_expected_tests_terminal_scoring_verified",
    "metadata.observed_judge_version",
    "metadata.judge_version_source",
    "metadata.judge_version_verified",
    "metadata.aggregate_marker_used_as_acceptance_authority",
    "metadata.run_terminal_receipt_blockers",
    "metadata.dataset_identity_receipt_schema_version",
    "metadata.dataset_identity_verified",
    "metadata.dataset_identity_receipt_sha256",
    "metadata.dataset_identity_manifest_sha256",
    "metadata.dataset_identity_content_sha256",
    "metadata.dataset_identity_content_collection",
    "metadata.dataset_identity_content_item_count",
    "metadata.dataset_identity_blockers",
]
REQUIRED_SEMANTIC_FIELDS = [
    "case_id",
    "scenario_id",
    "provider",
    "model",
    "prompt_template_id",
    "prompt_hash",
    "response_hash",
    "review_status",
    "reviewer_receipt",
    "reviewed_at_unix_ms",
    "sdk_language",
    "cost.prompt_tokens",
    "cost.completion_tokens",
    "cost.estimated_usd",
    "output.passed",
    "output.primary_failure_class",
    "output.score",
    "output.confidence",
    "output.rationale",
    "output.evidence_refs",
]


def build_evidence_readiness_report(
    calibration_matrix: dict[str, Any],
    batch_plan_report: dict[str, Any],
    semantic_harness_report: dict[str, Any],
    *,
    releasefoundry_case_map_path: str | Path = DEFAULT_RELEASEFOUNDRY_CASE_MAP,
    a1_real_api_evidence_index_path: str | Path = DEFAULT_A1_REAL_API_EVIDENCE_INDEX,
    a1_official_api_readonly_manifest_path: str | Path = DEFAULT_A1_OFFICIAL_API_READONLY_MANIFEST,
    a1_official_api_mutating_index_path: str | Path = DEFAULT_A1_OFFICIAL_API_MUTATING_INDEX,
    a1_official_api_paid_media_summary_path: str | Path = DEFAULT_A1_OFFICIAL_API_PAID_MEDIA_SUMMARY,
    a1_payment_provider_readiness_path: str | Path = DEFAULT_A1_PAYMENT_PROVIDER_READINESS,
    a1_billing_replay_fixture_path: str | Path = DEFAULT_A1_BILLING_REPLAY_FIXTURE,
    a1_billing_ledger_migration_manifest_path: str | Path = DEFAULT_A1_BILLING_LEDGER_MIGRATION_MANIFEST,
    a1_china_payment_migration_manifest_path: str | Path = DEFAULT_A1_CHINA_PAYMENT_MIGRATION_MANIFEST,
    a1_payment_verification_security_sql_path: str | Path = DEFAULT_A1_PAYMENT_VERIFICATION_SECURITY_SQL,
    a1_oauth_lifecycle_sql_path: str | Path = DEFAULT_A1_OAUTH_LIFECYCLE_SQL,
    a1_github_account_connection_evidence_path: str | Path = DEFAULT_A1_GITHUB_ACCOUNT_CONNECTION_EVIDENCE,
    a1_oauth_runtime_store_sql_path: str | Path = DEFAULT_A1_OAUTH_RUNTIME_STORE_SQL,
    a1_unified_identity_sql_path: str | Path = DEFAULT_A1_UNIFIED_IDENTITY_SQL,
    a1_oauth_identity_coordinator_sql_path: str | Path = DEFAULT_A1_OAUTH_IDENTITY_COORDINATOR_SQL,
    a1_identity_revocation_outbox_sql_path: str | Path = DEFAULT_A1_IDENTITY_REVOCATION_OUTBOX_SQL,
    a1_identity_session_authentication_sql_path: str | Path = DEFAULT_A1_IDENTITY_SESSION_AUTHENTICATION_SQL,
    a1_identity_verification_sql_path: str | Path = DEFAULT_A1_IDENTITY_VERIFICATION_SQL,
    a1_identity_verification_public_surface_path: str | Path = DEFAULT_A1_IDENTITY_VERIFICATION_PUBLIC_SURFACE,
    a1_unified_identity_contract_path: str | Path = DEFAULT_A1_UNIFIED_IDENTITY_CONTRACT,
    a1_unified_identity_localhost_evidence_path: str | Path = DEFAULT_A1_UNIFIED_IDENTITY_LOCALHOST_EVIDENCE,
    a1_google_oauth_localhost_evidence_path: str | Path = DEFAULT_A1_GOOGLE_OAUTH_LOCALHOST_EVIDENCE,
    a1_billing_sql_semantic_contract_path: str | Path = DEFAULT_A1_BILLING_SQL_SEMANTIC_CONTRACT,
    a1_object_storage_contract_path: str | Path = DEFAULT_A1_OBJECT_STORAGE_CONTRACT,
    official_sdk_smoke_path: str | Path = DEFAULT_A2_REAL_API_SMOKE,
    multimodal_real_api_smoke_path: str | Path = DEFAULT_A2_MULTIMODAL_REAL_API_SMOKE,
    multimodal_audio_real_api_smoke_path: str
    | Path = DEFAULT_A2_MULTIMODAL_AUDIO_REAL_API_SMOKE,
    multimodal_image_real_api_smoke_path: str
    | Path = DEFAULT_A2_MULTIMODAL_IMAGE_REAL_API_SMOKE,
    multimodal_file_real_api_smoke_path: str
    | Path = DEFAULT_A2_MULTIMODAL_FILE_REAL_API_SMOKE,
    releasefoundry_native_media_surface_path: str
    | Path = DEFAULT_A2_RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE,
    semantic_collection_packet: dict[str, Any] | None = None,
    semantic_collection_packet_path: str
    | Path = DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
) -> dict[str, Any]:
    """Describe what private evidence is still needed before C3/C4 can turn green."""
    cases = list(calibration_matrix.get("cases", []))
    case_ids = [str(case.get("case_id", "")) for case in cases]
    releasefoundry_case_map = _load_case_map(releasefoundry_case_map_path)
    mapped_case_ids = set(str(case_id) for case_id in releasefoundry_case_map.values())
    releasefoundry_missing = sorted(set(case_ids) - mapped_case_ids)
    semantic_languages = sorted(
        chain.get("language")
        for chain in semantic_harness_report.get("source_matrix", {}).get("official_sdk_chains", [])
        if chain.get("language")
    )
    source_coverage = calibration_matrix.get("source_coverage", {})
    releasefoundry_counts = source_coverage.get("releasefoundry_grading", {})
    llm_counts = source_coverage.get("llm_judge", {})
    llm_offline_only = _llm_offline_only(calibration_matrix)
    (
        semantic_collection_binding,
        semantic_collection_binding_blockers,
    ) = _resolve_semantic_collection_packet_binding(
        semantic_collection_packet,
        semantic_collection_packet_path,
    )
    releasefoundry_import_commands = [
        "python scripts/a2_scan_releasefoundry_grading_evidence.py --input docs/evidence/private_refs/a2_releasefoundry_get_run.redacted.json --case-map fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json",
            "python scripts/a2_import_releasefoundry_grading.py --input docs/evidence/private_refs/a2_releasefoundry_get_run.redacted.json --case-map fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json --identity-file docs/evidence/private_refs/a2_releasefoundry_dataset_identity.private.json --identity-receipt docs/evidence/a2_releasefoundry_dataset_identity_receipt.json --evidence-ref docs/evidence/private_refs/a2_releasefoundry_get_run.redacted.json --review-status reviewed --reviewer-receipt \"$A2_REVIEWER_RECEIPT\" --reviewed-at-unix-ms \"$A2_REVIEWED_AT_UNIX_MS\" --require-reviewed --require-complete --output docs/evidence/private_refs/a2_releasefoundry_grading_import.review.json",
        "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_releasefoundry_grading_import.review.json --source releasefoundry_grading --min-count 6 --require-reviewed --require-complete --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "python scripts/a2_regenerate_fixtures.py --write",
    ]
    semantic_import_commands = [
        "python scripts/a2_build_semantic_judge_collection_packet.py --check",
        "python scripts/a2_import_semantic_judge.py --input docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --evidence-ref docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --collection-packet fixtures/a2/calibration/a2_semantic_judge_collection_packet.json --require-reviewed --require-complete --output docs/evidence/private_refs/a2_semantic_judge_import.review.json",
        "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_semantic_judge_import.review.json --source llm_judge --semantic-collection-packet fixtures/a2/calibration/a2_semantic_judge_collection_packet.json --min-count 6 --require-reviewed --require-complete --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "python scripts/a2_regenerate_fixtures.py --write",
    ]
    semantic_risk = semantic_harness_report.get("risk_assessment", {})
    a1_real_api_evidence = _a1_real_api_evidence_summary(a1_real_api_evidence_index_path)
    a1_official_api_readonly_manifest = _a1_official_api_readonly_manifest_summary(
        a1_official_api_readonly_manifest_path
    )
    a1_official_api_mutating_index = _a1_official_api_mutating_index_summary(
        a1_official_api_mutating_index_path
    )
    a1_official_api_paid_media_summary = _a1_official_api_paid_media_summary(
        a1_official_api_paid_media_summary_path
    )
    a1_payment_provider_readiness = _a1_payment_provider_readiness_summary(
        a1_payment_provider_readiness_path
    )
    a1_billing_replay_evidence = _a1_billing_replay_evidence_summary(a1_billing_replay_fixture_path)
    a1_billing_ledger_migration = _a1_billing_ledger_migration_summary(
        a1_billing_ledger_migration_manifest_path
    )
    a1_china_payment_migration = _a1_china_payment_migration_summary(
        a1_china_payment_migration_manifest_path
    )
    a1_payment_verification_security = _a1_payment_verification_security_summary(
        a1_payment_verification_security_sql_path
    )
    a1_oauth_lifecycle_security = _a1_oauth_lifecycle_security_summary(
        a1_oauth_lifecycle_sql_path,
        a1_github_account_connection_evidence_path,
    )
    a1_unified_identity_security = _a1_unified_identity_security_summary(
        a1_oauth_runtime_store_sql_path,
        a1_unified_identity_sql_path,
        a1_oauth_identity_coordinator_sql_path,
        a1_identity_revocation_outbox_sql_path,
        a1_identity_session_authentication_sql_path,
        a1_identity_verification_sql_path,
        a1_identity_verification_public_surface_path,
        a1_unified_identity_contract_path,
        a1_unified_identity_localhost_evidence_path,
        a1_google_oauth_localhost_evidence_path,
    )
    a1_billing_sql_semantic_contract = _a1_billing_sql_semantic_contract_summary(
        a1_billing_sql_semantic_contract_path
    )
    a1_object_storage_contract = _a1_object_storage_contract_summary(a1_object_storage_contract_path)
    official_sdk_smoke = _official_sdk_smoke_summary(official_sdk_smoke_path)
    multimodal_real_api_smoke = _multimodal_real_api_smoke_summary(multimodal_real_api_smoke_path)
    multimodal_audio_real_api_smoke = _multimodal_real_api_smoke_summary(
        multimodal_audio_real_api_smoke_path
    )
    multimodal_image_real_api_smoke = _multimodal_real_api_smoke_summary(
        multimodal_image_real_api_smoke_path
    )
    multimodal_file_real_api_smoke = _multimodal_real_api_smoke_summary(
        multimodal_file_real_api_smoke_path
    )
    releasefoundry_native_media_surface = _releasefoundry_native_media_surface_summary(
        releasefoundry_native_media_surface_path
    )
    multimodal_generated_artifact_capabilities = (
        _multimodal_generated_artifact_capabilities_summary(
            [
                (
                    multimodal_image_real_api_smoke_path,
                    multimodal_image_real_api_smoke,
                ),
                (
                    multimodal_audio_real_api_smoke_path,
                    multimodal_audio_real_api_smoke,
                ),
                (
                    multimodal_file_real_api_smoke_path,
                    multimodal_file_real_api_smoke,
                ),
            ],
            releasefoundry_native_media_surface=releasefoundry_native_media_surface,
        )
    )

    readiness_boolean_inputs = {
        "semantic_harness_report.harness_ready": semantic_harness_report.get("harness_ready"),
        "semantic_harness_report.risk_assessment.tracking_ready": semantic_risk.get("tracking_ready"),
    }
    invalid_readiness_boolean_fields = sorted(
        field
        for field, value in readiness_boolean_inputs.items()
        if not isinstance(value, bool)
    )
    readiness_checks = {
        "has_calibration_cases": bool(cases),
        "releasefoundry_case_map_covers_cases": not releasefoundry_missing and len(releasefoundry_case_map) == len(cases),
        "releasefoundry_import_commands_documented": True,
        "semantic_harness_ready": semantic_harness_report.get("harness_ready") is True,
        "semantic_false_positive_tracking_ready": semantic_risk.get("tracking_ready") is True,
        "semantic_required_fields_documented": bool(REQUIRED_SEMANTIC_FIELDS),
        "semantic_sdk_language_matrix_ready": set(semantic_languages) >= {"python", "typescript"},
        "official_sdk_smoke_readonly_ok": official_sdk_smoke.get("read_only_reachable") is True,
        "multimodal_real_api_smoke_reached": multimodal_real_api_smoke.get("real_api_boundary_reached") is True,
        "multimodal_generated_artifacts_verified": (
            multimodal_generated_artifact_capabilities.get(
                "all_expected_modalities_verified"
            )
            is True
        ),
        "releasefoundry_native_media_surface_audited": (
            releasefoundry_native_media_surface.get("surface_audit_verified") is True
        ),
        "private_payload_boundary_documented": True,
    }

    report = {
        "schema_version": "a2.evidence_readiness.v1",
        "report_id": "a2_g3_evidence_readiness",
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "source_matrix_hash": stable_hash(calibration_matrix),
        "source_batch_plan_hash": stable_hash(batch_plan_report),
        "source_semantic_harness_hash": stable_hash(semantic_harness_report),
        "source_case_map_hash": stable_hash(releasefoundry_case_map),
        "status": "awaiting_private_evidence",
        "ready_for_external_collection": all(readiness_checks.values()),
        "readiness_checks": readiness_checks,
        "calibration_case_count": len(cases),
        "calibration_cases": [
            {
                "case_id": case.get("case_id", ""),
                "scenario_id": case.get("scenario_id", ""),
                "fixture_ref": case.get("fixture_ref", ""),
                "calibration_focus": case.get("calibration_focus", []),
            }
            for case in cases
        ],
        "releasefoundry_grading_preflight": {
            "source": "releasefoundry_grading",
            "current_available": _nonnegative_count(releasefoundry_counts.get("available", 0)),
            "current_missing": _nonnegative_count(
                releasefoundry_counts.get("missing", len(cases)),
                fallback=len(cases),
            ),
            "expected_observation_count": len(cases),
            "case_map_path": Path(releasefoundry_case_map_path).as_posix(),
            "case_map_count": len(releasefoundry_case_map),
            "case_map_covers_all_calibration_cases": not releasefoundry_missing and len(releasefoundry_case_map) == len(cases),
            "case_map_missing_case_ids": releasefoundry_missing,
            "expected_reviewed_observation_count": len(cases),
            "required_review_fields": REQUIRED_RELEASEFOUNDRY_REVIEW_FIELDS,
            "required_terminal_scoring_fields": (
                REQUIRED_RELEASEFOUNDRY_TERMINAL_SCORING_FIELDS
            ),
            "private_input_ref": "docs/evidence/private_refs/a2_releasefoundry_get_run.redacted.json",
            "commands": releasefoundry_import_commands,
        },
        "a1_real_api_evidence": a1_real_api_evidence,
        "a1_official_api_readonly_manifest": a1_official_api_readonly_manifest,
        "a1_official_api_mutating_index": a1_official_api_mutating_index,
        "a1_official_api_paid_media_summary": a1_official_api_paid_media_summary,
        "a1_payment_provider_readiness": a1_payment_provider_readiness,
        "a1_billing_replay_evidence": a1_billing_replay_evidence,
        "a1_billing_ledger_migration": a1_billing_ledger_migration,
        "a1_china_payment_migration": a1_china_payment_migration,
        "a1_payment_verification_security": a1_payment_verification_security,
        "a1_oauth_lifecycle_security": a1_oauth_lifecycle_security,
        "a1_unified_identity_security": a1_unified_identity_security,
        "a1_billing_sql_semantic_contract": a1_billing_sql_semantic_contract,
        "a1_object_storage_contract": a1_object_storage_contract,
        "official_sdk_smoke": official_sdk_smoke,
        "multimodal_real_api_smoke": multimodal_real_api_smoke,
        "releasefoundry_native_media_surface": releasefoundry_native_media_surface,
        "multimodal_generated_artifact_capabilities": (
            multimodal_generated_artifact_capabilities
        ),
        "releasefoundry_public_merge_gate": _releasefoundry_public_merge_gate(
            cases,
            releasefoundry_counts,
            len(cases),
            releasefoundry_import_commands,
            calibration_matrix.get("releasefoundry_run_terminal_receipt"),
        ),
        "semantic_judge_preflight": {
            "source": "llm_judge",
            "current_available": _nonnegative_count(llm_counts.get("available", 0)),
            "current_missing": _nonnegative_count(
                llm_counts.get("missing", len(cases)),
                fallback=len(cases),
            ),
            "offline_reference_only": llm_offline_only,
            "expected_observation_count": len(cases),
            "expected_reviewed_observation_count": len(cases),
            "reviewed_live_observation_count": _nonnegative_count(
                semantic_harness_report.get("reviewed_live_observation_count", 0)
            ),
            "missing_reviewed_live_observation_count": _nonnegative_count(
                semantic_harness_report.get("missing_reviewed_live_observation_count", len(cases)),
                fallback=len(cases),
            ),
            "reviewed_live_sdk_languages": semantic_harness_report.get("reviewed_live_sdk_languages", []),
            "reviewed_live_required_metadata_fields": semantic_harness_report.get(
                "reviewed_live_required_metadata_fields", []
            ),
            "risk_assessment_status": semantic_risk.get("status", "unknown"),
            "false_positive_tracking_ready": semantic_risk.get("tracking_ready") is True,
            "false_positive_candidate_count": _nonnegative_count(
                semantic_risk.get("false_positive_candidate_count", 0)
            ),
            "false_negative_candidate_count": _nonnegative_count(
                semantic_risk.get("false_negative_candidate_count", 0)
            ),
            "failure_class_drift_candidate_count": _nonnegative_count(
                semantic_risk.get("failure_class_drift_candidate_count", 0)
            ),
            "score_delta_review_count": _nonnegative_count(
                semantic_risk.get("score_delta_review_count", 0)
            ),
            "risk_case_count": _nonnegative_count(semantic_risk.get("risk_case_count", 0)),
            "required_fields": REQUIRED_SEMANTIC_FIELDS,
            "required_sdk_languages": semantic_harness_report.get("source_matrix", {}).get("required_languages", []),
            "covered_sdk_languages": semantic_harness_report.get("source_matrix", {}).get("covered_languages", []),
            "private_input_ref": "docs/evidence/private_refs/a2_semantic_judge_review.redacted.json",
            "collection_packet_ref": "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json",
            "collection_packet_binding_valid": (
                semantic_collection_binding is not None
            ),
            "collection_packet_id": (
                semantic_collection_binding.get("packet_id", "")
                if semantic_collection_binding
                else ""
            ),
            "collection_packet_sha256": (
                semantic_collection_binding.get("packet_sha256", "")
                if semantic_collection_binding
                else ""
            ),
            "collection_packet_binding_blockers": (
                semantic_collection_binding_blockers
            ),
            "commands": semantic_import_commands,
        },
        "semantic_live_merge_gate": _semantic_live_merge_gate(
            cases,
            llm_counts,
            llm_offline_only,
            len(cases),
            semantic_harness_report,
            semantic_import_commands,
            semantic_collection_binding,
            semantic_collection_binding_blockers,
            str(calibration_matrix.get("dataset_id", "")),
            calibration_matrix.get("semantic_human_review_receipt"),
        ),
        "batch_plan_refs": [
            batch.get("batch_id", "")
            for batch in batch_plan_report.get("batches", [])
            if batch.get("requires_private_evidence")
        ],
        "redaction_policy": {
            "raw_private_path": "docs/evidence/private_refs/",
            "commit_only": [
                "reviewed observation summaries",
                "provider/model names",
                "prompt and response hashes",
                "cost totals",
                "confidence and review status",
                "private evidence refs",
            ],
            "never_commit": ["API keys", "raw prompts", "raw model responses", "raw account payloads"],
        },
        "metadata": {
            "deterministic": True,
            "purpose": "Make C3/C4 evidence collection auditable without committing private payloads.",
        },
    }
    if invalid_readiness_boolean_fields:
        report["invalid_boolean_fields"] = invalid_readiness_boolean_fields
    return _seal_evidence_readiness_artifact(report)


def verify_evidence_readiness_artifact(
    report: dict[str, Any],
    *,
    calibration_matrix: dict[str, Any] | None = None,
    batch_plan_report: dict[str, Any] | None = None,
    semantic_harness_report: dict[str, Any] | None = None,
    releasefoundry_case_map: dict[str, Any] | None = None,
    semantic_collection_packet: dict[str, Any] | None = None,
) -> str:
    """Verify report integrity and any supplied source-artifact bindings."""
    if not isinstance(report, dict):
        raise TypeError("evidence-readiness artifact must be an object")

    hash_fields = (
        "source_matrix_hash",
        "source_batch_plan_hash",
        "source_semantic_harness_hash",
        "source_case_map_hash",
        "artifact_hash",
    )
    for field in hash_fields:
        value = report.get(field)
        if not isinstance(value, str) or not REVIEWER_RECEIPT_PATTERN.fullmatch(value):
            raise ValueError(
                f"evidence-readiness {field} must be a canonical sha256 reference"
            )

    artifact_hash = report["artifact_hash"]
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    if stable_hash(core) != artifact_hash:
        raise ValueError(
            "evidence-readiness artifact_hash does not match report content"
        )

    source_bindings = (
        ("source_matrix_hash", calibration_matrix),
        ("source_batch_plan_hash", batch_plan_report),
        ("source_semantic_harness_hash", semantic_harness_report),
        ("source_case_map_hash", releasefoundry_case_map),
    )
    for field, source in source_bindings:
        if source is not None and report[field] != stable_hash(source):
            raise ValueError(
                f"evidence-readiness {field} does not match supplied source"
            )

    releasefoundry_gate = report.get("releasefoundry_public_merge_gate")
    semantic_gate = report.get("semantic_live_merge_gate")
    c3_acceptance_claimed = (
        isinstance(releasefoundry_gate, dict)
        and releasefoundry_gate.get("safe_to_mark_c3_met") is True
    )
    c4_acceptance_claimed = (
        isinstance(semantic_gate, dict)
        and semantic_gate.get("safe_to_mark_c4_met") is True
    )
    if c3_acceptance_claimed or c4_acceptance_claimed:
        authoritative_sources = {
            "calibration_matrix": calibration_matrix,
            "batch_plan_report": batch_plan_report,
            "semantic_harness_report": semantic_harness_report,
            "releasefoundry_case_map": releasefoundry_case_map,
        }
        missing_sources = [
            name
            for name, source in authoritative_sources.items()
            if not isinstance(source, dict)
        ]
        if missing_sources:
            raise ValueError(
                "acceptance-ready evidence-readiness artifact is missing "
                "authoritative sources: "
                + ", ".join(missing_sources)
            )

    if c3_acceptance_claimed:
        assert isinstance(calibration_matrix, dict)
        cases = list(calibration_matrix.get("cases", []))
        source_coverage = calibration_matrix.get("source_coverage", {})
        releasefoundry_counts = (
            source_coverage.get("releasefoundry_grading", {})
            if isinstance(source_coverage, dict)
            else {}
        )
        releasefoundry_preflight = report.get("releasefoundry_grading_preflight", {})
        commands = (
            releasefoundry_preflight.get("commands", [])
            if isinstance(releasefoundry_preflight, dict)
            else []
        )
        expected_releasefoundry_gate = _releasefoundry_public_merge_gate(
            cases,
            releasefoundry_counts if isinstance(releasefoundry_counts, dict) else {},
            len(cases),
            commands if isinstance(commands, list) else [],
            calibration_matrix.get("releasefoundry_run_terminal_receipt"),
        )
        if releasefoundry_gate != expected_releasefoundry_gate:
            raise ValueError(
                "evidence-readiness releasefoundry_public_merge_gate does not match "
                "deterministic source rebuild"
            )

    if c4_acceptance_claimed:
        assert isinstance(calibration_matrix, dict)
        assert isinstance(semantic_harness_report, dict)
        if not isinstance(semantic_collection_packet, dict):
            raise ValueError(
                "acceptance-ready C4 evidence-readiness artifact is missing "
                "the authoritative semantic collection packet"
            )
        collection_packet_binding = semantic_collection_packet_binding(
            semantic_collection_packet
        )
        cases = list(calibration_matrix.get("cases", []))
        source_coverage = calibration_matrix.get("source_coverage", {})
        llm_counts = (
            source_coverage.get("llm_judge", {})
            if isinstance(source_coverage, dict)
            else {}
        )
        semantic_preflight = report.get("semantic_judge_preflight", {})
        commands = (
            semantic_preflight.get("commands", [])
            if isinstance(semantic_preflight, dict)
            else []
        )
        expected_semantic_gate = _semantic_live_merge_gate(
            cases,
            llm_counts if isinstance(llm_counts, dict) else {},
            _llm_offline_only(calibration_matrix),
            len(cases),
            semantic_harness_report,
            commands if isinstance(commands, list) else [],
            collection_packet_binding,
            [],
            str(calibration_matrix.get("dataset_id", "")),
            calibration_matrix.get("semantic_human_review_receipt"),
        )
        if semantic_gate != expected_semantic_gate:
            raise ValueError(
                "evidence-readiness semantic_live_merge_gate does not match "
                "deterministic source rebuild"
            )
    return artifact_hash


def _seal_evidence_readiness_artifact(report: dict[str, Any]) -> dict[str, Any]:
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    return {**core, "artifact_hash": stable_hash(core)}


def _resolve_semantic_collection_packet_binding(
    packet: dict[str, Any] | None,
    path: str | Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        binding = (
            semantic_collection_packet_binding(packet)
            if packet is not None
            else load_semantic_collection_packet_binding(path)
        )
    except ValueError as exc:
        return None, [f"semantic_collection_packet_invalid:{exc}"]
    return binding, []


def _semantic_live_merge_gate(
    cases: list[dict[str, Any]],
    llm_counts: dict[str, Any],
    llm_offline_only: bool,
    expected_count: int,
    semantic_harness_report: dict[str, Any],
    commands: list[str],
    collection_packet_binding: dict[str, Any] | None,
    collection_packet_binding_blockers: list[str],
    calibration_dataset_id: str,
    semantic_human_review_receipt: Any,
) -> dict[str, Any]:
    current_available, current_available_valid = _strict_nonnegative_count(
        llm_counts.get("available", 0)
    )
    reviewed_count, reviewed_count_valid = _strict_nonnegative_count(
        semantic_harness_report.get("reviewed_live_observation_count", 0)
    )
    reviewed_case_ids = _reviewed_semantic_case_ids(cases)
    case_level_reviewed_count = len(reviewed_case_ids)
    available_count_matches_case_evidence = (
        current_available_valid
        and current_available == case_level_reviewed_count
    )
    reviewed_count_matches_case_evidence = (
        reviewed_count_valid
        and reviewed_count == case_level_reviewed_count
    )
    live_model_raw = semantic_harness_report.get("live_model_evidence_available")
    live_model_evidence = live_model_raw is True
    invalid_count_fields = []
    if not current_available_valid:
        invalid_count_fields.append("source_coverage.llm_judge.available")
    if not reviewed_count_valid:
        invalid_count_fields.append("reviewed_live_observation_count")
    invalid_boolean_fields = (
        []
        if isinstance(live_model_raw, bool)
        else ["live_model_evidence_available"]
    )
    (
        collection_packet_binding_consistent,
        collection_packet_cohort_blockers,
    ) = _semantic_collection_cohort_consistency(
        cases,
        expected_count=expected_count,
        calibration_dataset_id=calibration_dataset_id,
        collection_packet_binding=collection_packet_binding,
        initial_blockers=collection_packet_binding_blockers,
    )
    audited_without_packet_binding = (
        expected_count > 0
        and not invalid_count_fields
        and not invalid_boolean_fields
        and current_available >= expected_count
        and reviewed_count >= expected_count
        and case_level_reviewed_count >= expected_count
        and available_count_matches_case_evidence
        and reviewed_count_matches_case_evidence
        and live_model_evidence
        and not llm_offline_only
    )
    semantic_observations = []
    for case in cases:
        source = case.get("sources", {}).get("llm_judge")
        if not isinstance(source, dict) or source.get("available") is not True:
            continue
        semantic_observations.append(
            {
                **source,
                "case_id": case.get("case_id"),
                "scenario_id": case.get("scenario_id"),
            }
        )
    review_receipt_binding = validate_semantic_review_receipt_binding(
        semantic_observations,
        semantic_human_review_receipt,
        expected_case_ids=[
            str(case.get("case_id", ""))
            for case in cases
            if str(case.get("case_id", "")).strip()
        ],
    )
    merged = (
        audited_without_packet_binding
        and collection_packet_binding_consistent
        and review_receipt_binding["valid"]
    )
    if merged:
        status = "audited_live_model_evidence"
    elif llm_offline_only:
        status = "offline_reference_only"
    elif audited_without_packet_binding:
        status = (
            "audited_unbound_collection_packet"
            if not collection_packet_binding_consistent
            else "audited_unbound_human_review_receipt"
        )
    else:
        status = "not_audited"
    gate = {
        "source": "llm_judge",
        "status": status,
        "audited_live_evidence_merged": merged,
        "safe_to_mark_c4_met": merged,
        "current_public_observation_count": current_available,
        "audited_public_observation_count": (
            case_level_reviewed_count if merged else 0
        ),
        "reviewed_live_observation_count": reviewed_count,
        "case_level_reviewed_observation_count": case_level_reviewed_count,
        "case_level_reviewed_case_ids": reviewed_case_ids,
        "aggregate_available_count_matches_case_evidence": (
            available_count_matches_case_evidence
        ),
        "aggregate_reviewed_count_matches_case_evidence": (
            reviewed_count_matches_case_evidence
        ),
        "collection_packet_binding_consistent": (
            collection_packet_binding_consistent
        ),
        "collection_packet_binding_blockers": (
            collection_packet_cohort_blockers
        ),
        "collection_packet_id": (
            collection_packet_binding.get("packet_id", "")
            if collection_packet_binding
            else ""
        ),
        "collection_packet_sha256": (
            collection_packet_binding.get("packet_sha256", "")
            if collection_packet_binding
            else ""
        ),
        "collection_packet_dataset_id": (
            collection_packet_binding.get("dataset_id", "")
            if collection_packet_binding
            else ""
        ),
        "review_receipt_binding_consistent": review_receipt_binding["valid"],
        "review_receipt_binding_blockers": review_receipt_binding["blockers"],
        "review_receipt_sha256": review_receipt_binding["artifact_sha256"],
        "review_receipt_artifact_present": review_receipt_binding[
            "artifact_present"
        ],
        "missing_audited_observation_count": max(
            0,
            expected_count - case_level_reviewed_count,
        ),
        "expected_reviewed_observation_count": expected_count,
        "offline_reference_only": llm_offline_only,
        "live_model_evidence_available": live_model_evidence,
        "public_matrix_path": "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "reviewed_private_import_ref": "docs/evidence/private_refs/a2_semantic_judge_import.review.json",
        "blocking_reason": ""
        if merged
        else (
            (
                "Audited semantic judge observations are not bound to the exact committed "
                "collection packet. Every reviewed row must match the packet case, SDK, "
                "prompt template, prompt material hash, dataset, and packet artifact hash."
            )
            if (
                audited_without_packet_binding
                and not collection_packet_binding_consistent
            )
            else (
                "Audited semantic judge observations are not bound to an "
                "independent, public-safe human review receipt. The retained "
                "receipt must exactly match every reviewed case and each row "
                "must bind the receipt hash and verification fields."
            )
            if audited_without_packet_binding
            else (
                "Audited semantic judge observations with canonical private evidence refs "
                "must replace offline references before C4 is met. Per-case evidence is "
                "acceptance authority; aggregate availability and reviewed-count markers "
                "must match it."
            )
        ),
        "required_commands": commands,
    }
    if invalid_count_fields:
        gate["invalid_count_fields"] = invalid_count_fields
    if invalid_boolean_fields:
        gate["invalid_boolean_fields"] = invalid_boolean_fields
    return gate


def _semantic_collection_cohort_consistency(
    cases: list[dict[str, Any]],
    *,
    expected_count: int,
    calibration_dataset_id: str,
    collection_packet_binding: dict[str, Any] | None,
    initial_blockers: list[str],
) -> tuple[bool, list[str]]:
    blockers = list(initial_blockers)
    if collection_packet_binding is None:
        if not blockers:
            blockers.append("semantic_collection_packet_unavailable")
        return False, sorted(set(blockers))

    packet_cases = collection_packet_binding["cases"]
    packet_case_ids = set(packet_cases)
    calibration_case_ids = [
        str(case.get("case_id", "")).strip()
        for case in cases
    ]
    if len(calibration_case_ids) != len(set(calibration_case_ids)):
        blockers.append("duplicate_calibration_case_id")
    if set(calibration_case_ids) != packet_case_ids:
        blockers.append("calibration_case_set_mismatch")
    if expected_count != collection_packet_binding["case_count"]:
        blockers.append("calibration_case_count_mismatch")
    if calibration_dataset_id != collection_packet_binding["dataset_id"]:
        blockers.append("calibration_dataset_id_mismatch")

    reviewed_rows = [
        (
            str(case.get("case_id", "")).strip(),
            case.get("sources", {}).get("llm_judge", {}),
        )
        for case in cases
        if _is_reviewed_semantic_source(
            case.get("sources", {}).get("llm_judge", {})
        )
    ]
    if len(reviewed_rows) != collection_packet_binding["case_count"]:
        blockers.append("reviewed_semantic_observation_count_mismatch")

    observed_packet_hashes: set[str] = set()
    for case_id, source in reviewed_rows:
        expected_case = packet_cases.get(case_id)
        if expected_case is None:
            blockers.append(f"{case_id}:semantic_collection_case_not_in_packet")
            continue
        metadata = (
            source.get("metadata")
            if isinstance(source.get("metadata"), dict)
            else {}
        )
        packet_hash = metadata.get("semantic_collection_packet_sha256")
        if isinstance(packet_hash, str) and packet_hash:
            observed_packet_hashes.add(packet_hash)
        expected_metadata = {
            "semantic_collection_packet_schema_version": (
                collection_packet_binding["schema_version"]
            ),
            "semantic_collection_packet_id": (
                collection_packet_binding["packet_id"]
            ),
            "semantic_collection_packet_sha256": (
                collection_packet_binding["packet_sha256"]
            ),
            "semantic_collection_dataset_id": (
                collection_packet_binding["dataset_id"]
            ),
            "semantic_collection_case_count": (
                collection_packet_binding["case_count"]
            ),
            "semantic_collection_target_observation_count": (
                collection_packet_binding["target_observation_count"]
            ),
            "semantic_collection_case_id": case_id,
            "semantic_collection_case_sdk_language": (
                expected_case["sdk_language"]
            ),
            "semantic_collection_case_prompt_template_id": (
                expected_case["prompt_template_id"]
            ),
            "semantic_collection_case_prompt_material_sha256": (
                expected_case["prompt_material_sha256"]
            ),
        }
        for field, expected_value in expected_metadata.items():
            if metadata.get(field) != expected_value:
                blockers.append(f"{case_id}:{field}_mismatch")

    if len(observed_packet_hashes) > 1:
        blockers.append("semantic_collection_packet_sha256_mixed")
    if observed_packet_hashes != {
        collection_packet_binding["packet_sha256"]
    }:
        blockers.append("semantic_collection_packet_sha256_cohort_mismatch")

    blockers = sorted(set(blockers))
    return not blockers, blockers


def _reviewed_semantic_case_ids(cases: list[dict[str, Any]]) -> list[str]:
    return sorted(
        str(case.get("case_id", ""))
        for case in cases
        if _is_reviewed_semantic_source(
            case.get("sources", {}).get("llm_judge", {})
        )
    )


def _is_reviewed_semantic_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    if source.get("available") is not True or source.get("status") != "available":
        return False
    if not is_canonical_private_evidence_ref(source.get("evidence_ref")):
        return False
    provider = str(source.get("provider", "")).strip().lower()
    if provider in {"", "offline_reference", "offline reference judge samples"}:
        return False
    if not str(source.get("model", "")).strip():
        return False

    metadata = (
        source.get("metadata")
        if isinstance(source.get("metadata"), dict)
        else {}
    )
    if any(
        not str(metadata.get(field, "")).strip()
        for field in (
            "prompt_template_id",
            "prompt_hash",
            "response_hash",
            "sdk_language",
        )
    ):
        return False
    if str(metadata.get("review_status", "")).strip().lower() != "reviewed":
        return False
    if str(metadata.get("sdk_language", "")).strip().lower() not in {
        "python",
        "typescript",
    }:
        return False
    if any(
        not isinstance(metadata.get(field), str)
        or REVIEWER_RECEIPT_PATTERN.fullmatch(metadata[field]) is None
        for field in ("prompt_hash", "response_hash", "reviewer_receipt")
    ):
        return False
    reviewed_at = metadata.get("reviewed_at_unix_ms")
    if (
        isinstance(reviewed_at, bool)
        or not isinstance(reviewed_at, int)
        or reviewed_at <= 0
    ):
        return False

    cost = source.get("cost") if isinstance(source.get("cost"), dict) else {}
    prompt_tokens = cost.get("prompt_tokens")
    completion_tokens = cost.get("completion_tokens")
    estimated_usd = cost.get("estimated_usd")
    return (
        not isinstance(prompt_tokens, bool)
        and isinstance(prompt_tokens, int)
        and prompt_tokens > 0
        and not isinstance(completion_tokens, bool)
        and isinstance(completion_tokens, int)
        and completion_tokens > 0
        and not isinstance(estimated_usd, bool)
        and isinstance(estimated_usd, (int, float))
        and math.isfinite(estimated_usd)
        and estimated_usd > 0
    )


def is_verified_reviewed_semantic_source(source: Any) -> bool:
    """Return whether a semantic judge row is sufficient for acceptance evidence."""
    return (
        isinstance(source, dict)
        and source.get("source") == "llm_judge"
        and _is_reviewed_semantic_source(source)
    )


def is_verified_reviewed_releasefoundry_source(source: Any) -> bool:
    """Return whether an ReleaseFoundry row has reviewed identity and per-test receipts."""
    if not isinstance(source, dict):
        return False
    return (
        source.get("source") == "releasefoundry_grading"
        and source.get("status") == "available"
        and str(source.get("provider", "")).strip().lower()
        == RELEASEFOUNDRY_SERVER_SIDE_PROVIDER
        and str(source.get("model", "")).strip().lower()
        == RELEASEFOUNDRY_SERVER_SIDE_MODEL
        and _is_reviewed_releasefoundry_source(source)
        and _has_verified_releasefoundry_terminal_receipt(source)
    )


def _releasefoundry_public_merge_gate(
    cases: list[dict[str, Any]],
    releasefoundry_counts: dict[str, Any],
    expected_count: int,
    commands: list[str],
    run_receipt_artifact: Any,
) -> dict[str, Any]:
    current_available, current_available_valid = _strict_nonnegative_count(
        releasefoundry_counts.get("available", 0)
    )
    current_missing, current_missing_valid = _strict_nonnegative_count(
        releasefoundry_counts.get("missing", expected_count),
        fallback=expected_count,
    )
    invalid_count_fields = []
    if not current_available_valid:
        invalid_count_fields.append("source_coverage.releasefoundry_grading.available")
    if not current_missing_valid:
        invalid_count_fields.append("source_coverage.releasefoundry_grading.missing")
    reviewed_count = _reviewed_releasefoundry_count(cases)
    terminal_receipt_count = _terminal_scoring_verified_releasefoundry_count(cases)
    receipt_cohort_consistent, receipt_cohort_blockers = (
        _releasefoundry_receipt_cohort_consistency(cases, expected_count)
    )
    receipt_artifact_binding = validate_releasefoundry_run_receipt_binding(
        [
            {
                "case_id": case.get("case_id"),
                "metadata": (
                    case.get("sources", {})
                    .get("releasefoundry_grading", {})
                    .get("metadata")
                ),
            }
            for case in cases
        ],
        run_receipt_artifact,
        expected_case_ids=[
            case.get("case_id")
            for case in cases
        ],
    )
    count_complete = (
        expected_count > 0
        and not invalid_count_fields
        and current_available >= expected_count
        and current_missing == 0
    )
    review_complete = reviewed_count >= expected_count
    terminal_receipts_complete = terminal_receipt_count >= expected_count
    merged = (
        count_complete
        and review_complete
        and terminal_receipts_complete
        and receipt_cohort_consistent
        and receipt_artifact_binding["valid"]
    )
    if merged:
        status = "merged"
    elif not count_complete:
        status = "not_merged"
    elif not review_complete:
        status = "merged_unreviewed"
    else:
        status = "merged_unverified_scoring"
    gate = {
        "source": "releasefoundry_grading",
        "status": status,
        "public_matrix_merged": merged,
        "safe_to_mark_c3_met": merged,
        "current_public_observation_count": current_available,
        "merged_public_observation_count": reviewed_count if merged else 0,
        "reviewed_public_observation_count": reviewed_count,
        "terminal_scoring_verified_observation_count": (
            terminal_receipt_count
        ),
        "receipt_cohort_consistent": receipt_cohort_consistent,
        "receipt_cohort_blockers": receipt_cohort_blockers,
        "run_receipt_artifact_present": receipt_artifact_binding[
            "artifact_present"
        ],
        "run_receipt_artifact_sha256": receipt_artifact_binding[
            "artifact_sha256"
        ],
        "run_receipt_artifact_binding_valid": receipt_artifact_binding[
            "valid"
        ],
        "run_receipt_artifact_blockers": receipt_artifact_binding["blockers"],
        "missing_public_observation_count": current_missing,
        "missing_reviewed_observation_count": max(0, expected_count - reviewed_count),
        "missing_terminal_scoring_receipt_count": max(
            0,
            expected_count - terminal_receipt_count,
        ),
        "required_public_observation_count": expected_count,
        "expected_reviewed_observation_count": expected_count,
        "required_review_fields": REQUIRED_RELEASEFOUNDRY_REVIEW_FIELDS,
        "required_terminal_scoring_fields": (
            REQUIRED_RELEASEFOUNDRY_TERMINAL_SCORING_FIELDS
        ),
        "public_matrix_path": "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "reviewed_private_import_ref": "docs/evidence/private_refs/a2_releasefoundry_grading_import.review.json",
        "blocking_reason": ""
        if merged
        else (
            "Reviewed ReleaseFoundry grading observations with review_status=reviewed, a canonical "
            "reviewer_receipt, a positive reviewed_at_unix_ms, and canonical private "
            "evidence_ref must be imported from one acceptance run bound to the fixed "
            "dataset identity, complete run lifecycle, exact test set, server-observed "
            "grader version, and independently verified per-test terminal scoring. "
            "The retained public run receipt must hash-bind every observation and "
            "match every run-level and per-test scoring field. "
            "Aggregate markers are not acceptance authority; merge and regenerate "
            "before C3 is met."
        ),
        "required_commands": commands,
    }
    if invalid_count_fields:
        gate["invalid_count_fields"] = invalid_count_fields
    return gate


def _reviewed_releasefoundry_count(cases: list[dict[str, Any]]) -> int:
    return sum(
        1
        for case in cases
        if _is_reviewed_releasefoundry_source(case.get("sources", {}).get("releasefoundry_grading", {}))
    )


def _terminal_scoring_verified_releasefoundry_count(
    cases: list[dict[str, Any]],
) -> int:
    return sum(
        1
        for case in cases
        if _has_verified_releasefoundry_terminal_receipt(
            case.get("sources", {}).get("releasefoundry_grading", {})
        )
    )


def _releasefoundry_receipt_cohort_consistency(
    cases: list[dict[str, Any]],
    expected_count: int,
) -> tuple[bool, list[str]]:
    metadata_rows = []
    for case in cases:
        source = case.get("sources", {}).get("releasefoundry_grading", {})
        if not _has_verified_releasefoundry_terminal_receipt(source):
            continue
        metadata = source.get("metadata")
        if isinstance(metadata, dict):
            metadata_rows.append(metadata)

    blockers = []
    if len(metadata_rows) != expected_count:
        blockers.append("verified_receipt_cohort_count_mismatch")
    if not metadata_rows:
        return False, blockers

    for field in (
        "run_terminal_receipt_sha256",
        "dataset_identity_receipt_sha256",
        "dataset_identity_manifest_sha256",
        "dataset_identity_content_sha256",
        "dataset_identity_content_collection",
        "observed_judge_version",
    ):
        if len({metadata.get(field) for metadata in metadata_rows}) != 1:
            blockers.append(f"{field}_mismatch")

    for field in (
        "run_expected_test_count",
        "run_verified_test_count",
        "dataset_identity_content_item_count",
    ):
        if any(metadata.get(field) != expected_count for metadata in metadata_rows):
            blockers.append(f"{field}_mismatch")

    return not blockers, blockers


def _is_reviewed_releasefoundry_source(source: dict[str, Any]) -> bool:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    reviewer_receipt = metadata.get("reviewer_receipt")
    reviewed_at = metadata.get("reviewed_at_unix_ms")
    return (
        source.get("available") is True
        and is_canonical_private_evidence_ref(source.get("evidence_ref"))
        and str(metadata.get("review_status", "")).lower() == "reviewed"
        and isinstance(reviewer_receipt, str)
        and REVIEWER_RECEIPT_PATTERN.fullmatch(reviewer_receipt) is not None
        and not isinstance(reviewed_at, bool)
        and isinstance(reviewed_at, int)
        and reviewed_at > 0
    )


def _has_verified_releasefoundry_terminal_receipt(source: dict[str, Any]) -> bool:
    if source.get("available") is not True:
        return False
    metadata = (
        source.get("metadata")
        if isinstance(source.get("metadata"), dict)
        else {}
    )
    signal_types = metadata.get("grading_signal_types")
    blockers = metadata.get("terminal_receipt_blockers")
    run_blockers = metadata.get("run_terminal_receipt_blockers")
    dataset_identity_blockers = metadata.get("dataset_identity_blockers")
    observed_judge_version = metadata.get("observed_judge_version")
    dataset_identity_collection = metadata.get(
        "dataset_identity_content_collection"
    )
    dataset_identity_item_count = metadata.get(
        "dataset_identity_content_item_count"
    )
    run_expected_test_count = metadata.get("run_expected_test_count")
    run_verified_test_count = metadata.get("run_verified_test_count")
    canonical_signal_types = (
        isinstance(signal_types, list)
        and bool(signal_types)
        and signal_types == sorted(set(signal_types))
        and all(
            isinstance(signal_type, str)
            and signal_type in TEST_SCORING_SIGNAL_TYPES
            for signal_type in signal_types
        )
    )
    return (
        metadata.get("terminal_scoring_receipt_schema_version")
        == TEST_SCORING_SUMMARY_SCHEMA_VERSION
        and metadata.get("terminal_status") in SCORING_TERMINAL_STATUSES
        and metadata.get("terminal_status_verified") is True
        and metadata.get("timestamps_verified") is True
        and metadata.get("response_evidence_verified") is True
        and metadata.get("server_grading_signal_verified") is True
        and metadata.get("terminal_scoring_verified") is True
        and canonical_signal_types
        and isinstance(blockers, list)
        and blockers == []
        and metadata.get("run_terminal_receipt_schema_version")
        == PUBLIC_RECEIPT_SCHEMA_VERSION
        and _is_sha256(metadata.get("run_terminal_receipt_sha256"))
        and isinstance(run_expected_test_count, int)
        and not isinstance(run_expected_test_count, bool)
        and run_expected_test_count > 0
        and isinstance(run_verified_test_count, int)
        and not isinstance(run_verified_test_count, bool)
        and run_verified_test_count > 0
        and run_verified_test_count == run_expected_test_count
        and metadata.get("run_receipt_complete") is True
        and metadata.get("run_dataset_id_verified") is True
        and metadata.get("run_result_terminal_verified") is True
        and metadata.get("server_grading_lifecycle_verified") is True
        and metadata.get("exact_test_set_verified") is True
        and metadata.get(
            "all_expected_tests_terminal_scoring_verified"
        )
        is True
        and isinstance(observed_judge_version, str)
        and bool(observed_judge_version.strip())
        and metadata.get("judge_version_source") == "server_observed"
        and metadata.get("judge_version_verified") is True
        and metadata.get(
            "aggregate_marker_used_as_acceptance_authority"
        )
        is False
        and isinstance(run_blockers, list)
        and run_blockers == []
        and metadata.get("dataset_identity_receipt_schema_version")
        == DATASET_IDENTITY_RECEIPT_SCHEMA_VERSION
        and metadata.get("dataset_identity_verified") is True
        and _is_sha256(metadata.get("dataset_identity_receipt_sha256"))
        and _is_sha256(metadata.get("dataset_identity_manifest_sha256"))
        and _is_sha256(metadata.get("dataset_identity_content_sha256"))
        and isinstance(dataset_identity_collection, str)
        and bool(dataset_identity_collection.strip())
        and isinstance(dataset_identity_item_count, int)
        and not isinstance(dataset_identity_item_count, bool)
        and dataset_identity_item_count > 0
        and isinstance(dataset_identity_blockers, list)
        and dataset_identity_blockers == []
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and REVIEWER_RECEIPT_PATTERN.fullmatch(value) is not None
    )


def _load_case_map(path: str | Path) -> dict[str, str]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _a1_real_api_evidence_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {
            "available": False,
            "index_path": target.as_posix(),
            "reason": "A1 public real API evidence index is not available yet.",
            "c3_grading_ready": False,
        }

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "available": False,
            "index_path": target.as_posix(),
            "reason": "A1 public real API evidence index is not a JSON object.",
            "c3_grading_ready": False,
        }

    records = [record for record in payload.get("records", []) if isinstance(record, dict)]
    real_ok_functions = sorted(
        {
            str(record.get("function"))
            for record in records
            if record.get("dry_run") is False and record.get("status") == "ok" and record.get("function")
        }
    )
    mutating_functions = sorted(
        {
            str(record.get("function"))
            for record in records
            if str(record.get("function", "")).startswith("create_")
        }
    )
    real_records = [record for record in records if record.get("dry_run") is False]
    real_read_records = [
        record
        for record in real_records
        if str(record.get("function", "")).startswith(("get_", "list_"))
        or record.get("function") in {"init", "keep_alive"}
    ]
    real_create_request_records = [
        record for record in real_records if record.get("function") == "create_request"
    ]
    real_quota_records = [
        record for record in real_records if isinstance(record.get("quota"), dict) and record["quota"].get("blocked")
    ]
    plan_batch_records = [record for record in records if record.get("function") == "plan_batch"]
    validate_gate_records = [record for record in records if record.get("function") == "validate_gate"]
    c3_candidate_records = [
        record
        for record in records
        if record.get("function") in {"get_run", "list_runs"} and record.get("dry_run") is False
    ]
    counts, invalid_count_fields = _validated_nonnegative_counts(
        payload,
        {
            "total_records": len(records),
            "quota_block_count": 0,
        },
    )
    return {
        "available": not invalid_count_fields,
        "index_path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "label": str(payload.get("label", "")),
        "field_map_version": str(payload.get("field_map_version", "")),
        "total_records": counts["total_records"],
        "status_counts": payload.get("status_counts", {}),
        "function_counts": payload.get("function_counts", {}),
        "quota_block_count": counts["quota_block_count"],
        "real_ok_functions": real_ok_functions,
        "mutating_functions_present": mutating_functions,
        "real_record_count": len(real_records),
        "real_read_status_counts": _count_records(real_read_records, "status"),
        "real_create_request_status_counts": _count_records(real_create_request_records, "status"),
        "real_create_request_error_kind_counts": _count_records(real_create_request_records, "error_kind"),
        "real_quota_gate": _quota_gate_summary(real_quota_records),
        "api_probe_gate_validation": _api_probe_gate_validation_summary(plan_batch_records, validate_gate_records),
        "c3_candidate_record_count": len(c3_candidate_records),
        "c3_grading_ready": False,
        "notes": [
            "A1 index is public-safe evidence of API reachability and field shapes, not an ReleaseFoundry grading import.",
            "Create-request records are commercial API shape evidence; they do not count as server-side grading.",
            "C3 still requires scanner-confirmed 6/6 A2 grading cases and reviewed releasefoundry_grading rows before public merge.",
            *(
                [
                    "Malformed non-negative integer count fields make this evidence index unavailable: "
                    + ", ".join(invalid_count_fields)
                    + "."
                ]
                if invalid_count_fields
                else []
            ),
        ],
    }


def _a1_official_api_readonly_manifest_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {
            "available": False,
            "path": target.as_posix(),
            "schema_version": "",
            "status": "missing",
            "source_private_manifest_present": False,
            "read_step_count": 0,
            "ok_or_planned_step_count": 0,
            "error_step_count": 0,
            "quota_block_count": 0,
            "public_safe": False,
            "redacted_summary_fields_only": False,
            "raw_payload_values_included": False,
            "ready_for_a2_evidence_context": False,
            "notes": [
                "A1 official API readonly manifest summary is not available on this branch yet.",
                "When present, A2 uses it as public API reachability context, not as C3 server-side grading evidence.",
            ],
        }

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "available": False,
            "path": target.as_posix(),
            "schema_version": "",
            "status": "invalid",
            "source_private_manifest_present": False,
            "read_step_count": 0,
            "ok_or_planned_step_count": 0,
            "error_step_count": 0,
            "quota_block_count": 0,
            "public_safe": False,
            "redacted_summary_fields_only": False,
            "raw_payload_values_included": False,
            "ready_for_a2_evidence_context": False,
            "notes": ["A1 official API readonly manifest summary is not a JSON object."],
        }

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    public_safety = payload.get("public_safety") if isinstance(payload.get("public_safety"), dict) else {}
    step_summaries = [step for step in payload.get("step_summaries", []) if isinstance(step, dict)]
    public_safe = _official_manifest_public_safe(public_safety)
    counts, invalid_count_fields = _validated_nonnegative_counts(
        summary,
        {
            "read_steps": 0,
            "ok_or_planned_steps": 0,
            "error_steps": 0,
            "quota_block_count": 0,
        },
    )
    ready = bool(
        public_safe
        and not invalid_count_fields
        and str(payload.get("status", "")) not in {"invalid"}
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "status": str(payload.get("status", "")),
        "source_private_manifest_present": payload.get("source_private_manifest_present") is True,
        "read_step_count": counts["read_steps"],
        "ok_or_planned_step_count": counts["ok_or_planned_steps"],
        "error_step_count": counts["error_steps"],
        "quota_block_count": counts["quota_block_count"],
        "modalities": [str(modality) for modality in summary.get("modalities", [])],
        "step_ids": sorted(str(step.get("step_id", "")) for step in step_summaries if step.get("step_id")),
        "public_safe": public_safe,
        "redacted_summary_fields_only": public_safety.get("redacted_summary_fields_only") is True,
        "raw_payload_values_included": public_safety.get("raw_payload_values_included") is True,
        "ready_for_a2_evidence_context": ready,
        "notes": [
            "A1 official API readonly manifest summary can support A2 evidence context and API shape confidence.",
            "It does not count as reviewed releasefoundry_grading rows for C3.",
            *(
                [
                    "Malformed non-negative integer count fields block A2 evidence readiness: "
                    + ", ".join(invalid_count_fields)
                    + "."
                ]
                if invalid_count_fields
                else []
            ),
        ],
    }


def _a1_official_api_mutating_index_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_mutating_index(target, "A1 official API mutating calibration index is not available yet.")

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _missing_mutating_index(target, "A1 official API mutating calibration index is not a JSON object.")

    records = [record for record in payload.get("records", []) if isinstance(record, dict)]
    mutating_step_ids = sorted(
        {
            str(step_id)
            for record in records
            for step_id in record.get("mutating_step_ids", [])
            if str(step_id).strip()
        }
    )
    modalities = sorted(
        {
            str(modality)
            for record in records
            for modality in record.get("summary_modalities", [])
            if str(modality).strip()
        }
    )
    observed_error_kinds = sorted(
        {
            str(error_kind)
            for record in records
            for error_kind in record.get("observed_error_kinds", [])
            if str(error_kind).strip()
        }
    )
    raw_payloads_included = (
        payload.get("raw_payloads_included") is True
        or any(record.get("raw_payloads_included") is True for record in records)
    )
    secret_values_included = payload.get("secret_values_included") is True
    public_safe = (
        payload.get("public_safe") is True
        and raw_payloads_included is False
        and secret_values_included is False
    )
    count_fields = ("total_steps", "read_steps", "quota_block_count")
    invalid_count_fields = sorted(
        f"records[{record_index}].{field}"
        for record_index, record in enumerate(records)
        for field in count_fields
        if field in record and not _strict_nonnegative_count(record.get(field))[1]
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "public_safe": public_safe,
        "raw_payloads_included": raw_payloads_included,
        "secret_values_included": secret_values_included,
        "record_count": len(records),
        "status_counts": _count_records(records, "status"),
        "modalities": modalities,
        "mutating_step_ids": mutating_step_ids,
        "observed_error_kinds": observed_error_kinds,
        "total_steps": sum(_nonnegative_count(record.get("total_steps")) for record in records),
        "read_step_count": sum(_nonnegative_count(record.get("read_steps")) for record in records),
        "mutating_step_count": len(mutating_step_ids),
        "quota_block_count": sum(_nonnegative_count(record.get("quota_block_count")) for record in records),
        "private_manifest_count": sum(1 for record in records if record.get("private_manifest")),
        "ready_for_a2_evidence_context": public_safe and bool(records) and not invalid_count_fields,
        "c3_grading_ready": False,
        "notes": [
            "A1 mutating calibration index is public-safe quota/error shape evidence for official create-request calls.",
            "It does not count as reviewed releasefoundry_grading rows for C3.",
            *(
                [
                    "Malformed non-negative integer count fields block A2 evidence readiness: "
                    + ", ".join(invalid_count_fields)
                    + "."
                ]
                if invalid_count_fields
                else []
            ),
        ],
    }


def _a1_official_api_paid_media_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_paid_media_summary(
            target,
            "A1 official API paid-media manifest summary is not available yet.",
        )

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _missing_paid_media_summary(
            target,
            "A1 official API paid-media manifest summary is not a JSON object.",
        )

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    guardrails = payload.get("guardrails") if isinstance(payload.get("guardrails"), dict) else {}
    output_policy = guardrails.get("output_policy") if isinstance(guardrails.get("output_policy"), dict) else {}
    public_safety = payload.get("public_safety") if isinstance(payload.get("public_safety"), dict) else {}
    step_summaries = [step for step in payload.get("step_summaries", []) if isinstance(step, dict)]
    mutating_steps = [
        step
        for step in step_summaries
        if step.get("kind") == "mutate" or str(step.get("function", "")).startswith("create_")
    ]
    quota_blocked_steps = [step for step in step_summaries if step.get("quota_blocked") is True]
    public_safe = _official_manifest_public_safe(public_safety)
    guardrail_summary = {
        "execute_requires_small_batch": guardrails.get("execute_requires_small_batch") is True,
        "mutating_execute_requires_quota_gate": guardrails.get("mutating_execute_requires_quota_gate") is True,
        "mutating_requires_include_mutating": guardrails.get("mutating_requires_include_mutating") is True,
        "paid_media_requires_allow_paid_media": guardrails.get("paid_media_requires_allow_paid_media") is True,
        "quota_gate_present": guardrails.get("quota_gate_present") is True,
        "output_is_private": output_policy.get("output_is_private") is True,
        "private_output_required": output_policy.get("private_output_required") is True,
        "raw_records_private": guardrails.get("raw_records_private") is True,
        "full_record_stdout_blocked": output_policy.get("full_record_stdout_blocked") is True,
    }
    ready = bool(
        public_safe
        and guardrail_summary["quota_gate_present"]
        and guardrail_summary["paid_media_requires_allow_paid_media"]
        and guardrail_summary["mutating_execute_requires_quota_gate"]
        and guardrail_summary["output_is_private"]
    )
    counts, invalid_count_fields = _validated_nonnegative_counts(
        summary,
        {
            "total_steps": len(step_summaries),
            "read_steps": 0,
            "mutating_steps": len(mutating_steps),
            "ok_or_planned_steps": 0,
            "error_steps": 0,
            "quota_block_count": len(quota_blocked_steps),
            "estimated_calls": 0,
        },
    )
    ready = ready and not invalid_count_fields
    error_step_count = counts["error_steps"]
    quota_block_count = counts["quota_block_count"]
    safe_for_claims = bool(
        not invalid_count_fields
        and str(payload.get("status", "")) == "ok"
        and error_step_count == 0
        and quota_block_count == 0
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "status": str(payload.get("status", "")),
        "mode": str(payload.get("mode", "")),
        "source_private_manifest_present": payload.get("source_private_manifest_present") is True,
        "public_safe": public_safe,
        "redacted_summary_fields_only": public_safety.get("redacted_summary_fields_only") is True,
        "raw_payload_values_included": public_safety.get("raw_payload_values_included") is True,
        "guardrails": guardrail_summary,
        "total_step_count": counts["total_steps"],
        "read_step_count": counts["read_steps"],
        "mutating_step_count": counts["mutating_steps"],
        "ok_or_planned_step_count": counts["ok_or_planned_steps"],
        "error_step_count": error_step_count,
        "quota_block_count": quota_block_count,
        "estimated_call_count": counts["estimated_calls"],
        "modalities": [str(modality) for modality in summary.get("modalities", [])],
        "step_ids": sorted(str(step.get("step_id", "")) for step in step_summaries if step.get("step_id")),
        "mutating_functions": sorted(
            {str(step.get("function", "")) for step in mutating_steps if step.get("function")}
        ),
        "mutating_modalities": sorted(
            {str(step.get("modality", "")) for step in mutating_steps if step.get("modality")}
        ),
        "quota_blocked_step_ids": sorted(
            str(step.get("step_id", "")) for step in quota_blocked_steps if step.get("step_id")
        ),
        "quota_remaining_observed": any(step.get("quota_remaining_present") is True for step in step_summaries),
        "status_code_counts": _count_records(step_summaries, "status_code"),
        "ready_for_a2_evidence_context": ready,
        "safe_for_paid_media_claims": safe_for_claims,
        "c3_grading_ready": False,
        "notes": [
            "A1 paid-media manifest summary is public-safe quota/error behavior context for mutating media calls.",
            "Partial or quota-blocked paid-media summaries must not be treated as hosted media readiness or C3 grading evidence.",
            *(
                [
                    "Malformed non-negative integer count fields block A2 evidence readiness and paid-media claims: "
                    + ", ".join(invalid_count_fields)
                    + "."
                ]
                if invalid_count_fields
                else []
            ),
        ],
    }


def _a1_payment_provider_readiness_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_payment_provider_readiness(
            target,
            "A1 payment provider readiness packet is not available on this branch yet.",
        )

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _missing_payment_provider_readiness(
            target,
            "A1 payment provider readiness packet is not a JSON object.",
        )

    payment_call_policy = (
        payload.get("payment_call_policy")
        if isinstance(payload.get("payment_call_policy"), dict)
        else {}
    )
    provider_secret_policy = (
        payload.get("provider_secret_policy")
        if isinstance(payload.get("provider_secret_policy"), dict)
        else {}
    )
    human_real_card_testing = (
        payload.get("human_real_card_testing")
        if isinstance(payload.get("human_real_card_testing"), dict)
        else {}
    )
    providers = [provider for provider in payload.get("providers", []) if isinstance(provider, dict)]
    webhook_hash_envelopes = [
        envelope for envelope in payload.get("webhook_hash_envelopes", []) if isinstance(envelope, dict)
    ]
    object_evidence_paths = [
        evidence for evidence in payload.get("object_evidence_paths", []) if isinstance(evidence, dict)
    ]
    provider_names = sorted(str(provider.get("provider", "")) for provider in providers if provider.get("provider"))
    modes = sorted(
        {
            str(mode)
            for provider in providers
            for mode in provider.get("modes", [])
            if str(mode).strip()
        }
    )
    payment_methods = sorted(
        {
            str(method)
            for provider in providers
            for method in provider.get("payment_methods", [])
            if str(method).strip()
        }
    )
    hosted_surface_count = len(
        [provider for provider in providers if str(provider.get("hosted_surface", "")).strip()]
    )
    provider_called = (
        payment_call_policy.get("provider_called") is True
        or any(
            isinstance(provider.get("side_effects"), dict)
            and provider["side_effects"].get("provider_called") is True
            for provider in providers
        )
    )
    checkout_or_portal_called = (
        payment_call_policy.get("checkout_or_portal_called") is True
        or any(
            isinstance(provider.get("side_effects"), dict)
            and provider["side_effects"].get("checkout_or_portal_called") is True
            for provider in providers
        )
    )
    real_charge_possible = (
        payment_call_policy.get("real_charge_possible") is True
        or any(
            isinstance(provider.get("side_effects"), dict)
            and provider["side_effects"].get("real_charge_possible") is True
            for provider in providers
        )
    )
    ci_payment_calls_allowed = payment_call_policy.get("ci_payment_calls_allowed") is True
    raw_secret_values_allowed = provider_secret_policy.get("raw_secret_values_allowed") is True
    secret_reference_prefixes = _string_list(provider_secret_policy.get("secret_reference_prefixes"))
    forbidden_material = _string_list(provider_secret_policy.get("forbidden_material"))
    raw_payload_included = any(envelope.get("raw_payload_included") is True for envelope in webhook_hash_envelopes)
    secret_value_present = any(envelope.get("secret_value_present") is True for envelope in webhook_hash_envelopes)
    verified_webhook_hash_count = len(
        [
            envelope
            for envelope in webhook_hash_envelopes
            if envelope.get("verified") is True and str(envelope.get("payload_sha256", "")).strip()
        ]
    )
    public_evidence_path_count = len(
        [
            evidence
            for evidence in object_evidence_paths
            if evidence.get("classification") == "public_contract"
            and evidence.get("allowed_in_public_repo") is True
        ]
    )
    private_ref_path_count = len(
        [
            evidence
            for evidence in object_evidence_paths
            if evidence.get("classification") in {"private_ref", "operator_runbook"}
            and evidence.get("allowed_in_public_repo") is False
        ]
    )
    stored_card_data_allowed = human_real_card_testing.get("stored_card_data_allowed") is True
    human_real_card_automation_allowed = human_real_card_testing.get("automation_allowed") is True
    human_real_card_testing_allowed = human_real_card_testing.get("allowed") is True
    public_safe = payload.get("public_safe") is True
    ready = bool(
        public_safe
        and not provider_called
        and not checkout_or_portal_called
        and not real_charge_possible
        and not ci_payment_calls_allowed
        and not raw_secret_values_allowed
        and not raw_payload_included
        and not secret_value_present
        and not stored_card_data_allowed
        and not human_real_card_automation_allowed
        and {"stripe", "wechat_pay", "alipay"} <= set(provider_names)
        and {"test", "live"} <= set(modes)
        and verified_webhook_hash_count >= 3
        and public_evidence_path_count >= 3
        and private_ref_path_count >= 1
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "owner": str(payload.get("owner", "")),
        "public_safe": public_safe,
        "provider_count": len(providers),
        "providers": provider_names,
        "mode_count": len(modes),
        "modes": modes,
        "hosted_surface_count": hosted_surface_count,
        "payment_methods": payment_methods,
        "provider_called": provider_called,
        "checkout_or_portal_called": checkout_or_portal_called,
        "real_charge_possible": real_charge_possible,
        "ci_payment_calls_allowed": ci_payment_calls_allowed,
        "raw_secret_values_allowed": raw_secret_values_allowed,
        "secret_reference_prefixes": secret_reference_prefixes,
        "forbidden_material_count": len(forbidden_material),
        "webhook_hash_envelope_count": len(webhook_hash_envelopes),
        "verified_webhook_hash_count": verified_webhook_hash_count,
        "raw_payload_included": raw_payload_included,
        "secret_value_present": secret_value_present,
        "human_real_card_testing_allowed": human_real_card_testing_allowed,
        "human_real_card_automation_allowed": human_real_card_automation_allowed,
        "stored_card_data_allowed": stored_card_data_allowed,
        "public_evidence_path_count": public_evidence_path_count,
        "private_ref_path_count": private_ref_path_count,
        "ready_for_a2_payment_policy_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "payment_provider_policy_context": ready,
            "can_support_payment_abuse_cases": ready,
            "live_payment_requires_human_operator": ready and human_real_card_testing_allowed,
            "must_not_mark_c3_from_payment_context": True,
        },
        "notes": [
            "A1 payment provider readiness is public-safe payment policy context for A2 cost, abuse, and release gates.",
            "It records provider references and webhook hashes only; it does not prove C3 grading or authorize CI payment calls.",
        ],
    }


def _a1_billing_replay_evidence_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_billing_replay_evidence(
            target,
            "A1 billing replay fixture is not available on this branch yet.",
        )

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _missing_billing_replay_evidence(
            target,
            "A1 billing replay fixture is not a JSON object.",
        )

    billing = payload.get("billing_evidence") if isinstance(payload.get("billing_evidence"), dict) else {}
    public_ledger = payload.get("public_ledger") if isinstance(payload.get("public_ledger"), dict) else {}
    accepted = (
        payload.get("accepted_provider_event")
        if isinstance(payload.get("accepted_provider_event"), dict)
        else {}
    )
    duplicate = (
        payload.get("duplicate_provider_event")
        if isinstance(payload.get("duplicate_provider_event"), dict)
        else {}
    )
    raw_payload_included = _contains_true_flag(payload, {"raw_payload_included"})
    secret_value_present = _contains_true_flag(payload, {"secret_value_present"})
    raw_secret_present = _contains_true_flag(payload, {"raw_secret_present"})
    public_safe = not raw_payload_included and not secret_value_present and not raw_secret_present
    ledger_event_count = _int_value(billing.get("ledger_event_count"))
    provider_event_count = _int_value(billing.get("provider_event_count"))
    usage_units = _int_value(billing.get("usage_units"))
    totals_by_currency = _currency_minor_totals(billing.get("totals_by_currency_minor"))
    duplicate_idempotency_proven = (
        str(accepted.get("ledger_event_id", "")) != ""
        and accepted.get("ledger_event_id") == duplicate.get("ledger_event_id")
        and str(accepted.get("ingest_status", "")) == "accepted"
        and str(duplicate.get("ingest_status", "")) == "duplicate"
        and _int_value(accepted.get("ledger_mutation_count")) >= 1
        and _int_value(duplicate.get("ledger_mutation_count")) == 0
    )
    ready = bool(
        public_safe
        and ledger_event_count > 0
        and provider_event_count > 0
        and usage_units >= 0
        and duplicate_idempotency_proven
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "billing_evidence_schema_version": str(billing.get("schema_version", "")),
        "tenant_id": str(billing.get("tenant_id", "")),
        "project_id": str(billing.get("project_id", "")),
        "provider": str(accepted.get("provider") or public_ledger.get("provider") or ""),
        "mode": str(accepted.get("mode") or public_ledger.get("mode") or ""),
        "ledger_event_count": ledger_event_count,
        "provider_event_count": provider_event_count,
        "usage_units": usage_units,
        "totals_by_currency_minor": totals_by_currency,
        "totals_currencies": sorted(totals_by_currency),
        "billing_snapshot_sha256_present": bool(str(billing.get("billing_snapshot_sha256", "")).strip()),
        "accepted_ingest_status": str(accepted.get("ingest_status", "")),
        "duplicate_ingest_status": str(duplicate.get("ingest_status", "")),
        "accepted_ledger_mutation_count": _int_value(accepted.get("ledger_mutation_count")),
        "duplicate_ledger_mutation_count": _int_value(duplicate.get("ledger_mutation_count")),
        "duplicate_idempotency_proven": duplicate_idempotency_proven,
        "raw_payload_included": raw_payload_included,
        "secret_value_present": secret_value_present,
        "raw_secret_present": raw_secret_present,
        "public_safe": public_safe,
        "ready_for_a2_evidence_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "billing_usage_policy_context": ready,
            "can_support_cost_policy_calibration": ready and usage_units > 0,
            "should_add_billing_abuse_cases": ready,
            "must_not_mark_c3_from_billing_context": True,
        },
        "notes": [
            "A1 billing replay fixture is public-safe usage and provider-ledger evidence for A2 cost/risk policy context.",
            "It does not count as reviewed releasefoundry_grading rows for C3.",
        ],
    }


def _a1_billing_ledger_migration_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_billing_ledger_migration(
            target,
            "A1 billing ledger migration manifest is not available on this branch yet.",
        )

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _missing_billing_ledger_migration(
            target,
            "A1 billing ledger migration manifest is not a JSON object.",
        )

    tables = [table for table in payload.get("tables", []) if isinstance(table, dict)]
    public_safety = payload.get("public_safety") if isinstance(payload.get("public_safety"), dict) else {}
    required_functions = (
        payload.get("required_functions")
        if isinstance(payload.get("required_functions"), dict)
        else {}
    )
    table_names = sorted(str(table.get("name", "")) for table in tables if table.get("name"))
    rls_table_names = sorted(
        str(table.get("name", ""))
        for table in tables
        if table.get("name") and table.get("tenant_column") and table.get("rls_policy")
    )
    constraint_names = sorted(
        {
            str(constraint)
            for table in tables
            for constraint in table.get("required_constraints", [])
            if str(constraint).strip()
        }
    )
    index_names = sorted(
        {
            str(index)
            for table in tables
            for index in table.get("required_indexes", [])
            if str(index).strip()
        }
    )
    function_names = sorted(str(name) for name in required_functions if str(name).strip())
    provider_event_types = _string_list(payload.get("provider_event_types"))
    ledger_event_types = _string_list(payload.get("ledger_event_types"))
    providers = _string_list(payload.get("providers"))
    modes = _string_list(payload.get("modes"))
    currencies = _string_list(payload.get("currencies"))
    raw_provider_payload_stored = public_safety.get("raw_provider_payload_stored") is True
    raw_provider_secret_stored = public_safety.get("raw_provider_secret_stored") is True
    raw_card_data_stored = public_safety.get("raw_card_data_stored") is True
    provider_calls_executed = public_safety.get("provider_calls_executed") is True
    public_safe = not (
        raw_provider_payload_stored
        or raw_provider_secret_stored
        or raw_card_data_stored
        or provider_calls_executed
    )
    tenant_rls_ready = len(tables) > 0 and len(rls_table_names) == len(tables)
    supported_provider_set = set(providers)
    supported_mode_set = set(modes)
    supported_currency_set = set(currencies)
    ready = bool(
        public_safe
        and tenant_rls_ready
        and len(tables) >= 3
        and {"billing_accounts", "billing_provider_events", "billing_ledger_events"} <= set(table_names)
        and {"stripe", "wechat_pay", "alipay"} <= supported_provider_set
        and {"test", "live"} <= supported_mode_set
        and {"usd", "cny"} <= supported_currency_set
        and {"normalize_billing_event_type", "ingest_billing_provider_event", "summarize_billing_ledger"}
        <= set(function_names)
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "version": _int_value(payload.get("version")),
        "migration": str(payload.get("migration", "")),
        "table_count": len(tables),
        "table_names": table_names,
        "tenant_rls_table_count": len(rls_table_names),
        "tenant_rls_ready": tenant_rls_ready,
        "required_index_count": len(index_names),
        "required_constraint_count": len(constraint_names),
        "constraint_names": constraint_names,
        "provider_event_type_count": len(provider_event_types),
        "ledger_event_type_count": len(ledger_event_types),
        "providers": providers,
        "modes": modes,
        "currencies": currencies,
        "required_function_names": function_names,
        "public_safe": public_safe,
        "raw_provider_payload_stored": raw_provider_payload_stored,
        "raw_provider_secret_stored": raw_provider_secret_stored,
        "raw_card_data_stored": raw_card_data_stored,
        "provider_calls_executed": provider_calls_executed,
        "ready_for_a2_evidence_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "sql_billing_policy_context": ready,
            "can_support_billing_abuse_cases": ready,
            "can_cross_check_usage_rollups": ready and "summarize_billing_ledger" in function_names,
            "must_not_mark_c3_from_billing_context": True,
        },
        "notes": [
            "A1 billing ledger migration manifest is public-safe SQL contract evidence for A2 billing/usage policy checks.",
            "It does not count as reviewed releasefoundry_grading rows for C3.",
        ],
    }


def _a1_china_payment_migration_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_china_payment_migration(
            target,
            "A1 China payment migration manifest is not available on this branch yet.",
        )

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _missing_china_payment_migration(
            target,
            "A1 China payment migration manifest is not a JSON object.",
        )

    tables = [table for table in payload.get("tables", []) if isinstance(table, dict)]
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    enforcement = payload.get("enforcement") if isinstance(payload.get("enforcement"), dict) else {}
    table_names = sorted(str(table.get("name", "")) for table in tables if table.get("name"))
    rls_table_names = sorted(
        str(table.get("name", ""))
        for table in tables
        if table.get("name") and table.get("rls_policy")
    )
    mutable_audited_tables = _string_list(payload.get("mutable_audited_tables"))
    append_only_tables = _string_list(payload.get("append_only_tables"))
    required_functions = _string_list(payload.get("required_functions"))
    providers = _string_list(payload.get("providers"))
    billing_ledger_providers = _string_list(enforcement.get("billing_ledger_providers"))
    idempotency_keys = _string_list(enforcement.get("idempotency"))
    required_constraints = sorted(
        {
            str(constraint)
            for table in tables
            for constraint in table.get("required_constraints", [])
            if str(constraint).strip()
        }
    )
    required_indexes = sorted(
        {
            str(index)
            for table in tables
            for index in table.get("required_indexes", [])
            if str(index).strip()
        }
    )
    raw_provider_payload_stored = safety.get("raw_provider_payload_stored") is True
    raw_provider_headers_stored = safety.get("raw_provider_headers_stored") is True
    raw_provider_secrets_stored = safety.get("raw_provider_secrets_stored") is True
    raw_card_data_stored = safety.get("raw_card_data_stored") is True
    pan_stored = safety.get("pan_stored") is True
    cvc_stored = safety.get("cvc_stored") is True
    otp_stored = safety.get("otp_stored") is True
    merchant_credentials_reference_only = safety.get("merchant_credentials_storage") == "reference_only"
    notification_hash_only = safety.get("notification_storage") == "identifier_and_sha256_only"
    bill_file_object_reference_only = safety.get("bill_file_storage") == "object_reference_and_sha256_only"
    mutation_evidence_hash_only = safety.get("mutation_evidence_storage") == "before_and_after_sha256_only"
    public_safe = bool(
        not raw_provider_payload_stored
        and not raw_provider_headers_stored
        and not raw_provider_secrets_stored
        and not raw_card_data_stored
        and not pan_stored
        and not cvc_stored
        and not otp_stored
        and merchant_credentials_reference_only
        and notification_hash_only
        and bill_file_object_reference_only
        and mutation_evidence_hash_only
    )
    tenant_rls_ready = len(tables) > 0 and len(rls_table_names) == len(tables)
    provider_set = set(providers)
    table_set = set(table_names)
    function_set = set(required_functions)
    billing_provider_set = set(billing_ledger_providers)
    has_money_flow_tables = {
        "china_payment_orders",
        "china_payment_refunds",
        "china_payment_provider_notifications",
        "china_payment_daily_bill_files",
        "china_payment_daily_bill_lines",
        "china_payment_reconciliation_discrepancies",
        "china_payment_ledger_links",
    } <= table_set
    has_fail_closed_functions = {
        "china_payment_public_metadata",
        "china_payment_reference_only",
        "china_payment_record_mutation",
        "china_payment_reject_mutation",
        "china_payment_validate_refund",
        "china_payment_validate_ledger_link",
    } <= function_set
    ready = bool(
        payload.get("schema_version") == "releasefoundry.a1_china_payment_migration_manifest.v1"
        and str(payload.get("currency", "")).lower() == "cny"
        and {"wechat_pay", "alipay", "domestic_bank_card"} <= provider_set
        and {"wechat_pay", "alipay", "domestic_bank_card"} <= billing_provider_set
        and public_safe
        and tenant_rls_ready
        and len(tables) >= 10
        and has_money_flow_tables
        and has_fail_closed_functions
        and "china_payment_orders.idempotency_key" in idempotency_keys
        and "china_payment_refunds.idempotency_key" in idempotency_keys
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "version": _int_value(payload.get("version")),
        "migration": str(payload.get("migration", "")),
        "currency": str(payload.get("currency", "")).lower(),
        "provider_count": len(providers),
        "providers": providers,
        "table_count": len(tables),
        "table_names": table_names,
        "mutable_audited_table_count": len(mutable_audited_tables),
        "mutable_audited_tables": mutable_audited_tables,
        "append_only_table_count": len(append_only_tables),
        "append_only_tables": append_only_tables,
        "tenant_rls_table_count": len(rls_table_names),
        "tenant_rls_ready": tenant_rls_ready,
        "required_constraint_count": len(required_constraints),
        "required_index_count": len(required_indexes),
        "required_function_names": required_functions,
        "public_safe": public_safe,
        "raw_provider_payload_stored": raw_provider_payload_stored,
        "raw_provider_headers_stored": raw_provider_headers_stored,
        "raw_provider_secrets_stored": raw_provider_secrets_stored,
        "raw_card_data_stored": raw_card_data_stored,
        "pan_stored": pan_stored,
        "cvc_stored": cvc_stored,
        "otp_stored": otp_stored,
        "merchant_credentials_reference_only": merchant_credentials_reference_only,
        "notification_hash_only": notification_hash_only,
        "bill_file_object_reference_only": bill_file_object_reference_only,
        "mutation_evidence_hash_only": mutation_evidence_hash_only,
        "idempotency_keys": idempotency_keys,
        "billing_ledger_providers": billing_ledger_providers,
        "has_money_flow_tables": has_money_flow_tables,
        "has_fail_closed_functions": has_fail_closed_functions,
        "ready_for_a2_payment_sql_policy_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "china_payment_sql_policy_context": ready,
            "can_support_payment_abuse_cases": ready,
            "can_support_payment_reconciliation_regressions": ready and has_money_flow_tables,
            "can_cross_check_billing_ledger_links": ready and "china_payment_ledger_links" in table_set,
            "must_not_mark_c3_from_payment_sql_context": True,
        },
        "notes": [
            "A1 China payment migration manifest is public-safe SQL contract evidence for A2 payment abuse, reconciliation, and fail-closed policy checks.",
            "It proves hash/reference-only payment persistence semantics, not live money movement or reviewed ReleaseFoundry grading rows.",
        ],
    }


def _a1_payment_verification_security_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_payment_verification_security(
            target,
            "A1 payment verification security SQL is not available on this branch yet.",
        )

    text = target.read_text(encoding="utf-8")
    lowered = text.lower()
    forbidden_aliases = [
        "primaryaccountnumber",
        "bankcardnumber",
        "cardnumber",
        "cardno",
        "accountnumber",
        "pan",
        "cvc",
        "cvv",
        "pin",
        "pinblock",
        "track1",
        "track2",
        "trackdata",
        "cryptogram",
        "otp",
        "onetimepassword",
        "privatekey",
        "merchantprivatekey",
        "certificatepem",
        "webhooksecret",
        "signingsecret",
        "authorization",
        "cookie",
    ]
    forbidden_alias_count = sum(1 for alias in forbidden_aliases if alias in lowered)
    recursive_metadata_check = all(
        marker in lowered
        for marker in (
            "china_payment_public_metadata",
            "jsonb_each",
            "jsonb_array_elements",
            "normalized_key",
        )
    )
    has_card_data_aliases = all(
        alias in lowered for alias in ("primaryaccountnumber", "pan", "cvc", "trackdata")
    )
    has_secret_material_aliases = all(
        alias in lowered for alias in ("clientsecret", "webhooksecret", "privatekey", "authorization")
    )
    verification_artifact_table_present = (
        "create table if not exists china_payment_verification_artifacts" in lowered
    )
    verification_artifact_digest_fields = all(
        marker in lowered
        for marker in (
            "payload_sha256",
            "headers_sha256",
            "signature_sha256",
            "artifact_sha256",
            "verification_key_fingerprint",
        )
    )
    verification_artifact_freshness_window = all(
        marker in lowered
        for marker in (
            "fresh_until",
            "verified_at <= created_at + interval '5 minutes'",
            "fresh_until <= verified_at + interval '24 hours'",
        )
    )
    verification_artifact_append_only = all(
        marker in lowered
        for marker in (
            "revoke update, delete, truncate on china_payment_verification_artifacts",
            "china_payment_reject_verification_artifact_mutation",
            "payment verification artifacts are append-only",
        )
    )
    notification_requires_verified_artifact = all(
        marker in lowered
        for marker in (
            "china_payment_require_verified_notification",
            "verified payment notification requires trusted verification artifact",
            "verification artifact does not match notification scope and digests",
        )
    )
    status_transition_requires_artifact = all(
        marker in lowered
        for marker in (
            "china_payment_require_verified_transition",
            "provider-authoritative payment status transition requires trusted verification artifact",
            "trusted verification artifact is missing, stale, consumed by another notification, or out of scope",
        )
    )
    trusted_apply_functions_present = all(
        marker in lowered
        for marker in (
            "apply_china_payment_verified_order_status",
            "apply_china_payment_verified_refund_status",
            "app.a1_payment_verification_artifact_id",
        )
    )
    project_rls_ready = all(
        marker in lowered
        for marker in (
            "a1_current_project_id",
            "china_payment_verification_artifacts_project_isolation",
            "force row level security",
        )
    )
    role_nobypassrls_assertion = all(
        marker in lowered
        for marker in (
            "a1_role_is_nobypassrls",
            "a1_assert_role_nobypassrls",
            "nobypassrls",
        )
    )
    metadata_constraints_present = all(
        marker in lowered
        for marker in (
            "billing_accounts_metadata_safe",
            "billing_provider_events_metadata_safe",
            "billing_ledger_events_metadata_safe",
            "china_payment_verification_artifacts_metadata_safe",
        )
    )
    raw_payload_storage_allowed = (
        "raw_payload_included true" in lowered
        or "raw provider payload stored" in lowered
        or "raw_payload bytea" in lowered
    )
    secret_value_storage_allowed = "secret_value" in lowered or "provider_secret text" in lowered
    ready = bool(
        recursive_metadata_check
        and forbidden_alias_count >= 16
        and has_card_data_aliases
        and has_secret_material_aliases
        and verification_artifact_table_present
        and verification_artifact_digest_fields
        and verification_artifact_freshness_window
        and verification_artifact_append_only
        and notification_requires_verified_artifact
        and status_transition_requires_artifact
        and trusted_apply_functions_present
        and project_rls_ready
        and role_nobypassrls_assertion
        and metadata_constraints_present
        and not raw_payload_storage_allowed
        and not secret_value_storage_allowed
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "migration": target.name,
        "public_safe": not raw_payload_storage_allowed and not secret_value_storage_allowed,
        "recursive_metadata_check": recursive_metadata_check,
        "forbidden_alias_count": forbidden_alias_count,
        "has_card_data_aliases": has_card_data_aliases,
        "has_secret_material_aliases": has_secret_material_aliases,
        "verification_artifact_table_present": verification_artifact_table_present,
        "verification_artifact_digest_fields": verification_artifact_digest_fields,
        "verification_artifact_freshness_window": verification_artifact_freshness_window,
        "verification_artifact_append_only": verification_artifact_append_only,
        "notification_requires_verified_artifact": notification_requires_verified_artifact,
        "status_transition_requires_artifact": status_transition_requires_artifact,
        "trusted_apply_functions_present": trusted_apply_functions_present,
        "project_rls_ready": project_rls_ready,
        "role_nobypassrls_assertion": role_nobypassrls_assertion,
        "metadata_constraints_present": metadata_constraints_present,
        "raw_payload_storage_allowed": raw_payload_storage_allowed,
        "secret_value_storage_allowed": secret_value_storage_allowed,
        "ready_for_a2_payment_verification_policy_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "payment_verification_policy_context": ready,
            "can_support_forbidden_payment_data_abuse_cases": ready,
            "can_support_fail_closed_payment_transition_regressions": ready,
            "can_cross_check_verified_notification_artifacts": ready and verification_artifact_table_present,
            "must_not_mark_c3_from_payment_verification_context": True,
        },
        "notes": [
            "A1 payment verification security SQL is public-safe policy context for forbidden payment data, trusted notification, and fail-closed transition checks.",
            "It proves SQL guard semantics, not live provider verification or reviewed ReleaseFoundry grading rows.",
        ],
    }


def _a1_oauth_lifecycle_security_summary(
    sql_path: str | Path,
    evidence_path: str | Path,
) -> dict[str, Any]:
    sql_target = Path(sql_path)
    evidence_target = Path(evidence_path)
    if not sql_target.exists() or not evidence_target.exists():
        return _missing_oauth_lifecycle_security(
            sql_target,
            evidence_target,
            "A1 OAuth lifecycle SQL or public GitHub connection evidence is not available on this branch yet.",
        )

    sql_text = sql_target.read_text(encoding="utf-8")
    lowered = sql_text.lower()
    payload = json.loads(evidence_target.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return _missing_oauth_lifecycle_security(
            sql_target,
            evidence_target,
            "A1 GitHub account connection evidence is not a JSON object.",
        )

    oauth_tables = [
        "users",
        "oauth_attempts",
        "external_identities",
        "sessions",
        "token_secret_refs",
        "oauth_revocations",
        "oauth_audit_events",
        "oauth_outbox",
    ]
    table_names = sorted(
        table
        for table in oauth_tables
        if f"create table if not exists {table}" in lowered
    )
    digest_fields = [
        "email_digest",
        "redirect_uri_digest",
        "state_digest",
        "code_digest",
        "pkce_challenge_digest",
        "nonce_digest",
        "subject_digest",
        "account_binding_digest",
        "session_digest",
        "secret_fingerprint",
        "event_digest",
    ]
    digest_field_count = sum(1 for field in digest_fields if field in lowered)
    recursive_metadata_check = all(
        marker in lowered
        for marker in (
            "a1_oauth_public_metadata",
            "jsonb_each",
            "jsonb_array_elements",
            "normalized_key",
        )
    )
    forbidden_oauth_keys = [
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "authorizationcode",
        "codeverifier",
        "clientsecret",
        "state",
        "nonce",
        "password",
        "cookie",
    ]
    forbidden_key_count = sum(1 for key in forbidden_oauth_keys if key in lowered)
    reference_only_secret_storage = all(
        marker in lowered
        for marker in (
            "a1_oauth_reference_only",
            "token_secret_refs",
            "secret_ref text not null",
            "'access'",
            "'refresh'",
        )
    )
    state_code_replay_controls = all(
        marker in lowered
        for marker in (
            "a1_consume_oauth_attempt",
            "oauth_attempts_state_key",
            "oauth_attempts_consumed_code_key",
            "oauth attempt already consumed or closed",
            "oauth state digest mismatch",
        )
    )
    account_takeover_controls = all(
        marker in lowered
        for marker in (
            "external_identities_provider_subject_key",
            "external_identities_user_provider_key",
            "oauth identity is already linked to another account",
            "oauth identity conflicts with an existing account",
        )
    )
    session_fixation_controls = all(
        marker in lowered
        for marker in (
            "sessions_digest_key",
            "session_digest",
            "insert into sessions",
        )
    )
    revocation_controls = all(
        marker in lowered
        for marker in (
            "a1_revoke_oauth_identity",
            "oauth_revocations",
            "token_secret_refs",
            "status = 'revoked'",
        )
    )
    audit_outbox_controls = all(
        marker in lowered
        for marker in (
            "oauth_audit_events",
            "oauth_outbox",
            "oauth.identity.linked",
            "oauth.identity.revoked",
        )
    )
    hard_delete_rejected = all(
        marker in lowered
        for marker in (
            "a1_oauth_reject_hard_delete",
            "users_reject_hard_delete",
            "sessions_reject_hard_delete",
            "token_secret_refs_reject_hard_delete",
        )
    )
    append_only_audit = all(
        marker in lowered
        for marker in (
            "a1_oauth_reject_append_only_mutation",
            "oauth_revocations_append_only",
            "oauth_audit_events_append_only",
        )
    )
    tenant_rls_ready = all(
        marker in lowered
        for marker in (
            "a1_oauth_assert_runtime_context",
            "a1_current_project_id",
            "force row level security",
            "users_tenant_isolation",
            "oauth_attempts_tenant_isolation",
            "oauth_outbox_tenant_isolation",
        )
    )
    raw_secret_columns_present = any(
        marker in lowered
        for marker in (
            "access_token text",
            "refresh_token text",
            "authorization_code text",
            "client_secret text",
            "raw_provider_response",
            "raw_email",
        )
    )
    raw_public_evidence_present = any(
        payload.get(field) is True
        for field in (
            "raw_state_recorded",
            "pkce_verifier_recorded",
            "authorization_code_recorded",
            "access_token_recorded",
            "client_secret_recorded",
            "raw_provider_response_recorded",
            "token_reference_exposed",
        )
    )
    successful_localhost_connection = bool(
        payload.get("start_status_code") == 200
        and payload.get("callback_status_code") == 200
        and payload.get("connection_status_code") == 200
        and payload.get("replay_denied") is True
        and payload.get("provider_token_revoked_before_local_delete") is True
    )
    scope_boundary_ready = set(_string_list(payload.get("requested_scopes"))) == {
        "read:user",
        "user:email",
    } and set(_string_list(payload.get("granted_scopes"))) == {"read:user", "user:email"}
    public_safe = not raw_secret_columns_present and not raw_public_evidence_present
    ready = bool(
        payload.get("schema_version") == "releasefoundry.github_account_connection_evidence.v1"
        and payload.get("provider") == "github"
        and public_safe
        and len(table_names) == len(oauth_tables)
        and digest_field_count >= 9
        and recursive_metadata_check
        and forbidden_key_count >= 8
        and reference_only_secret_storage
        and state_code_replay_controls
        and account_takeover_controls
        and session_fixation_controls
        and revocation_controls
        and audit_outbox_controls
        and hard_delete_rejected
        and append_only_audit
        and tenant_rls_ready
        and successful_localhost_connection
        and scope_boundary_ready
    )
    return {
        "available": True,
        "sql_path": sql_target.as_posix(),
        "evidence_path": evidence_target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "provider": str(payload.get("provider", "")),
        "environment": str(payload.get("environment", "")),
        "public_safe": public_safe,
        "sql_table_count": len(table_names),
        "sql_tables": table_names,
        "digest_field_count": digest_field_count,
        "recursive_metadata_check": recursive_metadata_check,
        "forbidden_key_count": forbidden_key_count,
        "reference_only_secret_storage": reference_only_secret_storage,
        "state_code_replay_controls": state_code_replay_controls,
        "account_takeover_controls": account_takeover_controls,
        "session_fixation_controls": session_fixation_controls,
        "revocation_controls": revocation_controls,
        "audit_outbox_controls": audit_outbox_controls,
        "hard_delete_rejected": hard_delete_rejected,
        "append_only_audit": append_only_audit,
        "tenant_rls_ready": tenant_rls_ready,
        "raw_secret_columns_present": raw_secret_columns_present,
        "raw_public_evidence_present": raw_public_evidence_present,
        "successful_localhost_connection": successful_localhost_connection,
        "scope_boundary_ready": scope_boundary_ready,
        "token_reference_present": payload.get("token_reference_present") is True,
        "token_reference_exposed": payload.get("token_reference_exposed") is True,
        "memory_backed": payload.get("memory_backed") is True,
        "production_ready": payload.get("production_ready") is True,
        "ready_for_a2_oauth_policy_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "oauth_lifecycle_policy_context": ready,
            "can_support_oauth_abuse_cases": ready,
            "can_support_account_takeover_regressions": ready,
            "can_cross_check_audit_outbox_events": ready and audit_outbox_controls,
            "must_not_mark_c3_from_oauth_context": True,
        },
        "notes": [
            "A1 OAuth lifecycle evidence is public-safe auth policy context for A2 replay, account-linking, and secret-redaction checks.",
            "The current public provider proof is localhost and memory-backed; it is not production OAuth readiness or reviewed ReleaseFoundry grading evidence.",
        ],
    }


def _a1_unified_identity_security_summary(
    runtime_sql_path: str | Path,
    identity_sql_path: str | Path,
    coordinator_sql_path: str | Path,
    revocation_outbox_sql_path: str | Path,
    session_authentication_sql_path: str | Path,
    identity_verification_sql_path: str | Path,
    identity_verification_public_surface_path: str | Path,
    contract_path: str | Path,
    same_account_evidence_path: str | Path,
    google_evidence_path: str | Path,
) -> dict[str, Any]:
    runtime_target = Path(runtime_sql_path)
    identity_target = Path(identity_sql_path)
    coordinator_target = Path(coordinator_sql_path)
    revocation_outbox_target = Path(revocation_outbox_sql_path)
    session_auth_target = Path(session_authentication_sql_path)
    identity_verification_target = Path(identity_verification_sql_path)
    identity_verification_surface_target = Path(identity_verification_public_surface_path)
    contract_target = Path(contract_path)
    same_account_target = Path(same_account_evidence_path)
    google_target = Path(google_evidence_path)
    required_paths = [
        runtime_target,
        identity_target,
        coordinator_target,
        revocation_outbox_target,
        session_auth_target,
        contract_target,
        same_account_target,
        google_target,
    ]
    if any(not target.exists() for target in required_paths):
        return _missing_unified_identity_security(
            runtime_target,
            identity_target,
            coordinator_target,
            revocation_outbox_target,
            session_auth_target,
            identity_verification_target,
            identity_verification_surface_target,
            contract_target,
            same_account_target,
            google_target,
            "A1 unified identity SQL and public OAuth identity evidence are not available on this branch yet.",
        )

    runtime_sql = runtime_target.read_text(encoding="utf-8").lower()
    identity_sql = identity_target.read_text(encoding="utf-8").lower()
    coordinator_sql = coordinator_target.read_text(encoding="utf-8").lower()
    revocation_outbox_sql = revocation_outbox_target.read_text(encoding="utf-8").lower()
    session_auth_sql = session_auth_target.read_text(encoding="utf-8").lower()
    identity_verification_sql = (
        identity_verification_target.read_text(encoding="utf-8").lower()
        if identity_verification_target.exists()
        else ""
    )
    combined_sql = "\n".join(
        [runtime_sql, identity_sql, coordinator_sql, revocation_outbox_sql, session_auth_sql, identity_verification_sql]
    )
    contract = json.loads(contract_target.read_text(encoding="utf-8-sig"))
    same_account = json.loads(same_account_target.read_text(encoding="utf-8-sig"))
    google = json.loads(google_target.read_text(encoding="utf-8-sig"))
    identity_verification_surface: dict[str, Any] = {}
    if identity_verification_surface_target.exists():
        surface_payload = json.loads(identity_verification_surface_target.read_text(encoding="utf-8-sig"))
        if isinstance(surface_payload, dict):
            identity_verification_surface = surface_payload
    if not all(isinstance(payload, dict) for payload in (contract, same_account, google)):
        return _missing_unified_identity_security(
            runtime_target,
            identity_target,
            coordinator_target,
            revocation_outbox_target,
            session_auth_target,
            identity_verification_target,
            identity_verification_surface_target,
            contract_target,
            same_account_target,
            google_target,
            "A1 unified identity contract or evidence payload is not a JSON object.",
        )

    identity_tables = [
        "identity_principals",
        "identity_credentials",
        "identity_organization_memberships",
        "identity_project_memberships",
        "identity_sessions",
        "identity_link_conflicts",
        "identity_account_merges",
        "identity_recovery_challenges",
        "identity_audit_events",
        "identity_outbox",
    ]
    runtime_tables = [
        "oauth_runtime_transactions",
        "oauth_replay_ledger",
        "oauth_token_opaque_refs",
        "oauth_account_connections",
        "oauth_revocation_outbox",
        "oauth_runtime_audit",
    ]
    identity_table_names = sorted(
        table
        for table in identity_tables
        if f"create table if not exists {table}" in identity_sql
    )
    runtime_table_names = sorted(
        table
        for table in runtime_tables
        if f"create table if not exists {table}" in runtime_sql
    )
    coordinator_table_present = "create table if not exists oauth_identity_operations" in coordinator_sql
    security_controls = contract.get("security_controls", {})
    membership_model = contract.get("membership_model", {})
    acceptance = contract.get("acceptance_status", {})
    verification = contract.get("verification_20260710", {})
    evidence_boundary = contract.get("evidence_boundary", {})
    same_account_boundary = same_account.get("evidence_boundary", {})
    google_controls = {
        str(control.get("control_id", "")): control
        for control in google.get("controls", [])
        if isinstance(control, dict)
    }
    required_identity_kinds = _string_list(contract.get("required_identity_kinds"))
    completed_providers = _string_list(contract.get("real_provider_calibration", {}).get("completed"))
    pending_providers = _string_list(contract.get("real_provider_calibration", {}).get("not_completed"))
    same_account_providers = _string_list(same_account.get("canonical_account", {}).get("providers"))
    runtime_checks = {
        str(check.get("check", "")): check
        for check in same_account.get("runtime_checks", [])
        if isinstance(check, dict)
    }
    public_keys = _string_list(same_account.get("public_account_credential_keys"))

    digest_only_identity_storage = all(
        marker in identity_sql
        for marker in (
            "a1_identity_digest_valid",
            "subject_digest text not null",
            "session_digest text not null",
            "request_context_digest text not null",
        )
    ) and all(
        marker in runtime_sql
        for marker in (
            "state_digest text not null",
            "opaque_ref_digest text not null",
            "provider_subject_digest text not null",
        )
    )
    reference_only_secret_storage = all(
        marker in combined_sql
        for marker in (
            "a1_oauth_reference_only",
            "secret_ref text",
            "opaque_ref text not null",
            "oauth_token_opaque_refs",
        )
    )
    recursive_metadata_check = all(
        marker in identity_sql
        for marker in (
            "a1_identity_public_metadata",
            "jsonb_each",
            "jsonb_array_elements",
            "normalized_key",
        )
    )
    tenant_principal_rls_ready = all(
        marker in combined_sql
        for marker in (
            "a1_current_principal_id",
            "a1_current_organization_id",
            "a1_current_project_id",
            "force row level security",
            "oauth_identity_operations_tenant_isolation",
            "identity_project_memberships_tenant_access",
        )
    )
    membership_identity_decoupled = bool(
        membership_model.get("separate_from_identity") is True
        and membership_model.get("references_internal_account_only") is True
        and membership_model.get("credential_unlink_does_not_delete_membership") is True
        and security_controls.get("membership_identity_coupling") == "forbidden"
    )
    account_takeover_controls = bool(
        security_controls.get("same_email_auto_merge") == "forbidden"
        and security_controls.get("unverified_credential_login") == "reject"
        and security_controls.get("cross_account_takeover") == "reject"
        and security_controls.get("caller_supplied_account_id") == "reject"
        and "identity_credentials_global_identity_key" in identity_sql
        and "oauth subject already belongs to another principal" in coordinator_sql
        and "oauth identity idempotency request mismatch" in coordinator_sql
    )
    same_account_provider_link_ready = bool(
        set(same_account_providers) >= {"github", "google"}
        and same_account.get("canonical_account", {}).get("credential_count", 0) >= 2
        and same_account.get("canonical_account", {}).get("all_credentials_verified") is True
        and same_account.get("canonical_account", {}).get("all_credentials_can_login") is True
        and same_account.get("canonical_account", {}).get("membership_count") == 0
        and runtime_checks.get("caller_supplied_account_mismatch", {}).get("status_code") == 403
        and runtime_checks.get("caller_supplied_account_mismatch", {}).get("failed_closed") is True
    )
    public_dto_allowlist_only = bool(
        security_controls.get("public_dto_policy") == "allowlist_only"
        and set(public_keys)
        <= {"can_login", "credential_id", "kind", "linked_at", "provider", "schema_version", "verified"}
        and runtime_checks.get("public_response_forbidden_material_scan", {}).get("status") == "passed"
        and runtime_checks.get("public_response_forbidden_material_scan", {}).get("forbidden_key_hits") == 0
    )
    same_account_secret_material_excluded = all(
        same_account_boundary.get(field) is False
        for field in (
            "raw_account_contact_recorded",
            "raw_provider_subject_recorded",
            "subject_digest_recorded",
            "oauth_code_recorded",
            "oauth_state_recorded",
            "oauth_nonce_recorded",
            "pkce_verifier_recorded",
            "access_token_recorded",
            "refresh_token_recorded",
            "id_token_recorded",
            "token_reference_recorded",
            "client_secret_recorded",
            "callback_query_recorded",
            "raw_provider_response_recorded",
        )
    )
    contract_secret_material_excluded = all(
        evidence_boundary.get(field) is False
        for field in (
            "contains_account_contact_data",
            "contains_provider_identity_data",
            "contains_credential_material",
            "contains_callback_query_data",
            "contains_session_or_cookie_data",
            "contains_provider_response_payload",
        )
    )
    google_secret_material_excluded = all(
        google.get(field) is False
        for field in (
            "raw_state_recorded",
            "nonce_recorded",
            "pkce_verifier_recorded",
            "authorization_code_recorded",
            "access_token_recorded",
            "refresh_token_recorded",
            "id_token_recorded",
            "client_secret_recorded",
            "raw_provider_response_recorded",
            "callback_query_recorded",
            "account_email_recorded",
            "stable_provider_identifier_recorded",
        )
    )
    google_real_provider_ready = bool(
        google.get("schema_version") == "releasefoundry.google_oauth_localhost.v1"
        and google.get("provider") == "google"
        and google.get("public_safe") is True
        and google.get("contains_secret_values") is False
        and google_controls.get("callback_success", {}).get("status") == "verified_real_provider"
        and google_controls.get("callback_success", {}).get("issuer_validation_passed") is True
        and google_controls.get("callback_success", {}).get("audience_validation_passed") is True
        and google_controls.get("callback_success", {}).get("nonce_validation_passed") is True
        and google_controls.get("callback_replay", {}).get("replay_denied") is True
        and google_controls.get("public_response_secret_scan", {}).get("public_response_secret_scan_passed") is True
    )
    outbox_audit_controls = all(
        marker in combined_sql
        for marker in (
            "identity_audit_events",
            "identity_outbox",
            "oauth_revocation_outbox",
            "provider_revoke_and_cleanup",
            "for update skip locked",
        )
    )
    recovery_merge_controls_present = all(
        marker in identity_sql
        for marker in (
            "identity_account_merges",
            "identity_recovery_challenges",
            "a1_merge_identity_accounts",
            "a1_consume_identity_recovery",
            "account merge requires independent approval",
        )
    )
    revocation_outbox_hardening_present = all(
        marker in revocation_outbox_sql
        for marker in (
            "lease_generation bigint not null default 0",
            "a1_claim_identity_revocation_outbox",
            "a1_mark_identity_revocation_provider_revoked",
            "a1_mark_identity_revocation_vault_deleted",
            "a1_complete_identity_revocation_outbox",
            "a1_retry_identity_revocation_outbox",
            "oauth revocation lease lost",
            "for update skip locked",
        )
    )
    revocation_external_checkpoints = all(
        marker in revocation_outbox_sql
        for marker in (
            "provider_revoked_at",
            "vault_deleted_at",
            "cleanup_completed_at",
            "dead_lettered_at",
            "oauth provider revocation is not checkpointed",
        )
    )
    revocation_fenced_retry_ready = all(
        marker in revocation_outbox_sql
        for marker in (
            "target.lease_generation <> p_lease_generation",
            "lease_generation = target.lease_generation + 1",
            "status = 'dead_letter'",
            "p_base_backoff_seconds",
            "p_max_backoff_seconds",
            "available_at = p_now",
        )
    )
    revocation_reconnect_cleanup_safe = all(
        marker in revocation_outbox_sql
        for marker in (
            "token_ref_id = target.token_ref_id",
            "status = 'revocation_pending'",
            "status = 'disconnected'",
        )
    ) and all(
        marker not in revocation_outbox_sql
        for marker in (
            "delete from oauth_account_connections",
            "delete from oauth_token_opaque_refs",
        )
    )
    session_authentication_ready = all(
        marker in session_auth_sql
        for marker in (
            "a1_authenticate_identity_session_digest",
            "a1_assert_role_nobypassrls(session_user)",
            "a1_identity_digest_valid(p_session_digest)",
            "identity_session.session_digest = p_session_digest",
            "principal.status = 'active'",
            "credential.status = 'active'",
            "credential.login_enabled",
            "identity_session.status = 'active'",
            "identity_session.expires_at > clock_timestamp()",
            "organization_membership.status = 'active'",
            "project_membership.status = 'active'",
            "revoke all on function a1_authenticate_identity_session_digest",
            "grant execute on function a1_authenticate_identity_session_digest",
        )
    )
    identity_verification_digest_only = bool(identity_verification_sql) and all(
        marker in identity_verification_sql
        for marker in (
            "identity_verification_challenges",
            "identity_verification_receipts",
            "subject_digest text not null",
            "challenge_digest text not null",
            "code_digest text not null",
            "request_context_digest text not null",
        )
    )
    identity_verification_abuse_controls = bool(identity_verification_sql) and all(
        marker in identity_verification_sql
        for marker in (
            "identity_verification_cooldowns",
            "identity_verification_abuse_budgets",
            "blocked_until",
            "interval '15 minutes'",
            "max_attempts between 1 and 10",
        )
    )
    identity_verification_receipt_controls = bool(identity_verification_sql) and all(
        marker in identity_verification_sql
        for marker in (
            "a1_verify_consume_identity_challenge",
            "a1_bind_verified_identity_credential",
            "a1_login_with_verified_identity",
            "a1_recover_verified_identity",
            "a1_identity_verification_receipt_transition",
            "idempotency_conflict",
        )
    )
    identity_verification_runtime_boundary = bool(identity_verification_sql) and all(
        marker in identity_verification_sql
        for marker in (
            "force row level security",
            "revoke all on table identity_verification_challenges from a1_runtime",
            "revoke all on table identity_verification_receipts from a1_runtime",
            "grant execute on function a1_issue_identity_verification_challenge",
            "grant execute on function a1_verify_consume_identity_challenge",
            "grant execute on function a1_bind_verified_identity_credential",
        )
    )
    identity_verification_public_surface_ready = bool(
        identity_verification_surface.get("schema_version")
        == "releasefoundry.identity_verification_public_surface.v1"
        and identity_verification_surface.get("route_neutral") is True
        and identity_verification_surface.get("secret_policy") == "digest_refs_only"
        and _int_value(identity_verification_surface.get("route_count")) >= 12
    )
    identity_verification_ready = bool(
        identity_verification_digest_only
        and identity_verification_abuse_controls
        and identity_verification_receipt_controls
        and identity_verification_runtime_boundary
        and identity_verification_public_surface_ready
    )
    append_only_controls = all(
        marker in combined_sql
        for marker in (
            "identity_audit_events_append_only",
            "identity_link_conflicts_append_only",
            "oauth_replay_ledger_append_only",
            "oauth_runtime_audit_append_only",
        )
    )
    hard_delete_rejected = all(
        marker in identity_sql
        for marker in (
            "identity_principals_reject_hard_delete",
            "identity_credentials_reject_hard_delete",
            "identity_sessions_reject_hard_delete",
        )
    )
    final_credential_unlink_rejected = bool(
        security_controls.get("last_credential_unlink") == "reject"
        and "cannot unlink the last active login credential" in identity_sql
        and "cannot disconnect the last active login credential" in coordinator_sql
    )
    raw_secret_columns_present = any(
        marker in combined_sql
        for marker in (
            "access_token text",
            "refresh_token text",
            "authorization_code text",
            "client_secret text",
            "raw_provider_response",
            "raw_email",
            "session_token text",
            "cookie text",
        )
    )
    public_safe = bool(
        contract.get("public_safe") is True
        and same_account.get("public_safe") is True
        and google.get("public_safe") is True
        and contract.get("contains_secret_values") is False
        and same_account.get("contains_secret_values") is False
        and google.get("contains_secret_values") is False
        and not raw_secret_columns_present
        and same_account_secret_material_excluded
        and contract_secret_material_excluded
        and google_secret_material_excluded
    )
    domain_invariants_ready = acceptance.get("domain_invariants") == "implemented_and_tested"
    postgres_contract_ready = bool(
        verification.get("postgres_integration", {}).get("passed", 0) >= 8
        and verification.get("postgres_integration", {}).get("runtime_role") == "NOSUPERUSER_NOBYPASSRLS"
    )
    multi_instance_gap_present = any(
        "multi-instance" in str(gap) or "postgres" in str(gap)
        for gap in contract.get("known_implementation_gaps", [])
    ) or acceptance.get("durable_postgres_runtime_wiring") == "not_completed"
    production_ready = bool(
        contract.get("production_ready") is True
        and same_account.get("production_ready") is True
        and google.get("production_ready") is True
    )
    ready = bool(
        contract.get("schema_version") == "releasefoundry.unified_identity.contract.v1"
        and same_account.get("schema_version") == "releasefoundry.unified_identity.same_account_localhost.v1"
        and public_safe
        and len(identity_table_names) == len(identity_tables)
        and len(runtime_table_names) == len(runtime_tables)
        and coordinator_table_present
        and set(required_identity_kinds) >= {"github", "google", "wechat", "qq", "alipay", "phone", "email"}
        and set(completed_providers) >= {"github", "google"}
        and domain_invariants_ready
        and postgres_contract_ready
        and digest_only_identity_storage
        and reference_only_secret_storage
        and recursive_metadata_check
        and tenant_principal_rls_ready
        and account_takeover_controls
        and membership_identity_decoupled
        and same_account_provider_link_ready
        and public_dto_allowlist_only
        and google_real_provider_ready
        and outbox_audit_controls
        and recovery_merge_controls_present
        and revocation_outbox_hardening_present
        and revocation_external_checkpoints
        and revocation_fenced_retry_ready
        and revocation_reconnect_cleanup_safe
        and session_authentication_ready
        and (not identity_verification_target.exists() or identity_verification_ready)
        and append_only_controls
        and hard_delete_rejected
        and final_credential_unlink_rejected
    )
    return {
        "available": True,
        "runtime_sql_path": runtime_target.as_posix(),
        "identity_sql_path": identity_target.as_posix(),
        "coordinator_sql_path": coordinator_target.as_posix(),
        "revocation_outbox_sql_path": revocation_outbox_target.as_posix(),
        "session_authentication_sql_path": session_auth_target.as_posix(),
        "contract_path": contract_target.as_posix(),
        "same_account_evidence_path": same_account_target.as_posix(),
        "google_evidence_path": google_target.as_posix(),
        "schema_version": str(contract.get("schema_version", "")),
        "same_account_schema_version": str(same_account.get("schema_version", "")),
        "google_schema_version": str(google.get("schema_version", "")),
        "public_safe": public_safe,
        "required_identity_kinds": required_identity_kinds,
        "real_provider_calibrated": completed_providers,
        "pending_provider_count": len(pending_providers),
        "identity_table_count": len(identity_table_names),
        "identity_tables": identity_table_names,
        "oauth_runtime_table_count": len(runtime_table_names),
        "oauth_runtime_tables": runtime_table_names,
        "coordinator_table_present": coordinator_table_present,
        "digest_only_identity_storage": digest_only_identity_storage,
        "reference_only_secret_storage": reference_only_secret_storage,
        "recursive_metadata_check": recursive_metadata_check,
        "tenant_principal_rls_ready": tenant_principal_rls_ready,
        "domain_invariants_ready": domain_invariants_ready,
        "postgres_contract_ready": postgres_contract_ready,
        "account_takeover_controls": account_takeover_controls,
        "same_account_provider_link_ready": same_account_provider_link_ready,
        "membership_identity_decoupled": membership_identity_decoupled,
        "public_dto_allowlist_only": public_dto_allowlist_only,
        "secret_material_excluded": same_account_secret_material_excluded
        and contract_secret_material_excluded
        and google_secret_material_excluded,
        "google_real_provider_ready": google_real_provider_ready,
        "outbox_audit_controls": outbox_audit_controls,
        "recovery_merge_controls_present": recovery_merge_controls_present,
        "revocation_outbox_hardening_present": revocation_outbox_hardening_present,
        "revocation_external_checkpoints": revocation_external_checkpoints,
        "revocation_fenced_retry_ready": revocation_fenced_retry_ready,
        "revocation_reconnect_cleanup_safe": revocation_reconnect_cleanup_safe,
        "session_authentication_ready": session_authentication_ready,
        "identity_verification_sql_path": identity_verification_target.as_posix(),
        "identity_verification_public_surface_path": identity_verification_surface_target.as_posix(),
        "identity_verification_surface_schema_version": str(identity_verification_surface.get("schema_version", "")),
        "identity_verification_route_count": _int_value(identity_verification_surface.get("route_count")),
        "identity_verification_digest_only": identity_verification_digest_only,
        "identity_verification_abuse_controls": identity_verification_abuse_controls,
        "identity_verification_receipt_controls": identity_verification_receipt_controls,
        "identity_verification_runtime_boundary": identity_verification_runtime_boundary,
        "identity_verification_public_surface_ready": identity_verification_public_surface_ready,
        "identity_verification_ready": identity_verification_ready,
        "append_only_controls": append_only_controls,
        "hard_delete_rejected": hard_delete_rejected,
        "final_credential_unlink_rejected": final_credential_unlink_rejected,
        "raw_secret_columns_present": raw_secret_columns_present,
        "multi_instance_gap_present": multi_instance_gap_present,
        "production_ready": production_ready,
        "ready_for_a2_identity_policy_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "identity_policy_context": ready,
            "can_support_account_takeover_regressions": ready and account_takeover_controls,
            "can_support_membership_decoupling_regressions": ready and membership_identity_decoupled,
            "can_support_provider_linking_abuse_cases": ready and same_account_provider_link_ready,
            "must_not_mark_c3_from_identity_context": True,
        },
        "notes": [
            "A1 unified identity evidence is public-safe auth policy context for A2 identity, OAuth linking, and membership-decoupling regressions.",
            "Current real-provider proof is localhost and not production readiness; pending China/phone/email providers remain contract-only.",
        ],
    }


def _a1_billing_sql_semantic_contract_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_billing_sql_semantic_contract(
            target,
            "A1 billing SQL semantic contract is not available on this branch yet.",
        )

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _missing_billing_sql_semantic_contract(
            target,
            "A1 billing SQL semantic contract is not a JSON object.",
        )

    provider_config = (
        payload.get("provider_config_storage")
        if isinstance(payload.get("provider_config_storage"), dict)
        else {}
    )
    replay_semantics = (
        payload.get("replay_semantics")
        if isinstance(payload.get("replay_semantics"), dict)
        else {}
    )
    object_linkage = (
        payload.get("object_evidence_linkage")
        if isinstance(payload.get("object_evidence_linkage"), dict)
        else {}
    )
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    replay_status_names = sorted(
        status
        for status in ("accepted", "duplicate", "conflict")
        if isinstance(replay_semantics.get(status), dict)
    )
    replay_records = [
        replay_semantics[status]
        for status in replay_status_names
        if isinstance(replay_semantics.get(status), dict)
    ]
    accepted = replay_semantics.get("accepted") if isinstance(replay_semantics.get("accepted"), dict) else {}
    duplicate = replay_semantics.get("duplicate") if isinstance(replay_semantics.get("duplicate"), dict) else {}
    conflict = replay_semantics.get("conflict") if isinstance(replay_semantics.get("conflict"), dict) else {}
    billing_sql_edges = [
        edge for edge in object_linkage.get("billing_sql_edges", []) if isinstance(edge, dict)
    ]
    hash_only_objects = [
        item for item in object_linkage.get("go_postgres_hash_only_objects", []) if isinstance(item, dict)
    ]
    raw_payload_column_present_count = len(
        [item for item in hash_only_objects if item.get("raw_payload_column_present") is True]
    )
    hash_columns = _string_list(provider_config.get("hash_columns"))
    reference_only_fields = _string_list(provider_config.get("reference_only_fields"))
    forbidden_durable_columns = _string_list(provider_config.get("forbidden_durable_columns"))
    match_key = _string_list(replay_semantics.get("match_key"))
    public_snapshot_fields = _string_list(object_linkage.get("public_snapshot_fields"))
    pytest_targets = _string_list(validation.get("pytest_targets"))
    raw_payload_included = any(record.get("raw_payload_included") is True for record in replay_records)
    secret_value_present = any(record.get("secret_value_present") is True for record in replay_records)
    provider_config_column_present = provider_config.get("provider_config_column_present") is True
    provider_config_object_persisted = provider_config.get("provider_config_object_persisted") is True
    ready = bool(
        payload.get("public_safe") is True
        and provider_config.get("durable_policy") == "hash_or_reference_only"
        and not provider_config_column_present
        and not provider_config_object_persisted
        and "billing_provider_events.payload_sha256" in hash_columns
        and {
            "provider_config",
            "provider_secret",
            "client_secret",
            "raw_payload",
            "payload",
            "card_number",
        }
        <= set(forbidden_durable_columns)
        and set(replay_status_names) == {"accepted", "conflict", "duplicate"}
        and _int_value(accepted.get("ledger_mutation_count")) == 1
        and _int_value(duplicate.get("ledger_mutation_count")) == 0
        and _int_value(conflict.get("ledger_mutation_count")) == 0
        and not raw_payload_included
        and not secret_value_present
        and len(match_key) >= 5
        and len(billing_sql_edges) >= 2
        and len(hash_only_objects) >= 3
        and raw_payload_column_present_count == 0
        and "billing_snapshot_sha256" in public_snapshot_fields
        and str(validation.get("schema_path", ""))
        == "docs/a1/schemas/billing_sql_semantic_contract.schema.json"
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "migration": str(payload.get("migration", "")),
        "public_safe": payload.get("public_safe") is True,
        "durable_policy": str(provider_config.get("durable_policy", "")),
        "provider_config_column_present": provider_config_column_present,
        "provider_config_object_persisted": provider_config_object_persisted,
        "hash_columns": hash_columns,
        "reference_only_field_count": len(reference_only_fields),
        "forbidden_durable_columns": forbidden_durable_columns,
        "forbidden_public_marker_count": len(_string_list(provider_config.get("forbidden_public_markers"))),
        "replay_statuses": replay_status_names,
        "accepted_ledger_mutation_count": _int_value(accepted.get("ledger_mutation_count")),
        "duplicate_ledger_mutation_count": _int_value(duplicate.get("ledger_mutation_count")),
        "conflict_ledger_mutation_count": _int_value(conflict.get("ledger_mutation_count")),
        "raw_payload_included": raw_payload_included,
        "secret_value_present": secret_value_present,
        "match_key": match_key,
        "billing_sql_edge_count": len(billing_sql_edges),
        "go_postgres_hash_only_object_count": len(hash_only_objects),
        "raw_payload_column_present_count": raw_payload_column_present_count,
        "public_snapshot_fields": public_snapshot_fields,
        "pytest_targets": pytest_targets,
        "schema_path": str(validation.get("schema_path", "")),
        "ready_for_a2_sql_policy_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "sql_semantic_policy_context": ready,
            "can_support_replay_regression_cases": ready,
            "can_support_hash_only_artifact_audit": ready,
            "must_not_mark_c3_from_sql_context": True,
        },
        "notes": [
            "A1 billing SQL semantic contract is public-safe SQL and replay semantics context for A2 policy checks.",
            "It validates hash/reference-only billing storage semantics, not reviewed ReleaseFoundry grading rows.",
        ],
    }


def _a1_object_storage_contract_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _missing_object_storage_contract(
            target,
            "A1 object storage contract evidence is not available on this branch yet.",
        )

    text = target.read_text(encoding="utf-8")
    lowered = text.lower()
    supported_backends = sorted(
        backend for backend in ("local-filesystem", "s3-compatible") if backend in lowered
    )
    manifest_fields = sorted(
        field
        for field in ("object_key", "storage_uri", "content_type", "size_bytes", "sha256")
        if field in lowered
    )
    test_targets = sorted(
        target_name
        for target_name in ("tests/a1/test_object_storage_contract.py", "tests/a1/test_saas_platform.py")
        if target_name in text
    )
    schema_version = "releasefoundry.object_storage.v1" if "releasefoundry.object_storage.v1" in text else ""
    scoped_object_keys = "category/tenant_id/project_id/run_id/object_id.ext" in text
    manifest_signature_sha256 = "manifest_signature" in lowered and "canonical json sha256" in lowered
    checksum_readback = "checksum" in lowered and "expected/actual sha256" in lowered
    local_readback_sha256 = "local filesystem writes perform a sha256 readback verification" in lowered
    s3_reference_only = "s3-compatible manifests accept reference strings only" in lowered
    lazy_network_adapter = "lazy sdk adapter" in lowered and "network reads require explicit adapter use" in lowered
    sdk_helper_present = "packages/sdk/releasefoundry/storage.py" in text
    api_integration_present = "services/api/platform.py" in text
    evidence_bundle_metadata_present = "evidence bundle records" in lowered and "object_storage" in text
    no_public_raw_values_clause = "public manifests do not include" in lowered
    raw_payload_bytes_included = not (no_public_raw_values_clause and "raw payload bytes" in lowered)
    absolute_local_paths_included = not (
        no_public_raw_values_clause and "absolute local filesystem paths" in lowered
    )
    raw_endpoint_values_included = not (no_public_raw_values_clause and "raw s3/minio endpoints" in lowered)
    raw_access_key_values_included = not (no_public_raw_values_clause and "access keys" in lowered)
    raw_secret_key_values_included = not (no_public_raw_values_clause and "secret keys" in lowered)
    raw_token_values_included = not (no_public_raw_values_clause and "tokens" in lowered and "api keys" in lowered)
    ready = bool(
        schema_version
        and set(supported_backends) == {"local-filesystem", "s3-compatible"}
        and scoped_object_keys
        and len(manifest_fields) == 5
        and manifest_signature_sha256
        and checksum_readback
        and s3_reference_only
        and lazy_network_adapter
        and local_readback_sha256
        and sdk_helper_present
        and api_integration_present
        and evidence_bundle_metadata_present
        and len(test_targets) >= 2
        and not raw_payload_bytes_included
        and not absolute_local_paths_included
        and not raw_endpoint_values_included
        and not raw_access_key_values_included
        and not raw_secret_key_values_included
        and not raw_token_values_included
    )
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": schema_version,
        "public_safe": ready,
        "backend_count": len(supported_backends),
        "supported_backends": supported_backends,
        "scoped_object_keys": scoped_object_keys,
        "manifest_field_count": len(manifest_fields),
        "manifest_fields": manifest_fields,
        "manifest_signature_sha256": manifest_signature_sha256,
        "checksum_readback": checksum_readback,
        "local_readback_sha256": local_readback_sha256,
        "s3_reference_only": s3_reference_only,
        "lazy_network_adapter": lazy_network_adapter,
        "sdk_helper_present": sdk_helper_present,
        "api_integration_present": api_integration_present,
        "evidence_bundle_metadata_present": evidence_bundle_metadata_present,
        "raw_payload_bytes_included": raw_payload_bytes_included,
        "absolute_local_paths_included": absolute_local_paths_included,
        "raw_endpoint_values_included": raw_endpoint_values_included,
        "raw_access_key_values_included": raw_access_key_values_included,
        "raw_secret_key_values_included": raw_secret_key_values_included,
        "raw_token_values_included": raw_token_values_included,
        "test_target_count": len(test_targets),
        "test_targets": test_targets,
        "ready_for_a2_artifact_policy_context": ready,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "object_storage_policy_context": ready,
            "can_support_artifact_bundle_evidence_handoff": ready,
            "can_support_checksum_regression_cases": ready,
            "must_not_mark_c3_from_storage_context": True,
        },
        "notes": [
            "A1 object storage contract is public-safe artifact and bundle handoff context for A2 evidence policy.",
            "It validates manifest/checksum/redaction semantics, not reviewed ReleaseFoundry grading rows.",
        ],
    }


def _missing_mutating_index(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "public_safe": False,
        "raw_payloads_included": False,
        "secret_values_included": False,
        "record_count": 0,
        "status_counts": {},
        "modalities": [],
        "mutating_step_ids": [],
        "observed_error_kinds": [],
        "total_steps": 0,
        "read_step_count": 0,
        "mutating_step_count": 0,
        "quota_block_count": 0,
        "private_manifest_count": 0,
        "ready_for_a2_evidence_context": False,
        "c3_grading_ready": False,
        "notes": [
            reason,
            "When present, A2 uses it as public quota/error behavior context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_paid_media_summary(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "status": "missing",
        "mode": "",
        "source_private_manifest_present": False,
        "public_safe": False,
        "redacted_summary_fields_only": False,
        "raw_payload_values_included": False,
        "guardrails": {
            "execute_requires_small_batch": False,
            "mutating_execute_requires_quota_gate": False,
            "mutating_requires_include_mutating": False,
            "paid_media_requires_allow_paid_media": False,
            "quota_gate_present": False,
            "output_is_private": False,
            "private_output_required": False,
            "raw_records_private": False,
            "full_record_stdout_blocked": False,
        },
        "total_step_count": 0,
        "read_step_count": 0,
        "mutating_step_count": 0,
        "ok_or_planned_step_count": 0,
        "error_step_count": 0,
        "quota_block_count": 0,
        "estimated_call_count": 0,
        "modalities": [],
        "step_ids": [],
        "mutating_functions": [],
        "mutating_modalities": [],
        "quota_blocked_step_ids": [],
        "quota_remaining_observed": False,
        "status_code_counts": {},
        "ready_for_a2_evidence_context": False,
        "safe_for_paid_media_claims": False,
        "c3_grading_ready": False,
        "notes": [
            reason,
            "When present, A2 uses it as public paid-media quota/error context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_payment_provider_readiness(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "owner": "",
        "public_safe": False,
        "provider_count": 0,
        "providers": [],
        "mode_count": 0,
        "modes": [],
        "hosted_surface_count": 0,
        "payment_methods": [],
        "provider_called": False,
        "checkout_or_portal_called": False,
        "real_charge_possible": False,
        "ci_payment_calls_allowed": False,
        "raw_secret_values_allowed": False,
        "secret_reference_prefixes": [],
        "forbidden_material_count": 0,
        "webhook_hash_envelope_count": 0,
        "verified_webhook_hash_count": 0,
        "raw_payload_included": False,
        "secret_value_present": False,
        "human_real_card_testing_allowed": False,
        "human_real_card_automation_allowed": False,
        "stored_card_data_allowed": False,
        "public_evidence_path_count": 0,
        "private_ref_path_count": 0,
        "ready_for_a2_payment_policy_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "payment_provider_policy_context": False,
            "can_support_payment_abuse_cases": False,
            "live_payment_requires_human_operator": False,
            "must_not_mark_c3_from_payment_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as payment provider policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_billing_replay_evidence(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "billing_evidence_schema_version": "",
        "tenant_id": "",
        "project_id": "",
        "provider": "",
        "mode": "",
        "ledger_event_count": 0,
        "provider_event_count": 0,
        "usage_units": 0,
        "totals_by_currency_minor": {},
        "totals_currencies": [],
        "billing_snapshot_sha256_present": False,
        "accepted_ingest_status": "",
        "duplicate_ingest_status": "",
        "accepted_ledger_mutation_count": 0,
        "duplicate_ledger_mutation_count": 0,
        "duplicate_idempotency_proven": False,
        "raw_payload_included": False,
        "secret_value_present": False,
        "raw_secret_present": False,
        "public_safe": False,
        "ready_for_a2_evidence_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "billing_usage_policy_context": False,
            "can_support_cost_policy_calibration": False,
            "should_add_billing_abuse_cases": False,
            "must_not_mark_c3_from_billing_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as billing usage and idempotency policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_billing_ledger_migration(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "version": 0,
        "migration": "",
        "table_count": 0,
        "table_names": [],
        "tenant_rls_table_count": 0,
        "tenant_rls_ready": False,
        "required_index_count": 0,
        "required_constraint_count": 0,
        "constraint_names": [],
        "provider_event_type_count": 0,
        "ledger_event_type_count": 0,
        "providers": [],
        "modes": [],
        "currencies": [],
        "required_function_names": [],
        "public_safe": False,
        "raw_provider_payload_stored": False,
        "raw_provider_secret_stored": False,
        "raw_card_data_stored": False,
        "provider_calls_executed": False,
        "ready_for_a2_evidence_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "sql_billing_policy_context": False,
            "can_support_billing_abuse_cases": False,
            "can_cross_check_usage_rollups": False,
            "must_not_mark_c3_from_billing_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as billing ledger SQL policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_china_payment_migration(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "version": 0,
        "migration": "",
        "currency": "",
        "provider_count": 0,
        "providers": [],
        "table_count": 0,
        "table_names": [],
        "mutable_audited_table_count": 0,
        "mutable_audited_tables": [],
        "append_only_table_count": 0,
        "append_only_tables": [],
        "tenant_rls_table_count": 0,
        "tenant_rls_ready": False,
        "required_constraint_count": 0,
        "required_index_count": 0,
        "required_function_names": [],
        "public_safe": False,
        "raw_provider_payload_stored": False,
        "raw_provider_headers_stored": False,
        "raw_provider_secrets_stored": False,
        "raw_card_data_stored": False,
        "pan_stored": False,
        "cvc_stored": False,
        "otp_stored": False,
        "merchant_credentials_reference_only": False,
        "notification_hash_only": False,
        "bill_file_object_reference_only": False,
        "mutation_evidence_hash_only": False,
        "idempotency_keys": [],
        "billing_ledger_providers": [],
        "has_money_flow_tables": False,
        "has_fail_closed_functions": False,
        "ready_for_a2_payment_sql_policy_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "china_payment_sql_policy_context": False,
            "can_support_payment_abuse_cases": False,
            "can_support_payment_reconciliation_regressions": False,
            "can_cross_check_billing_ledger_links": False,
            "must_not_mark_c3_from_payment_sql_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as payment SQL policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_payment_verification_security(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "migration": path.name,
        "public_safe": False,
        "recursive_metadata_check": False,
        "forbidden_alias_count": 0,
        "has_card_data_aliases": False,
        "has_secret_material_aliases": False,
        "verification_artifact_table_present": False,
        "verification_artifact_digest_fields": False,
        "verification_artifact_freshness_window": False,
        "verification_artifact_append_only": False,
        "notification_requires_verified_artifact": False,
        "status_transition_requires_artifact": False,
        "trusted_apply_functions_present": False,
        "project_rls_ready": False,
        "role_nobypassrls_assertion": False,
        "metadata_constraints_present": False,
        "raw_payload_storage_allowed": False,
        "secret_value_storage_allowed": False,
        "ready_for_a2_payment_verification_policy_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "payment_verification_policy_context": False,
            "can_support_forbidden_payment_data_abuse_cases": False,
            "can_support_fail_closed_payment_transition_regressions": False,
            "can_cross_check_verified_notification_artifacts": False,
            "must_not_mark_c3_from_payment_verification_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as payment verification policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_oauth_lifecycle_security(
    sql_path: Path,
    evidence_path: Path,
    reason: str,
) -> dict[str, Any]:
    return {
        "available": False,
        "sql_path": sql_path.as_posix(),
        "evidence_path": evidence_path.as_posix(),
        "schema_version": "",
        "provider": "",
        "environment": "",
        "public_safe": False,
        "sql_table_count": 0,
        "sql_tables": [],
        "digest_field_count": 0,
        "recursive_metadata_check": False,
        "forbidden_key_count": 0,
        "reference_only_secret_storage": False,
        "state_code_replay_controls": False,
        "account_takeover_controls": False,
        "session_fixation_controls": False,
        "revocation_controls": False,
        "audit_outbox_controls": False,
        "hard_delete_rejected": False,
        "append_only_audit": False,
        "tenant_rls_ready": False,
        "raw_secret_columns_present": False,
        "raw_public_evidence_present": False,
        "successful_localhost_connection": False,
        "scope_boundary_ready": False,
        "token_reference_present": False,
        "token_reference_exposed": False,
        "memory_backed": False,
        "production_ready": False,
        "ready_for_a2_oauth_policy_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "oauth_lifecycle_policy_context": False,
            "can_support_oauth_abuse_cases": False,
            "can_support_account_takeover_regressions": False,
            "can_cross_check_audit_outbox_events": False,
            "must_not_mark_c3_from_oauth_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as OAuth lifecycle policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_unified_identity_security(
    runtime_sql_path: Path,
    identity_sql_path: Path,
    coordinator_sql_path: Path,
    revocation_outbox_sql_path: Path,
    session_authentication_sql_path: Path,
    identity_verification_sql_path: Path,
    identity_verification_public_surface_path: Path,
    contract_path: Path,
    same_account_evidence_path: Path,
    google_evidence_path: Path,
    reason: str,
) -> dict[str, Any]:
    return {
        "available": False,
        "runtime_sql_path": runtime_sql_path.as_posix(),
        "identity_sql_path": identity_sql_path.as_posix(),
        "coordinator_sql_path": coordinator_sql_path.as_posix(),
        "revocation_outbox_sql_path": revocation_outbox_sql_path.as_posix(),
        "session_authentication_sql_path": session_authentication_sql_path.as_posix(),
        "identity_verification_sql_path": identity_verification_sql_path.as_posix(),
        "identity_verification_public_surface_path": identity_verification_public_surface_path.as_posix(),
        "contract_path": contract_path.as_posix(),
        "same_account_evidence_path": same_account_evidence_path.as_posix(),
        "google_evidence_path": google_evidence_path.as_posix(),
        "schema_version": "",
        "same_account_schema_version": "",
        "google_schema_version": "",
        "public_safe": False,
        "required_identity_kinds": [],
        "real_provider_calibrated": [],
        "pending_provider_count": 0,
        "identity_table_count": 0,
        "identity_tables": [],
        "oauth_runtime_table_count": 0,
        "oauth_runtime_tables": [],
        "coordinator_table_present": False,
        "digest_only_identity_storage": False,
        "reference_only_secret_storage": False,
        "recursive_metadata_check": False,
        "tenant_principal_rls_ready": False,
        "domain_invariants_ready": False,
        "postgres_contract_ready": False,
        "account_takeover_controls": False,
        "same_account_provider_link_ready": False,
        "membership_identity_decoupled": False,
        "public_dto_allowlist_only": False,
        "secret_material_excluded": False,
        "google_real_provider_ready": False,
        "outbox_audit_controls": False,
        "recovery_merge_controls_present": False,
        "revocation_outbox_hardening_present": False,
        "revocation_external_checkpoints": False,
        "revocation_fenced_retry_ready": False,
        "revocation_reconnect_cleanup_safe": False,
        "session_authentication_ready": False,
        "identity_verification_surface_schema_version": "",
        "identity_verification_route_count": 0,
        "identity_verification_digest_only": False,
        "identity_verification_abuse_controls": False,
        "identity_verification_receipt_controls": False,
        "identity_verification_runtime_boundary": False,
        "identity_verification_public_surface_ready": False,
        "identity_verification_ready": False,
        "append_only_controls": False,
        "hard_delete_rejected": False,
        "final_credential_unlink_rejected": False,
        "raw_secret_columns_present": False,
        "multi_instance_gap_present": False,
        "production_ready": False,
        "ready_for_a2_identity_policy_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "identity_policy_context": False,
            "can_support_account_takeover_regressions": False,
            "can_support_membership_decoupling_regressions": False,
            "can_support_provider_linking_abuse_cases": False,
            "must_not_mark_c3_from_identity_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as unified identity policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_billing_sql_semantic_contract(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "migration": "",
        "public_safe": False,
        "durable_policy": "",
        "provider_config_column_present": False,
        "provider_config_object_persisted": False,
        "hash_columns": [],
        "reference_only_field_count": 0,
        "forbidden_durable_columns": [],
        "forbidden_public_marker_count": 0,
        "replay_statuses": [],
        "accepted_ledger_mutation_count": 0,
        "duplicate_ledger_mutation_count": 0,
        "conflict_ledger_mutation_count": 0,
        "raw_payload_included": False,
        "secret_value_present": False,
        "match_key": [],
        "billing_sql_edge_count": 0,
        "go_postgres_hash_only_object_count": 0,
        "raw_payload_column_present_count": 0,
        "public_snapshot_fields": [],
        "pytest_targets": [],
        "schema_path": "",
        "ready_for_a2_sql_policy_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "sql_semantic_policy_context": False,
            "can_support_replay_regression_cases": False,
            "can_support_hash_only_artifact_audit": False,
            "must_not_mark_c3_from_sql_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as SQL semantic policy context, not as C3 server-side grading evidence.",
        ],
    }


def _missing_object_storage_contract(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "public_safe": False,
        "backend_count": 0,
        "supported_backends": [],
        "scoped_object_keys": False,
        "manifest_field_count": 0,
        "manifest_fields": [],
        "manifest_signature_sha256": False,
        "checksum_readback": False,
        "local_readback_sha256": False,
        "s3_reference_only": False,
        "lazy_network_adapter": False,
        "sdk_helper_present": False,
        "api_integration_present": False,
        "evidence_bundle_metadata_present": False,
        "raw_payload_bytes_included": False,
        "absolute_local_paths_included": False,
        "raw_endpoint_values_included": False,
        "raw_access_key_values_included": False,
        "raw_secret_key_values_included": False,
        "raw_token_values_included": False,
        "test_target_count": 0,
        "test_targets": [],
        "ready_for_a2_artifact_policy_context": False,
        "c3_grading_ready": False,
        "a2_policy_implications": {
            "object_storage_policy_context": False,
            "can_support_artifact_bundle_evidence_handoff": False,
            "can_support_checksum_regression_cases": False,
            "must_not_mark_c3_from_storage_context": True,
        },
        "notes": [
            reason,
            "When present, A2 uses it as artifact storage policy context, not as C3 server-side grading evidence.",
        ],
    }


def _official_manifest_public_safe(public_safety: dict[str, Any]) -> bool:
    return (
        public_safety.get("raw_key_material_present") is False
        and public_safety.get("header_values_included") is False
        and public_safety.get("raw_payload_values_included") is False
        and public_safety.get("private_payload_contents_present") is False
        and public_safety.get("request_parameter_values_included") is False
        and public_safety.get("step_record_locations_included") is False
        and public_safety.get("redacted_summary_fields_only") is True
    )


def _api_probe_gate_validation_summary(
    plan_batch_records: list[dict[str, Any]],
    validate_gate_records: list[dict[str, Any]],
) -> dict[str, Any]:
    validation_status_counts = _count_records(validate_gate_records, "status")
    plan_status_counts = _count_records(plan_batch_records, "status")
    ok_count = int(validation_status_counts.get("ok", 0))
    error_count = int(validation_status_counts.get("error", 0))
    blocked_plan_count = int(plan_status_counts.get("blocked", 0))
    return {
        "available": bool(plan_batch_records or validate_gate_records),
        "schema_ref": "docs/a1/schemas/api_probe_quota_gate.schema.json",
        "plan_batch_count": len(plan_batch_records),
        "validate_gate_count": len(validate_gate_records),
        "plan_batch_status_counts": plan_status_counts,
        "validate_gate_status_counts": validation_status_counts,
        "ok_validate_gate_count": ok_count,
        "error_validate_gate_count": error_count,
        "blocked_plan_batch_count": blocked_plan_count,
        "private_record_refs": sorted(
            str(record.get("path"))
            for record in (*plan_batch_records, *validate_gate_records)
            if record.get("path")
        ),
        "release_interpretation": _api_probe_gate_interpretation(ok_count, error_count, blocked_plan_count),
    }


def _api_probe_gate_interpretation(ok_count: int, error_count: int, blocked_plan_count: int) -> str:
    if ok_count and not error_count and not blocked_plan_count:
        return "target_bound_gate_evidence_available"
    if ok_count and (error_count or blocked_plan_count):
        return "mixed_gate_evidence_review_required"
    if error_count or blocked_plan_count:
        return "gate_validation_or_plan_blocked"
    return "not_indexed"


def _count_records(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(key)
        if value is None:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _strict_nonnegative_count(
    value: Any,
    *,
    fallback: int = 0,
) -> tuple[int, bool]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return fallback, False
    return value, True


def _validated_nonnegative_counts(
    source: dict[str, Any],
    defaults: dict[str, int],
) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    invalid_fields: list[str] = []
    for field, fallback in defaults.items():
        value = source[field] if field in source else fallback
        count, valid = _strict_nonnegative_count(value, fallback=fallback)
        counts[field] = count
        if not valid:
            invalid_fields.append(field)
    return counts, sorted(invalid_fields)


def _nonnegative_count(value: Any, *, fallback: int = 0) -> int:
    count, valid = _strict_nonnegative_count(value, fallback=fallback)
    return count if valid else fallback


def _currency_minor_totals(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(currency).lower(): _int_value(amount)
        for currency, amount in value.items()
        if str(currency).strip()
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value if str(item).strip())


def _contains_true_flag(value: Any, flag_names: set[str]) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) in flag_names and nested is True:
                return True
            if _contains_true_flag(nested, flag_names):
                return True
    elif isinstance(value, list):
        return any(_contains_true_flag(item, flag_names) for item in value)
    return False


def _quota_gate_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    quota_keys = sorted(
        {
            str(key)
            for record in records
            if isinstance(record.get("quota"), dict)
            for key in record["quota"].get("quota_keys", [])
        }
    )
    functions = sorted({str(record.get("function")) for record in records if record.get("function")})
    paths = sorted(str(record.get("path")) for record in records if record.get("path"))
    return {
        "blocked": bool(records),
        "blocked_count": len(records),
        "blocked_functions": functions,
        "create_request_blocked": "create_request" in functions,
        "quota_keys": quota_keys,
        "private_record_refs": paths,
        "public_action": (
            "Increase or reset hosted request quota before additional mutating create_request calibration."
            if "create_request" in functions
            else "No mutating request quota gate is currently visible in public-safe evidence."
        ),
    }


def _official_sdk_smoke_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {
            "available": False,
            "path": target.as_posix(),
            "read_only_reachable": False,
            "reason": "A2 official SDK smoke summary is not available yet.",
        }

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "available": False,
            "path": target.as_posix(),
            "read_only_reachable": False,
            "reason": "A2 official SDK smoke summary is not a JSON object.",
        }

    calls = [call for call in payload.get("calls", []) if isinstance(call, dict)]
    ok_count = sum(1 for call in calls if call.get("status") == "ok")
    api_call_count, api_call_count_valid = _strict_nonnegative_count(
        payload.get("api_call_count", len(calls)),
        fallback=len(calls),
    )
    all_required_calls_raw = payload.get("all_required_calls_reached")
    all_required_calls_reached = all_required_calls_raw is True
    required_call_names = {
        "init",
        "health_check",
        "list_datasets",
        "list_runs",
        "list_requests",
        "list_agents",
    }
    call_names = sorted(str(call.get("name")) for call in calls if call.get("name"))
    complete_call_set = len(calls) == len(required_call_names) and set(call_names) == required_call_names
    invalid_boolean_fields = (
        []
        if isinstance(all_required_calls_raw, bool)
        else ["all_required_calls_reached"]
    )
    invalid_count_fields = (
        []
        if api_call_count_valid and api_call_count == len(calls)
        else ["api_call_count"]
    )
    summary = {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "generated_at": str(payload.get("generated_at", "")),
        "sdk_source": str(payload.get("sdk_source", "")),
        "base_url": str(payload.get("base_url", "")),
        "api_call_count": api_call_count,
        "ok_call_count": ok_count,
        "error_call_count": sum(1 for call in calls if call.get("status") != "ok"),
        "call_status_counts": _count_records(calls, "status"),
        "call_names": call_names,
        "all_required_calls_reached": all_required_calls_reached,
        "read_only_reachable": (
            not invalid_boolean_fields
            and not invalid_count_fields
            and complete_call_set
            and ok_count == len(calls)
            and all_required_calls_reached
        ),
        "notes": [
            "This is a redacted official releasefoundry SDK smoke summary, separate from clone API calibration.",
            "It proves current authenticated read/list reachability but does not count as C3 server-side grading evidence.",
        ],
    }
    if invalid_boolean_fields:
        summary["invalid_boolean_fields"] = invalid_boolean_fields
    if invalid_count_fields:
        summary["invalid_count_fields"] = invalid_count_fields
    return summary




def _artifact_receipt_projection(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, list):
        return [], ["artifact_receipts"]

    allowed_keys = {
        "modality",
        "verification_status",
        "sha256",
        "byte_size",
        "response_mime",
    }
    allowed_modalities = {"image", "audio", "video", "file"}
    allowed_statuses = {
        "verified",
        "download_failed",
        "invalid_url",
        "invalid_redirect",
        "size_limit_exceeded",
        "empty_body",
    }
    receipts: list[dict[str, Any]] = []
    invalid_fields: list[str] = []
    for index, receipt in enumerate(value):
        prefix = f"artifact_receipts[{index}]"
        if not isinstance(receipt, dict):
            invalid_fields.append(prefix)
            continue
        for key in sorted(set(receipt) - allowed_keys):
            invalid_fields.append(f"{prefix}.{key}")

        modality = receipt.get("modality")
        verification_status = receipt.get("verification_status")
        sha256 = receipt.get("sha256")
        byte_size, byte_size_valid = _strict_nonnegative_count(
            receipt.get("byte_size"),
            fallback=0,
        )
        response_mime = receipt.get("response_mime")
        if modality not in allowed_modalities:
            invalid_fields.append(f"{prefix}.modality")
        if verification_status not in allowed_statuses:
            invalid_fields.append(f"{prefix}.verification_status")
        if not isinstance(sha256, str) or not re.fullmatch(r"(?:|[0-9a-f]{64})", sha256):
            invalid_fields.append(f"{prefix}.sha256")
            sha256 = ""
        if not byte_size_valid:
            invalid_fields.append(f"{prefix}.byte_size")
        if not isinstance(response_mime, str):
            invalid_fields.append(f"{prefix}.response_mime")
            response_mime = ""
        if verification_status == "verified" and (
            not sha256 or byte_size <= 0
        ):
            invalid_fields.append(f"{prefix}.verified_payload")

        receipts.append(
            {
                "modality": str(modality) if modality in allowed_modalities else "",
                "verification_status": (
                    str(verification_status)
                    if verification_status in allowed_statuses
                    else ""
                ),
                "sha256": sha256,
                "byte_size": byte_size,
                "response_mime": response_mime,
            }
        )
    return receipts, sorted(set(invalid_fields))


def _empty_multimodal_real_api_smoke_summary(
    path: str | Path,
    reason: str,
) -> dict[str, Any]:
    return {
        "available": False,
        "path": Path(path).as_posix(),
        "schema_version": "",
        "request_content_sha256": "",
        "requested_modalities": [],
        "required_modalities": [],
        "excluded_modalities": [],
        "request_config_accepted_modalities": [],
        "observed_artifact_modalities": [],
        "accepted_modalities": [],
        "modality_evidence": {},
        "generation_options": {},
        "artifact_origin": "",
        "artifact_receipt_status": "",
        "artifact_reference_count": 0,
        "artifact_download_attempt_count": 0,
        "artifact_download_verified_count": 0,
        "artifact_reference_modalities": [],
        "artifact_verified_modalities": [],
        "artifact_missing_modalities": [],
        "artifact_modality_coverage_complete": False,
        "artifact_receipts": [],
        "artifact_receipts_public_safe": False,
        "request_status": "",
        "api_call_count": 0,
        "ok_call_count": 0,
        "error_call_count": 0,
        "call_status_counts": {},
        "call_names": [],
        "quota_blocked": False,
        "real_api_boundary_reached": False,
        "all_required_modalities_requested": False,
        "create_request_reached": False,
        "request_reused": False,
        "wait_completed": False,
        "dataset_id_present": False,
        "dataset_request_binding_verified": False,
        "native_media_uploaded": False,
        "media_upload_api_observed": False,
        "public_safe": False,
        "c3_grading_ready": False,
        "reason": reason,
    }


def _multimodal_real_api_smoke_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _empty_multimodal_real_api_smoke_summary(
            target,
            "A2 multimodal real API smoke summary is not available yet.",
        )

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _empty_multimodal_real_api_smoke_summary(
            target,
            "A2 multimodal real API smoke summary is not valid UTF-8 JSON.",
        )
    if not isinstance(payload, dict):
        return _empty_multimodal_real_api_smoke_summary(
            target,
            "A2 multimodal real API smoke summary is not a JSON object.",
        )

    calls = [call for call in payload.get("calls", []) if isinstance(call, dict)]
    ok_count = sum(1 for call in calls if call.get("status") == "ok")
    create_call = next((call for call in calls if call.get("name") == "create_request"), {})
    create_error_message = str(create_call.get("error_message", "")) if isinstance(create_call, dict) else ""
    quota_blocked = "usage limit exceeded" in create_error_message.lower() or "quota" in create_error_message.lower()
    requested_modalities = _string_list(payload.get("requested_modalities"))
    required_modalities = _string_list(payload.get("required_modalities"))
    if not required_modalities:
        required_modalities = ["text", "image", "audio", "file", "video"]
    excluded_modalities = _string_list(payload.get("excluded_modalities"))
    request_config_accepted_modalities = _string_list(payload.get("request_config_accepted_modalities"))
    observed_artifact_modalities = _string_list(payload.get("observed_artifact_modalities"))
    accepted_modalities = _string_list(payload.get("accepted_modalities"))
    modality_evidence = payload.get("modality_evidence") if isinstance(payload.get("modality_evidence"), dict) else {}
    required_modality_set = set(required_modalities)
    generation_option_by_modality = {
        "image": "generate_images",
        "audio": "generate_audio",
        "file": "generate_files",
        "video": "generate_videos",
    }
    generation_options = payload.get("generation_options") if isinstance(payload.get("generation_options"), dict) else {}
    request_status = str(payload.get("request_status", ""))
    request_content_sha256 = payload.get("request_content_sha256")
    invalid_digest_fields = []
    if not isinstance(request_content_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}",
        request_content_sha256,
    ):
        request_content_sha256 = ""
        invalid_digest_fields.append("request_content_sha256")
    artifact_receipts, invalid_artifact_receipt_fields = _artifact_receipt_projection(
        payload.get("artifact_receipts", [])
    )
    modality_order = ("image", "audio", "file", "video")
    required_media_modalities = sorted(
        {
            modality
            for modality in required_modality_set
            if modality in modality_order
        },
        key=modality_order.index,
    )
    artifact_reference_modalities = sorted(
        {
            receipt["modality"]
            for receipt in artifact_receipts
            if receipt["modality"]
        },
        key=modality_order.index,
    )
    artifact_verified_modalities = sorted(
        {
            receipt["modality"]
            for receipt in artifact_receipts
            if receipt["verification_status"] == "verified"
            and receipt["modality"]
        },
        key=modality_order.index,
    )
    artifact_missing_modalities = [
        modality
        for modality in required_media_modalities
        if modality not in set(artifact_verified_modalities)
    ]
    artifact_modality_coverage_complete = bool(
        required_media_modalities and not artifact_missing_modalities
    )
    all_generation_options_enabled = all(
        generation_options.get(generation_option_by_modality[modality]) is True
        for modality in required_modality_set - {"text"}
        if modality in generation_option_by_modality
    )
    all_modalities_requested = set(requested_modalities) >= required_modality_set and all_generation_options_enabled
    counts, invalid_count_fields = _validated_nonnegative_counts(
        payload,
        {
            "api_call_count": len(calls),
            "artifact_reference_count": 0,
            "artifact_download_attempt_count": 0,
            "artifact_download_verified_count": 0,
        },
    )
    boolean_inputs = {
        "all_required_modalities_requested": payload.get("all_required_modalities_requested"),
        "create_request_reached": payload.get("create_request_reached"),
        "request_reused": payload.get("request_reused", False),
        "wait_completed": payload.get("wait_completed"),
        "dataset_id_present": payload.get("dataset_id_present"),
        "dataset_request_binding_verified": payload.get(
            "dataset_request_binding_verified"
        ),
        "native_media_uploaded": payload.get("native_media_uploaded"),
        "media_upload_api_observed": payload.get("media_upload_api_observed"),
        "c3_grading_ready": payload.get("c3_grading_ready"),
        "artifact_receipts_public_safe": payload.get(
            "artifact_receipts_public_safe"
        ),
        "artifact_modality_coverage_complete": payload.get(
            "artifact_modality_coverage_complete"
        ),
        "public_safe": payload.get("public_safe"),
    }
    invalid_boolean_fields = sorted(
        field
        for field, value in boolean_inputs.items()
        if not isinstance(value, bool)
    )
    api_call_count = counts["api_call_count"]
    artifact_reference_count = counts["artifact_reference_count"]
    artifact_download_attempt_count = counts["artifact_download_attempt_count"]
    artifact_download_verified_count = counts["artifact_download_verified_count"]
    if api_call_count != len(calls):
        invalid_count_fields.append("api_call_count")
    if artifact_download_attempt_count != len(artifact_receipts):
        invalid_count_fields.append("artifact_download_attempt_count")
    if artifact_download_verified_count != sum(
        receipt["verification_status"] == "verified"
        for receipt in artifact_receipts
    ):
        invalid_count_fields.append("artifact_download_verified_count")
    if not (
        artifact_download_verified_count
        <= artifact_download_attempt_count
        <= artifact_reference_count
    ):
        invalid_count_fields.extend(
            [
                "artifact_reference_count",
                "artifact_download_attempt_count",
                "artifact_download_verified_count",
            ]
        )
    invalid_count_fields = sorted(set(invalid_count_fields))
    if (
        artifact_download_verified_count
        == artifact_download_attempt_count
        == artifact_reference_count
        and artifact_reference_count > 0
        and artifact_modality_coverage_complete
    ):
        artifact_receipt_status = "verified"
    elif artifact_download_verified_count > 0:
        artifact_receipt_status = "partial"
    elif artifact_download_attempt_count > 0:
        artifact_receipt_status = "failed"
    else:
        artifact_receipt_status = str(
            payload.get("artifact_receipt_status", "")
        )
    create_request_reached = boolean_inputs["create_request_reached"] is True
    request_reused = boolean_inputs["request_reused"] is True
    real_api_boundary_reached = create_request_reached or request_reused or quota_blocked
    all_required_modalities_confirmed = (
        boolean_inputs["all_required_modalities_requested"] is True
        and all_modalities_requested
    )
    artifact_receipts_public_safe = bool(
        boolean_inputs["artifact_receipts_public_safe"] is True
        and not invalid_artifact_receipt_fields
    )
    public_safe = bool(
        boolean_inputs["public_safe"] is True
        and artifact_receipts_public_safe
    )
    invalid_semantic_fields = []
    for field in (
        "native_media_uploaded",
        "media_upload_api_observed",
        "c3_grading_ready",
    ):
        if boolean_inputs[field] is not False:
            invalid_semantic_fields.append(field)
    reported_artifact_fields = {
        "artifact_receipt_status": payload.get("artifact_receipt_status"),
        "artifact_reference_modalities": _string_list(
            payload.get("artifact_reference_modalities")
        ),
        "artifact_verified_modalities": _string_list(
            payload.get("artifact_verified_modalities")
        ),
        "artifact_missing_modalities": _string_list(
            payload.get("artifact_missing_modalities")
        ),
        "artifact_modality_coverage_complete": payload.get(
            "artifact_modality_coverage_complete"
        ),
    }
    recomputed_artifact_fields = {
        "artifact_receipt_status": artifact_receipt_status,
        "artifact_reference_modalities": artifact_reference_modalities,
        "artifact_verified_modalities": artifact_verified_modalities,
        "artifact_missing_modalities": artifact_missing_modalities,
        "artifact_modality_coverage_complete": (
            artifact_modality_coverage_complete
        ),
    }
    for field, recomputed_value in recomputed_artifact_fields.items():
        if reported_artifact_fields[field] != recomputed_value:
            invalid_semantic_fields.append(field)
    invalid_semantic_fields = sorted(set(invalid_semantic_fields))
    summary = {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "request_content_sha256": request_content_sha256,
        "generated_at": str(payload.get("generated_at", "")),
        "sdk_source": str(payload.get("sdk_source", "")),
        "base_url": str(payload.get("base_url", "")),
        "private_ref": str(payload.get("private_ref", "")),
        "private_ref_sha256_12": str(payload.get("private_ref_sha256_12", "")),
        "requested_modalities": requested_modalities,
        "required_modalities": required_modalities,
        "excluded_modalities": excluded_modalities,
        "request_config_accepted_modalities": request_config_accepted_modalities,
        "observed_artifact_modalities": observed_artifact_modalities,
        "accepted_modalities": accepted_modalities,
        "modality_evidence": modality_evidence,
        "generation_options": generation_options,
        "artifact_origin": str(payload.get("artifact_origin", "")),
        "artifact_receipt_status": artifact_receipt_status,
        "artifact_reference_count": artifact_reference_count,
        "artifact_download_attempt_count": artifact_download_attempt_count,
        "artifact_download_verified_count": artifact_download_verified_count,
        "artifact_reference_modalities": artifact_reference_modalities,
        "artifact_verified_modalities": artifact_verified_modalities,
        "artifact_missing_modalities": artifact_missing_modalities,
        "artifact_modality_coverage_complete": (
            artifact_modality_coverage_complete
        ),
        "artifact_receipts": artifact_receipts,
        "artifact_receipts_public_safe": artifact_receipts_public_safe,
        "request_status": request_status,
        "api_call_count": api_call_count,
        "ok_call_count": ok_count,
        "error_call_count": sum(1 for call in calls if call.get("status") != "ok"),
        "call_status_counts": _count_records(calls, "status"),
        "call_names": sorted(str(call.get("name")) for call in calls if call.get("name")),
        "quota_blocked": quota_blocked,
        "create_request_error_type": str(create_call.get("error_type", "")) if isinstance(create_call, dict) else "",
        "create_request_error_message": create_error_message,
        "real_api_boundary_reached": real_api_boundary_reached,
        "all_required_modalities_requested": all_required_modalities_confirmed,
        "create_request_reached": create_request_reached,
        "request_reused": request_reused,
        "wait_completed": boolean_inputs["wait_completed"] is True,
        "dataset_id_present": boolean_inputs["dataset_id_present"] is True,
        "dataset_request_binding_verified": (
            boolean_inputs["dataset_request_binding_verified"] is True
        ),
        "native_media_uploaded": False,
        "media_upload_api_observed": False,
        "public_safe": public_safe,
        "ready_for_a2_multimodal_context": (
            not invalid_boolean_fields
            and not invalid_count_fields
            and not invalid_digest_fields
            and not invalid_semantic_fields
            and public_safe
            and all_required_modalities_confirmed
            and real_api_boundary_reached
            and set(accepted_modalities) >= required_modality_set
        ),
        "c3_grading_ready": False,
        "notes": [
            "This is a redacted real ReleaseFoundry API smoke summary for the explicitly requested ReleaseFoundry-generated modalities.",
            "The request status is copied from the terminal request detail when available; failure is not treated as quota evidence or grading success.",
            "A reused request is selected only by its exact content-bound request name; generated artifacts do not prove caller media upload support.",
            "Artifact receipts contain only modality, status, SHA-256, byte count, and response MIME; links, object keys, paths, and bytes are not projected.",
            "Artifact modality coverage and receipt status are rebuilt from requested modalities and verified public receipts; contradictory claims fail closed.",
            "It is not reviewed ReleaseFoundry grading evidence and does not mark C3 ready.",
        ],
    }
    if invalid_boolean_fields:
        summary["invalid_boolean_fields"] = invalid_boolean_fields
    if invalid_count_fields:
        summary["invalid_count_fields"] = invalid_count_fields
    if invalid_artifact_receipt_fields:
        summary["invalid_artifact_receipt_fields"] = (
            invalid_artifact_receipt_fields
        )
    if invalid_digest_fields:
        summary["invalid_digest_fields"] = invalid_digest_fields
    if invalid_semantic_fields:
        summary["invalid_semantic_fields"] = invalid_semantic_fields
    return summary


def _public_multimodal_probe_path(path: str | Path) -> str:
    target = Path(path)
    if target.is_absolute():
        return ""
    posix_path = target.as_posix()
    if (
        target.suffix.lower() != ".json"
        or len(target.parts) < 3
        or target.parts[0:2] != ("docs", "evidence")
        or ".." in target.parts
        or "?" in posix_path
        or "#" in posix_path
        or ":" in posix_path
    ):
        return ""
    return posix_path


def _canonical_sha256(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    return ""


def _unexpected_record_fields(
    record: dict[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    prefix: str,
) -> list[str]:
    return sorted(
        [
            *(f"{prefix}.{field}" for field in required - set(record)),
            *(f"{prefix}.{field}" for field in set(record) - allowed),
        ]
    )


def _sensitive_native_surface_fields(value: Any, *, prefix: str = "payload") -> list[str]:
    sensitive_keys = {
        "apikey",
        "authorization",
        "bearertoken",
        "password",
        "secret",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
        "signedurl",
    }
    findings = []
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            field_path = f"{prefix}.{key}"
            if normalized_key in sensitive_keys:
                findings.append(field_path)
            findings.extend(
                _sensitive_native_surface_fields(nested, prefix=field_path)
            )
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(
                _sensitive_native_surface_fields(
                    nested,
                    prefix=f"{prefix}[{index}]",
                )
            )
    elif isinstance(value, str):
        if (
            re.search(r"(?i)\bbearer\s+[a-z0-9._~-]+", value)
            or re.search(r"https?://[^\s\"']+\?", value)
            or re.match(r"^[a-zA-Z]:[\\/]", value)
            or ("-----BEGIN " + "PRIVATE KEY-----") in value
        ):
            findings.append(prefix)
    return findings


def _empty_releasefoundry_native_media_surface_summary(
    path: str | Path,
    reason: str,
) -> dict[str, Any]:
    return {
        "available": False,
        "path": _public_multimodal_probe_path(path),
        "schema_version": "",
        "sdk_package_name": "",
        "sdk_version": "",
        "sdk_artifact_sha256": "",
        "static_audit_status": "",
        "expected_surface_matches": False,
        "surface_fingerprint_sha256": "",
        "live_session_requested": False,
        "live_session_attempted": False,
        "live_session_reached": False,
        "live_session_status": "",
        "live_session_api_call_count": 0,
        "mutation_attempt_count": 0,
        "generated_artifact_capabilities": {
            "image": "not_verified",
            "audio": "not_verified",
            "file": "not_verified",
            "video": "provider_unverified",
        },
        "generated_artifact_evidence_count": 0,
        "generated_artifact_evidence": [],
        "caller_native_submission": {
            "image": "sdk_surface_changed_review_required",
            "audio": "sdk_surface_changed_review_required",
            "file": "sdk_surface_changed_review_required",
            "video": "provider_unverified",
        },
        "upload_method_observed": False,
        "immutable_media_url_parameter_observed": False,
        "undocumented_endpoint_probed": False,
        "native_media_uploaded": False,
        "caller_native_input_support_proven": False,
        "surface_audit_verified": False,
        "public_safe": False,
        "c3_grading_ready": False,
        "invalid_fields": [],
        "reason": reason,
        "notes": [
            "No caller-native media capability may be inferred without a valid pinned SDK surface receipt.",
            "Video remains provider-unverified.",
        ],
    }


def _project_native_media_evidence(
    value: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, list):
        return [], ["generated_artifact_evidence"]

    modality_order = ("image", "audio", "file")
    projected = []
    invalid_fields = []
    for index, item in enumerate(value):
        prefix = f"generated_artifact_evidence[{index}]"
        if not isinstance(item, dict):
            invalid_fields.append(prefix)
            continue
        invalid_fields.extend(
            _unexpected_record_fields(
                item,
                required={"path", "sha256", "verified_modalities"},
                allowed={"path", "sha256", "verified_modalities"},
                prefix=prefix,
            )
        )
        path = _public_multimodal_probe_path(item.get("path", ""))
        digest = _canonical_sha256(item.get("sha256"))
        modalities = _string_list(item.get("verified_modalities"))
        if not path:
            invalid_fields.append(f"{prefix}.path")
        if not digest:
            invalid_fields.append(f"{prefix}.sha256")
        if (
            len(modalities) != len(set(modalities))
            or not set(modalities) <= set(modality_order)
        ):
            invalid_fields.append(f"{prefix}.verified_modalities")
            modalities = []
        else:
            modalities = sorted(modalities, key=modality_order.index)

        content_hash_verified = False
        if path and digest:
            target = Path(path)
            try:
                content_hash_verified = (
                    target.is_file()
                    and hashlib.sha256(target.read_bytes()).hexdigest() == digest
                )
            except OSError:
                content_hash_verified = False
        if not content_hash_verified:
            invalid_fields.append(f"{prefix}.content_hash")
        projected.append(
            {
                "path": path,
                "sha256": digest,
                "verified_modalities": modalities,
                "content_hash_verified": content_hash_verified,
            }
        )

    expected_paths = {
        DEFAULT_A2_MULTIMODAL_REAL_API_SMOKE.as_posix(),
        DEFAULT_A2_MULTIMODAL_AUDIO_REAL_API_SMOKE.as_posix(),
        DEFAULT_A2_MULTIMODAL_IMAGE_REAL_API_SMOKE.as_posix(),
        DEFAULT_A2_MULTIMODAL_FILE_REAL_API_SMOKE.as_posix(),
    }
    if len(projected) != len(expected_paths):
        invalid_fields.append("generated_artifact_evidence.count")
    if {item["path"] for item in projected} != expected_paths:
        invalid_fields.append("generated_artifact_evidence.paths")
    if len({item["path"] for item in projected if item["path"]}) != len(projected):
        invalid_fields.append("generated_artifact_evidence.path.not_unique")
    if len({item["sha256"] for item in projected if item["sha256"]}) != len(
        projected
    ):
        invalid_fields.append("generated_artifact_evidence.sha256.not_unique")
    verified_modalities = {
        modality
        for item in projected
        for modality in item["verified_modalities"]
        if item["content_hash_verified"]
    }
    if verified_modalities != set(modality_order):
        invalid_fields.append("generated_artifact_evidence.modality_coverage")
    return projected, sorted(set(invalid_fields))


def _releasefoundry_native_media_surface_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _empty_releasefoundry_native_media_surface_summary(
            target,
            "A2 ReleaseFoundry native-media SDK surface receipt is not available yet.",
        )
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _empty_releasefoundry_native_media_surface_summary(
            target,
            "A2 ReleaseFoundry native-media SDK surface receipt is not valid UTF-8 JSON.",
        )
    if not isinstance(payload, dict):
        return _empty_releasefoundry_native_media_surface_summary(
            target,
            "A2 ReleaseFoundry native-media SDK surface receipt is not a JSON object.",
        )

    expected_top_level = {
        "schema_version",
        "generated_at",
        "sdk",
        "static_audit",
        "live_session",
        "generated_artifact_capabilities",
        "generated_artifact_evidence",
        "caller_native_submission",
        "upload_method_observed",
        "immutable_media_url_parameter_observed",
        "undocumented_endpoint_probed",
        "mutation_attempt_count",
        "native_media_uploaded",
        "caller_native_input_support_proven",
        "c3_grading_ready",
        "public_safe",
        "notes",
    }
    invalid_fields = _unexpected_record_fields(
        payload,
        required=expected_top_level,
        allowed=expected_top_level,
        prefix="payload",
    )
    invalid_fields.extend(_sensitive_native_surface_fields(payload))

    sdk = payload.get("sdk") if isinstance(payload.get("sdk"), dict) else {}
    static_audit = (
        payload.get("static_audit")
        if isinstance(payload.get("static_audit"), dict)
        else {}
    )
    live_session = (
        payload.get("live_session")
        if isinstance(payload.get("live_session"), dict)
        else {}
    )
    generated_capabilities = (
        payload.get("generated_artifact_capabilities")
        if isinstance(payload.get("generated_artifact_capabilities"), dict)
        else {}
    )
    caller_submission = (
        payload.get("caller_native_submission")
        if isinstance(payload.get("caller_native_submission"), dict)
        else {}
    )

    invalid_fields.extend(
        _unexpected_record_fields(
            sdk,
            required={
                "package_name",
                "version",
                "artifact_path",
                "artifact_sha256",
                "source_file_sha256",
            },
            allowed={
                "package_name",
                "version",
                "artifact_path",
                "artifact_sha256",
                "source_file_sha256",
            },
            prefix="sdk",
        )
    )
    static_audit_fields = {
        "status",
        "expected_surface_matches",
        "surface_fingerprint_sha256",
        "public_client_methods",
        "upload_method_names_observed",
        "dataset_ingestion_method_names_observed",
        "immutable_media_url_parameters_observed",
        "generic_payload_parameters_observed",
        "accepted_inputs",
        "add_user_file",
        "eval_runner",
    }
    invalid_fields.extend(
        _unexpected_record_fields(
            static_audit,
            required=static_audit_fields,
            allowed=static_audit_fields,
            prefix="static_audit",
        )
    )
    invalid_fields.extend(
        _unexpected_record_fields(
            live_session,
            required={
                "requested",
                "attempted",
                "reached",
                "status",
                "api_call_count",
                "mutation_attempt_count",
            },
            allowed={
                "requested",
                "attempted",
                "reached",
                "status",
                "api_call_count",
                "mutation_attempt_count",
                "error_type",
            },
            prefix="live_session",
        )
    )
    for field, record in (
        ("generated_artifact_capabilities", generated_capabilities),
        ("caller_native_submission", caller_submission),
    ):
        invalid_fields.extend(
            _unexpected_record_fields(
                record,
                required={"image", "audio", "file", "video"},
                allowed={"image", "audio", "file", "video"},
                prefix=field,
            )
        )

    public_path = _public_multimodal_probe_path(target)
    schema_version = (
        payload.get("schema_version")
        if isinstance(payload.get("schema_version"), str)
        else ""
    )
    sdk_package_name = (
        sdk.get("package_name") if isinstance(sdk.get("package_name"), str) else ""
    )
    sdk_version = sdk.get("version") if isinstance(sdk.get("version"), str) else ""
    sdk_artifact_sha256 = _canonical_sha256(sdk.get("artifact_sha256"))
    static_audit_status = (
        static_audit.get("status")
        if static_audit.get("status") in {"completed", "review_required"}
        else ""
    )
    surface_fingerprint_sha256 = _canonical_sha256(
        static_audit.get("surface_fingerprint_sha256")
    )
    live_session_status = (
        live_session.get("status")
        if live_session.get("status") in {"not_requested", "ok", "error"}
        else ""
    )
    live_api_call_count, live_api_call_count_valid = _strict_nonnegative_count(
        live_session.get("api_call_count")
    )
    mutation_attempt_count, mutation_attempt_count_valid = _strict_nonnegative_count(
        payload.get("mutation_attempt_count")
    )
    live_mutation_attempt_count, live_mutation_attempt_count_valid = (
        _strict_nonnegative_count(live_session.get("mutation_attempt_count"))
    )
    if not public_path:
        invalid_fields.append("path")
    if schema_version != EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_SCHEMA_VERSION:
        invalid_fields.append("schema_version")
    if sdk_package_name != "releasefoundry":
        invalid_fields.append("sdk.package_name")
    if sdk_version != EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SDK_VERSION:
        invalid_fields.append("sdk.version")
    if sdk_artifact_sha256 != EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SDK_ARTIFACT_SHA256:
        invalid_fields.append("sdk.artifact_sha256")
    if static_audit_status != "completed":
        invalid_fields.append("static_audit.status")
    if static_audit.get("expected_surface_matches") is not True:
        invalid_fields.append("static_audit.expected_surface_matches")
    if (
        surface_fingerprint_sha256
        != EXPECTED_RELEASEFOUNDRY_NATIVE_MEDIA_SURFACE_FINGERPRINT_SHA256
    ):
        invalid_fields.append("static_audit.surface_fingerprint_sha256")
    for field in (
        "upload_method_names_observed",
        "dataset_ingestion_method_names_observed",
        "immutable_media_url_parameters_observed",
    ):
        if static_audit.get(field) != []:
            invalid_fields.append(f"static_audit.{field}")

    accepted_inputs = (
        static_audit.get("accepted_inputs")
        if isinstance(static_audit.get("accepted_inputs"), dict)
        else {}
    )
    add_user_file = (
        static_audit.get("add_user_file")
        if isinstance(static_audit.get("add_user_file"), dict)
        else {}
    )
    eval_runner = (
        static_audit.get("eval_runner")
        if isinstance(static_audit.get("eval_runner"), dict)
        else {}
    )
    static_contract_checks = {
        "static_audit.accepted_inputs": (
            accepted_inputs.get("observed") is True
            and accepted_inputs.get("classification")
            == "agent_capability_declaration_not_media_transport"
        ),
        "static_audit.add_user_file": (
            add_user_file.get("observed") is True
            and add_user_file.get("records_file_path") is True
            and add_user_file.get("file_io_calls_observed") == []
            and add_user_file.get("classification") == "metadata_only"
        ),
        "static_audit.eval_runner": (
            eval_runner.get("action_content_read") is True
            and eval_runner.get("agent_respond_receives_content") is True
            and eval_runner.get("native_file_action_call_observed") is False
            and eval_runner.get("classification") == "text_content_only_observed"
        ),
    }
    invalid_fields.extend(
        field for field, passed in static_contract_checks.items() if not passed
    )

    boolean_expectations = {
        "live_session.requested": (live_session.get("requested"), False),
        "live_session.attempted": (live_session.get("attempted"), False),
        "live_session.reached": (live_session.get("reached"), False),
        "upload_method_observed": (
            payload.get("upload_method_observed"),
            False,
        ),
        "immutable_media_url_parameter_observed": (
            payload.get("immutable_media_url_parameter_observed"),
            False,
        ),
        "undocumented_endpoint_probed": (
            payload.get("undocumented_endpoint_probed"),
            False,
        ),
        "native_media_uploaded": (payload.get("native_media_uploaded"), False),
        "caller_native_input_support_proven": (
            payload.get("caller_native_input_support_proven"),
            False,
        ),
        "c3_grading_ready": (payload.get("c3_grading_ready"), False),
        "public_safe": (payload.get("public_safe"), True),
    }
    for field, (actual, expected) in boolean_expectations.items():
        if not isinstance(actual, bool) or actual is not expected:
            invalid_fields.append(field)
    if live_session_status != "not_requested":
        invalid_fields.append("live_session.status")
    if not live_api_call_count_valid or live_api_call_count != 0:
        invalid_fields.append("live_session.api_call_count")
    if (
        not mutation_attempt_count_valid
        or mutation_attempt_count != 0
        or not live_mutation_attempt_count_valid
        or live_mutation_attempt_count != 0
    ):
        invalid_fields.append("mutation_attempt_count")

    expected_generated_capabilities = {
        "image": "verified",
        "audio": "verified",
        "file": "verified",
        "video": "provider_unverified",
    }
    expected_caller_submission = {
        "image": "provider_surface_missing",
        "audio": "provider_surface_missing",
        "file": "provider_surface_missing",
        "video": "provider_unverified",
    }
    if generated_capabilities != expected_generated_capabilities:
        invalid_fields.append("generated_artifact_capabilities")
    if caller_submission != expected_caller_submission:
        invalid_fields.append("caller_native_submission")

    generated_evidence, evidence_invalid_fields = (
        _project_native_media_evidence(
            payload.get("generated_artifact_evidence")
        )
    )
    invalid_fields.extend(evidence_invalid_fields)
    invalid_fields = sorted(set(invalid_fields))
    surface_audit_verified = not invalid_fields

    return {
        "available": True,
        "path": public_path,
        "schema_version": schema_version,
        "sdk_package_name": sdk_package_name,
        "sdk_version": sdk_version,
        "sdk_artifact_sha256": sdk_artifact_sha256,
        "static_audit_status": static_audit_status,
        "expected_surface_matches": (
            static_audit.get("expected_surface_matches") is True
        ),
        "surface_fingerprint_sha256": surface_fingerprint_sha256,
        "live_session_requested": live_session.get("requested") is True,
        "live_session_attempted": live_session.get("attempted") is True,
        "live_session_reached": live_session.get("reached") is True,
        "live_session_status": live_session_status,
        "live_session_api_call_count": (
            live_api_call_count if live_api_call_count_valid else 0
        ),
        "mutation_attempt_count": (
            mutation_attempt_count if mutation_attempt_count_valid else 0
        ),
        "generated_artifact_capabilities": (
            expected_generated_capabilities
            if surface_audit_verified
            else {
                "image": "not_verified",
                "audio": "not_verified",
                "file": "not_verified",
                "video": "provider_unverified",
            }
        ),
        "generated_artifact_evidence_count": (
            len(generated_evidence) if surface_audit_verified else 0
        ),
        "generated_artifact_evidence": (
            generated_evidence if surface_audit_verified else []
        ),
        "caller_native_submission": (
            expected_caller_submission
            if surface_audit_verified
            else {
                "image": "sdk_surface_changed_review_required",
                "audio": "sdk_surface_changed_review_required",
                "file": "sdk_surface_changed_review_required",
                "video": "provider_unverified",
            }
        ),
        "upload_method_observed": payload.get("upload_method_observed") is True,
        "immutable_media_url_parameter_observed": (
            payload.get("immutable_media_url_parameter_observed") is True
        ),
        "undocumented_endpoint_probed": (
            payload.get("undocumented_endpoint_probed") is True
        ),
        "native_media_uploaded": False,
        "caller_native_input_support_proven": False,
        "surface_audit_verified": surface_audit_verified,
        "public_safe": surface_audit_verified,
        "c3_grading_ready": False,
        "invalid_fields": invalid_fields,
        "notes": [
            "The pinned offline releasefoundry 0.3.1 compatibility surface is hash-verified when surface_audit_verified is true.",
            "No live API session is claimed by the static compatibility fixture.",
            "Image, audio, and file verification refers only to ReleaseFoundry-generated artifacts, not caller-native upload or grading.",
            "Video remains provider-unverified and cannot become verified through this receipt.",
            "Any SDK surface drift, mutation, upload signal, malformed field, or private material fails closed for manual review.",
        ],
    }


def _multimodal_generated_artifact_capabilities_summary(
    probes: list[tuple[str | Path, dict[str, Any]]],
    *,
    releasefoundry_native_media_surface: dict[str, Any],
) -> dict[str, Any]:
    expected_modalities = ("image", "audio", "file")
    projected_probes = []
    invalid_probe_fields = []

    for index, (path, summary) in enumerate(probes):
        prefix = f"probes[{index}]"
        expected_modality = (
            expected_modalities[index]
            if index < len(expected_modalities)
            else ""
        )
        public_path = _public_multimodal_probe_path(path)
        if not public_path:
            invalid_probe_fields.append(f"{prefix}.path")

        request_content_sha256 = summary.get("request_content_sha256")
        if not isinstance(request_content_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}",
            request_content_sha256,
        ):
            request_content_sha256 = ""
            invalid_probe_fields.append(
                f"{prefix}.request_content_sha256"
            )

        artifact_receipts, receipt_invalid_fields = _artifact_receipt_projection(
            summary.get("artifact_receipts", [])
        )
        invalid_probe_fields.extend(
            f"{prefix}.{field}" for field in receipt_invalid_fields
        )
        inherited_invalid_fields = sorted(
            field
            for key, value in summary.items()
            if key.startswith("invalid_") and isinstance(value, list)
            for field in value
        )
        invalid_probe_fields.extend(
            f"{prefix}.{field}" for field in inherited_invalid_fields
        )

        verified_modalities = sorted(
            {
                receipt["modality"]
                for receipt in artifact_receipts
                if receipt["verification_status"] == "verified"
                and receipt["modality"] in expected_modalities
            },
            key=expected_modalities.index,
        )
        unexpected_verified_modalities = sorted(
            {
                receipt["modality"]
                for receipt in artifact_receipts
                if receipt["verification_status"] == "verified"
                and receipt["modality"] not in expected_modalities
            }
        )
        if unexpected_verified_modalities:
            invalid_probe_fields.append(
                f"{prefix}.unexpected_verified_modalities"
            )

        validity_checks = {
            "available": summary.get("available") is True,
            "schema_version": (
                summary.get("schema_version")
                == "a2.multimodal_real_api_smoke.v1"
            ),
            "required_modality_binding": (
                len(summary.get("required_modalities", [])) == 2
                and set(summary.get("required_modalities", []))
                == {"text", expected_modality}
            ),
            "verified_modality_binding": (
                verified_modalities == [expected_modality]
            ),
            "public_safe": summary.get("public_safe") is True,
            "artifact_origin": (
                summary.get("artifact_origin")
                == "releasefoundry_generated_dataset"
            ),
            "artifact_receipt_status": (
                summary.get("artifact_receipt_status") == "verified"
            ),
            "request_status": summary.get("request_status") == "completed",
            "real_api_boundary_reached": (
                summary.get("real_api_boundary_reached") is True
            ),
            "wait_completed": summary.get("wait_completed") is True,
            "dataset_id_present": summary.get("dataset_id_present") is True,
            "dataset_request_binding_verified": (
                summary.get("dataset_request_binding_verified") is True
            ),
            "native_media_uploaded": (
                summary.get("native_media_uploaded") is False
            ),
            "media_upload_api_observed": (
                summary.get("media_upload_api_observed") is False
            ),
            "c3_grading_ready": (
                summary.get("c3_grading_ready") is False
            ),
            "artifact_receipts": bool(artifact_receipts)
            and all(
                receipt["verification_status"] == "verified"
                for receipt in artifact_receipts
            ),
            "verified_modalities": bool(verified_modalities),
        }
        for field, passed in validity_checks.items():
            if not passed:
                invalid_probe_fields.append(f"{prefix}.{field}")

        projected_probes.append(
            {
                "path": public_path,
                "request_content_sha256": request_content_sha256,
                "request_status": str(summary.get("request_status", "")),
                "dataset_request_binding_verified": (
                    summary.get("dataset_request_binding_verified") is True
                ),
                "artifact_receipts": artifact_receipts,
                "verified_generated_artifact_modalities": verified_modalities,
                "valid_for_aggregation": all(validity_checks.values())
                and not receipt_invalid_fields
                and not inherited_invalid_fields
                and not unexpected_verified_modalities
                and bool(public_path)
                and bool(request_content_sha256),
            }
        )

    request_hashes = [
        probe["request_content_sha256"]
        for probe in projected_probes
        if probe["request_content_sha256"]
    ]
    if len(set(request_hashes)) != len(request_hashes):
        invalid_probe_fields.append(
            "probes.request_content_sha256.not_unique"
        )
    artifact_hashes = [
        receipt["sha256"]
        for probe in projected_probes
        for receipt in probe["artifact_receipts"]
        if receipt["verification_status"] == "verified"
        and receipt["sha256"]
    ]
    if len(set(artifact_hashes)) != len(artifact_hashes):
        invalid_probe_fields.append(
            "probes.artifact_receipts.sha256.not_unique"
        )

    invalid_probe_fields = sorted(set(invalid_probe_fields))
    aggregation_valid = (
        len(projected_probes) == len(expected_modalities)
        and not invalid_probe_fields
        and all(probe["valid_for_aggregation"] for probe in projected_probes)
    )
    verified_modalities = (
        sorted(
            {
                modality
                for probe in projected_probes
                for modality in probe[
                    "verified_generated_artifact_modalities"
                ]
            },
            key=expected_modalities.index,
        )
        if aggregation_valid
        else []
    )
    all_expected_modalities_verified = (
        aggregation_valid
        and verified_modalities == list(expected_modalities)
    )
    native_media_surface_binding_verified = bool(
        releasefoundry_native_media_surface.get("surface_audit_verified") is True
        and releasefoundry_native_media_surface.get("generated_artifact_capabilities")
        == {
            "image": "verified",
            "audio": "verified",
            "file": "verified",
            "video": "provider_unverified",
        }
        and releasefoundry_native_media_surface.get("caller_native_input_support_proven")
        is False
        and releasefoundry_native_media_surface.get("c3_grading_ready") is False
    )

    return {
        "artifact_origin": "releasefoundry_generated_dataset",
        "aggregation_status": (
            "verified"
            if all_expected_modalities_verified
            else "invalid"
            if invalid_probe_fields
            else "incomplete"
        ),
        "probe_count": len(projected_probes),
        "verified_probe_count": (
            sum(
                probe["valid_for_aggregation"]
                for probe in projected_probes
            )
            if aggregation_valid
            else 0
        ),
        "independent_request_count": (
            len(set(request_hashes)) if aggregation_valid else 0
        ),
        "required_verified_modalities": list(expected_modalities),
        "verified_generated_artifact_modalities": verified_modalities,
        "provider_unverified_modalities": ["video"],
        "all_expected_modalities_verified": (
            all_expected_modalities_verified
        ),
        "native_media_uploaded": False,
        "media_upload_api_observed": False,
        "caller_native_input_support_proven": False,
        "native_media_surface_path": (
            str(releasefoundry_native_media_surface.get("path", ""))
            if native_media_surface_binding_verified
            else ""
        ),
        "native_media_surface_binding_verified": (
            native_media_surface_binding_verified
        ),
        "public_safe": aggregation_valid,
        "c3_grading_ready": False,
        "probes": projected_probes,
        "invalid_probe_fields": invalid_probe_fields,
        "notes": [
            "This projection combines three independent public-safe ReleaseFoundry request receipts without merging their request identities.",
            "It proves only ReleaseFoundry-generated image, audio, and file artifact availability.",
            "It does not prove caller-native media upload support, reviewed grading, Reward Model training, or C3 completion.",
            "Video remains provider-unverified and is excluded from the default real-API smoke path.",
        ],
    }


def _llm_offline_only(calibration_matrix: dict[str, Any]) -> bool:
    providers = set()
    for row in calibration_matrix.get("cost_ledger", []):
        if row.get("source") == "llm_judge":
            providers.update(str(provider) for provider in row.get("provider_counts", {}))
    return providers == {"offline_reference"}
