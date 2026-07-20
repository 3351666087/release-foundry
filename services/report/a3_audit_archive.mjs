#!/usr/bin/env node
import { createHash, generateKeyPairSync, sign as cryptoSign, verify as cryptoVerify } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { redactExport } from "./export_redaction_firewall.mjs";

export const A3_AUDIT_ARCHIVE_MANIFEST_SCHEMA_VERSION = "a3.audit_archive_manifest.v1";
export const A3_AUDIT_ARCHIVE_VERIFICATION_SCHEMA_VERSION = "a3.audit_archive_verification.v1";

export async function buildAuditArchiveManifest(indexPathOrObject, options = {}) {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const bundleIndexPath = typeof indexPathOrObject === "string"
    ? resolve(indexPathOrObject)
    : options.bundleIndexPath
      ? resolve(options.bundleIndexPath)
      : null;
  const bundleIndex = typeof indexPathOrObject === "string"
    ? JSON.parse(await readFile(bundleIndexPath, "utf8"))
    : indexPathOrObject || {};
  const bundleIndexEntry = bundleIndexPath
    ? await fileArchiveEntry("audit_bundle_index", bundleIndexPath, {
      workspaceRoot,
      archiveRole: "bundle_index",
      required: true,
      createdBy: "ashr gate audit bundle index"
    })
    : null;
  const artifactEntries = arrayOf(bundleIndex.bundle_artifacts).map((artifact) => normalizeArchiveEntry({
    ...artifact,
    archive_role: artifact.bundle_role || "bundle_artifact",
    created_by: artifact.created_by || "ashr gate audit bundle"
  }, workspaceRoot));
  const archiveEntries = dedupeEntries([
    ...(bundleIndexEntry ? [bundleIndexEntry] : []),
    ...artifactEntries
  ]).sort(compareEntries);
  const archiveId = options.archiveId || buildArchiveId(
    bundleIndex.bundle_id || "unknown-bundle",
    bundleIndex.bundle_root_hash || "unknown-root"
  );
  const unsignedManifest = {
    schema_version: A3_AUDIT_ARCHIVE_MANIFEST_SCHEMA_VERSION,
    generated_at: options.generatedAt || "runtime",
    source: options.source || bundleIndex.source || "local-fixtures",
    archive_id: archiveId,
    archive_format: {
      format: options.archiveFormat || "portable-directory-or-zip-manifest",
      zip_compatible: true,
      compression_required: false,
      canonical_order: "archive_entries sorted by archive_role:id:path",
      manifest_self_hash: "excluded_to_avoid_self_reference"
    },
    archive_file: options.archiveFile ? portableArtifactPath(resolve(options.archiveFile), workspaceRoot) : null,
    bundle: {
      bundle_id: bundleIndex.bundle_id || "unknown-bundle",
      bundle_root_hash: bundleIndex.bundle_root_hash || null,
      bundle_index_file: bundleIndex.bundle_index_file || (bundleIndexPath ? portableArtifactPath(bundleIndexPath, workspaceRoot) : null),
      release: bundleIndex.release || {},
      artifact_count: archiveEntries.length
    },
    immutable_policy: {
      overwrite_allowed: false,
      append_only_after_seal: true,
      private_key_persisted: false,
      intended_storage: options.intendedStorage || "local-filesystem-or-self-host-object-storage",
      retention_class: options.retentionClass || "release_evidence_legal_hold_ready"
    },
    archive_entries: archiveEntries,
    verification: {
      command_shape: "ashr archive verify --manifest <archive-manifest.json>",
      verifies_bundle_root_hash: true,
      verifies_artifact_hashes: true,
      verifies_archive_signature: true
    },
    safety: {
      contains_secret_values: false,
      local_absolute_paths_allowed: false,
      raw_private_key_stored: false,
      dry_run_compatible: true
    }
  };
  const archiveRootHash = sha256Text(canonicalJson(unsignedManifest));
  const sealedManifest = {
    ...unsignedManifest,
    archive_root_hash: archiveRootHash
  };
  const signedManifest = {
    ...sealedManifest,
    signature: signArchiveManifest(sealedManifest, options)
  };
  const { value } = redactExport(signedManifest, { surface: "audit_archive_manifest" });
  return value;
}

export async function verifyAuditArchiveManifest(manifestPathOrObject, options = {}) {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const manifestPath = typeof manifestPathOrObject === "string" ? resolve(manifestPathOrObject) : null;
  const manifest = manifestPath
    ? JSON.parse(await readFile(manifestPath, "utf8"))
    : manifestPathOrObject || {};
  const findings = [];

  if (manifest.schema_version !== A3_AUDIT_ARCHIVE_MANIFEST_SCHEMA_VERSION) {
    findings.push(archiveFinding("schema_version", "blocking", "Archive manifest schema_version must be a3.audit_archive_manifest.v1."));
  }

  const { archive_root_hash: expectedRootHash, signature, ...manifestWithoutRootAndSignature } = manifest;
  const actualRootHash = sha256Text(canonicalJson(manifestWithoutRootAndSignature));
  if (!/^[a-f0-9]{64}$/.test(String(expectedRootHash || ""))) {
    findings.push(archiveFinding("archive_root_hash_missing", "blocking", "Archive manifest is missing a valid SHA-256 root hash."));
  } else if (actualRootHash !== expectedRootHash) {
    findings.push(archiveFinding("archive_root_hash_mismatch", "blocking", "Archive root hash does not match canonical archive manifest data."));
  }

  const signatureResult = verifyArchiveSignature({
    ...manifestWithoutRootAndSignature,
    archive_root_hash: expectedRootHash
  }, signature);
  if (!signatureResult.passed) {
    findings.push(archiveFinding("archive_signature_invalid", "blocking", signatureResult.message));
  }

  const entryResults = await Promise.all(arrayOf(manifest.archive_entries).map((entry) => verifyArchiveEntry(entry, workspaceRoot)));
  for (const entryResult of entryResults) {
    if (["missing", "hash_mismatch", "byte_size_mismatch"].includes(entryResult.status)) {
      findings.push(archiveFinding(`entry_${entryResult.status}`, "blocking", `${entryResult.id}: ${entryResult.message}`));
    } else if (entryResult.status === "skipped_outside_workspace") {
      findings.push(archiveFinding("entry_outside_workspace", "warning", `${entryResult.id}: ${entryResult.message}`));
    }
  }

  const unsafeEntries = entryResults.filter((entry) => entry.path_is_absolute || entry.path_includes_user_home);
  for (const entry of unsafeEntries) {
    findings.push(archiveFinding("unsafe_archive_entry_path", "blocking", `${entry.id}: archive entry path is not safe to share.`));
  }

  const blockingFindings = findings.filter((finding) => finding.severity === "blocking");
  const result = {
    schema_version: A3_AUDIT_ARCHIVE_VERIFICATION_SCHEMA_VERSION,
    verified_at: options.generatedAt || "runtime",
    manifest_path: manifestPath ? portableArtifactPath(manifestPath, workspaceRoot) : null,
    archive_id: manifest.archive_id || "unknown-archive",
    status: blockingFindings.length ? "failed" : "passed",
    root_hash: {
      expected: expectedRootHash || null,
      actual: actualRootHash,
      passed: actualRootHash === expectedRootHash
    },
    signature: signatureResult,
    entries: {
      total: entryResults.length,
      checked: entryResults.filter((entry) => entry.status !== "skipped_outside_workspace").length,
      passed: entryResults.filter((entry) => entry.status === "passed").length,
      skipped: entryResults.filter((entry) => entry.status === "skipped_outside_workspace").length,
      failed: entryResults.filter((entry) => ["missing", "hash_mismatch", "byte_size_mismatch"].includes(entry.status)).length,
      results: entryResults
    },
    safety: {
      contains_secret_values: false,
      local_absolute_paths_allowed: false,
      unsafe_path_count: unsafeEntries.length,
      raw_private_key_stored: false
    },
    findings,
    process_exit_code: options.noFail ? 0 : blockingFindings.length ? 1 : 0
  };
  const { value } = redactExport(result, { surface: "audit_archive_verification" });
  return value;
}

export function renderArchiveVerificationMarkdown(verification = {}) {
  const findings = arrayOf(verification.findings);
  const lines = [
    "# Ashr++ Audit Archive Verification",
    "",
    `- Archive: ${verification.archive_id || "unknown"}`,
    `- Status: ${verification.status || "unknown"}`,
    `- Root hash: ${verification.root_hash?.passed ? "passed" : "failed"}`,
    `- Signature: ${verification.signature?.passed ? "passed" : "failed"}`,
    `- Entries: ${verification.entries?.passed || 0}/${verification.entries?.total || 0} passed`,
    `- Blocking findings: ${findings.filter((finding) => finding.severity === "blocking").length}`,
    "",
    "## Findings",
    "",
    ...(findings.length ? findings.map((finding) => `- ${finding.severity}: ${finding.id} - ${finding.message}`) : ["- No findings."]),
    ""
  ];
  return `${lines.join("\n")}\n`;
}

export async function writeAuditArchiveManifest(options = {}) {
  const manifest = await buildAuditArchiveManifest(options.index, options);
  if (!options.output) {
    return manifest;
  }
  const resolvedOutput = resolve(options.output);
  await mkdir(dirname(resolvedOutput), { recursive: true });
  await writeFile(resolvedOutput, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return manifest;
}

function signArchiveManifest(manifest, options = {}) {
  const payload = Buffer.from(canonicalJson(manifest));
  const keyPair = options.signingKeyPair || generateKeyPairSync("ed25519");
  const publicKeyPem = keyPair.publicKey.export({ type: "spki", format: "pem" });
  const signatureBase64 = cryptoSign(null, payload, keyPair.privateKey).toString("base64");
  return {
    schema_version: "a3.audit_archive_signature.v1",
    signature_status: "signed",
    algorithm: "ed25519",
    signed_payload: "canonical_archive_manifest_with_archive_root_hash",
    signed_payload_sha256: sha256Text(payload),
    signer: {
      signer_type: options.signerType || "local-a3-gate-cli",
      identity_binding: options.identityBinding || "self_signed_local_key_not_sso_bound",
      public_key_pem: publicKeyPem
    },
    signature_base64: signatureBase64
  };
}

function verifyArchiveSignature(manifest, signature = {}) {
  try {
    if (signature.schema_version !== "a3.audit_archive_signature.v1") {
      return { passed: false, algorithm: signature.algorithm || "unknown", message: "Archive signature schema is missing or invalid." };
    }
    if (signature.algorithm !== "ed25519") {
      return { passed: false, algorithm: signature.algorithm || "unknown", message: "Archive signature algorithm must be ed25519." };
    }
    const payload = Buffer.from(canonicalJson(manifest));
    const expectedPayloadHash = sha256Text(payload);
    if (signature.signed_payload_sha256 !== expectedPayloadHash) {
      return {
        passed: false,
        algorithm: signature.algorithm,
        expected_payload_sha256: signature.signed_payload_sha256 || null,
        actual_payload_sha256: expectedPayloadHash,
        message: "Archive signature payload hash does not match manifest."
      };
    }
    const verified = cryptoVerify(
      null,
      payload,
      signature.signer?.public_key_pem || "",
      Buffer.from(signature.signature_base64 || "", "base64")
    );
    return {
      passed: verified,
      algorithm: signature.algorithm,
      signed_payload_sha256: expectedPayloadHash,
      signer_type: signature.signer?.signer_type || "unknown",
      identity_binding: signature.signer?.identity_binding || "unknown",
      message: verified ? "Archive signature is valid." : "Archive signature failed verification."
    };
  } catch (error) {
    return {
      passed: false,
      algorithm: signature.algorithm || "unknown",
      message: `Archive signature verification failed: ${error.message}`
    };
  }
}

async function fileArchiveEntry(id, path, options = {}) {
  const resolvedPath = resolve(path);
  return normalizeArchiveEntry({
    id,
    path: portableArtifactPath(resolvedPath, options.workspaceRoot || process.cwd()),
    archive_role: options.archiveRole || "archive_file",
    content_type: options.contentType || contentTypeForPath(resolvedPath),
    required: options.required !== false,
    sha256: await sha256File(resolvedPath),
    byte_size: await byteSizeFile(resolvedPath),
    created_by: options.createdBy || "ashr archive builder"
  }, options.workspaceRoot || process.cwd());
}

function normalizeArchiveEntry(entry = {}, workspaceRoot) {
  const path = normalizePortablePath(entry.path || "");
  return {
    id: entry.id || entry.artifact_id || "unknown_entry",
    path,
    archive_role: entry.archive_role || entry.bundle_role || "bundle_artifact",
    content_type: entry.content_type || contentTypeForPath(path),
    required: entry.required !== false,
    sha256: entry.sha256 || null,
    byte_size: Number.isFinite(Number(entry.byte_size)) ? Number(entry.byte_size) : null,
    created_by: entry.created_by || "ashr archive",
    ...(entry.origin ? { origin: entry.origin } : {}),
    redaction_status: entry.redaction_status || "redacted_or_safe_for_audit",
    workspace_relative: !path.startsWith("[outside-workspace]/")
  };
}

async function verifyArchiveEntry(entry = {}, workspaceRoot) {
  const id = entry.id || "unknown_entry";
  const path = normalizePortablePath(entry.path || "");
  const pathIsOutsideWorkspace = path.startsWith("[outside-workspace]/");
  const pathIsAbsolute = /^[A-Za-z]:\//.test(path) || path.startsWith("/");
  const pathIncludesUserHome = path.includes("Users/") || path.includes("C:/Users");
  if (!path || pathIsOutsideWorkspace || pathIsAbsolute) {
    return {
      id,
      path,
      status: "skipped_outside_workspace",
      expected_sha256: entry.sha256 || null,
      actual_sha256: null,
      expected_byte_size: entry.byte_size ?? null,
      actual_byte_size: null,
      path_is_absolute: pathIsAbsolute,
      path_includes_user_home: pathIncludesUserHome,
      message: "Archive entry path is outside the verifiable workspace."
    };
  }
  const resolvedPath = resolve(workspaceRoot, path);
  const portablePath = portableArtifactPath(resolvedPath, workspaceRoot);
  if (portablePath.startsWith("[outside-workspace]/")) {
    return {
      id,
      path,
      status: "skipped_outside_workspace",
      expected_sha256: entry.sha256 || null,
      actual_sha256: null,
      expected_byte_size: entry.byte_size ?? null,
      actual_byte_size: null,
      path_is_absolute: true,
      path_includes_user_home: pathIncludesUserHome,
      message: "Archive entry resolves outside the workspace."
    };
  }
  try {
    const bytes = await readFile(resolvedPath);
    const actualSha256 = sha256Text(bytes);
    const actualByteSize = bytes.length;
    if (actualSha256 !== entry.sha256) {
      return {
        id,
        path,
        status: "hash_mismatch",
        expected_sha256: entry.sha256 || null,
        actual_sha256: actualSha256,
        expected_byte_size: entry.byte_size ?? null,
        actual_byte_size: actualByteSize,
        path_is_absolute: false,
        path_includes_user_home: pathIncludesUserHome,
        message: "Archive entry SHA-256 does not match manifest."
      };
    }
    if (Number.isFinite(Number(entry.byte_size)) && actualByteSize !== Number(entry.byte_size)) {
      return {
        id,
        path,
        status: "byte_size_mismatch",
        expected_sha256: entry.sha256 || null,
        actual_sha256: actualSha256,
        expected_byte_size: Number(entry.byte_size),
        actual_byte_size: actualByteSize,
        path_is_absolute: false,
        path_includes_user_home: pathIncludesUserHome,
        message: "Archive entry byte size does not match manifest."
      };
    }
    return {
      id,
      path,
      status: "passed",
      expected_sha256: entry.sha256 || null,
      actual_sha256: actualSha256,
      expected_byte_size: entry.byte_size ?? null,
      actual_byte_size: actualByteSize,
      path_is_absolute: false,
      path_includes_user_home: pathIncludesUserHome,
      message: "Archive entry hash and byte size match."
    };
  } catch {
    return {
      id,
      path,
      status: "missing",
      expected_sha256: entry.sha256 || null,
      actual_sha256: null,
      expected_byte_size: entry.byte_size ?? null,
      actual_byte_size: null,
      path_is_absolute: false,
      path_includes_user_home: pathIncludesUserHome,
      message: "Archive entry file is missing or unreadable."
    };
  }
}

function contentTypeForPath(path = "") {
  const normalized = String(path).toLowerCase();
  if (normalized.endsWith(".json")) {
    return "application/json";
  }
  if (normalized.endsWith(".md")) {
    return "text/markdown";
  }
  if (normalized.endsWith(".zip")) {
    return "application/zip";
  }
  if (normalized.endsWith(".tar")) {
    return "application/x-tar";
  }
  return "application/octet-stream";
}

function portableArtifactPath(resolvedPath, workspaceRoot) {
  const relativePath = relative(resolve(workspaceRoot), resolve(resolvedPath));
  if (relativePath.startsWith("..") || isAbsolute(relativePath)) {
    return `[outside-workspace]/${basename(resolvedPath)}`;
  }
  return relativePath.replaceAll("\\", "/");
}

function normalizePortablePath(path = "") {
  const normalized = String(path).replaceAll("\\", "/");
  if (!normalized) {
    return "";
  }
  if (/^[A-Za-z]:\//.test(normalized) || normalized.startsWith("/")) {
    return `[outside-workspace]/${basename(normalized)}`;
  }
  return normalized;
}

async function sha256File(path) {
  const bytes = await readFile(resolve(path));
  return sha256Text(bytes);
}

async function byteSizeFile(path) {
  return (await stat(resolve(path))).size;
}

function sha256Text(value) {
  return createHash("sha256").update(value).digest("hex");
}

function buildArchiveId(bundleId = "unknown-bundle", rootHash = "unknown-root") {
  const shortRoot = /^[a-f0-9]{64}$/.test(rootHash) ? rootHash.slice(0, 12) : sha256Text(rootHash).slice(0, 12);
  return `a3-archive-${slugify(bundleId).slice(0, 54)}-${shortRoot}`;
}

function slugify(value = "") {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "local-bundle";
}

function arrayOf(value) {
  return Array.isArray(value) ? value : [];
}

function dedupeEntries(entries = []) {
  const seen = new Set();
  const deduped = [];
  for (const entry of entries) {
    const key = `${entry.id}\n${entry.path}`;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(entry);
    }
  }
  return deduped;
}

function compareEntries(left, right) {
  return `${left.archive_role}:${left.id}:${left.path}`.localeCompare(`${right.archive_role}:${right.id}:${right.path}`);
}

function archiveFinding(id, severity, message) {
  return { id, severity, message };
}

function canonicalJson(value) {
  return JSON.stringify(canonicalizeValue(value));
}

function canonicalizeValue(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalizeValue);
  }
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((object, key) => {
      object[key] = canonicalizeValue(value[key]);
      return object;
    }, {});
  }
  return value;
}

function parseArgs(argv = []) {
  const options = {
    format: "json",
    generatedAt: "runtime"
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === "--index") {
      options.index = next;
      index += 1;
    } else if (arg === "--output") {
      options.output = next;
      index += 1;
    } else if (arg === "--verify") {
      options.verify = next;
      index += 1;
    } else if (arg === "--generated-at") {
      options.generatedAt = next;
      index += 1;
    } else if (arg === "--source") {
      options.source = next;
      index += 1;
    } else if (arg === "--no-fail") {
      options.noFail = true;
    } else if (arg === "--markdown") {
      options.format = "markdown";
    } else if (arg === "--json") {
      options.format = "json";
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (options.help) {
    process.stdout.write(helpText());
    process.exit(0);
  }
  if (!options.index && !options.verify) {
    throw new Error("--index or --verify is required.");
  }
  return options;
}

function helpText() {
  return `Usage: node services/report/a3_audit_archive.mjs --index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --output fixtures/a3/p3/a3_audit_archive_manifest.redacted.json --json\n       node services/report/a3_audit_archive.mjs --verify fixtures/a3/p3/a3_audit_archive_manifest.redacted.json --json [--no-fail]\n`;
}

async function main(argv = []) {
  const options = parseArgs(argv);
  if (options.verify) {
    const verification = await verifyAuditArchiveManifest(options.verify, options);
    const output = options.format === "markdown"
      ? renderArchiveVerificationMarkdown(verification)
      : `${JSON.stringify(verification, null, 2)}\n`;
    if (options.output) {
      const resolvedOutput = resolve(options.output);
      await mkdir(dirname(resolvedOutput), { recursive: true });
      await writeFile(resolvedOutput, output, "utf8");
    }
    process.stdout.write(output);
    return verification.process_exit_code;
  }
  const manifest = await writeAuditArchiveManifest(options);
  process.stdout.write(`${JSON.stringify(manifest, null, 2)}\n`);
  return 0;
}

const isDirectRun = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectRun) {
  main(process.argv.slice(2)).then((exitCode) => {
    process.exitCode = exitCode;
  }).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 2;
  });
}
