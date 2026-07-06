import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { ASHR_API_FIELD_MAP_VERSION, buildPrivateEvidenceIndex, EVIDENCE_INDEX_SCHEMA_VERSION, writePrivateEvidenceIndex } from "../dist/index.js";

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
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
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
