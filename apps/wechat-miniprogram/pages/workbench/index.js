const { errorMessage, loadWorkbench } = require("../../services/release-center.js");

Page({
  data: {
    viewState: "loading",
    errorText: "",
    snapshot: null,
    meta: {},
    release: {},
    tasks: [],
    modeLabel: "正在连接"
  },

  onShow() {
    this.refresh({ showLoading: !this.data.snapshot });
  },

  onPullDownRefresh() {
    this.refresh({ showLoading: false, stopPullDown: true });
  },

  async refresh({ showLoading = false, stopPullDown = false } = {}) {
    if (showLoading || !this.data.snapshot) {
      this.setData({ viewState: "loading", errorText: "" });
    }
    try {
      const snapshot = await loadWorkbench();
      const tasks = Array.isArray(snapshot.tasks) ? snapshot.tasks : [];
      this.setData({
        viewState: tasks.length ? "ready" : "empty",
        snapshot,
        meta: snapshot.meta || {},
        release: snapshot.release || {},
        tasks,
        modeLabel: snapshot.meta && snapshot.meta.modeLabel ? snapshot.meta.modeLabel : "企业环境",
        errorText: ""
      });
    } catch (error) {
      this.setData({
        viewState: this.data.snapshot ? "partial" : "error",
        errorText: errorMessage(error)
      });
    } finally {
      if (stopPullDown && typeof wx !== "undefined" && typeof wx.stopPullDownRefresh === "function") {
        wx.stopPullDownRefresh();
      }
    }
  },

  openTask(event) {
    const task = event.currentTarget.dataset.task;
    const app = getApp();
    if (!task || !app) return;
    if (task.type === "incident") {
      app.globalData.selectedIncidentId = task.incidentId || "incident-local-risk";
      wx.switchTab({ url: "/pages/incident-alert/index" });
      return;
    }
    app.globalData.selectedReleaseId = task.releaseId || this.data.release.id;
    wx.switchTab({ url: "/pages/release-approval/index" });
  },

  openApproval() {
    const app = getApp();
    if (app) app.globalData.selectedReleaseId = this.data.release.id;
    wx.switchTab({ url: "/pages/release-approval/index" });
  },

  retry() {
    this.refresh({ showLoading: true });
  }
});
