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
          eyebrow="A3 / RELEASE INTELLIGENCE"
          title={zh ? "发布总览" : "Release overview"}
          summary={zh ? "先核验 A2 决策账本，再查看案例、证据和人工审核。" : "Verify the A2 Decision Ledger before inspecting cases, evidence, and review."}
          meta={<><span>{model.sourceLabel}</span><strong>{model.summary.lastRunId}</strong></>}
        />

        <section className="release-signal">
          <div className="release-signal-copy">
            <span className="eyebrow">{zh ? "A2 可信发布信号" : "A2 TRUSTED RELEASE SIGNAL"}</span>
            <StatusBadge value={releaseSignal} tone={releaseTone} />
            <h2>{authority.releaseReady
              ? (zh ? "决策账本已核验，可以进入发布流程" : "Verified ledger permits the release workflow")
              : (zh ? "当前不得发布，需要先处理阻断项" : "Release is not authorized; resolve the blockers first")}</h2>
            <p>{zh
              ? `账本完整性：${authority.integrityVerified ? "已核验" : "未通过"}；A2 决策：${authority.upstreamDecision}；原因：${authority.reasonCode}。`
              : `Ledger integrity: ${authority.integrityVerified ? "verified" : "not verified"}; A2 decision: ${authority.upstreamDecision}; reason: ${authority.reasonCode}.`}</p>
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
