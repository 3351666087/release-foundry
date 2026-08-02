from __future__ import annotations

import argparse
import copy
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import a2_releasefoundry_live_calibration as calibration  # noqa: E402
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue  # noqa: E402
from services.judge.releasefoundry_preference_evaluation import (  # noqa: E402
    build_releasefoundry_run_binding_receipt,
    build_provisional_preference_artifact,
    build_public_provisional_preference_artifact,
)
from services.judge.result_persistence import stable_hash  # noqa: E402


DEFAULT_QUEUE = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_disagreement_review_queue.json"
)
DEFAULT_MAPPING_PRIVATE_REVIEW = calibration.DEFAULT_PRIVATE_MAPPING_REVIEW
DEFAULT_MAPPING_RECEIPT = calibration.DEFAULT_MAPPING_RECEIPT
DEFAULT_PRIVATE_SOURCE = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_exploratory_preference_calibration_source.private.json"
)
DEFAULT_PRIVATE_ARTIFACTS = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_exploratory_preference_calibration.private.json"
)
DEFAULT_PUBLIC_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_preference_calibration.json"
)
DEFAULT_QUALITY_LADDER_PRIVATE_SOURCE = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_quality_ladder_calibration_source.private.json"
)
DEFAULT_QUALITY_LADDER_PRIVATE_ARTIFACTS = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_quality_ladder_calibration.private.json"
)
DEFAULT_QUALITY_LADDER_PUBLIC_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_quality_ladder_calibration.json"
)
DEFAULT_SENSITIVITY_PROBE_PRIVATE_SOURCE = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_sensitivity_probe_source.private.json"
)
DEFAULT_SENSITIVITY_PROBE_PRIVATE_ARTIFACTS = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_sensitivity_probe.private.json"
)
DEFAULT_SENSITIVITY_PROBE_PUBLIC_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_sensitivity_probe.json"
)
DEFAULT_ACTION_VALUE_PROBE_PRIVATE_SOURCE = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_action_value_probe_source.private.json"
)
DEFAULT_ACTION_VALUE_PROBE_PRIVATE_ARTIFACTS = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_action_value_probe.private.json"
)
DEFAULT_ACTION_VALUE_PROBE_PUBLIC_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_action_value_probe.json"
)
DEFAULT_DECISION_BOUNDARY_PROBE_PRIVATE_SOURCE = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_decision_boundary_probe_source.private.json"
)
DEFAULT_DECISION_BOUNDARY_PROBE_PRIVATE_ARTIFACTS = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_decision_boundary_probe.private.json"
)
DEFAULT_DECISION_BOUNDARY_PROBE_PUBLIC_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_decision_boundary_probe.json"
)
BASELINE_STRATEGIES = (
    "observed_fixture",
    "reference_aligned",
    "degraded_control",
)
QUALITY_LADDER_STRATEGIES = (
    "reference_aligned",
    "minor_final_answer_defect",
    "wrong_final_answer",
    "minor_tool_argument_defect",
    "wrong_tool_order",
    "premature_stop",
    "observed_fixture",
    "severe_control",
)
SENSITIVITY_PROBE_STRATEGIES = (
    "reference_aligned",
    "wrong_tool_order",
    "reverse_tool_order",
    "missing_middle_tool",
    "wrong_tool_name",
    "double_tool_argument_defect",
    "tool_and_answer_defect",
    "severe_control",
)
ACTION_VALUE_PROBE_STRATEGIES = (
    "reference_aligned",
    "premature_stop",
    "hallucinated_without_tools",
    "redundant_post_success_call",
    "recovered_argument_error",
    "recovered_wrong_tool",
    "contradictory_final_answer_after_tools",
    "severe_control",
)
DECISION_BOUNDARY_PROBE_STRATEGIES = (
    "reference_aligned",
    "redundant_post_success_call",
    "redundant_post_success_calls_2",
    "redundant_post_success_calls_3",
    "premature_stop",
    "premature_stop_two_actions",
    "minor_final_answer_after_tools",
    "contradictory_final_answer_after_tools",
)
STRATEGIES = BASELINE_STRATEGIES
STRATEGY_PROFILES = {
    "baseline": BASELINE_STRATEGIES,
    "quality_ladder": QUALITY_LADDER_STRATEGIES,
    "sensitivity_probe": SENSITIVITY_PROBE_STRATEGIES,
    "action_value_probe": ACTION_VALUE_PROBE_STRATEGIES,
    "decision_boundary_probe": DECISION_BOUNDARY_PROBE_STRATEGIES,
}
SCHEMA_VERSION = "a2.releasefoundry_preference_calibration.v1"
PRIVATE_SOURCE_SCHEMA_VERSION = "a2.releasefoundry_preference_source_private.v1"
PRIVATE_RESULT_SCHEMA_VERSION = "a2.releasefoundry_preference_results_private.v1"
PROMPT_VERSION = "a2.releasefoundry_preference_prompt.v1"
STRATEGY_VERSION = "a2.releasefoundry_preference_candidate.v1"
QUALITY_LADDER_STRATEGY_VERSION = "a2.releasefoundry_quality_ladder_candidate.v1"
SENSITIVITY_PROBE_STRATEGY_VERSION = "a2.releasefoundry_sensitivity_probe_candidate.v1"
ACTION_VALUE_PROBE_STRATEGY_VERSION = "a2.releasefoundry_action_value_probe_candidate.v1"
DECISION_BOUNDARY_PROBE_STRATEGY_VERSION = (
    "a2.releasefoundry_decision_boundary_probe_candidate.v1"
)


class ReleaseFoundryPreferenceCalibrationError(ValueError):
    pass


def build_strategy_matrices(
    queue: dict[str, Any],
    base_matrix: list[dict[str, Any]],
    *,
    strategies: tuple[str, ...] = STRATEGIES,
) -> dict[str, list[dict[str, Any]]]:
    selected = _selected_variants(queue, base_matrix)
    matrices = {strategy: [] for strategy in strategies}
    for item, variant in selected:
        for strategy in strategies:
            candidate = copy.deepcopy(variant)
            candidate["review_item_id"] = item["review_item_id"]
            candidate["source_variant_hash"] = item["variant_id_hash"]
            candidate["candidate_strategy"] = strategy
            candidate["candidate_run"] = _strategy_candidate_run(
                strategy,
                variant,
            )
            matrices[strategy].append(candidate)
    expected_ids = {
        str(variant["variant_id"]) for _, variant in selected
    }
    for strategy, matrix in matrices.items():
        observed_ids = [str(item["variant_id"]) for item in matrix]
        if len(observed_ids) != len(set(observed_ids)):
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_test_ids_not_unique"
            )
        if set(observed_ids) != expected_ids:
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_test_set_mismatch"
            )
    return matrices


def build_private_source_bundle(
    queue: dict[str, Any],
    matrices: dict[str, list[dict[str, Any]]],
    *,
    experiment_label: str | None = None,
    strategies: tuple[str, ...] = STRATEGIES,
    strategy_version: str = STRATEGY_VERSION,
    strategy_profile: str | None = None,
) -> dict[str, Any]:
    _require_strategy_matrices(matrices, strategies=strategies)
    by_strategy = {
        strategy: {
            str(item["source_variant_hash"]): item
            for item in matrices[strategy]
        }
        for strategy in strategies
    }
    items = []
    anchor_strategy = strategies[0]
    for queue_item in queue.get("items", []):
        variant_hash = str(queue_item["variant_id_hash"])
        observed = by_strategy[anchor_strategy][variant_hash]
        candidates = []
        for strategy in strategies:
            variant = by_strategy[strategy][variant_hash]
            candidates.append(
                {
                    "candidate_id": strategy,
                    "candidate_run": copy.deepcopy(variant["candidate_run"]),
                }
            )
        items.append(
            {
                "review_item_id": queue_item["review_item_id"],
                "variant_id": observed["variant_id"],
                "variant_id_hash": variant_hash,
                "case_id": observed["case_id"],
                "fixture_ref": observed["fixture_ref"],
                "prompt": observed["prompt"],
                "reference_answer": observed["expected_response"],
                "expected_tool_calls": copy.deepcopy(
                    observed["expected_tool_calls"]
                ),
                "candidates": candidates,
            }
        )
    core = {
        "schema_version": PRIVATE_SOURCE_SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "warning": "Private raw candidate material. Do not commit.",
        "harness_revision": calibration.HARNESS_REVISION,
        "tool_call_alignment": calibration.TOOL_CALL_ALIGNMENT,
        "source_queue_sha256": review_queue._sha256_json(queue),
        "strategy_version": strategy_version,
        "candidate_strategies": list(strategies),
        "text_projection_only": True,
        "native_media_uploaded": False,
        "items": items,
    }
    if experiment_label is not None:
        core["experiment_label"] = experiment_label
    if strategy_profile is not None:
        core["strategy_profile"] = strategy_profile
    return {**core, "source_bundle_hash": stable_hash(core)}


def build_preference_outputs(
    queue: dict[str, Any],
    matrices: dict[str, list[dict[str, Any]]],
    journals: dict[str, dict[str, Any]],
    *,
    dataset_identity_hash: str,
    experiment_label: str | None = None,
    strategies: tuple[str, ...] = STRATEGIES,
    strategy_version: str = STRATEGY_VERSION,
    strategy_profile: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _require_strategy_matrices(matrices, strategies=strategies)
    if set(journals) != set(strategies):
        raise ReleaseFoundryPreferenceCalibrationError("strategy_journals_missing")

    anchor_strategy = strategies[0]
    expected_ids = {
        str(item["variant_id"]) for item in matrices[anchor_strategy]
    }
    test_maps: dict[str, dict[str, dict[str, Any]]] = {}
    run_receipts: dict[str, dict[str, Any]] = {}
    dataset_binding_hashes = set()
    for strategy in strategies:
        journal = journals[strategy]
        terminal = _completed_terminal(
            journal,
            expected_ids=expected_ids,
            strategy=strategy,
        )
        run = _unwrap_run(terminal)
        binding = journal.get("dataset_binding")
        if not isinstance(binding, dict) or binding.get("dataset_id") is None:
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_dataset_binding_missing"
            )
        dataset_id = binding["dataset_id"]
        dataset_binding_hashes.add(stable_hash(binding))
        test_maps[strategy] = _terminal_tests_by_id(run, expected_ids)
        run_receipts[strategy] = build_releasefoundry_run_binding_receipt(
            run,
            expected_test_ids=sorted(expected_ids),
            expected_dataset_id=dataset_id,
            dataset_identity_hash=dataset_identity_hash,
        )
    if len(dataset_binding_hashes) != 1:
        raise ReleaseFoundryPreferenceCalibrationError("strategy_dataset_binding_mismatch")

    queue_by_hash = {
        str(item["variant_id_hash"]): item for item in queue["items"]
    }
    matrix_by_strategy = {
        strategy: {
            str(item["source_variant_hash"]): item
            for item in matrices[strategy]
        }
        for strategy in strategies
    }
    private_items = []
    public_items = []
    for variant_hash in sorted(queue_by_hash):
        queue_item = queue_by_hash[variant_hash]
        observed = matrix_by_strategy[anchor_strategy][variant_hash]
        candidates = [
            _public_candidate(
                matrix_by_strategy[strategy][variant_hash],
                strategy=strategy,
                dataset_identity_hash=dataset_identity_hash,
                strategy_version=strategy_version,
            )
            for strategy in strategies
        ]
        candidate_batch_id = stable_hash(
            {
                "schema_version": strategy_version,
                "source_queue_sha256": review_queue._sha256_json(queue),
                "review_item_id": queue_item["review_item_id"],
                "variant_id_hash": variant_hash,
                "candidate_hashes": [
                    {
                        "candidate_id": item["candidate_id"],
                        "trace_hash": item["trace_hash"],
                        "final_answer_hash": item["final_answer_hash"],
                    }
                    for item in candidates
                ],
            }
        )
        observations = []
        for strategy in strategies:
            variant = matrix_by_strategy[strategy][variant_hash]
            test_id = str(variant["variant_id"])
            observations.append(
                {
                    "candidate_id": strategy,
                    "expected_test_id": test_id,
                    "server_test_result": test_maps[strategy][test_id],
                    "run_receipt": run_receipts[strategy],
                }
            )
        private_artifact = build_provisional_preference_artifact(
            candidate_batch_id=candidate_batch_id,
            candidates=candidates,
            observations=observations,
        )
        public_artifact = build_public_provisional_preference_artifact(
            private_artifact
        )
        private_items.append(
            {
                "review_item_id": queue_item["review_item_id"],
                "variant_id": observed["variant_id"],
                "private_artifact": private_artifact,
            }
        )
        public_items.append(
            {
                "review_item_id": queue_item["review_item_id"],
                "case_id": queue_item["case_id"],
                "channel": queue_item["channel"],
                "prompt_variant": queue_item["prompt_variant"],
                "expected_variant": queue_item["expected_variant"],
                "preference_artifact": public_artifact,
            }
        )

    metrics = _preference_metrics(public_items, strategies=strategies)
    http_metrics = _http_metrics(journals, strategies=strategies)
    for strategy in strategies:
        create_metrics = http_metrics["by_strategy"][strategy]["create_run"]
        if create_metrics["retry_count"] != 0:
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_create_run_retry_forbidden"
            )
        if (
            create_metrics["attempt_count"] != 1
            or create_metrics["success_count"] != 1
            or create_metrics["error_count"] != 0
        ):
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_create_run_receipt_invalid"
            )

    private_core = {
        "schema_version": PRIVATE_RESULT_SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "warning": "Private ReleaseFoundry receipts and identifiers. Do not commit.",
        "harness_revision": calibration.HARNESS_REVISION,
        "tool_call_alignment": calibration.TOOL_CALL_ALIGNMENT,
        "source_queue_sha256": review_queue._sha256_json(queue),
        "dataset_identity_hash": dataset_identity_hash,
        "candidate_strategies": list(strategies),
        "items": private_items,
    }
    if experiment_label is not None:
        private_core["experiment_label"] = experiment_label
    if strategy_profile is not None:
        private_core["strategy_profile"] = strategy_profile
    private_output = {
        **private_core,
        "artifact_bundle_hash": stable_hash(private_core),
    }
    public_core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "experiment_status": "completed",
        "harness_revision": calibration.HARNESS_REVISION,
        "tool_call_alignment": calibration.TOOL_CALL_ALIGNMENT,
        "source_queue_sha256": review_queue._sha256_json(queue),
        "candidate_strategies": list(strategies),
        "experiment_plan": {
            "task_count": len(public_items),
            "candidate_count_per_task": len(strategies),
            "planned_paid_evaluations": len(public_items) * len(strategies),
            "observed_paid_evaluations": len(public_items) * len(strategies),
            "planned_create_run_calls": len(strategies),
            "observed_create_run_calls": http_metrics["create_run"][
                "attempt_count"
            ],
            "create_run_retries": 0,
        },
        "server_grading": {
            "tests_with_structure_grading": len(public_items) * len(strategies),
            "tests_with_final_answer_grading": (
                len(public_items) * len(strategies)
            ),
            "exact_test_set_verified_for_every_strategy": True,
            "per_test_receipts_verified": True,
            "aggregate_marker_used_as_authority": False,
        },
        "ranking": {
            "source": "derived_from_releasefoundry_observations",
            "server_native_pairwise_ranking": False,
        },
        "preference_summary": metrics,
        "http_calls": http_metrics,
        "items": public_items,
        "text_projection_only": True,
        "native_media_uploaded": False,
        "human_gold": False,
        "human_reviewed": False,
        "human_review_required": True,
        "training_eligible": False,
        "c3_authority": False,
        "c3_transition_allowed": False,
        "release_authority": False,
        "public_safety": {
            "contains_api_key": False,
            "contains_api_key_hash": False,
            "contains_raw_prompt": False,
            "contains_raw_candidate_response": False,
            "contains_raw_tool_arguments": False,
            "contains_private_service_ids": False,
            "contains_local_absolute_paths": False,
        },
        "notes": [
            "Each strategy used one independent, non-retried create_run call.",
            "All rankings are derived from receipt-bound ReleaseFoundry observations; ReleaseFoundry did not return a native pairwise ranking.",
            "These candidates remain text projections over the existing fixtures and do not claim native image, audio, video, or document upload.",
            "ReleaseFoundry-only preferences are provisional and require human review before training or release use.",
        ],
    }
    if experiment_label is not None:
        public_core["experiment_label"] = experiment_label
    if strategy_profile is not None:
        public_core["strategy_profile"] = strategy_profile
    public_output = {**public_core, "artifact_hash": stable_hash(public_core)}
    _assert_public_output_safe(public_output, matrices=matrices, journals=journals)
    return private_output, public_output


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[int], Any] | None = None,
    environ: dict[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score candidate strategies for stable A2 disagreements using "
            "independent, receipt-bound ReleaseFoundry runs."
        )
    )
    parser.add_argument(
        "--strategy-profile",
        choices=sorted(STRATEGY_PROFILES),
        default="baseline",
        help=(
            "baseline preserves the original three-candidate experiment; "
            "quality_ladder spans isolated quality defects; "
            "sensitivity_probe targets tool-order blindness and the missing "
            "mid-reward band; action_value_probe tests stop, recovery, and "
            "post-tool answer decisions; decision_boundary_probe sweeps "
            "redundant-call count, missing-action count, and final-answer "
            "contradiction severity."
        ),
    )
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument(
        "--mapping-private-review",
        default=str(DEFAULT_MAPPING_PRIVATE_REVIEW),
    )
    parser.add_argument(
        "--mapping-receipt",
        default=str(DEFAULT_MAPPING_RECEIPT),
    )
    parser.add_argument("--private-source")
    parser.add_argument(
        "--private-artifacts",
    )
    parser.add_argument("--public-output")
    parser.add_argument(
        "--experiment-label",
        help=(
            "Optional safe label for an independent repeat. It namespaces "
            "private journals so completed runs are never overwritten or "
            "resubmitted."
        ),
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--poll-timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Read-only get_dataset/get_run retries only; create_run is never retried.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-mutate", action="store_true")
    parser.add_argument("--allow-unverified-exploration", action="store_true")
    args = parser.parse_args(argv)
    experiment_label = _validate_experiment_label(args.experiment_label)
    strategies = STRATEGY_PROFILES[args.strategy_profile]
    strategy_version = {
        "baseline": STRATEGY_VERSION,
        "quality_ladder": QUALITY_LADDER_STRATEGY_VERSION,
        "sensitivity_probe": SENSITIVITY_PROBE_STRATEGY_VERSION,
        "action_value_probe": ACTION_VALUE_PROBE_STRATEGY_VERSION,
        "decision_boundary_probe": (
            DECISION_BOUNDARY_PROBE_STRATEGY_VERSION
        ),
    }[args.strategy_profile]
    if args.strategy_profile != "baseline" and experiment_label is None:
        parser.error(
            f"--strategy-profile {args.strategy_profile} requires "
            "--experiment-label"
        )

    if args.execute and not (
        args.allow_mutate and args.allow_unverified_exploration
    ):
        parser.error(
            "--execute requires --allow-mutate and "
            "--allow-unverified-exploration"
        )
    if not args.execute and (
        args.allow_mutate or args.allow_unverified_exploration
    ):
        parser.error(
            "--allow-mutate and --allow-unverified-exploration require --execute"
        )

    queue_path = calibration._resolve(args.queue)
    mapping_private_path = calibration._resolve(args.mapping_private_review)
    mapping_receipt_path = calibration._resolve(args.mapping_receipt)
    private_source_path = calibration._resolve(
        args.private_source
        or (
            {
                "baseline": DEFAULT_PRIVATE_SOURCE,
                "quality_ladder": DEFAULT_QUALITY_LADDER_PRIVATE_SOURCE,
                "sensitivity_probe": (
                    DEFAULT_SENSITIVITY_PROBE_PRIVATE_SOURCE
                ),
                "action_value_probe": (
                    DEFAULT_ACTION_VALUE_PROBE_PRIVATE_SOURCE
                ),
                "decision_boundary_probe": (
                    DEFAULT_DECISION_BOUNDARY_PROBE_PRIVATE_SOURCE
                ),
            }[args.strategy_profile]
        )
    )
    private_artifacts_path = calibration._resolve(
        args.private_artifacts
        or (
            {
                "baseline": DEFAULT_PRIVATE_ARTIFACTS,
                "quality_ladder": DEFAULT_QUALITY_LADDER_PRIVATE_ARTIFACTS,
                "sensitivity_probe": (
                    DEFAULT_SENSITIVITY_PROBE_PRIVATE_ARTIFACTS
                ),
                "action_value_probe": (
                    DEFAULT_ACTION_VALUE_PROBE_PRIVATE_ARTIFACTS
                ),
                "decision_boundary_probe": (
                    DEFAULT_DECISION_BOUNDARY_PROBE_PRIVATE_ARTIFACTS
                ),
            }[args.strategy_profile]
        )
    )
    public_output_path = calibration._resolve(
        args.public_output
        or (
            {
                "baseline": DEFAULT_PUBLIC_OUTPUT,
                "quality_ladder": DEFAULT_QUALITY_LADDER_PUBLIC_OUTPUT,
                "sensitivity_probe": (
                    DEFAULT_SENSITIVITY_PROBE_PUBLIC_OUTPUT
                ),
                "action_value_probe": DEFAULT_ACTION_VALUE_PROBE_PUBLIC_OUTPUT,
                "decision_boundary_probe": (
                    DEFAULT_DECISION_BOUNDARY_PROBE_PUBLIC_OUTPUT
                ),
            }[args.strategy_profile]
        )
    )
    for path in (private_source_path, private_artifacts_path):
        calibration._require_private_ref(path)

    queue = calibration._read_json(queue_path)
    matrices = build_strategy_matrices(
        queue,
        calibration.build_matrix(),
        strategies=strategies,
    )
    private_source = build_private_source_bundle(
        queue,
        matrices,
        experiment_label=experiment_label,
        strategies=strategies,
        strategy_version=strategy_version,
        strategy_profile=args.strategy_profile,
    )
    calibration._write_json(private_source_path, private_source)

    journal_paths = {
        strategy: _strategy_private_path(
            strategy,
            "journal",
            experiment_label=experiment_label,
        )
        for strategy in strategies
    }
    summary_paths = {
        strategy: _strategy_private_path(
            strategy,
            "summary",
            experiment_label=experiment_label,
        )
        for strategy in strategies
    }
    for strategy in strategies:
        _bind_strategy_journal(
            journal_paths[strategy],
            strategy=strategy,
            queue=queue,
            matrix=matrices[strategy],
            experiment_label=experiment_label,
        )

    result = 0
    if args.execute:
        for strategy in strategies:
            journal = calibration._load_journal(journal_paths[strategy])
            expected_ids = {
                str(item["variant_id"]) for item in matrices[strategy]
            }
            if _journal_completed(journal, expected_ids=expected_ids):
                continue
            calibration_args = [
                "--execute",
                "--allow-mutate",
                "--allow-unverified-exploration",
                "--batch-size",
                str(len(matrices[strategy])),
                "--batches",
                "1",
                "--timeout",
                str(args.timeout),
                "--poll-timeout",
                str(args.poll_timeout),
                "--poll-interval",
                str(args.poll_interval),
                "--max-retries",
                str(args.max_retries),
                "--mapping-private-review",
                str(mapping_private_path),
                "--mapping-receipt",
                str(mapping_receipt_path),
                "--private-journal",
                str(journal_paths[strategy]),
                "--public-output",
                str(summary_paths[strategy]),
            ]
            result = calibration.main(
                calibration_args,
                client_factory=client_factory,
                environ=environ,
                matrix_factory=lambda strategy=strategy: matrices[strategy],
            )
            if result != 0:
                break

    journals = {
        strategy: calibration._load_journal(journal_paths[strategy])
        for strategy in strategies
    }
    if not all(
        _journal_completed(
            journals[strategy],
            expected_ids={
                str(item["variant_id"]) for item in matrices[strategy]
            },
        )
        for strategy in strategies
    ):
        public = _planned_public_output(
            queue,
            matrices,
            journals,
            experiment_label=experiment_label,
            strategies=strategies,
            strategy_profile=args.strategy_profile,
        )
        calibration._write_public_summary(public_output_path, public)
        return result or (2 if args.execute else 0)

    mapping_receipt = calibration._read_json(mapping_receipt_path)
    dataset_identity_hash = mapping_receipt.get("dataset_content_sha256")
    if not isinstance(dataset_identity_hash, str):
        raise ReleaseFoundryPreferenceCalibrationError(
            "mapping_dataset_identity_hash_missing"
        )
    private_output, public_output = build_preference_outputs(
        queue,
        matrices,
        journals,
        dataset_identity_hash=dataset_identity_hash,
        experiment_label=experiment_label,
        strategies=strategies,
        strategy_version=strategy_version,
        strategy_profile=args.strategy_profile,
    )
    calibration._write_json(private_artifacts_path, private_output)
    calibration._write_public_summary(public_output_path, public_output)
    print(
        "ReleaseFoundry preference calibration completed: "
        f"tasks={public_output['experiment_plan']['task_count']} "
        f"evaluations={public_output['experiment_plan']['observed_paid_evaluations']} "
        f"chosen={public_output['preference_summary']['chosen_pairs']} "
        f"blocked={public_output['preference_summary']['blocked_pairs']} "
        f"output={calibration._display_path(public_output_path)}"
    )
    return result


def _selected_variants(
    queue: dict[str, Any],
    base_matrix: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if (
        not isinstance(queue, dict)
        or queue.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise ReleaseFoundryPreferenceCalibrationError("queue_not_exploratory")
    items = queue.get("items")
    if not isinstance(items, list) or not items:
        raise ReleaseFoundryPreferenceCalibrationError("queue_items_missing")
    by_hash: dict[str, dict[str, Any]] = {}
    for variant in base_matrix:
        variant_id = str(variant["variant_id"])
        variant_hash = review_queue._sha256_text(
            f"a2:releasefoundry-exploratory-variant:v1:{variant_id}"
        )
        if variant_hash in by_hash:
            raise ReleaseFoundryPreferenceCalibrationError(
                "base_matrix_variant_hash_collision"
            )
        by_hash[variant_hash] = variant
    selected = []
    observed_hashes = set()
    for item in items:
        if not isinstance(item, dict):
            raise ReleaseFoundryPreferenceCalibrationError("queue_item_invalid")
        variant_hash = str(item.get("variant_id_hash", ""))
        if not variant_hash or variant_hash in observed_hashes:
            raise ReleaseFoundryPreferenceCalibrationError(
                "queue_variant_hash_not_unique"
            )
        variant = by_hash.get(variant_hash)
        if variant is None:
            raise ReleaseFoundryPreferenceCalibrationError(
                "queue_variant_not_found_in_matrix"
            )
        observed_hashes.add(variant_hash)
        selected.append((item, variant))
    return selected


def _strategy_candidate_run(
    strategy: str,
    variant: dict[str, Any],
) -> dict[str, Any]:
    if strategy == "observed_fixture":
        fixture = calibration._read_json(ROOT / variant["fixture_ref"])
        run = fixture.get("run")
        if not isinstance(run, dict):
            raise ReleaseFoundryPreferenceCalibrationError("fixture_run_missing")
        candidate = run
    elif strategy == "reference_aligned":
        candidate = _reference_candidate(variant)
    elif strategy == "minor_final_answer_defect":
        candidate = _reference_candidate(variant)
        candidate["final_response"] = _minor_final_answer_defect(
            candidate["final_response"]
        )
    elif strategy == "wrong_final_answer":
        candidate = _reference_candidate(variant)
        candidate["final_response"] = _wrong_final_answer(
            candidate["final_response"]
        )
    elif strategy == "minor_tool_argument_defect":
        candidate = _reference_candidate(variant)
        _mutate_last_tool_argument(candidate["tool_calls"])
    elif strategy == "wrong_tool_order":
        candidate = _reference_candidate(variant)
        if len(candidate["tool_calls"]) < 2:
            raise ReleaseFoundryPreferenceCalibrationError(
                "wrong_tool_order_requires_two_calls"
            )
        candidate["tool_calls"][0], candidate["tool_calls"][1] = (
            candidate["tool_calls"][1],
            candidate["tool_calls"][0],
        )
    elif strategy == "reverse_tool_order":
        candidate = _reference_candidate(variant)
        if len(candidate["tool_calls"]) < 2:
            raise ReleaseFoundryPreferenceCalibrationError(
                "reverse_tool_order_requires_two_calls"
            )
        candidate["tool_calls"] = list(
            reversed(candidate["tool_calls"])
        )
    elif strategy == "missing_middle_tool":
        candidate = _reference_candidate(variant)
        if len(candidate["tool_calls"]) < 3:
            raise ReleaseFoundryPreferenceCalibrationError(
                "missing_middle_tool_requires_three_calls"
            )
        middle = len(candidate["tool_calls"]) // 2
        candidate["tool_calls"] = (
            candidate["tool_calls"][:middle]
            + candidate["tool_calls"][middle + 1 :]
        )
    elif strategy == "wrong_tool_name":
        candidate = _reference_candidate(variant)
        if not candidate["tool_calls"]:
            raise ReleaseFoundryPreferenceCalibrationError(
                "wrong_tool_name_requires_tool_call"
            )
        candidate["tool_calls"][-1]["tool"] += ".wrong"
    elif strategy == "double_tool_argument_defect":
        candidate = _reference_candidate(variant)
        if len(candidate["tool_calls"]) < 2:
            raise ReleaseFoundryPreferenceCalibrationError(
                "double_tool_argument_defect_requires_two_calls"
            )
        _mutate_tool_argument(candidate["tool_calls"][0])
        _mutate_tool_argument(candidate["tool_calls"][-1])
    elif strategy == "tool_and_answer_defect":
        candidate = _reference_candidate(variant)
        _mutate_last_tool_argument(candidate["tool_calls"])
        candidate["final_response"] = _wrong_final_answer(
            candidate["final_response"]
        )
    elif strategy == "premature_stop":
        candidate = _reference_candidate(variant)
        if not candidate["tool_calls"]:
            raise ReleaseFoundryPreferenceCalibrationError(
                "premature_stop_requires_tool_call"
            )
        candidate["tool_calls"] = candidate["tool_calls"][:-1]
    elif strategy == "premature_stop_two_actions":
        candidate = _reference_candidate(variant)
        if len(candidate["tool_calls"]) < 2:
            raise ReleaseFoundryPreferenceCalibrationError(
                "premature_stop_two_actions_requires_two_calls"
            )
        candidate["tool_calls"] = candidate["tool_calls"][:-2]
    elif strategy == "hallucinated_without_tools":
        candidate = _reference_candidate(variant)
        candidate["tool_calls"] = []
    elif strategy == "redundant_post_success_call":
        candidate = _reference_candidate(variant)
        if not candidate["tool_calls"]:
            raise ReleaseFoundryPreferenceCalibrationError(
                "redundant_post_success_call_requires_tool_call"
            )
        candidate["tool_calls"].append(
            copy.deepcopy(candidate["tool_calls"][-1])
        )
    elif strategy in {
        "redundant_post_success_calls_2",
        "redundant_post_success_calls_3",
    }:
        candidate = _reference_candidate(variant)
        if not candidate["tool_calls"]:
            raise ReleaseFoundryPreferenceCalibrationError(
                "redundant_post_success_calls_requires_tool_call"
            )
        repeat_count = (
            2 if strategy == "redundant_post_success_calls_2" else 3
        )
        redundant_call = copy.deepcopy(candidate["tool_calls"][-1])
        candidate["tool_calls"].extend(
            copy.deepcopy(redundant_call) for _ in range(repeat_count)
        )
    elif strategy == "recovered_argument_error":
        candidate = _reference_candidate(variant)
        if not candidate["tool_calls"]:
            raise ReleaseFoundryPreferenceCalibrationError(
                "recovered_argument_error_requires_tool_call"
            )
        failed_call = copy.deepcopy(candidate["tool_calls"][0])
        _mutate_tool_argument(failed_call)
        failed_call["error"] = "simulated invalid arguments"
        candidate["tool_calls"] = [failed_call, *candidate["tool_calls"]]
    elif strategy == "recovered_wrong_tool":
        candidate = _reference_candidate(variant)
        if not candidate["tool_calls"]:
            raise ReleaseFoundryPreferenceCalibrationError(
                "recovered_wrong_tool_requires_tool_call"
            )
        failed_call = copy.deepcopy(candidate["tool_calls"][0])
        failed_call["tool"] = f"{failed_call['tool']}.wrong"
        failed_call["error"] = "simulated wrong tool"
        candidate["tool_calls"] = [failed_call, *candidate["tool_calls"]]
    elif strategy == "contradictory_final_answer_after_tools":
        candidate = _reference_candidate(variant)
        candidate["final_response"] = _wrong_final_answer(
            candidate["final_response"]
        )
    elif strategy == "minor_final_answer_after_tools":
        candidate = _reference_candidate(variant)
        candidate["final_response"] = _minor_final_answer_defect(
            candidate["final_response"]
        )
    elif strategy in {"degraded_control", "severe_control"}:
        expected = variant["expected_tool_calls"]
        tool_calls = []
        if expected:
            tool_calls.append(
                {
                    "tool": str(expected[0].get("tool", "")),
                    "args": {"degraded_control": True},
                    "output": {"control": "intentionally_unreliable"},
                }
            )
        else:
            tool_calls.append(
                {
                    "tool": "control.unexpected",
                    "args": {},
                    "output": {"control": "intentionally_unreliable"},
                }
            )
        candidate = {
            "tool_calls": tool_calls,
            "final_response": (
                "The requested result is definitely available and correct."
            ),
        }
    else:
        raise ReleaseFoundryPreferenceCalibrationError("candidate_strategy_unknown")
    return calibration._candidate_run({"candidate_run": candidate}, {})


def _reference_candidate(variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_calls": [
            {
                "tool": str(item.get("tool", "")),
                "args": copy.deepcopy(
                    item.get("args")
                    if isinstance(item.get("args"), dict)
                    else {}
                ),
            }
            for item in variant["expected_tool_calls"]
        ],
        "final_response": str(variant["expected_response"]),
    }


def _minor_final_answer_defect(response: str) -> str:
    replacements = (
        (r"\bred\b", "colored"),
        (r"\bcritical\b", "notable"),
        (r"\bexactly\b", "approximately"),
    )
    for pattern, replacement in replacements:
        mutated, count = re.subn(
            pattern,
            replacement,
            response,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            return mutated
    return response.rstrip(".") + ", but one requested detail is unconfirmed."


def _wrong_final_answer(response: str) -> str:
    entity_swaps = (
        (r"\bBilling\b", "Payments"),
        (r"\bPayments\b", "Billing"),
        (r"\bpass(?:ed)?\b", "failed"),
        (r"\bfailed\b", "passed"),
    )
    for pattern, replacement in entity_swaps:
        mutated, count = re.subn(
            pattern,
            replacement,
            response,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            return mutated
    return "The evidence supports the opposite conclusion."


def _mutate_last_tool_argument(tool_calls: list[dict[str, Any]]) -> None:
    if not tool_calls:
        raise ReleaseFoundryPreferenceCalibrationError(
            "minor_tool_argument_defect_requires_tool_call"
        )
    _mutate_tool_argument(tool_calls[-1])


def _mutate_tool_argument(tool_call: dict[str, Any]) -> None:
    args = tool_call.get("args")
    if not isinstance(args, dict) or not args:
        raise ReleaseFoundryPreferenceCalibrationError(
            "minor_tool_argument_defect_requires_argument"
        )
    key = sorted(args)[0]
    value = args[key]
    if isinstance(value, str):
        args[key] = f"{value}-near-miss"
    elif isinstance(value, bool):
        args[key] = not value
    elif isinstance(value, (int, float)):
        args[key] = value + 1
    else:
        args[key] = {"quality_ladder_defect": True}


def _public_candidate(
    variant: dict[str, Any],
    *,
    strategy: str,
    dataset_identity_hash: str,
    strategy_version: str = STRATEGY_VERSION,
) -> dict[str, Any]:
    candidate_run = variant["candidate_run"]
    return {
        "candidate_id": strategy,
        "task_id": str(variant["review_item_id"]),
        "sample_id": stable_hash(
            {
                "review_item_id": variant["review_item_id"],
                "source_variant_hash": variant["source_variant_hash"],
            }
        ),
        "dataset_identity_hash": dataset_identity_hash,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": stable_hash(variant["prompt"]),
        "media_evidence_hashes": [],
        "model_version": f"{strategy_version}:{strategy}",
        "trace_hash": stable_hash(candidate_run["tool_calls"]),
        "final_answer_hash": stable_hash(candidate_run["final_response"]),
    }


def _completed_terminal(
    journal: dict[str, Any],
    *,
    expected_ids: set[str],
    strategy: str,
) -> dict[str, Any]:
    batches = [
        batch
        for batch in journal.get("batches", [])
        if isinstance(batch, dict) and batch.get("status") == "completed"
    ]
    if len(batches) != 1:
        raise ReleaseFoundryPreferenceCalibrationError(
            f"{strategy}_completed_batch_count_invalid"
        )
    batch = batches[0]
    variant_ids = batch.get("variant_ids")
    if not isinstance(variant_ids, list) or any(
        not isinstance(value, str) or not value for value in variant_ids
    ):
        raise ReleaseFoundryPreferenceCalibrationError(
            f"{strategy}_completed_test_ids_invalid"
        )
    if len(variant_ids) != len(set(variant_ids)):
        raise ReleaseFoundryPreferenceCalibrationError(
            f"{strategy}_completed_test_ids_not_unique"
        )
    if set(variant_ids) != expected_ids:
        raise ReleaseFoundryPreferenceCalibrationError(
            f"{strategy}_completed_test_set_mismatch"
        )
    terminal = batch.get("terminal_response")
    if not isinstance(terminal, dict):
        raise ReleaseFoundryPreferenceCalibrationError(
            f"{strategy}_terminal_response_missing"
        )
    if not calibration.server_grading_complete(terminal, expected_ids):
        raise ReleaseFoundryPreferenceCalibrationError(
            f"{strategy}_server_grading_incomplete"
        )
    return terminal


def _unwrap_run(terminal: dict[str, Any]) -> dict[str, Any]:
    run = (
        terminal.get("run")
        if isinstance(terminal.get("run"), dict)
        else terminal
    )
    if not isinstance(run, dict):
        raise ReleaseFoundryPreferenceCalibrationError("terminal_run_invalid")
    return run


def _terminal_tests_by_id(
    run: dict[str, Any],
    expected_ids: set[str],
) -> dict[str, dict[str, Any]]:
    result = run.get("result")
    tests = result.get("tests") if isinstance(result, dict) else None
    if not isinstance(tests, list):
        raise ReleaseFoundryPreferenceCalibrationError("terminal_tests_missing")
    indexed: dict[str, list[dict[str, Any]]] = {}
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("test_id"), str):
            raise ReleaseFoundryPreferenceCalibrationError("terminal_test_invalid")
        indexed.setdefault(test["test_id"], []).append(test)
    if set(indexed) != expected_ids:
        raise ReleaseFoundryPreferenceCalibrationError("terminal_test_set_mismatch")
    if any(len(values) != 1 for values in indexed.values()):
        raise ReleaseFoundryPreferenceCalibrationError("terminal_test_id_not_unique")
    return {key: values[0] for key, values in indexed.items()}


def _preference_metrics(
    items: list[dict[str, Any]],
    *,
    strategies: tuple[str, ...] = STRATEGIES,
) -> dict[str, Any]:
    chosen = Counter()
    rejected = Counter()
    statuses = Counter()
    rewards: dict[str, list[float]] = {strategy: [] for strategy in strategies}
    for item in items:
        pair = item["preference_artifact"]["pair"]
        statuses[str(pair["status"])] += 1
        if isinstance(pair.get("chosen"), dict):
            chosen[str(pair["chosen"]["candidate_id"])] += 1
        if isinstance(pair.get("rejected"), dict):
            rejected[str(pair["rejected"]["candidate_id"])] += 1
        for evaluation in pair["releasefoundry_evaluations"]:
            rewards[str(evaluation["candidate_id"])].append(
                float(evaluation["overall_reward"])
            )
    return {
        "chosen_pairs": sum(chosen.values()),
        "blocked_pairs": statuses["blocked"],
        "pair_statuses": dict(sorted(statuses.items())),
        "chosen_by_strategy": {
            strategy: chosen[strategy] for strategy in strategies
        },
        "rejected_by_strategy": {
            strategy: rejected[strategy] for strategy in strategies
        },
        "reward_distribution_by_strategy": {
            strategy: _score_statistics(rewards[strategy])
            for strategy in strategies
        },
    }


def _score_statistics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "maximum": None,
            "mean": None,
            "population_std": None,
        }
    return {
        "count": len(values),
        "minimum": round(min(values), 4),
        "maximum": round(max(values), 4),
        "mean": round(statistics.fmean(values), 4),
        "population_std": round(statistics.pstdev(values), 4),
    }


def _http_metrics(
    journals: dict[str, dict[str, Any]],
    *,
    strategies: tuple[str, ...] = STRATEGIES,
) -> dict[str, Any]:
    events_by_strategy = {
        strategy: _journal_http_events(journals[strategy])
        for strategy in strategies
    }
    events = [
        event
        for strategy in strategies
        for event in events_by_strategy[strategy]
    ]
    by_strategy = {
        strategy: _summarize_http_events(events_by_strategy[strategy])
        for strategy in strategies
    }
    return {
        **_summarize_http_events(events),
        "by_strategy": by_strategy,
    }


def _journal_http_events(journal: dict[str, Any]) -> list[dict[str, Any]]:
    events = [
        event
        for event in journal.get("preflight_http_events", [])
        if isinstance(event, dict)
    ]
    for batch in journal.get("batches", []):
        if isinstance(batch, dict):
            events.extend(
                event
                for event in batch.get("http_events", [])
                if isinstance(event, dict)
            )
    return events


def _summarize_http_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    operations = Counter(str(event.get("operation", "")) for event in events)
    create_events = [
        event for event in events if event.get("operation") == "create_run"
    ]
    return {
        "total": len(events),
        "by_operation": dict(sorted(operations.items())),
        "create_run": {
            "attempt_count": len(create_events),
            "success_count": sum(
                event.get("status") == "ok" for event in create_events
            ),
            "error_count": sum(
                event.get("status") == "error" for event in create_events
            ),
            "retry_count": sum(bool(event.get("retry")) for event in create_events),
            "automatic_retry_enabled": False,
        },
    }


def _planned_public_output(
    queue: dict[str, Any],
    matrices: dict[str, list[dict[str, Any]]],
    journals: dict[str, dict[str, Any]],
    *,
    experiment_label: str | None = None,
    strategies: tuple[str, ...] = STRATEGIES,
    strategy_profile: str | None = None,
) -> dict[str, Any]:
    task_count = len(matrices[strategies[0]])
    statuses = {
        strategy: Counter(
            str(batch.get("status", "unknown"))
            for batch in journals[strategy].get("batches", [])
            if isinstance(batch, dict)
        )
        for strategy in strategies
    }
    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "experiment_status": "partial",
        "source_queue_sha256": review_queue._sha256_json(queue),
        "candidate_strategies": list(strategies),
        "experiment_plan": {
            "task_count": task_count,
            "candidate_count_per_task": len(strategies),
            "planned_paid_evaluations": task_count * len(strategies),
            "planned_create_run_calls": len(strategies),
            "create_run_retries_allowed": 0,
        },
        "strategy_batch_statuses": {
            strategy: dict(sorted(statuses[strategy].items()))
            for strategy in strategies
        },
        "text_projection_only": True,
        "native_media_uploaded": False,
        "human_gold": False,
        "human_review_required": True,
        "training_eligible": False,
        "c3_authority": False,
        "c3_transition_allowed": False,
        "release_authority": False,
        "public_safety": {
            "contains_api_key": False,
            "contains_api_key_hash": False,
            "contains_raw_prompt": False,
            "contains_raw_candidate_response": False,
            "contains_raw_tool_arguments": False,
            "contains_private_service_ids": False,
            "contains_local_absolute_paths": False,
        },
    }
    if experiment_label is not None:
        core["experiment_label"] = experiment_label
    if strategy_profile is not None:
        core["strategy_profile"] = strategy_profile
    return {**core, "artifact_hash": stable_hash(core)}


def _bind_strategy_journal(
    path: Path,
    *,
    strategy: str,
    queue: dict[str, Any],
    matrix: list[dict[str, Any]],
    experiment_label: str | None = None,
) -> None:
    calibration._require_private_ref(path)
    journal = calibration._load_journal(path)
    expected = {
        "schema_version": "a2.releasefoundry_preference_strategy_binding.v2",
        "strategy": strategy,
        "harness_revision": calibration.HARNESS_REVISION,
        "tool_call_alignment": calibration.TOOL_CALL_ALIGNMENT,
        "source_queue_sha256": review_queue._sha256_json(queue),
        "matrix_hash": stable_hash(
            [
                {
                    "variant_id": item["variant_id"],
                    "source_variant_hash": item["source_variant_hash"],
                    "candidate_run": item["candidate_run"],
                }
                for item in matrix
            ]
        ),
        "create_run_automatic_retry": False,
    }
    if experiment_label is not None:
        expected["experiment_label"] = experiment_label
    observed = journal.get("preference_experiment")
    if observed is None:
        if journal.get("batches"):
            raise ReleaseFoundryPreferenceCalibrationError(
                "strategy_journal_binding_missing"
            )
        journal["preference_experiment"] = expected
        calibration._write_private_journal(path, journal)
    elif observed != expected:
        raise ReleaseFoundryPreferenceCalibrationError(
            "strategy_journal_binding_mismatch"
        )


def _journal_completed(
    journal: dict[str, Any],
    *,
    expected_ids: set[str],
) -> bool:
    try:
        _completed_terminal(
            journal,
            expected_ids=expected_ids,
            strategy="strategy",
        )
    except ReleaseFoundryPreferenceCalibrationError:
        return False
    return True


def _strategy_private_path(
    strategy: str,
    kind: str,
    *,
    experiment_label: str | None = None,
) -> Path:
    label = _private_experiment_label_suffix(experiment_label)
    return (
        calibration.PRIVATE_ROOT
        / (
            "a2_rf_exploratory_preference_"
            f"{strategy}{label}_{kind}.private.json"
        )
    )


def _private_experiment_label_suffix(value: str | None) -> str:
    if value is None:
        return ""
    if len(value) <= 24:
        return f"_{value}"
    return f"_exp-{stable_hash(value)[:12]}"


def _validate_experiment_label(value: str | None) -> str | None:
    if value is None:
        return None
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ReleaseFoundryPreferenceCalibrationError(
            "experiment_label_must_be_safe_slug"
        )
    return value


def _require_strategy_matrices(
    matrices: dict[str, list[dict[str, Any]]],
    *,
    strategies: tuple[str, ...] = STRATEGIES,
) -> None:
    if set(matrices) != set(strategies):
        raise ReleaseFoundryPreferenceCalibrationError("strategy_matrix_set_mismatch")
    lengths = {len(matrices[strategy]) for strategy in strategies}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) < 1:
        raise ReleaseFoundryPreferenceCalibrationError("strategy_matrix_size_mismatch")
    expected_test_ids: set[str] | None = None
    expected_source_hashes: set[str] | None = None
    for strategy in strategies:
        matrix = matrices[strategy]
        if any(not isinstance(item, dict) for item in matrix):
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_strategy_matrix_item_invalid"
            )
        test_ids = [str(item.get("variant_id", "")) for item in matrix]
        source_hashes = [
            str(item.get("source_variant_hash", "")) for item in matrix
        ]
        if any(not value for value in test_ids):
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_strategy_test_id_missing"
            )
        if any(not value for value in source_hashes):
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_strategy_source_hash_missing"
            )
        if len(test_ids) != len(set(test_ids)):
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_strategy_test_ids_not_unique"
            )
        if len(source_hashes) != len(set(source_hashes)):
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_strategy_source_hashes_not_unique"
            )
        if expected_test_ids is None:
            expected_test_ids = set(test_ids)
            expected_source_hashes = set(source_hashes)
            continue
        if set(test_ids) != expected_test_ids:
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_strategy_test_set_mismatch"
            )
        if set(source_hashes) != expected_source_hashes:
            raise ReleaseFoundryPreferenceCalibrationError(
                f"{strategy}_strategy_source_set_mismatch"
            )


def _assert_public_output_safe(
    payload: dict[str, Any],
    *,
    matrices: dict[str, list[dict[str, Any]]],
    journals: dict[str, dict[str, Any]],
) -> None:
    calibration._assert_public_summary_safe(payload)
    forbidden_keys = {
        "releasefoundry_test_id_hash",
        "server_test_result_hash",
        "run_receipt_hash",
        "score_receipts",
        "run_id",
        "dataset_id",
        "test_id",
        "variant_id",
        "fixture_ref",
        "candidate_run",
        "tool_calls",
        "final_response",
    }
    observed_keys = {
        str(key).lower() for key in calibration._walk_mapping_keys(payload)
    }
    unsafe_keys = sorted(forbidden_keys.intersection(observed_keys))
    if unsafe_keys:
        raise ReleaseFoundryPreferenceCalibrationError(
            "public_output_private_fields:" + ",".join(unsafe_keys)
        )
    serialized = json.dumps(payload, sort_keys=True)
    forbidden_values = []
    for strategy in matrices:
        for variant in matrices[strategy]:
            forbidden_values.extend(
                (
                    str(variant["variant_id"]),
                    str(variant["fixture_ref"]),
                    str(variant["prompt"]),
                    str(variant["candidate_run"]["final_response"]),
                )
            )
            for call in variant["candidate_run"]["tool_calls"]:
                args = call.get("args") if isinstance(call, dict) else None
                if not isinstance(args, dict):
                    continue
                forbidden_values.append(json.dumps(args, sort_keys=True))
                forbidden_values.extend(_private_string_values(args))
        for batch in journals[strategy].get("batches", []):
            if not isinstance(batch, dict):
                continue
            for key in ("run_id",):
                if batch.get(key) is not None:
                    forbidden_values.append(str(batch[key]))
    for value in forbidden_values:
        if len(value) >= 8 and value in serialized:
            raise ReleaseFoundryPreferenceCalibrationError(
                "public_output_private_value_leak"
            )
    if any(
        path in serialized
        for path in (
            str(ROOT),
            str(ROOT).replace("\\", "/"),
        )
    ):
        raise ReleaseFoundryPreferenceCalibrationError(
            "public_output_absolute_path_leak"
        )


def _private_string_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [
            item
            for child in value.values()
            for item in _private_string_values(child)
        ]
    if isinstance(value, list):
        return [
            item
            for child in value
            for item in _private_string_values(child)
        ]
    return [value] if isinstance(value, str) else []


if __name__ == "__main__":
    raise SystemExit(main())
