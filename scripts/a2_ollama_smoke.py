"""Opt-in local Ollama text/image smoke that emits only public-safe JSON evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    parser.add_argument("--max-image-bytes", type=int, default=10 * 1024 * 1024)
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be finite and strictly positive")
    if args.num_predict < 1 or args.num_predict > 256:
        parser.error("--num-predict must be between 1 and 256")
    if args.max_image_bytes < 1 or args.max_image_bytes > 50 * 1024 * 1024:
        parser.error("--max-image-bytes must be between 1 and 52428800")
    parts = [{"modality": "text", "text": "Return a small JSON object with a boolean field named passed."}]
    hashes = []
    if args.image:
        if args.image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            parser.error("--image must use .png, .jpg, .jpeg, or .webp")
        image_size = args.image.stat().st_size
        if image_size > args.max_image_bytes:
            parser.error(f"--image exceeds --max-image-bytes ({image_size} > {args.max_image_bytes})")
        image_bytes = args.image.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        digest = "sha256:" + hashlib.sha256(image_bytes).hexdigest()
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
    started = time.monotonic()
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
        duration_seconds=time.monotonic() - started,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
