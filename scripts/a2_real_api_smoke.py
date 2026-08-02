from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SDK_PATH = ROOT / "packages" / "sdk"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an optional real ReleaseFoundry API smoke check and save a redacted summary."
    )
    parser.add_argument("--output", default="docs/evidence/a2_real_api_smoke.json")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    if not os.environ.get("RELEASEFOUNDRY_API_KEY"):
        raise SystemExit("RELEASEFOUNDRY_API_KEY is required; the script never reads key files directly.")

    _ensure_releasefoundry_sdk_importable()
    from releasefoundry import ReleaseFoundryClient  # type: ignore

    client = ReleaseFoundryClient.from_env(timeout=args.timeout)
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
        "base_url": os.environ.get("RELEASEFOUNDRY_BASE_URL", "https://api.releasefoundry.example/testing-platform-api"),
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
    sys.path.insert(0, str(SDK_PATH))
    if importlib.util.find_spec("releasefoundry") is None:
        raise RuntimeError("releasefoundry is not installed and packages/sdk is unavailable.")


def _sdk_source() -> str:
    spec = importlib.util.find_spec("releasefoundry")
    if not spec or not spec.origin:
        return "installed"
    origin = Path(spec.origin).resolve()
    try:
        return origin.relative_to(ROOT).as_posix()
    except ValueError:
        return str(origin)


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
    email = str(user.get("email", ""))
    return {
        "session_reached": True,
        "status": str(session.get("status", "")),
        "user_id_present": user.get("id") is not None,
        "user_email_sha256_12": hashlib.sha256(email.encode("utf-8")).hexdigest()[:12] if email else "",
        "tenant_id_present": tenant.get("id") is not None,
        "tenant_name_present": bool(tenant.get("tenant_name")),
        "note_count": len(session.get("notes", [])) if isinstance(session.get("notes"), list) else 0,
    }


def _safe_error_message(message: str) -> str:
    api_key = os.environ.get("RELEASEFOUNDRY_API_KEY", "")
    if api_key:
        message = message.replace(api_key, "[REDACTED_API_KEY]")
    return message[:240]


if __name__ == "__main__":
    raise SystemExit(main())
