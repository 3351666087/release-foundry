from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import a2_releasefoundry_live_calibration as calibration  # noqa: E402
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue  # noqa: E402


DEFAULT_QUEUE = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_disagreement_review_queue.json"
)
DEFAULT_PRIVATE_JOURNAL_BASE = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_exploratory_disagreement_repeat_exact_ids.private.json"
)
DEFAULT_PRIVATE_RUN_SUMMARY_BASE = (
    calibration.PRIVATE_ROOT
    / "a2_releasefoundry_exploratory_disagreement_repeat_exact_ids_summary.private.json"
)
DEFAULT_PUBLIC_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_disagreement_repeat_stability.json"
)
REPEAT_SCHEMA_VERSION = "a2.releasefoundry_disagreement_repeat.v2"
DEFAULT_REPEAT_COUNT = 3


class DisagreementRepeatError(ValueError):
    pass


def build_repeat_matrix(
    queue: dict[str, Any],
    base_matrix: list[dict[str, Any]],
    *,
    repeat_count: int = DEFAULT_REPEAT_COUNT,
) -> list[dict[str, Any]]:
    _require_repeat_queue(queue, repeat_count=repeat_count)
    by_hash: dict[str, dict[str, Any]] = {}
    for variant in base_matrix:
        variant_hash = _variant_id_hash(str(variant["variant_id"]))
        if variant_hash in by_hash:
            raise DisagreementRepeatError("base_matrix_variant_hash_collision")
        by_hash[variant_hash] = variant

    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in queue["items"]:
        variant_hash = str(item["variant_id_hash"])
        variant = by_hash.get(variant_hash)
        if variant is None:
            raise DisagreementRepeatError("review_variant_not_found_in_matrix")
        selected.append((item, variant))

    repeats: list[dict[str, Any]] = []
    for repeat_index in range(1, repeat_count + 1):
        current_ids = []
        for item, variant in selected:
            repeated = dict(variant)
            repeated.update(
                {
                    "source_variant_hash": item["variant_id_hash"],
                    "review_item_id": item["review_item_id"],
                    "repeat_index": repeat_index,
                    "repeat_count": repeat_count,
                }
            )
            repeats.append(repeated)
            current_ids.append(str(repeated["variant_id"]))
        if len(current_ids) != len(set(current_ids)):
            raise DisagreementRepeatError("repeat_run_test_ids_not_unique")
    return repeats


def build_repeat_report(
    queue: dict[str, Any],
    repeat_matrix: list[dict[str, Any]],
    journals: dict[int, dict[str, Any]],
    *,
    repeat_count: int = DEFAULT_REPEAT_COUNT,
    source_queue_ref: str | Path = DEFAULT_QUEUE,
    private_journal_base_ref: str | Path = DEFAULT_PRIVATE_JOURNAL_BASE,
) -> dict[str, Any]:
    _require_repeat_queue(queue, repeat_count=repeat_count)
    outcomes: list[dict[str, Any]] = []
    completed_batches = 0
    http_events: list[dict[str, Any]] = []

    for repeat_index in range(1, repeat_count + 1):
        current_matrix = _matrix_for_repeat(repeat_matrix, repeat_index)
        by_variant = {
            str(item["variant_id"]): item for item in current_matrix
        }
        if len(by_variant) != len(current_matrix):
            raise DisagreementRepeatError("repeat_run_test_ids_not_unique")
        expected_matrix_ids = set(by_variant)
        journal = journals.get(repeat_index, {"batches": []})
        http_events.extend(_journal_http_events(journal))
        batches = [
            batch
            for batch in journal.get("batches", [])
            if isinstance(batch, dict) and batch.get("status") == "completed"
        ]
        if len(batches) > 1:
            raise DisagreementRepeatError("repeat_run_has_multiple_batches")
        for batch in batches:
            completed_batches += 1
            expected_ids = {
                str(value)
                for value in batch.get("variant_ids", [])
                if isinstance(value, str) and value
            }
            if expected_ids != expected_matrix_ids:
                raise DisagreementRepeatError("completed_batch_test_ids_mismatch")
            terminal = batch.get("terminal_response")
            if not calibration.server_grading_markers_complete(
                terminal,
                expected_ids,
            ):
                raise DisagreementRepeatError("completed_batch_grading_incomplete")
            batch_outcomes = calibration._terminal_outcomes(
                terminal,
                by_variant,
            )
            observed_ids = [str(item["variant_id"]) for item in batch_outcomes]
            if (
                len(observed_ids) != len(expected_ids)
                or set(observed_ids) != expected_ids
            ):
                raise DisagreementRepeatError("completed_batch_outcomes_mismatch")
            tests_by_id = _terminal_tests_by_id(terminal)
            for outcome in batch_outcomes:
                variant = by_variant[str(outcome["variant_id"])]
                test = tests_by_id[str(outcome["variant_id"])]
                outcomes.append(
                    {
                        **outcome,
                        "source_variant_hash": variant["source_variant_hash"],
                        "review_item_id": variant["review_item_id"],
                        "repeat_index": repeat_index,
                        "final_answer_grading_observed": (
                            _final_answer_grading_observed(test)
                        ),
                    }
                )

    outcome_keys = [
        (str(item["source_variant_hash"]), int(item["repeat_index"]))
        for item in outcomes
    ]
    if len(outcome_keys) != len(set(outcome_keys)):
        raise DisagreementRepeatError("duplicate_repeat_outcomes")

    outcomes_by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        outcomes_by_hash[str(outcome["source_variant_hash"])].append(outcome)

    report_items = []
    for item in queue["items"]:
        variant_hash = str(item["variant_id_hash"])
        rows = sorted(
            outcomes_by_hash.get(variant_hash, []),
            key=lambda row: int(row["repeat_index"]),
        )
        disagreement_count = sum(
            row["passed"] != item["local_expected_passed"] for row in rows
        )
        complete_signal = (
            len(rows) == repeat_count
            and all(row["final_answer_grading_observed"] for row in rows)
        )
        if len(rows) < repeat_count:
            classification = "incomplete"
        elif not complete_signal:
            classification = "incomplete_grading_signal"
        elif disagreement_count == repeat_count:
            classification = "persistent_disagreement"
        elif disagreement_count == 0:
            classification = "persistent_agreement"
        else:
            classification = "stochastic_boundary"
        scores = [
            float(row["score"])
            for row in rows
            if _finite_number(row.get("score"))
        ]
        pass_values = [bool(row["passed"]) for row in rows]
        report_items.append(
            {
                "review_item_id": item["review_item_id"],
                "variant_id_hash": variant_hash,
                "case_id": item["case_id"],
                "channel": item["channel"],
                "prompt_variant": item["prompt_variant"],
                "expected_variant": item["expected_variant"],
                "local_expected_passed": item["local_expected_passed"],
                "original_releasefoundry_passed": item["releasefoundry_passed"],
                "original_releasefoundry_score": item["releasefoundry_score"],
                "repeat_count_required": repeat_count,
                "repeat_count_observed": len(rows),
                "final_answer_grading_complete": complete_signal,
                "releasefoundry_pass_count": sum(pass_values),
                "releasefoundry_fail_count": len(rows) - sum(pass_values),
                "releasefoundry_pass_rate": _ratio(sum(pass_values), len(rows)),
                "local_releasefoundry_disagreement_count": disagreement_count,
                "classification": classification,
                "all_repeat_pass_statuses_equal": (
                    len(rows) == repeat_count and len(set(pass_values)) == 1
                ),
                "score_statistics": _score_statistics(scores),
                "llm_verdicts": dict(
                    sorted(
                        Counter(
                            verdict
                            for row in rows
                            for verdict in row.get("llm_verdicts", [])
                        ).items()
                    )
                ),
                "repeat_outcomes": [
                    {
                        "repeat_index": row["repeat_index"],
                        "releasefoundry_passed": row["passed"],
                        "releasefoundry_score": row["score"],
                        "failed_action_count": row["failed_action_count"],
                        "llm_verdicts": row["llm_verdicts"],
                        "final_answer_grading_observed": row[
                            "final_answer_grading_observed"
                        ],
                    }
                    for row in rows
                ],
                "human_review_state": "pending",
                "training_eligible": False,
                "c3_authority": False,
                "release_authority": False,
            }
        )

    classifications = Counter(item["classification"] for item in report_items)
    repeat_indices = Counter(
        int(outcome["repeat_index"]) for outcome in outcomes
    )
    create_events = [
        event for event in http_events if event.get("operation") == "create_run"
    ]
    planned_evaluations = len(queue["items"]) * repeat_count
    final_answer_graded = sum(
        bool(row["final_answer_grading_observed"]) for row in outcomes
    )
    all_completed = (
        len(outcomes) == planned_evaluations
        and final_answer_graded == planned_evaluations
    )
    report = {
        "schema_version": REPEAT_SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "source_queue_ref": calibration._display_path(source_queue_ref),
        "source_queue_sha256": review_queue._sha256_json(queue),
        "private_journal_refs": [
            calibration._display_path(
                _repeat_path(
                    calibration._resolve(private_journal_base_ref),
                    repeat_index,
                )
            )
            for repeat_index in range(1, repeat_count + 1)
        ],
        "repeat_status": "completed" if all_completed else "partial",
        "human_review_required": True,
        "human_reviewed": False,
        "review_status": "pending_human_review",
        "acceptance_authority": False,
        "training_eligible": False,
        "human_gold": False,
        "release_authority": False,
        "c3_authority": False,
        "c3_transition_allowed": False,
        "repeat_plan": {
            "base_review_items": len(queue["items"]),
            "repeat_count_per_item": repeat_count,
            "planned_evaluations": planned_evaluations,
            "observed_evaluations": len(outcomes),
            "completed_batches": completed_batches,
            "expected_create_runs": repeat_count,
            "dataset_bound_test_ids_preserved_across_runs": True,
            "observed_by_repeat_index": {
                str(index): repeat_indices.get(index, 0)
                for index in range(1, repeat_count + 1)
            },
        },
        "create_run_safety": {
            "attempts": len(create_events),
            "successful": sum(
                event.get("status") == "ok" for event in create_events
            ),
            "errors": sum(
                event.get("status") == "error" for event in create_events
            ),
            "retries": sum(bool(event.get("retry")) for event in create_events),
            "automatic_retry_enabled": False,
            "one_repeat_index_per_completed_run": completed_batches <= repeat_count,
        },
        "server_grading": {
            "per_test_marker_required": True,
            "tests_with_confirmed_marker": len(outcomes),
            "tests_with_final_answer_grading": final_answer_graded,
            "tests_with_numeric_score": sum(
                _finite_number(row.get("score")) for row in outcomes
            ),
            "aggregate_marker_alone_accepted": False,
        },
        "http_calls": _http_summary(http_events),
        "outcome_summary": {
            "releasefoundry_passed": sum(bool(row["passed"]) for row in outcomes),
            "releasefoundry_failed": sum(not bool(row["passed"]) for row in outcomes),
            "local_releasefoundry_disagreements": sum(
                row["passed"] != row["expected_passed"] for row in outcomes
            ),
            "classifications": dict(sorted(classifications.items())),
            "score_statistics": _score_statistics(
                [
                    float(row["score"])
                    for row in outcomes
                    if _finite_number(row.get("score"))
                ]
            ),
        },
        "items": report_items,
        "public_safety": {
            "contains_api_key": False,
            "contains_api_key_hash": False,
            "contains_raw_payload": False,
            "contains_raw_candidate_response": False,
            "contains_run_id": False,
            "contains_dataset_id": False,
            "contains_raw_variant_id": False,
        },
        "notes": [
            "Each repeat index is submitted in a separate ReleaseFoundry create_run.",
            "Dataset-bound test IDs are preserved privately across runs so final-answer grading remains attached.",
            "Missing final-answer grading is reported as incomplete_grading_signal, never as a pass.",
            "The experiment still uses text projections rather than native media bytes.",
            "Repeated ReleaseFoundry outputs measure grader stability; they are not human gold labels.",
            "No result may enter RM, DPO, action-value, C3, or release evidence before governed human adjudication.",
        ],
    }
    calibration._assert_public_summary_safe(report)
    return report


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[int], Any] | None = None,
    environ: dict[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repeat exploratory ReleaseFoundry/local disagreements in independent paid "
            "runs while preserving dataset-bound test IDs."
        )
    )
    parser.add_argument("--repeat-count", type=int, default=DEFAULT_REPEAT_COUNT)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--poll-timeout", type=int, default=600)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--max-retries", type=int, default=2)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-mutate", action="store_true")
    parser.add_argument("--allow-unverified-exploration", action="store_true")
    parser.add_argument(
        "--queue",
        default=calibration._display_path(DEFAULT_QUEUE),
    )
    parser.add_argument(
        "--private-journal-base",
        default=calibration._display_path(DEFAULT_PRIVATE_JOURNAL_BASE),
    )
    parser.add_argument(
        "--private-run-summary-base",
        default=calibration._display_path(DEFAULT_PRIVATE_RUN_SUMMARY_BASE),
    )
    parser.add_argument(
        "--output",
        default=calibration._display_path(DEFAULT_PUBLIC_OUTPUT),
    )
    parser.add_argument(
        "--mapping-private-review",
        default=calibration._display_path(
            calibration.DEFAULT_PRIVATE_MAPPING_REVIEW
        ),
    )
    parser.add_argument(
        "--mapping-receipt",
        default=calibration._display_path(calibration.DEFAULT_MAPPING_RECEIPT),
    )
    args = parser.parse_args(argv)

    if args.repeat_count < DEFAULT_REPEAT_COUNT:
        parser.error(
            f"--repeat-count must be at least {DEFAULT_REPEAT_COUNT}"
        )
    if args.execute and not args.allow_mutate:
        parser.error("--execute requires --allow-mutate")
    if args.execute and not args.allow_unverified_exploration:
        parser.error("--execute requires --allow-unverified-exploration")
    if not args.execute and args.allow_mutate:
        parser.error("--allow-mutate requires --execute")
    if not args.execute and args.allow_unverified_exploration:
        parser.error("--allow-unverified-exploration requires --execute")

    queue_path = calibration._resolve(args.queue)
    journal_base = calibration._resolve(args.private_journal_base)
    summary_base = calibration._resolve(args.private_run_summary_base)
    output_path = calibration._resolve(args.output)
    calibration._require_private_ref(journal_base)
    calibration._require_private_ref(summary_base)

    queue = calibration._read_json(queue_path)
    repeat_matrix = build_repeat_matrix(
        queue,
        calibration.build_matrix(),
        repeat_count=args.repeat_count,
    )
    journals = {}
    for repeat_index in range(1, args.repeat_count + 1):
        journal_path = _repeat_path(journal_base, repeat_index)
        calibration._require_private_ref(journal_path)
        current_matrix = _matrix_for_repeat(repeat_matrix, repeat_index)
        _bind_repeat_journal(
            journal_path,
            queue=queue,
            repeat_matrix=current_matrix,
            repeat_count=args.repeat_count,
            repeat_index=repeat_index,
        )
        journals[repeat_index] = calibration._load_journal(journal_path)

    result = 0
    if args.execute:
        for repeat_index in range(1, args.repeat_count + 1):
            current_matrix = _matrix_for_repeat(repeat_matrix, repeat_index)
            journal_path = _repeat_path(journal_base, repeat_index)
            run_summary_path = _repeat_path(summary_base, repeat_index)
            calibration._require_private_ref(run_summary_path)
            journal = calibration._load_journal(journal_path)
            if _repeat_run_completed(journal, current_matrix):
                continue
            _prepare_incomplete_repeat_for_resume(
                journal_path,
                journal,
                current_matrix,
            )
            calibration_args = [
                "--batch-size",
                str(len(current_matrix)),
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
                "--private-journal",
                str(journal_path),
                "--public-output",
                str(run_summary_path),
                "--mapping-private-review",
                str(calibration._resolve(args.mapping_private_review)),
                "--mapping-receipt",
                str(calibration._resolve(args.mapping_receipt)),
                "--execute",
                "--allow-mutate",
                "--allow-unverified-exploration",
            ]
            result = calibration.main(
                calibration_args,
                client_factory=client_factory,
                environ=environ,
                matrix_factory=lambda matrix=current_matrix: matrix,
            )
            journals[repeat_index] = calibration._load_journal(journal_path)
            if result != 0:
                break

    journals = {
        repeat_index: calibration._load_journal(
            _repeat_path(journal_base, repeat_index)
        )
        for repeat_index in range(1, args.repeat_count + 1)
    }
    report = build_repeat_report(
        queue,
        repeat_matrix,
        journals,
        repeat_count=args.repeat_count,
        source_queue_ref=queue_path,
        private_journal_base_ref=journal_base,
    )
    calibration._write_public_summary(output_path, report)
    print(
        "ReleaseFoundry disagreement repeat report written: "
        f"status={report['repeat_status']} "
        f"observed={report['repeat_plan']['observed_evaluations']} "
        f"final_answer_graded="
        f"{report['server_grading']['tests_with_final_answer_grading']} "
        f"planned={report['repeat_plan']['planned_evaluations']} "
        f"output={calibration._display_path(output_path)}"
    )
    if args.execute and report["repeat_status"] != "completed":
        return result or 2
    return result


def _bind_repeat_journal(
    path: Path,
    *,
    queue: dict[str, Any],
    repeat_matrix: list[dict[str, Any]],
    repeat_count: int,
    repeat_index: int,
) -> None:
    journal = calibration._load_journal(path)
    calibration._bind_journal_to_evidence_lane(
        journal,
        calibration.EXPLORATORY_EVIDENCE_LANE,
    )
    binding = {
        "schema_version": REPEAT_SCHEMA_VERSION,
        "source_queue_sha256": review_queue._sha256_json(queue),
        "repeat_count": repeat_count,
        "repeat_index": repeat_index,
        "base_review_items": len(queue["items"]),
        "planned_evaluations": len(repeat_matrix),
        "dataset_bound_test_ids_preserved": True,
        "repeat_matrix_sha256": review_queue._sha256_json(
            [
                {
                    "variant_id": item["variant_id"],
                    "source_variant_hash": item["source_variant_hash"],
                }
                for item in repeat_matrix
            ]
        ),
    }
    existing = journal.get("repeat_experiment")
    if existing is not None and existing != binding:
        raise DisagreementRepeatError("repeat_journal_binding_mismatch")
    journal["repeat_experiment"] = binding
    calibration._write_private_journal(path, journal)


def _require_repeat_queue(
    queue: dict[str, Any],
    *,
    repeat_count: int,
) -> None:
    if (
        queue.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise DisagreementRepeatError("queue_not_exploratory")
    if queue.get("review_status") != "pending_human_review":
        raise DisagreementRepeatError("queue_not_pending_human_review")
    for field in (
        "acceptance_authority",
        "training_eligible",
        "human_gold",
        "release_authority",
        "c3_authority",
    ):
        if queue.get(field) is not False:
            raise DisagreementRepeatError(f"queue_{field}_must_be_false")
    if queue.get("repeat_experiment_eligible") is not True:
        raise DisagreementRepeatError("queue_not_repeat_eligible")
    items = queue.get("items")
    if not isinstance(items, list) or not items:
        raise DisagreementRepeatError("queue_items_missing")
    if queue.get("review_item_count") != len(items):
        raise DisagreementRepeatError("queue_item_count_mismatch")
    hashes = [str(item.get("variant_id_hash", "")) for item in items]
    if any(not value.startswith("sha256:") for value in hashes):
        raise DisagreementRepeatError("queue_variant_hash_invalid")
    if len(hashes) != len(set(hashes)):
        raise DisagreementRepeatError("queue_variant_hashes_not_unique")
    for item in items:
        if item.get("human_review_state") != "pending":
            raise DisagreementRepeatError("queue_item_not_pending")
        if item.get("training_eligible") is not False:
            raise DisagreementRepeatError(
                "queue_item_training_eligible_must_be_false"
            )
        if item.get("repeat_requested") is not True:
            raise DisagreementRepeatError("queue_item_repeat_not_requested")
        minimum = item.get("minimum_repeat_count")
        if not isinstance(minimum, int) or minimum < DEFAULT_REPEAT_COUNT:
            raise DisagreementRepeatError("queue_item_minimum_repeat_invalid")
        if repeat_count < minimum:
            raise DisagreementRepeatError("repeat_count_below_queue_minimum")


def _matrix_for_repeat(
    repeat_matrix: list[dict[str, Any]],
    repeat_index: int,
) -> list[dict[str, Any]]:
    return [
        item
        for item in repeat_matrix
        if item.get("repeat_index") == repeat_index
    ]


def _repeat_run_completed(
    journal: dict[str, Any],
    repeat_matrix: list[dict[str, Any]],
) -> bool:
    expected_ids = {str(item["variant_id"]) for item in repeat_matrix}
    completed = [
        batch
        for batch in journal.get("batches", [])
        if isinstance(batch, dict) and batch.get("status") == "completed"
    ]
    if len(completed) != 1:
        return False
    batch = completed[0]
    observed_ids = {
        str(value)
        for value in batch.get("variant_ids", [])
        if isinstance(value, str) and value
    }
    return observed_ids == expected_ids and calibration.server_grading_complete(
        batch.get("terminal_response"),
        expected_ids,
    )


def _prepare_incomplete_repeat_for_resume(
    path: Path,
    journal: dict[str, Any],
    repeat_matrix: list[dict[str, Any]],
) -> bool:
    expected_ids = {str(item["variant_id"]) for item in repeat_matrix}
    completed = [
        batch
        for batch in journal.get("batches", [])
        if isinstance(batch, dict) and batch.get("status") == "completed"
    ]
    if len(completed) != 1:
        return False
    batch = completed[0]
    observed_ids = {
        str(value)
        for value in batch.get("variant_ids", [])
        if isinstance(value, str) and value
    }
    if observed_ids != expected_ids:
        return False
    if calibration.server_grading_complete(
        batch.get("terminal_response"),
        expected_ids,
    ):
        return False
    if batch.get("run_id") is None:
        raise DisagreementRepeatError("incomplete_repeat_run_id_missing")
    batch["status"] = "submitted"
    batch["last_poll_outcome"] = "incomplete_final_answer_grading"
    batch.pop("completed_at", None)
    calibration._write_private_journal(path, journal)
    return True


def _terminal_tests_by_id(terminal: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(terminal, dict):
        return {}
    run = (
        terminal.get("run")
        if isinstance(terminal.get("run"), dict)
        else terminal
    )
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    tests = result.get("tests") if isinstance(result.get("tests"), list) else []
    return {
        str(test["test_id"]): test
        for test in tests
        if isinstance(test, dict) and test.get("test_id")
    }


def _final_answer_grading_observed(test: dict[str, Any]) -> bool:
    return calibration.has_final_answer_grading_marker(test)


def _variant_id_hash(variant_id: str) -> str:
    return review_queue._sha256_text(
        f"a2:releasefoundry-exploratory-variant:v1:{variant_id}"
    )


def _repeat_path(base: Path, repeat_index: int) -> Path:
    suffix = ".private.json"
    if base.name.endswith(suffix):
        stem = base.name[: -len(suffix)]
        name = f"{stem}.r{repeat_index:02d}{suffix}"
    else:
        name = f"{base.stem}.r{repeat_index:02d}{base.suffix}"
    return base.with_name(name)


def _journal_http_events(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event
        for event in journal.get("preflight_http_events", [])
        if isinstance(event, dict)
    ] + [
        event
        for batch in journal.get("batches", [])
        if isinstance(batch, dict)
        for event in batch.get("http_events", [])
        if isinstance(event, dict)
    ]


def _http_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(event.get("status", "")) for event in events)
    operations = Counter(str(event.get("operation", "")) for event in events)
    errors = Counter(
        str(event.get("error_type", "unknown"))
        for event in events
        if event.get("status") == "error"
    )
    return {
        "total": len(events),
        "ok": statuses.get("ok", 0),
        "error": statuses.get("error", 0),
        "retries": sum(bool(event.get("retry")) for event in events),
        "by_operation": dict(sorted(operations.items())),
        "error_types": dict(sorted(errors.items())),
    }


def _score_statistics(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "population_std": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 2),
        "population_std": round(statistics.pstdev(values), 2),
        "minimum": round(min(values), 2),
        "maximum": round(max(values), 2),
    }


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


if __name__ == "__main__":
    raise SystemExit(main())
