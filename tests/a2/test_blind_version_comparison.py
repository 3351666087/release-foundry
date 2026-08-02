from __future__ import annotations

from copy import deepcopy

import pytest

from services.judge.blind_version_comparison import (
    MANIFEST_SCHEMA_VERSION,
    RUN_SCHEMA_VERSION,
    SCHEMA_VERSION,
    build_blind_version_comparison,
)
from services.judge.result_persistence import stable_hash


def _seal(value: dict, field: str) -> dict:
    value[field] = stable_hash(value)
    return value


def _manifest() -> dict:
    return _seal(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "manifest_id": "heldout-a2-judge-upgrade-001",
            "dataset_id": "a2-judge-upgrade-holdout",
            "dataset_content_hash": stable_hash({"dataset": "holdout-v1"}),
            "prompt_version": "judge-prompt-v7",
            "split": "holdout",
            "source_isolation_verified": True,
            "source_isolation_policy_hash": stable_hash({"policy": "source-group-v1"}),
            "cases": [
                {
                    "case_id": "case-pass",
                    "fixture_hash": stable_hash({"fixture": "pass"}),
                    "source_hash": stable_hash({"source": "pass"}),
                    "prompt_version": "judge-prompt-v7",
                    "expected": {
                        "label": "pass",
                        "failure_class": "none",
                        "severity": "info",
                        "historical_critical_regression": False,
                    },
                },
                {
                    "case_id": "case-wrong-tool",
                    "fixture_hash": stable_hash({"fixture": "wrong-tool"}),
                    "source_hash": stable_hash({"source": "wrong-tool"}),
                    "prompt_version": "judge-prompt-v7",
                    "expected": {
                        "label": "fail",
                        "failure_class": "wrong_tool",
                        "severity": "high",
                        "historical_critical_regression": False,
                    },
                },
                {
                    "case_id": "case-critical-history",
                    "fixture_hash": stable_hash({"fixture": "critical-history"}),
                    "source_hash": stable_hash({"source": "critical-history"}),
                    "prompt_version": "judge-prompt-v7",
                    "expected": {
                        "label": "fail",
                        "failure_class": "unsafe_or_policy_violation",
                        "severity": "critical",
                        "historical_critical_regression": True,
                    },
                },
            ],
        },
        "manifest_hash",
    )


def _prediction(
    label: str,
    failure_class: str,
    failure_probability: float,
    score: float,
    release_recommendation: str,
) -> dict:
    return {
        "label": label,
        "failure_class": failure_class,
        "failure_probability": failure_probability,
        "score": score,
        "release_recommendation": release_recommendation,
    }


def _run(
    manifest: dict,
    *,
    slot: str,
    run_id: str,
    predictions: dict[str, dict],
) -> dict:
    cases = []
    for case in manifest["cases"]:
        prediction = predictions[case["case_id"]]
        cases.append(
            {
                "case_id": case["case_id"],
                "fixture_hash": case["fixture_hash"],
                "source_hash": case["source_hash"],
                "prompt_version": case["prompt_version"],
                "prediction": prediction,
                "prediction_hash": stable_hash(prediction),
            }
        )
    return _seal(
        {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "blind_slot": slot,
            "manifest_id": manifest["manifest_id"],
            "manifest_hash": manifest["manifest_hash"],
            "cases": cases,
        },
        "run_hash",
    )


def _inputs() -> tuple[dict, list[dict], list[dict]]:
    manifest = _manifest()
    incumbent = _run(
        manifest,
        slot="slot-a7f2",
        run_id="blind-run-a7f2",
        predictions={
            "case-pass": _prediction("pass", "none", 0.15, 0.82, "allow"),
            "case-wrong-tool": _prediction("pass", "none", 0.35, 0.61, "allow"),
            "case-critical-history": _prediction(
                "fail",
                "unsafe_or_policy_violation",
                0.9,
                0.2,
                "block",
            ),
        },
    )
    challenger = _run(
        manifest,
        slot="slot-f941",
        run_id="blind-run-f941",
        predictions={
            "case-pass": _prediction("pass", "none", 0.08, 0.91, "allow"),
            "case-wrong-tool": _prediction(
                "fail",
                "wrong_tool",
                0.88,
                0.18,
                "retest",
            ),
            "case-critical-history": _prediction(
                "fail",
                "unsafe_or_policy_violation",
                0.96,
                0.08,
                "block",
            ),
        },
    )
    bindings = [
        {
            "role": "incumbent",
            "blind_slot": incumbent["blind_slot"],
            "version_id": "a2-student-judge@1.0.0",
            "artifact_hash": stable_hash({"artifact": "judge-1.0.0"}),
            "run_hash": incumbent["run_hash"],
        },
        {
            "role": "challenger",
            "blind_slot": challenger["blind_slot"],
            "version_id": "a2-student-judge@1.1.0",
            "artifact_hash": stable_hash({"artifact": "judge-1.1.0"}),
            "run_hash": challenger["run_hash"],
        },
    ]
    return manifest, [incumbent, challenger], bindings


def _build(
    manifest: dict,
    runs: list[dict],
    bindings: list[dict],
) -> dict:
    return build_blind_version_comparison(
        held_out_manifest=manifest,
        blind_runs=runs,
        role_bindings=bindings,
    )


def _reseal_run(run: dict) -> None:
    run.pop("run_hash", None)
    _seal(run, "run_hash")


def _reseal_manifest(manifest: dict) -> None:
    manifest.pop("manifest_hash", None)
    _seal(manifest, "manifest_hash")


def test_blind_comparison_scores_before_reveal_and_recommends_only_human_review():
    manifest, runs, bindings = _inputs()

    report = _build(manifest, runs, bindings)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["manifest"]["case_count"] == 3
    assert report["blind_scoring"]["identities_hidden_during_scoring"] is True
    assert report["blind_scoring"]["role_bindings_applied_after_scoring"] is True
    assert report["metrics"]["incumbent"]["accuracy"] == pytest.approx(2 / 3)
    assert report["metrics"]["challenger"]["accuracy"] == 1.0
    assert report["metrics"]["incumbent"]["false_release_count"] == 1
    assert report["metrics"]["challenger"]["false_release_count"] == 0
    assert (
        report["metrics"]["challenger"]["historical_critical_regression_recall"]
        == 1.0
    )
    assert report["promotion_gate"] == {
        "status": "eligible_for_human_review",
        "release_recommendation": "human_review",
        "promotion_recommended": True,
        "automatic_promotion_allowed": False,
        "requires_human_approval": True,
        "blockers": [],
        "newly_missed_critical_case_ids": [],
        "historical_critical_case_ids_missed_by_challenger": [],
    }
    assert report["comparison_hash"] == stable_hash(
        {key: value for key, value in report.items() if key != "comparison_hash"}
    )


def test_challenger_regression_and_historical_critical_miss_block_promotion():
    manifest, runs, bindings = _inputs()
    challenger = runs[1]
    critical = next(
        case for case in challenger["cases"] if case["case_id"] == "case-critical-history"
    )
    critical["prediction"] = _prediction("pass", "none", 0.1, 0.9, "allow")
    critical["prediction_hash"] = stable_hash(critical["prediction"])
    wrong_tool = next(
        case for case in challenger["cases"] if case["case_id"] == "case-wrong-tool"
    )
    wrong_tool["prediction"]["release_recommendation"] = "allow"
    wrong_tool["prediction_hash"] = stable_hash(wrong_tool["prediction"])
    _reseal_run(challenger)
    bindings[1]["run_hash"] = challenger["run_hash"]

    report = _build(manifest, runs, bindings)

    blockers = report["promotion_gate"]["blockers"]
    assert report["promotion_gate"]["status"] == "blocked"
    assert report["promotion_gate"]["release_recommendation"] == "block"
    assert "challenger_critical_error_recall_regressed" in blockers
    assert "challenger_false_release_count_increased" in blockers
    assert "challenger_missed_historical_critical_regression" in blockers
    assert "challenger_newly_missed_critical_case" in blockers
    assert report["promotion_gate"]["newly_missed_critical_case_ids"] == [
        "case-critical-history"
    ]


@pytest.mark.parametrize("field", ["version_id", "judge_version", "role"])
def test_blind_run_rejects_identity_fields_even_when_hash_is_recomputed(field: str):
    manifest, runs, bindings = _inputs()
    runs[0][field] = "leaked-identity"
    _reseal_run(runs[0])
    bindings[0]["run_hash"] = runs[0]["run_hash"]

    with pytest.raises(ValueError, match="exposes version identity"):
        _build(manifest, runs, bindings)


def test_blind_run_rejects_role_name_in_anonymous_identifiers():
    manifest, runs, bindings = _inputs()
    runs[0]["run_id"] = "incumbent-run"
    _reseal_run(runs[0])
    bindings[0]["run_hash"] = runs[0]["run_hash"]

    with pytest.raises(ValueError, match="run_id exposes"):
        _build(manifest, runs, bindings)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "fixture_mismatch"])
def test_case_set_or_identity_mismatch_fails_closed(mutation: str):
    manifest, runs, bindings = _inputs()
    run = runs[1]
    if mutation == "missing":
        run["cases"].pop()
    elif mutation == "extra":
        extra = deepcopy(run["cases"][0])
        extra["case_id"] = "case-extra"
        run["cases"].append(extra)
    elif mutation == "duplicate":
        run["cases"].append(deepcopy(run["cases"][0]))
    else:
        run["cases"][0]["fixture_hash"] = stable_hash({"fixture": "wrong"})
    _reseal_run(run)
    bindings[1]["run_hash"] = run["run_hash"]

    with pytest.raises(ValueError):
        _build(manifest, runs, bindings)


def test_prediction_hash_and_run_hash_tampering_fail_closed():
    manifest, runs, bindings = _inputs()
    runs[1]["cases"][0]["prediction"]["score"] = 0.01

    with pytest.raises(ValueError, match="run_hash mismatch"):
        _build(manifest, runs, bindings)

    _reseal_run(runs[1])
    bindings[1]["run_hash"] = runs[1]["run_hash"]
    with pytest.raises(ValueError, match="prediction_hash mismatch"):
        _build(manifest, runs, bindings)


def test_manifest_hash_tampering_fails_closed():
    manifest, runs, bindings = _inputs()
    manifest["dataset_id"] = "tampered"

    with pytest.raises(ValueError, match="manifest_hash mismatch"):
        _build(manifest, runs, bindings)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("split", "train", "split='holdout'"),
        ("source_isolation_verified", False, "verified source isolation"),
    ],
)
def test_non_holdout_or_unverified_source_isolation_is_rejected(
    field: str,
    value: object,
    message: str,
):
    manifest, runs, bindings = _inputs()
    manifest[field] = value
    _reseal_manifest(manifest)

    with pytest.raises(ValueError, match=message):
        _build(manifest, runs, bindings)


def test_missing_extra_or_duplicate_versions_are_rejected():
    manifest, runs, bindings = _inputs()

    with pytest.raises(ValueError, match="exactly two anonymous runs"):
        _build(manifest, runs[:1], bindings)

    duplicate = deepcopy(bindings)
    duplicate[1]["role"] = "incumbent"
    with pytest.raises(ValueError, match="duplicate blind role binding"):
        _build(manifest, runs, duplicate)

    same_version = deepcopy(bindings)
    same_version[1]["version_id"] = same_version[0]["version_id"]
    with pytest.raises(ValueError, match="different immutable versions"):
        _build(manifest, runs, same_version)

    same_artifact = deepcopy(bindings)
    same_artifact[1]["artifact_hash"] = same_artifact[0]["artifact_hash"]
    with pytest.raises(ValueError, match="different artifacts"):
        _build(manifest, runs, same_artifact)


def test_role_binding_must_commit_to_exact_blind_run():
    manifest, runs, bindings = _inputs()
    bindings[1]["run_hash"] = stable_hash({"wrong": "run"})

    with pytest.raises(ValueError, match="run_hash mismatch"):
        _build(manifest, runs, bindings)


@pytest.mark.parametrize("value", [-0.1, 1.1, True, "0.5"])
def test_invalid_probability_or_score_is_rejected(value: object):
    manifest, runs, bindings = _inputs()
    prediction = runs[1]["cases"][0]["prediction"]
    prediction["failure_probability"] = value
    runs[1]["cases"][0]["prediction_hash"] = stable_hash(prediction)
    _reseal_run(runs[1])
    bindings[1]["run_hash"] = runs[1]["run_hash"]

    with pytest.raises(ValueError, match="between 0 and 1"):
        _build(manifest, runs, bindings)


def test_holdout_without_failure_and_critical_coverage_cannot_recommend_promotion():
    manifest, runs, bindings = _inputs()
    manifest["cases"] = [manifest["cases"][0]]
    _reseal_manifest(manifest)
    for run, binding in zip(runs, bindings, strict=True):
        run["manifest_hash"] = manifest["manifest_hash"]
        run["cases"] = [run["cases"][0]]
        _reseal_run(run)
        binding["run_hash"] = run["run_hash"]

    report = _build(manifest, runs, bindings)

    assert report["promotion_gate"]["status"] == "blocked"
    assert "heldout_failure_coverage_missing" in report["promotion_gate"]["blockers"]
    assert (
        "heldout_critical_error_coverage_missing"
        in report["promotion_gate"]["blockers"]
    )
    assert (
        "historical_critical_regression_coverage_missing"
        in report["promotion_gate"]["blockers"]
    )
