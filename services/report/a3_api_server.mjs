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

      if (request.method === "GET" && url.pathname === "/api/a3/db-migrations") {
        return sendJson(response, 200, await store.getDbMigrationPlan({
          dialect: url.searchParams.get("dialect") || "postgres"
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/usage/ledger") {
        return sendJson(response, 200, await store.getUsageLedger({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
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

      const releaseEvidenceMatch = url.pathname.match(/^\/api\/a3\/releases\/([^/]+)\/evidence-summary$/);
      if (request.method === "GET" && releaseEvidenceMatch) {
        const summary = await store.getReleaseEvidenceSummary(decodeURIComponent(releaseEvidenceMatch[1]), {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          version: url.searchParams.get("version") || url.searchParams.get("schema_version") || undefined
        });
        return summary
          ? sendJson(response, 200, summary)
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceMatch[1]));
      }

      const releaseEvidenceHealthMatch = url.pathname.match(/^\/api\/a3\/releases\/([^/]+)\/evidence-health$/);
      if (request.method === "GET" && releaseEvidenceHealthMatch) {
        const summary = await store.getReleaseEvidenceSummary(decodeURIComponent(releaseEvidenceHealthMatch[1]), {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          version: "2"
        });
        return summary
          ? sendJson(response, 200, {
            schema_version: "a3.release_evidence_health_api_response.v1",
            release_id: summary.release_id,
            summary_id: summary.summary_id,
            tenant_scope: summary.tenant_scope,
            release_evidence_health: summary.release_evidence_health,
            next_action: summary.next_action,
            safety: summary.safety
          })
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceHealthMatch[1]));
      }

      const releaseEvidenceDiffMatch = url.pathname.match(/^\/api\/a3\/releases\/([^/]+)\/evidence-diff$/);
      if (request.method === "GET" && releaseEvidenceDiffMatch) {
        const diff = await store.getReleaseEvidenceDiff(decodeURIComponent(releaseEvidenceDiffMatch[1]), {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          from: url.searchParams.get("from") || undefined,
          to: url.searchParams.get("to") || undefined
        });
        return diff
          ? sendJson(response, 200, diff)
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceDiffMatch[1]));
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

      if (request.method === "POST" && url.pathname === "/api/a3/admin/actions/submit") {
        const body = await readJsonBody(request);
        const receipt = await store.submitSaasAdminAction(body.action, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          reason: body.reason,
          target: body.target,
          requestedAt: body.requested_at || body.requestedAt
        });
        return sendJson(response, 202, receipt);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/admin/actions") {
        return sendJson(response, 200, await store.listSaasAdminActionRequests({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/review/waivers") {
        const body = await readJsonBody(request);
        const receipt = await store.submitReviewWaiver(body.waiver || body.waiver_request || body, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha
        });
        return sendJson(response, 202, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/review/approvals") {
        const body = await readJsonBody(request);
        const receipt = await store.submitReviewApproval(body.approval || body.approval_record || body, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha,
          waiver: body.waiver
        });
        return sendJson(response, 202, receipt);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/review/workflow") {
        return sendJson(response, 200, await store.getReviewWorkflow({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
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

      if (request.method === "GET" && url.pathname === "/api/a3/reports/center") {
        return sendJson(response, 200, await store.getReportCenter({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/artifacts/registry") {
        return sendJson(response, 200, await store.getArtifactRegistry({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/product/console") {
        return sendJson(response, 200, await store.getProductConsole({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      const reportMatch = url.pathname.match(/^\/api\/a3\/reports\/([^/]+)$/);
      if (request.method === "GET" && reportMatch) {
        const report = await store.getReport(decodeURIComponent(reportMatch[1]), reportScopeFrom(url));
        return report
          ? sendJson(response, 200, report)
          : sendJson(response, 404, notFound("report", reportMatch[1]));
      }

      const reportManifestMatch = url.pathname.match(/^\/api\/a3\/reports\/([^/]+)\/manifest$/);
      if (request.method === "GET" && reportManifestMatch) {
        const manifest = await store.getReportManifest(decodeURIComponent(reportManifestMatch[1]), reportScopeFrom(url));
        return manifest
          ? sendJson(response, 200, manifest)
          : sendJson(response, 404, notFound("report", reportManifestMatch[1]));
      }

      const reportRevokeMatch = url.pathname.match(/^\/api\/a3\/reports\/([^/]+)\/revoke$/);
      if (request.method === "POST" && reportRevokeMatch) {
        const body = await readJsonBody(request);
        const receipt = await store.revokeReport(decodeURIComponent(reportRevokeMatch[1]), {
          reason: body.reason,
          revokedBy: body.revoked_by || body.revokedBy || "a3-api",
          revokedAt: body.revoked_at || body.revokedAt,
          ...reportScopeFrom(url, body)
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
          viewedAt: body.viewed_at || body.viewedAt,
          ...reportScopeFrom(url, body)
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

      const shareTokenMatch = url.pathname.match(/^\/r\/([^/]+)$/);
      if (request.method === "GET" && shareTokenMatch) {
        const report = await store.getReportForShareToken(decodeURIComponent(shareTokenMatch[1]), {
          viewer: "share_token",
          viewedAt: url.searchParams.get("viewed_at") || undefined
        });
        if (!report || report.status === "not_found") {
          return sendHtml(response, 404, renderShareableReportHtml(report || { status: "not_found", access_result: "not_found" }));
        }
        return report.status === "shareable"
          ? sendHtml(response, 200, renderShareableReportHtml(report))
          : sendHtml(response, 410, renderShareableReportHtml(report));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/reports") {
        return sendJson(response, 200, {
          schema_version: "a3.api_report_list.v1",
          reports: await store.listReports(reportScopeFrom(url))
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
        message: redactErrorMessage(error.message)
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

function reportScopeFrom(url, body = {}) {
  return {
    source: body.source || sourceFrom(url),
    organizationId: body.organization_id || body.organizationId || url.searchParams.get("organization_id") || undefined,
    projectId: body.project_id || body.projectId || url.searchParams.get("project_id") || undefined
  };
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

function redactErrorMessage(message) {
  return String(message || "Unexpected internal error.")
    .replace(/\b(Authorization:\s*Bearer\s+)[A-Za-z0-9._-]{8,}/gi, "$1[REDACTED]")
    .replace(/\bBearer\s+[A-Za-z0-9._-]{8,}/gi, "Bearer [REDACTED]")
    .replace(/\bCookie:\s*[^;\n]+/gi, "Cookie: [REDACTED]")
    .replace(/\bASHR(?:_LABS)?_API_KEY\s*[:=]\s*[^\s"']+/gi, "ASHR_API_KEY=[REDACTED]")
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]");
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
