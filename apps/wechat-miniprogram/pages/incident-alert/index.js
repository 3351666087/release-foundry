const { errorMessage, loadIncidents } = require("../../services/release-center.js");

Page({
  data: {
    viewState: "loading",
    incidents: [],
    filteredIncidents: [],
    selectedIncident: {},
    selectedIncidentId: "incident-local-risk",
    selectedFilter: "all",
    filterOptions: [
      { id: "all", label: "全部" },
      { id: "open", label: "待处理" },
      { id: "reviewing", label: "复核中" }
    ],
    meta: {},
    modeLabel: "正在连接",
    errorText: ""
  },

  onLoad(query = {}) {
    if (query.incidentId) this.setData({ selectedIncidentId: query.incidentId });
  },

  onShow() {
    const app = getApp();
    const selectedIncidentId = app && app.globalData.selectedIncidentId;
    if (selectedIncidentId) this.setData({ selectedIncidentId });
    this.refresh({ showLoading: !this.data.incidents.length });
  },

  onPullDownRefresh() {
    this.refresh({ showLoading: false, stopPullDown: true });
  },

  async refresh({ showLoading = false, stopPullDown = false } = {}) {
    if (showLoading || !this.data.incidents.length) {
      this.setData({ viewState: "loading", errorText: "" });
    }
    try {
      const snapshot = await loadIncidents();
      const incidents = Array.isArray(snapshot.incidents) ? snapshot.incidents : [];
      this.setData({
        incidents,
        meta: snapshot.meta || {},
        modeLabel: snapshot.meta && snapshot.meta.modeLabel ? snapshot.meta.modeLabel : "企业环境",
        errorText: ""
      });
      this.applyFilter(this.data.selectedFilter, incidents, this.data.selectedIncidentId);
    } catch (error) {
      this.setData({
        viewState: this.data.incidents.length ? "partial" : "error",
        errorText: errorMessage(error)
      });
    } finally {
      if (stopPullDown && typeof wx !== "undefined" && typeof wx.stopPullDownRefresh === "function") {
        wx.stopPullDownRefresh();
      }
    }
  },

  changeFilter(event) {
    this.applyFilter(event.currentTarget.dataset.filter, this.data.incidents, "");
  },

  applyFilter(filter, incidents, preferredId) {
    const selectedFilter = ["all", "open", "reviewing"].includes(filter) ? filter : "all";
    const filteredIncidents = selectedFilter === "all"
      ? incidents
      : incidents.filter((incident) => incident.state === selectedFilter);
    const selectedIncident = filteredIncidents.find((incident) => incident.id === preferredId)
      || filteredIncidents[0]
      || {};
    this.setData({
      selectedFilter,
      filteredIncidents,
      selectedIncident,
      selectedIncidentId: selectedIncident.id || "",
      viewState: filteredIncidents.length ? "ready" : "empty"
    });
  },

  selectIncident(event) {
    const selectedIncidentId = event.currentTarget.dataset.id;
    const selectedIncident = this.data.filteredIncidents.find((incident) => incident.id === selectedIncidentId) || {};
    this.setData({ selectedIncidentId, selectedIncident });
    const app = getApp();
    if (app) app.globalData.selectedIncidentId = selectedIncidentId;
  },

  openRelatedRelease() {
    const app = getApp();
    if (app) app.globalData.selectedReleaseId = this.data.selectedIncident.releaseId;
    wx.switchTab({ url: "/pages/release-approval/index" });
  },

  retry() {
    this.refresh({ showLoading: true });
  }
});
