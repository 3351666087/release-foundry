"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, CircleDashed, FolderKanban } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function ProjectsPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  return <DataBoundary>{(model) => {
    const consoleModel = record(model.raw.product_console);
    const project = record(consoleModel.project_console);
    const onboarding = record(consoleModel.onboarding);
    const projectSummary = record(project.summary);
    const steps = array(onboarding.steps).map(record);
    const tenant = record(consoleModel.tenant_scope);
    return (
      <>
        <PageHeader
          eyebrow="WORKSPACE / PROJECTS"
          title={zh ? "项目工作区" : "Project workspace"}
          summary={zh ? "把 Agent、数据集、运行和发布状态放进同一个项目边界。" : "Keep agents, datasets, runs, and release state inside one project boundary."}
          actions={<button type="button" className="command-button" disabled title={zh ? "等待真实 hosted auth" : "Requires hosted auth"}>+ {zh ? "新建项目" : "New project"}</button>}
        />

        <section className="project-spotlight">
          <div className="project-symbol"><FolderKanban size={28} /></div>
          <div>
            <span className="eyebrow">{string(tenant.organization_id, "org-local")}</span>
            <h2>{string(tenant.project_id, "project-local")}</h2>
            <p>{zh ? "已接入 A1 执行证据和 A2 判定结果的演示项目。" : "Demo project connected to A1 execution evidence and A2 decisions."}</p>
          </div>
          <StatusBadge value={string(project.status)} />
          <Link className="signal-action light" href="/runs">{zh ? "查看运行" : "View runs"}<ArrowRight size={17} /></Link>
        </section>

        <MetricStrip items={[
          { label: zh ? "运行" : "Runs", value: number(projectSummary.run_count, model.summary.totalRuns), tone: "info" },
          { label: zh ? "案例" : "Cases", value: number(projectSummary.case_count, model.summary.totalCases), tone: "neutral" },
          { label: zh ? "失败" : "Failed", value: number(projectSummary.failed_case_count, model.summary.failed), tone: "fail" },
          { label: zh ? "引导完成度" : "Onboarding", value: `${number(onboarding.completion_rate)}%`, tone: "pass" }
        ]} />

        <div className="content-grid equal">
          <Section title={zh ? "接入进度" : "Onboarding"} description={zh ? "项目进入可评测状态所需的证据" : "Evidence required before the project is evaluation-ready"}>
            <div className="step-list">
              {steps.map((step, index) => {
                const complete = string(step.status).includes("complete");
                return <div key={`${string(step.id, string(step.label))}-${index}`}>{complete ? <CheckCircle2 size={18} /> : <CircleDashed size={18} />}<span><strong>{string(step.label)}</strong><small>{string(step.evidence, string(step.status))}</small></span><StatusBadge value={string(step.status)} /></div>;
              })}
            </div>
          </Section>
          <Section title={zh ? "项目边界" : "Project boundary"} description={zh ? "当前仅显示可公开的租户与环境元数据" : "Only public-safe tenant and environment metadata is shown"}>
            <dl className="definition-list">
              <div><dt>Organization</dt><dd>{string(tenant.organization_id)}</dd></div>
              <div><dt>Workspace</dt><dd>{string(tenant.workspace_id)}</dd></div>
              <div><dt>Project</dt><dd>{string(tenant.project_id)}</dd></div>
              <div><dt>Environment</dt><dd>{string(tenant.environment_id)}</dd></div>
              <div><dt>Source</dt><dd>{model.source}</dd></div>
            </dl>
          </Section>
        </div>
      </>
    );
  }}</DataBoundary>;
}
