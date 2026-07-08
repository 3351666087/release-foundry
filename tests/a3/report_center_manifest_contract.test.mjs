import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const DOC_PATH = new URL("../../docs/a3/p3_report_center_manifest_growth_2026_07_07.md", import.meta.url);

test("A3 Report Center manifest contract preserves required section anchors", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredAnchors = [
    "ANCHOR: A3_REPORT_CENTER_MANIFEST_CONTRACT",
    "ANCHOR: MANIFEST_ENVELOPE",
    "ANCHOR: ARTIFACT_REGISTRY",
    "ANCHOR: REQUIRED_ARTIFACT_NAMES",
    "ANCHOR: LIFECYCLE_FIELDS",
    "ANCHOR: SURFACE_CONTRACTS",
    "ANCHOR: SAFETY_CONTRACT",
    "ANCHOR: SQL_AUDIT_LINKAGE",
    "ANCHOR: EXAMPLE_SKELETON",
    "ANCHOR: ACCEPTANCE_GUARD"
  ];

  for (const anchor of requiredAnchors) {
    assert.ok(doc.includes(anchor), `missing Report Center manifest anchor: ${anchor}`);
  }
});

test("A3 Report Center manifest contract names every critical artifact", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredArtifacts = [
    "json_report",
    "markdown_report",
    "csv_export",
    "pdf_print_report",
    "hosted_report",
    "pr_comment_markdown",
    "github_check_run",
    "audit_bundle_index",
    "replay_pack",
    "reviewer_board",
    "usage_ledger"
  ];

  for (const artifactId of requiredArtifacts) {
    assert.match(doc, new RegExp(`\\\`${escapeRegExp(artifactId)}\\\``), `missing artifact id: ${artifactId}`);
  }

  const requiredDisplayNames = [
    "JSON report",
    "Markdown report",
    "CSV export",
    "PDF/print report",
    "Hosted report",
    "PR comment Markdown",
    "GitHub check run",
    "Audit bundle index",
    "Replay pack",
    "Reviewer board",
    "Usage ledger"
  ];

  for (const displayName of requiredDisplayNames) {
    assert.ok(doc.includes(displayName), `missing artifact display name: ${displayName}`);
  }
});

test("A3 Report Center manifest contract guards lifecycle fields and states", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredLifecycleFields = [
    "lifecycle_state",
    "created_at",
    "updated_at",
    "created_by",
    "published_at",
    "expires_at",
    "revoked_at",
    "viewed_at",
    "verified_at",
    "purged_at",
    "retention_policy",
    "blocking_reason",
    "audit_event_ids"
  ];

  for (const field of requiredLifecycleFields) {
    assert.match(doc, new RegExp(`\\\`${escapeRegExp(field)}\\\``), `missing lifecycle field: ${field}`);
  }

  const requiredStates = [
    "planned",
    "queued",
    "building",
    "redaction_scanning",
    "redaction_blocked",
    "generated",
    "published",
    "shared",
    "viewed",
    "revoked",
    "expired",
    "verified",
    "retained",
    "purged",
    "failed"
  ];

  for (const state of requiredStates) {
    assert.match(doc, new RegExp(`\\\`${escapeRegExp(state)}\\\``), `missing lifecycle state: ${state}`);
  }
});

test("A3 Report Center manifest contract keeps safety and schema anchors stable", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredTerms = [
    "a3.report_center_manifest.v1",
    "a3.export_report.v1",
    "a3.generated_artifact_manifest.v1",
    "a3.audit_bundle_index.v1",
    "a3.shareable_report.v1",
    "a3.github_check_run.v1",
    "a3.incident_replay_queue.v1",
    "a3.review_board.v1",
    "a3.usage_ledger.v1",
    "contains_secret_values",
    "local_absolute_paths_allowed",
    "raw_signed_urls_allowed",
    "raw_cookies_allowed",
    "raw_tokens_allowed",
    "csv_formula_injection_allowed",
    "report.share_link_created",
    "report.share_link_viewed",
    "report.share_link_revoked",
    "report.bundle_verified",
    "usage.recorded",
    "The usage ledger is append-only"
  ];

  for (const term of requiredTerms) {
    assert.ok(doc.includes(term), `missing required manifest term: ${term}`);
  }
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
