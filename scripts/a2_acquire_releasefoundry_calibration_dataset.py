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
    atomic_write_public_json,
    blocked_public_receipt,
    build_calibration_dataset_request,
    create_request_once,
    fetch_and_verify_dataset,
    load_request_ref,
    validated_private_path,
    wait_for_request_terminal,
    write_request_ref,
    write_verified_manifest,
)


DEFAULT_REQUEST_REF = (
    "docs/evidence/private_refs/a2_releasefoundry_dataset_request.private.json"
)
DEFAULT_PRIVATE_MANIFEST = (
    "docs/evidence/private_refs/a2_releasefoundry_dataset_acquisition.private.json"
)
DEFAULT_PUBLIC_RECEIPT = (
    "docs/evidence/a2_releasefoundry_dataset_acquisition_receipt.json"
)


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[int], Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build or acquire the fixed six-case ReleaseFoundry calibration dataset. "
            "Dry-run is the default and performs no network or mutating call."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Create one new ReleaseFoundry dataset-generation request.",
    )
    mode.add_argument(
        "--resume",
        action="store_true",
        help="Resume polling from the existing private request reference.",
    )
    parser.add_argument(
        "--allow-mutate",
        action="store_true",
        help="Second explicit authorization required with --execute.",
    )
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--client-timeout", type=int, default=30)
    parser.add_argument("--request-ref", default=DEFAULT_REQUEST_REF)
    parser.add_argument("--private-manifest", default=DEFAULT_PRIVATE_MANIFEST)
    parser.add_argument("--output", default=DEFAULT_PUBLIC_RECEIPT)
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    spec = build_calibration_dataset_request(root=ROOT)
    if not args.execute and not args.resume:
        if args.allow_mutate:
            parser.error("--allow-mutate requires --execute")
        print(
            json.dumps(
                spec.public_summary(),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 0
    if args.execute and not args.allow_mutate:
        parser.error("--execute requires --allow-mutate")
    if args.resume and args.allow_mutate:
        parser.error("--resume is read-only and must not use --allow-mutate")

    request_ref_path = _private_cli_path(args.request_ref)
    manifest_path = _private_cli_path(args.private_manifest)
    if args.execute and (request_ref_path.exists() or manifest_path.exists()):
        raise SystemExit(
            "private acquisition state already exists; use --resume instead of "
            "creating a duplicate paid request"
        )

    environment = environ if environ is not None else os.environ
    api_key = environment.get("RELEASEFOUNDRY_LABS_API_KEY")
    if not api_key:
        raise SystemExit(
            "RELEASEFOUNDRY_LABS_API_KEY is required for live execution; its value is "
            "never printed or persisted."
        )
    factory = client_factory or _client_from_env
    client = factory(args.client_timeout)

    phase = "request_creation" if args.execute else "request_resume"
    try:
        if args.execute:
            request_id = create_request_once(client, spec)
            write_request_ref(
                request_ref_path,
                private_root=PRIVATE_ROOT,
                request_id=request_id,
                spec=spec,
            )
        else:
            request_id = load_request_ref(
                request_ref_path,
                private_root=PRIVATE_ROOT,
                spec=spec,
            )

        phase = "request_polling"
        wait_for_request_terminal(
            client,
            request_id,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
        )
        phase = "dataset_discovery_and_verification"
        manifest, receipt = fetch_and_verify_dataset(
            client,
            request_id=request_id,
            spec=spec,
            forbidden_values=(api_key,),
        )
        write_verified_manifest(
            manifest_path,
            manifest,
            private_root=PRIVATE_ROOT,
        )
        atomic_write_public_json(ROOT / args.output, receipt)
    except DatasetAcquisitionError as exc:
        blocker = str(exc)
        if phase == "request_creation":
            blocker = (
                "create_request_outcome_unknown_do_not_retry"
                if blocker
                else "create_request_failed_do_not_retry"
            )
        blocked = blocked_public_receipt(
            spec,
            blocker=blocker,
            phase=phase,
        )
        atomic_write_public_json(ROOT / args.output, blocked)
        print(
            f"A2 ReleaseFoundry dataset acquisition blocked at {phase}: {blocker}",
            file=sys.stderr,
        )
        return 2
    except Exception:
        blocker = (
            "create_request_outcome_unknown_do_not_retry"
            if phase == "request_creation"
            else "unexpected_live_api_error"
        )
        blocked = blocked_public_receipt(
            spec,
            blocker=blocker,
            phase=phase,
        )
        atomic_write_public_json(ROOT / args.output, blocked)
        print(
            f"A2 ReleaseFoundry dataset acquisition blocked at {phase}: {blocker}",
            file=sys.stderr,
        )
        return 2

    print(
        "Verified the fixed six-case ReleaseFoundry dataset. Private service IDs remain "
        f"under {PRIVATE_ROOT.relative_to(ROOT).as_posix()}/; public receipt: "
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
