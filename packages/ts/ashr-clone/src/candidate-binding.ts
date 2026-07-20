import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const A1_CANDIDATE_BINDING_SCHEMA_VERSION = "ashr.clone.a1_candidate_binding.v1";

const GIT_SHA_PATTERN = /^[0-9a-f]{40}$/;
const SEMVER_PATTERN = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const CANDIDATE_NAME_PATTERN = /^[0-9A-Za-z][0-9A-Za-z._:/-]*$/;

export interface A1CandidateBindingInput {
  candidateId: string;
  candidateSourceCommit: string;
  evidenceReleaseVersion: string;
  caseSet: unknown;
  repoRoot?: string;
}

export interface A1CandidateBinding {
  schema_version: typeof A1_CANDIDATE_BINDING_SCHEMA_VERSION;
  candidate_id: string;
  git_sha: string;
  candidate_source_commit: string;
  evidence_release_version: string;
  source_tree_clean: true;
  source_tree_sha: string;
  case_set_sha256: string;
}

export class CandidateBindingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CandidateBindingError";
  }
}

export async function buildA1CandidateBinding(input: A1CandidateBindingInput): Promise<A1CandidateBinding> {
  const candidateId = requireText(input.candidateId, "candidateId");
  const sourceCommit = requireGitSha(input.candidateSourceCommit, "candidateSourceCommit");
  const releaseVersion = requireSemVer(input.evidenceReleaseVersion, "evidenceReleaseVersion");
  validateCandidateId(candidateId, releaseVersion);
  if (!Array.isArray(input.caseSet) || input.caseSet.length === 0) {
    throw new CandidateBindingError("caseSet must be a non-empty JSON array");
  }

  const repoRoot = resolve(input.repoRoot ?? process.cwd());
  const actualHead = requireGitSha(await runGit(repoRoot, ["rev-parse", "HEAD"]), "git HEAD");
  if (actualHead !== sourceCommit) {
    throw new CandidateBindingError(`candidate source commit does not match repository HEAD (${actualHead})`);
  }

  const dirtyEntries = await runGit(repoRoot, ["status", "--porcelain=v1", "--untracked-files=all"]);
  if (dirtyEntries.length > 0) {
    throw new CandidateBindingError("candidate source tree must be clean before the run starts");
  }

  const treeSha = requireGitSha(await runGit(repoRoot, ["rev-parse", "HEAD^{tree}"]), "git tree");
  return {
    schema_version: A1_CANDIDATE_BINDING_SCHEMA_VERSION,
    candidate_id: candidateId,
    git_sha: sourceCommit,
    candidate_source_commit: sourceCommit,
    evidence_release_version: releaseVersion,
    source_tree_clean: true,
    source_tree_sha: treeSha,
    case_set_sha256: sha256Ref(canonicalJson(input.caseSet)),
  };
}

export function canonicalCandidateCaseSetJson(value: unknown): string {
  return canonicalJson(value);
}

function validateCandidateId(candidateId: string, releaseVersion: string): void {
  const separator = candidateId.lastIndexOf("@");
  if (separator <= 0 || separator === candidateId.length - 1) {
    throw new CandidateBindingError("candidateId must use <agent>@<semver>");
  }
  const name = candidateId.slice(0, separator);
  const version = candidateId.slice(separator + 1);
  if (!CANDIDATE_NAME_PATTERN.test(name)) {
    throw new CandidateBindingError("candidateId agent name contains unsupported characters");
  }
  requireSemVer(version, "candidateId version");
  if (version !== releaseVersion) {
    throw new CandidateBindingError("candidateId version must match evidenceReleaseVersion");
  }
}

function requireText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim().length === 0 || value !== value.trim()) {
    throw new CandidateBindingError(`${field} must be a non-empty trimmed string`);
  }
  return value;
}

function requireGitSha(value: unknown, field: string): string {
  const text = requireText(value, field);
  if (!GIT_SHA_PATTERN.test(text)) {
    throw new CandidateBindingError(`${field} must be a lowercase 40-character Git SHA`);
  }
  return text;
}

function requireSemVer(value: unknown, field: string): string {
  const text = requireText(value, field);
  if (!SEMVER_PATTERN.test(text)) {
    throw new CandidateBindingError(`${field} must be a valid SemVer value`);
  }
  return text;
}

async function runGit(repoRoot: string, args: string[]): Promise<string> {
  try {
    const { stdout } = await execFileAsync("git", args, {
      cwd: repoRoot,
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      windowsHide: true,
    });
    return String(stdout).trim();
  } catch {
    throw new CandidateBindingError(`git preflight failed: git ${args.join(" ")}`);
  }
}

function canonicalJson(value: unknown): string {
  const normalized = canonicalValue(value);
  const serialized = JSON.stringify(normalized);
  if (serialized === undefined) {
    throw new CandidateBindingError("caseSet must be JSON serializable");
  }
  return serialized;
}

function canonicalValue(value: unknown): unknown {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new CandidateBindingError("caseSet must not contain non-finite numbers");
    }
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => canonicalValue(item));
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return Object.fromEntries(
      Object.keys(record)
        .sort()
        .filter((key) => record[key] !== undefined)
        .map((key) => [key, canonicalValue(record[key])]),
    );
  }
  throw new CandidateBindingError("caseSet must contain JSON values only");
}

function sha256Ref(value: string): string {
  return `sha256:${createHash("sha256").update(value, "utf8").digest("hex")}`;
}
