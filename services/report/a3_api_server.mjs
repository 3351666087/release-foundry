import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  A3_DB_CONTRACT,
  A3StoreValidationError,
  createFixtureBackedA3Store
} from "./a3_store.mjs";
import {
  authorizeA3Operation,
  buildA3AuthContext,
  buildA3RbacPolicy
} from "./a3_auth_rbac_boundary.mjs";
import { renderShareableReportHtml } from "./a3_shareable_report.mjs";
import { buildA1A2SchemaDriftRadar } from "./a3_schema_drift_radar.mjs";
import { preflightA3UiAction } from "./a3_ui_action_security.mjs";

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

      if (request.method === "GET" && url.pathname === "/api/a3/auth/context") {
        const authContext = buildAuthContextFromRequest(request, url);
        return sendJson(response, 200, {
          schema_version: "a3.auth_context_api_response.v1",
          auth_context: authContext,
          rbac_policy_id: buildA3RbacPolicy().policy_id,
          sample_decisions: [
            authorizeA3Operation("read_dashboard", authContext),
            authorizeA3Operation("share_report", authContext),
            authorizeA3Operation("rotate_api_key", authContext)
          ],
          safety: {
            raw_actor_identity_exposed: false,
            raw_token_allowed: false,
            raw_cookie_allowed: false,
            raw_api_key_allowed: false
          }
        });
      }

      if (request.method === "GET" && url.pathname === "/api/a3/auth/rbac-policy") {
        return sendJson(response, 200, buildA3RbacPolicy());
      }

      if (request.method === "POST" && url.pathname === "/api/a3/auth/authorize") {
        const body = await readJsonBody(request);
        const authContext = buildAuthContextFromRequest(request, url, body);
        return sendJson(response, 200, authorizeA3Operation(body.operation || body.route || "read_dashboard", authContext, {
          requestId: body.request_id || body.requestId,
          traceId: body.trace_id || body.traceId
        }));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/ui-actions/preflight") {
        const body = await readJsonBody(request);
        const authContext = buildAuthContextFromRequest(request, url, body);
        const trustedIdentity = options.trustedIdentityBackend === true
          && ["hosted_session", "service_account"].includes(authContext.auth_state);
        return sendJson(response, 200, preflightA3UiAction({
          action: body.action,
          scope: body.scope || authContext.tenant_scope,
          auth: {
            authenticated: trustedIdentity,
            auth_state: authContext.auth_state,
            scope: authContext.tenant_scope
          },
          session: {
            state: trustedIdentity ? "active" : "untrusted",
            session_ref: trustedIdentity ? body.session_ref : null,
            expires_at: body.session_expires_at,
            scope: authContext.tenant_scope
          },
          actor: {
            role: authContext.role,
            permissions: authContext.permissions,
            actor_hash: authContext.actor_hash,
            scope: authContext.tenant_scope
          },
          evidence: body.evidence,
          audit_envelope: body.audit_envelope,
          payload: body.payload
        }));
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

      if (request.method === "GET" && url.pathname === "/api/a3/billing/readiness") {
        return sendJson(response, 200, await store.getBillingReadiness({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/billing/migration-readiness") {
        return sendJson(response, 200, await store.getBillingMigrationReadiness({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/live-workflow/readiness") {
        return sendJson(response, 200, await store.getLiveWorkflowReadiness({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/live-ops/control-plane") {
        return sendJson(response, 200, await store.getLiveOpsControlPlane({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/notifications/control-plane") {
        return sendJson(response, 200, await store.getNotificationControlPlane({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/commercial-api/contract") {
        return sendJson(response, 200, await store.getCommercialApiContract({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/peer-branches/calibration") {
        const authz = authorizeRequest(request, url, "read_peer_branch_calibration");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await store.getPeerBranchCalibration({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/a1-a2/schema-drift") {
        const authz = authorizeRequest(request, url, "read_schema_drift");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await buildA1A2SchemaDriftRadar({
          repoRoot: options.repoRoot,
          repoRef: url.searchParams.get("repo_ref") || undefined,
          comparedAgainst: url.searchParams.get("compared_against") || undefined
        }));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/events/outbox") {
        const authz = authorizeRequest(request, url, "read_event_outbox");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await store.listEventOutbox({
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined,
          eventType: url.searchParams.get("event_type") || undefined,
          deliveryStatus: url.searchParams.get("delivery_status") || undefined
        }));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a1-run-result") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "import_a1_run_result", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
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
        const authz = authorizeRequest(request, url, "import_a2_grade_result", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
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
        const security = dashboardSecurityContext(request, url, options);
        return sendJson(response, 200, await store.getDashboardSnapshot(sourceFrom(url), security));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/release-decision/provenance") {
        const security = dashboardSecurityContext(request, url, options);
        const dashboard = await store.getDashboardSnapshot(sourceFrom(url), security);
        return sendJson(response, 200, dashboard.release_decision_provenance);
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

      if (request.method === "POST" && url.pathname === "/api/a3/github/check-run/publish") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "publish_github_check", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const liveGuard = authorizeLiveGitHubPublish(request, url, body);
        if (!liveGuard.allowed) {
          return sendJson(response, 403, liveGitHubPublishDenied(liveGuard));
        }
        const receipt = await store.publishGitHubCheckRun({
          source: body.source || sourceFrom(url),
          repo: body.repo,
          headSha: body.head_sha || body.headSha,
          detailsUrl: body.details_url || body.detailsUrl,
          checkRunId: body.check_run_id || body.checkRunId,
          dryRun: liveGuard.dryRun,
          tokenEnvName: body.token_env || body.tokenEnvName || "GITHUB_TOKEN",
          apiBaseUrl: body.api_base_url || body.apiBaseUrl,
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          releaseVersion: body.release_version,
          environment: body.environment,
          idempotencyKey: idempotencyKeyFrom(request, body)
        });
        return receipt
          ? sendJson(response, 202, receipt)
          : sendJson(response, 404, notFound("github_publish_scope", body.source || sourceFrom(url)));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/github/pr-comment/publish") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "publish_github_pr_comment", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const liveGuard = authorizeLiveGitHubPublish(request, url, body);
        if (!liveGuard.allowed) {
          return sendJson(response, 403, liveGitHubPublishDenied(liveGuard));
        }
        const receipt = await store.publishGitHubPrComment({
          source: body.source || sourceFrom(url),
          repo: body.repo,
          pullNumber: body.pull_number || body.pullNumber,
          dryRun: liveGuard.dryRun,
          tokenEnvName: body.token_env || body.tokenEnvName || "GITHUB_TOKEN",
          apiBaseUrl: body.api_base_url || body.apiBaseUrl,
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          releaseVersion: body.release_version,
          environment: body.environment,
          idempotencyKey: idempotencyKeyFrom(request, body)
        });
        return receipt
          ? sendJson(response, 202, receipt)
          : sendJson(response, 404, notFound("github_publish_scope", body.source || sourceFrom(url)));
      }

      const releaseEvidenceReadbacksMatch = url.pathname.match(/^\/api\/a3\/releases\/([^/]+)\/readbacks$/);
      if (request.method === "POST" && releaseEvidenceReadbacksMatch) {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "capture_release_readback", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitReleaseEvidenceReadback(decodeURIComponent(releaseEvidenceReadbacksMatch[1]), body.readback || body, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          capturedAt: body.captured_at || body.capturedAt,
          idempotencyKey: idempotencyKeyFrom(request, body)
        });
        return receipt
          ? sendJson(response, 202, receipt)
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceReadbacksMatch[1]));
      }

      if (request.method === "GET" && releaseEvidenceReadbacksMatch) {
        const readbacks = await store.listReleaseEvidenceReadbacks(decodeURIComponent(releaseEvidenceReadbacksMatch[1]), {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        });
        return readbacks
          ? sendJson(response, 200, readbacks)
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceReadbacksMatch[1]));
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
        const authz = authorizeRequest(request, url, "plan_admin_action", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const plan = await store.planSaasAdminAction(body.action, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id
        });
        return sendJson(response, 200, plan);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/admin/actions/submit") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_admin_action", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitSaasAdminAction(body.action, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          reason: body.reason,
          target: body.target,
          requestedAt: body.requested_at || body.requestedAt,
          idempotencyKey: idempotencyKeyFrom(request, body)
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
        const authz = authorizeRequest(request, url, "submit_review_waiver", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitReviewWaiver(body.waiver || body.waiver_request || body, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha,
          idempotencyKey: idempotencyKeyFrom(request, body)
        });
        return sendJson(response, 202, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/review/approvals") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_review_approval", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitReviewApproval(body.approval || body.approval_record || body, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha,
          waiver: body.waiver,
          idempotencyKey: idempotencyKeyFrom(request, body)
        });
        return sendJson(response, 202, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/review/denials") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_review_denial", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitReviewDenial(body.denial || body.denial_record || body, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha,
          idempotencyKey: idempotencyKeyFrom(request, body)
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
        const authz = authorizeRequest(request, url, "share_report", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const report = await store.createShareableReport({
          source: body.source || sourceFrom(url),
          title: body.title,
          visibility: body.visibility,
          createdBy: body.created_by || body.createdBy || "a3-api",
          expiresAt: body.expires_at || body.expiresAt,
          organizationId: body.organization_id,
          projectId: body.project_id,
          idempotencyKey: idempotencyKeyFrom(request, body)
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
        const authz = authorizeRequest(request, url, "revoke_report", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.revokeReport(decodeURIComponent(reportRevokeMatch[1]), {
          reason: body.reason,
          revokedBy: body.revoked_by || body.revokedBy || "a3-api",
          revokedAt: body.revoked_at || body.revokedAt,
          idempotencyKey: idempotencyKeyFrom(request, body),
          ...reportScopeFrom(url, body)
        });
        return receipt
          ? sendJson(response, 200, receipt)
          : sendJson(response, 404, notFound("report", reportRevokeMatch[1]));
      }

      const reportViewMatch = url.pathname.match(/^\/api\/a3\/reports\/([^/]+)\/view$/);
      if (request.method === "POST" && reportViewMatch) {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "view_report", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const report = await store.getReportForView(decodeURIComponent(reportViewMatch[1]), {
          viewer: body.viewer || "api",
          viewedAt: body.viewed_at || body.viewedAt,
          idempotencyKey: idempotencyKeyFrom(request, body),
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

function authorizeRequest(request, url, operation, body = {}) {
  const authContext = buildAuthContextFromRequest(request, url, body);
  return authorizeA3Operation(operation, authContext, {
    requestId: body.request_id || body.requestId || request.headers["x-a3-request-id"],
    traceId: body.trace_id || body.traceId || request.headers["x-a3-trace-id"]
  });
}

function buildAuthContextFromRequest(request, url, body = {}) {
  return buildA3AuthContext({
    role: body.role || url.searchParams.get("role") || request.headers["x-a3-role"],
    actor_id: body.actor_id || body.actorId || url.searchParams.get("actor_id") || request.headers["x-a3-actor-id"],
    actor_hash: body.actor_hash || body.actorHash || request.headers["x-a3-actor-hash"],
    hosted_session: body.hosted_session === true || url.searchParams.get("hosted_session") === "true",
    service_account: body.service_account === true || request.headers["x-a3-service-account"] === "true",
    organization_id: body.organization_id || body.organizationId || url.searchParams.get("organization_id") || request.headers["x-a3-organization-id"],
    tenant_id: body.tenant_id || body.tenantId || url.searchParams.get("tenant_id") || request.headers["x-a3-tenant-id"],
    workspace_id: body.workspace_id || body.workspaceId || url.searchParams.get("workspace_id") || request.headers["x-a3-workspace-id"],
    project_id: body.project_id || body.projectId || url.searchParams.get("project_id") || request.headers["x-a3-project-id"],
    environment_id: body.environment_id || body.environmentId || url.searchParams.get("environment_id") || request.headers["x-a3-environment-id"]
  });
}

function dashboardSecurityContext(request, url, options = {}) {
  const authContext = buildAuthContextFromRequest(request, url);
  const trustedIdentity = options.trustedIdentityBackend === true
    && ["hosted_session", "service_account"].includes(authContext.auth_state);
  return {
    actor: trustedIdentity ? {
      role: authContext.role,
      ...authContext.tenant_scope
    } : {},
    auth: {
      trusted: trustedIdentity,
      auth_state: authContext.auth_state
    }
  };
}

function reportScopeFrom(url, body = {}) {
  return {
    source: body.source || sourceFrom(url),
    organizationId: body.organization_id || body.organizationId || url.searchParams.get("organization_id") || undefined,
    projectId: body.project_id || body.projectId || url.searchParams.get("project_id") || undefined
  };
}

function forbiddenPayload(decision = {}) {
  return {
    schema_version: "a3.api_authz_denied.v1",
    error: "forbidden",
    operation: decision.operation || "unknown",
    decision: decision.decision || "denied",
    reason: decision.reason || "This role is not allowed to perform the requested action.",
    required_permission: decision.required_permission || "unknown",
    role: decision.role || "unknown",
    tenant_scope: decision.tenant_scope,
    denied_state: decision.denied_state,
    authz_audit_event: decision.audit_event,
    safety: {
      raw_request_body_echoed: false,
      raw_actor_identity_exposed: false,
      raw_secret_values_allowed: false,
      real_cloud_mutation_performed: false
    }
  };
}

function authorizeLiveGitHubPublish(request, url, body = {}) {
  const liveRequested = body.allow_live === true || body.live === true || body.dry_run === false || body.dryRun === false;
  if (!liveRequested) {
    return {
      allowed: true,
      dryRun: true,
      liveRequested: false,
      reason: "Dry-run GitHub publish request; no external mutation is allowed."
    };
  }
  const authContext = buildAuthContextFromRequest(request, url, body);
  const hostedOrService = authContext.auth_state === "hosted_session" || authContext.auth_state === "service_account";
  return {
    allowed: hostedOrService,
    dryRun: false,
    liveRequested: true,
    auth_state: authContext.auth_state,
    role: authContext.role,
    tenant_scope: authContext.tenant_scope,
    reason: hostedOrService
      ? "Live GitHub publish is explicitly requested by hosted/session or service-account context."
      : "Live GitHub publish requires hosted session or service-account context."
  };
}

function liveGitHubPublishDenied(guard = {}) {
  return {
    schema_version: "a3.github_live_publish_denied.v1",
    error: "live_publish_requires_hosted_or_service_account",
    decision: "denied_requires_hosted_auth_or_service_account",
    live_requested: guard.liveRequested === true,
    auth_state: guard.auth_state || "unknown",
    role: guard.role || "unknown",
    reason: guard.reason,
    tenant_scope: guard.tenant_scope,
    denied_state: {
      http_status: 403,
      customer_message: "Live GitHub publishing requires hosted auth or a service account. Retry as dry-run or from CI/GitHub App worker."
    },
    safety: {
      raw_request_body_echoed: false,
      raw_actor_identity_exposed: false,
      raw_secret_values_allowed: false,
      token_included: false,
      real_github_mutation_performed: false
    }
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
    "access-control-allow-headers": "content-type,idempotency-key,x-idempotency-key,x-a3-role,x-a3-actor-id,x-a3-actor-hash,x-a3-organization-id,x-a3-tenant-id,x-a3-workspace-id,x-a3-project-id,x-a3-environment-id,x-a3-service-account"
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
