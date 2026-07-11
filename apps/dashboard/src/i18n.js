(() => {
  const STORAGE_KEY = "a3.dashboard.language";
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  const translations = new Map([
    ["A3 Dashboard & Triage", "A3 仪表盘与问题分诊"],
    ["A3 Signal/Form Dashboard", "A3 Signal/Form 仪表盘"],
    ["Release intelligence", "发布智能"],
    ["Product console / review workflow / report center", "产品控制台 / 审核流程 / 报告中心"],
    ["LANE CONTRACT / 006", "责任边界 / 006"],
    ["A1 captures. A2 decides. A3 operates.", "A1 采集，A2 判定，A3 运营。"],
    ["Upstream evidence remains read-only and source-owned.", "上游证据保持只读，并由来源模块负责。"],
    ["AGENT RELEASE OS / A3", "智能体发布系统 / A3"],
    ["Release", "发布"],
    ["Intelligence", "智能"],
    ["Read only", "只读"],
    ["Redacted", "已脱敏"],
    ["No cloud mutations", "不修改云端"],
    ["Evidence source", "证据来源"],
    ["A1/A2 Mock", "A1/A2 模拟数据"],
    ["API-backed Mock", "API 支持的模拟数据"],
    ["Raw A1 RunResult", "原始 A1 运行结果"],
    ["Raw A2 Single Case", "原始 A2 单案例"],
    ["P3 Media Sample", "P3 媒体样本"],
    ["P3 Official Demo 884/11926", "P3 官方演示 884/11926"],
    ["Print", "打印"],
    ["Runs", "运行"],
    ["Cases", "案例"],
    ["Pass Rate", "通过率"],
    ["Average Score", "平均分"],
    ["Trace Complete", "Trace 完整率"],
    ["Media Evidence", "媒体证据"],
    ["execution batches", "执行批次"],
    ["normalized test cases", "标准化测试案例"],
    ["current source", "当前数据源"],
    ["0-100 normalized", "0-100 标准分"],
    ["A1 evidence coverage", "A1 证据覆盖率"],
    ["case-level attachments", "案例级附件"],
    ["Operations fabric", "运营工作台"],
    ["runtime / administration / calibration", "运行时 / 管理 / 校准"],
    ["Workflow", "工作流"],
    ["Request to report", "从请求到报告"],
    ["Requests", "请求"],
    ["Datasets", "数据集"],
    ["Analysis", "分析"],
    ["Export", "导出"],
    ["calibrated", "已校准"],
    ["loaded", "已加载"],
    ["ready", "就绪"],
    ["checking", "检查中"],
    ["unknown", "未知"],
    ["waiting", "等待中"],
    ["watching", "监测中"],
    ["not attached", "未接入"],
    ["metadata only", "仅元数据"],
    ["not shared", "未分享"],
    ["read-only", "只读"],
    ["API + DB-ready", "API + 数据库就绪"],
    ["SaaS Runtime", "SaaS 运行时"],
    ["Billing Migration Readiness", "计费迁移准备度"],
    ["Live Workflow Readiness", "实时工作流准备度"],
    ["Live Ops Control Plane", "实时运营控制面"],
    ["Notification Control Plane", "通知控制面"],
    ["Product Console", "产品控制台"],
    ["onboarding / audit", "引导 / 审计"],
    ["SaaS Admin Console", "SaaS 管理控制台"],
    ["clean-room shell", "洁净室界面"],
    ["Enterprise Readiness", "企业级准备度"],
    ["self-host / audit", "私有部署 / 审计"],
    ["A1/A2 Contract Radar", "A1/A2 契约雷达"],
    ["Peer Branch Calibration", "协作分支校准"],
    ["Usage / Quota", "用量 / 配额"],
    ["Objects", "对象"],
    ["Requests / datasets / runs", "请求 / 数据集 / 运行"],
    ["Cloud Console Shell", "云端控制台"],
    ["mock controls", "模拟控制"],
    ["Official Ashr Gap", "官方 Ashr 差距"],
    ["read-only map", "只读映射"],
    ["Official Frontend Mirror", "官方前端映射"],
    ["Official Code Crawl", "官方代码分析"],
    ["Official Parity Roadmap", "官方对齐路线图"],
    ["build order", "构建顺序"],
    ["Request Provenance", "请求来源"],
    ["Release control", "发布控制"],
    ["gate / replay / review / audit", "门禁 / 回放 / 审核 / 审计"],
    ["Release Gate", "发布门禁"],
    ["Release War Room", "发布作战室"],
    ["Incident Replay", "故障回放"],
    ["Observability Replay", "可观测性回放"],
    ["Regression Factory", "回归工厂"],
    ["Reviewer Workflow", "审核人工作流"],
    ["PR Gate & Audit", "PR 门禁与审计"],
    ["Release Evidence", "发布证据"],
    ["Coverage Health", "覆盖健康度"],
    ["Triage Queue", "问题分诊队列"],
    ["Highest-risk failures first", "优先显示最高风险失败"],
    ["Report Center", "报告中心"],
    ["Markdown", "Markdown"],
    ["Print/PDF", "打印/PDF"],
    ["Share Hosted Report", "分享托管报告"],
    ["API-backed mode can create a redacted hosted report payload.", "API 模式可创建已脱敏的托管报告。"],
    ["Export Safety", "导出安全"],
    ["Report output", "报告输出"],
    ["evidence / export / handoff", "证据 / 导出 / 交接"],
    ["Report Preview", "报告预览"],
    ["Print-ready handoff", "可打印交付"],
    ["Case inspection", "案例检查"],
    ["expected / actual / trace / failure", "预期 / 实际 / Trace / 失败"],
    ["Status", "状态"],
    ["All", "全部"],
    ["Passed", "通过"],
    ["Failed", "失败"],
    ["Scenario Family", "场景类别"],
    ["Failure Class", "失败分类"],
    ["Run", "运行"],
    ["Severity", "严重程度"],
    ["Score Band", "分数区间"],
    ["Judge Mode", "判定模式"],
    ["Run List", "运行列表"],
    ["Case Detail", "案例详情"],
    ["No case", "未选择案例"],
    ["Select a case to inspect expected vs actual.", "请选择案例查看预期与实际结果。"],
    ["Expected", "预期"],
    ["Actual", "实际"],
    ["Trace Timeline", "Trace 时间线"],
    ["A1 observations and trace events", "A1 观察记录与 Trace 事件"],
    ["Failure Clusters", "失败聚类"],
    ["Grouped by A2 primary failure class", "按 A2 主要失败分类分组"],
    ["Overview", "总览"],
    ["health", "健康度"],
    ["Source & exports", "数据源与导出"],
    ["Product surfaces", "产品模块"],
    ["Workspace shortcuts", "工作区快捷入口"],
    ["Run metrics", "运行指标"],
    ["A1/A2 evidence spine", "A1/A2 证据链"],
    ["Evaluate", "评测"],
    ["runs", "运行"],
    ["Console", "控制台"],
    ["Product console", "产品控制台"],
    ["Media readiness", "媒体准备度"],
    ["Official gap", "官方差距"],
    ["Frontend mirror", "前端映射"],
    ["Code crawl parity", "代码分析对齐"],
    ["Parity roadmap", "对齐路线图"],
    ["Review", "审核"],
    ["cases", "案例"],
    ["Run list", "运行列表"],
    ["Case detail", "案例详情"],
    ["Trace timeline", "Trace 时间线"],
    ["Failure clusters", "失败聚类"],
    ["Reviewer workflow", "审核人工作流"],
    ["Reports", "报告"],
    ["export", "导出"],
    ["Report preview", "报告预览"],
    ["Report center", "报告中心"],
    ["Export safety", "导出安全"],
    ["Release evidence", "发布证据"],
    ["Admin", "管理"],
    ["access", "访问"],
    ["Login / team", "登录 / 团队"],
    ["Live workflow", "实时工作流"],
    ["Live ops", "实时运营"],
    ["Notifications", "通知"],
    ["API keys", "API 密钥"],
    ["Usage / quota", "用量 / 配额"],
    ["Billing migration", "计费迁移"],
    ["Trust", "信任与合规"],
    ["audit", "审计"],
    ["Enterprise posture", "企业级状态"],
    ["Contract radar", "契约雷达"],
    ["Peer Branches", "协作分支"],
    ["Release gate", "发布门禁"],
    ["PR gate", "PR 门禁"],
    ["War room", "作战室"],
    ["Incident replay", "故障回放"],
    ["Observability replay", "可观测性回放"],
    ["Regression factory", "回归工厂"],
    ["Workspace", "工作区"],
    ["source and release health", "数据源与发布健康度"],
    ["Evaluation", "评测"],
    ["runs, cases and traces", "运行、案例与 Trace"],
    ["human release decisions", "人工发布决策"],
    ["evidence and export lifecycle", "证据与导出生命周期"],
    ["Administration", "系统管理"],
    ["identity, team and billing", "身份、团队与计费"],
    ["contracts, audit and policy", "契约、审计与策略"],
    ["Live", "实时"],
    ["Control", "控制"],
    ["Evidence", "证据"],
    ["Billing", "计费"],
    ["Enterprise", "企业级"],
    ["Media", "媒体"],
    ["Contracts", "契约"],
    ["Official parity", "官方对齐"],
    ["Evidence spine", "证据链"],
    ["Waiting for A1 and A2 evidence contracts.", "正在等待 A1 与 A2 证据契约。"],
    ["A1 identity", "A1 身份证据"],
    ["A2 multimodal", "A2 多模态证据"],
    ["not observed", "未观测到"],
    ["no current peer signal", "当前没有协作信号"],
    ["A1 captures execution. A2 owns evaluation and release policy. A3 presents the evidence and workflow without changing either upstream meaning.", "A1 采集执行过程，A2 负责评测与发布策略，A3 在不改变上游语义的前提下展示证据和工作流。"],
    ["Capture", "采集"],
    ["Gate", "门禁"],
    ["Operate", "运营"],
    ["draft watch / not main authority", "草稿观察 / 非主分支权威"],
    ["RBAC Matrix", "RBAC 权限矩阵"],
    ["Invite Workflow", "邀请流程"],
    ["Seat / License Posture", "席位 / 许可状态"],
    ["API Key Lifecycle", "API 密钥生命周期"],
    ["API Key Audit", "API 密钥审计"],
    ["Control Summary", "控制摘要"],
    ["Tenant / Environment Control", "租户 / 环境控制"],
    ["Release / Rollout Control", "发布 / 灰度控制"],
    ["Notification Destinations", "通知目标"],
    ["Billing Account", "计费账户"],
    ["Trust Center", "信任中心"],
    ["Compliance Posture", "合规状态"],
    ["Cloud Management", "云端管理"],
    ["Workspace / Cloud Posture", "工作区 / 云端状态"],
    ["Audit Log", "审计日志"],
    ["Reviewer timeline", "审核人时间线"],
    ["GitHub publish step", "GitHub 发布步骤"],
    ["Share-link lifecycle", "分享链接生命周期"],
    ["Audit history", "审计历史"],
    ["Release publish chain", "发布链路"],
    ["Publish blockers", "发布阻塞项"],
    ["Commercial sign-off", "商业签核"],
    ["Sign-off blockers", "签核阻塞项"],
    ["Language", "语言"],
    ["Primary product areas", "主要产品区域"],
    ["Product surfaces", "产品模块"],
    ["A3 workspace shortcuts", "A3 工作区快捷入口"],
    ["Run summary metrics", "运行摘要指标"],
    ["A1 and A2 evidence spine", "A1 与 A2 证据链"],
    ["Operational triage", "运营问题分诊"],
    ["PDF-ready report preview", "PDF 报告预览"],
    ["Filters", "筛选器"]
  ]);

  const patterns = [
    [/^(\d+) visible$/, "$1 条可见"],
    [/^API-backed A1\/A2 mock fixture:\s*(.+); Coverage:\s*(.+)$/, "API 支持的 A1/A2 模拟数据：$1；覆盖数据：$2"],
    [/^Loading local fixtures\.\.\.$/, "正在加载本地数据..."],
    [/^Waiting for A1 run evidence and A2 evaluation authority\.$/, "正在等待 A1 运行证据和 A2 评测判定。"]
  ];

  let language = initialLanguage();
  let observer;

  function initialLanguage() {
    const requested = new URLSearchParams(window.location.search).get("lang");
    if (requested === "en") return "en";
    if (requested === "zh" || requested === "zh-CN") return "zh-CN";
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "zh-CN";
    } catch {
      return "zh-CN";
    }
  }

  function translatedValue(value) {
    const direct = translations.get(value);
    if (direct) return direct;
    for (const [pattern, replacement] of patterns) {
      if (pattern.test(value)) return value.replace(pattern, replacement);
    }
    return value;
  }

  function translateTextNode(node) {
    if (!node.parentElement || node.parentElement.closest("script, style, pre, code, [data-i18n-ignore]")) return;
    if (!originalText.has(node)) originalText.set(node, node.nodeValue || "");
    const original = originalText.get(node) || "";
    if (language === "en") {
      node.nodeValue = original;
      return;
    }
    const leading = original.match(/^\s*/)?.[0] || "";
    const trailing = original.match(/\s*$/)?.[0] || "";
    const core = original.slice(leading.length, original.length - trailing.length);
    node.nodeValue = `${leading}${translatedValue(core)}${trailing}`;
  }

  function translateAttributes(element) {
    if (element.closest("[data-i18n-ignore]")) return;
    let originals = originalAttributes.get(element);
    if (!originals) {
      originals = new Map();
      originalAttributes.set(element, originals);
    }
    for (const attribute of ["aria-label", "title", "placeholder"]) {
      if (!element.hasAttribute(attribute)) continue;
      if (!originals.has(attribute)) originals.set(attribute, element.getAttribute(attribute) || "");
      const original = originals.get(attribute) || "";
      element.setAttribute(attribute, language === "en" ? original : translatedValue(original));
    }
  }

  function applyTo(root) {
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE) translateAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let current = walker.nextNode();
    while (current) {
      if (current.nodeType === Node.TEXT_NODE) translateTextNode(current);
      else translateAttributes(current);
      current = walker.nextNode();
    }
  }

  function syncControls() {
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
    document.documentElement.dataset.language = language === "en" ? "en" : "zh";
    for (const button of document.querySelectorAll("[data-language-choice]")) {
      button.setAttribute("aria-pressed", String(button.dataset.languageChoice === language));
    }
  }

  function setLanguage(nextLanguage, persist = true) {
    language = nextLanguage === "en" ? "en" : "zh-CN";
    if (persist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, language);
      } catch {
        // The language still changes when browser storage is unavailable.
      }
      const url = new URL(window.location.href);
      url.searchParams.set("lang", language);
      window.history.replaceState(null, "", url);
    }
    applyTo(document);
    syncControls();
    document.dispatchEvent(new CustomEvent("a3:language-change", { detail: { language } }));
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-language-choice]");
    if (button) setLanguage(button.dataset.languageChoice);
  });

  applyTo(document);
  syncControls();
  observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) applyTo(node);
    }
    syncControls();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.A3_I18N = Object.freeze({
    getLanguage: () => language,
    setLanguage
  });
})();
