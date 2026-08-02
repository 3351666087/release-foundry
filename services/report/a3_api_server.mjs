import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  A3_DB_CONTRACT,
  A3StoreResourceNotFoundError,
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
import {
  A3_ROUTE_ACCESS_MODES,
  guardA3RouteAccess,
  matchA3RouteAccess
} from "./a3_route_access_control.mjs";

const REQUEST_BODY_PROMISE = Symbol("a3.requestBodyPromise");
const REQUEST_TRUSTED_ACCESS = Symbol("a3.trustedRouteAccess");
const A3_PREFLIGHT_ROUTE_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);
const DEFAULT_A3_MAX_JSON_BODY_BYTES = 1024 * 1024;
const DEFAULT_A3_BODY_READ_TIMEOUT_MS = 10_000;
const A3_SCOPE_FIELDS = [
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
];
const A3_DEPLOYMENT_VERIFICATION_REQUEST_FIELDS = new Set([
  "source",
  "expected_version",
  "expectedVersion",
  "request_id",
  "requestId",
  "trace_id",
  "traceId",
  ...A3_SCOPE_FIELDS
]);

class A3RequestBodyBoundaryError extends Error {
  constructor(bodyState, message) {
    super(message);
    this.name = "A3RequestBodyBoundaryError";
    this.code = "A3_REQUEST_BODY_BOUNDARY";
    this.bodyState = bodyState;
  }
}

export function createA3ApiHandler(options = {}) {
  const storePromise = Promise.resolve(options.store || createFixtureBackedA3Store({
    sources: options.sources || ["refund-demo", "mock", "raw-a1", "raw-a2", "p3-media", "p3-a2-round50", "p3-a2-round51", "p3-a2-round52", "p3-official-demo", "a3-golden-path", "a3-golden-path-rc2"],
    repoRoot: options.repoRoot
  }));

  return async function handleA3ApiRequest(request, response) {
    try {
      const store = await storePromise;
      const url = new URL(request.url || "/", "http://127.0.0.1");

      const routeAccess = await enforceRouteAccess(request, url, store, options);
      if (routeAccess?.halt) {
        return sendJson(response, routeAccess.status, routeAccess.body);
      }

      if (request.method === "OPTIONS") {
        return sendJson(response, 204, {});
      }

      if (request.method === "GET" && url.pathname === "/api/a3/health") {
        return sendJson(response, 200, {
          schema_version: "a3.api_health.v1",
          ok: true,
          service: "a3-api",
          storage_mode: store.storage_mode || "fixture_file",
          db_ready: store.db_ready === true,
          route_access_mode: configuredRouteAccessMode(options),
          hosted_identity_resolver_configured: typeof trustedPrincipalResolver(options) === "function",
          production_auth_claimed: false
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
        const trustedIdentity = request[REQUEST_TRUSTED_ACCESS]?.productionEnforced === true
          || (options.trustedIdentityBackend === true
            && ["hosted_session", "service_account"].includes(authContext.auth_state));
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
        return sendJson(response, 200, await store.getUsageLedger(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/billing/readiness") {
        return sendJson(response, 200, await store.getBillingReadiness(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/billing/migration-readiness") {
        return sendJson(response, 200, await store.getBillingMigrationReadiness(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/live-workflow/readiness") {
        return sendJson(response, 200, await store.getLiveWorkflowReadiness(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/live-ops/control-plane") {
        return sendJson(response, 200, await store.getLiveOpsControlPlane(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/notifications/control-plane") {
        return sendJson(response, 200, await store.getNotificationControlPlane(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/commercial-api/contract") {
        return sendJson(response, 200, await store.getCommercialApiContract(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/peer-branches/calibration") {
        const authz = authorizeRequest(request, url, "read_peer_branch_calibration");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await store.getPeerBranchCalibration(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        })));
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

      if (request.method === "GET" && url.pathname === "/api/a3/a1-a2/evidence-spine") {
        const authz = authorizeRequest(request, url, "read_schema_drift");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await store.getA1A2EvidenceSpine(scopedStoreOptions(url, {
          source: sourceFrom(url)
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/events/outbox") {
        const authz = authorizeRequest(request, url, "read_event_outbox");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await store.listEventOutbox(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined,
          eventType: url.searchParams.get("event_type") || undefined,
          deliveryStatus: url.searchParams.get("delivery_status") || undefined
        })));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a1-run-result") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "import_a1_run_result", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.importA1RunResult(body.run_result || body.runResult || body, scopedStoreOptions(url, {
          source: body.source || url.searchParams.get("source") || "api-ingest",
          sourceLabel: body.source_label || body.sourceLabel,
          organizationId: body.organization_id,
          projectId: body.project_id,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 201, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a2-grade-result") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "import_a2_grade_result", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.importA2GradeResult(body.grade_result || body.gradeResult || body, scopedStoreOptions(url, {
          source: body.source || url.searchParams.get("source") || "api-ingest",
          sourceLabel: body.source_label || body.sourceLabel,
          organizationId: body.organization_id,
          projectId: body.project_id,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 201, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a2-multimodal-comparison") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "import_a2_multimodal_comparison", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.importA2MultimodalComparison(
          body.comparison || body.multimodal_comparison || body,
          scopedStoreOptions(url, {
            source: body.source || url.searchParams.get("source") || "api-ingest",
            sourceLabel: body.source_label || body.sourceLabel,
            organizationId: body.organization_id,
            tenantId: body.tenant_id,
            workspaceId: body.workspace_id,
            projectId: body.project_id,
            environmentId: body.environment_id,
            actorHash: authz.actor_hash,
            importedAt: serverNow(options),
            idempotencyKey: request.headers["idempotency-key"]
          })
        );
        return sendJson(response, 201, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a2-multimodal-repeat-stability") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "import_a2_multimodal_repeat_stability", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.importA2MultimodalRepeatStability(
          body.stability_evidence || body.multimodal_repeat_stability || body,
          scopedStoreOptions(url, {
            source: body.source || url.searchParams.get("source") || "api-ingest",
            sourceLabel: body.source_label || body.sourceLabel,
            organizationId: body.organization_id,
            tenantId: body.tenant_id,
            workspaceId: body.workspace_id,
            projectId: body.project_id,
            environmentId: body.environment_id,
            actorHash: authz.actor_hash,
            importedAt: serverNow(options),
            idempotencyKey: request.headers["idempotency-key"]
          })
        );
        return sendJson(response, 201, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/import/a2-multimodal-provider-readiness") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "import_a2_multimodal_provider_readiness", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.importA2MultimodalProviderReadiness(
          body.provider_readiness_evidence || body.multimodal_provider_readiness || body,
          scopedStoreOptions(url, {
            source: body.source || url.searchParams.get("source") || "api-ingest",
            sourceLabel: body.source_label || body.sourceLabel,
            organizationId: body.organization_id,
            tenantId: body.tenant_id,
            workspaceId: body.workspace_id,
            projectId: body.project_id,
            environmentId: body.environment_id,
            actorHash: authz.actor_hash,
            importedAt: serverNow(options),
            idempotencyKey: request.headers["idempotency-key"]
          })
        );
        return sendJson(response, 201, receipt);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/dashboard") {
        const security = dashboardSecurityContext(request, url, options);
        return sendJson(response, 200, await store.getDashboardSnapshot(sourceFrom(url), security));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/deployment/sandbox-calibration") {
        const calibration = await store.getSelfHostSandboxCalibration(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        }));
        return calibration
          ? sendJson(response, 200, calibration)
          : sendJson(response, 404, notFound("self_host_sandbox_calibration", sourceFrom(url)));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/deployment/receipts") {
        return sendJson(response, 200, await store.listDeploymentReceipts(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/deployment/receipts") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_deployment_receipt", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitDeploymentReceipt(body.receipt || body, scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          submittedAt: body.submitted_at || body.submittedAt,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 201, receipt);
      }

      const deploymentReceiptReviewMatch = url.pathname.match(/^\/api\/a3\/deployment\/receipts\/([^/]+)\/review$/);
      if (request.method === "POST" && deploymentReceiptReviewMatch) {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "review_deployment_receipt", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.reviewDeploymentReceipt(
          decodeURIComponent(deploymentReceiptReviewMatch[1]),
          body.review || body,
          scopedStoreOptions(url, {
            source: body.source || sourceFrom(url),
            organizationId: body.organization_id,
            projectId: body.project_id,
            actor: body.actor,
            actorHash: body.actor_hash,
            reviewedAt: body.reviewed_at || body.reviewedAt,
            idempotencyKey: idempotencyKeyFrom(request, body)
          })
        );
        return receipt
          ? sendJson(response, 200, receipt)
          : sendJson(response, 404, notFound("deployment_receipt", deploymentReceiptReviewMatch[1]));
      }

      const deploymentReceiptVerifyMatch = url.pathname.match(/^\/internal\/a3\/deployment\/receipts\/([^/]+)\/verify$/);
      if (request.method === "POST" && deploymentReceiptVerifyMatch) {
        const body = await readJsonBody(request);
        const guard = trustedDeploymentReceiptVerifierGuard(request, body, options);
        if (!guard.allowed) {
          return sendJson(response, guard.status, guard.body);
        }
        const receiptId = decodeURIComponent(deploymentReceiptVerifyMatch[1]);
        const receipt = await store.verifyDeploymentReceiptAuthoritatively(
          receiptId,
          async (resolverInput) => guard.resolver({
            ...resolverInput,
            operation: "verify_deployment_receipt",
            requested_at: serverNow(options)
          }),
          scopedStoreOptions(url, {
            source: body.source || sourceFrom(url),
            expectedVersion: body.expected_version ?? body.expectedVersion,
            actorHash: guard.resolverIdAlias,
            resolverIdAlias: guard.resolverIdAlias,
            principalKind: "service_account",
            trustedResolver: true,
            idempotencyKey: idempotencyKeyFrom(request, body)
          })
        );
        return receipt
          ? sendJson(response, 200, receipt)
          : sendJson(response, 404, notFound("deployment_receipt", receiptId));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/release-decision/provenance") {
        const security = dashboardSecurityContext(request, url, options);
        const dashboard = await store.getDashboardSnapshot(sourceFrom(url), security);
        return sendJson(response, 200, dashboard.release_decision_provenance);
      }

      const releaseEvidenceMatch = url.pathname.match(/^\/api\/a3\/releases\/([^/]+)\/evidence-summary$/);
      if (request.method === "GET" && releaseEvidenceMatch) {
        const summary = await store.getReleaseEvidenceSummary(decodeURIComponent(releaseEvidenceMatch[1]), scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          version: url.searchParams.get("version") || url.searchParams.get("schema_version") || undefined
        }));
        return summary
          ? sendJson(response, 200, summary)
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceMatch[1]));
      }

      const releaseEvidenceHealthMatch = url.pathname.match(/^\/api\/a3\/releases\/([^/]+)\/evidence-health$/);
      if (request.method === "GET" && releaseEvidenceHealthMatch) {
        const summary = await store.getReleaseEvidenceSummary(decodeURIComponent(releaseEvidenceHealthMatch[1]), scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          version: "2"
        }));
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
        const diff = await store.getReleaseEvidenceDiff(decodeURIComponent(releaseEvidenceDiffMatch[1]), scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          from: url.searchParams.get("from") || undefined,
          to: url.searchParams.get("to") || undefined
        }));
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
        const liveGuard = await authorizeLiveGitHubPublish(request, url, body, store, options);
        if (!liveGuard.allowed) {
          return sendJson(response, 403, liveGitHubPublishDenied(liveGuard));
        }
        const receipt = await store.publishGitHubCheckRun(scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          repo: liveGuard.repo || body.repo,
          headSha: body.head_sha || body.headSha,
          detailsUrl: body.details_url || body.detailsUrl,
          checkRunId: body.check_run_id || body.checkRunId,
          dryRun: liveGuard.dryRun,
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          releaseVersion: body.release_version,
          environment: body.environment,
          decisionLedgerHeadHash: body.decision_ledger_head_hash || body.decisionLedgerHeadHash,
          decisionRecordId: body.decision_record_id || body.decisionRecordId,
          trustedReleaseAuthorization: liveGuard.releaseAuthorization,
          trustedGitHubTarget: liveGuard.githubTarget,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
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
        const liveGuard = await authorizeLiveGitHubPublish(request, url, body, store, options);
        if (!liveGuard.allowed) {
          return sendJson(response, 403, liveGitHubPublishDenied(liveGuard));
        }
        const receipt = await store.publishGitHubPrComment(scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          repo: liveGuard.repo || body.repo,
          pullNumber: body.pull_number || body.pullNumber,
          dryRun: liveGuard.dryRun,
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          releaseVersion: body.release_version,
          environment: body.environment,
          decisionLedgerHeadHash: body.decision_ledger_head_hash || body.decisionLedgerHeadHash,
          decisionRecordId: body.decision_record_id || body.decisionRecordId,
          trustedReleaseAuthorization: liveGuard.releaseAuthorization,
          trustedGitHubTarget: liveGuard.githubTarget,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
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
        const receipt = await store.submitReleaseEvidenceReadback(decodeURIComponent(releaseEvidenceReadbacksMatch[1]), body.readback || body, scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          capturedAt: body.captured_at || body.capturedAt,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return receipt
          ? sendJson(response, 202, receipt)
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceReadbacksMatch[1]));
      }

      if (request.method === "GET" && releaseEvidenceReadbacksMatch) {
        const readbacks = await store.listReleaseEvidenceReadbacks(decodeURIComponent(releaseEvidenceReadbacksMatch[1]), scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        }));
        return readbacks
          ? sendJson(response, 200, readbacks)
          : sendJson(response, 404, notFound("release_evidence", releaseEvidenceReadbacksMatch[1]));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/admin/console") {
        return sendJson(response, 200, await store.getSaasAdminConsole(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/enterprise/readiness") {
        return sendJson(response, 200, await store.getEnterpriseReadiness(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/admin/actions/plan") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "plan_admin_action", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const plan = await store.planSaasAdminAction(body.action, scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id
        }));
        return sendJson(response, 200, plan);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/admin/actions/submit") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_admin_action", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitSaasAdminAction(body.action, scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          actor: body.actor,
          actorHash: body.actor_hash,
          reason: body.reason,
          target: body.target,
          requestedAt: body.requested_at || body.requestedAt,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 202, receipt);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/admin/actions") {
        return sendJson(response, 200, await store.listSaasAdminActionRequests(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "POST" && url.pathname === "/api/a3/review/waivers") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_review_waiver", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitReviewWaiver(body.waiver || body.waiver_request || body, scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 202, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/review/approvals") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_review_approval", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitReviewApproval(body.approval || body.approval_record || body, scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 202, receipt);
      }

      if (request.method === "POST" && url.pathname === "/api/a3/review/denials") {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_review_denial", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.submitReviewDenial(body.denial || body.denial_record || body, scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          organizationId: body.organization_id,
          projectId: body.project_id,
          requestedAt: body.requested_at || body.requestedAt,
          generatedAt: body.generated_at || body.generatedAt,
          releaseVersion: body.release_version,
          environment: body.environment,
          headSha: body.head_sha || body.headSha,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 202, receipt);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/review/workflow") {
        return sendJson(response, 200, await store.getReviewWorkflow(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/review/multimodal-queue") {
        return sendJson(response, 200, await store.getMultimodalReviewQueue(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined,
          now: serverNow(options)
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/review/multimodal-repeat-stability") {
        const authz = authorizeRequest(request, url, "read_multimodal_repeat_stability");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await store.getMultimodalRepeatStability(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/providers/multimodal-readiness") {
        const authz = authorizeRequest(request, url, "read_multimodal_provider_readiness");
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        return sendJson(response, 200, await store.getMultimodalProviderReadiness(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          tenantId: url.searchParams.get("tenant_id") || undefined,
          workspaceId: url.searchParams.get("workspace_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined,
          environmentId: url.searchParams.get("environment_id") || undefined
        })));
      }

      const multimodalAssignmentMatch = url.pathname.match(/^\/api\/a3\/review\/multimodal-queue\/([^/]+)\/assignment$/);
      if (request.method === "POST" && multimodalAssignmentMatch) {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "manage_multimodal_review_assignment", body);
        if (!authz.allowed) {
          return sendJson(response, 403, forbiddenPayload(authz));
        }
        const receipt = await store.mutateMultimodalReviewAssignment(
          decodeURIComponent(multimodalAssignmentMatch[1]),
          body.assignment || {},
          scopedStoreOptions(url, {
            source: body.source || sourceFrom(url),
            organizationId: body.organization_id,
            tenantId: body.tenant_id,
            workspaceId: body.workspace_id,
            projectId: body.project_id,
            environmentId: body.environment_id,
            actorHash: authz.actor_hash,
            actorRole: authz.role,
            idempotencyKey: request.headers["idempotency-key"],
            now: serverNow(options)
          })
        );
        return sendJson(response, 200, receipt);
      }

      const multimodalEvidenceRequestCollectionMatch = url.pathname.match(
        /^\/api\/a3\/review\/multimodal-queue\/([^/]+)\/evidence-requests$/
      );
      if (request.method === "GET" && multimodalEvidenceRequestCollectionMatch) {
        const authz = authorizeRequest(request, url, "read_multimodal_review_evidence_requests");
        if (!authz.allowed) return sendJson(response, 403, forbiddenPayload(authz));
        const listing = await store.listMultimodalReviewEvidenceRequests(
          decodeURIComponent(multimodalEvidenceRequestCollectionMatch[1]),
          scopedStoreOptions(url, {
            source: sourceFrom(url),
            organizationId: url.searchParams.get("organization_id") || undefined,
            tenantId: url.searchParams.get("tenant_id") || undefined,
            workspaceId: url.searchParams.get("workspace_id") || undefined,
            projectId: url.searchParams.get("project_id") || undefined,
            environmentId: url.searchParams.get("environment_id") || undefined,
            now: serverNow(options)
          })
        );
        return sendJson(response, 200, listing);
      }
      if (request.method === "POST" && multimodalEvidenceRequestCollectionMatch) {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "create_multimodal_review_evidence_request", body);
        if (!authz.allowed) return sendJson(response, 403, forbiddenPayload(authz));
        const receipt = await store.createMultimodalReviewEvidenceRequest(
          decodeURIComponent(multimodalEvidenceRequestCollectionMatch[1]),
          body.evidence_request || {},
          scopedStoreOptions(url, {
            source: body.source || sourceFrom(url),
            organizationId: body.organization_id,
            tenantId: body.tenant_id,
            workspaceId: body.workspace_id,
            projectId: body.project_id,
            environmentId: body.environment_id,
            actorHash: authz.actor_hash,
            actorRole: authz.role,
            idempotencyKey: request.headers["idempotency-key"],
            now: serverNow(options)
          })
        );
        return sendJson(response, 201, receipt);
      }

      const multimodalEvidenceSubmissionMatch = url.pathname.match(
        /^\/api\/a3\/review\/multimodal-queue\/([^/]+)\/evidence-requests\/([^/]+)\/submissions$/
      );
      if (request.method === "POST" && multimodalEvidenceSubmissionMatch) {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "submit_multimodal_review_evidence_request", body);
        if (!authz.allowed) return sendJson(response, 403, forbiddenPayload(authz));
        const receipt = await store.submitMultimodalReviewEvidenceRequest(
          decodeURIComponent(multimodalEvidenceSubmissionMatch[1]),
          decodeURIComponent(multimodalEvidenceSubmissionMatch[2]),
          body.submission || {},
          scopedStoreOptions(url, {
            source: body.source || sourceFrom(url),
            organizationId: body.organization_id,
            tenantId: body.tenant_id,
            workspaceId: body.workspace_id,
            projectId: body.project_id,
            environmentId: body.environment_id,
            actorHash: authz.actor_hash,
            actorRole: authz.role,
            idempotencyKey: request.headers["idempotency-key"],
            now: serverNow(options)
          })
        );
        return sendJson(response, 200, receipt);
      }

      const multimodalEvidenceReviewMatch = url.pathname.match(
        /^\/api\/a3\/review\/multimodal-queue\/([^/]+)\/evidence-requests\/([^/]+)\/review$/
      );
      if (request.method === "POST" && multimodalEvidenceReviewMatch) {
        const body = await readJsonBody(request);
        const authz = authorizeRequest(request, url, "review_multimodal_review_evidence_request", body);
        if (!authz.allowed) return sendJson(response, 403, forbiddenPayload(authz));
        const receipt = await store.reviewMultimodalReviewEvidenceRequest(
          decodeURIComponent(multimodalEvidenceReviewMatch[1]),
          decodeURIComponent(multimodalEvidenceReviewMatch[2]),
          body.review || {},
          scopedStoreOptions(url, {
            source: body.source || sourceFrom(url),
            organizationId: body.organization_id,
            tenantId: body.tenant_id,
            workspaceId: body.workspace_id,
            projectId: body.project_id,
            environmentId: body.environment_id,
            actorHash: authz.actor_hash,
            actorRole: authz.role,
            idempotencyKey: request.headers["idempotency-key"],
            now: serverNow(options)
          })
        );
        return sendJson(response, 200, receipt);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/runs") {
        return sendJson(response, 200, {
          schema_version: "a3.api_run_list.v1",
          source: sourceFrom(url),
          runs: await store.listRuns(scopedStoreOptions(url, { source: sourceFrom(url) }))
        });
      }

      const runMatch = url.pathname.match(/^\/api\/a3\/runs\/([^/]+)$/);
      if (request.method === "GET" && runMatch) {
        const run = await store.getRun(decodeURIComponent(runMatch[1]), scopedStoreOptions(url, { source: sourceFrom(url) }));
        return run
          ? sendJson(response, 200, run)
          : sendJson(response, 404, notFound("run", runMatch[1]));
      }

      const caseMatch = url.pathname.match(/^\/api\/a3\/cases\/([^/]+)$/);
      if (request.method === "GET" && caseMatch) {
        const detail = await store.getCase(decodeURIComponent(caseMatch[1]), scopedStoreOptions(url, { source: sourceFrom(url) }));
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
        const report = await store.createShareableReport(scopedStoreOptions(url, {
          source: body.source || sourceFrom(url),
          title: body.title,
          visibility: body.visibility,
          createdBy: body.created_by || body.createdBy || "a3-api",
          expiresAt: body.expires_at || body.expiresAt,
          organizationId: body.organization_id,
          projectId: body.project_id,
          idempotencyKey: idempotencyKeyFrom(request, body)
        }));
        return sendJson(response, 201, report);
      }

      if (request.method === "GET" && url.pathname === "/api/a3/reports/center") {
        return sendJson(response, 200, await store.getReportCenter(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/artifacts/registry") {
        return sendJson(response, 200, await store.getArtifactRegistry(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
      }

      if (request.method === "GET" && url.pathname === "/api/a3/product/console") {
        return sendJson(response, 200, await store.getProductConsole(scopedStoreOptions(url, {
          source: sourceFrom(url),
          organizationId: url.searchParams.get("organization_id") || undefined,
          projectId: url.searchParams.get("project_id") || undefined
        })));
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
        const report = await store.getReportForView(decodeURIComponent(reportViewMatch[1]), scopedStoreOptions(url, {
          viewer: body.viewer || "api",
          viewedAt: serverNow(options),
          idempotencyKey: idempotencyKeyFrom(request, body),
          ...reportScopeFrom(url, body)
        }));
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
        const report = await store.getReportForView(decodeURIComponent(hostedReportMatch[1]), scopedStoreOptions(url, {
          viewer: "hosted_report",
          viewedAt: serverNow(options)
        }));
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
          viewedAt: serverNow(options)
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
      if (error instanceof A3StoreResourceNotFoundError) {
        return sendJson(response, 404, {
          schema_version: "a3.api_error.v1",
          error: "not_found"
        });
      }
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

export function resolveA3DirectStartRouteAccessMode(env = {}) {
  return env.A3_ROUTE_ACCESS_MODE || A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED;
}

function sourceFrom(url) {
  return url.searchParams.get("source") || "mock";
}

async function enforceRouteAccess(request, url, store, options = {}) {
  const mode = configuredRouteAccessMode(options);
  const transport = resolveRouteAccessTransport(request);
  const accessRequest = { method: transport.routeMethod, url: request.url };
  const route = matchA3RouteAccess(accessRequest);
  if (!route.matched && mode !== A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED && !transport.preflight) {
    return null;
  }

  const readsBody = route.matched
    && route.access === "sensitive"
    && !["GET", "HEAD"].includes(transport.routeMethod)
    && !transport.preflight;
  let body = {};
  let requestBodyState = "not_read";
  let principal;
  const requestId = request.headers["x-request-id"] || request.headers["x-a3-request-id"] || randomUUID();
  const traceId = request.headers["x-trace-id"] || request.headers["x-a3-trace-id"];

  if (mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED && route.access === "sensitive") {
    const resolver = trustedPrincipalResolver(options);
    try {
      principal = resolver
        ? await resolver(request, {
            method: transport.routeMethod,
            transport_method: transport.transportMethod,
            preflight_for_method: transport.preflightMethod,
            pathname: url.pathname,
            operation: route.operation_id,
            required_permission: route.required_permission
          })
        : null;
    } catch {
      principal = null;
    }

    if (readsBody) {
      const principalScope = extractScopeAssertions(principal)[0] || {};
      const preliminaryScope = mergeTrustedRequestedScope(principalScope, url, {});
      const preliminaryDecision = guardA3RouteAccess({
        ...accessRequest,
        body: {},
        requested_scope: preliminaryScope
      }, {
        mode,
        trustedPrincipal: principal,
        requestedScope: preliminaryScope,
        requestId,
        traceId,
        requestBodyState: "not_read",
        transportMethod: transport.transportMethod,
        preflightMethod: transport.preflightMethod,
        now: typeof options.now === "function" ? options.now() : options.now
      });
      if (!preliminaryDecision.allowed) {
        if (!await persistHostedAccessDecision(store, preliminaryDecision)) {
          return hostedAccessAuditUnavailable();
        }
        return {
          halt: true,
          status: preliminaryDecision.http_status,
          body: preliminaryDecision.response.body
        };
      }
    }
  }

  if (readsBody) {
    try {
      body = await readJsonBody(request, options);
      requestBodyState = "valid_json";
    } catch (error) {
      if (!(error instanceof A3RequestBodyBoundaryError)) throw error;
      requestBodyState = error.bodyState;
    }
  }

  if (mode === A3_ROUTE_ACCESS_MODES.DEMO_CONTRACT) {
    principal = buildDemoContractPrincipal(request, url, body, options);
  }

  const principalScope = extractScopeAssertions(principal)[0] || {};
  const requestedScope = mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED
    ? mergeTrustedRequestedScope(principalScope, url, body)
    : principalScope;
  const decision = guardA3RouteAccess({
    method: transport.routeMethod,
    url: request.url,
    body,
    requested_scope: requestedScope
  }, {
    mode,
    trustedPrincipal: mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED ? principal : undefined,
    contractPrincipal: mode === A3_ROUTE_ACCESS_MODES.DEMO_CONTRACT ? principal : undefined,
    requestedScope,
    requestId,
    traceId,
    requestBodyState,
    transportMethod: transport.transportMethod,
    preflightMethod: transport.preflightMethod,
    now: typeof options.now === "function" ? options.now() : options.now
  });

  if (mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED && route.access !== "public") {
    if (!await persistHostedAccessDecision(store, decision)) {
      return hostedAccessAuditUnavailable();
    }
  }

  if (decision.decision === "denied_invalid_enforcement_mode") {
    return {
      halt: true,
      status: 503,
      body: {
        schema_version: "a3.route_access_unavailable.v1",
        error: "authorization_configuration_invalid",
        message: "The authorization service is temporarily unavailable."
      }
    };
  }

  if (!decision.allowed) {
    if (mode !== A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED
      && !transport.preflight
      && ["not_read", "valid_json"].includes(requestBodyState)) {
      return null;
    }
    return {
      halt: true,
      status: decision.http_status,
      body: decision.response.body
    };
  }

  if (mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED && route.access === "sensitive") {
    attachTrustedRequestAccess(request, url, body, principal, decision);
  }
  return { halt: false, decision };
}

async function persistHostedAccessDecision(store, decision) {
  if (typeof store.recordAccessDecision !== "function") return false;
  try {
    await store.recordAccessDecision(decision, { source: "hosted-access" });
    return true;
  } catch {
    return false;
  }
}

function resolveRouteAccessTransport(request) {
  const transportMethod = String(request.method || "GET").trim().toUpperCase();
  if (transportMethod !== "OPTIONS") {
    return {
      transportMethod,
      routeMethod: transportMethod,
      preflight: false,
      preflightMethod: null
    };
  }

  const requestedMethod = String(request.headers["access-control-request-method"] || "")
    .trim()
    .toUpperCase();
  const preflightMethod = A3_PREFLIGHT_ROUTE_METHODS.has(requestedMethod) ? requestedMethod : null;
  return {
    transportMethod: "OPTIONS",
    routeMethod: preflightMethod || "OPTIONS",
    preflight: true,
    preflightMethod
  };
}

function configuredRouteAccessMode(options = {}) {
  const value = String(
    options.routeAccessMode
    || options.accessMode
    || A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED
  ).trim().toLowerCase();
  if (["hosted", A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED].includes(value)) {
    return A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED;
  }
  if (["demo", "contract", A3_ROUTE_ACCESS_MODES.DEMO_CONTRACT].includes(value)) {
    return A3_ROUTE_ACCESS_MODES.DEMO_CONTRACT;
  }
  return value;
}

function trustedPrincipalResolver(options = {}) {
  if (typeof options.resolveTrustedPrincipal === "function") return options.resolveTrustedPrincipal;
  if (typeof options.trustedPrincipalResolver === "function") return options.trustedPrincipalResolver;
  return null;
}

function buildDemoContractPrincipal(request, url, body, options = {}) {
  const context = buildA3AuthContext({
    role: body.role || url.searchParams.get("role") || request.headers["x-a3-role"] || options.demoRole || "owner",
    actor_id: body.actor_id || body.actorId || url.searchParams.get("actor_id") || request.headers["x-a3-actor-id"] || "actor-demo-contract",
    actor_hash: body.actor_hash || body.actorHash || request.headers["x-a3-actor-hash"],
    organization_id: body.organization_id || body.organizationId || url.searchParams.get("organization_id") || request.headers["x-a3-organization-id"],
    tenant_id: body.tenant_id || body.tenantId || url.searchParams.get("tenant_id") || request.headers["x-a3-tenant-id"],
    workspace_id: body.workspace_id || body.workspaceId || url.searchParams.get("workspace_id") || request.headers["x-a3-workspace-id"],
    project_id: body.project_id || body.projectId || url.searchParams.get("project_id") || request.headers["x-a3-project-id"],
    environment_id: body.environment_id || body.environmentId || url.searchParams.get("environment_id") || request.headers["x-a3-environment-id"]
  });
  return {
    role: context.role,
    actor_hash: context.actor_hash,
    permissions: context.permissions,
    tenant_scope: context.tenant_scope,
    principal_type: "demo_contract"
  };
}

function mergeTrustedRequestedScope(principalScope, url, body) {
  const assertions = [scopeAssertionsFromUrl(url), ...extractScopeAssertions(body)];
  const merged = { ...principalScope };
  const mismatchedFields = new Set();
  for (const assertion of assertions) {
    for (const field of A3_SCOPE_FIELDS) {
      if (Object.prototype.hasOwnProperty.call(assertion, field)) {
        if (assertion[field] !== principalScope[field] && !mismatchedFields.has(field)) {
          merged[field] = assertion[field];
          mismatchedFields.add(field);
        }
      }
    }
  }
  return merged;
}

function scopeAssertionsFromUrl(url) {
  const scope = {};
  for (const field of A3_SCOPE_FIELDS) {
    const camel = snakeToCamel(field);
    if (url.searchParams.has(field)) scope[field] = url.searchParams.get(field);
    else if (url.searchParams.has(camel)) scope[field] = url.searchParams.get(camel);
  }
  return scope;
}

function extractScopeAssertions(value, seen = new Set()) {
  if (!value || typeof value !== "object" || seen.has(value)) return [];
  seen.add(value);
  if (Array.isArray(value)) {
    return value.flatMap((item) => extractScopeAssertions(item, seen));
  }
  const assertion = {};
  for (const field of A3_SCOPE_FIELDS) {
    const camel = snakeToCamel(field);
    if (Object.prototype.hasOwnProperty.call(value, field)) assertion[field] = value[field];
    else if (Object.prototype.hasOwnProperty.call(value, camel)) assertion[field] = value[camel];
  }
  return [
    ...(Object.keys(assertion).length ? [assertion] : []),
    ...Object.values(value).flatMap((item) => extractScopeAssertions(item, seen))
  ];
}

function attachTrustedRequestAccess(request, url, body, principal, decision) {
  const scope = Object.fromEntries(A3_SCOPE_FIELDS.map((field) => [field, decision.audit_event[field]]));
  const authContext = buildA3AuthContext({
    role: decision.role,
    actor_hash: decision.principal.principal_fingerprint,
    tenant_scope: scope,
    hosted_session: decision.principal.principal_type !== "service_account",
    service_account: decision.principal.principal_type === "service_account",
    credential_source: "a1_trusted_principal"
  });
  if (Array.isArray(principal?.permissions)) {
    authContext.permissions = authContext.permissions.filter((permission) => principal.permissions.includes(permission));
  }
  request[REQUEST_TRUSTED_ACCESS] = {
    productionEnforced: true,
    authContext,
    tenantScope: scope,
    accessDecision: decision
  };
  applyTrustedScope(url, scope);
}

function applyTrustedScope(url, scope) {
  for (const field of A3_SCOPE_FIELDS) {
    url.searchParams.set(field, scope[field]);
  }
  // The trusted scope lives in request context and rewritten selectors. A1/A2 payload bodies stay byte-for-byte owned by their lanes.
}

function hostedAccessAuditUnavailable() {
  return {
    halt: true,
    status: 503,
    body: {
      schema_version: "a3.route_access_unavailable.v1",
      error: "authorization_audit_unavailable",
      message: "The authorization service is temporarily unavailable."
    }
  };
}

function snakeToCamel(field) {
  return field.replace(/_([a-z])/g, (_, character) => character.toUpperCase());
}

function authorizeRequest(request, url, operation, body = {}) {
  const authContext = buildAuthContextFromRequest(request, url, body);
  return authorizeA3Operation(operation, authContext, {
    requestId: body.request_id || body.requestId || request.headers["x-a3-request-id"],
    traceId: body.trace_id || body.traceId || request.headers["x-a3-trace-id"]
  });
}

function buildAuthContextFromRequest(request, url, body = {}) {
  if (request[REQUEST_TRUSTED_ACCESS]?.authContext) {
    return request[REQUEST_TRUSTED_ACCESS].authContext;
  }
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
  const trustedIdentity = request[REQUEST_TRUSTED_ACCESS]?.productionEnforced === true
    || (options.trustedIdentityBackend === true
      && ["hosted_session", "service_account"].includes(authContext.auth_state));
  return {
    ...scopedStoreOptions(url),
    now: serverNow(options),
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
  return scopedStoreOptions(url, {
    source: body.source || sourceFrom(url),
    organizationId: body.organization_id || body.organizationId || url.searchParams.get("organization_id") || undefined,
    projectId: body.project_id || body.projectId || url.searchParams.get("project_id") || undefined
  });
}

function scopedStoreOptions(url, options = {}) {
  const trustedScope = {};
  for (const field of A3_SCOPE_FIELDS) {
    if (url.searchParams.has(field)) {
      trustedScope[snakeToCamel(field)] = url.searchParams.get(field);
    }
  }
  const hostedScopeBound = A3_SCOPE_FIELDS.every((field) => url.searchParams.has(field));
  return {
    ...options,
    ...(hostedScopeBound && options.source !== undefined ? { source: sourceFrom(url) } : {}),
    ...trustedScope,
    enforceScope: hostedScopeBound
  };
}

function serverNow(options = {}) {
  const value = typeof options.now === "function" ? options.now() : options.now;
  const parsed = value === undefined ? Date.now() : new Date(value).getTime();
  return new Date(Number.isFinite(parsed) ? parsed : Date.now()).toISOString();
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

async function authorizeLiveGitHubPublish(request, url, body = {}, store = {}, options = {}) {
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
  const productionEnforced = request[REQUEST_TRUSTED_ACCESS]?.productionEnforced === true;
  if (!productionEnforced || !hostedOrService) {
    return {
      allowed: false,
      dryRun: false,
      liveRequested: true,
      auth_state: authContext.auth_state,
      role: authContext.role,
      tenant_scope: authContext.tenant_scope,
      decision: "denied_requires_hosted_auth_or_service_account",
      error: "live_publish_requires_hosted_or_service_account",
      reason: "Live GitHub publish requires hosted enforcement and a server-verified session or service account."
    };
  }

  const releaseResolver = trustedReleaseAuthorizationResolver(options);
  if (!releaseResolver) {
    return {
      allowed: false,
      dryRun: false,
      liveRequested: true,
      auth_state: authContext.auth_state,
      role: authContext.role,
      tenant_scope: authContext.tenant_scope,
      decision: "denied_a2_trusted_authority_unavailable",
      error: "a2_release_decision_required",
      reason: "Live GitHub publish requires a server-side A2 trusted authority resolver.",
      release_authorization: { reason_code: "trusted_a2_authority_unavailable", release_ready: false }
    };
  }

  let releaseAuthorization;
  try {
    releaseAuthorization = await releaseResolver({
      source: body.source || sourceFrom(url),
      tenant_scope: request[REQUEST_TRUSTED_ACCESS]?.tenantScope,
      decisionLedgerHeadHash: body.decision_ledger_head_hash || body.decisionLedgerHeadHash,
      decisionRecordId: body.decision_record_id || body.decisionRecordId,
      operation: url.pathname.includes("pr-comment") ? "publish_github_pr_comment" : "publish_github_check"
    });
  } catch {
    releaseAuthorization = null;
  }
  const expectedHeadHash = body.decision_ledger_head_hash || body.decisionLedgerHeadHash;
  const expectedRecordId = body.decision_record_id || body.decisionRecordId;
  const trustedRequestScope = request[REQUEST_TRUSTED_ACCESS]?.tenantScope || {};
  const releaseScope = releaseAuthorization?.tenant_scope || {};
  const releaseAuthorityVerified = releaseAuthorization?.authority === "a2_trusted_service"
    && releaseAuthorization?.allowed === true
    && releaseAuthorization?.release_ready === true
    && releaseAuthorization?.upstream_decision === "allow"
    && releaseAuthorization?.decision_ledger?.head_hash === expectedHeadHash
    && releaseAuthorization?.decision_ledger?.record_id === expectedRecordId
    && A3_SCOPE_FIELDS.every((field) => releaseScope[field] === trustedRequestScope[field]);
  if (!releaseAuthorityVerified) {
    return {
      allowed: false,
      dryRun: false,
      liveRequested: true,
      auth_state: authContext.auth_state,
      role: authContext.role,
      tenant_scope: authContext.tenant_scope,
      decision: "denied_by_a2_decision_ledger",
      error: "a2_release_decision_required",
      reason: "Live GitHub publish requires a current release-ready A2 Decision Ledger record.",
      release_authorization: {
        reason_code: releaseAuthorization?.reason_code || "trusted_decision_authorization_failed",
        release_ready: releaseAuthorization?.release_ready === true,
        upstream_decision: releaseAuthorization?.upstream_decision || "unknown"
      }
    };
  }
  if ((options.githubExecutorAuthority || store.github_executor_authority) !== "a1_trusted_worker") {
    return {
      allowed: false,
      dryRun: false,
      liveRequested: true,
      auth_state: authContext.auth_state,
      role: authContext.role,
      tenant_scope: authContext.tenant_scope,
      decision: "denied_requires_a1_trusted_github_worker",
      error: "trusted_github_executor_required",
      reason: "Live GitHub publication requires an A1-owned trusted worker with server-fixed endpoint and secret custody.",
      release_authorization: {
        reason_code: "a1_trusted_github_worker_unavailable",
        release_ready: true,
        upstream_decision: releaseAuthorization.upstream_decision || "allow"
      }
    };
  }

  const targetResolver = trustedGitHubTargetResolver(options);
  let githubTarget;
  try {
    githubTarget = targetResolver
      ? await targetResolver({
          tenant_scope: request[REQUEST_TRUSTED_ACCESS]?.tenantScope,
          requested_repo: body.repo,
          operation: url.pathname.includes("pr-comment") ? "publish_github_pr_comment" : "publish_github_check"
        })
      : null;
  } catch {
    githubTarget = null;
  }
  const trustedRepo = String(githubTarget?.repo || "");
  const targetScope = githubTarget?.tenant_scope || {};
  const targetVerified = githubTarget?.authority === "a1_github_installation"
    && /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(trustedRepo)
    && trustedRepo === String(body.repo || "")
    && A3_SCOPE_FIELDS.every((field) => targetScope[field] === trustedRequestScope[field]);
  if (!targetVerified) {
    return {
      allowed: false,
      dryRun: false,
      liveRequested: true,
      auth_state: authContext.auth_state,
      role: authContext.role,
      tenant_scope: authContext.tenant_scope,
      decision: "denied_untrusted_github_target",
      error: "trusted_github_target_required",
      reason: "Live GitHub publication requires an A1-owned tenant installation and repository allowlist.",
      release_authorization: {
        reason_code: "github_target_not_bound_to_tenant",
        release_ready: true,
        upstream_decision: releaseAuthorization.upstream_decision
      }
    };
  }
  return {
    allowed: true,
    dryRun: false,
    liveRequested: true,
    auth_state: authContext.auth_state,
    role: authContext.role,
    tenant_scope: authContext.tenant_scope,
    repo: trustedRepo,
    releaseAuthorization,
    githubTarget,
    decision: "allowed_by_trusted_a1_a2_authorities",
    release_authorization: releaseAuthorization,
    reason: "Live GitHub publish is authorized by server-verified A1 identity, A2 decision authority, and a tenant-bound GitHub installation."
  };
}

function trustedReleaseAuthorizationResolver(options = {}) {
  if (typeof options.resolveTrustedReleaseAuthorization === "function") return options.resolveTrustedReleaseAuthorization;
  if (typeof options.trustedReleaseAuthorizationResolver === "function") return options.trustedReleaseAuthorizationResolver;
  return null;
}

function trustedDeploymentReceiptVerifierResolver(options = {}) {
  if (typeof options.resolveAuthoritativeDeploymentReceipt === "function") return options.resolveAuthoritativeDeploymentReceipt;
  if (typeof options.deploymentReceiptVerifierResolver === "function") return options.deploymentReceiptVerifierResolver;
  return null;
}

function trustedDeploymentReceiptVerifierGuard(request, body = {}, options = {}) {
  const trustedAccess = request[REQUEST_TRUSTED_ACCESS];
  const authContext = trustedAccess?.authContext || {};
  const unexpectedFields = Object.keys(body || {}).filter((field) => !A3_DEPLOYMENT_VERIFICATION_REQUEST_FIELDS.has(field));
  if (unexpectedFields.length) {
    return {
      allowed: false,
      status: 400,
      body: deploymentReceiptVerifierDenied(
        "client_verification_result_forbidden",
        "Authoritative verification results must come from the configured server resolver."
      )
    };
  }
  const serviceAccount = trustedAccess?.productionEnforced === true
    && authContext.auth_state === "service_account"
    && trustedAccess.accessDecision?.principal?.principal_type === "service_account";
  if (!serviceAccount) {
    return {
      allowed: false,
      status: 403,
      body: deploymentReceiptVerifierDenied(
        "trusted_deployment_verifier_required",
        "This internal operation requires a server-verified A1 service account."
      )
    };
  }
  const resolver = trustedDeploymentReceiptVerifierResolver(options);
  if (!resolver) {
    return {
      allowed: false,
      status: 503,
      body: deploymentReceiptVerifierDenied(
        "authoritative_verifier_unavailable",
        "The authoritative deployment receipt verifier is unavailable."
      )
    };
  }
  return {
    allowed: true,
    resolver,
    resolverIdAlias: authContext.actor_hash
  };
}

function deploymentReceiptVerifierDenied(error, message) {
  return {
    schema_version: "a3.deployment_receipt_verifier_denied.v1",
    error,
    message,
    safety: {
      client_verification_result_used: false,
      raw_request_body_echoed: false,
      raw_resolver_error_exposed: false,
      production_verified: false,
      a2_decision_recomputed: false
    }
  };
}

function trustedGitHubTargetResolver(options = {}) {
  if (typeof options.resolveTrustedGitHubTarget === "function") return options.resolveTrustedGitHubTarget;
  if (typeof options.trustedGitHubTargetResolver === "function") return options.trustedGitHubTargetResolver;
  return null;
}

function liveGitHubPublishDenied(guard = {}) {
  return {
    schema_version: "a3.github_live_publish_denied.v1",
    error: guard.error || "live_publish_requires_hosted_or_service_account",
    decision: guard.decision || "denied_requires_hosted_auth_or_service_account",
    live_requested: guard.liveRequested === true,
    auth_state: guard.auth_state || "unknown",
    role: guard.role || "unknown",
    reason: guard.reason,
    release_authorization: guard.release_authorization || null,
    tenant_scope: guard.tenant_scope,
    denied_state: {
      http_status: 403,
      customer_message: "Live GitHub publishing is unavailable until trusted identity, release authority, executor, and tenant repository checks all pass. Retry as dry-run."
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

async function readJsonBody(request, options = {}) {
  if (!request[REQUEST_BODY_PROMISE]) {
    request[REQUEST_BODY_PROMISE] = (async () => {
      const contentType = firstHeaderValue(request.headers["content-type"])
        .split(";", 1)[0]
        .trim()
        .toLowerCase();
      if (contentType !== "application/json") {
        throw new A3RequestBodyBoundaryError(
          "unsupported_media_type",
          "Request content type must be application/json."
        );
      }

      const maxBytes = positiveIntegerOption(
        options.maxJsonBodyBytes ?? options.requestBodyMaxBytes,
        DEFAULT_A3_MAX_JSON_BODY_BYTES
      );
      const timeoutMs = positiveIntegerOption(
        options.jsonBodyReadTimeoutMs ?? options.requestBodyReadTimeoutMs,
        DEFAULT_A3_BODY_READ_TIMEOUT_MS
      );
      const declaredLength = Number.parseInt(firstHeaderValue(request.headers["content-length"]), 10);
      if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
        throw new A3RequestBodyBoundaryError("payload_too_large", "Request body exceeds the configured limit.");
      }

      const chunks = [];
      let receivedBytes = 0;
      const deadline = Date.now() + timeoutMs;
      const iterator = request[Symbol.asyncIterator]();
      while (true) {
        const remainingMs = deadline - Date.now();
        if (remainingMs <= 0) {
          closeRequestIterator(iterator);
          throw new A3RequestBodyBoundaryError("body_read_timeout", "Request body read timed out.");
        }
        let next;
        try {
          next = await nextRequestChunk(iterator, remainingMs);
        } catch (error) {
          if (error instanceof A3RequestBodyBoundaryError) closeRequestIterator(iterator);
          throw error;
        }
        if (next.done) break;
        const chunk = Buffer.isBuffer(next.value) ? next.value : Buffer.from(next.value);
        receivedBytes += chunk.byteLength;
        if (receivedBytes > maxBytes) {
          closeRequestIterator(iterator);
          throw new A3RequestBodyBoundaryError("payload_too_large", "Request body exceeds the configured limit.");
        }
        chunks.push(chunk);
      }
      const text = Buffer.concat(chunks).toString("utf8").trim();
      if (!text) return {};
      let parsed;
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new A3RequestBodyBoundaryError("malformed_json", "Request body is not valid JSON.");
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new A3RequestBodyBoundaryError("invalid_json_shape", "JSON request body must be an object.");
      }
      return parsed;
    })();
  }
  return request[REQUEST_BODY_PROMISE];
}

function firstHeaderValue(value) {
  return Array.isArray(value) ? String(value[0] || "") : String(value || "");
}

function positiveIntegerOption(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

async function nextRequestChunk(iterator, timeoutMs) {
  let timer;
  try {
    return await Promise.race([
      iterator.next(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(
          new A3RequestBodyBoundaryError("body_read_timeout", "Request body read timed out.")
        ), timeoutMs);
      })
    ]);
  } finally {
    clearTimeout(timer);
  }
}

function closeRequestIterator(iterator) {
  if (typeof iterator.return !== "function") return;
  Promise.resolve(iterator.return()).catch(() => {});
}

function sendJson(response, statusCode, payload) {
  const body = statusCode === 204 ? "" : `${JSON.stringify(payload, null, 2)}\n`;
  response.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff"
  });
  response.end(body);
}

function sendHtml(response, statusCode, body) {
  response.writeHead(statusCode, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff"
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
    .replace(/\bRELEASEFOUNDRY(?:_LABS)?_API_KEY\s*[:=]\s*[^\s"']+/gi, "RELEASEFOUNDRY_API_KEY=[REDACTED]")
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
  const routeAccessMode = resolveA3DirectStartRouteAccessMode(process.env);
  startA3ApiServer({ port: portArg, routeAccessMode }).then(({ url }) => {
    console.log(`A3 API server listening on ${url}`);
    console.log(`A3 route access mode: ${routeAccessMode}`);
  });
}
