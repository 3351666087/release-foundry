"""Versioned semantic evidence derived from immutable artifacts."""

from __future__ import annotations

from typing import Any

from .result_persistence import stable_hash


DERIVED_EVIDENCE_SCHEMA_VERSION = "a2.derived_evidence.v1"
SCOPE_FIELDS = (
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id",
)


def build_ocr_derived_evidence(
    *,
    tenant_scope: dict[str, str],
    artifact_id: str,
    content_hash: str,
    media_type: str,
    width: int,
    height: int,
    blocks: list[dict[str, Any]],
    extractor: dict[str, Any],
    extractor_qualification: dict[str, Any] | None = None,
    minimum_confidence: float = 0.75,
    provider_disclosure_allowed: bool = False,
    prompt_injection_status: str = "not_assessed",
    redaction_status: str = "not_assessed",
) -> dict[str, Any]:
    """Build private OCR evidence plus a hash-bound public-safe projection."""
    _validate_scope(tenant_scope)
    if media_type not in {"image/png", "image/jpeg"}:
        raise ValueError("OCR derived evidence requires a supported image media type")
    if not artifact_id or not _is_hash(content_hash):
        raise ValueError("artifact identity and content hash are required")
    if width <= 0 or height <= 0:
        raise ValueError("positive image dimensions are required")
    if not 0 <= minimum_confidence <= 1:
        raise ValueError("minimum_confidence must be between zero and one")
    if prompt_injection_status not in {"passed", "detected", "not_assessed"}:
        raise ValueError("unsupported prompt injection status")
    if redaction_status not in {"passed", "failed", "not_assessed"}:
        raise ValueError("unsupported redaction status")
    if provider_disclosure_allowed and redaction_status != "passed":
        raise ValueError("provider disclosure requires passed redaction")

    normalized_blocks: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "").strip()
        confidence = _finite_score(block.get("confidence"))
        polygon = _polygon(block.get("polygon"), width=width, height=height)
        if not text:
            blockers.append(f"ocr_block_{index}_text_empty")
        if confidence is None:
            blockers.append(f"ocr_block_{index}_confidence_invalid")
            confidence = 0.0
        if polygon is None:
            blockers.append(f"ocr_block_{index}_polygon_invalid")
            polygon = []
        normalized_blocks.append(
            {
                "block_id": f"ocr-{index + 1}",
                "reading_order": index,
                "text": text,
                "text_hash": stable_hash(text),
                "confidence": confidence,
                "polygon": polygon,
                "citation_id": stable_hash(
                    {
                        "artifact_id": artifact_id,
                        "content_hash": content_hash,
                        "block_index": index,
                        "text_hash": stable_hash(text),
                        "polygon": polygon,
                    }
                ),
            }
        )

    nonempty = [item for item in normalized_blocks if item["text"]]
    mean_confidence = (
        sum(float(item["confidence"]) for item in nonempty) / len(nonempty) if nonempty else 0.0
    )
    if not nonempty:
        blockers.append("ocr_text_empty")
    if mean_confidence < minimum_confidence:
        blockers.append("ocr_confidence_below_policy")
    extractor_core = _extractor_identity(extractor)
    production_qualified = _is_production_qualified(
        extractor_core,
        extractor_qualification,
    )
    extractor_core["production_qualified"] = production_qualified
    if not production_qualified:
        blockers.append("ocr_runtime_not_production_qualified")
    if prompt_injection_status != "passed":
        blockers.append(
            "ocr_prompt_injection_detected"
            if prompt_injection_status == "detected"
            else "ocr_prompt_injection_not_assessed"
        )
    if redaction_status != "passed":
        blockers.append(
            "ocr_redaction_failed"
            if redaction_status == "failed"
            else "ocr_redaction_not_assessed"
        )

    public_blocks = [
        {
            "block_id": item["block_id"],
            "reading_order": item["reading_order"],
            "text_hash": item["text_hash"],
            "confidence": item["confidence"],
            "polygon": item["polygon"],
            "citation_id": item["citation_id"],
        }
        for item in normalized_blocks
    ]
    public_core = {
        "schema_version": DERIVED_EVIDENCE_SCHEMA_VERSION,
        "tenant_scope": dict(tenant_scope),
        "artifact_id": artifact_id,
        "content_hash": content_hash,
        "media_type": media_type,
        "derivation_type": "ocr",
        "image": {"width": width, "height": height},
        "extractor": extractor_core,
        "blocks": public_blocks,
        "quality": {
            "block_count": len(nonempty),
            "mean_confidence": round(mean_confidence, 6),
            "minimum_confidence": minimum_confidence,
        },
        "status": "ready" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "prompt_injection": {
            "status": prompt_injection_status,
            "release_eligible": prompt_injection_status == "passed",
        },
        "redaction": {
            "status": redaction_status,
            "provider_disclosure_allowed": bool(provider_disclosure_allowed),
        },
        "semantic_ready": not blockers,
        "development_eligible": bool(nonempty)
        and mean_confidence >= minimum_confidence
        and prompt_injection_status == "passed"
        and redaction_status == "passed",
        "production_eligible": not blockers,
        "raw_artifact_included": False,
        "raw_text_in_public_projection": False,
        "public_safe": True,
    }
    public_core["derived_evidence_id"] = stable_hash(public_core)
    public_core["derived_evidence_hash"] = stable_hash(public_core)
    private_core = {
        **public_core,
        "blocks": normalized_blocks,
        "public_projection_hash": public_core["derived_evidence_hash"],
        "raw_text_in_public_projection": False,
        "public_safe": False,
    }
    private_core["derived_evidence_hash"] = stable_hash(
        {key: value for key, value in private_core.items() if key != "derived_evidence_hash"}
    )
    return private_core


def public_derived_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Validate private evidence and return its public-safe, text-free projection."""
    _validate_record(record)
    blocks = [
        {
            key: block[key]
            for key in (
                "block_id",
                "reading_order",
                "text_hash",
                "confidence",
                "polygon",
                "citation_id",
            )
        }
        for block in record["blocks"]
    ]
    projection = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "blocks",
            "public_projection_hash",
            "derived_evidence_hash",
        }
    }
    projection["blocks"] = blocks
    projection["public_safe"] = True
    projection["derived_evidence_hash"] = stable_hash(projection)
    if projection["derived_evidence_hash"] != record.get("public_projection_hash"):
        raise ValueError("derived evidence public projection hash mismatch")
    return projection


def provider_text_parts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return explicitly authorized OCR text parts without persisting the text."""
    parts: list[dict[str, Any]] = []
    for record in records:
        _validate_record(record)
        if (
            record["status"] != "ready"
            or record["redaction"]["provider_disclosure_allowed"] is not True
        ):
            continue
        text = "\n".join(block["text"] for block in record["blocks"] if block["text"])
        if not text:
            continue
        parts.append(
            {
                "modality": "text",
                "text": text,
                "source_modality": "image",
                "content_hash": record["content_hash"],
                "derived_evidence_hash": record["derived_evidence_hash"],
                "citation_ids": [block["citation_id"] for block in record["blocks"]],
            }
        )
    return parts


def _validate_record(record: dict[str, Any]) -> None:
    if record.get("schema_version") != DERIVED_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported derived evidence schema")
    _validate_scope(record.get("tenant_scope"))
    expected = stable_hash(
        {key: value for key, value in record.items() if key != "derived_evidence_hash"}
    )
    if record.get("derived_evidence_hash") != expected:
        raise ValueError("derived evidence hash mismatch")
    if not isinstance(record.get("blocks"), list):
        raise ValueError("derived evidence blocks are required")
    if record.get("status") not in {"ready", "blocked"}:
        raise ValueError("derived evidence status is invalid")
    blockers = record.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise ValueError("derived evidence blockers are invalid")
    ready = not blockers
    if (
        record.get("semantic_ready") is not ready
        or record.get("production_eligible") is not ready
        or (record.get("status") == "ready") is not ready
    ):
        raise ValueError("derived evidence readiness is inconsistent")
    for index, block in enumerate(record["blocks"]):
        _validate_block(record, block, index=index)


def _validate_block(record: dict[str, Any], block: Any, *, index: int) -> None:
    if not isinstance(block, dict):
        raise ValueError("derived evidence block is invalid")
    text = block.get("text")
    if not isinstance(text, str) or block.get("text_hash") != stable_hash(text):
        raise ValueError("derived evidence block text hash mismatch")
    image = record.get("image")
    if not isinstance(image, dict):
        raise ValueError("derived evidence image dimensions are required")
    polygon = _polygon(
        block.get("polygon"),
        width=int(image.get("width") or 0),
        height=int(image.get("height") or 0),
    )
    if polygon is None or polygon != block.get("polygon"):
        raise ValueError("derived evidence block polygon is invalid")
    confidence = _finite_score(block.get("confidence"))
    if confidence is None or confidence != block.get("confidence"):
        raise ValueError("derived evidence block confidence is invalid")
    citation = stable_hash(
        {
            "artifact_id": record.get("artifact_id"),
            "content_hash": record.get("content_hash"),
            "block_index": index,
            "text_hash": block.get("text_hash"),
            "polygon": polygon,
        }
    )
    if (
        block.get("block_id") != f"ocr-{index + 1}"
        or block.get("reading_order") != index
        or block.get("citation_id") != citation
    ):
        raise ValueError("derived evidence block citation is invalid")


def _validate_scope(scope: Any) -> None:
    if (
        not isinstance(scope, dict)
        or set(scope) != set(SCOPE_FIELDS)
        or any(not isinstance(scope[field], str) or not scope[field] for field in SCOPE_FIELDS)
    ):
        raise ValueError("complete five-field tenant scope is required")


def _extractor_identity(extractor: dict[str, Any]) -> dict[str, Any]:
    required = (
        "extractor_id",
        "extractor_version",
        "runtime_id",
        "runtime_version",
        "model_id",
        "model_hash",
        "config_hash",
        "dictionary_hash",
    )
    if any(key not in extractor for key in required):
        raise ValueError("complete extractor identity is required")
    if any(
        not _is_hash(str(extractor[key]))
        for key in ("model_hash", "config_hash", "dictionary_hash")
    ):
        raise ValueError("extractor supply-chain hashes are invalid")
    return {key: extractor[key] for key in required}


def _is_production_qualified(
    extractor: dict[str, Any],
    qualification: dict[str, Any] | None,
) -> bool:
    """Resolve qualification from a trusted policy record, never producer metadata."""
    if not isinstance(qualification, dict):
        return False
    expected = {**extractor, "production_qualified": True}
    return qualification == expected


def _finite_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score or score < 0 or score > 1:
        return None
    return round(score, 6)


def _polygon(value: Any, *, width: int, height: int) -> list[list[float]] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    points: list[list[float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return None
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            return None
        if x != x or y != y or x < 0 or y < 0 or x > width or y > height:
            return None
        points.append([round(x, 3), round(y, 3)])
    return points


def _is_hash(value: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(char in "0123456789abcdef" for char in value[7:])
    )
