const surfaceContract = require("../../contracts/a3-client-surface.contract.js");

const releaseApprovalPage = surfaceContract.pages.find((page) => page.route === "pages/release-approval/index");

Page({
  data: {
    pageTitle: releaseApprovalPage.title,
    releaseId: "local-mock-commercial-gate",
    tenantState: "tenant scoped",
    approvalState: "review required",
    evidenceFeeds: releaseApprovalPage.consumes,
    guardrailSummary: "No token, cookie, raw key, Authorization header, or raw signed URL persistence."
  },
  onLoad(query = {}) {
    this.setData({
      releaseId: query.releaseId || this.data.releaseId
    });
  }
});
