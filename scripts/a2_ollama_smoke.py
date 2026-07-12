"""Opt-in local Ollama text/image smoke that emits only public-safe JSON evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path

from services.judge.provider_gateway import OllamaAdapter, ProviderDefinition, ProviderGateway
from services.judge.provider_runtime import build_local_smoke_evidence
from services.judge.result_persistence import stable_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--model-digest", default="")
    parser.add_argument("--num-predict", type=int, default=24)
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be finite and strictly positive")
    if args.num_predict < 1 or args.num_predict > 256:
        parser.error("--num-predict must be between 1 and 256")
    parts = [{"modality": "text", "text": "Return a small JSON object with a boolean field named passed."}]
    hashes = []
    if args.image:
        image_bytes = args.image.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        digest = hashlib.sha256(image_bytes).hexdigest()
        hashes.append(digest)
        parts.append({"modality": "image", "data": encoded, "content_hash": digest})
    snapshot_core = {"tenant_id": "local-smoke", "completeness": "complete", "source": "local"}
    snapshot = {
        **snapshot_core,
        "snapshot_id": stable_hash(snapshot_core),
        "snapshot_hash": stable_hash(snapshot_core),
    }
    provider = ProviderDefinition(
        "ollama-local",
        "ollama",
        args.base_url,
        "",
        frozenset({"text", "image"}),
        frozenset({"local-smoke"}),
        data_residency="local",
    )
    result = ProviderGateway([provider], {"ollama": OllamaAdapter()}).invoke(
        tenant_id="local-smoke",
        snapshot=snapshot,
        provider_id="ollama-local",
        model_id=args.model,
        parts=parts,
        idempotency_key=stable_hash({"model": args.model, "hashes": hashes}),
        timeout_seconds=args.timeout_seconds,
        model_options={"num_predict": args.num_predict, "temperature": 0},
    )
    evidence = build_local_smoke_evidence(
        modality="image" if args.image else "text",
        model_id=args.model,
        provider_result=result,
        content_hashes=hashes,
        model_digest=args.model_digest,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
