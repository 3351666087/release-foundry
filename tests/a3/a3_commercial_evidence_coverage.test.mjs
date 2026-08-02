import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const FIXTURE_PATH = new URL("../../fixtures/a3/p3/a3_commercial_evidence_coverage.redacted.json", import.meta.url);
const DOC_PATH = new URL("../../docs/a3/p3_commercial_evidence_coverage_2026_07_09.md", import.meta.url);

const REQUIRED_FAMILIES = [
  "A1 RunResult",
  "A2 GradeResult",
  "A3 Report",
  "A3 Review",
  "A3 GitHub",
  "A3 Billing",
  "A3 Audit",
  "A3 Redaction"
];

const REQUIRED_GOVERNANCE_SECTIONS = [
  "tenant",
  "auth",
  "rbac",
  "usage",
  "audit",
  "redaction"
];

const LEAK_PATTERNS = [
  {
    id: "api_key_assignment",
    regex: /\b(?:RELEASEFOUNDRY(?:_LABS)?_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GITHUB_TOKEN|GH_TOKEN)\s*[:=]\s*["']?(?!\[REDACTED\]|redacted\b|\.\.\.|example\b|dummy\b|test\b|false\b|true\b|null\b)[A-Za-z0-9._~+/=-]{12,}/gi
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

test("A3 commercial evidence coverage fixture binds required commercial artifact families", async () => {
  const fixture = await loadFixture();

  assert.equal(fixture.schema_version, "a3.commercial_evidence_coverage.v1");
  assert.equal(fixture.coverage_summary.all_required_families_bound, true);
  assert.equal(fixture.coverage_summary.customer_safe_packet, true);

  const artifactTypes = new Set(fixture.artifact_types.map((artifact) => artifact.type));
  assert.equal(artifactTypes.size >= 8, true, `expected 8+ artifact types, saw ${artifactTypes.size}`);
  assert.equal(fixture.coverage_summary.artifact_type_count, fixture.artifact_types.length);

  const families = new Set(fixture.artifact_types.map((artifact) => artifact.family));
  for (const family of REQUIRED_FAMILIES) {
    assert.equal(fixture.evidence_families.includes(family), true, `missing evidence family ${family}`);
    assert.equal(families.has(family), true, `missing artifact binding for ${family}`);
  }

  for (const artifact of fixture.artifact_types) {
    assert.equal(typeof artifact.binding, "string", `${artifact.type} missing binding`);
    assert.equal(artifact.binding.length > 20, true, `${artifact.type} binding is too thin`);
    assert.equal(Array.isArray(artifact.source_paths), true, `${artifact.type} missing source paths`);
    assert.equal(artifact.source_paths.length > 0, true, `${artifact.type} has no source paths`);
  }
});

test("A3 commercial evidence coverage declares tenant auth RBAC usage audit and redaction boundaries", async () => {
  const fixture = await loadFixture();
  const governance = fixture.tenant_auth_rbac_usage_audit_redaction;

  for (const section of REQUIRED_GOVERNANCE_SECTIONS) {
    assert.ok(governance[section], `missing governance section ${section}`);
  }

  assert.deepEqual(governance.tenant.required_fields, [
    "organization_id",
    "project_id",
    "release_id"
  ]);
  assert.equal(governance.auth.credential_material_stored, false);
  assert.equal(governance.rbac.mutation_boundary.includes("read-only"), true);
  assert.equal(governance.usage.billing_mutations_enabled, false);
  assert.equal(governance.audit.append_only_required, true);
  assert.equal(governance.redaction.raw_values_allowed, false);
  assert.equal(governance.redaction.secret_values_allowed, false);
  assert.equal(fixture.safety.live_provider_mutations_performed, false);
  assert.equal(fixture.safety.a1_semantics_changed, false);
  assert.equal(fixture.safety.a2_semantics_changed, false);
});

test("A3 commercial evidence coverage artifact and docs are secret-free", async () => {
  const fixtureText = await readFile(FIXTURE_PATH, "utf8");
  const docText = await readFile(DOC_PATH, "utf8");

  assert.deepEqual(scanForLeaks("fixture", fixtureText), []);
  assert.deepEqual(scanForLeaks("doc", docText), []);

  const docRequiredTerms = [
    "ANCHOR: A3_COMMERCIAL_EVIDENCE_COVERAGE",
    "ANCHOR: EVIDENCE_BINDINGS",
    "ANCHOR: ARTIFACT_TYPES",
    "ANCHOR: TENANT_AUTH_RBAC_USAGE_AUDIT_REDACTION",
    "A1 RunResult",
    "A2 GradeResult",
    "A3 Report",
    "A3 Review",
    "A3 GitHub",
    "A3 Billing",
    "A3 Audit",
    "A3 Redaction",
    "node --test tests/a3/a3_commercial_evidence_coverage.test.mjs"
  ];

  for (const term of docRequiredTerms) {
    assert.ok(docText.includes(term), `missing doc term ${term}`);
  }
});

async function loadFixture() {
  return JSON.parse(await readFile(FIXTURE_PATH, "utf8"));
}

function scanForLeaks(label, text) {
  const findings = [];
  for (const pattern of LEAK_PATTERNS) {
    pattern.regex.lastIndex = 0;
    let match;
    while ((match = pattern.regex.exec(text)) !== null) {
      findings.push(`${label}:${pattern.id}:${lineForIndex(text, match.index)}`);
      if (match[0].length === 0) {
        pattern.regex.lastIndex += 1;
      }
    }
  }
  return findings;
}

function lineForIndex(text, index) {
  return text.slice(0, index).split(/\r\n|\n|\r/).length;
}
