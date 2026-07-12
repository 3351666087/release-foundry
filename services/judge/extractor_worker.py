"""JSON-over-stdio worker for bounded artifact extraction."""

from __future__ import annotations

import base64
import json
import sys

from .artifact_pipeline import ArtifactLimits, extract_artifact
from .extractor_runtime import WORKER_PROTOCOL_VERSION


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        if request.get("protocol_version") != WORKER_PROTOCOL_VERSION:
            return 2
        content = base64.b64decode(request["content_base64"], validate=True)
        limits = ArtifactLimits(**request["limits"])
        result = extract_artifact(
            content,
            media_type=str(request["media_type"]),
            input_hash=str(request["input_hash"]),
            limits=limits,
        )
        sys.stdout.write(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 0
    except Exception:
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
