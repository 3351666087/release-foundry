const surfaceContract = require("./contracts/a3-client-surface.contract.js");
const { normalizeApiBaseUrl } = require("./utils/api-client.js");

function readExtConfig() {
  try {
    return typeof wx !== "undefined" && typeof wx.getExtConfigSync === "function"
      ? wx.getExtConfigSync() || {}
      : {};
  } catch {
    return {};
  }
}

App({
  onLaunch() {
    const extConfig = readExtConfig();
    const apiBaseUrl = normalizeApiBaseUrl(extConfig.apiBaseUrl);
    this.globalData.apiBaseUrl = apiBaseUrl;
    this.globalData.dataMode = apiBaseUrl ? "connected" : "preview";
    this.globalData.connectionLabel = apiBaseUrl ? "企业环境" : "演示数据";
    this.globalData.selectedReleaseId = apiBaseUrl ? "current" : "local-mock-commercial-gate";
  },
  globalData: {
    surfaceContract,
    apiBaseUrl: "",
    dataMode: "preview",
    connectionLabel: "演示数据",
    selectedReleaseId: "local-mock-commercial-gate",
    selectedIncidentId: "incident-local-risk",
    tokenPersistence: "disabled",
    customerFacingLaneLabels: false
  }
});
