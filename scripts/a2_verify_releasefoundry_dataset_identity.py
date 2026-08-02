from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_REFS = (ROOT / "docs" / "evidence" / "private_refs").resolve()
WHEEL = ROOT / "docs" / "a1" / "_pypi_artifacts" / "releasefoundry-0.3.1-py3-none-any.whl"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.judge.releasefoundry_dataset_identity import (  # noqa: E402
    DatasetIdentityError,
    load_dataset_identity_manifest,
    pin_dataset_identity,
    verify_dataset_identity,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pin or verify one ReleaseFoundry dataset by explicit ID, exact name, and "
            "canonical dataset-source SHA-256 without listing or auto-selecting datasets."
        )
    )
    parser.add_argument(
        "--identity-file",
        default="docs/evidence/private_refs/a2_releasefoundry_dataset_identity.private.json",
    )
    parser.add_argument(
        "--output",
        default="docs/evidence/a2_releasefoundry_dataset_identity_receipt.json",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--pin-from-env",
        action="store_true",
        help=(
            "Create the first private pin from RELEASEFOUNDRY_DATASET_ID and "
            "RELEASEFOUNDRY_DATASET_NAME after exact live verification."
        ),
    )
    parser.add_argument(
        "--replace-pin",
        action="store_true",
        help="Explicitly replace an existing private pin when --pin-from-env is used.",
    )
    args = parser.parse_args()

    if not os.environ.get("RELEASEFOUNDRY_LABS_API_KEY"):
        raise SystemExit("RELEASEFOUNDRY_LABS_API_KEY is required; its value is never printed.")

    identity_path = _private_identity_path(args.identity_file)
    _ensure_releasefoundry_sdk_importable()
    from releasefoundry import ReleaseFoundryLabsClient  # type: ignore

    client = ReleaseFoundryLabsClient.from_env(timeout=args.timeout)
    if args.pin_from_env:
        if identity_path.exists() and not args.replace_pin:
            raise SystemExit("dataset_identity_pin_exists")
        expected_id = _dataset_id_from_env()
        expected_name = os.environ.get("RELEASEFOUNDRY_DATASET_NAME", "")
        if not expected_name:
            raise SystemExit("RELEASEFOUNDRY_DATASET_NAME is required for --pin-from-env")
        dataset = client.get_dataset(expected_id, include_signed_urls=False)
        expectation = pin_dataset_identity(
            dataset,
            expected_dataset_id=expected_id,
            expected_dataset_name=expected_name,
        )
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(
            json.dumps(expectation.private_manifest(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        binding_action = "pinned_and_verified"
    else:
        expectation = load_dataset_identity_manifest(identity_path)
        dataset = client.get_dataset(
            expectation.dataset_id,
            include_signed_urls=False,
        )
        binding_action = "verified_existing_pin"

    receipt = verify_dataset_identity(
        dataset,
        expected_dataset_id=expectation.dataset_id,
        expected_dataset_name=expectation.dataset_name,
        expected_content_sha256=expectation.dataset_content_sha256,
    )
    receipt.update(
        {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "binding_action": binding_action,
            "identity_manifest_sha256": _sha256_file(identity_path),
            "sdk_source": _sdk_source(),
            "base_url": os.environ.get(
                "RELEASEFOUNDRY_LABS_BASE_URL",
                "https://api.releasefoundry.io/testing-platform-api",
            ),
            "notes": [
                "The official ReleaseFoundry SDK fetched one explicitly pinned dataset ID directly.",
                "No dataset list ordering or request-linked fallback was used.",
                "The private identity manifest and raw dataset payload are not included.",
            ],
        }
    )
    output = (ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "ReleaseFoundry dataset identity verified: state={state} items={count} output={output}".format(
            state=receipt["verification_state"],
            count=receipt["content_item_count"],
            output=output,
        )
    )
    return 0


def _private_identity_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    try:
        path.relative_to(PRIVATE_REFS)
    except ValueError as exc:
        raise DatasetIdentityError(
            "dataset_identity_manifest_must_be_under_private_refs"
        ) from exc
    return path


def _dataset_id_from_env() -> int:
    value = os.environ.get("RELEASEFOUNDRY_DATASET_ID", "")
    try:
        dataset_id = int(value)
    except ValueError as exc:
        raise SystemExit("RELEASEFOUNDRY_DATASET_ID must be a positive integer") from exc
    if dataset_id <= 0:
        raise SystemExit("RELEASEFOUNDRY_DATASET_ID must be a positive integer")
    return dataset_id


def _ensure_releasefoundry_sdk_importable() -> None:
    if importlib.util.find_spec("releasefoundry") is not None:
        return
    if WHEEL.exists():
        sys.path.insert(0, str(WHEEL))
        return
    raise RuntimeError("releasefoundry is not installed and the local PyPI wheel artifact is missing.")


def _sdk_source() -> str:
    if WHEEL.exists() and str(WHEEL) in sys.path:
        return "docs/a1/_pypi_artifacts/releasefoundry-0.3.1-py3-none-any.whl"
    spec = importlib.util.find_spec("releasefoundry")
    return str(spec.origin) if spec and spec.origin else "installed"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
