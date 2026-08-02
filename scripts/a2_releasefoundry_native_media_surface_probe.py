from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "docs" / "a1" / "_pypi_artifacts" / "releasefoundry-0.3.1-py3-none-any.whl"
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "a2_releasefoundry_native_media_surface.json"
EXPECTED_PACKAGE_NAME = "releasefoundry"
EXPECTED_SDK_VERSION = "0.3.1"
EXPECTED_CREATE_REQUEST_PARAMETERS = [
    "self",
    "request_name",
    "request",
    "request_input_schema",
    "tenant_id",
    "requestor_id",
]
EXPECTED_ADD_USER_FILE_PARAMETERS = [
    "self",
    "file_path",
    "description",
    "action_index",
]
MEDIA_MODALITIES = ("image", "audio", "file", "video")
GENERATED_ARTIFACT_EVIDENCE = (
    ROOT / "docs" / "evidence" / "a2_multimodal_real_api_smoke.json",
    ROOT / "docs" / "evidence" / "a2_multimodal_audio_real_api_smoke.json",
    ROOT / "docs" / "evidence" / "a2_multimodal_image_real_api_smoke.json",
    ROOT / "docs" / "evidence" / "a2_multimodal_file_real_api_smoke.json",
)
SDK_SOURCE_FILES = (
    "releasefoundry/client.py",
    "releasefoundry/eval.py",
    "releasefoundry/run_builder.py",
)
FIRST_CLASS_MEDIA_URL_PARAMETERS = {
    "media_url",
    "image_url",
    "audio_url",
    "file_url",
    "video_url",
    "media_urls",
    "image_urls",
    "audio_urls",
    "file_urls",
    "video_urls",
}
UPLOAD_METHOD_PATTERN = re.compile(
    r"(?:upload|attach|submit).*(?:media|image|audio|file|video)"
    r"|(?:media|image|audio|file|video).*(?:upload|attach|submit)"
)
DATASET_INGESTION_METHOD_PATTERN = re.compile(
    r"(?:create|import|upload|ingest|attach).*dataset"
    r"|dataset.*(?:create|import|upload|ingest|attach)"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the pinned ReleaseFoundry SDK compatibility surface for caller-native media submission "
            "surfaces and optionally perform one read-only authenticated init call."
        )
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT.relative_to(ROOT)))
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use an installed network-capable SDK for exactly one read-only client.init() call.",
    )
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive.")
    if args.live and not os.environ.get("RELEASEFOUNDRY_LABS_API_KEY"):
        raise SystemExit(
            "RELEASEFOUNDRY_LABS_API_KEY is required for --live; the probe never reads key files."
        )

    output = _resolve_output(args.output)
    report = build_report(live=args.live, timeout=args.timeout)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": _repo_relative(output),
                "static_audit_status": report["static_audit"]["status"],
                "live_session_status": report["live_session"]["status"],
                "caller_native_input_support_proven": report[
                    "caller_native_input_support_proven"
                ],
                "c3_grading_ready": report["c3_grading_ready"],
            },
            sort_keys=True,
        )
    )

    if report["static_audit"]["status"] != "completed":
        return 1
    if args.live and not report["live_session"]["reached"]:
        return 1
    return 0


def build_report(
    *,
    live: bool,
    timeout: int = 30,
    wheel: Path = WHEEL,
    client_factory: Callable[[int], Any] | None = None,
) -> dict[str, Any]:
    audit = audit_sdk_surface(wheel)
    generated_capabilities, evidence = _generated_artifact_capabilities()
    submission_status = _caller_native_submission_status(audit)
    live_session = _probe_live_session(
        requested=live,
        timeout=timeout,
        wheel=wheel,
        client_factory=client_factory,
    )
    return {
        "schema_version": "a2.releasefoundry_native_media_surface.v1",
        "generated_at": _now(),
        "sdk": {
            "package_name": audit["package_name"],
            "version": audit["version"],
            "artifact_path": _repo_relative(wheel),
            "artifact_sha256": _sha256_file(wheel),
            "source_file_sha256": audit["source_file_sha256"],
        },
        "static_audit": {
            "status": audit["status"],
            "expected_surface_matches": audit["expected_surface_matches"],
            "surface_fingerprint_sha256": audit["surface_fingerprint_sha256"],
            "public_client_methods": audit["public_client_methods"],
            "upload_method_names_observed": audit["upload_method_names_observed"],
            "dataset_ingestion_method_names_observed": audit[
                "dataset_ingestion_method_names_observed"
            ],
            "immutable_media_url_parameters_observed": audit[
                "immutable_media_url_parameters_observed"
            ],
            "generic_payload_parameters_observed": audit[
                "generic_payload_parameters_observed"
            ],
            "accepted_inputs": audit["accepted_inputs"],
            "add_user_file": audit["add_user_file"],
            "eval_runner": audit["eval_runner"],
        },
        "live_session": live_session,
        "generated_artifact_capabilities": generated_capabilities,
        "generated_artifact_evidence": evidence,
        "caller_native_submission": {
            modality: (
                "provider_unverified" if modality == "video" else submission_status
            )
            for modality in MEDIA_MODALITIES
        },
        "upload_method_observed": bool(audit["upload_method_names_observed"]),
        "immutable_media_url_parameter_observed": bool(
            audit["immutable_media_url_parameters_observed"]
        ),
        "undocumented_endpoint_probed": False,
        "mutation_attempt_count": 0,
        "native_media_uploaded": False,
        "caller_native_input_support_proven": False,
        "c3_grading_ready": False,
        "public_safe": True,
        "notes": [
            (
                "accepted_inputs describes the tested agent's declared input "
                "capabilities; it is not a caller media transport."
            ),
            (
                "RunBuilder.TestBuilder.add_user_file records file_path metadata "
                "inside a run result; the pinned implementation performs no file I/O."
            ),
            (
                "EvalRunner passes action content text to agent.respond and does not "
                "expose a native media byte transport in the audited path."
            ),
            (
                "Generic dict parameters may carry undocumented nested values, but "
                "this probe does not call undocumented endpoints or treat them as a "
                "verified media submission API."
            ),
            (
                "Verified image, audio, and file capabilities refer only to "
                "ReleaseFoundry-generated dataset artifacts. Video remains provider-unverified."
            ),
        ],
    }


def audit_sdk_surface(wheel: Path = WHEEL) -> dict[str, Any]:
    if not wheel.is_file():
        raise FileNotFoundError(f"Pinned ReleaseFoundry SDK artifact is missing: {_repo_relative(wheel)}")

    with zipfile.ZipFile(wheel) as archive:
        package_name, version = _read_package_metadata(archive)
        sources = {
            name: archive.read(name).decode("utf-8", errors="strict")
            for name in SDK_SOURCE_FILES
        }

    client_tree = ast.parse(sources["releasefoundry/client.py"])
    run_builder_tree = ast.parse(sources["releasefoundry/run_builder.py"])
    client_methods = _class_public_methods(client_tree, "ReleaseFoundryLabsClient")
    test_builder_methods = _class_public_methods(run_builder_tree, "TestBuilder")
    create_request_parameters = client_methods.get("create_request", [])
    add_user_file_parameters = test_builder_methods.get("add_user_file", [])

    upload_methods = sorted(
        name for name in client_methods if UPLOAD_METHOD_PATTERN.search(name)
    )
    dataset_ingestion_methods = sorted(
        name for name in client_methods if DATASET_INGESTION_METHOD_PATTERN.search(name)
    )
    media_url_parameters = sorted(
        {
            f"{method}.{parameter}"
            for method, parameters in client_methods.items()
            for parameter in parameters
            if parameter in FIRST_CLASS_MEDIA_URL_PARAMETERS
        }
    )
    generic_payload_parameters = sorted(
        {
            f"{method}.{parameter}"
            for method, parameters in client_methods.items()
            for parameter in parameters
            if parameter in {"config", "request", "request_input_schema", "result"}
        }
    )

    add_user_file = _audit_add_user_file(
        run_builder_tree,
        sources["releasefoundry/run_builder.py"],
    )
    eval_runner = _audit_eval_runner(sources["releasefoundry/eval.py"])
    accepted_inputs_observed = '"accepted_inputs"' in sources["releasefoundry/client.py"]
    generation_options_observed = '"generation_options"' in sources[
        "releasefoundry/client.py"
    ]
    expected_surface_matches = (
        package_name == EXPECTED_PACKAGE_NAME
        and version == EXPECTED_SDK_VERSION
        and create_request_parameters == EXPECTED_CREATE_REQUEST_PARAMETERS
        and add_user_file_parameters == EXPECTED_ADD_USER_FILE_PARAMETERS
        and add_user_file["classification"] == "metadata_only"
        and eval_runner["classification"] == "text_content_only_observed"
        and accepted_inputs_observed
        and generation_options_observed
    )
    method_records = [
        {"name": name, "parameters": parameters}
        for name, parameters in sorted(client_methods.items())
    ]
    source_hashes = {
        name: _sha256_text(sources[name])
        for name in sorted(sources)
    }
    fingerprint = _canonical_sha256(
        {
            "package_name": package_name,
            "version": version,
            "public_client_methods": method_records,
            "source_file_sha256": source_hashes,
        }
    )
    return {
        "status": "completed" if expected_surface_matches else "review_required",
        "package_name": package_name,
        "version": version,
        "expected_surface_matches": expected_surface_matches,
        "surface_fingerprint_sha256": fingerprint,
        "source_file_sha256": source_hashes,
        "public_client_methods": method_records,
        "upload_method_names_observed": upload_methods,
        "dataset_ingestion_method_names_observed": dataset_ingestion_methods,
        "immutable_media_url_parameters_observed": media_url_parameters,
        "generic_payload_parameters_observed": generic_payload_parameters,
        "accepted_inputs": {
            "observed": accepted_inputs_observed,
            "classification": (
                "agent_capability_declaration_not_media_transport"
                if accepted_inputs_observed
                else "not_observed"
            ),
        },
        "add_user_file": add_user_file,
        "eval_runner": eval_runner,
    }


def _class_public_methods(tree: ast.Module, class_name: str) -> dict[str, list[str]]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name: _function_parameters(child)
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not child.name.startswith("_")
            }
    return {}


def _function_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    parameters = [
        argument.arg
        for argument in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
    ]
    if node.args.vararg is not None:
        parameters.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg is not None:
        parameters.append(f"**{node.args.kwarg.arg}")
    return parameters


def _audit_add_user_file(tree: ast.Module, source: str) -> dict[str, Any]:
    method = _class_method(tree, "TestBuilder", "add_user_file")
    if method is None:
        return {
            "observed": False,
            "parameters": [],
            "records_file_path": False,
            "file_io_calls_observed": [],
            "classification": "not_observed",
        }

    io_call_names = sorted(
        {
            _call_name(node.func)
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and _call_name(node.func)
            in {
                "open",
                "read",
                "read_bytes",
                "read_text",
                "request",
                "urlopen",
                "post",
                "put",
            }
        }
    )
    records_file_path = '"file_path": file_path' in source
    return {
        "observed": True,
        "parameters": _function_parameters(method),
        "records_file_path": records_file_path,
        "file_io_calls_observed": io_call_names,
        "classification": (
            "metadata_only"
            if records_file_path and not io_call_names
            else "transport_or_unknown_review_required"
        ),
    }


def _audit_eval_runner(source: str) -> dict[str, Any]:
    action_content_read = 'content = action.get("content", "")' in source
    text_respond_call = (
        "agent.respond(content)" in source
        or "agent.respond(content, scenario_id=run_id)" in source
    )
    native_file_action_call = "test.add_user_file(" in source
    classification = (
        "text_content_only_observed"
        if action_content_read and text_respond_call and not native_file_action_call
        else "transport_or_unknown_review_required"
    )
    return {
        "action_content_read": action_content_read,
        "agent_respond_receives_content": text_respond_call,
        "native_file_action_call_observed": native_file_action_call,
        "classification": classification,
    }


def _class_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if (
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name == method_name
                ):
                    return child
    return None


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _caller_native_submission_status(audit: dict[str, Any]) -> str:
    if not audit["expected_surface_matches"]:
        return "sdk_surface_changed_review_required"
    if (
        audit["upload_method_names_observed"]
        or audit["dataset_ingestion_method_names_observed"]
        or audit["immutable_media_url_parameters_observed"]
        or audit["add_user_file"]["classification"] != "metadata_only"
        or audit["eval_runner"]["classification"] != "text_content_only_observed"
    ):
        return "provider_surface_observed_requires_validation"
    return "provider_surface_missing"


def _generated_artifact_capabilities() -> tuple[dict[str, str], list[dict[str, Any]]]:
    capabilities = {
        "image": "not_verified",
        "audio": "not_verified",
        "file": "not_verified",
        "video": "provider_unverified",
    }
    evidence: list[dict[str, Any]] = []
    for path in GENERATED_ARTIFACT_EVIDENCE:
        record = {
            "path": _repo_relative(path),
            "sha256": "",
            "verified_modalities": [],
        }
        if path.is_file():
            record["sha256"] = _sha256_file(path)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                payload = {}

            if isinstance(payload, dict):
                (
                    collections_valid,
                    required_modalities,
                    verified_receipt_modalities,
                    reported_verified_modalities,
                    reported_missing_modalities,
                ) = _validated_generated_artifact_collections(payload)
                recomputed_missing_modalities = (
                    required_modalities - verified_receipt_modalities
                )
                evidence_verified = (
                    collections_valid
                    and payload.get("schema_version")
                    == "a2.multimodal_real_api_smoke.v1"
                    and payload.get("artifact_origin") == "releasefoundry_generated_dataset"
                    and payload.get("artifact_receipt_status") == "verified"
                    and payload.get("artifact_modality_coverage_complete") is True
                    and payload.get("artifact_receipts_public_safe") is True
                    and payload.get("public_safe") is True
                    and payload.get("request_status") == "completed"
                    and payload.get("dataset_request_binding_verified") is True
                    and payload.get("native_media_uploaded") is False
                    and payload.get("media_upload_api_observed") is False
                    and bool(required_modalities)
                    and not recomputed_missing_modalities
                    and not reported_missing_modalities
                    and reported_verified_modalities
                    == verified_receipt_modalities
                )
                if evidence_verified:
                    verified = sorted(required_modalities)
                    record["verified_modalities"] = verified
                    for modality in verified:
                        capabilities[modality] = "verified"
        evidence.append(record)
    return capabilities, evidence


def _validated_generated_artifact_collections(
    payload: dict[str, Any],
) -> tuple[bool, set[str], set[str], set[str], set[str]]:
    allowed_required_modalities = {"text", "image", "audio", "file"}
    allowed_artifact_modalities = {"image", "audio", "file"}
    list_fields = {
        "required_modalities": payload.get("required_modalities"),
        "artifact_verified_modalities": payload.get(
            "artifact_verified_modalities"
        ),
        "artifact_missing_modalities": payload.get(
            "artifact_missing_modalities"
        ),
    }
    if any(
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
        or len(value) != len(set(value))
        for value in list_fields.values()
    ):
        return False, set(), set(), set(), set()

    required_values = list_fields["required_modalities"]
    reported_verified_values = list_fields["artifact_verified_modalities"]
    reported_missing_values = list_fields["artifact_missing_modalities"]
    if (
        "text" not in required_values
        or not set(required_values) <= allowed_required_modalities
        or not set(reported_verified_values) <= allowed_artifact_modalities
        or not set(reported_missing_values) <= allowed_artifact_modalities
    ):
        return False, set(), set(), set(), set()

    artifact_receipts = payload.get("artifact_receipts")
    if not isinstance(artifact_receipts, list) or not artifact_receipts:
        return False, set(), set(), set(), set()

    receipt_modalities: list[str] = []
    receipt_hashes: list[str] = []
    for receipt in artifact_receipts:
        if not isinstance(receipt, dict):
            return False, set(), set(), set(), set()
        modality = receipt.get("modality")
        sha256 = receipt.get("sha256")
        byte_size = receipt.get("byte_size")
        response_mime = receipt.get("response_mime")
        if (
            modality not in allowed_artifact_modalities
            or receipt.get("verification_status") != "verified"
            or not isinstance(sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
            or isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or byte_size <= 0
            or not isinstance(response_mime, str)
            or not response_mime.strip()
        ):
            return False, set(), set(), set(), set()
        receipt_modalities.append(modality)
        receipt_hashes.append(sha256)

    if (
        len(receipt_modalities) != len(set(receipt_modalities))
        or len(receipt_hashes) != len(set(receipt_hashes))
    ):
        return False, set(), set(), set(), set()

    required_modalities = set(required_values) - {"text"}
    verified_receipt_modalities = set(receipt_modalities)
    reported_verified_modalities = set(reported_verified_values)
    reported_missing_modalities = set(reported_missing_values)
    collections_valid = bool(required_modalities) and (
        reported_verified_modalities == verified_receipt_modalities
        and reported_missing_modalities
        == required_modalities - verified_receipt_modalities
    )
    return (
        collections_valid,
        required_modalities,
        verified_receipt_modalities,
        reported_verified_modalities,
        reported_missing_modalities,
    )


def _probe_live_session(
    *,
    requested: bool,
    timeout: int,
    wheel: Path,
    client_factory: Callable[[int], Any] | None,
) -> dict[str, Any]:
    if not requested:
        return {
            "requested": False,
            "attempted": False,
            "reached": False,
            "status": "not_requested",
            "api_call_count": 0,
            "mutation_attempt_count": 0,
        }

    try:
        client = (
            client_factory(timeout)
            if client_factory is not None
            else _pinned_client_from_env(wheel=wheel, timeout=timeout)
        )
        client.init()
    except Exception as exc:  # pragma: no cover - exercised with a fake in tests.
        return {
            "requested": True,
            "attempted": True,
            "reached": False,
            "status": "error",
            "error_type": exc.__class__.__name__,
            "api_call_count": 1,
            "mutation_attempt_count": 0,
        }

    return {
        "requested": True,
        "attempted": True,
        "reached": True,
        "status": "ok",
        "api_call_count": 1,
        "mutation_attempt_count": 0,
    }


def _pinned_client_from_env(*, wheel: Path, timeout: int) -> Any:
    wheel_path = str(wheel.resolve())
    if wheel_path not in sys.path:
        sys.path.insert(0, wheel_path)
    module = importlib.import_module("releasefoundry")
    module_file = str(getattr(module, "__file__", ""))
    if wheel.name not in module_file:
        raise RuntimeError("releasefoundry did not load from the pinned SDK artifact.")
    return module.ReleaseFoundryLabsClient.from_env(timeout=timeout)


def _read_package_metadata(archive: zipfile.ZipFile) -> tuple[str, str]:
    metadata_names = [
        name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
    ]
    if len(metadata_names) != 1:
        raise RuntimeError("Pinned SDK must contain exactly one distribution METADATA file.")
    metadata = archive.read(metadata_names[0]).decode("utf-8", errors="strict")
    fields: dict[str, str] = {}
    for line in metadata.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in {"Name", "Version"} and key not in fields:
            fields[key] = value.strip()
    return fields.get("Name", ""), fields.get("Version", "")


def _resolve_output(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    evidence_root = (ROOT / "docs" / "evidence").resolve()
    if resolved != evidence_root and evidence_root not in resolved.parents:
        raise SystemExit("--output must stay under docs/evidence.")
    return resolved


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


if __name__ == "__main__":
    raise SystemExit(main())
