"""Isolated execution boundary for artifact extractors."""

from __future__ import annotations

import base64
from dataclasses import asdict
import json
import subprocess
import sys
import time
from typing import Any

from .artifact_pipeline import ArtifactLimits
from .result_persistence import stable_hash


WORKER_PROTOCOL_VERSION = "a2.extractor_worker.v1"


class SubprocessExtractorRuntime:
    """Run the deterministic parser in a separate, time-bounded process."""

    runtime_id = "a2.python_subprocess"
    runtime_version = "1.0.0"

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        python_executable: str | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self.python_executable = python_executable or sys.executable

    def extract(
        self,
        content: bytes,
        *,
        media_type: str,
        input_hash: str,
        limits: ArtifactLimits,
    ) -> dict[str, Any]:
        request = {
            "protocol_version": WORKER_PROTOCOL_VERSION,
            "media_type": media_type,
            "input_hash": input_hash,
            "limits": asdict(limits),
            "content_base64": base64.b64encode(content).decode("ascii"),
        }
        config_hash = stable_hash(
            {
                "runtime_id": self.runtime_id,
                "runtime_version": self.runtime_version,
                "protocol_version": WORKER_PROTOCOL_VERSION,
                "limits": request["limits"],
            }
        )
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [self.python_executable, "-B", "-m", "services.judge.extractor_worker"],
                input=json.dumps(request, separators=(",", ":")),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _runtime_failure(
                media_type,
                input_hash,
                "extractor_timeout",
                "TimeoutExpired",
                self,
                config_hash,
                started,
            )
        if completed.returncode != 0:
            return _runtime_failure(
                media_type,
                input_hash,
                "extractor_worker_failed",
                "WorkerProcessError",
                self,
                config_hash,
                started,
                exit_code=completed.returncode,
            )
        try:
            result = json.loads(completed.stdout)
        except (TypeError, ValueError):
            return _runtime_failure(
                media_type,
                input_hash,
                "extractor_protocol_error",
                "InvalidWorkerResponse",
                self,
                config_hash,
                started,
                exit_code=completed.returncode,
            )
        if (
            not isinstance(result, dict)
            or result.get("input_hash") != input_hash
            or result.get("media_type") != media_type
        ):
            return _runtime_failure(
                media_type,
                input_hash,
                "extractor_protocol_error",
                "WorkerBindingMismatch",
                self,
                config_hash,
                started,
                exit_code=completed.returncode,
            )
        return _with_execution(
            result,
            runtime=self,
            config_hash=config_hash,
            started=started,
            exit_code=completed.returncode,
        )


def _with_execution(
    result: dict[str, Any],
    *,
    runtime: SubprocessExtractorRuntime,
    config_hash: str,
    started: float,
    exit_code: int | None,
) -> dict[str, Any]:
    core = {key: value for key, value in result.items() if key != "extraction_hash"}
    core["execution"] = {
        "isolation": "subprocess",
        "runtime_id": runtime.runtime_id,
        "runtime_version": runtime.runtime_version,
        "protocol_version": WORKER_PROTOCOL_VERSION,
        "config_hash": config_hash,
        "latency_ms": max(0, round((time.monotonic() - started) * 1000)),
        "exit_code": exit_code,
    }
    return {**core, "extraction_hash": stable_hash(core)}


def _runtime_failure(
    media_type: str,
    input_hash: str,
    blocker: str,
    error_class: str,
    runtime: SubprocessExtractorRuntime,
    config_hash: str,
    started: float,
    *,
    exit_code: int | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": "a2.artifact_extraction.v1",
        "extractor_id": "a2.extraction_worker",
        "extractor_version": "1.0.0",
        "media_type": media_type,
        "input_hash": input_hash,
        "status": "failed",
        "metadata": {},
        "quality": {
            "score": 0.0,
            "signals": [],
            "limitations": ["isolated_worker_did_not_complete"],
        },
        "blockers": [blocker],
        "error_class": error_class,
        "raw_content_included": False,
        "derived_content_included": False,
    }
    return _with_execution(
        result,
        runtime=runtime,
        config_hash=config_hash,
        started=started,
        exit_code=exit_code,
    )
