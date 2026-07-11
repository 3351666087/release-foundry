"use client";

import Link from "next/link";
import { Check, CircleSlash2, Clock3, ShieldAlert, X } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, EmptyState, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function ReviewPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  return <DataBoundary>{(model) => {
    const workflow = record(model.raw.review_workflow);
    const spine = record(model.raw.a1_a2_evidence_spine);
    const records = array(workflow.records).map(record);
    const blockers = array(record(model.raw.release_decision_provenance).blockers);
    const decision = string(spine.release_decision, "block_release");
    return (
      <>
        <PageHeader
          eyebrow="RELEASE / HUMAN REVIEW"
          title={zh ? "人工审核" : "Human review"}
          summary={zh ? "审核人依据 A1 执行证据和 A2 发布判定做最终治理记录。" : "Reviewers use A1 execution evidence and A2 release authority to record governance decisions."}
          meta={<><span>{zh ? "A2 判定" : "A2 decision"}</span><StatusBadge value={decision} tone={decision.includes("block") ? "fail" : "pass"} /></>}
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

        <div className="content-grid two-one">
          <Section title={zh ? "审核队列" : "Review queue"} description={zh ? "优先处理失败和高严重度案例" : "Failed and high-severity cases first"} action={<Link className="text-link" href="/runs">{zh ? "查看全部案例" : "View all cases"}</Link>}>
            <DataTable headers={[zh ? "案例" : "Case", zh ? "失败分类" : "Failure class", zh ? "严重度" : "Severity", zh ? "分数" : "Score", zh ? "状态" : "State"]} label="Review queue">
              {model.cases.filter((item) => !item.passed).slice(0, 8).map((item) => <tr key={item.caseId}><td><Link href={{ pathname: "/case", query: { case_id: item.caseId } }}><strong>{item.caseId}</strong><small>{item.title}</small></Link></td><td>{item.failureClass}</td><td><StatusBadge value={item.severity} /></td><td>{item.score}</td><td><StatusBadge value="review_required" tone="warn" /></td></tr>)}
            </DataTable>
          </Section>

          <Section title={zh ? "发布阻塞项" : "Release blockers"} description={zh ? "解除前不能进入客户发布" : "Must be resolved before customer release"}>
            <div className="blocker-list">
              {blockers.length ? blockers.slice(0, 8).map((blocker, index) => <div key={`${string(blocker)}-${index}`}><Clock3 size={16} /><span>{string(blocker)}</span></div>) : <EmptyState title={zh ? "没有阻塞详情" : "No blocker detail"} detail={zh ? "等待 release provenance。" : "Waiting for release provenance."} />}
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
