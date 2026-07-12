"""Evaluate an authenticated A1 evidence bundle through the A2 release spine."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.bundle_evaluation import evaluate_a1_bundle
from services.judge.provider_gateway import OllamaAdapter, ProviderDefinition, ProviderGateway
from services.judge.provider_runtime import EnvironmentCredentialResolver, OpenAICompatibleAdapter, validate_semantic_judge_output
from services.judge.sql_store import initialize_sql_store


def main() -> int:
    parser = argparse.ArgumentParser(description="A1 bundle -> A2 Judge -> PASS/BLOCK/INCOMPLETE")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default="-", type=str)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--provider", choices=("ollama", "openai-compatible"), required=True)
    parser.add_argument("--provider-id", default="local-judge")
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--credential-env", default="")
    parser.add_argument("--bundle-key-env", default="A1_EVIDENCE_HMAC_KEY")
    parser.add_argument("--now-unix-ms", required=True, type=int)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("input must be one JSON object")
    payload["provider_id"] = args.provider_id
    payload["model_id"] = args.model
    tenant = str(payload.get("tenant_id") or "")
    modalities = frozenset(str(item) for item in payload.get("provider_modalities", ["text", "image"]))
    credential_ref = ""
    adapters = {"ollama": OllamaAdapter()}
    protocol = "ollama"
    if args.provider == "openai-compatible":
        if not args.credential_env:
            raise SystemExit("--credential-env is required for openai-compatible")
        secret = os.environ.get(args.credential_env, "")
        if not secret:
            raise SystemExit("configured Provider credential environment variable is unavailable")
        credential_ref = f"secret://cli/{args.provider_id}"
        adapters = {"openai_compatible": OpenAICompatibleAdapter(EnvironmentCredentialResolver({credential_ref: secret}))}
        protocol = "openai_compatible"
    provider = ProviderDefinition(args.provider_id, protocol, args.base_url, credential_ref, modalities, frozenset({tenant}), data_residency="local" if args.provider == "ollama" else "unspecified")
    gateway = ProviderGateway([provider], adapters, response_validator=validate_semantic_judge_output)

    key = os.environ.get(args.bundle_key_env, "")
    if not key:
        raise SystemExit("configured A1 evidence verification key environment variable is unavailable")
    args.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.database)
    try:
        initialize_sql_store(connection)
        result = evaluate_a1_bundle(payload, gateway=gateway, key_resolver=lambda _: key.encode("utf-8"), now_unix_ms=args.now_unix_ms, persistence_connection=connection)
    finally:
        connection.close()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        print(text, end="")
    else:
        Path(args.output).write_text(text, encoding="utf-8")
    return {"PASS": 0, "BLOCK": 2, "INCOMPLETE": 3}[result["decision"]]


if __name__ == "__main__":
    raise SystemExit(main())
