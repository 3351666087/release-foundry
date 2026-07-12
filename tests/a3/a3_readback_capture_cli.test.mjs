import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";

import {
  buildReadbackCaptureCliReceipt,
  parseReadbackCaptureArgs,
  runReadbackCaptureCli
} from "../../services/report/a3_readback_capture_cli.mjs";
import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 readback capture CLI parses dry-run and submit arguments", () => {
  const args = parseReadbackCaptureArgs([
    "--api-url", "http://127.0.0.1:4173",
    "--release-id", "current",
    "--readback", "artifacts/readback.json",
    "--source", "mock",
    "--organization-id", "org-local",
    "--project-id", "project-local",
    "--actor-hash", "actor_[REDACTED_HASH]",
    "--idempotency-key", "idem-readback",
    "--output-receipt", "artifacts/readback-capture.json",
    "--submit",
    "--json"
  ]);

  assert.equal(args.apiUrl, "http://127.0.0.1:4173");
  assert.equal(args.releaseId, "current");
  assert.equal(args.readback, "artifacts/readback.json");
  assert.equal(args.source, "mock");
  assert.equal(args.dryRun, false);
  assert.equal(args.json, true);
});

test("A3 readback capture CLI builds dry-run request without leaking nested secrets", async () => {
  const dir = await mkdtemp(join(tmpdir(), "a3-readback-dry-run-"));
  const readbackPath = join(dir, "readback.json");
  try {
    const fixture = await loadJson("../../fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json");
    await writeFile(readbackPath, JSON.stringify({
      ...fixture,
      expected: {
        ...fixture.expected,
        authorization: `Bearer ${"x".repeat(24)}`,
        reviewer_email: ["reviewer", "example.com"].join("@")
      }
    }), "utf8");

    const receipt = await buildReadbackCaptureCliReceipt({
      apiUrl: "http://127.0.0.1:4173",
      releaseId: "current",
      readback: readbackPath,
      source: "mock",
      idempotencyKey: "idem-readback-dry-run"
    });

    assert.equal(receipt.schema_version, "a3.readback_capture_cli_receipt.v1");
    assert.equal(receipt.status, "planned");
    assert.equal(receipt.dry_run, true);
    assert.equal(receipt.submitted, false);
    assert.equal(receipt.request.idempotency_key_present, true);
    assert.equal(receipt.request.readback_kind, "github_check");
    assert.equal(receipt.safety.token_included, false);
    assert.doesNotMatch(JSON.stringify(receipt), /Bearer x|reviewer@example.com|Authorization/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("A3 readback capture CLI submits sanitized readback into the A3 API", async () => {
  const dir = await mkdtemp(join(tmpdir(), "a3-readback-submit-"));
  const readbackPath = join(dir, "readback.json");
  const outputReceipt = join(dir, "capture.json");
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const { server, url } = await startA3ApiServer({ store, routeAccessMode: "demo_contract" });
  try {
    const fixture = await loadJson("../../fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json");
    await writeFile(readbackPath, JSON.stringify({
      ...fixture,
      readback_id: "ghcrb_cli_submitted",
      expected: {
        ...fixture.expected,
        authorization: `Bearer ${"y".repeat(24)}`
      }
    }), "utf8");

    const exitCode = await runReadbackCaptureCli([
      "--api-url", url,
      "--release-id", "current",
      "--readback", readbackPath,
      "--source", "mock",
      "--idempotency-key", "idem-readback-cli-submit",
      "--output-receipt", outputReceipt,
      "--submit"
    ], {
      stdout: { write() {} },
      stderr: { write(value) { throw new Error(value); } }
    });
    assert.equal(exitCode, 0);
    const capture = JSON.parse(await readFile(outputReceipt, "utf8"));

    assert.equal(capture.status, "submitted");
    assert.equal(capture.http_status, 202);
    assert.equal(capture.api_receipt.schema_version, "a3.release_evidence_readback_capture_receipt.v1");
    assert.equal(capture.api_receipt.readback_id, "ghcrb_cli_submitted");
    assert.equal(capture.safety.token_included, false);
    assert.doesNotMatch(JSON.stringify(capture), /Bearer y|Authorization/);

    const list = await getJson(`${url}/api/a3/releases/current/readbacks?source=mock`);
    assert.equal(list.readback_count, 1);
    assert.equal(list.readbacks[0].readback_id, "ghcrb_cli_submitted");

    const summary = await getJson(`${url}/api/a3/releases/current/evidence-summary?source=mock&version=2`);
    assert.equal(summary.release_evidence_summary.github_check_readback.readback_id, "ghcrb_cli_submitted");
    assert.equal(summary.release_evidence_summary.github_check_readback.readback_status, "readback_confirmed");
  } finally {
    await new Promise((resolve) => server.close(resolve));
    await rm(dir, { recursive: true, force: true });
  }
});

async function getJson(url) {
  const response = await fetch(url);
  assert.equal(response.ok, true, `${url} returned ${response.status}`);
  return response.json();
}
