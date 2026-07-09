# A1 Object Storage Contract Evidence

This evidence note records the public-safe A1 object storage contract added for local filesystem and S3-compatible deployments.

## Contract

- Schema version: `ashr.clone.object_storage.v1`.
- Supported backends: `local-filesystem` and `s3-compatible`.
- Object keys are scoped as `category/tenant_id/project_id/run_id/object_id.ext`.
- Public manifests include `object_key`, `storage_uri`, `content_type`, `size_bytes`, `sha256`, backend reference fields, and redaction guarantees.
- Public manifests do not include raw payload bytes, absolute local filesystem paths, raw S3/MinIO endpoints, access keys, secret keys, bearer tokens, or API keys.
- S3-compatible manifests accept reference strings only, such as `env:ASHR_OBJECT_STORE_BUCKET` and `env:ASHR_OBJECT_STORE_ENDPOINT`.
- Local filesystem writes perform a sha256 readback verification when a local object root is provided.

## Wiring

- SDK helper: `packages/sdk/ashr_clone/storage.py`.
- API integration: `services/api/platform.py` stores manifest-shaped object metadata on artifacts and evidence bundles.
- Evidence bundle records keep the existing public `local://object-store/...` URI shape and add `object_storage` plus optional `write_readback_verified` metadata.

## Test Coverage

- `tests/a1/test_object_storage_contract.py` covers scoped key validation, local filesystem write/readback verification, tamper detection, S3-compatible reference-only manifests, metadata redaction, and API evidence bundle wiring.
- `tests/a1/test_saas_platform.py` continues to cover the existing artifact/evidence bundle release packet behavior.

No real MinIO or S3 network calls are required or performed by this contract evidence.
