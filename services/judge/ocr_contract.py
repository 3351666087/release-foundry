"""Provider-independent OCR observation contracts for A2 multimodal evaluation."""

from __future__ import annotations

import time
import re
from typing import Any

from .result_persistence import stable_hash

_SHA256_REF = re.compile(r"^sha256:[a-f0-9]{64}$")


def run_optional_ocr_adapter(
    *,
    image_path: str,
    adapter_id: str,
    adapter_version_hash: str,
    adapter: Any | None,
    minimum_confidence: float = 0.0,
) -> dict[str, Any]:
    """Run an OCR adapter while keeping text, confidence and geometry non-authoritative."""
    if not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError("minimum_confidence must be between zero and one")
    if _SHA256_REF.fullmatch(adapter_version_hash) is None:
        raise ValueError("adapter_version_hash must be a sha256 reference")
    started = time.perf_counter()
    try:
        import psutil

        process = psutil.Process()
        rss_before = process.memory_info().rss
    except (ImportError, OSError):
        process = None
        rss_before = None
    base = {
        "adapter_id": adapter_id,
        "adapter_version_hash": adapter_version_hash,
        "minimum_confidence": minimum_confidence,
        "release_authority": False,
        "public_safe": True,
    }
    if adapter is None:
        return {
            **base,
            "state": "unavailable",
            "text": "",
            "text_hash": "",
            "token_boxes_hash": "",
            "token_count": 0,
            "minimum_observed_confidence": None,
            "confidence_summary": {"count": 0, "minimum": None, "maximum": None, "mean": None},
            "latency_ms": 0.0,
            "process_rss_before_bytes": rss_before,
            "process_rss_after_bytes": rss_before,
            "process_rss_delta_bytes": 0 if rss_before is not None else None,
            "blockers": ["ocr_adapter_unavailable"],
        }
    try:
        raw = adapter(image_path)
        if isinstance(raw, dict):
            text = str(raw.get("text") or "").strip()
            tokens = list(raw.get("tokens") or [])
        else:
            text = str(raw).strip()
            tokens = []
        confidences = [
            float(token["confidence"])
            for token in tokens
            if isinstance(token, dict) and token.get("confidence") is not None
        ]
        observed = min(confidences) if confidences else None
        rss_after = process.memory_info().rss if process is not None else None
        blockers = (
            ["ocr_confidence_below_policy"]
            if observed is not None and observed < minimum_confidence
            else []
        )
        return {
            **base,
            "state": "completed",
            "text": text,
            "text_hash": stable_hash(text),
            # Geometry is audit-bound but deliberately not returned.
            "token_boxes_hash": stable_hash(tokens) if tokens else "",
            "token_count": len(tokens),
            "minimum_observed_confidence": observed,
            "confidence_summary": {
                "count": len(confidences),
                "minimum": observed,
                "maximum": max(confidences) if confidences else None,
                "mean": sum(confidences) / len(confidences) if confidences else None,
            },
            "latency_ms": (time.perf_counter() - started) * 1000,
            "process_rss_before_bytes": rss_before,
            "process_rss_after_bytes": rss_after,
            "process_rss_delta_bytes": (
                rss_after - rss_before
                if rss_after is not None and rss_before is not None
                else None
            ),
            "blockers": blockers,
        }
    except Exception:
        return {
            **base,
            "state": "failed",
            "text": "",
            "text_hash": "",
            "token_boxes_hash": "",
            "token_count": 0,
            "minimum_observed_confidence": None,
            "confidence_summary": {"count": 0, "minimum": None, "maximum": None, "mean": None},
            "latency_ms": (time.perf_counter() - started) * 1000,
            "process_rss_before_bytes": rss_before,
            "process_rss_after_bytes": process.memory_info().rss if process is not None else None,
            "process_rss_delta_bytes": None,
            "blockers": ["ocr_adapter_failed"],
        }


def compare_ocr_with_fixture_text(*, ocr_text: str, fixture_text: str) -> dict[str, Any]:
    def normalized(value: str) -> str:
        return "".join(character.lower() for character in value if character.isalnum())

    matched = normalized(fixture_text) in normalized(ocr_text)
    return {
        "ocr_text_hash": stable_hash(ocr_text),
        "fixture_text_hash": stable_hash(fixture_text),
        "match_state": "matched" if matched else "disagreement",
        "human_review_required": not matched,
        "release_authority": False,
        "blockers": [] if matched else ["ocr_fixture_text_disagreement"],
        "public_safe": True,
    }


def build_offline_ocr_closure(*, ocr_observation: dict[str, Any]) -> dict[str, Any]:
    """Prove OCR provider failure does not disable deterministic release closure."""
    available = ocr_observation.get("state") == "completed" and not ocr_observation.get("blockers")
    return {
        "ocr_usable": available,
        "deterministic_closure_available": True,
        "decision_ceiling": "human_review" if available else "incomplete",
        "release_authority": False,
        "blockers": [] if available else ["ocr_observation_not_qualified"],
        "public_safe": True,
    }
