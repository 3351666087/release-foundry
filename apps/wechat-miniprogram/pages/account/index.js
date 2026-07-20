const {
  checkConnection,
  errorMessage,
  loadWorkbench
} = require("../../services/release-center.js");

Page({
  data: {
    viewState: "loading",
    meta: {},
    account: {},
    connection: {},
    securityItems: [],
    errorText: "",
    checking: false,
    capabilities: [
      { id: "identity", label: "企业身份会话", value: "待服务端接入", tone: "warning", detail: "需要企业身份后端签发会话，小程序不保存 Token。" },
      { id: "wechat-login", label: "微信登录", value: "尚未启用", tone: "neutral", detail: "仍使用游客调试 AppID，取得主体资质与正式 AppID 后才能接入。" },
      { id: "review-write", label: "审批写入", value: "仅权限预检", tone: "warning", detail: "当前不会提交批准、拒绝或豁免结果。" },
      { id: "message", label: "订阅消息", value: "尚未接入", tone: "neutral", detail: "不会宣称已发送真实微信通知。" }
    ]
  },

  onShow() {
    this.refresh({ showLoading: !this.data.connection.status });
  },

  onPullDownRefresh() {
    this.refresh({ showLoading: false, stopPullDown: true });
  },

  async refresh({ showLoading = false, stopPullDown = false } = {}) {
    if (showLoading || !this.data.connection.status) {
      this.setData({ viewState: "loading", errorText: "" });
    }
    const [snapshotResult, connectionResult] = await Promise.allSettled([
      loadWorkbench(),
      checkConnection()
    ]);
    try {
      const snapshot = snapshotResult.status === "fulfilled" ? snapshotResult.value : null;
      const connection = connectionResult.status === "fulfilled" ? connectionResult.value : null;
      if (!snapshot && !connection) throw snapshotResult.reason || connectionResult.reason;
      const account = snapshot && snapshot.account ? snapshot.account : this.data.account;
      const securityItems = account && Array.isArray(account.securityItems) ? account.securityItems : this.data.securityItems;
      this.setData({
        viewState: snapshot && connection ? "ready" : "partial",
        meta: snapshot && snapshot.meta ? snapshot.meta : this.data.meta,
        account: account || {},
        securityItems,
        connection: connection || {
          status: "unknown",
          statusLabel: "状态未知",
          detail: "连接诊断暂时不可用。"
        },
        errorText: snapshot && connection ? "" : "部分账户诊断未能完成，未确认的能力保持关闭。"
      });
    } catch (error) {
      this.setData({ viewState: "error", errorText: errorMessage(error) });
    } finally {
      if (stopPullDown && typeof wx !== "undefined" && typeof wx.stopPullDownRefresh === "function") {
        wx.stopPullDownRefresh();
      }
    }
  },

  async checkAgain() {
    if (this.data.checking) return;
    this.setData({ checking: true });
    try {
      const connection = await checkConnection();
      this.setData({ connection, viewState: "ready", errorText: "" });
      wx.showToast({
        title: connection.status === "connected" ? "服务可达" : "诊断已更新",
        icon: connection.status === "connected" ? "success" : "none"
      });
    } catch (error) {
      this.setData({
        connection: { status: "error", statusLabel: "连接失败", detail: errorMessage(error) },
        viewState: "partial"
      });
    } finally {
      this.setData({ checking: false });
    }
  },

  retry() {
    this.refresh({ showLoading: true });
  }
});
