"use client";

import { Archive, FileCheck2, LockKeyhole, ShieldAlert, ShieldCheck } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, EvidenceDetails, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function TrustPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  return <DataBoundary>{(model) => {
    const admin = record(model.raw.saas_admin_console);
    const trust = record(admin.trust);
    const center = record(trust.trust_center);
    const compliance = record(trust.compliance_posture);
    const enterprise = record(model.raw.enterprise_readiness);
    const provenance = record(model.raw.release_decision_provenance);
    const artifacts = array(center.artifacts).map(record);
    const blockers = array(trust.publish_blockers);
    const missingContracts = array(provenance.missing_contracts);
    return (
      <>
        <PageHeader
          eyebrow="TRUST / AUDIT / COMPLIANCE"
          title={zh ? "信任与审计" : "Trust and audit"}
          summary={zh ? "客户可见的信任声明必须由发布证据、脱敏报告和审计记录支持。" : "Customer-facing trust claims require release evidence, redacted reports, and audit records."}
          meta={<><span>{zh ? "公开发布" : "Public publish"}</span><StatusBadge value={string(trust.status)} tone="fail" /></>}
        />

        <section className="trust-posture">
          <div><ShieldAlert size={27} /><span className="eyebrow">{zh ? "当前信任状态" : "CURRENT TRUST POSTURE"}</span><h2>{string(trust.release_gate_label, "Block release")}</h2><p>{string(trust.blocked_reason, zh ? "发布证据尚未满足。" : "Release evidence is incomplete.")}</p></div>
          <div className="trust-score"><strong>{number(enterprise.readiness_score)}</strong><span>{zh ? "企业准备度" : "enterprise readiness"}</span></div>
        </section>

        <MetricStrip items={[
          { label: zh ? "审计导出" : "Audit export", value: compliance.audit_export_ready ? "ready" : "blocked", tone: "pass" },
          { label: zh ? "公开发布" : "Public publish", value: trust.publish_enabled ? "enabled" : "blocked", tone: "fail" },
          { label: zh ? "信任制品" : "Trust artifacts", value: artifacts.length, tone: "info" },
          { label: zh ? "缺失契约" : "Missing contracts", value: missingContracts.length, tone: "warn" }
        ]} />

        <div className="content-grid two-one">
          <Section title={zh ? "信任制品" : "Trust artifacts"} description={zh ? "可进入客户报告的安全证据" : "Customer-safe evidence eligible for reports"}>
            <div className="artifact-grid trust-artifacts">{artifacts.map((artifact, index) => <article key={`${string(artifact.artifact)}-${index}`}><FileCheck2 size={17} /><div><strong>{string(artifact.artifact)}</strong><span>{string(artifact.status)}</span></div><StatusBadge value={string(artifact.status)} /></article>)}</div>
          </Section>
          <Section title={zh ? "发布阻塞" : "Publish blockers"} description={zh ? "Trust Center 对外发布前必须补齐" : "Required before Trust Center publication"}>
            <div className="blocker-list">{blockers.map((blocker, index) => <div key={`${string(blocker)}-${index}`}><LockKeyhole size={16} /><span>{string(blocker)}</span></div>)}</div>
          </Section>
        </div>

        <Section title={zh ? "审计与契约" : "Audit and contracts"} description={zh ? "保持来源、租户范围和判定权可追踪" : "Keep source, tenant scope, and decision authority traceable"}>
          <div className="audit-grid">
            <article><Archive size={20} /><div><span>{zh ? "审计包" : "Audit bundle"}</span><strong>{compliance.audit_export_ready ? "ready" : "not ready"}</strong><p>{string(record(trust.audit_log_policy).retention_policy, "tenant-scoped / redacted")}</p></div></article>
            <article><ShieldCheck size={20} /><div><span>{zh ? "判定权" : "Decision authority"}</span><strong>{zh ? "评测与决策服务" : "Evaluation authority"}</strong><p>{string(provenance.release_decision)}</p></div></article>
          </div>
          <EvidenceDetails summary={zh ? "查看缺失契约和企业阻塞项" : "View missing contracts and enterprise blockers"}><pre>{JSON.stringify({ missing_contracts: missingContracts, enterprise_blockers: enterprise.blockers, a1_a2_compatibility: enterprise.a1_a2_compatibility_notes }, null, 2)}</pre></EvidenceDetails>
        </Section>
      </>
    );
  }}</DataBoundary>;
}
