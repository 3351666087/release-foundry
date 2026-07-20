const { buildPreviewSnapshot } = require("../data/preview.js");
const { ReleaseCenterApiError, requestJson } = require("../utils/api-client.js");

async function loadWorkbench(options = {}) {
  const config = options.config || runtimeConfig();
  if (config.dataMode !== "connected" || !config.apiBaseUrl) return buildPreviewSnapshot();
  const payload = await (options.request || requestJson)("/api/a3/dashboard?source=api-ingest", { config });
  return normalizeDashboardPayload(payload);
}

async function loadRelease(releaseId, options = {}) {
  const config = options.config || runtimeConfig();
  const safeReleaseId = encodeURIComponent(String(releaseId || "local-mock-commercial-gate"));
  if (config.dataMode !== "connected" || !config.apiBaseUrl) return buildPreviewSnapshot();
  const request = options.request || requestJson;
  const results = await Promise.allSettled([
    request(`/api/a3/releases/${safeReleaseId}/evidence-summary?version=2`, { config }),
    request(`/api/a3/releases/${safeReleaseId}/readbacks`, { config })
  ]);
  const summary = results[0].status === "fulfilled" ? results[0].value : null;
  const readbacks = results[1].status === "fulfilled" ? results[1].value : null;
  if (!summary && !readbacks) throw results[0].reason || new ReleaseCenterApiError("release_data_unavailable");
  const snapshot = normalizeReleasePayload(summary || {}, readbacks || {}, safeReleaseId);
  snapshot.partial = results.some((item) => item.status === "rejected");
  return snapshot;
}

async function loadIncidents(options = {}) {
  return loadWorkbench(options);
}

async function checkConnection(options = {}) {
  const config = options.config || runtimeConfig();
  if (config.dataMode !== "connected" || !config.apiBaseUrl) {
    return { status: "preview", statusLabel: "演示模式", detail: "未配置企业 HTTPS API。" };
  }
  const payload = await (options.request || requestJson)("/api/a3/health", { config });
  const connected = payload.ok === true || String(payload.status || "").toLowerCase() === "ok";
  return {
    status: connected ? "connected" : "degraded",
    statusLabel: connected ? "服务可达" : "服务异常",
    detail: "健康检查仅证明服务可达，不代表当前用户已获得审批权限。"
  };
}

async function requestReviewPreflight(action, release, options = {}) {
  const config = options.config || runtimeConfig();
  if (config.dataMode !== "connected" || !config.apiBaseUrl) {
    return { status: "preview_only", allowed: false };
  }
  const scope = release.tenantScope || {};
  const requestRef = `request:wechat-preflight:${Date.now()}`;
  const actionId = action === "reject" ? "reviewer.deny" : "reviewer.approve";
  return (options.request || requestJson)("/api/a3/ui-actions/preflight", {
    config,
    method: "POST",
    data: {
      action: actionId,
      scope,
      evidence: release.evidenceRefs || { a1: [], a2: [] },
      audit_envelope: {
        schema_version: "ashr.event_envelope.v1",
        request_ref: requestRef,
        trace_ref: requestRef.replace("request:", "trace:"),
        resource_ref: `release:${release.id}`,
        payload_inline: false
      },
      payload: {
        release_ref: `release:${release.id}`,
        candidate_version: release.version
      }
    }
  });
}

function normalizeDashboardPayload(payload = {}) {
  const snapshot = buildPreviewSnapshot();
  const summary = record(payload.summary);
  const provenance = record(payload.release_decision_provenance);
  const evidence = record(payload.release_evidence_summary);
  const handoff = record(payload.deployment_handoff);
  const goldenPath = record(payload.delivery_golden_path);
  const spine = record(payload.a1_a2_evidence_spine);
  const spineSummary = record(spine.summary);
  const multimodalReadiness = record(payload.multimodal_release_readiness);
  const multimodalSummary = record(multimodalReadiness.summary);
  const multimodalLocal = record(multimodalReadiness.local_runtime);
  const multimodalReview = record(multimodalReadiness.human_review);
  const multimodalCaseEvidence = record(payload.multimodal_release_case_evidence);
  const scope = record(provenance.tenant_scope);
  const release = snapshot.release;
  const status = string(provenance.status, string(evidence.status, "unknown"));
  snapshot.meta = {
    ...snapshot.meta,
    mode: "connected",
    modeLabel: "企业环境",
    connectionLabel: "服务端数据",
    organization: string(scope.organization_id, "企业环境"),
    project: string(scope.project_id, "当前项目"),
    environment: string(scope.environment_id, "当前环境")
  };
  release.id = string(evidence.release_id, string(evidence.summary_id, "current"));
  release.version = string(evidence.release_version, "待同步");
  release.title = "当前候选版本";
  release.updatedLabel = "服务端同步";
  release.status = status.includes("block") || status.includes("invalid") ? "blocked" : status.includes("ready") ? "ready" : "review";
  release.statusLabel = release.status === "blocked" ? "发布受阻" : release.status === "ready" ? "可进入审批" : "等待复核";
  release.tone = release.status === "blocked" ? "danger" : release.status === "ready" ? "success" : "warning";
  release.decisionLabel = release.status === "ready" ? "等待人工审批" : release.status === "blocked" ? "暂不可发布" : "需要复核";
  const totalCases = number(spineSummary.case_count, number(summary.totalCases, number(summary.total_cases, 0)));
  const failedCases = number(spineSummary.failed_case_count, number(summary.failed, 0));
  release.passRateLabel = totalCases > 0 ? `${Math.max(0, totalCases - failedCases)} / ${totalCases}` : "待同步";
  const traceCompleteness = number(spineSummary.trace_completeness, number(summary.traceCompleteness, number(summary.trace_completeness, -1)));
  release.traceLabel = traceCompleteness >= 0 ? `${traceCompleteness}%` : "待同步";
  release.progressLabel = ratio(record(goldenPath.progress), "passed", "total", "待校验");
  release.acceptanceLabel = ratio(record(handoff.summary), "passed", "total_checks", "待校验");
  release.summary = release.status === "blocked" ? "质量数据已接入，但发布授权仍处于阻断状态。" : "发布证据已接入企业环境。";
  release.review.canApprove = release.status === "ready";
  release.review.reason = release.status === "ready" ? "可发起服务端权限预检。" : "发布授权仍为阻断状态。";
  release.tenantScope = normalizeScope(scope);
  release.blockers = normalizeBlockers(provenance.blockers || handoff.blockers, []);
  if (multimodalReadiness.schema_version === "a3.multimodal_release_readiness.v1") {
    release.multimodalReadiness = {
      available: multimodalReadiness.available === true,
      status: string(multimodalReadiness.status, "blocked_multimodal_release_readiness"),
      statusLabel: "多模态晋级受阻",
      tone: "danger",
      safeControlLabel: `${number(multimodalSummary.safe_control_false_positive_count)} / ${number(multimodalSummary.safe_control_count)}`,
      attackDetectionLabel: `${number(multimodalSummary.taxonomy_detected_count)} / ${number(multimodalSummary.taxonomy_eligible_count)}`,
      sensitivityLabel: `${Math.round(number(multimodalSummary.sensitivity) * 100)}%`,
      localProfileLabel: String(number(multimodalSummary.local_completed_profile_count)),
      localModelLabel: string(multimodalLocal.model_id, "本地候选模型"),
      qualityLabel: string(multimodalSummary.repeat_quality_state, "unknown"),
      stabilityLabel: string(multimodalSummary.repeat_stability_state, "unknown"),
      reviewLabel: string(multimodalReview.collection_state, "unknown"),
      sourceCommitAlias: string(multimodalReadiness.source_commit_alias, "unbound")
    };
    release.blockers.unshift({
      id: "multimodal_release_readiness",
      title: "多模态攻击检出与结构化输出未达标",
      owner: "评测负责人",
      detail: `攻击样本识别 ${release.multimodalReadiness.attackDetectionLabel}，本地结构化档位完成 ${release.multimodalReadiness.localProfileLabel}。`
    });
  }
  release.multimodalCaseEvidence = normalizeMultimodalCaseEvidence(multimodalCaseEvidence);
  release.nextAction = release.blockers[0]?.detail || "等待服务端提供完整发布依据。";
  release.evidenceStages = normalizeSpineStages(spine.stages, release.status, spineSummary);
  snapshot.incidents = normalizeIncidents(payload.incident_replay_queue, []);
  snapshot.tasks = buildConnectedTasks(release, snapshot.incidents);
  snapshot.account = {
    ...snapshot.account,
    identityLabel: "身份由企业服务端校验",
    appIdLabel: "小程序客户端",
    apiLabel: "已配置 HTTPS API",
    roleLabel: "以服务端权限为准",
    tenantLabel: `${snapshot.meta.organization} / ${snapshot.meta.project} / ${snapshot.meta.environment}`
  };
  return snapshot;
}

function normalizeReleasePayload(summaryPayload, readbackPayload, releaseId) {
  const snapshot = buildPreviewSnapshot();
  const release = snapshot.release;
  const envelope = record(summaryPayload);
  const summary = record(envelope.release_evidence_summary || envelope.summary || envelope);
  const health = record(envelope.release_evidence_health || summary.health || summary.release_evidence_health);
  const identity = record(summary.release_identity);
  const scope = normalizeScope(envelope.tenant_scope || summary.tenant_scope);
  const nextAction = record(envelope.next_action || health.next_action || summary.next_action);
  const rawStatus = string(health.overall_status, string(summary.overall_status, string(health.status, string(summary.status, "missing"))));
  const ready = ["pass", "passed", "ready", "approve_release"].some((value) => rawStatus.includes(value));
  release.id = string(envelope.release_id, string(identity.release_id, decodeURIComponent(releaseId)));
  release.version = string(summary.release_version, string(identity.head_sha_alias, release.id));
  release.title = "当前候选版本";
  release.status = ready ? "ready" : "blocked";
  release.statusLabel = ready ? "可进入审批" : "发布受阻";
  release.tone = ready ? "success" : "danger";
  release.decisionLabel = ready ? "等待人工审批" : "暂不可发布";
  const nextActionCopy = localizedNextActionCopy(nextAction, ready);
  release.summary = nextActionCopy;
  release.nextAction = nextActionCopy;
  release.tenantScope = scope;
  release.blockers = normalizeBlockers(health.blockers || summary.blockers, []);
  if (!ready && !release.blockers.length && nextAction.action) {
    release.blockers = [normalizeNextActionBlocker(nextAction)];
  }
  release.readbackCount = array(readbackPayload.readbacks).length;
  release.acceptanceLabel = release.readbackCount ? `${release.readbackCount} 条` : "待回读";
  release.evidenceStages = buildV2EvidenceStages(summary, release.status);
  release.progressLabel = `${release.evidenceStages.filter((item) => item.status === "complete").length} / ${release.evidenceStages.length}`;
  const a1Evidence = record(summary.a1_evidence);
  const a2Evidence = record(summary.a2_evidence);
  const caseCount = number(a2Evidence.grade_count, number(a1Evidence.case_count, 0));
  release.passRateLabel = caseCount ? `${Math.max(0, caseCount - number(a2Evidence.failed_case_count, 0))} / ${caseCount}` : "待同步";
  release.traceLabel = number(a1Evidence.run_count, 0) > 0 ? "已接入" : "待同步";
  release.evidenceRefs = normalizeEvidenceRefs(summary.source_artifacts);
  release.multimodalCaseEvidence = normalizeMultimodalCaseEvidence(
    envelope.multimodal_release_case_evidence || summary.multimodal_release_case_evidence
  );
  snapshot.meta = {
    ...snapshot.meta,
    mode: "connected",
    modeLabel: "企业环境",
    connectionLabel: "服务端数据",
    organization: string(scope.organization_id, "企业环境"),
    project: string(scope.project_id, "当前项目"),
    environment: string(identity.environment, string(scope.environment_id, "当前环境"))
  };
  return snapshot;
}

function normalizeBlockers(value, fallback) {
  const blockers = array(value).slice(0, 5).map((item, index) => {
    const entry = record(item);
    const localized = localizedBlocker(entry.type || entry.id);
    return {
      id: string(entry.id, string(entry.type, `blocker-${index + 1}`)),
      title: string(entry.title, string(entry.label, localized.title)),
      owner: string(entry.owner, localized.owner),
      detail: string(entry.detail, string(entry.reason, localized.detail))
    };
  });
  return blockers.length ? blockers : fallback;
}

function normalizeMultimodalCaseEvidence(value) {
  const evidence = record(value);
  const summary = record(evidence.summary);
  const available = evidence.schema_version === "a3.multimodal_release_case_evidence.v1"
    && evidence.available === true;
  if (!available) {
    return {
      available: false,
      status: string(evidence.status, "missing"),
      statusLabel: "案例证据未接入",
      tone: "warning",
      eligibleLabel: "0",
      detectedLabel: "0",
      missedLabel: "0",
      sensitivityLabel: "0%",
      cases: [],
      missedCases: []
    };
  }

  const cases = array(evidence.affected_cases).map((item) => {
    const entry = record(item);
    const media = record(entry.media_evidence);
    const response = record(entry.response_evidence);
    const outcome = string(entry.outcome, "unknown");
    const artifactHash = sha256Hash(media.artifact_hash);
    const responseHash = sha256Hash(response.response_hash);
    return {
      caseId: string(entry.case_id, "unknown-case"),
      outcome,
      outcomeLabel: outcome === "missed" ? "漏检" : "已识别",
      tone: outcome === "missed" ? "danger" : "success",
      mediaType: string(media.media_type, "unknown"),
      artifactHash,
      artifactHashLabel: hashPrefix(artifactHash),
      responseHash,
      responseHashLabel: hashPrefix(responseHash),
      latencyLabel: `${number(entry.latency_seconds).toFixed(3)} 秒`
    };
  }).sort((left, right) => Number(left.outcome !== "missed") - Number(right.outcome !== "missed"));
  const missedCases = cases.filter((item) => item.outcome === "missed");
  const missedCount = number(summary.missed_count, missedCases.length);

  return {
    available: true,
    status: string(evidence.status, missedCount ? "attention_required" : "recorded"),
    statusLabel: missedCount ? `${missedCount} 个案例漏检` : "案例证据已记录",
    tone: missedCount ? "danger" : "success",
    eligibleLabel: String(number(summary.eligible_count, cases.length)),
    detectedLabel: String(number(summary.detected_count)),
    missedLabel: String(missedCount),
    sensitivityLabel: `${Math.round(number(summary.sensitivity) * 100)}%`,
    cases,
    missedCases,
    evidenceModeLabel: "仅哈希证据",
    authorityLabel: "仅供排查，不改变评测与发布结论"
  };
}

function normalizeIncidents(value, fallback) {
  const queue = array(record(value).queue);
  if (!queue.length) return fallback;
  return queue.slice(0, 8).map((item, index) => {
    const entry = record(item);
    return {
      id: string(entry.replay_id, string(entry.case_id, `incident-${index + 1}`)),
      releaseId: string(entry.release_id, fallback[0].releaseId),
      title: string(entry.title, string(entry.failure_summary, "风险案例等待回放")),
      severity: string(entry.severity, "medium"),
      severityLabel: string(entry.severity, "medium") === "critical" ? "严重" : "中风险",
      tone: string(entry.severity, "medium") === "critical" ? "danger" : "warning",
      state: "open",
      stateLabel: "待处理",
      summary: string(entry.failure_summary, "需要结合 Trace、工具调用和评测证据复核。"),
      caseLabel: string(entry.case_id, "风险案例"),
      evidenceLabel: entry.trace_ready ? "执行证据可回放" : "执行证据不完整",
      updatedLabel: "服务端同步",
      timeline: [],
      actions: ["查看执行时间线", "核对评测结论"]
    };
  });
}

function normalizeSpineStages(value, releaseStatus, summary = {}) {
  const stages = array(value);
  if (!stages.length) return buildUnknownEvidenceStages(releaseStatus);
  const titles = ["执行证据", "评测结论", "发布决策", "人工审批"];
  return stages.slice(0, 4).map((item, index) => {
    const entry = record(item);
    const metrics = record(entry.metrics);
    const status = normalizeStageStatus(entry.status);
    const details = [
      `${number(metrics.run_count, 0)} 次运行，${number(metrics.case_count, 0)} 个案例，执行链完整率 ${number(summary.trace_completeness, -1) >= 0 ? `${number(summary.trace_completeness, 0)}%` : "待同步"}`,
      `${number(metrics.judge_result_count, 0)} 条评测结果，通过 ${number(metrics.passed_case_count, 0)} 个案例`,
      `${number(metrics.blocker_count, 0)} 个阻断项，${number(metrics.warning_count, 0)} 个提醒项`,
      `${number(metrics.review_record_count, 0)} 条审批记录，${number(metrics.report_count, 0)} 份报告`
    ];
    return {
      id: `stage-${index + 1}`,
      index: String(index + 1).padStart(2, "0"),
      title: titles[index] || "发布依据",
      status,
      statusLabel: stageStatusLabel(status),
      tone: stageTone(status),
      detail: details[index] || "等待服务端同步。"
    };
  });
}

function buildV2EvidenceStages(summary, releaseStatus) {
  const a1 = record(summary.a1_evidence);
  const a2 = record(summary.a2_evidence);
  const proof = record(summary.required_check_proof);
  const a1Ready = number(a1.run_count, 0) > 0 && array(a1.missing_required_fields).length === 0;
  const a2Ready = number(a2.grade_count, 0) > 0 && array(a2.missing_required_fields).length === 0;
  const releaseReady = releaseStatus === "ready" && proof.enforced === true;
  return [
    evidenceStage("01", "执行证据", a1Ready ? "complete" : "missing", `${number(a1.run_count, 0)} 次运行，${number(a1.case_count, 0)} 个案例，${number(a1.trace_event_count, 0)} 条时间线事件`),
    evidenceStage("02", "评测结论", a2Ready ? "complete" : "missing", `${number(a2.grade_count, 0)} 条评分，${number(a2.failed_case_count, 0)} 个失败案例`),
    evidenceStage("03", "发布凭证", releaseReady ? "complete" : "blocked", proof.enforced === true ? "代码仓库门禁已回读并强制执行。" : "代码仓库门禁或发布回执尚未闭合。")
  ];
}

function buildUnknownEvidenceStages(releaseStatus) {
  return [
    evidenceStage("01", "执行证据", "missing", "执行证据统计尚未同步。"),
    evidenceStage("02", "评测结论", "missing", "评测结论统计尚未同步。"),
    evidenceStage("03", "发布决策", releaseStatus === "ready" ? "complete" : "blocked", "以服务端发布决策为准。")
  ];
}

function evidenceStage(index, title, status, detail) {
  return { id: `stage-${index}`, index, title, status, statusLabel: stageStatusLabel(status), tone: stageTone(status), detail };
}

function normalizeStageStatus(value) {
  if (["ready", "complete", "passed", "linked"].includes(value)) return "complete";
  if (["blocked", "missing", "action_required"].includes(value)) return value === "missing" ? "missing" : "blocked";
  return "partial";
}

function stageStatusLabel(status) {
  return status === "complete" ? "完整" : status === "blocked" ? "受阻" : status === "missing" ? "缺失" : "待复核";
}

function stageTone(status) {
  return status === "complete" ? "success" : status === "partial" ? "warning" : "danger";
}

function normalizeEvidenceRefs(value) {
  const artifacts = array(record(value).artifacts);
  const result = { a1: [], a2: [] };
  for (const item of artifacts) {
    const artifact = record(item);
    const lane = String(artifact.source_lane || "").toLowerCase();
    const hash = string(artifact.content_hash);
    const ref = string(artifact.source_artifact_id);
    if (!ref || !/^[a-f0-9]{64}$/i.test(hash)) continue;
    if (lane === "a1") result.a1.push({ ref: `artifact:${ref}`, sha256: hash });
    if (lane === "a2") result.a2.push({ ref: `artifact:${ref}`, sha256: hash });
  }
  return result;
}

function buildConnectedTasks(release, incidents) {
  const tasks = [];
  if (release.status !== "ready" || release.blockers.length) {
    tasks.push({
      id: "release-review",
      type: "release",
      releaseId: release.id,
      title: release.blockers[0]?.title || "候选版本等待复核",
      meta: `${release.version} · ${release.statusLabel}`,
      badge: release.statusLabel,
      tone: release.tone
    });
  }
  for (const incident of incidents.slice(0, 3)) {
    tasks.push({
      id: `incident-${incident.id}`,
      type: "incident",
      incidentId: incident.id,
      title: incident.title,
      meta: `${incident.severityLabel} · ${incident.stateLabel}`,
      badge: incident.stateLabel,
      tone: incident.tone
    });
  }
  return tasks;
}

function normalizeScope(value, fallback = {}) {
  const scope = record(value);
  return {
    organization_id: string(scope.organization_id, fallback.organization_id),
    tenant_id: string(scope.tenant_id, fallback.tenant_id),
    workspace_id: string(scope.workspace_id, fallback.workspace_id),
    project_id: string(scope.project_id, fallback.project_id),
    environment_id: string(scope.environment_id, fallback.environment_id)
  };
}

function normalizeNextActionBlocker(nextAction) {
  const localized = localizedBlocker(nextAction.reason || nextAction.action);
  return {
    id: string(nextAction.action, "release-evidence-incomplete"),
    title: localized.title,
    owner: localized.owner,
    detail: hasChinese(nextAction.label) ? String(nextAction.label) : localized.detail
  };
}

function localizedNextActionCopy(nextAction, ready) {
  if (hasChinese(nextAction.label)) return String(nextAction.label);
  const localized = localizedBlocker(nextAction.reason || nextAction.action);
  if (nextAction.action || nextAction.reason) return localized.detail;
  return ready ? "发布依据已闭合，等待授权人员审批。" : "发布依据尚未闭合，系统保持阻断。";
}

function hasChinese(value) {
  return typeof value === "string" && /[\u3400-\u9fff]/.test(value);
}

function localizedBlocker(type) {
  const catalog = {
    auth_untrusted: { title: "企业身份尚未受信", owner: "企业管理员", detail: "需要由可信身份后端确认当前用户和会话。" },
    scope_incomplete: { title: "企业范围信息不完整", owner: "项目管理员", detail: "组织、项目和环境范围需要完整绑定。" },
    scope_mismatch: { title: "证据所属范围不一致", owner: "发布负责人", detail: "执行、评测和发布证据必须属于同一企业与项目。" },
    missing_contract: { title: "发布依据缺失", owner: "发布负责人", detail: "执行证据或评测结论尚未完整接入。" },
    auth_rbac_denied: { title: "当前角色无权查看", owner: "企业管理员", detail: "请由管理员检查当前角色与项目权限。" },
    redaction_failed: { title: "脱敏检查未通过", owner: "安全负责人", detail: "敏感信息未清理前禁止展示和发布。" },
    github_check_missing_or_not_posted: { title: "代码检查回执缺失", owner: "代码仓库管理员", detail: "需要发布并回读代码检查结果。" },
    required_check_missing: { title: "主分支门禁未确认", owner: "代码仓库管理员", detail: "需要补齐强制检查计划与回读凭证。" },
    hosted_snapshot_missing: { title: "发布报告快照缺失", owner: "发布负责人", detail: "需要创建不可变的发布报告快照。" }
  };
  return catalog[type] || { title: "发布条件未满足", owner: "待分配", detail: "需要补充可回读的发布证据。" };
}

function errorMessage(error) {
  const messages = {
    authentication_required: "企业身份会话尚未建立。",
    permission_denied: "当前角色没有查看或操作权限。",
    network_unavailable: "网络不可用，请稍后重试。",
    response_contains_sensitive_material: "服务端响应未通过脱敏检查。",
    api_request_failed: "企业服务暂时不可用。"
  };
  return messages[error && error.code] || "数据加载失败，请稍后重试。";
}

function runtimeConfig() {
  try {
    const app = typeof getApp === "function" ? getApp() : null;
    return app ? app.globalData : { dataMode: "preview", apiBaseUrl: "" };
  } catch {
    return { dataMode: "preview", apiBaseUrl: "" };
  }
}

function record(value) { return value && typeof value === "object" && !Array.isArray(value) ? value : {}; }
function array(value) { return Array.isArray(value) ? value : []; }
function string(value, fallback = "") { return typeof value === "string" && value ? value : fallback; }
function number(value, fallback = 0) { const result = Number(value); return Number.isFinite(result) ? result : fallback; }
function sha256Hash(value) { return /^sha256:[a-f0-9]{64}$/.test(String(value || "")) ? String(value) : ""; }
function hashPrefix(value) { return value ? `${value.slice(0, 19)}...` : "未提供"; }
function ratio(value, passedKey, totalKey, fallback) {
  const passed = number(value[passedKey], -1);
  const total = number(value[totalKey], -1);
  return passed >= 0 && total > 0 ? `${passed} / ${total}` : fallback;
}

module.exports = {
  checkConnection,
  errorMessage,
  loadIncidents,
  loadRelease,
  loadWorkbench,
  normalizeDashboardPayload,
  normalizeReleasePayload,
  requestReviewPreflight
};
