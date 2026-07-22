"use client";

import Link from "next/link";
import { Activity, ArrowRight, CircleAlert, FolderKanban, PackageCheck, ShieldCheck, UserCheck } from "lucide-react";

import { array, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, MetricStrip, PageHeader, Section, StatusBadge, formatDate, formatDuration } from "../ui";

export function OverviewPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";

  return <DataBoundary>{(model) => {
    const spine = record(model.raw.a1_a2_evidence_spine);
    const authority = model.trustedReleaseAuthority;
    const releaseSignal = authority.releaseReady ? "release_ready" : authority.status;
    const releaseTone = authority.releaseReady
      ? "pass"
      : authority.status === "blocked" || authority.status === "integrity_invalid"
        ? "fail"
        : "warn";
    const stages = array(spine.stages).map(record);
    const failureCounts = new Map<string, number>();
    for (const item of model.cases.filter((entry) => !entry.passed)) {
      failureCounts.set(item.failureClass, (failureCounts.get(item.failureClass) || 0) + 1);
    }
    const failures = [...failureCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);

    return (
      <>
        <PageHeader
          eyebrow="RELEASE INTELLIGENCE"
          title={zh ? "发布总览" : "Release overview"}
          summary={zh ? "先核验权威决策账本，再查看案例、证据和人工审核。" : "Verify the authoritative decision ledger before inspecting cases, evidence, and review."}
          meta={<><span>{model.sourceLabel}</span><strong>{model.summary.lastRunId}</strong></>}
        />

        <section className="getting-started" aria-labelledby="getting-started-title">
          <header className="getting-started-header">
            <div>
              <span className="eyebrow">{zh ? "首次进入" : "FIRST SESSION"}</span>
              <h2 id="getting-started-title">{zh ? "从运行到发布，按这条线查看" : "Follow the path from run to release"}</h2>
              <p>{zh ? "每一步都对应一类证据，点击入口即可进入对应模块。" : "Each step has its own evidence surface. Open a step to inspect it."}</p>
            </div>
            <span className="getting-started-count">{zh ? "4 个入口" : "4 steps"}</span>
          </header>
          <ol className="workflow-steps">
            {[
              { href: "/projects", icon: FolderKanban, number: "01", zh: "准备项目", en: "Set up project", detailZh: "项目与数据", detailEn: "Project & data" },
              { href: "/runs", icon: Activity, number: "02", zh: "运行 Agent", en: "Run the agent", detailZh: "运行与 Trace", detailEn: "Run & trace" },
              { href: "/review", icon: UserCheck, number: "03", zh: "检查质量", en: "Review quality", detailZh: "评分与失败", detailEn: "Scores & failures" },
              { href: "/delivery?source=a3-golden-path", icon: PackageCheck, number: "04", zh: "决定发布", en: "Decide release", detailZh: "门禁与审计", detailEn: "Gate & audit" }
            ].map((step) => {
              const StepIcon = step.icon;
              return (
                <li key={step.href}>
                  <Link href={step.href} className="workflow-step">
                    <span className="workflow-step-number">{step.number}</span>
                    <span className="workflow-step-icon"><StepIcon size={18} strokeWidth={1.9} aria-hidden="true" /></span>
                    <span className="workflow-step-copy">
                      <strong>{zh ? step.zh : step.en}</strong>
                      <small>{zh ? step.detailZh : step.detailEn}</small>
                    </span>
                    <ArrowRight className="workflow-step-arrow" size={17} aria-hidden="true" />
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>

        <section className="release-signal">
          <div className="release-signal-copy">
            <span className="eyebrow">{zh ? "可信发布信号" : "TRUSTED RELEASE SIGNAL"}</span>
            <StatusBadge value={releaseSignal} tone={releaseTone} />
            <h2>{authority.releaseReady
              ? (zh ? "决策账本已核验，可以进入发布流程" : "Verified ledger permits the release workflow")
              : (zh ? "当前不得发布，需要先处理阻断项" : "Release is not authorized; resolve the blockers first")}</h2>
            <p>{zh
              ? `账本完整性：${authority.integrityVerified ? "已核验" : "未通过"}；权威决策：${authority.upstreamDecision}；原因：${authority.reasonCode}。`
              : `Ledger integrity: ${authority.integrityVerified ? "verified" : "not verified"}; authoritative decision: ${authority.upstreamDecision}; reason: ${authority.reasonCode}.`}</p>
            <Link className="signal-action" href="/review">{zh ? "进入人工审核" : "Open review"}<ArrowRight size={17} /></Link>
          </div>
          <div className="release-signal-aside">
            <strong>{model.summary.passRate}%</strong><span>{zh ? "当前通过率" : "current pass rate"}</span>
            <strong>{model.summary.avgScore}</strong><span>{zh ? "平均分" : "average score"}</span>
          </div>
        </section>

        <MetricStrip items={[
          { label: zh ? "运行" : "Runs", value: model.summary.totalRuns, tone: "info", detail: model.summary.lastRunId },
          { label: zh ? "案例" : "Cases", value: model.summary.totalCases, tone: "neutral", detail: `${model.summary.passed} pass / ${model.summary.failed} fail` },
          { label: zh ? "Trace 完整率" : "Trace complete", value: `${model.summary.traceCompleteness}%`, tone: "pass", detail: zh ? "执行证据" : "execution evidence" },
          { label: zh ? "媒体案例" : "Media cases", value: model.summary.mediaEvidenceCases, tone: "cobalt", detail: "image / audio / file" }
        ]} />

        <div className="content-grid two-one">
          <Section title={zh ? "最近运行" : "Recent runs"} description={zh ? "来自运行服务的执行批次" : "Execution batches from the runtime service"} action={<Link className="text-link" href="/runs">{zh ? "全部运行" : "All runs"}<ArrowRight size={14} /></Link>}>
            <DataTable headers={[zh ? "运行 ID" : "Run ID", zh ? "状态" : "Status", zh ? "案例" : "Cases", zh ? "耗时" : "Duration", zh ? "开始时间" : "Started"]} label="Recent runs">
              {model.runs.map((run) => (
                <tr key={run.runId}>
                  <td><strong>{run.runId}</strong><small>{run.datasetId}</small></td>
                  <td><StatusBadge value={run.status} /></td>
                  <td>{run.totalCases}</td>
                  <td>{formatDuration(run.durationMs)}</td>
                  <td>{formatDate(run.startedAt)}</td>
                </tr>
              ))}
            </DataTable>
          </Section>

          <Section title={zh ? "失败集中点" : "Failure concentration"} description={zh ? "按权威评测的主要失败分类" : "By authoritative primary failure class"}>
            <div className="rank-list">
              {failures.map(([name, count], index) => <Link href={`/runs?failure=${encodeURIComponent(name)}`} key={name}><span>{String(index + 1).padStart(2, "0")}</span><strong>{name}</strong><b>{count}</b></Link>)}
            </div>
          </Section>
        </div>

        <Section title={zh ? "证据链" : "Evidence spine"} description={zh ? "执行取证，独立评测，人工发布" : "Capture evidence, evaluate independently, release with human control"}>
          <div className="spine-grid">
            {stages.map((stage, index) => (
              <article className="spine-stage" key={`${string(stage.stage)}-${index}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <ShieldCheck size={18} aria-hidden="true" />
                <h3>{string(stage.label, string(stage.stage))}</h3>
                <strong>{string(stage.status)}</strong>
                <p>{string(stage.summary, string(stage.owner))}</p>
              </article>
            ))}
            {!stages.length && <div className="inline-alert"><CircleAlert size={18} />{zh ? "证据链尚未加载" : "Evidence spine is not loaded"}</div>}
          </div>
        </Section>
      </>
    );
  }}</DataBoundary>;
}
