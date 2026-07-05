from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT_DIR = Path("fixtures/a2/results")
DEFAULT_EVIDENCE_READINESS = DEFAULT_RESULT_DIR / "a2_evidence_readiness_report.json"
DEFAULT_CASE_BOOK = DEFAULT_RESULT_DIR / "a2_case_book.json"
DEFAULT_REGRESSION_REPLAY = DEFAULT_RESULT_DIR / "a2_regression_replay_report.json"
DEFAULT_COMMERCIAL_READINESS = DEFAULT_RESULT_DIR / "a2_commercial_readiness_report.json"


def build_preflight(
    *,
    evidence_readiness_path: str | Path = DEFAULT_EVIDENCE_READINESS,
    case_book_path: str | Path = DEFAULT_CASE_BOOK,
    regression_replay_path: str | Path = DEFAULT_REGRESSION_REPLAY,
    commercial_readiness_path: str | Path = DEFAULT_COMMERCIAL_READINESS,
) -> dict[str, Any]:
    evidence = _load_json(evidence_readiness_path)
    case_book = _load_json(case_book_path)
    replay = _load_json(regression_replay_path)
    commercial = _load_json(commercial_readiness_path)

    ashr_gate = evidence.get("ashr_public_merge_gate", {})
    semantic_gate = evidence.get("semantic_live_merge_gate", {})
    ashr_preflight = evidence.get("ashr_grading_preflight", {})
    semantic_preflight = evidence.get("semantic_judge_preflight", {})
    case_book_gate = case_book.get("maturity_gate", {})
    replay_gate = replay.get("maturity_gate", {})
    commercial_gates = {gate.get("gate"): gate for gate in commercial.get("gate_status", [])}

    return {
        "schema_version": "a2.external_evidence_preflight.v1",
        "preflight_id": "a2_external_evidence_preflight",
        "requires_network": False,
        "requires_ashr_api_key": False,
        "reads_private_payloads": False,
        "writes_files": False,
        "public_inputs": [
            Path(evidence_readiness_path).as_posix(),
            Path(case_book_path).as_posix(),
            Path(regression_replay_path).as_posix(),
            Path(commercial_readiness_path).as_posix(),
        ],
        "environment_probe": {
            "ashr_labs_api_key_present": bool(os.environ.get("ASHR_LABS_API_KEY")),
            "value_redacted": True,
        },
        "gate_summary": {
            "C3": _c3_summary(ashr_gate, ashr_preflight, commercial_gates.get("C3", {})),
            "C4": _c4_summary(semantic_gate, semantic_preflight, commercial_gates.get("C4", {})),
            "C5": _c5_summary(case_book_gate, replay_gate, commercial_gates.get("C5", {})),
        },
        "private_input_refs": _private_input_refs(ashr_preflight, semantic_preflight),
        "recommended_commands": {
            "ashr_grading": list(ashr_preflight.get("commands", [])),
            "semantic_judge": list(semantic_preflight.get("commands", [])),
            "post_merge_verification": [
                "python -B scripts/a2_regenerate_fixtures.py --check",
                "python -B -m unittest discover -s tests/a2 -v",
            ],
        },
        "redaction_policy": evidence.get("redaction_policy", {}),
        "next_actions": _next_actions(ashr_gate, semantic_gate, case_book_gate, replay_gate),
        "metadata": {
            "deterministic": True,
            "purpose": "Summarize the safe C3/C4/C5 evidence workflow without reading keys or private payloads.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print an offline A2 C3/C4/C5 external-evidence preflight without reading private payloads."
    )
    parser.add_argument("--json", action="store_true", help="Print the full preflight as JSON.")
    parser.add_argument("--evidence-readiness", default=DEFAULT_EVIDENCE_READINESS.as_posix())
    parser.add_argument("--case-book", default=DEFAULT_CASE_BOOK.as_posix())
    parser.add_argument("--regression-replay", default=DEFAULT_REGRESSION_REPLAY.as_posix())
    parser.add_argument("--commercial-readiness", default=DEFAULT_COMMERCIAL_READINESS.as_posix())
    args = parser.parse_args()

    os.chdir(ROOT)
    preflight = build_preflight(
        evidence_readiness_path=Path(args.evidence_readiness),
        case_book_path=Path(args.case_book),
        regression_replay_path=Path(args.regression_replay),
        commercial_readiness_path=Path(args.commercial_readiness),
    )
    if args.json:
        print(json.dumps(preflight, indent=2))
    else:
        print(_text_summary(preflight))
    return 0


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    return json.loads(resolved.read_text(encoding="utf-8"))


def _c3_summary(
    ashr_gate: dict[str, Any],
    ashr_preflight: dict[str, Any],
    commercial_gate: dict[str, Any],
) -> dict[str, Any]:
    expected = int(ashr_gate.get("expected_reviewed_observation_count", 0))
    reviewed = int(ashr_gate.get("reviewed_public_observation_count", 0))
    return {
        "name": "Reviewed Ashr grading calibration",
        "commercial_status": commercial_gate.get("status", "unknown"),
        "merge_status": ashr_gate.get("status", "unknown"),
        "safe_to_mark_met": bool(ashr_gate.get("safe_to_mark_c3_met")),
        "reviewed_observations": reviewed,
        "expected_reviewed_observations": expected,
        "missing_reviewed_observations": max(0, expected - reviewed),
        "case_map_covers_all_calibration_cases": bool(ashr_preflight.get("case_map_covers_all_calibration_cases")),
        "blocking_reason": ashr_gate.get("blocking_reason", ""),
    }


def _c4_summary(
    semantic_gate: dict[str, Any],
    semantic_preflight: dict[str, Any],
    commercial_gate: dict[str, Any],
) -> dict[str, Any]:
    expected = int(semantic_gate.get("expected_reviewed_observation_count", 0))
    reviewed = int(semantic_gate.get("reviewed_live_observation_count", 0))
    return {
        "name": "Audited semantic judge evidence",
        "commercial_status": commercial_gate.get("status", "unknown"),
        "merge_status": semantic_gate.get("status", "unknown"),
        "safe_to_mark_met": bool(semantic_gate.get("safe_to_mark_c4_met")),
        "reviewed_live_observations": reviewed,
        "expected_reviewed_observations": expected,
        "missing_reviewed_observations": max(0, expected - reviewed),
        "offline_reference_only": bool(semantic_preflight.get("offline_reference_only")),
        "covered_sdk_languages": list(semantic_preflight.get("covered_sdk_languages", [])),
        "blocking_reason": semantic_gate.get("blocking_reason", ""),
    }


def _c5_summary(
    case_book_gate: dict[str, Any],
    replay_gate: dict[str, Any],
    commercial_gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": "Reviewed disagreement regression maturity",
        "commercial_status": commercial_gate.get("status", "unknown"),
        "case_book_status": case_book_gate.get("status", "unknown"),
        "case_book_ready": bool(case_book_gate.get("ready")),
        "replay_ready": bool(replay_gate.get("ready")),
        "current_regression_cases": int(case_book_gate.get("current_regression_case_count", 0)),
        "target_regression_cases": int(case_book_gate.get("target_regression_case_count", 0)),
        "reviewed_external_evidence": int(case_book_gate.get("reviewed_external_evidence_count", 0)),
        "reviewed_evidence_target": int(case_book_gate.get("reviewed_evidence_target_count", 0)),
        "gaps": list(case_book_gate.get("gaps", [])) + list(replay_gate.get("gaps", [])),
    }


def _private_input_refs(*preflights: dict[str, Any]) -> list[str]:
    refs = []
    for preflight in preflights:
        ref = str(preflight.get("private_input_ref", "")).strip()
        if ref:
            refs.append(ref)
    return sorted(set(refs))


def _next_actions(
    ashr_gate: dict[str, Any],
    semantic_gate: dict[str, Any],
    case_book_gate: dict[str, Any],
    replay_gate: dict[str, Any],
) -> list[str]:
    actions = []
    if not ashr_gate.get("safe_to_mark_c3_met"):
        actions.append("Collect, review, import, and merge all six Ashr grading observations before marking C3 met.")
    if not semantic_gate.get("safe_to_mark_c4_met"):
        actions.append("Replace offline llm_judge references with audited live semantic judge summaries before marking C4 met.")
    if not case_book_gate.get("ready") or not replay_gate.get("ready"):
        actions.append("Promote reviewed cross-judge disagreements until the case book and replay maturity gates both pass.")
    return actions


def _text_summary(preflight: dict[str, Any]) -> str:
    lines = [
        "A2 external evidence preflight",
        "network: off | private payloads: not read | writes files: no | API key value: never printed",
        "",
    ]
    for gate_id, gate in preflight["gate_summary"].items():
        status = "ready" if gate.get("safe_to_mark_met") or gate.get("case_book_ready") else "waiting"
        lines.append(f"{gate_id}: {status} ({gate.get('commercial_status', 'unknown')})")
        if gate.get("blocking_reason"):
            lines.append(f"  reason: {gate['blocking_reason']}")
        for gap in gate.get("gaps", []):
            lines.append(f"  gap: {gap}")
    lines.extend(["", "Next actions:"])
    lines.extend(f"- {action}" for action in preflight["next_actions"])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
