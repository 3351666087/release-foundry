import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const TAILWIND_CONFIG = new URL("../../tailwind.config.ts", import.meta.url);
const POSTCSS_CONFIG = new URL("../../postcss.config.mjs", import.meta.url);
const CONTRACT_DOC = new URL("../../docs/a3/p3_tailwind_product_system_contract_2026_07_09.md", import.meta.url);

const SECRET_PATTERNS = [
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{40,}\b/,
  /\bghp_[A-Za-z0-9]{36}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{12,}/i,
  /\b(?:RELEASEFOUNDRY(?:_LABS)?_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GITHUB_TOKEN|GH_TOKEN)\s*[:=]\s*["']?(?!\[REDACTED\]|redacted\b|\.\.\.|example\b|dummy\b|test\b)[A-Za-z0-9._~+/=-]{12,}/i
];

test("Tailwind product-system config covers A3 dashboard, report, docs, fixture, and E2E surfaces", async () => {
  const source = await readFile(TAILWIND_CONFIG, "utf8");

  for (const requiredGlob of [
    "./apps/dashboard/index.html",
    "./apps/dashboard/src/**/*.{js,mjs,jsx,ts,tsx,html}",
    "./services/report/**/*.{js,mjs,ts,tsx}",
    "./tests/a3/**/*.{js,mjs,ts,tsx}",
    "./tests/e2e/**/*.{js,mjs,ts,tsx}",
    "./docs/a3/**/*.{md,mdx,html}",
    "./fixtures/a3/**/*.{json,md,html}"
  ]) {
    assert.ok(source.includes(requiredGlob), `missing Tailwind content glob: ${requiredGlob}`);
  }

  assert.match(source, /darkMode:\s*\["class", '\[data-theme="dark"\]'\]/);
  assert.doesNotMatch(source, /process\.env|\.env\.local|private_refs|\.secrets/);
});

test("Tailwind product-system config exposes semantic color, spacing, radius, and font tokens", async () => {
  const source = await readFile(TAILWIND_CONFIG, "utf8");

  for (const token of [
    "canvas",
    "surface",
    "ink",
    "line",
    "accent",
    "evidence",
    "success",
    "warning",
    "danger",
    "review",
    "a3-field",
    "a3-row",
    "a3-panel",
    "a3-section",
    "a3-gutter",
    "a3-touch",
    "control",
    "card",
    "modal",
    "fontFamily",
    "a3-caption",
    "a3-body",
    "a3-label",
    "a3-title",
    "a3-metric"
  ]) {
    assert.match(source, new RegExp(`["']?${escapeRegExp(token)}["']?`), `missing product-system token: ${token}`);
  }

  assert.doesNotMatch(source, /purple|violet|from-purple|to-blue|gradient/i);
  assert.ok(source.includes("#b56a09"), "warning hue should keep release risk distinct from evidence blue");
  assert.ok(source.includes("#b7354a"), "danger hue should keep blockers distinct from evidence blue");
  assert.ok(source.includes("#2f7d4f"), "success hue should keep approvals distinct from evidence blue");
});

test("PostCSS config is Tailwind-ready without adding runtime behavior", async () => {
  const source = await readFile(POSTCSS_CONFIG, "utf8");

  assert.match(source, /tailwindcss:\s*\{\}/);
  assert.match(source, /autoprefixer:\s*\{\}/);
  assert.doesNotMatch(source, /process\.env|\.env\.local|private_refs|\.secrets/);
});

test("Tailwind product-system documentation preserves A1/A2/A3 commercial contract boundaries", async () => {
  const doc = await readFile(CONTRACT_DOC, "utf8");

  for (const term of [
    "API Contract",
    "DB Contract",
    "Event Contract",
    "Artifact Contract",
    "Tenant",
    "Auth",
    "RBAC",
    "Usage",
    "Audit",
    "A1 integration",
    "A2 integration",
    "A3 integration",
    "GET /api/a3/dashboard",
    "release_evidence_readbacks",
    "product_system.theme_preference_changed",
    "artifact_type=product_system_contract"
  ]) {
    assert.ok(doc.includes(term), `missing Tailwind contract doc term: ${term}`);
  }

  assert.match(doc, /Tailwind classes should not encode business decisions/);
  assert.match(doc, /must not reinterpret A2 `primary_failure_class`/);
  assert.match(doc, /must not invent A1 authority/);
});

test("Tailwind product-system config and docs are free of high-confidence secret patterns", async () => {
  const files = [
    ["tailwind.config.ts", await readFile(TAILWIND_CONFIG, "utf8")],
    ["postcss.config.mjs", await readFile(POSTCSS_CONFIG, "utf8")],
    ["p3_tailwind_product_system_contract_2026_07_09.md", await readFile(CONTRACT_DOC, "utf8")]
  ];

  for (const [file, text] of files) {
    for (const pattern of SECRET_PATTERNS) {
      assert.doesNotMatch(text, pattern, `${file} matched high-confidence secret pattern ${pattern}`);
    }
  }
});

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
