import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  LocalFilesystemObjectStorage,
  OBJECT_STORAGE_CONTRACT_VERSION,
  ObjectStorageContractError,
  S3CompatibleObjectStorage,
  assertPublicObjectManifestSafe,
  buildObjectManifest,
  scopedObjectKey,
  sha256Bytes,
  verifyObjectBytes,
  verifyObjectManifestSignature,
} from "../dist/index.js";

test("TS object keys preserve tenant/project/run scope and reject traversal", () => {
  assert.equal(
    scopedObjectKey({
      tenantId: "tenant_safe",
      projectId: "project_safe",
      runId: "run_safe",
      objectId: "artifact_safe",
      category: "evidence-bundles",
      suffix: ".json",
    }),
    "evidence-bundles/tenant_safe/project_safe/run_safe/artifact_safe.json",
  );
  assert.throws(
    () => scopedObjectKey({ tenantId: "tenant/escape", projectId: "project", runId: "run", objectId: "artifact" }),
    ObjectStorageContractError,
  );
  assert.throws(
    () => scopedObjectKey({ tenantId: "tenant", projectId: "project", runId: "run", objectId: ".." }),
    /unsafe characters/,
  );
});

test("TS local object storage writes a public-safe manifest and detects content tampering", async () => {
  const root = await mkdtemp(join(tmpdir(), "ashr-ts-object-store-"));
  const store = new LocalFilesystemObjectStorage(root);
  const content = '{"redacted":true}';
  const manifest = await store.writeObject({
    tenantId: "tenant_obj",
    projectId: "project_obj",
    runId: "run_obj",
    objectId: "artifact_obj",
    content,
    contentType: "application/json",
    suffix: ".json",
    metadata: { source: "ts-unit", api_key: "tp_should_not_leak", nested: { password: "not-public" } },
  });

  assert.equal(manifest.schema_version, OBJECT_STORAGE_CONTRACT_VERSION);
  assert.equal(manifest.backend, "local-filesystem");
  assert.equal(manifest.object_key, "artifacts/tenant_obj/project_obj/run_obj/artifact_obj.json");
  assert.equal(manifest.backend_refs.storage_uri, "local://object-store/artifacts/tenant_obj/project_obj/run_obj/artifact_obj.json");
  assert.equal(manifest.write_readback_verification.verified, true);
  assert.equal(manifest.write_readback_verification.manifest_signature_verification.verified, true);
  assert.equal(JSON.stringify(manifest).includes("tp_should_not_leak"), false);
  assert.equal(JSON.stringify(manifest).includes(root), false);
  assertPublicObjectManifestSafe(manifest);

  const path = join(root, "artifacts", "tenant_obj", "project_obj", "run_obj", "artifact_obj.json");
  assert.equal(await readFile(path, "utf8"), content);
  await writeFile(path, '{"redacted":false}', "utf8");
  const tampered = await store.verifyObject(manifest);
  assert.equal(tampered.verified, false);
  assert.equal(tampered.failures[0].reason, "sha256_mismatch");
});

test("TS canonical manifest signature detects ref and checksum tampering", () => {
  const objectKey = scopedObjectKey({
    tenantId: "tenant_sig",
    projectId: "project_sig",
    runId: "run_sig",
    objectId: "bundle_sig",
    suffix: ".json",
  });
  const manifest = buildObjectManifest({
    backend: "s3-compatible",
    objectKey,
    tenantId: "tenant_sig",
    projectId: "project_sig",
    runId: "run_sig",
    objectId: "bundle_sig",
    contentType: "application/json",
    sizeBytes: 2,
    sha256: sha256Bytes("{}"),
    bucketRef: "env:ASHR_OBJECT_STORE_BUCKET",
    endpointRef: "env:ASHR_OBJECT_STORE_ENDPOINT",
    accessKeyRef: "env:ASHR_OBJECT_STORE_ACCESS_KEY",
    secretKeyRef: "env:ASHR_OBJECT_STORE_SECRET_KEY",
    metadata: { payload_preview: "{}", secret_key: "sk-should-not-render" },
  });

  assert.equal(verifyObjectManifestSignature(manifest).verified, true);
  assert.equal(verifyObjectBytes(manifest, "{}").verified, true);
  assert.equal(JSON.stringify(manifest).includes("sk-should-not-render"), false);

  const mutated = structuredClone(manifest);
  mutated.backend_refs.endpoint_ref = "env:ASHR_OBJECT_STORE_OTHER_ENDPOINT";
  assert.equal(verifyObjectManifestSignature(mutated).verified, false);
  assert.equal(verifyObjectBytes(mutated, "{}").failures.at(-1).reason, "manifest_signature_mismatch");
});

test("TS S3-compatible adapter is reference-only and fail-closed without a network dependency", () => {
  const adapter = new S3CompatibleObjectStorage({
    bucketRef: "env:ASHR_OBJECT_STORE_BUCKET",
    endpointRef: "env:ASHR_OBJECT_STORE_ENDPOINT",
    accessKeyRef: "env:ASHR_OBJECT_STORE_ACCESS_KEY",
    secretKeyRef: "env:ASHR_OBJECT_STORE_SECRET_KEY",
  });
  const manifest = adapter.buildManifest({
    tenantId: "tenant_s3",
    projectId: "project_s3",
    runId: "run_s3",
    objectId: "bundle_s3",
    contentType: "application/json",
    sizeBytes: 2,
    sha256: sha256Bytes("{}"),
    category: "evidence-bundles",
    suffix: ".json",
  });

  assert.equal(manifest.backend_refs.storage_uri, "s3-compatible://env:ASHR_OBJECT_STORE_BUCKET/evidence-bundles/tenant_s3/project_s3/run_s3/bundle_s3.json");
  assert.equal(manifest.adapter_status.network_allowed, false);
  assert.equal(manifest.adapter_status.available, false);
  assert.equal(verifyObjectBytes(manifest, "{}").verified, true);
  assertPublicObjectManifestSafe(manifest);

  assert.throws(
    () => new S3CompatibleObjectStorage({ bucketRef: "raw-bucket", endpointRef: "env:ASHR_OBJECT_STORE_ENDPOINT" }),
    /approved reference prefix/,
  );
  assert.throws(
    () => new S3CompatibleObjectStorage({
      bucketRef: "env:ASHR_OBJECT_STORE_BUCKET",
      endpointRef: "env:ASHR_OBJECT_STORE_ENDPOINT",
      accessKeyRef: "env:ASHR_OBJECT_STORE_ACCESS_KEY",
    }),
    /both access_key_ref and secret_key_ref/,
  );
});
