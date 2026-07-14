const snapshot = {
  schema_version: "release_center.preview.v1",
  meta: {
    mode: "preview",
    modeLabel: "演示数据",
    connectionLabel: "未连接企业环境",
    organization: "示例企业",
    project: "智能客服助手",
    environment: "预发布"
  },
  release: {
    id: "local-mock-commercial-gate",
    version: "0.2.0-rc.2",
    title: "智能客服助手 · 候选版本",
    status: "blocked",
    statusLabel: "发布受阻",
    tone: "danger",
    decisionLabel: "暂不可发布",
    summary: "案例质量已通过，但发布凭证与目标环境回执尚未闭合。",
    updatedLabel: "刚刚校准",
    progressLabel: "7 / 11",
    acceptanceLabel: "8 / 17",
    passRateLabel: "3 / 3",
    traceLabel: "100%",
    multimodalReadiness: {
      available: true,
      status: "blocked_multimodal_release_readiness",
      statusLabel: "多模态晋级受阻",
      tone: "danger",
      safeControlLabel: "0 / 10",
      attackDetectionLabel: "3 / 5",
      sensitivityLabel: "60%",
      localProfileLabel: "0",
      localModelLabel: "qwen3-vl:8b",
      qualityLabel: "blocked",
      stabilityLabel: "qualified",
      reviewLabel: "pending",
      sourceCommitAlias: "850b39a"
    },
    nextAction: "补齐同一候选版本的评测账本、仓库门禁和部署回执。",
    tenantScope: {
      organization_id: "org-local",
      tenant_id: "tenant-local",
      workspace_id: "workspace-local",
      project_id: "project-local",
      environment_id: "staging"
    },
    evidenceStages: [
      { id: "execution", index: "01", title: "执行证据", status: "complete", statusLabel: "完整", tone: "success", detail: "3/3 案例完成，Trace 完整率 100%。" },
      { id: "evaluation", index: "02", title: "评测结论", status: "complete", statusLabel: "已生成", tone: "success", detail: "案例评分完成，质量检查通过。" },
      { id: "release", index: "03", title: "发布凭证", status: "blocked", statusLabel: "未闭合", tone: "danger", detail: "当前凭证不属于同一候选版本，保持阻断。" }
    ],
    blockers: [
      { id: "candidate_integrity", title: "候选版本证据不一致", owner: "发布负责人", detail: "执行记录、评测账本与发布制品需要绑定同一版本。" },
      { id: "repository_gate", title: "主分支门禁未强制", owner: "代码仓库管理员", detail: "尚未证明失败候选无法合并到主分支。" },
      { id: "deployment_receipt", title: "目标环境回执缺失", owner: "平台运维", detail: "缺少部署身份、镜像、迁移、健康和租户隔离回读。" }
    ],
    review: {
      canApprove: false,
      canReject: true,
      approvalLabel: "检查批准权限",
      rejectionLabel: "检查拒绝权限",
      reason: "发布决策仍为阻断状态。"
    }
  },
  tasks: [
    { id: "release-review", type: "release", releaseId: "local-mock-commercial-gate", title: "候选版本等待复核", meta: "0.2.0-rc.2 · 预发布", badge: "受阻", tone: "danger" },
    { id: "incident-review", type: "incident", incidentId: "incident-local-risk", title: "退款状态链路不一致", meta: "高风险 · 需要回放", badge: "待处理", tone: "warning" }
  ],
  incidents: [
    {
      id: "incident-local-risk",
      releaseId: "local-mock-commercial-gate",
      title: "退款状态链路不一致",
      severity: "high",
      severityLabel: "高风险",
      tone: "danger",
      state: "open",
      stateLabel: "待处理",
      summary: "页面显示退款完成，但后端确认动作晚于页面状态变化。",
      caseLabel: "退款案例 03",
      evidenceLabel: "Trace、工具调用和评测证据齐全",
      updatedLabel: "12 分钟前",
      timeline: [
        { time: "14:22:10", title: "页面状态变更", detail: "前端缓存将状态更新为“退款完成”。" },
        { time: "14:23:05", title: "退款动作执行", detail: "确认工具返回成功并记录退款引用。" },
        { time: "14:24:18", title: "风险规则命中", detail: "状态顺序不一致，自动进入回放队列。" }
      ],
      actions: ["核对数据库退款记录", "核对支付渠道结算状态", "修复乐观状态更新"]
    },
    {
      id: "incident-tool-coverage",
      releaseId: "local-mock-commercial-gate",
      title: "关键工具证据完整性复核",
      severity: "medium",
      severityLabel: "中风险",
      tone: "warning",
      state: "reviewing",
      stateLabel: "复核中",
      summary: "候选版本工具调用已补齐，仍需确认发布账本绑定。",
      caseLabel: "发布凭证",
      evidenceLabel: "工具证据完整，版本绑定待确认",
      updatedLabel: "34 分钟前",
      timeline: [],
      actions: ["确认候选版本标识", "重新生成发布凭证"]
    }
  ],
  account: {
    identityStatus: "not_configured",
    identityLabel: "企业身份未连接",
    appIdLabel: "游客调试 AppID",
    apiLabel: "未配置 HTTPS API",
    roleLabel: "只读演示",
    tenantLabel: "示例企业 / 智能客服助手 / 预发布",
    securityItems: [
      { label: "本地 Token 存储", value: "已禁用", tone: "success" },
      { label: "敏感字段渲染", value: "默认拒绝", tone: "success" },
      { label: "审批写入", value: "需要服务端授权", tone: "warning" }
    ]
  }
};

function buildPreviewSnapshot() {
  return JSON.parse(JSON.stringify(snapshot));
}

module.exports = { buildPreviewSnapshot };
