"use client";

import Link from "next/link";
import { ArrowRight, CircleAlert, ShieldCheck } from "lucide-react";

import { array, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, MetricStrip, PageHeader, Section, StatusBadge, formatDate, formatDuration } from "../ui";

export function OverviewPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";

  return <DataBoundary>{(model) => {
    const spine = record(model.raw.a1_a2_evidence_spine);
    const releaseDecision = string(spine.release_decision, "block");
    const stages = array(spine.stages).map(record);
    const failureCounts = new Map<string, number>();
    for (const item of model.cases.filter((entry) => !entry.passed)) {
      failureCounts.set(item.failureClass, (failureCounts.get(item.failureClass) || 0) + 1);
    }
    const failures = [...failureCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);

    return (
      <>
        <PageHeader
          eyebrow="A3 / RELEASE INTELLIGENCE"
          title={zh ? "发布总览" : "Release overview"}
          summary={zh ? "先看发布结论，再进入案例和证据。" : "Start with the release decision, then inspect cases and evidence."}
          meta={<><span>{model.sourceLabel}</span><strong>{model.summary.lastRunId}</strong></>}
        />

        <section className="release-signal">
          <div className="release-signal-copy">
            <span className="eyebrow">{zh ? "当前发布信号" : "CURRENT RELEASE SIGNAL"}</span>
            <StatusBadge value={releaseDecision} tone={releaseDecision.includes("block") ? "fail" : "pass"} />
            <h2>{zh ? `${model.summary.failed} 个案例需要处理` : `${model.summary.failed} cases need attention`}</h2>
            <p>{zh ? "A2 仍拥有发布判定权；A3 只展示阻塞原因和人工审核入口。" : "A2 remains the release authority; A3 presents blockers and human review."}</p>
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
          { label: zh ? "Trace 完整率" : "Trace complete", value: `${model.summary.traceCompleteness}%`, tone: "pass", detail: "A1 evidence" },
          { label: zh ? "媒体案例" : "Media cases", value: model.summary.mediaEvidenceCases, tone: "cobalt", detail: "image / audio / file" }
        ]} />

        <div className="content-grid two-one">
          <Section title={zh ? "最近运行" : "Recent runs"} description={zh ? "来自 A1 RunResult 的执行批次" : "Execution batches from A1 RunResult"} action={<Link className="text-link" href="/runs">{zh ? "全部运行" : "All runs"}<ArrowRight size={14} /></Link>}>
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

          <Section title={zh ? "失败集中点" : "Failure concentration"} description={zh ? "按 A2 主要失败分类" : "By A2 primary failure class"}>
            <div className="rank-list">
              {failures.map(([name, count], index) => <Link href={`/runs?failure=${encodeURIComponent(name)}`} key={name}><span>{String(index + 1).padStart(2, "0")}</span><strong>{name}</strong><b>{count}</b></Link>)}
            </div>
          </Section>
        </div>

        <Section title={zh ? "证据链" : "Evidence spine"} description={zh ? "A1 采集，A2 判定，A3 运营" : "A1 captures, A2 decides, A3 operates"}>
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
