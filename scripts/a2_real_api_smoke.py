from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "docs" / "a1" / "_pypi_artifacts" / "releasefoundry-0.3.1-py3-none-any.whl"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an optional real ReleaseFoundry API smoke check and save a redacted summary."
    )
    parser.add_argument("--output", default="docs/evidence/a2_real_api_smoke.json")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    if not os.environ.get("RELEASEFOUNDRY_LABS_API_KEY"):
        raise SystemExit("RELEASEFOUNDRY_LABS_API_KEY is required; the script never reads key files directly.")

    _ensure_releasefoundry_sdk_importable()
    from releasefoundry import ReleaseFoundryLabsClient  # type: ignore

    client = ReleaseFoundryLabsClient.from_env(timeout=args.timeout)
    calls: list[dict[str, Any]] = []

    session = _record_call(calls, "init", client.init)
    _record_call(calls, "health_check", client.health_check)
    _record_call(calls, "list_datasets", lambda: client.list_datasets(limit=5, include_signed_urls=False))
    _record_call(calls, "list_runs", lambda: client.list_runs(limit=5))
    _record_call(calls, "list_requests", lambda: client.list_requests(limit=5))
    _record_call(calls, "list_agents", client.list_agents)

    summary = {
        "schema_version": "a2.real_api_smoke.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sdk_source": _sdk_source(),
        "base_url": os.environ.get("RELEASEFOUNDRY_LABS_BASE_URL", "https://api.releasefoundry.io/testing-platform-api"),
        "auth": _redacted_session(session),
        "api_call_count": len(calls),
        "calls": calls,
        "all_required_calls_reached": all(call["status"] == "ok" for call in calls[:3]),
        "notes": [
            "This file is a redacted real-API calibration summary.",
            "No API key, signed media URL, dataset payload, run payload, or raw private response is stored.",
            "Local deterministic unit tests must not depend on this smoke result.",
        ],
    }

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "real API smoke wrote {path}: {ok}/{total} calls ok".format(
            path=output.as_posix(),
            ok=sum(1 for call in calls if call["status"] == "ok"),
            total=len(calls),
        )
    )
    return 0


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


def _record_call(calls: list[dict[str, Any]], name: str, fn: Callable[[], Any]) -> Any:
    try:
        payload = fn()
    except Exception as exc:  # pragma: no cover - only exercised against live API failures.
        calls.append(
            {
                "name": name,
                "status": "error",
                "error_type": exc.__class__.__name__,
                "error_message": _safe_error_message(str(exc)),
            }
        )
        return None

    calls.append({"name": name, "status": "ok", "summary": _summarize_payload(payload)})
    return payload


def _summarize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        return {"type": "list", "count": len(payload), "item_keys": _sample_keys(payload)}
    if isinstance(payload, dict):
        summary: dict[str, Any] = {
            "type": "dict",
            "keys": sorted(str(key) for key in payload.keys()),
        }
        for key in ("datasets", "runs", "requests", "agents", "api_keys", "notes"):
            value = payload.get(key)
            if isinstance(value, list):
                summary[f"{key}_count"] = len(value)
                summary[f"{key}_item_keys"] = _sample_keys(value)
        if "status" in payload:
            summary["status_value"] = str(payload.get("status"))
        return summary
    return {"type": type(payload).__name__}


def _sample_keys(items: list[Any]) -> list[str]:
    for item in items:
        if isinstance(item, dict):
            return sorted(str(key) for key in item.keys())
    return []


def _redacted_session(session: Any) -> dict[str, Any]:
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


if __name__ == "__main__":
    raise SystemExit(main())
