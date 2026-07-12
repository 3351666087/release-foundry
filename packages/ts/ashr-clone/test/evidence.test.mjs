import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  ASHR_API_FIELD_MAP_VERSION,
  buildPrivateEvidenceIndex,
  buildPrivateEvidenceIndexFromDir,
  buildResponseFieldMap,
  EVIDENCE_INDEX_SCHEMA_VERSION,
  mergeEvidenceIndices,
  renderResponseFieldMapMarkdown,
  validatePublicEvidenceIndex,
  writePrivateEvidenceIndex,
  writeResponseFieldMapMarkdown,
} from "../dist/index.js";

test("buildPrivateEvidenceIndex summarizes safe private API records", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-evidence-"));
  try {
    const second = join(temp, "b.json");
    const first = join(temp, "a.json");
    const invalid = join(temp, "invalid.json");
    writeFileSync(
      second,
      JSON.stringify({
        function: "create_request",
        dry_run: false,
        status: "error",
        status_code: 200,
        attempts: 1,
        request: { api_key: "tp_syntheticsecret", request_name: "quota" },
        response: {
          status: "error",
          message: "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
          quota: { resource: "requests", limit: 5, used: 5, requested: 1, remaining: 0, secret_token: "tp_syntheticsecret" },
        },
        error: { error_kind: "api", message: "Bearer abc.secret" },
      }),
      "utf8",
    );
    writeFileSync(
      first,
      JSON.stringify({
        function: "list_runs",
        dry_run: true,
        status: "planned",
        status_code: null,
        attempts: 0,
        request: { params: {} },
        response: { status: "planned", runs: [{ run_id: "run_1" }, { run_id: "run_2" }] },
        response_summary: { request_failure: {} },
      }),
      "utf8",
    );
    writeFileSync(invalid, "not-json", "utf8");

    const index = await buildPrivateEvidenceIndex([second, invalid, first], { label: "a1-ts-test" });

    assert.equal(index.schema_version, EVIDENCE_INDEX_SCHEMA_VERSION);
    assert.equal(index.label, "a1-ts-test");
    assert.equal(index.field_map_version, ASHR_API_FIELD_MAP_VERSION);
    assert.equal(index.total_records, 2);
    assert.deepEqual(index.status_counts, { error: 1, planned: 1 });
    assert.deepEqual(index.function_counts, { create_request: 1, list_runs: 1 });
    assert.deepEqual(index.error_kind_counts, { api: 1 });
    assert.equal(index.quota_block_count, 1);
    assert.deepEqual(index.records.map((record) => record.function), ["list_runs", "create_request"]);
    assert.deepEqual(index.records[0].top_counts, { runs: 2 });
    assert.deepEqual(index.records[1].quota, {
      blocked: true,
      message: "Usage limit exceeded; exact quota details are kept in private evidence",
      quota_keys: ["limit", "remaining", "requested", "resource", "secret_token", "used"],
      resource: "requests",
      limit_present: true,
      used_present: true,
      requested_present: true,
      remaining_present: true,
    });
    assert.equal(JSON.stringify(index).includes("tp_syntheticsecret"), false);
    assert.equal(JSON.stringify(index).includes("Bearer abc.secret"), false);
    assert.equal(JSON.stringify(index).includes("5/5 " + "used"), false);
    assert.deepEqual(validatePublicEvidenceIndex(index), []);

    const fieldMap = buildResponseFieldMap(index);
    assert.equal(fieldMap.schema_version, "ashr.clone.response_field_map.v1");
    assert.equal(fieldMap.source_label, "a1-ts-test");
    assert.equal(fieldMap.source_total_records, 2);
    assert.equal(fieldMap.field_map_version, ASHR_API_FIELD_MAP_VERSION);
    assert.deepEqual(fieldMap.functions.create_request, {
      records: 1,
      statuses: { error: 1 },
      response_keys: ["message", "quota", "status"],
      response_summary_keys: [],
      error_keys: ["error_kind", "message"],
      quota_block_count: 1,
      top_count_keys: [],
    });
    assert.deepEqual(fieldMap.functions.list_runs, {
      records: 1,
      statuses: { planned: 1 },
      response_keys: ["runs", "status"],
      response_summary_keys: ["request_failure"],
      error_keys: [],
      quota_block_count: 0,
      top_count_keys: ["runs"],
    });
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("validatePublicEvidenceIndex flags unsafe public evidence details", () => {
  const issues = validatePublicEvidenceIndex({
    records: [
      {
        function: "create_request",
        quota: { blocked: true, limit: 5, used: 5, requested: 1, remaining: 0 },
      },
      "not-a-record",
    ],
    response: {
      message: "Usage limit exceeded for requests: 5/5 used",
      token: "tp_syntheticsecret",
    },
  });

  assert.equal(issues.some((issue) => issue.kind === "exact_quota_detail" && issue.pattern === "5/5 used"), true);
  assert.equal(issues.some((issue) => issue.kind === "secret_like_text"), true);
  assert.equal(issues.some((issue) => issue.kind === "malformed_record" && issue.record_index === 1), true);
  assert.deepEqual(
    issues
      .filter((issue) => issue.kind === "quota_value_not_public_safe")
      .map((issue) => issue.field)
      .sort(),
    ["limit", "remaining", "requested", "used"],
  );
});

test("validatePublicEvidenceIndex distinguishes tp credentials from identifier fragments", () => {
  const credentialIssues = validatePublicEvidenceIndex({
    records: [{ path: "public.json", note: "credential=tp_actualCredentialShape" }],
  });
  const benignIssues = validatePublicEvidenceIndex({
    records: [
      {
        path: "public.json",
        http_status: "ok",
        http_test: "passed",
        trusted_proof: "verified",
        otp_present: true,
      },
    ],
  });

  assert.equal(credentialIssues.some((issue) => issue.kind === "secret_like_text"), true);
  assert.equal(benignIssues.some((issue) => issue.kind === "secret_like_text"), false);
});

test("writePrivateEvidenceIndex creates parents and redacts output", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-evidence-write-"));
  try {
    const output = join(temp, "nested", "index.json");
    const written = await writePrivateEvidenceIndex(output, { schema_version: EVIDENCE_INDEX_SCHEMA_VERSION, token: "tp_syntheticsecret" });

    assert.equal(written, output);
    const payload = readFileSync(output, "utf8");
    assert.equal(payload.endsWith("\n"), true);
    assert.equal(payload.includes("tp_syntheticsecret"), false);
    assert.equal(JSON.parse(payload).token, "[redacted]");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("TS directory indexing, incremental merge, and Markdown field maps match Python workflows", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-evidence-parity-"));
  try {
    writeFileSync(join(temp, "first.json"), JSON.stringify({ function: "list_runs", status: "ok", dry_run: false, response: { runs: [] } }), "utf8");
    writeFileSync(join(temp, "second.json"), JSON.stringify({ function: "create_request", status: "planned", dry_run: true, response: { status: "planned" } }), "utf8");
    writeFileSync(join(temp, "ignored.txt"), "not json", "utf8");

    const initial = await buildPrivateEvidenceIndexFromDir(temp, { label: "directory", maxFiles: 1 });
    const fresh = await buildPrivateEvidenceIndex([join(temp, "second.json")], { label: "fresh" });
    const merged = mergeEvidenceIndices(initial, fresh, "merged");
    const fieldMap = buildResponseFieldMap(merged);
    const markdown = renderResponseFieldMapMarkdown(fieldMap);
    const output = join(temp, "nested", "field-map.md");

    assert.equal(initial.total_records, 1);
    assert.equal(merged.total_records, 2);
    assert.deepEqual(merged.records.map((record) => record.function), ["list_runs", "create_request"]);
    assert.match(markdown, /# Ashr Real API Response Field Map/u);
    assert.match(markdown, /create_request/u);
    assert.equal(await writeResponseFieldMapMarkdown(output, fieldMap), output);
    assert.equal(readFileSync(output, "utf8"), markdown);
    assert.equal(JSON.stringify(merged).includes("private_refs"), false);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
