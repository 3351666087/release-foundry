"""Evaluate an authenticated A1 evidence bundle through the A2 release spine."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.bundle_evaluation import evaluate_a1_bundle
from services.judge.evaluation_trust_policy import normalize_evaluation_trust_policy
from services.judge.provider_gateway import OllamaAdapter, ProviderDefinition, ProviderGateway
from services.judge.provider_runtime import EnvironmentCredentialResolver, OllamaDiscovery, OpenAICompatibleAdapter, validate_semantic_judge_output
from services.judge.sql_store import initialize_sql_store


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} could not be loaded as JSON") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be one JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="A1 bundle -> A2 Judge -> PASS/BLOCK/INCOMPLETE")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default="-", type=str)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--provider", choices=("ollama", "openai-compatible", "qwen"), required=True)
    parser.add_argument("--provider-id", default="local-judge")
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--credential-env", default="")
    parser.add_argument("--quality-proof", type=Path)
    parser.add_argument("--trust-policy", type=Path)
    parser.add_argument("--bundle-key-env", default="A1_EVIDENCE_HMAC_KEY")
    parser.add_argument("--model-storage-path", type=Path)
    parser.add_argument("--minimum-free-gb", type=float, default=0)
    parser.add_argument("--now-unix-ms", required=True, type=int)
    args = parser.parse_args()

    payload = _read_json_object(args.input, "input")
    if args.quality_proof:
        quality_proof = _read_json_object(args.quality_proof, "quality proof")
        payload["evaluation_quality_proof"] = quality_proof
    trust_policy = None
    if args.trust_policy:
        trust_policy = normalize_evaluation_trust_policy(
            _read_json_object(args.trust_policy, "trust policy")
        )
    payload["provider_id"] = args.provider_id
    payload["model_id"] = args.model
    tenant = str(payload.get("tenant_id") or "")
    modalities = frozenset(str(item) for item in payload.get("provider_modalities", ["text", "image"]))
    credential_ref = ""
    adapters = {"ollama": OllamaAdapter()}
    protocol = "ollama"
    base_url = args.base_url
    credential_env = args.credential_env
    if args.provider == "qwen":
        base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        credential_env = credential_env or "DASHSCOPE_API_KEY"
    if args.provider in {"openai-compatible", "qwen"}:
        if not credential_env:
            raise SystemExit("--credential-env is required for openai-compatible")
        secret = os.environ.get(credential_env, "")
        if not secret:
            raise SystemExit("configured Provider credential environment variable is unavailable")
        credential_ref = f"secret://cli/{args.provider_id}"
        adapters = {"openai_compatible": OpenAICompatibleAdapter(EnvironmentCredentialResolver({credential_ref: secret}))}
        protocol = "openai_compatible"
    if not base_url:
        raise SystemExit("--base-url is required for this provider")
    provider = ProviderDefinition(args.provider_id, protocol, base_url, credential_ref, modalities, frozenset({tenant}), data_residency="local" if args.provider == "ollama" else "unspecified")
    gateway = ProviderGateway([provider], adapters, response_validator=validate_semantic_judge_output)

    key = os.environ.get(args.bundle_key_env, "")
    if not key:
        raise SystemExit("configured A1 evidence verification key environment variable is unavailable")
    if args.provider == "ollama":
        if args.model_storage_path:
            _validate_model_storage(args.model_storage_path, args.minimum_free_gb)
        _validate_ollama_model(payload, args.model, base_url)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.database)
    try:
        initialize_sql_store(connection)
        result = evaluate_a1_bundle(
            payload, gateway=gateway, key_resolver=lambda _: key.encode("utf-8"),
            now_unix_ms=args.now_unix_ms, persistence_connection=connection,
            quality_trust_policy=trust_policy,
        )
    finally:
        connection.close()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        print(text, end="")
    else:
        Path(args.output).write_text(text, encoding="utf-8")
    return {"PASS": 0, "BLOCK": 2, "INCOMPLETE": 3}[result["decision"]]


def _validate_ollama_model(payload: dict[str, object], model_id: str, base_url: str) -> None:
    required = {"text", *(str(item) for item in payload.get("required_modalities", ["text"]))}
    try:
        records = OllamaDiscovery().discover(base_url)
    except Exception as exc:
        raise SystemExit("Ollama capability discovery is unavailable") from exc
    record = next((item for item in records if item.model_id == model_id), None)
    if record is None:
        raise SystemExit("configured Ollama model was not discovered")
    missing = sorted(required - record.modalities)
    if missing:
        raise SystemExit("configured Ollama model lacks required modalities: " + ",".join(missing))


def _validate_model_storage(path: Path, minimum_free_gb: float) -> None:
    resolved = path.expanduser().resolve()
    existing = next((item for item in (resolved, *resolved.parents) if item.exists()), None)
    if existing is None:
        raise SystemExit("configured model storage path has no existing parent")
    free_gb = shutil.disk_usage(existing).free / (1024 ** 3)
    if free_gb < max(0, minimum_free_gb):
        raise SystemExit(
            f"configured model storage has insufficient free space: "
            f"{free_gb:.2f} GiB available, {minimum_free_gb:.2f} GiB required"
        )


def _validate_local_runtime_paths(executable_path: Path, model_path: Path) -> None:
    executable = executable_path.expanduser().resolve()
    models = model_path.expanduser().resolve()
    if not executable.is_file():
        raise SystemExit("configured local runtime executable does not exist")
    model_parent = next((item for item in (models, *models.parents) if item.exists()), None)
    if model_parent is None:
        raise SystemExit("configured local model path has no existing parent")
    if executable.drive.lower() != models.drive.lower():
        raise SystemExit("local runtime executable and model directory must use the same drive")


if __name__ == "__main__":
    raise SystemExit(main())
