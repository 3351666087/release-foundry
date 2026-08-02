"use client";

import { Download, FileJson, Link2, Printer, ShieldCheck } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, EmptyState, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function ReportsPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  return <DataBoundary>{(model) => {
    const center = record(model.raw.report_center);
    const summary = record(center.summary);
    const reports = array(center.reports).map(record);
    const registry = record(model.raw.artifact_registry);
    const artifacts = array(registry.entries).map(record);

    const exportJson = () => {
      const blob = new Blob([JSON.stringify(model.raw, null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `releasefoundry-a3-${model.summary.lastRunId}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    };

    return (
      <>
        <PageHeader
          eyebrow="RELEASE / REPORT CENTER"
          title={zh ? "报告中心" : "Report center"}
          summary={zh ? "把运行、评分、审核和发布证据整理成可交付报告。" : "Package runs, grades, reviews, and release evidence into a deliverable report."}
          actions={<><button className="command-button" type="button" onClick={exportJson}><FileJson size={15} />JSON</button><button className="command-button" type="button" onClick={() => window.print()}><Printer size={15} />{zh ? "打印" : "Print"}</button></>}
        />

        <section className="report-spotlight">
          <div><span className="eyebrow">{zh ? "最新证据包" : "LATEST EVIDENCE PACKET"}</span><h2>{model.summary.lastRunId}</h2><p>{zh ? `${model.summary.totalCases} 个案例，${model.summary.failed} 个失败，Trace 完整率 ${model.summary.traceCompleteness}%。` : `${model.summary.totalCases} cases, ${model.summary.failed} failed, ${model.summary.traceCompleteness}% trace complete.`}</p></div>
          <div className="report-spotlight-actions"><button type="button" onClick={exportJson}><Download size={17} />{zh ? "下载 JSON" : "Download JSON"}</button><button type="button" disabled title={zh ? "等待托管报告服务" : "Requires hosted report service"}><Link2 size={17} />{zh ? "创建分享链接" : "Create share link"}</button></div>
        </section>

        <MetricStrip items={[
          { label: zh ? "托管报告" : "Hosted reports", value: number(summary.report_count), tone: "info" },
          { label: zh ? "可分享" : "Shareable", value: number(summary.shareable_count), tone: "pass" },
          { label: zh ? "已撤销" : "Revoked", value: number(summary.revoked_count), tone: "warn" },
          { label: zh ? "证据制品" : "Artifacts", value: number(summary.artifact_registry_count, artifacts.length), tone: "cobalt" }
        ]} />

        <Section title={zh ? "托管报告" : "Hosted reports"} description={zh ? "分享链接可撤销、可过期并保留审计" : "Share links are revocable, expirable, and auditable"}>
          {reports.length ? <DataTable headers={["Report", "Status", "Scope", "Views"]} label="Hosted reports">{reports.map((report, index) => <tr key={`${string(report.report_id)}-${index}`}><td><strong>{string(report.title, string(report.report_id))}</strong><small>{string(report.report_id)}</small></td><td><StatusBadge value={string(report.status)} /></td><td>{string(record(report.tenant_scope).project_id)}</td><td>{number(report.view_count)}</td></tr>)}</DataTable> : <EmptyState title={zh ? "还没有托管报告" : "No hosted reports yet"} detail={zh ? "本地导出可用；真实分享需要 auth、DB、审计和撤销接口。" : "Local export works; hosted sharing requires auth, DB, audit, and revoke APIs."} />}
        </Section>

        <Section title={zh ? "证据制品" : "Artifact registry"} description={zh ? "进入报告和审计包的哈希化制品" : "Hashed artifacts entering reports and audit bundles"}>
          <div className="artifact-grid">{artifacts.slice(0, 10).map((artifact, index) => <article key={`${string(artifact.artifact_id)}-${index}`}><ShieldCheck size={17} /><div><strong>{string(artifact.artifact_type, string(artifact.artifact_id))}</strong><span>{string(artifact.customer_value, string(artifact.lifecycle_state))}</span></div><StatusBadge value={string(artifact.hash_status)} /></article>)}</div>
        </Section>
      </>
    );
  }}</DataBoundary>;
}
