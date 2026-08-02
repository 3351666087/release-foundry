from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "docs" / "a1" / "_pypi_artifacts" / "releasefoundry-0.3.1-py3-none-any.whl"
MODALITIES = ["text", "image", "audio", "file", "video"]
MEDIA_MODALITIES = ["image", "audio", "file", "video"]
DEFAULT_MEDIA_MODALITIES = ["image", "audio", "file"]
DEFAULT_REQUIRED_MODALITIES = ["text", "image", "audio", "file"]
PROVIDER_LIMITATIONS = {
    "video": "provider_unverified",
}
DEFAULT_ARTIFACT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_ARTIFACTS = 64
DEFAULT_REQUEST_PAGE_LIMIT = 50
DEFAULT_MAX_REQUEST_PAGES = 100
SUCCESSFUL_REQUEST_STATUSES = frozenset({"completed", "ready", "succeeded"})
FAILED_REQUEST_STATUSES = frozenset(
    {"failed", "error", "cancelled", "canceled", "rejected", "expired"}
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a real ReleaseFoundry API multimodal request smoke and save a redacted public summary."
    )
    parser.add_argument("--output", default="docs/evidence/a2_multimodal_real_api_smoke.json")
    parser.add_argument(
        "--private-output",
        default="docs/evidence/private_refs/a2_multimodal_real_api_smoke.private.json",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--wait-timeout", type=int, default=180)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument(
        "--artifact-timeout",
        type=int,
        default=DEFAULT_ARTIFACT_TIMEOUT_SECONDS,
        help="Per-artifact HTTPS download timeout in seconds.",
    )
    parser.add_argument(
        "--max-artifact-bytes",
        type=int,
        default=DEFAULT_MAX_ARTIFACT_BYTES,
        help="Maximum bytes read for any one generated artifact.",
    )
    parser.add_argument(
        "--max-artifacts",
        type=int,
        default=DEFAULT_MAX_ARTIFACTS,
        help="Maximum number of generated artifact URLs downloaded from one dataset.",
    )
    parser.add_argument(
        "--modalities",
        default=",".join(DEFAULT_MEDIA_MODALITIES),
        help=(
            "Comma-separated ReleaseFoundry-generated media modalities. "
            "Defaults to image,audio,file."
        ),
    )
    parser.add_argument(
        "--allow-provider-unverified-video",
        action="store_true",
        help=(
            "Explicitly authorize a provider-capability probe when --modalities "
            "includes video. Video remains provider-unverified and cannot satisfy "
            "A2 multimodal acceptance."
        ),
    )
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument(
        "--no-artifact-download",
        action="store_true",
        help="Do not request signed URLs or download generated artifacts.",
    )
    args = parser.parse_args()

    if args.artifact_timeout <= 0:
        raise SystemExit("--artifact-timeout must be positive.")
    if args.max_artifact_bytes <= 0:
        raise SystemExit("--max-artifact-bytes must be positive.")
    if args.max_artifacts <= 0:
        raise SystemExit("--max-artifacts must be positive.")

    requested_media_modalities = _parse_modalities(args.modalities)
    _require_provider_capability_opt_in(
        requested_media_modalities,
        allow_provider_unverified_video=args.allow_provider_unverified_video,
    )

    if not os.environ.get("RELEASEFOUNDRY_LABS_API_KEY"):
        raise SystemExit("RELEASEFOUNDRY_LABS_API_KEY is required; the script never reads key files directly.")

    _ensure_releasefoundry_sdk_importable()
    from releasefoundry import ReleaseFoundryLabsClient  # type: ignore

    client = ReleaseFoundryLabsClient.from_env(timeout=args.timeout)
    requested_modalities = [
        modality
        for modality in MODALITIES
        if modality == "text" or modality in requested_media_modalities
    ]
    required_modalities = list(requested_modalities)
    request_config = _request_config(requested_media_modalities)
    request_input_schema = _request_input_schema(request_config)
    request_content_sha256 = _request_content_sha256(
        request_config=request_config,
        request_input_schema=request_input_schema,
    )
    request_name = f"A2 multimodal generated-artifact smoke {request_content_sha256[:12]}"
    calls: list[dict[str, Any]] = []
    raw: dict[str, Any] = {
        "schema_version": "a2.multimodal_real_api_private.v1",
        "generated_at": _now(),
        "warning": "Private raw ReleaseFoundry API smoke evidence. Do not commit.",
        "request_content_sha256": request_content_sha256,
    }

    session = _record_call(calls, raw, "init", client.init)
    request_inventory = _find_single_request_by_exact_name(
        client,
        request_name=request_name,
        calls=calls,
        raw=raw,
    )
    existing_request = request_inventory["request"]
    mutation_guard_status = (
        "reused_exact_request" if existing_request is not None else "created_once"
    )

    created = existing_request
    if existing_request is None:
        created = _record_call(
            calls,
            raw,
            "create_request",
            lambda: _create_request_once(
                client,
                request_name=request_name,
                request=request_config,
                request_input_schema=request_input_schema,
            ),
        )

    request_reused = existing_request is not None
    create_request_attempt_count = sum(call["name"] == "create_request" for call in calls)
    if create_request_attempt_count > 1:
        raise RuntimeError("create_request must never be attempted more than once per smoke execution.")
    if create_request_attempt_count == 1 and created is None:
        mutation_guard_status = "create_request_failed_once"

    request_id = _int_or_none(_field(created, "id"))
    waited = None
    request_detail = None
    dataset = None
    dataset_id = None
    dataset_binding_verified = False
    request_status = _request_status(created)
    artifact_receipt_result = _empty_artifact_receipt_result(
        "dataset_unavailable",
        required_modalities=requested_media_modalities,
    )
    if request_id is not None and not args.no_wait:
        waited = _record_call(
            calls,
            raw,
            "wait_for_request",
            lambda: client.wait_for_request(
                request_id,
                timeout=args.wait_timeout,
                poll_interval=args.poll_interval,
            ),
        )
        request_detail = _record_call(
            calls,
            raw,
            "get_request",
            lambda: client.get_request(request_id),
        )
        if _int_or_none(_field(request_detail, "id")) not in {None, request_id}:
            raise RuntimeError("get_request returned an identifier that does not match the selected request.")
        request_status = _request_status(request_detail, waited, created)
        (
            dataset,
            dataset_id,
            dataset_binding_verified,
            artifact_receipt_result,
        ) = _collect_completed_request_evidence(
            client=client,
            request_id=request_id,
            request_status=request_status,
            calls=calls,
            raw=raw,
            allowed_modalities=requested_media_modalities,
            download_artifacts=not args.no_artifact_download,
            artifact_timeout=args.artifact_timeout,
            max_artifact_bytes=args.max_artifact_bytes,
            max_artifacts=args.max_artifacts,
        )

    raw["selection"] = {
        "request_reused": request_reused,
        "mutation_guard_status": mutation_guard_status,
        "create_request_attempt_count": create_request_attempt_count,
        "request_inventory_page_count": request_inventory["page_count"],
        "request_inventory_complete": request_inventory["inventory_complete"],
        "request_inventory_exact_match_count": request_inventory["exact_match_count"],
        "selected_request_id": request_id,
        "dataset_binding_verified": dataset_binding_verified,
    }
    raw["artifact_receipt_summary"] = artifact_receipt_result

    private_output = ROOT / args.private_output
    private_output.parent.mkdir(parents=True, exist_ok=True)
    private_output.write_text(json.dumps(_redact_raw(raw), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    modality_evidence = _modality_evidence(
        request_created=request_id is not None,
        dataset=dataset,
        requested_modalities=requested_modalities,
        verified_artifact_modalities=[
            receipt["modality"]
            for receipt in artifact_receipt_result["artifact_receipts"]
            if receipt["verification_status"] == "verified"
        ],
    )
    excluded_modalities = [
        modality for modality in MEDIA_MODALITIES if modality not in requested_media_modalities
    ]
    summary = {
        "schema_version": "a2.multimodal_real_api_smoke.v1",
        "generated_at": _now(),
        "sdk_source": _sdk_source(),
        "base_url": os.environ.get("RELEASEFOUNDRY_LABS_BASE_URL", "https://api.releasefoundry.io/testing-platform-api"),
        "auth": _redacted_session(session),
        "private_ref": args.private_output,
        "private_ref_sha256_12": _sha256_file(private_output)[:12],
        "request_content_sha256": request_content_sha256,
        "required_modalities": required_modalities,
        "excluded_modalities": excluded_modalities,
        "provider_limitations": dict(PROVIDER_LIMITATIONS),
        "requested_modalities": modality_evidence["requested_modalities"],
        "request_config_accepted_modalities": modality_evidence["request_config_accepted_modalities"],
        "observed_artifact_modalities": modality_evidence["observed_artifact_modalities"],
        "accepted_modalities": modality_evidence["accepted_modalities"],
        "modality_evidence": modality_evidence["modalities"],
        "generation_options": request_config["generation_options"],
        "artifact_origin": "releasefoundry_generated_dataset",
        "artifact_receipt_status": artifact_receipt_result["artifact_receipt_status"],
        "artifact_reference_count": artifact_receipt_result["artifact_reference_count"],
        "artifact_download_attempt_count": artifact_receipt_result[
            "artifact_download_attempt_count"
        ],
        "artifact_download_verified_count": artifact_receipt_result[
            "artifact_download_verified_count"
        ],
        "artifact_reference_modalities": artifact_receipt_result[
            "artifact_reference_modalities"
        ],
        "artifact_verified_modalities": artifact_receipt_result[
            "artifact_verified_modalities"
        ],
        "artifact_missing_modalities": artifact_receipt_result[
            "artifact_missing_modalities"
        ],
        "artifact_modality_coverage_complete": artifact_receipt_result[
            "artifact_modality_coverage_complete"
        ],
        "artifact_receipts": artifact_receipt_result["artifact_receipts"],
        "artifact_receipts_public_safe": True,
        "native_media_uploaded": False,
        "media_upload_api_observed": False,
        "api_call_count": len(calls),
        "calls": calls,
        "mutation_guard_status": mutation_guard_status,
        "create_request_attempt_count": create_request_attempt_count,
        "create_request_retry_count": 0,
        "request_inventory_page_count": request_inventory["page_count"],
        "request_inventory_complete": request_inventory["inventory_complete"],
        "request_inventory_exact_match_count": request_inventory["exact_match_count"],
        "request_reused": request_reused,
        "request_id_present": request_id is not None,
        "request_id_sha256_12": _sha256_text(str(request_id))[:12] if request_id is not None else "",
        "request_status": request_status,
        "dataset_id_present": _field(dataset, "id") is not None,
        "dataset_id_sha256_12": _sha256_text(str(_field(dataset, "id")))[:12] if _field(dataset, "id") is not None else "",
        "dataset_content_sha256": _canonical_sha256(dataset) if dataset is not None else "",
        "dataset_request_binding_verified": dataset_binding_verified,
        "dataset_summary": _dataset_summary(dataset),
        "all_required_modalities_requested": _all_required_modalities_requested(
            required_modalities=required_modalities,
            requested_modalities=modality_evidence["requested_modalities"],
            generation_options=request_config["generation_options"],
        ),
        "create_request_reached": any(call["name"] == "create_request" and call["status"] == "ok" for call in calls),
        "wait_completed": _request_completed(request_status),
        "public_safe": True,
        "c3_grading_ready": False,
        "notes": [
            "This is a redacted public summary of a real ReleaseFoundry multimodal request smoke.",
            "The default smoke requests ReleaseFoundry-generated image, audio, and file artifacts; video is excluded unless explicitly opted in.",
            "Every request-inventory page is scanned before create_request is allowed, preventing reuse misses beyond the first page.",
            "Generated dataset artifacts do not prove that the SDK accepts caller-uploaded native media.",
            "The private ref is ignored by git and may contain raw API structure for human review.",
            "No API key, authorization header, signed URL, binary payload, or raw private response is stored in this public summary.",
        ],
    }

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "multimodal real API smoke wrote {path}: create_request={created} wait_completed={waited}".format(
            path=output.as_posix(),
            created=summary["create_request_reached"],
            waited=summary["wait_completed"],
        )
    )
    return 0


def _parse_modalities(value: str) -> list[str]:
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    unknown = sorted(set(requested) - set(MEDIA_MODALITIES))
    if unknown:
        raise SystemExit(
            "Unsupported --modalities value(s): "
            + ", ".join(unknown)
            + ". Allowed values: "
            + ", ".join(MEDIA_MODALITIES)
        )
    if not requested:
        raise SystemExit("--modalities must include at least one media modality.")
    return [modality for modality in MEDIA_MODALITIES if modality in set(requested)]


def _require_provider_capability_opt_in(
    requested_modalities: list[str] | tuple[str, ...],
    *,
    allow_provider_unverified_video: bool,
) -> None:
    if (
        "video" in requested_modalities
        and not allow_provider_unverified_video
    ):
        raise SystemExit(
            "video is provider-unverified; rerun with "
            "--allow-provider-unverified-video only for an explicit capability probe."
        )


def _all_required_modalities_requested(
    *,
    required_modalities: list[str] | tuple[str, ...],
    requested_modalities: list[str] | tuple[str, ...],
    generation_options: dict[str, Any],
) -> bool:
    generation_option_by_modality = {
        "image": "generate_images",
        "audio": "generate_audio",
        "file": "generate_files",
        "video": "generate_videos",
    }
    required = set(required_modalities)
    requested = set(requested_modalities)
    return required.issubset(requested) and all(
        generation_options.get(generation_option_by_modality[modality]) is True
        for modality in required - {"text"}
    )


def _request_config(media_modalities: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    selected_media = list(media_modalities or DEFAULT_MEDIA_MODALITIES)
    selected_modalities = ["text", *selected_media]
    examples = {
        "image": {"asset_ref": "synthetic:image:dashboard-error", "expected_boundary": "describe visible UI only"},
        "audio": {"asset_ref": "synthetic:audio:customer-complaint", "expected_boundary": "summarize transcript only"},
        "file": {"asset_ref": "synthetic:file:q1-usage-csv", "expected_boundary": "compute from file rows only"},
        "video": {"asset_ref": "synthetic:video:checkout-flow", "expected_boundary": "cite observed steps only"},
    }
    return {
        "metadata": {
            "dataset_name": "A2 Multimodal Artifact Receipt v1",
            "description": (
                "Stable calibration request for generated image, audio, and file "
                "artifact byte verification."
            ),
        },
        "agent": {
            "name": "A2 Multimodal Injection Probe",
            "description": (
                "Evaluates whether an enterprise support agent handles ReleaseFoundry-generated "
                + ", ".join(selected_media)
                + " context without ignoring modality boundaries."
            ),
            "system_prompt": "Answer from provided multimodal evidence only. Ask for clarification when a referenced asset is missing or ambiguous.",
            "accepted_inputs": {
                modality: {"enabled": modality in selected_modalities}
                for modality in MODALITIES
            },
            "output_format": {"type": "text"},
            "tools": [
                {
                    "name": "inspect_asset_manifest",
                    "description": "Inspect a provided multimodal asset manifest before answering.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "asset_id": {"type": "string"},
                            "modality": {"type": "string", "enum": MODALITIES},
                        },
                        "required": ["asset_id", "modality"],
                    },
                }
            ],
        },
        "context": {
            "domain": "enterprise SaaS support analytics",
            "use_case": "Ground customer-support answers in mixed media attachments and file evidence.",
            "scenario_context": (
                "The generated dataset may include "
                + ", ".join(selected_media)
                + " artifacts. The agent must not invent missing evidence or treat one modality as another."
            ),
            "sample_data": {
                "examples": [examples[modality] for modality in selected_media]
            },
        },
        "test_config": {
            "num_variations": 1,
            "strategy": "focused",
            "coverage": {
                "happy_path": True,
                "edge_cases": False,
                "error_handling": False,
                "multi_input": False,
                "multi_turn": False,
            },
            "complexity_distribution": {
                "simple": 1,
                "moderate": 0,
                "complex": 0,
            },
        },
        "generation_options": {
            "scenario_count": 1,
            "generate_audio": "audio" in selected_media,
            "generate_files": "file" in selected_media,
            "generate_images": "image" in selected_media,
            "generate_videos": "video" in selected_media,
            "generate_simulations": False,
        },
    }


def _request_input_schema(request_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = request_config or _request_config()
    return {
        "type": "object",
        "properties": {
            "agent": {"type": "object"},
            "context": {"type": "object"},
            "test_config": {"type": "object"},
            "generation_options": {"type": "object"},
        },
        "required": ["agent", "context", "test_config", "generation_options"],
        "tools": config["agent"]["tools"],
    }


def _request_content_sha256(
    *,
    request_config: dict[str, Any],
    request_input_schema: dict[str, Any],
) -> str:
    return _canonical_sha256(
        {
            "request": request_config,
            "request_input_schema": request_input_schema,
        }
    )


def _create_request_once(
    client: Any,
    *,
    request_name: str,
    request: dict[str, Any],
    request_input_schema: dict[str, Any],
) -> Any:
    return client.create_request(
        request_name=request_name,
        request=request,
        request_input_schema=request_input_schema,
    )


def _find_single_request_by_exact_name(
    client: Any,
    *,
    request_name: str,
    calls: list[dict[str, Any]],
    raw: dict[str, Any],
    page_limit: int = DEFAULT_REQUEST_PAGE_LIMIT,
    max_pages: int = DEFAULT_MAX_REQUEST_PAGES,
) -> dict[str, Any]:
    if not isinstance(request_name, str) or not request_name:
        raise ValueError("request_name must be a non-empty string.")
    if (
        not isinstance(page_limit, int)
        or isinstance(page_limit, bool)
        or page_limit <= 0
    ):
        raise ValueError("page_limit must be a positive integer.")
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or max_pages <= 0
    ):
        raise ValueError("max_pages must be a positive integer.")

    cursor: int | None = None
    seen_cursors: set[int] = set()
    matches: list[dict[str, Any]] = []
    raw_pages = raw.setdefault("request_inventory_pages", [])
    if not isinstance(raw_pages, list):
        raise RuntimeError("raw request inventory storage must be a list.")

    for page_number in range(1, max_pages + 1):
        try:
            response = client.list_requests(limit=page_limit, cursor=cursor)
        except Exception as exc:
            error = {
                "type": exc.__class__.__name__,
                "message": _safe_error_message(str(exc)),
            }
            calls.append(
                {
                    "name": "list_requests",
                    "status": "error",
                    "error_type": error["type"],
                    "error_message": "Request inventory page read failed.",
                }
            )
            raw.setdefault("request_inventory_errors", []).append(
                {"page_number": page_number, "error": error}
            )
            raise RuntimeError(
                "Request inventory could not be read completely; "
                "refusing to create a potentially duplicate request."
            ) from exc

        response = _to_plain(response)
        raw_pages.append(response)
        calls.append(
            {
                "name": "list_requests",
                "status": "ok",
                "summary": {
                    "type": "dict" if isinstance(response, dict) else type(response).__name__,
                    "page_number": page_number,
                },
            }
        )
        if not isinstance(response, dict):
            raise RuntimeError("Request inventory response must be an object.")

        requests = response.get("requests")
        if not isinstance(requests, list):
            raise RuntimeError("Request inventory response must contain a requests list.")
        for request in requests:
            if not isinstance(request, dict):
                raise RuntimeError("Every request inventory item must be an object.")
            observed_name = request.get("request_name")
            if observed_name is None:
                observed_name = request.get("name")
            if observed_name == request_name:
                matches.append(request)
                if len(matches) > 1:
                    raise RuntimeError(
                        "Found multiple requests with the exact content-bound name; "
                        "refusing to guess which paid request to reuse."
                    )

        next_cursor = response.get("next_cursor")
        if next_cursor is None:
            return {
                "request": matches[0] if matches else None,
                "page_count": page_number,
                "inventory_complete": True,
                "exact_match_count": len(matches),
            }
        if (
            not isinstance(next_cursor, int)
            or isinstance(next_cursor, bool)
            or next_cursor <= 0
        ):
            raise RuntimeError("Request inventory next_cursor must be a positive integer.")
        if next_cursor == cursor or next_cursor in seen_cursors:
            raise RuntimeError("Request inventory cursor loop detected.")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    raise RuntimeError(
        "Request inventory exceeded the maximum page count; "
        "refusing to create a potentially duplicate request."
    )


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


def _record_call(calls: list[dict[str, Any]], raw: dict[str, Any], name: str, fn: Callable[[], Any]) -> Any:
    try:
        payload = fn()
    except Exception as exc:  # pragma: no cover - live API failure surface.
        error = {"type": exc.__class__.__name__, "message": _safe_error_message(str(exc))}
        calls.append({"name": name, "status": "error", "error_type": error["type"], "error_message": error["message"]})
        raw[name] = {"error": error}
        return None

    calls.append({"name": name, "status": "ok", "summary": _summarize_payload(payload)})
    raw[name] = _to_plain(payload)
    return payload


def _summarize_payload(payload: Any) -> dict[str, Any]:
    payload = _to_plain(payload)
    if isinstance(payload, list):
        return {"type": "list", "count": len(payload), "item_keys": _sample_keys(payload)}
    if isinstance(payload, dict):
        summary: dict[str, Any] = {"type": "dict", "keys": sorted(str(key) for key in payload.keys())}
        for key in ("datasets", "runs", "requests", "scenarios", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                summary[f"{key}_count"] = len(value)
                summary[f"{key}_item_keys"] = _sample_keys(value)
        if "status" in payload:
            summary["status_value"] = str(payload.get("status"))
        if "id" in payload:
            summary["id_present"] = payload.get("id") is not None
        return summary
    return {"type": type(payload).__name__}


def _dataset_summary(dataset: Any) -> dict[str, Any]:
    payload = _to_plain(dataset)
    if not isinstance(payload, dict):
        return {"available": False}
    evidence = _modality_evidence(request_created=True, dataset=payload)
    return {
        "available": True,
        "keys": sorted(str(key) for key in payload.keys()),
        "observed_artifact_modalities": evidence["observed_artifact_modalities"],
        "signed_urls_included": False,
    }


def _ordered_media_modalities(values: list[str] | tuple[str, ...]) -> list[str]:
    selected = set(values)
    return [modality for modality in MEDIA_MODALITIES if modality in selected]


def _empty_artifact_receipt_result(
    status: str,
    *,
    required_modalities: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    required = _ordered_media_modalities(required_modalities)
    return {
        "artifact_receipt_status": status,
        "artifact_reference_count": 0,
        "artifact_download_attempt_count": 0,
        "artifact_download_verified_count": 0,
        "artifact_reference_modalities": [],
        "artifact_verified_modalities": [],
        "artifact_missing_modalities": required,
        "artifact_modality_coverage_complete": False,
        "artifact_receipts": [],
    }


def _request_status(*payloads: Any) -> str:
    for payload in payloads:
        value = _field(payload, "request_status") or _field(payload, "status")
        if value is not None and str(value).strip():
            return str(value).strip().lower()
    return ""


def _request_completed(status: str) -> bool:
    return str(status).strip().lower() in SUCCESSFUL_REQUEST_STATUSES


def _request_artifact_gate_status(status: str) -> str:
    normalized = str(status).strip().lower()
    if normalized in SUCCESSFUL_REQUEST_STATUSES:
        return ""
    if normalized in FAILED_REQUEST_STATUSES:
        return "request_failed"
    return "request_not_completed"


def _collect_completed_request_evidence(
    *,
    client: Any,
    request_id: int,
    request_status: str,
    calls: list[dict[str, Any]],
    raw: dict[str, Any],
    allowed_modalities: list[str] | tuple[str, ...],
    download_artifacts: bool,
    artifact_timeout: int,
    max_artifact_bytes: int,
    max_artifacts: int,
) -> tuple[Any, int | None, bool, dict[str, Any]]:
    gate_status = _request_artifact_gate_status(request_status)
    if gate_status:
        return (
            None,
            None,
            False,
            _empty_artifact_receipt_result(
                gate_status,
                required_modalities=allowed_modalities,
            ),
        )

    datasets = _record_call(
        calls,
        raw,
        "list_datasets",
        lambda: client.list_datasets(limit=50, include_signed_urls=False),
    )
    dataset_id = _dataset_id_for_request(datasets, request_id)
    if dataset_id is None:
        return (
            None,
            None,
            False,
            _empty_artifact_receipt_result(
                "dataset_unavailable",
                required_modalities=allowed_modalities,
            ),
        )

    dataset = _record_call(
        calls,
        raw,
        "get_dataset",
        lambda: client.get_dataset(dataset_id, include_signed_urls=False),
    )
    returned_dataset_id = _int_or_none(_field(dataset, "id"))
    returned_request_id = _int_or_none(_field(dataset, "request_id"))
    dataset_binding_verified = (
        returned_dataset_id == dataset_id
        and returned_request_id in {None, request_id}
    )
    if not dataset_binding_verified:
        artifact_result = _empty_artifact_receipt_result(
            "dataset_binding_failed",
            required_modalities=allowed_modalities,
        )
    elif not download_artifacts:
        artifact_result = _empty_artifact_receipt_result(
            "download_disabled",
            required_modalities=allowed_modalities,
        )
    else:
        artifact_result = _collect_artifact_receipts(
            client=client,
            dataset_id=dataset_id,
            request_id=request_id,
            calls=calls,
            allowed_modalities=allowed_modalities,
            timeout=artifact_timeout,
            max_artifact_bytes=max_artifact_bytes,
            max_artifacts=max_artifacts,
        )
    return dataset, dataset_id, dataset_binding_verified, artifact_result


def _collect_artifact_receipts(
    *,
    client: Any,
    dataset_id: int,
    request_id: int,
    calls: list[dict[str, Any]],
    allowed_modalities: list[str] | tuple[str, ...],
    timeout: int,
    max_artifact_bytes: int,
    max_artifacts: int,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    try:
        signed_dataset = client.get_dataset(
            dataset_id,
            include_signed_urls=True,
            url_expires_seconds=max(60, min(3600, timeout * 4)),
        )
    except Exception as exc:  # pragma: no cover - live API failure surface.
        calls.append(
            {
                "name": "get_dataset_artifact_links",
                "status": "error",
                "error_type": exc.__class__.__name__,
                "error_message": "Artifact link retrieval failed.",
            }
        )
        return _empty_artifact_receipt_result(
            "signed_dataset_fetch_failed",
            required_modalities=allowed_modalities,
        )

    returned_dataset_id = _int_or_none(_field(signed_dataset, "id"))
    returned_request_id = _int_or_none(_field(signed_dataset, "request_id"))
    if returned_dataset_id != dataset_id or returned_request_id not in {None, request_id}:
        calls.append(
            {
                "name": "get_dataset_artifact_links",
                "status": "error",
                "error_type": "DatasetBindingError",
                "error_message": "Artifact dataset identity did not match the bound dataset.",
            }
        )
        return _empty_artifact_receipt_result(
            "signed_dataset_binding_failed",
            required_modalities=allowed_modalities,
        )

    required_modalities = _ordered_media_modalities(allowed_modalities)
    allowed_modality_set = set(required_modalities)
    references = [
        reference
        for reference in _signed_artifact_refs(signed_dataset)
        if reference["modality"] in allowed_modality_set
    ]
    reference_modalities = _ordered_media_modalities(
        [reference["modality"] for reference in references]
    )
    calls.append(
        {
            "name": "get_dataset_artifact_links",
            "status": "ok",
            "summary": {
                "type": "dict",
                "id_present": True,
                "signed_artifact_reference_count": len(references),
            },
        }
    )
    if not references:
        return _empty_artifact_receipt_result(
            "no_signed_artifact_urls",
            required_modalities=required_modalities,
        )

    selected_references = references[:max_artifacts]
    receipts = [
        _download_artifact_receipt(
            reference,
            timeout=timeout,
            max_artifact_bytes=max_artifact_bytes,
            opener=opener,
        )
        for reference in selected_references
    ]
    receipts.sort(
        key=lambda receipt: (
            receipt["modality"],
            receipt["verification_status"],
            receipt["sha256"],
            receipt["byte_size"],
            receipt["response_mime"],
        )
    )
    verified_count = sum(
        receipt["verification_status"] == "verified" for receipt in receipts
    )
    verified_modalities = _ordered_media_modalities(
        [
            receipt["modality"]
            for receipt in receipts
            if receipt["verification_status"] == "verified"
        ]
    )
    missing_modalities = [
        modality
        for modality in required_modalities
        if modality not in set(verified_modalities)
    ]
    coverage_complete = bool(required_modalities) and not missing_modalities
    if (
        verified_count == len(references) == len(receipts)
        and coverage_complete
    ):
        status = "verified"
    elif verified_count:
        status = "partial"
    else:
        status = "failed"
    return {
        "artifact_receipt_status": status,
        "artifact_reference_count": len(references),
        "artifact_download_attempt_count": len(receipts),
        "artifact_download_verified_count": verified_count,
        "artifact_reference_modalities": reference_modalities,
        "artifact_verified_modalities": verified_modalities,
        "artifact_missing_modalities": missing_modalities,
        "artifact_modality_coverage_complete": coverage_complete,
        "artifact_receipts": receipts,
    }


def _signed_artifact_refs(payload: Any) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    def visit(node: Any, inherited_modality: str = "", inherited_mime: str = "") -> None:
        if isinstance(node, dict):
            mime = str(
                node.get("mime_type")
                or node.get("content_type")
                or inherited_mime
                or ""
            ).strip().lower()
            modality = _normalize_artifact_modality(
                node.get("modality") or node.get("media_type")
            )
            if not modality:
                modality = _modality_from_mime(mime)
            for key, value in node.items():
                normalized_key = str(key).strip().lower().replace("-", "_")
                if isinstance(value, str) and _is_artifact_url(
                    normalized_key,
                    value,
                ):
                    reference_modality = (
                        _modality_from_key(normalized_key)
                        or modality
                        or _modality_from_mime(mime)
                        or _modality_from_url_path(value)
                    )
                    if reference_modality and value not in seen_urls:
                        seen_urls.add(value)
                        references.append(
                            {
                                "url": value,
                                "modality": reference_modality,
                            }
                        )
                visit(value, modality, mime)
        elif isinstance(node, list):
            for item in node:
                visit(item, inherited_modality, inherited_mime)

    visit(_to_plain(payload))
    return references


def _is_artifact_url(
    key: str,
    value: str,
) -> bool:
    parsed = urlparse(value)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        return False
    if "url" not in key:
        return False
    if any(token in key for token in ("callback", "webpage", "source_page")):
        return False
    explicit_artifact_key = any(
        token in key
        for token in (
            "signed",
            "presigned",
            "download",
            "image",
            "audio",
            "video",
            "file",
            "document",
            "media",
        )
    )
    query = parsed.query.lower()
    has_signed_query = any(
        token in query
        for token in (
            "x-amz-signature=",
            "x-goog-signature=",
            "signature=",
            "sig=",
            "token=",
        )
    )
    return bool(
        explicit_artifact_key
        or has_signed_query
        or _modality_from_url_path(value)
    )


def _normalize_artifact_modality(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in MEDIA_MODALITIES:
        return normalized
    if normalized in {"document", "attachment"}:
        return "file"
    return ""


def _modality_from_key(key: str) -> str:
    for modality in ("image", "audio", "video"):
        if modality in key:
            return modality
    if "file" in key or "document" in key or "attachment" in key:
        return "file"
    return ""


def _modality_from_mime(mime: str) -> str:
    normalized = str(mime or "").split(";", 1)[0].strip().lower()
    for modality in ("image", "audio", "video"):
        if normalized.startswith(f"{modality}/"):
            return modality
    if normalized and normalized not in {"text/plain", "application/json"}:
        return "file"
    return ""


def _modality_from_url_path(value: str) -> str:
    path = urlparse(value).path.lower()
    suffixes = {
        "image": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"),
        "audio": (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".opus"),
        "video": (".mp4", ".mov", ".webm", ".avi", ".mkv"),
        "file": (
            ".pdf",
            ".csv",
            ".tsv",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".txt",
            ".html",
            ".htm",
            ".zip",
        ),
    }
    for modality, endings in suffixes.items():
        if path.endswith(endings):
            return modality
    return ""


def _download_artifact_receipt(
    reference: dict[str, str],
    *,
    timeout: int,
    max_artifact_bytes: int,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    modality = reference["modality"]
    empty_receipt = {
        "modality": modality,
        "verification_status": "download_failed",
        "sha256": "",
        "byte_size": 0,
        "response_mime": "",
    }
    url = reference.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        return {**empty_receipt, "verification_status": "invalid_url"}

    request = Request(
        url,
        headers={
            "Accept": "*/*",
            "User-Agent": "release-foundry-a2-artifact-verifier/1",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else url
            final_parsed = urlparse(str(final_url))
            if final_parsed.scheme.lower() != "https" or not final_parsed.netloc:
                return {**empty_receipt, "verification_status": "invalid_redirect"}

            headers = getattr(response, "headers", {})
            response_mime = str(
                headers.get("Content-Type", "") if hasattr(headers, "get") else ""
            ).split(";", 1)[0].strip().lower()
            content_length_value = (
                headers.get("Content-Length") if hasattr(headers, "get") else None
            )
            content_length = _int_or_none(content_length_value)
            if content_length is not None and content_length > max_artifact_bytes:
                return {
                    **empty_receipt,
                    "verification_status": "size_limit_exceeded",
                    "response_mime": response_mime,
                }

            digest = hashlib.sha256()
            byte_size = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                byte_size += len(chunk)
                if byte_size > max_artifact_bytes:
                    return {
                        **empty_receipt,
                        "verification_status": "size_limit_exceeded",
                        "response_mime": response_mime,
                    }
                digest.update(chunk)
    except Exception:  # pragma: no cover - live network failure surface.
        return empty_receipt

    if byte_size <= 0:
        return {
            **empty_receipt,
            "verification_status": "empty_body",
            "response_mime": response_mime,
        }
    observed_modality = _modality_from_mime(response_mime)
    if observed_modality in MEDIA_MODALITIES:
        modality = observed_modality
    return {
        "modality": modality,
        "verification_status": "verified",
        "sha256": digest.hexdigest(),
        "byte_size": byte_size,
        "response_mime": response_mime,
    }


def _sample_keys(items: list[Any]) -> list[str]:
    for item in items:
        if isinstance(item, dict):
            return sorted(str(key) for key in item.keys())
    return []


def _redacted_session(session: Any) -> dict[str, Any]:
    session = _to_plain(session)
    if not isinstance(session, dict):
        return {"session_reached": False}
    user = session.get("user") if isinstance(session.get("user"), dict) else {}
    tenant = session.get("tenant") if isinstance(session.get("tenant"), dict) else {}
    return {
        "session_reached": True,
        "status": str(session.get("status", "")),
        "user_id_present": user.get("id") is not None,
        "user_email_present": bool(user.get("email")),
        "tenant_id_present": tenant.get("id") is not None,
        "tenant_name_present": bool(tenant.get("tenant_name")),
        "note_count": len(session.get("notes", [])) if isinstance(session.get("notes"), list) else 0,
    }


def _request_for_name(payload: Any, request_name: str) -> dict[str, Any] | None:
    payload = _to_plain(payload)
    requests = payload.get("requests", []) if isinstance(payload, dict) else []
    matches = [
        request
        for request in requests
        if isinstance(request, dict)
        and str(request.get("request_name") or request.get("name") or "") == request_name
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Found {len(matches)} requests with the exact content-bound name; "
            "refusing to guess which paid request to reuse."
        )
    return matches[0] if matches else None


def _dataset_id_for_request(payload: Any, request_id: int) -> int | None:
    payload = _to_plain(payload)
    datasets = payload.get("datasets", []) if isinstance(payload, dict) else []
    matches = [
        dataset
        for dataset in datasets
        if isinstance(dataset, dict)
        and _int_or_none(dataset.get("request_id")) == request_id
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Found {len(matches)} datasets for request {request_id}; "
            "refusing to take the first dataset."
        )
    return _int_or_none(matches[0].get("id")) if matches else None


def _field(payload: Any, key: str) -> Any:
    payload = _to_plain(payload)
    return payload.get(key) if isinstance(payload, dict) else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_plain(payload: Any) -> Any:
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    if isinstance(payload, dict):
        return {str(key): _to_plain(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_to_plain(item) for item in payload]
    if hasattr(payload, "model_dump"):
        return _to_plain(payload.model_dump())
    if hasattr(payload, "dict"):
        return _to_plain(payload.dict())
    return str(payload)


def _redact_raw(payload: Any) -> Any:
    text = json.dumps(_to_plain(payload), ensure_ascii=False, sort_keys=True)
    return json.loads(_redact_sensitive_text(text))


def _safe_error_message(message: str) -> str:
    return _redact_sensitive_text(message)[:240]


def _redact_sensitive_text(message: str) -> str:
    for secret in (os.environ.get("RELEASEFOUNDRY_LABS_API_KEY", ""), os.environ.get("RELEASEFOUNDRY_API_KEY", "")):
        if secret:
            message = message.replace(secret, "[REDACTED_API_KEY]")
    message = re.sub(
        r"https?://[^\s\"'<>]+",
        lambda match: match.group(0).split("?", 1)[0] + "?[REDACTED_QUERY]"
        if "?" in match.group(0)
        else match.group(0),
        message,
    )
    message = re.sub(
        r"(?i)\bauthorization\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
        "Authorization: [REDACTED]",
        message,
    )
    message = re.sub(r"(?i)\bbearer\s+[^\s,;]+", "[REDACTED_AUTH]", message)
    message = re.sub(
        r"(?i)\b(?:cookie|set-cookie)\s*[:=]\s*[^,;\s]+",
        "Cookie: [REDACTED]",
        message,
    )
    message = re.sub(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|session(?:_id)?|token|signature|sig)"
        r"\s*=\s*[^&;,\s]+",
        "[REDACTED_SECRET]",
        message,
    )
    message = re.sub(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        "[REDACTED_EMAIL]",
        message,
    )
    return message


def _modality_evidence(
    *,
    request_created: bool,
    dataset: Any,
    requested_modalities: list[str] | tuple[str, ...] | None = None,
    verified_artifact_modalities: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    requested = list(requested_modalities or MODALITIES)
    requested_set = set(requested)
    observed = _observed_artifact_modalities(dataset)
    observed.update(
        modality
        for modality in (verified_artifact_modalities or [])
        if modality in MEDIA_MODALITIES
    )
    accepted = ["text"] if request_created and "text" in observed else []
    records: dict[str, dict[str, Any]] = {}
    for modality in MODALITIES:
        modality_requested = modality in requested_set
        request_accepted = request_created and modality_requested
        artifact_observed = modality in observed
        if modality == "text" and artifact_observed and request_accepted:
            input_support_status = "observed"
            grading_path = "native_text"
        elif artifact_observed:
            input_support_status = "not_proven"
            grading_path = "generated_artifact"
        elif request_accepted:
            input_support_status = "not_proven"
            grading_path = "request_configuration_only"
        else:
            input_support_status = "unknown"
            grading_path = "not_observed"
        records[modality] = {
            "requested": modality_requested,
            "request_accepted": request_accepted,
            "artifact_observed": artifact_observed,
            "grading_path": grading_path,
            "input_support_status": input_support_status,
            "evidence_status": (
                "artifact_observed"
                if artifact_observed
                else "request_config_accepted"
                if request_accepted
                else "not_observed"
            ),
        }
    return {
        "requested_modalities": requested,
        "request_config_accepted_modalities": requested if request_created else [],
        "observed_artifact_modalities": [modality for modality in MODALITIES if modality in observed],
        "accepted_modalities": accepted,
        "modalities": records,
    }


def _observed_artifact_modalities(payload: Any) -> set[str]:
    observed: set[str] = set()
    text_keys = {
        "content",
        "text",
        "prompt",
        "message",
        "transcript",
        "ocr_text",
        "description",
    }
    media_keys = {
        "image": "image",
        "images": "image",
        "image_url": "image",
        "audio": "audio",
        "audios": "audio",
        "audio_url": "audio",
        "video": "video",
        "videos": "video",
        "video_url": "video",
        "file": "file",
        "files": "file",
        "file_url": "file",
        "document": "file",
        "documents": "file",
    }
    extensions = {
        "image": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"),
        "audio": (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".opus"),
        "video": (".mp4", ".mov", ".webm", ".avi", ".mkv"),
        "file": (".pdf", ".csv", ".tsv", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"),
    }

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            mime_value = str(node.get("mime_type") or node.get("content_type") or "").lower()
            media_type = str(node.get("media_type") or node.get("modality") or "").lower()
            for modality in ("image", "audio", "video"):
                if mime_value.startswith(f"{modality}/") or media_type == modality:
                    observed.add(modality)
            if mime_value and not any(mime_value.startswith(f"{modality}/") for modality in ("image", "audio", "video")):
                observed.add("file")
            for key, value in node.items():
                normalized_key = str(key).lower().replace("-", "_")
                if normalized_key in text_keys and isinstance(value, str) and value.strip():
                    observed.add("text")
                keyed_modality = media_keys.get(normalized_key)
                if keyed_modality and _artifact_value_present(value):
                    observed.add(keyed_modality)
                if isinstance(value, str):
                    lowered = value.lower().split("?", 1)[0]
                    for modality, suffixes in extensions.items():
                        if lowered.endswith(suffixes):
                            observed.add(modality)
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(_to_plain(payload))
    return observed


def _artifact_value_present(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return bool(value)
    return False


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _to_plain(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
