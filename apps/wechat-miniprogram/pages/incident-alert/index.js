const surfaceContract = require("../../contracts/a3-client-surface.contract.js");

const incidentAlertPage = surfaceContract.pages.find((page) => page.route === "pages/incident-alert/index");

Page({
  data: {
    pageTitle: incidentAlertPage.title,
    incidentId: "incident-local-risk",
    releaseId: "local-mock-commercial-gate",
    alertState: "needs replay review",
    evidenceFeeds: incidentAlertPage.consumes,
    guardrailSummary: "Incident alerts render redacted evidence aliases, hashes, counts, and statuses only."
  },
  onLoad(query = {}) {
    this.setData({
      incidentId: query.incidentId || this.data.incidentId,
      releaseId: query.releaseId || this.data.releaseId
    });
  }
});
