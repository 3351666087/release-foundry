const {
  errorMessage,
  loadRelease,
  requestReviewPreflight
} = require("../../services/release-center.js");

Page({
  data: {
    viewState: "loading",
    releaseId: "local-mock-commercial-gate",
    release: {},
    meta: {},
    evidenceStages: [],
    blockers: [],
    errorText: "",
    actionPending: false,
    modeLabel: "正在连接"
  },

  onLoad(query = {}) {
    if (query.releaseId) this.setData({ releaseId: query.releaseId });
  },

  onShow() {
    const app = getApp();
    const selectedReleaseId = app && app.globalData.selectedReleaseId;
    if (selectedReleaseId && selectedReleaseId !== this.data.releaseId) {
      this.setData({ releaseId: selectedReleaseId });
    }
    this.refresh({ showLoading: !this.data.release.id });
  },

  onPullDownRefresh() {
    this.refresh({ showLoading: false, stopPullDown: true });
  },

  async refresh({ showLoading = false, stopPullDown = false } = {}) {
    if (showLoading || !this.data.release.id) {
      this.setData({ viewState: "loading", errorText: "" });
    }
    try {
      const snapshot = await loadRelease(this.data.releaseId);
      const release = snapshot.release || {};
      this.setData({
        viewState: snapshot.partial ? "partial" : "ready",
        release,
        releaseId: release.id || this.data.releaseId,
        meta: snapshot.meta || {},
        evidenceStages: Array.isArray(release.evidenceStages) ? release.evidenceStages : [],
        blockers: Array.isArray(release.blockers) ? release.blockers : [],
        modeLabel: snapshot.meta && snapshot.meta.modeLabel ? snapshot.meta.modeLabel : "企业环境",
        errorText: snapshot.partial ? "部分发布证据暂时无法读取，当前结果按缺失处理。" : ""
      });
    } catch (error) {
      this.setData({
        viewState: this.data.release.id ? "partial" : "error",
        errorText: errorMessage(error)
      });
    } finally {
      if (stopPullDown && typeof wx !== "undefined" && typeof wx.stopPullDownRefresh === "function") {
        wx.stopPullDownRefresh();
      }
    }
  },

  async checkReviewPermission(event) {
    if (this.data.actionPending) return;
    const action = event.currentTarget.dataset.action === "reject" ? "reject" : "approve";
    const actionLabel = action === "approve" ? "批准" : "拒绝";
    this.setData({ actionPending: true });
    try {
      const result = await requestReviewPreflight(action, this.data.release);
      if (result.status === "preview_only") {
        wx.showModal({
          title: "当前为演示模式",
          content: `这里仅展示${actionLabel}流程，不会写入真实发布记录。连接企业身份和服务端授权后才可执行。`,
          showCancel: false,
          confirmText: "知道了"
        });
        return;
      }
      wx.showModal({
        title: result.allowed ? "权限预检通过" : "权限预检未通过",
        content: result.allowed
          ? `当前身份具备${actionLabel}资格。本版本只完成权限预检，尚未提交审批结果。`
          : (result.reason || "当前身份或发布状态不满足操作条件。"),
        showCancel: false,
        confirmText: "知道了"
      });
    } catch (error) {
      wx.showModal({
        title: "无法完成权限预检",
        content: errorMessage(error),
        showCancel: false,
        confirmText: "关闭"
      });
    } finally {
      this.setData({ actionPending: false });
    }
  },

  retry() {
    this.refresh({ showLoading: true });
  }
});
