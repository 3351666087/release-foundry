import assert from "node:assert/strict";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const WORKSPACE_ROOT = path.resolve(fileURLToPath(new URL("../../", import.meta.url)));
const SCAN_ROOTS = [
  "docs/a3",
  "fixtures/a3"
];

const TEXT_EXTENSIONS = new Set([
  ".csv",
  ".html",
  ".json",
  ".md",
  ".txt",
  ".yaml",
  ".yml"
]);

const BINARY_EXTENSIONS = new Set([
  ".avif",
  ".bmp",
  ".gif",
  ".gz",
  ".ico",
  ".jpeg",
  ".jpg",
  ".pdf",
  ".png",
  ".tar",
  ".webp",
  ".whl",
  ".zip"
]);

const LEAK_PATTERNS = [
  {
    id: "api_key_assignment",
    regex: /\b(?:ASHR(?:_LABS)?_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GITHUB_TOKEN|GH_TOKEN)\s*[:=]\s*["']?(?!\[REDACTED\]|redacted\b|\.\.\.|example\b|dummy\b|test\b|false\b|true\b|null\b)[A-Za-z0-9._~+/=-]{12,}/gi
  },
  {
    id: "generic_secret_assignment",
    regex: /\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|session[_-]?id|session|csrf|xsrf|jwt|secret)\b\s*[:=]\s*["']?(?!\[REDACTED\]|redacted\b|\.\.\.|example\b|dummy\b|test\b|false\b|true\b|null\b)[A-Za-z0-9._~+/=-]{12,}/gi
  },
  {
    id: "authorization_header",
    regex: /\bAuthorization\s*:\s*(?!\[REDACTED\]|\.\.\.)(?:Bearer\s+)?[A-Za-z0-9._~+/=-]{12,}/gi
  },
  {
    id: "bearer_token",
    regex: /\bBearer\s+(?!\[REDACTED\]|\.\.\.)[A-Za-z0-9._~+/=-]{12,}/g
  },
  {
    id: "cookie_header",
    regex: /\b(?:Cookie|Set-Cookie)\s*:\s*(?!\[REDACTED\]|\.\.\.)[^\n\r]+/gi
  },
  {
    id: "prefixed_secret_token",
    regex: /\b(?:ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|sk_[A-Za-z0-9_-]{20,})\b/g
  },
  {
    id: "signed_media_url",
    regex: /https?:\/\/[^\s"'<>]*(?:X-Amz-|X-Goog-|Signature=|\bsig=|signed_url|access_token=|id_token=|refresh_token=|token=|expires=|Expires=)[^\s"'<>]*/gi
  },
  {
    id: "email_address",
    regex: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi
  },
  {
    id: "windows_user_home_path",
    regex: /\b[A-Z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+(?:[\\/][^\\/\s"'<>`]+)*/gi
  },
  {
    id: "unix_user_home_path",
    regex: /\/Users\/[A-Za-z0-9._-]+(?:\/[^/\s"'<>`]+)*/g
  }
];

const INTENTIONAL_REDACTION_DOC_EXAMPLES = [{
  file: "docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md",
  patternIds: new Set([
    "api_key_assignment",
    "authorization_header",
    "bearer_token",
    "cookie_header",
    "generic_secret_assignment",
    "unix_user_home_path",
    "windows_user_home_path"
  ]),
  allowedFragments: [
    "ASHR_API_KEY=...",
    "api_key=`,",
    "access_token=`,",
    "refresh_token=`,",
    "session=`,",
    "secret=`",
    "Authorization:`",
    "Bearer ...",
    "Cookie: ...",
    "/Users/`,",
    "C:/Users/`,"
  ],
  reason: "documents intentional firewall pattern examples without real values"
}];

test("generated A3 docs and fixture report artifacts are free of unredacted secrets and account paths", async () => {
  const artifactFiles = await collectArtifactFiles();
  const relativeFiles = artifactFiles.map(toPortablePath).sort();
  const findings = [];

  for (const file of artifactFiles) {
    const relPath = toPortablePath(file);
    const text = await readFile(file, "utf8");
    findings.push(...scanTextArtifact(relPath, text));
  }

  const unexpectedFindings = findings.filter((finding) => !isIntentionalExample(finding));

  assert.ok(relativeFiles.length > 80, `expected broad A3 artifact scan, saw ${relativeFiles.length} files`);
  assert.ok(relativeFiles.includes("docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md"));
  assert.ok(relativeFiles.includes("docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md"));
  assert.ok(relativeFiles.includes("fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json"));
  assert.ok(relativeFiles.includes("fixtures/a3/p3/a3_gate_cli_report.redacted.md"));
  assert.ok(relativeFiles.includes("fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json"));
  assert.ok(relativeFiles.includes("fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"));
  assert.equal(
    unexpectedFindings.length,
    0,
    formatFindings(unexpectedFindings)
  );
});

async function collectArtifactFiles() {
  const files = [];
  for (const relRoot of SCAN_ROOTS) {
    await collectFromDirectory(path.join(WORKSPACE_ROOT, relRoot), files);
  }
  return files.sort((left, right) => toPortablePath(left).localeCompare(toPortablePath(right)));
}

async function collectFromDirectory(directory, files) {
  const entries = await readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    const relPath = toPortablePath(fullPath);
    if (shouldSkipPath(relPath, entry.name)) {
      continue;
    }
    if (entry.isDirectory()) {
      await collectFromDirectory(fullPath, files);
      continue;
    }
    if (!entry.isFile()) {
      continue;
    }
    const extension = path.extname(entry.name).toLowerCase();
    if (!TEXT_EXTENSIONS.has(extension)) {
      continue;
    }
    const fileStat = await stat(fullPath);
    if (fileStat.size === 0) {
      continue;
    }
    files.push(fullPath);
  }
}

function shouldSkipPath(relPath, name) {
  const extension = path.extname(name).toLowerCase();
  return (
    BINARY_EXTENSIONS.has(extension) ||
    /(^|\/)\.env(?:\.|$)/i.test(relPath) ||
    /(^|\/)docs\/screenshots\//i.test(relPath) ||
    /(^|\/)private_refs\//i.test(relPath)
  );
}

function scanTextArtifact(file, text) {
  const findings = [];
  for (const pattern of LEAK_PATTERNS) {
    pattern.regex.lastIndex = 0;
    let match;
    while ((match = pattern.regex.exec(text)) !== null) {
      const location = locationForIndex(text, match.index);
      const lineText = lineAt(text, location.line);
      findings.push({
        file,
        pattern_id: pattern.id,
        line: location.line,
        column: location.column,
        lineText
      });
      if (match[0].length === 0) {
        pattern.regex.lastIndex += 1;
      }
    }
  }
  return findings;
}

function isIntentionalExample(finding) {
  return INTENTIONAL_REDACTION_DOC_EXAMPLES.some((allowance) => (
    allowance.file === finding.file &&
    allowance.patternIds.has(finding.pattern_id) &&
    allowance.allowedFragments.some((fragment) => finding.lineText.includes(fragment))
  ));
}

function formatFindings(findings) {
  if (findings.length === 0) {
    return "";
  }
  const details = findings
    .slice(0, 20)
    .map((finding) => `${finding.file}:${finding.line}:${finding.column} ${finding.pattern_id}`)
    .join("\n");
  const suffix = findings.length > 20 ? `\n...and ${findings.length - 20} more finding(s)` : "";
  return `Unexpected generated artifact firewall finding(s):\n${details}${suffix}`;
}

function locationForIndex(text, index) {
  const prefix = text.slice(0, index);
  const lines = prefix.split(/\r\n|\n|\r/);
  return {
    line: lines.length,
    column: lines.at(-1).length + 1
  };
}

function lineAt(text, lineNumber) {
  return text.split(/\r\n|\n|\r/)[lineNumber - 1] || "";
}

function toPortablePath(file) {
  return path.relative(WORKSPACE_ROOT, file).split(path.sep).join("/");
}
