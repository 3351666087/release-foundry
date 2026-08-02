import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildCsvReport,
  buildDashboardSummary,
  buildJsonReport,
  buildMarkdownReport
} from "./report_builder.mjs";


export async function exportDemoReports(options) {
  const runFixture = await readJson(options.runs);
  const gradeFixture = await readJson(options.grades);
  const outputDir = resolve(options.outputDir);
  await mkdir(outputDir, { recursive: true });

  const jsonReport = buildJsonReport(runFixture, gradeFixture);
  const markdownReport = buildMarkdownReport(runFixture, gradeFixture);
  const csvReport = buildCsvReport(runFixture, gradeFixture);
  const files = {
    json: join(outputDir, "a3_report.json"),
    markdown: join(outputDir, "a3_report.md"),
    csv: join(outputDir, "a3_report.csv")
  };
  await writeFile(files.json, `${JSON.stringify(jsonReport, null, 2)}\n`, "utf8");
  await writeFile(files.markdown, markdownReport, "utf8");
  await writeFile(files.csv, csvReport, "utf8");

  const receipt = {
    schema_version: "a3.live_refund_report_export.v1",
    summary: buildDashboardSummary(runFixture, gradeFixture),
    a1_run_id: runFixture.run_id || runFixture.runs?.[0]?.run_id || "unknown",
    a2_report_id: gradeFixture.report_id || "unknown",
    exports: await Promise.all(Object.entries(files).map(async ([format, path]) => ({
      format,
      filename: basename(path),
      sha256: sha256(await readFile(path))
    }))),
    redaction_boundary: {
      source_is_synthetic: true,
      secret_values_allowed: false,
      real_customer_data_allowed: false
    }
  };
  await writeFile(join(outputDir, "a3_report_receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`, "utf8");
  return receipt;
}


function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (key === "--runs") options.runs = value;
    if (key === "--grades") options.grades = value;
    if (key === "--output-dir") options.outputDir = value;
    if (["--runs", "--grades", "--output-dir"].includes(key)) index += 1;
  }
  if (!options.runs || !options.grades || !options.outputDir) {
    throw new Error("Usage: node a3_demo_report_cli.mjs --runs <file> --grades <file> --output-dir <directory>");
  }
  return options;
}


async function readJson(path) {
  const location = path instanceof URL ? path : resolve(path);
  return JSON.parse(await readFile(location, "utf8"));
}


function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}


if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  exportDemoReports(parseArgs(process.argv.slice(2)))
    .then((receipt) => console.log(JSON.stringify(receipt, null, 2)))
    .catch((error) => {
      console.error(error.message);
      process.exitCode = 1;
    });
}
