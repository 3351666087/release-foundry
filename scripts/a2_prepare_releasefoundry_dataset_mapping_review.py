from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = (ROOT / "docs" / "evidence" / "private_refs").resolve()
WHEEL = (
    ROOT
    / "docs"
    / "a1"
    / "_pypi_artifacts"
    / "releasefoundry-0.3.1-py3-none-any.whl"
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.judge.releasefoundry_dataset_acquisition import (  # noqa: E402
    DatasetAcquisitionError,
    atomic_write_private_json,
    atomic_write_public_json,
    build_calibration_dataset_request,
    find_single_dataset_for_request,
    load_request_ref,
    validated_private_path,
    wait_for_request_terminal,
)
from services.judge.releasefoundry_dataset_mapping import (  # noqa: E402
    blocked_mapping_receipt,
    build_dataset_mapping_proposal,
)


DEFAULT_REQUEST_REF = (
    "docs/evidence/private_refs/a2_releasefoundry_dataset_request.private.json"
)
DEFAULT_PRIVATE_REVIEW = (
    "docs/evidence/private_refs/a2_releasefoundry_dataset_mapping_review.private.json"
)
DEFAULT_PUBLIC_RECEIPT = "docs/evidence/a2_releasefoundry_dataset_mapping_receipt.json"


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[int], Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a private machine-proposed mapping for human review. "
            "The command is read-only against ReleaseFoundry and never authorizes paid runs."
        )
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch the existing generated dataset through read-only API calls.",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--client-timeout", type=int, default=30)
    parser.add_argument("--request-ref", default=DEFAULT_REQUEST_REF)
    parser.add_argument("--private-review", default=DEFAULT_PRIVATE_REVIEW)
    parser.add_argument("--output", default=DEFAULT_PUBLIC_RECEIPT)
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    spec = build_calibration_dataset_request(root=ROOT)
    if not args.fetch:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "case_count": len(spec.case_contracts),
                    "request_sha256": spec.request_sha256,
                    "case_contract_set_sha256": spec.case_contract_set_sha256,
                    "network_calls": 0,
                    "mutating_calls": 0,
                    "mapping_authority": "none",
                    "paid_create_run_allowed": False,
                    "human_review_required": True,
                    "public_safe": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    environment = environ if environ is not None else os.environ
    api_key = environment.get("RELEASEFOUNDRY_LABS_API_KEY")
    if not api_key:
        raise SystemExit(
            "RELEASEFOUNDRY_LABS_API_KEY is required for read-only live fetch; its value "
            "is never printed or persisted."
        )

    request_ref = _private_cli_path(args.request_ref)
    private_review = _private_cli_path(args.private_review)
    client = (client_factory or _client_from_env)(args.client_timeout)
    try:
        request_id = load_request_ref(
            request_ref,
            private_root=PRIVATE_ROOT,
            spec=spec,
        )
        wait_for_request_terminal(
            client,
            request_id,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
        )
        listed = find_single_dataset_for_request(
            client,
            request_id,
            forbidden_values=(api_key,),
        )
        dataset_id = listed.get("id")
        dataset = client.get_dataset(
            dataset_id,
            include_signed_urls=False,
        )
        if not isinstance(dataset, Mapping):
            raise DatasetAcquisitionError("get_dataset_response_invalid")
        proposal = build_dataset_mapping_proposal(
            dataset,
            request_id=request_id,
            spec=spec,
            forbidden_values=(api_key,),
        )
        atomic_write_private_json(
            private_review,
            proposal.private_payload(),
            private_root=PRIVATE_ROOT,
        )
        atomic_write_public_json(ROOT / args.output, proposal.public_receipt())
    except DatasetAcquisitionError as exc:
        receipt = blocked_mapping_receipt(spec, blocker=str(exc))
        atomic_write_public_json(ROOT / args.output, receipt)
        print(f"A2 ReleaseFoundry dataset mapping blocked: {exc}", file=sys.stderr)
        return 2
    except Exception:
        receipt = blocked_mapping_receipt(
            spec,
            blocker="unexpected_live_api_error",
        )
        atomic_write_public_json(ROOT / args.output, receipt)
        print(
            "A2 ReleaseFoundry dataset mapping blocked: unexpected_live_api_error",
            file=sys.stderr,
        )
        return 2

    print(
        "Prepared a machine-only six-case mapping proposal for human review. "
        "The proposal does not authorize paid create_run; public receipt: "
        f"{Path(args.output).as_posix()}"
    )
    return 0


def _private_cli_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return validated_private_path(candidate, private_root=PRIVATE_ROOT)


def _client_from_env(timeout: int) -> Any:
    _ensure_releasefoundry_sdk_importable()
    from releasefoundry import ReleaseFoundryLabsClient  # type: ignore

    return ReleaseFoundryLabsClient.from_env(timeout=timeout)


def _ensure_releasefoundry_sdk_importable() -> None:
    if importlib.util.find_spec("releasefoundry") is not None:
        return
    if not WHEEL.is_file():
        raise SystemExit(f"official ReleaseFoundry SDK wheel not found: {WHEEL}")
    sys.path.insert(0, str(WHEEL))


if __name__ == "__main__":
    raise SystemExit(main())
