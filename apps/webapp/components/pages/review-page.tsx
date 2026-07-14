"use client";

import Link from "next/link";
import { Check, CircleSlash2, Clock3, FileCheck2, GitCompareArrows, History, Images, LockKeyhole, ShieldAlert, UserRoundCheck, X } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { MultimodalEvidenceRequestPanel } from "../multimodal-evidence-request-panel";
import { DataBoundary, DataTable, EmptyState, formatDate, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function ReviewPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  return <DataBoundary>{(model) => {
    const workflow = record(model.raw.review_workflow);
    const spine = record(model.raw.a1_a2_evidence_spine);
    const records = array(workflow.records).map(record);
    const blockers = array(record(model.raw.release_decision_provenance).blockers);
    const decision = string(spine.release_decision, "block_release");
    const multimodalQueue = record(model.raw.multimodal_review_queue);
    const multimodalSummary = record(multimodalQueue.summary);
    const multimodalAuthority = record(multimodalQueue.authority_boundary);
    const multimodalItems = array(multimodalQueue.items).map(record);
    const multimodalPacket = record(model.raw.multimodal_review_assignment_packet);
    const multimodalPacketIntegrity = record(multimodalPacket.integrity);
    const multimodalPacketArchive = record(multimodalPacket.archive_binding);
    const multimodalAvailable = multimodalQueue.available === true;
    const multimodalStatus = string(multimodalQueue.status, "not_ingested");
    return (
      <>
        <PageHeader
          eyebrow="RELEASE / HUMAN REVIEW"
          title={zh ? "人工审核" : "Human review"}
          summary={zh ? "审核人依据执行证据和权威发布判定做最终治理记录。" : "Reviewers use execution evidence and release authority to record governance decisions."}
          meta={<><span>{zh ? "权威判定" : "Authoritative decision"}</span><StatusBadge value={decision} tone={decision.includes("block") ? "fail" : "pass"} /></>}
        />

        <section className="review-decision">
          <div><ShieldAlert size={26} /><span className="eyebrow">{zh ? "当前决策" : "CURRENT DECISION"}</span><h2>{decision}</h2><p>{zh ? "真实批准、拒绝和豁免需要 hosted auth、RBAC 和持久化审计。" : "Live approve, deny, and waiver actions require hosted auth, RBAC, and durable audit."}</p></div>
          <div className="review-actions" aria-label="Review actions">
            <button type="button" disabled title={zh ? "等待真实审核执行器" : "Requires live review executor"}><Check size={17} />{zh ? "批准" : "Approve"}</button>
            <button type="button" disabled title={zh ? "等待真实审核执行器" : "Requires live review executor"}><X size={17} />{zh ? "拒绝" : "Deny"}</button>
            <button type="button" disabled title={zh ? "等待真实审核执行器" : "Requires live review executor"}><CircleSlash2 size={17} />{zh ? "申请豁免" : "Request waiver"}</button>
          </div>
        </section>

        <MetricStrip items={[
          { label: zh ? "审核记录" : "Records", value: number(workflow.record_count), tone: "info" },
          { label: zh ? "批准" : "Approvals", value: number(workflow.approval_count), tone: "pass" },
          { label: zh ? "拒绝" : "Denials", value: number(workflow.denial_count), tone: "fail" },
          { label: zh ? "豁免" : "Waivers", value: number(workflow.waiver_count), tone: "warn" }
        ]} />

        <Section
          className="multimodal-review-section"
          title={zh ? "多模态分歧审核" : "Multimodal disagreement review"}
          description={zh ? "比较不同模型对同一媒体证据的观察，分歧必须交给权威人工复核服务。" : "Compare model observations for the same media evidence and hand disagreements to the authoritative review service."}
        >
          <div className="multimodal-review-summary" data-status={multimodalStatus}>
            <div className="multimodal-review-lead">
              <span className="multimodal-review-icon"><Images size={22} aria-hidden="true" /></span>
              <div>
                <span className="eyebrow">{zh ? "评测服务 / 模型比较" : "EVALUATION / MODEL COMPARISON"}</span>
                <strong>{multimodalAvailable
                  ? (zh ? "发现需要人工确认的模型分歧" : "Model disagreement requires human confirmation")
                  : multimodalStatus === "invalid_upstream_contract"
                    ? (zh ? "上游比较契约校验失败" : "Upstream comparison contract failed validation")
                    : (zh ? "尚未接入多模态比较数据" : "No multimodal comparison data ingested")}</strong>
                <p>{zh
                  ? "队列回执不具备发布权，产品不会据此改写分数、风险或发布决定。"
                  : "Queue receipts have no release authority; the product does not rewrite scores, risk, or the release decision."}</p>
              </div>
            </div>
            <div className="multimodal-review-metrics" aria-label={zh ? "多模态比较摘要" : "Multimodal comparison summary"}>
              <div><span>{zh ? "比较记录" : "Comparisons"}</span><strong>{number(multimodalSummary.comparison_count)}</strong></div>
              <div><span>{zh ? "语义分歧" : "Disagreements"}</span><strong>{number(multimodalSummary.semantic_disagreement)}</strong></div>
              <div><span>{zh ? "等待复核" : "Awaiting review"}</span><strong>{number(multimodalSummary.review_required_count)}</strong></div>
              <div><span>{zh ? "可改变发布决定" : "May change release"}</span><strong>{multimodalAuthority.can_change_release_decision === true ? (zh ? "是" : "Yes") : (zh ? "否" : "No")}</strong></div>
            </div>
          </div>

          {multimodalAvailable && (
            <div className="multimodal-assignment-strip" aria-label={zh ? "审核领取状态" : "Review assignment status"}>
              <div><UserRoundCheck size={17} aria-hidden="true" /><span>{zh ? "正在处理" : "Actively assigned"}</span><strong>{number(multimodalSummary.assignment_active_count)}</strong></div>
              <div><LockKeyhole size={17} aria-hidden="true" /><span>{zh ? "等待领取" : "Unassigned"}</span><strong>{number(multimodalSummary.assignment_unassigned_count)}</strong></div>
              <div><Clock3 size={17} aria-hidden="true" /><span>{zh ? "锁已过期" : "Expired leases"}</span><strong>{number(multimodalSummary.assignment_expired_count)}</strong></div>
            </div>
          )}

          {multimodalAvailable && (
            <div className="multimodal-review-packet" data-integrity={string(multimodalPacketIntegrity.status, "unknown")}>
              <span className="multimodal-review-packet-icon"><FileCheck2 size={20} aria-hidden="true" /></span>
              <div>
                <small>{zh ? "审核操作留痕" : "Review operation evidence"}</small>
                <strong>{number(multimodalPacket.event_count) > 0
                  ? (zh ? "历史记录已通过内部完整性校验" : "History passed internal integrity checks")
                  : (zh ? "等待第一条审核操作记录" : "Waiting for the first review operation")}</strong>
                <span>{zh
                  ? "领取记录只证明人员协作；必须进入签名审计归档后，才能作为可验证交付证据。"
                  : "Assignment history proves coordination only; it becomes verifiable delivery evidence after inclusion in a signed Audit Archive."}</span>
              </div>
              <div className="multimodal-review-packet-state">
                <StatusBadge value={packetIntegrityLabel(multimodalPacketIntegrity.status, zh)} tone={multimodalPacketIntegrity.status === "passed" ? "pass" : "fail"} />
                <StatusBadge value={multimodalPacketArchive.audit_archive_signature_verified === true
                  ? (zh ? "归档签名已验证" : "archive signature verified")
                  : (zh ? "等待归档签名" : "archive signature pending")} tone="warn" />
                <code title={string(multimodalPacket.packet_root_hash)}>{hashPrefix(string(multimodalPacket.packet_root_hash, "hash-pending"))}</code>
              </div>
            </div>
          )}

          {multimodalItems.length ? (
            <div className="multimodal-review-list" role="region" aria-label={zh ? "多模态分歧审核队列" : "Multimodal disagreement review queue"}>
              {multimodalItems.map((item) => {
                const left = record(item.left);
                const right = record(item.right);
                const threeWayProviders = array(item.providers).map(record);
                const comparedProviders = threeWayProviders.length ? threeWayProviders : [left, right];
                const providerLabels = comparedProviders.map(providerObservationLabel);
                const operational = record(item.operational_state);
                const assignmentHistory = array(item.assignment_history).map(record);
                return (
                  <article key={string(item.queue_id)}>
                    <div><small>{zh ? "案例与证据" : "Case and evidence"}</small><strong>{string(item.case_id)}</strong><span>{comparisonScopeLabel(item, zh)}</span><code>{hashPrefix(string(item.artifact_hash))}</code></div>
                    <div>
                      <small>{comparedProviders.length > 2 ? (zh ? "三方模型比较" : "Three-provider comparison") : (zh ? "模型比较" : "Model pair")}</small>
                      <span className="model-pair"><GitCompareArrows size={15} aria-hidden="true" /><strong>{providerLabels.join(" / ")}</strong></span>
                      <span>{comparedProviders.length} {zh ? "路观察" : "observations"} · {zh ? "同一媒体证据" : "same media evidence"}{threeWayProviders.length ? ` · ${zh ? "可用" : "eligible"} ${number(item.eligible_provider_count)}` : ""}</span>
                    </div>
                    <div>
                      <small>{zh ? "风险观察" : "Risk observation"}</small>
                      <span className="observation-pair-risk">
                        {comparedProviders.map((provider, providerIndex) => (
                          <span key={`${providerObservationLabel(provider)}-${providerIndex}`} title={string(provider.observation_state, zh ? "状态未知" : "state unknown")}>
                            <StatusBadge value={`${providerObservationLabel(provider)}: ${modelRiskLabel(provider, zh)}`} tone={modelRiskTone(provider)} />
                          </span>
                        ))}
                      </span>
                    </div>
                    <div className="multimodal-assignment-state">
                      <small>{zh ? "人员领取状态" : "Human assignment"}</small>
                      <StatusBadge value={assignmentStateLabel(operational.status, zh)} tone={assignmentStateTone(operational.status)} />
                      <span>{zh ? "评测队列" : "Evaluation queue"}: {queueStateLabel(item.queue_state, zh)}</span>
                      <span>{operational.assigned_reviewer_hash
                        ? `${zh ? "审核员" : "Reviewer"} ${hashPrefix(string(operational.assigned_reviewer_hash))}`
                        : (zh ? "尚未分配审核员" : "No reviewer assigned")}</span>
                      <span>{zh ? "版本" : "Version"} {number(operational.version)} · {leaseLabel(operational.lease_expires_at, zh)}</span>
                      {assignmentHistory.length > 0 && (
                        <details className="assignment-history">
                          <summary><History size={14} aria-hidden="true" />{zh ? `查看 ${assignmentHistory.length} 条操作记录` : `View ${assignmentHistory.length} operation event(s)`}</summary>
                          <ol>
                            {assignmentHistory.map((event, eventIndex) => (
                              <li key={`${string(event.event_id)}-${eventIndex}`}>
                                <strong>{assignmentEventLabel(event.event_type, zh)}</strong>
                                <span>{formatDate(string(event.created_at))} · v{number(event.version)}</span>
                                <code title={string(event.event_hash)}>{hashPrefix(string(event.event_hash))}</code>
                              </li>
                            ))}
                          </ol>
                        </details>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title={multimodalStatus === "invalid_upstream_contract"
                ? (zh ? "比较数据未通过安全校验" : "Comparison data failed safety validation")
                : (zh ? "暂无多模态复核项" : "No multimodal review items")}
              detail={multimodalStatus === "invalid_upstream_contract"
                ? (zh ? "已停止展示不一致或不安全的上游字段，请检查导入回执。" : "Unsafe or inconsistent upstream fields are hidden; inspect the import receipt.")
                : (zh ? "接入评测服务比较回执后，这里会显示真实分歧。" : "Authoritative comparison receipts will appear here after ingestion.")}
            />
          )}

          {multimodalAvailable && (
            <MultimodalEvidenceRequestPanel
              source={model.source}
              tenantScope={record(multimodalQueue.tenant_scope)}
              queueItems={multimodalItems}
              summary={multimodalSummary}
              zh={zh}
            />
          )}

          <div className="multimodal-authority-note">
            <ShieldAlert size={17} aria-hidden="true" />
            <span>{zh
              ? "必须收到权威人工复核结果和同一候选版本的决策账本，发布状态才可能改变。"
              : "Release state may change only after an authoritative human resolution and a same-candidate decision ledger are available."}</span>
            <StatusBadge value={capabilityLabel(multimodalQueue.capability_state, zh)} tone="warn" />
          </div>
        </Section>

        <div className="content-grid two-one">
          <Section title={zh ? "审核队列" : "Review queue"} description={zh ? "优先处理失败和高严重度案例" : "Failed and high-severity cases first"} action={<Link className="text-link" href="/runs">{zh ? "查看全部案例" : "View all cases"}</Link>}>
            <DataTable headers={[zh ? "案例" : "Case", zh ? "失败分类" : "Failure class", zh ? "严重度" : "Severity", zh ? "分数" : "Score", zh ? "状态" : "State"]} label="Review queue">
              {model.cases.filter((item) => !item.passed).slice(0, 8).map((item) => <tr key={item.caseId}><td><Link href={{ pathname: "/case", query: { case_id: item.caseId } }}><strong>{item.caseId}</strong><small>{item.title}</small></Link></td><td>{item.failureClass}</td><td><StatusBadge value={item.severity} /></td><td>{item.score}</td><td><StatusBadge value="review_required" tone="warn" /></td></tr>)}
            </DataTable>
          </Section>

          <Section title={zh ? "发布阻塞项" : "Release blockers"} description={zh ? "解除前不能进入客户发布" : "Must be resolved before customer release"}>
            <div className="blocker-list">
              {blockers.length ? blockers.slice(0, 8).map((blocker, index) => <div key={`${blockerLabel(blocker)}-${index}`}><Clock3 size={16} /><span>{blockerLabel(blocker)}</span></div>) : <EmptyState title={zh ? "没有阻塞详情" : "No blocker detail"} detail={zh ? "等待 release provenance。" : "Waiting for release provenance."} />}
            </div>
          </Section>
        </div>

        <Section title={zh ? "历史审核记录" : "Review history"} description={zh ? "租户范围内可审计的人工操作" : "Auditable human actions inside the tenant scope"}>
          {records.length ? <DataTable headers={["Record", "Decision", "Actor", "Created"]} label="Review records">{records.map((recordItem, index) => <tr key={`${string(recordItem.record_id)}-${index}`}><td>{string(recordItem.record_id)}</td><td><StatusBadge value={string(recordItem.decision)} /></td><td>{string(recordItem.actor_role, "[REDACTED]")}</td><td>{string(recordItem.created_at)}</td></tr>)}</DataTable> : <EmptyState title={zh ? "暂无持久化审核记录" : "No durable review records"} detail={zh ? "当前数据源仍处于只读演示状态。" : "The current source remains a read-only demo."} />}
        </Section>
      </>
    );
  }}</DataBoundary>;
}

function riskLabel(value: unknown, zh: boolean) {
  if (value === true) return zh ? "发现风险" : "risk observed";
  if (value === false) return zh ? "未发现风险" : "no risk observed";
  return zh ? "不可用" : "unavailable";
}

function modelRiskLabel(value: unknown, zh: boolean) {
  const observation = record(value);
  const validRisks = array(observation.valid_risks).filter((item) => typeof item === "boolean");
  if (validRisks.includes(true) && validRisks.includes(false)) {
    return zh ? "重复结果不稳定" : "unstable across repeats";
  }
  return riskLabel(observation.observed_risk, zh);
}

function modelRiskTone(value: unknown): "pass" | "warn" | "fail" {
  const observation = record(value);
  const validRisks = array(observation.valid_risks).filter((item) => typeof item === "boolean");
  if (validRisks.includes(true) && validRisks.includes(false)) return "warn";
  if (observation.observed_risk === true) return "fail";
  if (observation.observed_risk === false) return "pass";
  return "warn";
}

function providerObservationLabel(value: unknown) {
  const observation = record(value);
  return string(observation.model_id, string(observation.provider_key, string(observation.provider_id, "provider")));
}

function comparisonScopeLabel(value: unknown, zh: boolean) {
  const item = record(value);
  const scope = string(item.comparison_scope, "case");
  if (scope === "aggregate") return zh ? "重复结果聚合" : "aggregate across repeats";
  if (scope === "repeat") return zh ? `第 ${number(item.repeat)} 次观察` : `repeat ${number(item.repeat)}`;
  return zh ? "单次比较" : "single comparison";
}

function queueStateLabel(value: unknown, zh: boolean) {
  const state = string(value, "unknown");
  if (state === "awaiting_human_review") return zh ? "等待人工复核" : "awaiting human review";
  return state;
}

function assignmentStateLabel(value: unknown, zh: boolean) {
  const state = string(value, "unassigned");
  if (state === "claimed") return zh ? "处理中" : "claimed";
  if (state === "expired") return zh ? "锁已过期" : "lease expired";
  return zh ? "等待领取" : "unassigned";
}

function assignmentStateTone(value: unknown): "pass" | "warn" | "fail" {
  const state = string(value, "unassigned");
  if (state === "claimed") return "pass";
  if (state === "expired") return "fail";
  return "warn";
}

function assignmentEventLabel(value: unknown, zh: boolean) {
  const event = string(value, "unknown");
  const labels: Record<string, [string, string]> = {
    claimed: ["领取", "claimed"],
    reclaimed_after_expiry: ["超时后重新领取", "reclaimed after expiry"],
    renewed: ["续期", "renewed"],
    released: ["释放", "released"],
    transferred: ["转交", "transferred"]
  };
  return labels[event]?.[zh ? 0 : 1] || event;
}

function packetIntegrityLabel(value: unknown, zh: boolean) {
  return string(value) === "passed"
    ? (zh ? "内部完整性通过" : "integrity passed")
    : (zh ? "完整性失败" : "integrity failed");
}

function leaseLabel(value: unknown, zh: boolean) {
  if (!value) return zh ? "无活动锁" : "no active lease";
  return `${zh ? "锁定至" : "lease until"} ${formatDate(string(value))}`;
}

function capabilityLabel(value: unknown, zh: boolean) {
  const state = string(value, "not_available");
  if (state === "peer_branch_contract_not_merged") return zh ? "上游契约待合并" : "upstream contract pending merge";
  if (state === "contract_supported_unverified_candidate_binding") return zh ? "候选版本绑定待验证" : "candidate binding unverified";
  if (state === "contract_supported_not_production_verified") return zh ? "契约已支持，未完成生产验证" : "contract supported, not production verified";
  return zh ? "尚不可用" : "not available";
}

function hashPrefix(value: string) {
  return value.startsWith("sha256:") ? `${value.slice(0, 19)}...` : value;
}

function blockerLabel(value: unknown) {
  const item = record(value);
  return string(item.message, string(item.reason, string(item.type, string(value))));
}
