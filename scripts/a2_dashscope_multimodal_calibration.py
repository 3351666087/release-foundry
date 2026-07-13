from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

import jsonschema
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_ollama_multimodal_matrix import (
    OUTPUT_SCHEMA,
    PROMPT,
    atomic_write,
    classify_public_response,
    sha256_ref,
)


SCHEMA = ROOT / "docs/a2/schemas/dashscope_multimodal_calibration.schema.json"


def build_calibration(
    *,
    cases: list[dict[str, Any]],
    model_id: str,
    endpoint_class: str,
    invoke: Callable[[dict[str, Any], float], dict[str, Any]],
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    observations = []
    for case in cases:
        artifact_path = ROOT / case["artifact_path"]
        artifact = artifact_path.read_bytes()
        if sha256_ref(artifact) != case["artifact_hash"]:
            raise ValueError(f"artifact hash mismatch: {case['case_id']}")
        suffix = artifact_path.suffix.lower()
        transmitted_artifact = artifact
        mime = "image/png"
        if suffix == ".ppm":
            converted = io.BytesIO()
            with Image.open(io.BytesIO(artifact)) as image:
                image.convert("RGB").save(
                    converted,
                    format="PNG",
                    optimize=False,
                    compress_level=9,
                )
            transmitted_artifact = converted.getvalue()
        elif suffix != ".png":
            raise ValueError(f"unsupported cloud image format: {suffix}")
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,"
                                + base64.b64encode(transmitted_artifact).decode("ascii")
                            },
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        started = time.monotonic()
        http_state = "completed"
        error_class = ""
        content = ""
        response_model_id = ""
        try:
            envelope = invoke(payload, timeout_seconds)
            choices = envelope.get("choices") or []
            message = choices[0].get("message") if choices else {}
            content = str((message or {}).get("content") or "")
            response_model_id = str(envelope.get("model") or "")
        except TimeoutError:
            http_state = "failed"
            error_class = "timeout"
        except PermissionError:
            http_state = "failed"
            error_class = "authentication_or_authorization_failed"
        except ValueError:
            http_state = "failed"
            error_class = "provider_rejected_request"
        except Exception:
            http_state = "failed"
            error_class = "provider_failure"
        parse_state, observed_risk = (
            classify_public_response(content)
            if http_state == "completed"
            else ("not_attempted", None)
        )
        observations.append(
            {
                "case_id": case["case_id"],
                "taxonomy": case["taxonomy"],
                "expected_risk": case["expected_risk"],
                "artifact_hash": case["artifact_hash"],
                "request_hash": sha256_ref(
                    json.dumps(payload, sort_keys=True, separators=(",", ":"))
                ),
                "response_hash": sha256_ref(content) if http_state == "completed" else "",
                "response_model_id": response_model_id,
                "http_state": http_state,
                "parse_state": parse_state,
                "observed_risk": observed_risk,
                "wall_seconds": round(time.monotonic() - started, 3),
                "error_class": error_class,
                "raw_payload_included": False,
                "release_authority": False,
            }
        )
    eligible = [item for item in observations if item["parse_state"] == "valid_json"]
    safe = [item for item in eligible if not item["expected_risk"]]
    attack = [item for item in eligible if item["expected_risk"]]
    blockers = []
    if len(safe) < 5:
        blockers.append("dashscope_safe_sample_minimum_not_met")
    if len(attack) < 5:
        blockers.append("dashscope_attack_sample_minimum_not_met")
    if any(item["parse_state"] != "valid_json" for item in observations):
        blockers.append("dashscope_invalid_structured_output_observed")
    if any(item["http_state"] != "completed" for item in observations):
        blockers.append("dashscope_provider_failure_observed")
    sensitivity = (
        sum(item["observed_risk"] is True for item in attack) / len(attack)
        if attack
        else None
    )
    specificity = (
        sum(item["observed_risk"] is False for item in safe) / len(safe)
        if safe
        else None
    )
    result = {
        "schema_version": "a2.dashscope_multimodal_calibration.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider_id": "dashscope",
        "model_id": model_id,
        "endpoint_class": endpoint_class,
        "credential_source": "environment:DASHSCOPE_API_KEY",
        "prompt_hash": sha256_ref(PROMPT),
        "output_schema_hash": sha256_ref(
            json.dumps(OUTPUT_SCHEMA, sort_keys=True, separators=(",", ":"))
        ),
        "observations": observations,
        "metrics": {
            "eligible_count": len(eligible),
            "safe_count": len(safe),
            "attack_count": len(attack),
            "sensitivity": sensitivity,
            "specificity": specificity,
            "balanced_accuracy": (
                (sensitivity + specificity) / 2
                if sensitivity is not None and specificity is not None
                else None
            ),
        },
        "qualification_state": "blocked" if blockers else "qualified_for_review",
        "blockers": blockers,
        "secret_included": False,
        "release_authority": False,
        "public_safe": True,
    }
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    ).validate(result)
    return result


def http_invoke(endpoint: str, api_key: str) -> Callable[[dict[str, Any], float], dict[str, Any]]:
    def invoke(payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        req = request.Request(
            endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError from exc
            raise ValueError from exc
        except error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError from exc
            raise

    return invoke


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an opt-in, hash-safe DashScope multimodal calibration."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="qwen-vl-plus")
    parser.add_argument(
        "--endpoint",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    parser.add_argument("--execute-live", action="store_true")
    args = parser.parse_args()
    if not args.execute_live:
        raise SystemExit("--execute-live is required; live cloud calls are opt-in")
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is unavailable")
    cases = json.loads((ROOT / args.manifest).read_text(encoding="utf-8"))["cases"]
    result = build_calibration(
        cases=cases,
        model_id=args.model,
        endpoint_class="dashscope_openai_compatible_legacy_china",
        invoke=http_invoke(args.endpoint, api_key),
    )
    atomic_write(ROOT / args.output, result)
    print(
        f"wrote {args.output}: eligible={result['metrics']['eligible_count']} "
        f"qualification={result['qualification_state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
