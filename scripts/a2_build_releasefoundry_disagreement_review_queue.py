from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import a2_releasefoundry_live_calibration as calibration  # noqa: E402


DEFAULT_PRIVATE_JOURNAL = calibration.DEFAULT_EXPLORATORY_PRIVATE_JOURNAL
DEFAULT_PUBLIC_RECEIPT = calibration.DEFAULT_EXPLORATORY_PUBLIC_OUTPUT
DEFAULT_PUBLIC_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_disagreement_review_queue.json"
)


class DisagreementQueueError(ValueError):
    pass


def build_review_queue(
    journal: dict[str, Any],
    public_receipt: dict[str, Any],
    matrix: list[dict[str, Any]],
    *,
    source_receipt_ref: str | Path = DEFAULT_PUBLIC_RECEIPT,
) -> dict[str, Any]:
    _require_exploratory_boundary(journal, public_receipt)
    by_variant = {str(item["variant_id"]): item for item in matrix}
    if len(by_variant) != len(matrix):
        raise DisagreementQueueError("matrix_variant_ids_not_unique")

    outcomes: list[dict[str, Any]] = []
    observed_variant_ids: list[str] = []
    for batch in journal.get("batches", []):
        if not isinstance(batch, dict) or batch.get("status") != "completed":
            raise DisagreementQueueError("journal_contains_noncompleted_batch")
        expected_ids = {
            str(value)
            for value in batch.get("variant_ids", [])
            if isinstance(value, str) and value
        }
        terminal = batch.get("terminal_response")
        _require_per_test_server_grading(terminal, expected_ids)
        if not calibration.server_grading_complete(terminal, expected_ids):
            raise DisagreementQueueError("batch_server_grading_incomplete")
        batch_outcomes = calibration._terminal_outcomes(terminal, by_variant)
        batch_ids = [str(item["variant_id"]) for item in batch_outcomes]
        if len(batch_ids) != len(expected_ids) or set(batch_ids) != expected_ids:
            raise DisagreementQueueError("batch_terminal_outcomes_mismatch")
        observed_variant_ids.extend(batch_ids)
        outcomes.extend(batch_outcomes)

    if len(observed_variant_ids) != len(set(observed_variant_ids)):
        raise DisagreementQueueError("duplicate_terminal_outcomes")

    _require_public_receipt_matches(public_receipt, outcomes, journal)
    disagreements = [
        row
        for row in outcomes
        if row.get("passed") != row.get("expected_passed")
    ]
    items = [_review_item(row) for row in disagreements]
    items.sort(key=lambda item: item["variant_id_hash"])

    by_channel = Counter(str(item["channel"]) for item in items)
    by_prompt_variant = Counter(str(item["prompt_variant"]) for item in items)
    by_case = Counter(str(item["case_id"]) for item in items)
    queue = {
        "schema_version": "a2.releasefoundry_disagreement_review_queue.v1",
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "source_receipt_ref": calibration._display_path(source_receipt_ref),
        "source_receipt_sha256": _sha256_json(public_receipt),
        "review_status": "pending_human_review",
        "human_review_required": True,
        "human_reviewed": False,
        "acceptance_authority": False,
        "training_eligible": False,
        "human_gold": False,
        "release_authority": False,
        "c3_authority": False,
        "repeat_experiment_eligible": True,
        "review_item_count": len(items),
        "coverage": {
            "by_case": dict(sorted(by_case.items())),
            "by_channel": dict(sorted(by_channel.items())),
            "by_prompt_variant": dict(sorted(by_prompt_variant.items())),
        },
        "items": items,
        "public_safety": {
            "contains_api_key": False,
            "contains_raw_payload": False,
            "contains_raw_candidate_response": False,
            "contains_run_id": False,
            "contains_dataset_id": False,
            "contains_raw_variant_id": False,
        },
        "notes": [
            "Every item is a machine-observed ReleaseFoundry/local-expectation disagreement.",
            "The queue is for repeated experiments and human adjudication only.",
            "No item may enter RM, DPO, action-value, release, or C3 evidence before governed review.",
            "The source experiment used text projections and does not prove native multimodal behavior.",
        ],
    }
    calibration._assert_public_summary_safe(queue)
    return queue


def _require_per_test_server_grading(
    terminal: Any,
    expected_test_ids: set[str],
) -> None:
    if not isinstance(terminal, dict):
        raise DisagreementQueueError("batch_server_grading_incomplete")
    run = (
        terminal.get("run")
        if isinstance(terminal.get("run"), dict)
        else terminal
    )
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    tests = result.get("tests") if isinstance(result.get("tests"), list) else []
    tests_by_id = {
        str(test.get("test_id")): test
        for test in tests
        if isinstance(test, dict) and test.get("test_id")
    }
    for test_id in expected_test_ids:
        test = tests_by_id.get(test_id)
        if not isinstance(test, dict) or not _has_server_grading_marker(test):
            raise DisagreementQueueError("test_server_grading_marker_missing")


def _has_server_grading_marker(test: dict[str, Any]) -> bool:
    return calibration.has_server_grading_marker(test)


def _review_item(row: dict[str, Any]) -> dict[str, Any]:
    variant_id = str(row["variant_id"])
    variant_id_hash = _sha256_text(
        f"a2:releasefoundry-exploratory-variant:v1:{variant_id}"
    )
    item = {
        "review_item_id": _sha256_text(
            "a2:releasefoundry-disagreement-review:v1:"
            f"{variant_id_hash}:{row.get('expected_passed')}:{row.get('passed')}"
        ),
        "variant_id_hash": variant_id_hash,
        "case_id": row.get("case_id"),
        "channel": row.get("channel"),
        "prompt_variant": row.get("prompt_variant"),
        "expected_variant": row.get("expected_variant"),
        "local_expected_passed": row.get("expected_passed"),
        "releasefoundry_passed": row.get("passed"),
        "releasefoundry_score": row.get("score"),
        "failure_cluster": row.get("failure_cluster"),
        "issue_cluster": row.get("issue_cluster"),
        "failed_action_count": row.get("failed_action_count"),
        "llm_verdicts": list(row.get("llm_verdicts", [])),
        "human_review_state": "pending",
        "human_decision": None,
        "training_eligible": False,
        "c3_authority": False,
        "release_authority": False,
        "repeat_requested": True,
        "minimum_repeat_count": 3,
    }
    return item


def _require_exploratory_boundary(
    journal: dict[str, Any],
    public_receipt: dict[str, Any],
) -> None:
    if journal.get("evidence_lane") != calibration.EXPLORATORY_EVIDENCE_LANE:
        raise DisagreementQueueError("journal_not_exploratory")
    if journal.get("preflight_status") != "verified_for_exploration_only":
        raise DisagreementQueueError("journal_preflight_not_exploration_only")
    binding = journal.get("dataset_binding")
    if not isinstance(binding, dict):
        raise DisagreementQueueError("journal_dataset_binding_missing")
    if binding.get("evidence_lane") != calibration.EXPLORATORY_EVIDENCE_LANE:
        raise DisagreementQueueError("journal_binding_lane_mismatch")

    for field in (
        "acceptance_authority",
        "training_eligible",
        "release_authority",
        "c3_transition_allowed",
    ):
        if binding.get(field) is not False:
            raise DisagreementQueueError(f"journal_binding_{field}_must_be_false")

    if public_receipt.get("evidence_lane") != calibration.EXPLORATORY_EVIDENCE_LANE:
        raise DisagreementQueueError("public_receipt_not_exploratory")
    for field in (
        "acceptance_authority",
        "training_eligible",
        "human_gold",
        "release_authority",
        "c3_transition_allowed",
    ):
        if public_receipt.get(field) is not False:
            raise DisagreementQueueError(f"public_receipt_{field}_must_be_false")
    if public_receipt.get("human_review_required") is not True:
        raise DisagreementQueueError("public_receipt_human_review_required")


def _require_public_receipt_matches(
    public_receipt: dict[str, Any],
    outcomes: list[dict[str, Any]],
    journal: dict[str, Any],
) -> None:
    expected = {
        "graded_evaluations": len(outcomes),
        "successful_evaluations": sum(1 for row in outcomes if row.get("passed")),
        "failed_evaluations": sum(1 for row in outcomes if not row.get("passed")),
    }
    for field, value in expected.items():
        if public_receipt.get(field) != value:
            raise DisagreementQueueError(f"public_receipt_{field}_mismatch")

    expected_disagreements = sum(
        1 for row in outcomes if row.get("passed") != row.get("expected_passed")
    )
    receipt_disagreements = sum(
        int(case.get("disagreement_count", 0))
        for case in public_receipt.get("by_case", {}).values()
        if isinstance(case, dict)
    )
    if receipt_disagreements != expected_disagreements:
        raise DisagreementQueueError("public_receipt_disagreement_count_mismatch")

    completed_batches = sum(
        1
        for batch in journal.get("batches", [])
        if isinstance(batch, dict) and batch.get("status") == "completed"
    )
    create_calls = (
        public_receipt.get("http_calls", {})
        .get("by_operation", {})
        .get("create_run")
    )
    if create_calls != completed_batches:
        raise DisagreementQueueError("public_receipt_create_run_count_mismatch")
    if public_receipt.get("pending_batch_statuses") != {}:
        raise DisagreementQueueError("public_receipt_has_pending_batches")


def _sha256_json(value: Any) -> str:
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return _sha256_text(serialized)


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a redacted, non-training human-review queue from completed "
            "exploratory ReleaseFoundry/local expectation disagreements."
        )
    )
    parser.add_argument(
        "--private-journal",
        default=calibration._display_path(DEFAULT_PRIVATE_JOURNAL),
    )
    parser.add_argument(
        "--public-receipt",
        default=calibration._display_path(DEFAULT_PUBLIC_RECEIPT),
    )
    parser.add_argument(
        "--output",
        default=calibration._display_path(DEFAULT_PUBLIC_OUTPUT),
    )
    args = parser.parse_args(argv)

    private_journal_path = calibration._resolve(args.private_journal)
    public_receipt_path = calibration._resolve(args.public_receipt)
    output_path = calibration._resolve(args.output)
    calibration._require_private_ref(private_journal_path)

    queue = build_review_queue(
        calibration._read_json(private_journal_path),
        calibration._read_json(public_receipt_path),
        calibration.build_matrix(),
        source_receipt_ref=public_receipt_path,
    )
    calibration._write_public_summary(output_path, queue)
    print(
        "ReleaseFoundry disagreement review queue written: "
        f"items={queue['review_item_count']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
