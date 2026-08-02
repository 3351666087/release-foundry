from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_REFS = (ROOT / "docs" / "evidence" / "private_refs").resolve()
WHEEL = ROOT / "docs" / "a1" / "_pypi_artifacts" / "releasefoundry-0.3.1-py3-none-any.whl"
HARD_POLL_BLOCKERS = frozenset(
    {
        "aggregate_total_mismatch",
        "grading_status_ambiguous",
        "judge_version_ambiguous",
        "judge_version_mismatch",
        "run_dataset_id_mismatch",
        "test_entry_not_object",
        "test_id_duplicate",
        "test_id_missing_or_invalid",
        "unexpected_test_present",
    }
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.judge.releasefoundry_dataset_identity import (  # noqa: E402
    load_dataset_identity_manifest,
)
from services.judge.releasefoundry_test_receipts import (  # noqa: E402
    PRIVATE_RECEIPT_SCHEMA_VERSION,
    assert_public_releasefoundry_test_terminal_receipt_safe,
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_terminal_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Poll one explicit ReleaseFoundry run and verify every mapped test reaches its "
            "own terminal server-scoring state. This command never creates a run."
        )
    )
    parser.add_argument(
        "--identity-file",
        default="docs/evidence/private_refs/a2_releasefoundry_dataset_identity.private.json",
    )
    parser.add_argument(
        "--case-map",
        default="fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json",
    )
    parser.add_argument(
        "--private-output",
        default="docs/evidence/private_refs/a2_releasefoundry_test_terminal_receipt.private.json",
    )
    parser.add_argument(
        "--public-output",
        default="docs/evidence/a2_releasefoundry_test_terminal_receipt.json",
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    args = parser.parse_args()
    _validate_poll_parameters(
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
        request_timeout=args.request_timeout,
    )

    run_id = _positive_int_from_env("RELEASEFOUNDRY_RUN_ID")
    judge_version = os.environ.get("RELEASEFOUNDRY_JUDGE_VERSION", "")
    identity_path = _private_path(args.identity_file)
    private_output = _private_path(args.private_output)
    public_output = (ROOT / args.public_output).resolve()
    case_map_path = (ROOT / args.case_map).resolve()
    case_map = _load_case_map(case_map_path)

    startup_receipt = _initial_blocked_receipt(
        run_id=run_id,
        expected_test_count=len(case_map),
    )
    _write_receipt_pair(
        startup_receipt,
        private_output=private_output,
        public_output=public_output,
        public_metadata={
            "generated_at": _utc_now(),
            "verification_in_progress": True,
            "read_only_api_calls_only": True,
            "create_run_called": False,
        },
    )

    if not os.environ.get("RELEASEFOUNDRY_LABS_API_KEY"):
        raise SystemExit("RELEASEFOUNDRY_LABS_API_KEY is required; its value is never printed.")
    expectation = load_dataset_identity_manifest(identity_path)

    _ensure_releasefoundry_sdk_importable()
    from releasefoundry import ReleaseFoundryLabsClient  # type: ignore

    client = ReleaseFoundryLabsClient.from_env(timeout=args.request_timeout)
    receipt = poll_releasefoundry_run_receipt(
        client,
        run_id=run_id,
        case_map=case_map,
        expected_dataset_id=expectation.dataset_id,
        expected_judge_version=judge_version,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
        request_timeout=args.request_timeout,
    )
    receipt.update(
        {
            "generated_at": _utc_now(),
            "identity_manifest_hash": _sha256_file(identity_path),
            "case_map_hash": _sha256_file(case_map_path),
            "sdk_source": _sdk_source(),
            "read_only_api_calls_only": True,
            "create_run_called": False,
        }
    )
    _write_receipt_pair(
        receipt,
        private_output=private_output,
        public_output=public_output,
        public_metadata={
            key: receipt[key]
            for key in (
                "generated_at",
                "poll_count",
                "poll_elapsed_ms",
                "case_map_hash",
                "sdk_source",
                "read_only_api_calls_only",
                "create_run_called",
            )
        },
    )
    print(
        "ReleaseFoundry per-test verification: state={state} verified={verified}/{expected} "
        "polls={polls} public_output={output}".format(
            state=receipt["verification_state"],
            verified=receipt["verified_test_count"],
            expected=receipt["expected_test_count"],
            polls=receipt["poll_count"],
            output=public_output,
        )
    )
    return 0 if receipt["verification_state"] == "verified" else 2


def poll_releasefoundry_run_receipt(
    client: Any,
    *,
    run_id: int,
    case_map: dict[str, str],
    expected_dataset_id: int,
    expected_judge_version: str = "",
    poll_seconds: float = 5.0,
    timeout_seconds: float = 300.0,
    request_timeout: float = 30.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Poll within one strict deadline and always return a blocked receipt on errors."""
    _validate_poll_parameters(
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
        request_timeout=request_timeout,
    )
    started = monotonic()
    deadline = started + timeout_seconds
    poll_count = 0
    receipt = _initial_blocked_receipt(
        run_id=run_id,
        expected_test_count=len(case_map),
        expected_dataset_id=expected_dataset_id,
    )

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            receipt = _add_poll_blocker(receipt, "poll_timeout")
            break

        poll_count += 1
        if hasattr(client, "timeout"):
            client.timeout = min(request_timeout, max(0.1, remaining))
        try:
            run = client.get_run(run_id)
        except Exception as exc:  # noqa: BLE001 - receipt stores only exception type
            receipt = _add_poll_blocker(receipt, "poll_read_error")
            receipt["poll_error_type"] = type(exc).__name__
            break

        receipt = build_releasefoundry_test_terminal_receipt(
            run,
            case_map=case_map,
            expected_dataset_id=expected_dataset_id,
            expected_judge_version=expected_judge_version,
        )
        if _polling_finished(receipt):
            break

        remaining = deadline - monotonic()
        if remaining <= 0:
            receipt = _add_poll_blocker(receipt, "poll_timeout")
            break
        sleep(min(poll_seconds, remaining))

    receipt["poll_count"] = poll_count
    receipt["poll_elapsed_ms"] = round((monotonic() - started) * 1000)
    return receipt


def _polling_finished(receipt: dict[str, Any]) -> bool:
    if receipt.get("receipt_complete") is True:
        return True
    blockers = set(receipt.get("blockers") or [])
    if blockers & HARD_POLL_BLOCKERS:
        return True
    if receipt.get("all_expected_tests_terminal_scoring_verified") is True:
        return True
    if (
        receipt.get("run_result_terminal_verified") is True
        and "test_missing" in blockers
    ):
        return True
    return False


def _initial_blocked_receipt(
    *,
    run_id: int,
    expected_test_count: int,
    expected_dataset_id: int | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PRIVATE_RECEIPT_SCHEMA_VERSION,
        "verification_state": "blocked",
        "run_id": run_id,
        "dataset_id": None,
        "expected_dataset_id": expected_dataset_id,
        "run_result_status": "",
        "run_result_terminal_verified": False,
        "grading_status": "",
        "grading_status_present": False,
        "grading_status_source_paths": [],
        "grading_status_terminal_verified": None,
        "server_grading_lifecycle_verified": False,
        "expected_judge_version": "",
        "observed_judge_version": "",
        "observed_judge_version_paths": [],
        "judge_version_candidate_count": 0,
        "judge_version_source": "missing",
        "judge_version_verified": False,
        "expected_test_count": expected_test_count,
        "observed_test_count": 0,
        "valid_test_object_count": 0,
        "verified_test_count": 0,
        "missing_test_count": expected_test_count,
        "duplicate_test_count": 0,
        "unexpected_test_count": 0,
        "unidentified_test_count": 0,
        "malformed_test_count": 0,
        "nonterminal_test_count": 0,
        "exact_test_set_verified": False,
        "aggregate_total_marker_present": False,
        "aggregate_total_marker_consistent": None,
        "aggregate_marker_used_as_acceptance_authority": False,
        "all_expected_tests_terminal_scoring_verified": False,
        "receipt_complete": False,
        "tests": [],
        "blockers": ["verification_in_progress"],
        "release_authority": False,
    }


def _add_poll_blocker(
    receipt: dict[str, Any],
    blocker: str,
) -> dict[str, Any]:
    receipt = dict(receipt)
    receipt["blockers"] = list(
        dict.fromkeys([*(receipt.get("blockers") or []), blocker])
    )
    receipt["verification_state"] = "blocked"
    receipt["receipt_complete"] = False
    return receipt


def _write_receipt_pair(
    private_receipt: dict[str, Any],
    *,
    private_output: Path,
    public_output: Path,
    public_metadata: dict[str, Any],
) -> None:
    public_receipt = public_releasefoundry_test_terminal_receipt(private_receipt)
    public_receipt.update(public_metadata)
    assert_public_releasefoundry_test_terminal_receipt_safe(public_receipt)
    _atomic_write_json(private_output, private_receipt)
    _atomic_write_json(public_output, public_receipt)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _validate_poll_parameters(
    *,
    poll_seconds: float,
    timeout_seconds: float,
    request_timeout: float,
) -> None:
    for name, value in (
        ("poll_seconds", poll_seconds),
        ("timeout_seconds", timeout_seconds),
        ("request_timeout", request_timeout),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value <= 0
        ):
            raise SystemExit(f"{name} must be a positive finite number")


def _positive_int_from_env(name: str) -> int:
    raw = os.environ.get(name, "")
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise SystemExit(f"{name} must be a positive integer")
    return value


def _private_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    try:
        path.relative_to(PRIVATE_REFS)
    except ValueError as exc:
        raise SystemExit("private paths must remain under docs/evidence/private_refs") from exc
    return path


def _load_case_map(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("--case-map must point to a JSON object")
    return payload


def _ensure_releasefoundry_sdk_importable() -> None:
    if importlib.util.find_spec("releasefoundry") is not None:
        return
    if WHEEL.exists():
        sys.path.insert(0, str(WHEEL))
        return
    raise RuntimeError(
        "releasefoundry is not installed and the local PyPI wheel artifact is missing."
    )


def _sdk_source() -> str:
    version = "unknown"
    try:
        version = importlib.metadata.version("releasefoundry")
    except importlib.metadata.PackageNotFoundError:
        if WHEEL.exists():
            version = "0.3.1"
    source = (
        "bundled-wheel"
        if WHEEL.exists() and str(WHEEL) in sys.path
        else "installed-package"
    )
    return f"{source}:releasefoundry=={version}"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
