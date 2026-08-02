import assert from "node:assert/strict";
import { test } from "node:test";

import { buildReportCenterIndex } from "../../services/report/a3_report_center.mjs";
import { buildSaasAdminActionRequest, planSaasAdminAction } from "../../services/report/a3_saas_admin.mjs";
import {
  assertA3SecurityGuardPassed,
  guardA3SecuritySurface,
  scanA3SecurityLeaks
} from "../../services/report/a3_security_redaction_guard.mjs";

const TENANT_SCOPE = {
  organization_id: "org-sec",
  project_id: "project-sec"
};

const PRIVILEGED_ACTORS = {
  admin_action: { role: "admin", ...TENANT_SCOPE },
  review_workflow: { role: "reviewer", ...TENANT_SCOPE },
  report_center: { role: "auditor", ...TENANT_SCOPE }
};

const LEAK_REGEX = /Authorization:\s*Bearer|Bearer\s+(?!\[REDACTED\])|plainApiKey|owner@example\.com|reviewer@example\.com|approver@example\.com|X-Amz-Signature|sig=raw|signed-media-token|sk_live/i;

test("A3 security redaction guard scrubs admin, review, and report payloads before export", () => {
  const cases = [
    ["admin_action", dirtyAdminActionPayload()],
    ["review_workflow", dirtyReviewWorkflowPayload()],
    ["report_center", dirtyReportCenterPayload()]
  ];

  for (const [surface, payload] of cases) {
    const guarded = guardA3SecuritySurface(payload, {
      surface,
      tenantScope: TENANT_SCOPE,
      actor: PRIVILEGED_ACTORS[surface],
      requireActorTenant: true
    });
    const serialized = JSON.stringify(guarded);

    assert.equal(guarded.allowed, true, `${surface} should pass after redaction`);
    assert.equal(guarded.redaction.residual_finding_count, 0, `${surface} should have no residual findings`);
    assert.ok(guarded.redaction.replacement_count >= 3, `${surface} should redact several sensitive fields`);
    assert.equal(scanA3SecurityLeaks(guarded.value, { surface }).length, 0);
    assert.doesNotMatch(serialized, LEAK_REGEX, `${surface} leaked raw sensitive material`);
    assert.match(serialized, /\[REDACTED(?:_[A-Z]+)?\]/, `${surface} should retain redaction markers`);
  }
});

test("A3 security redaction guard fails closed on RBAC and tenant mismatches", () => {
  const guarded = guardA3SecuritySurface({ report_id: "a3r_safe", title: "Safe report" }, {
    surface: "report_center",
    tenantScope: TENANT_SCOPE,
    actor: {
      role: "developer",
      organization_id: "org-other",
      project_id: "project-sec"
    },
    requireActorTenant: true
  });

  assert.equal(guarded.allowed, false);
  assert.equal(guarded.status, "blocked");
  assert.ok(guarded.tenant.reasons.includes("organization_mismatch"));
  assert.ok(guarded.rbac.reasons.includes("missing_required_role"));
  assert.throws(
    () => assertA3SecurityGuardPassed(guarded.value, {
      surface: "report_center",
      tenantScope: TENANT_SCOPE,
      actor: {
        role: "developer",
        organization_id: "org-other",
        project_id: "project-sec"
      },
      requireActorTenant: true
    }),
    /organization_mismatch.*missing_required_role/
  );
});

function dirtyAdminActionPayload() {
  const plan = planSaasAdminAction("invite_teammate", {
    organizationId: TENANT_SCOPE.organization_id,
    projectId: TENANT_SCOPE.project_id
  });
  return {
    ...buildSaasAdminActionRequest("invite_teammate", {
      plan,
      requestId: "aar_security_guard",
      actorHash: "actor_hash_only",
      requestedAt: "2026-07-09T00:00:00.000Z"
    }),
    headers: {
      Authorization: "Bearer admin-action-token-1234567890"
    },
    target: {
      email: "owner@example.com",
      api_key: "plainApiKey-admin-action-1234567890",
      signed_url: "https://media.example.test/admin.png?X-Amz-Signature=raw-admin-signature&Expires=9999999999"
    },
    "owner@example.com": {
      note: "object keys are part of the export surface too"
    }
  };
}

function dirtyReviewWorkflowPayload() {
  return {
    schema_version: "a3.review_workflow_record.v1",
    record_id: "rwr_security_guard",
    record_type: "approval",
    organization_id: TENANT_SCOPE.organization_id,
    project_id: TENANT_SCOPE.project_id,
    payload: {
      approved_by: [
        {
          role: "reviewer",
          email: "reviewer@example.com"
        }
      ],
      authorization: "Bearer review-workflow-token-1234567890",
      signer: {
        email_address: "approver@example.com",
        api_key: "synthetic-review-workflow-credential"
      }
    },
    evidence: {
      media_signed_url: "https://media.example.test/review.png?sig=raw-review-signature&token=signed-media-token"
    }
  };
}

function dirtyReportCenterPayload() {
  return buildReportCenterIndex([
    {
      report_id: "a3r_security_guard",
      title: "owner@example.com Authorization: Bearer report-center-token-1234567890",
      source: "mock",
      status: "shareable",
      share_url_path: "/reports/a3r_security_guard",
      internal_url_path: "https://media.example.test/report.html?X-Amz-Signature=raw-report-signature&Expires=9999999999",
      created_at: "2026-07-09T00:00:00.000Z",
      expires_at: "2026-07-10T00:00:00.000Z",
      lifecycle: { revocable: true, view_audit_enabled: true },
      view_audit: {
        view_count: 1,
        last_viewer_email: "owner@example.com"
      },
      redaction: { status: "passed", blocked: false, residual_finding_count: 0 },
      sealed_evidence: {
        payload_hash: "abc123",
        hash_algorithm: "sha256",
        secret_free: true
      },
      artifacts: [
        { id: "json_report", sha256: "jsonhash" }
      ]
    }
  ], {
    source: "mock",
    organizationId: TENANT_SCOPE.organization_id,
    projectId: TENANT_SCOPE.project_id,
    now: "2026-07-09T01:00:00.000Z"
  });
}
