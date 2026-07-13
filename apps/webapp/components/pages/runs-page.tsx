"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Search } from "lucide-react";

import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, EmptyState, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function RunsPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const requestedFailure = new URLSearchParams(window.location.search).get("failure");
    if (requestedFailure) setQuery(requestedFailure);
  }, []);

  useEffect(() => setPage(1), [query, status]);

  return <DataBoundary>{(model) => {
    const filtered = model.cases.filter((item) => {
      const matchesStatus = status === "all" || (status === "passed" ? item.passed : !item.passed);
      const haystack = `${item.caseId} ${item.scenarioId} ${item.title} ${item.family} ${item.failureClass}`.toLowerCase();
      return matchesStatus && haystack.includes(query.toLowerCase());
    });
    const pageSize = 10;
    const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
    const visibleCases = filtered.slice((page - 1) * pageSize, page * pageSize);

    return (
      <>
        <PageHeader
          eyebrow="EVALUATE / RUNS"
          title={zh ? "运行与案例" : "Runs and cases"}
          summary={zh ? "先筛出失败案例，再进入 Expected、Actual 和 Trace。" : "Find failed cases first, then inspect Expected, Actual, and Trace."}
          meta={<><span>{model.summary.lastRunId}</span><strong>{filtered.length} / {model.summary.totalCases}</strong></>}
        />

        <MetricStrip items={[
          { label: zh ? "通过" : "Passed", value: model.summary.passed, tone: "pass" },
          { label: zh ? "失败" : "Failed", value: model.summary.failed, tone: "fail" },
          { label: zh ? "通过率" : "Pass rate", value: `${model.summary.passRate}%`, tone: "warn" },
          { label: zh ? "平均分" : "Average score", value: model.summary.avgScore, tone: "cobalt" }
        ]} />

        <Section title={zh ? "案例队列" : "Case queue"} description={zh ? "执行记录与权威评测结果的联合视图" : "Joined execution and authoritative decision view"}>
          <div className="filter-bar">
            <label className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索案例、场景或失败分类" : "Search case, scenario, or failure class"} /></label>
            <div className="segmented-control" role="group" aria-label="Case status">
              {[{ id: "all", label: zh ? "全部" : "All" }, { id: "failed", label: zh ? "失败" : "Failed" }, { id: "passed", label: zh ? "通过" : "Passed" }].map((item) => <button type="button" aria-pressed={status === item.id} onClick={() => setStatus(item.id)} key={item.id}>{item.label}</button>)}
            </div>
          </div>
          {filtered.length ? (
            <>
              <DataTable headers={[zh ? "案例" : "Case", zh ? "场景" : "Scenario", zh ? "状态" : "Status", zh ? "分数" : "Score", zh ? "失败分类" : "Failure class", ""]} label="Cases">
                {visibleCases.map((item) => (
                  <tr key={item.caseId} className={!item.passed ? "risk-row" : ""}>
                    <td><strong>{item.caseId}</strong><small>{item.runId}</small></td>
                    <td><strong>{item.title}</strong><small>{item.family} / {item.scenarioId}</small></td>
                    <td><StatusBadge value={item.passed ? "passed" : "failed"} /></td>
                    <td><b className="score-value">{item.score}</b></td>
                    <td>{item.failureClass}</td>
                    <td><Link className="row-action" href={{ pathname: "/case", query: { case_id: item.caseId } }} aria-label={`${zh ? "查看" : "Open"} ${item.caseId}`}><ArrowRight size={16} /></Link></td>
                  </tr>
                ))}
              </DataTable>
              <div className="table-pagination">
                <span>{zh ? `第 ${page} / ${pageCount} 页 · 共 ${filtered.length} 条` : `Page ${page} of ${pageCount} · ${filtered.length} items`}</span>
                <div>
                  <button type="button" aria-label={zh ? "上一页" : "Previous page"} disabled={page === 1} onClick={() => setPage((current) => Math.max(1, current - 1))}><ArrowLeft size={15} /></button>
                  <button type="button" aria-label={zh ? "下一页" : "Next page"} disabled={page === pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}><ArrowRight size={15} /></button>
                </div>
              </div>
            </>
          ) : <EmptyState title={zh ? "没有符合条件的案例" : "No matching cases"} detail={zh ? "请更换关键词或状态筛选。" : "Try another search term or status filter."} />}
        </Section>
      </>
    );
  }}</DataBoundary>;
}
