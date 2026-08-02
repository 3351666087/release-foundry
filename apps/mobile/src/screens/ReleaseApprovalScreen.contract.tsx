import { a3MobileClientSurfaceContract, type A3MobileReleaseCard } from "../release-intelligence-contract";

export type ReleaseApprovalScreenContract = {
  title: "Release Approval";
  reads: typeof a3MobileClientSurfaceContract.allowed_api_surfaces;
  card: A3MobileReleaseCard;
  mutationPolicy: "approval_requires_hosted_auth_rbac_and_audit";
};

export const releaseApprovalScreenContract: ReleaseApprovalScreenContract = {
  title: "Release Approval",
  reads: a3MobileClientSurfaceContract.allowed_api_surfaces,
  mutationPolicy: "approval_requires_hosted_auth_rbac_and_audit",
  card: {
    releaseId: "release_[REDACTED]",
    status: "review_required",
    evidenceSummaryId: "summary_[REDACTED]",
    hostedReportPath: "/r/[REDACTED_TOKEN]",
    a1Evidence: {
      runResultReady: true,
      traceReady: true,
      toolCallCount: 0
    },
    a2Evidence: {
      gradeResultReady: true,
      passFailReady: true,
      failureTaxonomyReady: true
    },
    a3Evidence: {
      releaseEvidenceReady: true,
      reviewerWorkflowReady: true,
      auditExportReady: true
    }
  }
};
