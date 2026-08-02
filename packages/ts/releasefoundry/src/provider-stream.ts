import { createHash } from "node:crypto";

export const PROVIDER_STREAM_SCHEMA_VERSION = "releasefoundry.provider_stream.v1";
const ZERO_DIGEST = "0".repeat(64);
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

export class ProviderStreamIntegrityError extends Error {}

export interface ProviderStreamFrame {
  sequence: number;
  kind: string;
  content_digest: string;
  previous_digest: string;
  frame_digest: string;
  terminal: boolean;
  entry_id?: string;
  fencing_token?: number;
}

export interface ProviderStreamSnapshot {
  schema_version: typeof PROVIDER_STREAM_SCHEMA_VERSION;
  frames: ProviderStreamFrame[];
  frame_count: number;
  terminal_observed: boolean;
  stream_digest: string;
  entry_id?: string;
  fencing_token?: number;
}

export class ProviderStreamLedger {
  private readonly frames: ProviderStreamFrame[] = [];
  private terminal = false;
  private entryId?: string;
  private fencingToken?: number;

  constructor(
    snapshot?: ProviderStreamSnapshot,
    binding?: { entry_id: string; fencing_token: number },
  ) {
    [this.entryId, this.fencingToken] = validateBinding(binding?.entry_id, binding?.fencing_token);
    if (snapshot !== undefined) this.load(snapshot);
  }

  observe(sequence: number, kind: string, content: unknown, terminal = false): ProviderStreamFrame {
    if (!Number.isSafeInteger(sequence) || sequence < 0) {
      throw new ProviderStreamIntegrityError("stream sequence must be a non-negative integer");
    }
    if (typeof kind !== "string" || kind.length === 0 || kind.length > 64) {
      throw new ProviderStreamIntegrityError("stream kind must be a controlled non-empty label");
    }
    if (this.terminal) throw new ProviderStreamIntegrityError("stream already has a terminal frame");
    const contentDigest = contentDigestOf(content);
    if (sequence < this.frames.length) {
      const existing = this.frames[sequence];
      if (existing.kind === kind && existing.content_digest === contentDigest && existing.terminal === terminal) {
        return structuredClone(existing);
      }
      throw new ProviderStreamIntegrityError("stream sequence conflicts with an existing frame");
    }
    if (sequence !== this.frames.length) {
      throw new ProviderStreamIntegrityError("stream sequence contains a gap or is out of order");
    }
    const previousDigest = this.frames.at(-1)?.frame_digest ?? ZERO_DIGEST;
    const frame: ProviderStreamFrame = {
      sequence,
      kind,
      content_digest: contentDigest,
      previous_digest: previousDigest,
      frame_digest: frameDigest(
        sequence, kind, contentDigest, previousDigest, terminal, this.entryId, this.fencingToken,
      ),
      terminal,
    };
    if (this.entryId !== undefined) {
      frame.entry_id = this.entryId;
      frame.fencing_token = this.fencingToken;
    }
    this.frames.push(frame);
    this.terminal = terminal;
    return structuredClone(frame);
  }

  finalize(): ProviderStreamSnapshot {
    if (!this.terminal) throw new ProviderStreamIntegrityError("stream is missing a terminal frame");
    return this.snapshot();
  }

  snapshot(): ProviderStreamSnapshot {
    const snapshot: ProviderStreamSnapshot = {
      schema_version: PROVIDER_STREAM_SCHEMA_VERSION,
      frames: structuredClone(this.frames),
      frame_count: this.frames.length,
      terminal_observed: this.terminal,
      stream_digest: this.frames.at(-1)?.frame_digest ?? ZERO_DIGEST,
    };
    if (this.entryId !== undefined) {
      snapshot.entry_id = this.entryId;
      snapshot.fencing_token = this.fencingToken;
    }
    return snapshot;
  }

  private load(snapshot: ProviderStreamSnapshot): void {
    if (snapshot?.schema_version !== PROVIDER_STREAM_SCHEMA_VERSION || !Array.isArray(snapshot.frames)) {
      throw new ProviderStreamIntegrityError("unsupported or malformed provider stream schema");
    }
    const [snapshotEntryId, snapshotFencingToken] = validateBinding(snapshot.entry_id, snapshot.fencing_token);
    const snapshotKeys = [
      "frame_count", "frames", "schema_version", "stream_digest", "terminal_observed",
      ...(snapshotEntryId === undefined ? [] : ["entry_id", "fencing_token"]),
    ].sort().join(",");
    if (Object.keys(snapshot).sort().join(",") !== snapshotKeys) {
      throw new ProviderStreamIntegrityError("provider stream snapshot is malformed");
    }
    if (this.entryId === undefined) {
      this.entryId = snapshotEntryId;
      this.fencingToken = snapshotFencingToken;
    } else if (snapshotEntryId !== this.entryId || snapshotFencingToken !== this.fencingToken) {
      throw new ProviderStreamIntegrityError("provider stream journal binding conflicts with constructor");
    }
    for (const raw of snapshot.frames) {
      const expectedFrameKeys = [
        "content_digest", "frame_digest", "kind", "previous_digest", "sequence", "terminal",
        ...(this.entryId === undefined ? [] : ["entry_id", "fencing_token"]),
      ].sort().join(",");
      if (
        raw === null || typeof raw !== "object"
        || Object.keys(raw).sort().join(",") !== expectedFrameKeys
        || !isSha256(raw.content_digest)
        || !isSha256(raw.previous_digest)
        || !isSha256(raw.frame_digest)
      ) {
        throw new ProviderStreamIntegrityError("provider stream frame is malformed");
      }
      if (this.entryId !== undefined && (
        raw.entry_id !== this.entryId || raw.fencing_token !== this.fencingToken
      )) {
        throw new ProviderStreamIntegrityError("provider stream frame journal binding is invalid");
      }
      const frame = this.observe(raw.sequence, raw.kind, { sha256: raw.content_digest }, raw.terminal);
      if (
        frame.content_digest !== raw.content_digest
        || frame.previous_digest !== raw.previous_digest
        || frame.frame_digest !== raw.frame_digest
      ) {
        throw new ProviderStreamIntegrityError("provider stream digest chain is invalid");
      }
    }
    const expected = this.snapshot();
    if (
      snapshot.frame_count !== expected.frame_count
      || snapshot.terminal_observed !== expected.terminal_observed
      || snapshot.stream_digest !== expected.stream_digest
    ) {
      throw new ProviderStreamIntegrityError("provider stream summary is invalid");
    }
  }
}

export function canonicalProviderJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalProviderJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonicalProviderJson(record[key])}`).join(",")}}`;
}

export const canonical_provider_json = canonicalProviderJson;

function contentDigestOf(content: unknown): string {
  if (
    content !== null && typeof content === "object" && !Array.isArray(content)
    && Object.keys(content).length === 1 && typeof (content as { sha256?: unknown }).sha256 === "string"
    && isSha256((content as { sha256: string }).sha256)
  ) {
    return (content as { sha256: string }).sha256;
  }
  const payload = content instanceof Uint8Array
    ? content
    : new TextEncoder().encode(typeof content === "string" ? content : canonicalProviderJson(content));
  return createHash("sha256").update(payload).digest("hex");
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && SHA256_PATTERN.test(value);
}

function frameDigest(
  sequence: number,
  kind: string,
  contentDigest: string,
  previousDigest: string,
  terminal: boolean,
  entryId?: string,
  fencingToken?: number,
): string {
  const frame: Record<string, unknown> = {
    content_digest: contentDigest,
    kind,
    previous_digest: previousDigest,
    sequence,
    terminal,
  };
  if (entryId !== undefined) {
    frame.entry_id = entryId;
    frame.fencing_token = fencingToken;
  }
  return createHash("sha256").update(canonicalProviderJson(frame)).digest("hex");
}

function validateBinding(entryId: unknown, fencingToken: unknown): [string | undefined, number | undefined] {
  if (entryId === undefined && fencingToken === undefined) return [undefined, undefined];
  if (entryId === undefined || fencingToken === undefined) {
    throw new ProviderStreamIntegrityError("provider stream journal binding fields must appear together");
  }
  if (typeof entryId !== "string" || !/^[A-Za-z0-9_.:-]{1,128}$/.test(entryId)) {
    throw new ProviderStreamIntegrityError("provider stream entry_id is invalid");
  }
  if (!Number.isSafeInteger(fencingToken) || (fencingToken as number) <= 0) {
    throw new ProviderStreamIntegrityError("provider stream fencing_token must be a positive integer");
  }
  return [entryId, fencingToken as number];
}
