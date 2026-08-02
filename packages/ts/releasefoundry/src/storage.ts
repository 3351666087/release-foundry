import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve, sep } from "node:path";

export type ObjectStorageJsonRecord = Record<string, unknown>;
export type ObjectStorageContent = string | Uint8Array;

export const OBJECT_STORAGE_CONTRACT_VERSION = "releasefoundry.object_storage.v1";
export const OBJECT_STORAGE_MANIFEST_SIGNATURE_VERSION = "releasefoundry.object_storage_manifest_signature.v1";
export const OBJECT_STORAGE_VERIFICATION_VERSION = "releasefoundry.object_storage_verification.v1";
export const OBJECT_STORAGE_ADAPTER_STATUS_VERSION = "releasefoundry.object_storage_adapter_status.v1";

const SAFE_SCOPE_PART = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/u;
const SAFE_CATEGORY = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/u;
const SAFE_SUFFIX = /^\.[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$/u;
const SECRET_REF_PREFIXES = ["env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:", "secret-ref:"];
const SENSITIVE_KEY_PARTS = ["access_key", "secret_key", "api_key", "authorization", "bearer", "password", "credential", "token"];
const ALLOWED_SAFETY_KEYS = new Set(["raw_payload_included", "secret_value_present"]);
const SECRET_VALUE_PATTERNS = [
  /tp_[A-Za-z0-9_-]+/u,
  /sk-[A-Za-z0-9_-]{8,}/u,
  /Bearer\s+[A-Za-z0-9._-]+/iu,
  /AKIA[0-9A-Z]{16}/u,
  /releasefoundry_live_[A-Za-z0-9_-]+/u,
];

export class ObjectStorageContractError extends Error {
  readonly code = "object_storage_contract_error";

  constructor(message: string) {
    super(message);
    this.name = "ObjectStorageContractError";
  }
}

export interface ScopedObjectKeyOptions {
  tenantId: string;
  projectId: string;
  runId: string;
  objectId: string;
  category?: string;
  suffix?: string;
}

export interface BuildObjectManifestOptions extends ScopedObjectKeyOptions {
  backend: "local-filesystem" | "s3-compatible";
  objectKey: string;
  contentType: string;
  sizeBytes: number;
  sha256: string;
  bucketRef?: string;
  endpointRef?: string;
  regionRef?: string;
  accessKeyRef?: string;
  secretKeyRef?: string;
  metadata?: ObjectStorageJsonRecord;
}

export interface LocalFilesystemWriteOptions extends ScopedObjectKeyOptions {
  content: ObjectStorageContent;
  contentType: string;
  metadata?: ObjectStorageJsonRecord;
}

export interface S3CompatibleObjectStorageOptions {
  bucketRef: string;
  endpointRef: string;
  regionRef?: string;
  accessKeyRef?: string;
  secretKeyRef?: string;
  adapter?: "aws-sdk-v3" | "minio";
}

export function sha256Bytes(content: ObjectStorageContent): string {
  return createHash("sha256").update(toBytes(content)).digest("hex");
}

export function scopedObjectKey(options: ScopedObjectKeyOptions): string {
  const category = options.category ?? "artifacts";
  const suffix = options.suffix ?? ".bin";
  const parts: Array<[string, string, RegExp]> = [
    ["category", category, SAFE_CATEGORY],
    ["tenant_id", options.tenantId, SAFE_SCOPE_PART],
    ["project_id", options.projectId, SAFE_SCOPE_PART],
    ["run_id", options.runId, SAFE_SCOPE_PART],
    ["object_id", options.objectId, SAFE_SCOPE_PART],
  ];
  for (const [name, value, pattern] of parts) {
    if (!value || !pattern.test(value)) {
      throw new ObjectStorageContractError(`${name} contains unsafe characters`);
    }
  }
  if (suffix && !SAFE_SUFFIX.test(suffix)) {
    throw new ObjectStorageContractError("suffix contains unsafe characters");
  }
  return `${category}/${options.tenantId}/${options.projectId}/${options.runId}/${options.objectId}${suffix}`;
}

export function buildObjectManifest(options: BuildObjectManifestOptions): ObjectStorageJsonRecord {
  validateObjectKeyScope(options.objectKey, options.tenantId, options.projectId, options.runId);
  if (!/^[a-f0-9]{64}$/u.test(options.sha256)) {
    throw new ObjectStorageContractError("sha256 must be a lowercase hex digest");
  }
  if (!Number.isSafeInteger(options.sizeBytes) || options.sizeBytes < 0) {
    throw new ObjectStorageContractError("size_bytes must be a non-negative safe integer");
  }

  const backendRefs: ObjectStorageJsonRecord = {
    bucket_ref: options.bucketRef ?? null,
    endpoint_ref: options.endpointRef ?? null,
    region_ref: options.regionRef ?? null,
    access_key_ref: options.accessKeyRef ?? null,
    secret_key_ref: options.secretKeyRef ?? null,
    access_key_ref_present: options.accessKeyRef !== undefined,
    secret_key_ref_present: options.secretKeyRef !== undefined,
  };
  if (options.backend === "local-filesystem") {
    backendRefs.storage_uri = `local://object-store/${options.objectKey}`;
  } else if (options.backend === "s3-compatible") {
    if (!options.bucketRef || !options.endpointRef) {
      throw new ObjectStorageContractError("s3-compatible manifests require bucket_ref and endpoint_ref");
    }
    for (const [name, value] of [
      ["bucket_ref", options.bucketRef],
      ["endpoint_ref", options.endpointRef],
      ["region_ref", options.regionRef],
      ["access_key_ref", options.accessKeyRef],
      ["secret_key_ref", options.secretKeyRef],
    ] as const) {
      if (value !== undefined) {
        assertApprovedRef(name, value);
      }
    }
    if ((options.accessKeyRef === undefined) !== (options.secretKeyRef === undefined)) {
      throw new ObjectStorageContractError("s3-compatible credentials require both access_key_ref and secret_key_ref");
    }
    backendRefs.storage_uri = `s3-compatible://${options.bucketRef}/${options.objectKey}`;
  } else {
    throw new ObjectStorageContractError("backend must be local-filesystem or s3-compatible");
  }

  const manifest: ObjectStorageJsonRecord = {
    schema_version: OBJECT_STORAGE_CONTRACT_VERSION,
    backend: options.backend,
    tenant_id: options.tenantId,
    project_id: options.projectId,
    run_id: options.runId,
    object_id: options.objectId,
    object_key: options.objectKey,
    content_type: options.contentType,
    size_bytes: options.sizeBytes,
    sha256: options.sha256,
    raw_payload_included: false,
    secret_value_present: false,
    backend_refs: backendRefs,
    metadata: publicSafeMetadata(options.metadata ?? {}),
  };
  manifest.manifest_signature = signObjectManifest(manifest);
  assertPublicObjectManifestSafe(manifest);
  return cloneJson(manifest);
}

export function signObjectManifest(manifest: ObjectStorageJsonRecord): ObjectStorageJsonRecord {
  return {
    schema_version: OBJECT_STORAGE_MANIFEST_SIGNATURE_VERSION,
    algorithm: "sha256-canonical-json",
    digest: canonicalManifestSha256(manifest),
    signature_key_ref: "contract:self-sha256",
    raw_payload_included: false,
    secret_value_present: false,
  };
}

export function verifyObjectManifestSignature(manifest: ObjectStorageJsonRecord): ObjectStorageJsonRecord {
  const signature = isRecord(manifest.manifest_signature) ? manifest.manifest_signature : null;
  const failures: ObjectStorageJsonRecord[] = [];
  const expectedDigest = signature?.digest;
  const actualDigest = canonicalManifestSha256(manifest);
  if (signature === null) {
    failures.push({ reason: "manifest_signature_missing" });
  } else if (signature.schema_version !== OBJECT_STORAGE_MANIFEST_SIGNATURE_VERSION) {
    failures.push({ reason: "manifest_signature_schema_mismatch", actual: signature.schema_version });
  } else if (signature.algorithm !== "sha256-canonical-json") {
    failures.push({ reason: "manifest_signature_algorithm_mismatch", actual: signature.algorithm });
  } else if (expectedDigest !== actualDigest) {
    failures.push({ reason: "manifest_signature_digest_mismatch", expected: expectedDigest, actual: actualDigest });
  }
  return {
    schema_version: OBJECT_STORAGE_MANIFEST_SIGNATURE_VERSION,
    verified: failures.length === 0,
    digest: expectedDigest,
    actual_digest: actualDigest,
    failures,
    raw_payload_included: false,
    secret_value_present: false,
  };
}

export function verifyObjectBytes(manifest: ObjectStorageJsonRecord, content: ObjectStorageContent): ObjectStorageJsonRecord {
  const raw = toBytes(content);
  const actual = sha256Bytes(raw);
  const expected = manifest.sha256;
  const expectedSize = manifest.size_bytes;
  const failures: ObjectStorageJsonRecord[] = [];
  if (expected !== actual) {
    failures.push({ reason: "sha256_mismatch", expected, actual });
  }
  if (expectedSize !== raw.byteLength) {
    failures.push({ reason: "size_bytes_mismatch", expected: expectedSize, actual: raw.byteLength });
  }
  if (manifest.raw_payload_included === true) {
    failures.push({ reason: "raw_payload_included" });
  }
  if (manifest.secret_value_present === true) {
    failures.push({ reason: "secret_value_present" });
  }
  const signatureVerification = verifyObjectManifestSignature(manifest);
  if (signatureVerification.verified !== true) {
    failures.push({ reason: "manifest_signature_mismatch", details: signatureVerification.failures });
  }
  return {
    schema_version: OBJECT_STORAGE_VERIFICATION_VERSION,
    verified: failures.length === 0,
    object_key: manifest.object_key,
    sha256: expected,
    actual_sha256: actual,
    size_bytes: expectedSize,
    actual_size_bytes: raw.byteLength,
    checksum: { algorithm: "sha256", expected, actual, verified: expected === actual },
    manifest_signature_verification: signatureVerification,
    failures,
    raw_payload_included: false,
    secret_value_present: false,
  };
}

export function assertPublicObjectManifestSafe(manifest: ObjectStorageJsonRecord): void {
  const issues = findPublicSafetyIssues(manifest);
  if (issues.length > 0) {
    throw new ObjectStorageContractError(`object storage manifest is not public-safe: ${String(issues[0]?.reason)} at ${String(issues[0]?.path)}`);
  }
}

export class LocalFilesystemObjectStorage {
  readonly root: string;

  constructor(root: string) {
    if (!root) {
      throw new ObjectStorageContractError("root must be a non-empty string");
    }
    this.root = resolve(root);
  }

  async writeObject(options: LocalFilesystemWriteOptions): Promise<ObjectStorageJsonRecord> {
    const raw = toBytes(options.content);
    const objectKey = scopedObjectKey(options);
    const path = this.resolveObjectKey(objectKey);
    await mkdir(resolve(path, ".."), { recursive: true });
    await writeFile(path, raw);
    const manifest = buildObjectManifest({
      ...options,
      backend: "local-filesystem",
      objectKey,
      sizeBytes: raw.byteLength,
      sha256: sha256Bytes(raw),
    });
    const verification = await this.verifyObject(manifest);
    if (verification.verified !== true) {
      throw new ObjectStorageContractError("local object write failed readback verification");
    }
    return { ...manifest, write_readback_verification: verification };
  }

  async readObject(manifest: ObjectStorageJsonRecord): Promise<Uint8Array> {
    if (typeof manifest.object_key !== "string") {
      throw new ObjectStorageContractError("manifest object_key must be a string");
    }
    return readFile(this.resolveObjectKey(manifest.object_key));
  }

  async verifyObject(manifest: ObjectStorageJsonRecord): Promise<ObjectStorageJsonRecord> {
    return verifyObjectBytes(manifest, await this.readObject(manifest));
  }

  private resolveObjectKey(objectKey: string): string {
    validateSafePathSegments(objectKey);
    const path = resolve(this.root, ...objectKey.split("/"));
    if (path !== this.root && !path.startsWith(`${this.root}${sep}`)) {
      throw new ObjectStorageContractError("object_key resolves outside storage root");
    }
    return path;
  }
}

export class S3CompatibleObjectStorage {
  readonly bucketRef: string;
  readonly endpointRef: string;
  readonly regionRef?: string;
  readonly accessKeyRef?: string;
  readonly secretKeyRef?: string;
  readonly adapter: "aws-sdk-v3" | "minio";

  constructor(options: S3CompatibleObjectStorageOptions) {
    this.bucketRef = options.bucketRef;
    this.endpointRef = options.endpointRef;
    this.regionRef = options.regionRef;
    this.accessKeyRef = options.accessKeyRef;
    this.secretKeyRef = options.secretKeyRef;
    this.adapter = options.adapter ?? "aws-sdk-v3";
    assertApprovedRef("bucket_ref", this.bucketRef);
    assertApprovedRef("endpoint_ref", this.endpointRef);
    if ((this.accessKeyRef === undefined) !== (this.secretKeyRef === undefined)) {
      throw new ObjectStorageContractError("s3-compatible credentials require both access_key_ref and secret_key_ref");
    }
  }

  adapterStatus(): ObjectStorageJsonRecord {
    return {
      schema_version: OBJECT_STORAGE_ADAPTER_STATUS_VERSION,
      backend: "s3-compatible",
      adapter: this.adapter,
      available: false,
      missing_dependencies: [this.adapter === "aws-sdk-v3" ? "@aws-sdk/client-s3" : "minio"],
      network_allowed: false,
      raw_payload_included: false,
      secret_value_present: false,
    };
  }

  buildManifest(options: Omit<BuildObjectManifestOptions, "backend" | "objectKey" | "bucketRef" | "endpointRef" | "regionRef" | "accessKeyRef" | "secretKeyRef">): ObjectStorageJsonRecord {
    const objectKey = scopedObjectKey(options);
    return {
      ...buildObjectManifest({
        ...options,
        backend: "s3-compatible",
        objectKey,
        bucketRef: this.bucketRef,
        endpointRef: this.endpointRef,
        regionRef: this.regionRef,
        accessKeyRef: this.accessKeyRef,
        secretKeyRef: this.secretKeyRef,
      }),
      adapter_status: this.adapterStatus(),
    };
  }
}

function canonicalManifestSha256(manifest: ObjectStorageJsonRecord): string {
  const publicManifest = cloneJson(manifest);
  delete publicManifest.manifest_signature;
  delete publicManifest.write_readback_verification;
  delete publicManifest.adapter_status;
  return createHash("sha256").update(canonicalJson(publicManifest), "utf8").digest("hex");
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalValue(value)).replace(/[\u007f-\uffff]/gu, (character) => `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`);
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalValue);
  }
  if (isRecord(value)) {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]));
  }
  return value;
}

function validateObjectKeyScope(objectKey: string, tenantId: string, projectId: string, runId: string): void {
  validateSafePathSegments(objectKey);
  const parts = objectKey.split("/");
  if (parts.length < 5) {
    throw new ObjectStorageContractError("object_key must include category/tenant/project/run/object");
  }
  if (parts[1] !== tenantId || parts[2] !== projectId || parts[3] !== runId) {
    throw new ObjectStorageContractError("object_key tenant/project/run scope mismatch");
  }
}

function validateSafePathSegments(objectKey: string): void {
  if (objectKey.startsWith("/") || objectKey.includes("\\") || objectKey.split("/").some((part) => part === "" || part === "." || part === "..")) {
    throw new ObjectStorageContractError("object_key contains unsafe path segments");
  }
}

function assertApprovedRef(name: string, value: string): void {
  if (!SECRET_REF_PREFIXES.some((prefix) => value.startsWith(prefix))) {
    throw new ObjectStorageContractError(`${name} must use an approved reference prefix`);
  }
}

function publicSafeMetadata(metadata: ObjectStorageJsonRecord): ObjectStorageJsonRecord {
  const safe: ObjectStorageJsonRecord = {};
  for (const [key, value] of Object.entries(metadata)) {
    const normalized = key.toLowerCase().replaceAll("-", "_");
    if (ALLOWED_SAFETY_KEYS.has(normalized) || SENSITIVE_KEY_PARTS.some((part) => normalized.includes(part))) {
      continue;
    }
    safe[key] = redactValue(value);
  }
  return safe;
}

function redactValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redactValue);
  }
  if (isRecord(value)) {
    return publicSafeMetadata(value);
  }
  if (typeof value === "string" && SECRET_VALUE_PATTERNS.some((pattern) => pattern.test(value))) {
    return "[REDACTED]";
  }
  return value;
}

function findPublicSafetyIssues(value: unknown, path = "$"): ObjectStorageJsonRecord[] {
  const issues: ObjectStorageJsonRecord[] = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => issues.push(...findPublicSafetyIssues(item, `${path}[${index}]`)));
  } else if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      const normalized = key.toLowerCase().replaceAll("-", "_");
      const itemPath = `${path}.${key}`;
      if (
        !ALLOWED_SAFETY_KEYS.has(normalized)
        && SENSITIVE_KEY_PARTS.some((part) => normalized.includes(part))
        && !normalized.endsWith("_ref")
        && !normalized.endsWith("_ref_present")
      ) {
        issues.push({ reason: "sensitive_key_present", path: itemPath });
      }
      issues.push(...findPublicSafetyIssues(item, itemPath));
    }
  } else if (typeof value === "string") {
    if (SECRET_VALUE_PATTERNS.some((pattern) => pattern.test(value))) {
      issues.push({ reason: "secret_like_value_present", path });
    }
    if (value.startsWith("file://") || /^[A-Za-z]:[\\/]/u.test(value)) {
      issues.push({ reason: "absolute_local_path_present", path });
    }
  } else if (value !== null && !["boolean", "number"].includes(typeof value)) {
    issues.push({ reason: "non_json_value_present", path });
  }
  return issues;
}

function toBytes(content: ObjectStorageContent): Uint8Array {
  return typeof content === "string" ? Buffer.from(content, "utf8") : Uint8Array.from(content);
}

function isRecord(value: unknown): value is ObjectStorageJsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
