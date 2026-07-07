import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  A3_DB_CONTRACT,
  A3StoreValidationError,
  createFixtureBackedA3Store
} from "./a3_store.mjs";
import { renderShareableReportHtml } from "./a3_shareable_report.mjs";

export function createA3ApiHandler(options = {}) {
  const storePromise = Promise.resolve(options.store || createFixtureBackedA3Store({
    sources: options.sources || ["mock", "raw-a1", "raw-a2", "p3-media", "p3-official-demo"],
    repoRoot: options.repoRoot
  }));

  return async function handleA3ApiRequest(request, response) {
    try {
      const store = await storePromise;
      const url = new URL(request.url || "/", "http://127.0.0.1");

      if (request.method === "OPTIONS") {
        return sendJson(response, 204, {});
      }

      if (request.method === "GET" && url.pathname === "/api/a3/health") {
        return sendJson(response, 200, {
          schema_version: "a3.api_health.v1",
          ok: true,
          service: "a3-api",
          storage_mode: store.storage_mode || "fixture_file",
          db_ready: true
        });
      }

      if (request.method === "GET" && url.pathname === "/api/a3/db-contract") {
        return sendJson(response, 200, A3_DB_CONTRACT);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a1-run-result") {
        const body = await readJsonBody(request);
        const receipt = await store.importA1RunResult(body.run_result || body.runResult || body, {
          source: body.source || url.searchParams.get("source") || "api-ingest",
          sourceLabel: body.source_label || body.sourceLabel,
          organizationId: body.organization_id,
          projectId: body.project_id,
          idempotencyKey: idempotencyKeyFrom(request, body)
        });
        return sendJson(response, 201, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a2-grade-result") {
        const body = await readJsonBody(request);
        const receipt = await store.importA2GradeResult(body.grade_result || body.gradeResult || body, {
          source: body.source || url.searchParams.get("source") || "api-ingest",
          sourceLabel: body.source_label || body.sourceLabel,
          organizationId: body.organization_id,
          projectId: body.project_id,
          idempotencyKey: idempotencyKeyFrom(request, body)
        });
        return sendJson(response, 201, receipt);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/dashboard") {
        return sendJson(response, 200, await store.getDashboardSnapshot(sourceFrom(url)));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/admin/console") {
        return sendJson(response, 200, await store.getSaasAdminConsole({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/enterprise/readiness") {
        return sendJson(response, 200, await store.getEnterpriseReadiness({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/admin/actions/plan") {
        const body = await readJsonBody(request);
        const plan = await store.planSaasAdminAction(body.action, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id
        });
        return sendJson(response, 200, plan);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/runs") {
        return sendJson(response, 200, {
          schema_version: "a3.api_run_list.v1",
          source: sourceFrom(url),
          runs: await store.listRuns({ source: sourceFrom(url) })
        });
      }

      const runMatch = url.pathname.match(/^\/api\/a3\/runs\/([^/]+)$/);
      if (request.method === "GET" && runMatch) {
        const run = await store.getRun(decodeURIComponent(runMatch[1]), { source: sourceFrom(url) });
        return run
          ? sendJson(response, 200, run)
          : sendJson(response, 404, notFound("run", runMatch[1]));
      }

      const caseMatch = url.pathname.match(/^\/api\/a3\/cases\/([^/]+)$/);
      if (request.method === "GET" && caseMatch) {
        const detail = await store.getCase(decodeURIComponent(caseMatch[1]), { source: sourceFrom(url) });
        return detail
          ? sendJson(response, 200, detail)
          : sendJson(response, 404, notFound("case", caseMatch[1]));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/reports/share") {
        const body = await readJsonBody(request);
        const report = await store.createShareableReport({
          source: body.source || sourceFrom(url),
          title: body.title,
          visibility: body.visibility,
          createdBy: body.created_by || body.createdBy || "a3-api",
          expiresAt: body.expires_at || body.expiresAt,
          organizationId: body.organization_id,
          projectId: body.project_id
        });
        return sendJson(response, 201, report);
      }

      const reportMatch = url.pathname.match(/^\/api\/a3\/reports\/([^/]+)$/);
      if (request.method === "GET" && reportMatch) {
        const report = await store.getReport(decodeURIComponent(reportMatch[1]));
        return report
          ? sendJson(response, 200, report)
          : sendJson(response, 404, notFound("report", reportMatch[1]));
      }

      const reportRevokeMatch = url.pathname.match(/^\/api\/a3\/reports\/([^/]+)\/revoke$/);
      if (request.method === "POST" && reportRevokeMatch) {
        const body = await readJsonBody(request);
        const receipt = await store.revokeReport(decodeURIComponent(reportRevokeMatch[1]), {
          reason: body.reason,
          revokedBy: body.revoked_by || body.revokedBy || "a3-api",
          revokedAt: body.revoked_at || body.revokedAt
        });
        return receipt
          ? sendJson(response, 200, receipt)
          : sendJson(response, 404, notFound("report", reportRevokeMatch[1]));
      }

      const reportViewMatch = url.pathname.match(/^\/api\/a3\/reports\/([^/]+)\/view$/);
      if (request.method === "POST" && reportViewMatch) {
        const body = await readJsonBody(request);
        const report = await store.getReportForView(decodeURIComponent(reportViewMatch[1]), {
          viewer: body.viewer || "api",
          viewedAt: body.viewed_at || body.viewedAt
        });
        return report
          ? sendJson(response, report.status === "shareable" ? 200 : 410, {
            schema_version: "a3.report_view_receipt.v1",
            report_id: report.report_id,
            status: report.status,
            view_audit: report.view_audit,
            expires_at: report.expires_at,
            revoked_at: report.revoked_at
          })
          : sendJson(response, 404, notFound("report", reportViewMatch[1]));
      }

      const hostedReportMatch = url.pathname.match(/^\/reports\/([^/]+)$/);
      if (request.method === "GET" && hostedReportMatch) {
        const report = await store.getReportForView(decodeURIComponent(hostedReportMatch[1]), {
          viewer: "hosted_report",
          viewedAt: url.searchParams.get("viewed_at") || undefined
        });
        return report
          ? report.status === "shareable"
            ? sendHtml(response, 200, renderShareableReportHtml(report))
            : sendHtml(response, 410, renderShareableReportHtml(report))
          : sendHtml(response, 404, `<h1>Report not found</h1><p>${escapeHtml(hostedReportMatch[1])}</p>`);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/reports") {
        return sendJson(response, 200, {
          schema_version: "a3.api_report_list.v1",
          reports: await store.listReports()
        });
      }

      return sendJson(response, 404, notFound("route", url.pathname));
    } catch (error) {
      if (error instanceof A3StoreValidationError) {
        return sendJson(response, error.statusCode || 400, validationErrorPayload(error));
      }
      return sendJson(response, 500, {
        schema_version: "a3.api_error.v1",
        error: "internal_error",
        message: error.message
      });
    }
  };
}

export async function startA3ApiServer(options = {}) {
  const handler = createA3ApiHandler(options);
  const server = createServer(handler);
  const port = options.port || 0;
  const host = options.host || "127.0.0.1";
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, resolve);
  });
  const address = server.address();
  return {
    server,
    url: `http://${address.address}:${address.port}`
  };
}

function sourceFrom(url) {
  return url.searchParams.get("source") || "mock";
}

function idempotencyKeyFrom(request, body = {}) {
  return request.headers["idempotency-key"]
    || request.headers["x-idempotency-key"]
    || body.idempotency_key
    || body.idempotencyKey;
}

async function readJsonBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString("utf8").trim();
  return text ? JSON.parse(text) : {};
}

function sendJson(response, statusCode, payload) {
  const body = statusCode === 204 ? "" : `${JSON.stringify(payload, null, 2)}\n`;
  response.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type,idempotency-key,x-idempotency-key"
  });
  response.end(body);
}

function sendHtml(response, statusCode, body) {
  response.writeHead(statusCode, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
    "access-control-allow-origin": "*"
  });
  response.end(body);
}

function notFound(kind, id) {
  return {
    schema_version: "a3.api_error.v1",
    error: "not_found",
    kind,
    id: String(id)
  };
}

function validationErrorPayload(error) {
  return {
    schema_version: error.schema_version || "a3.api_validation_error.v1",
    error: error.error || "validation_error",
    message: error.message,
    request_type: error.requestType || "unknown",
    source: error.source || "unknown",
    details: error.details || [],
    private_evidence_path: null,
    redacted_summary: "Request was rejected before persistence; payload body is not echoed.",
    quota_or_cost: "local_validation_only"
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const portArg = Number.parseInt(process.env.PORT || process.argv[2] || "4173", 10);
  startA3ApiServer({ port: portArg }).then(({ url }) => {
    console.log(`A3 API server listening on ${url}`);
  });
}
