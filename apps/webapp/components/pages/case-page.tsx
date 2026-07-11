"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bot, Braces, MessageSquareText, Wrench } from "lucide-react";

import { array, pretty, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, EmptyState, EvidenceDetails, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function CasePage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [requestedCase, setRequestedCase] = useState("");
  useEffect(() => setRequestedCase(new URLSearchParams(window.location.search).get("case_id") || ""), []);

  return <DataBoundary>{(model) => {
    const item = model.cases.find((candidate) => candidate.caseId === requestedCase)
      || model.cases.find((candidate) => !candidate.passed)
      || model.cases[0];
    if (!item) return <EmptyState title={zh ? "没有案例" : "No cases"} detail={zh ? "当前数据源没有可检查的案例。" : "The current source has no inspectable cases."} />;
    const expectedSummary = string(item.expected.summary, array(item.expected.expected_responses)[0] ? string(array(item.expected.expected_responses)[0]) : "No expected summary.");
    const actualResponse = string(item.actual.final_response, "No final response.");
    const timeline = item.traceEvents.length ? item.traceEvents : item.observations;

    return (
      <>
        <PageHeader
          eyebrow={`CASE / ${item.scenarioId}`}
          title={item.title}
          summary={item.failureSummary}
          meta={<><span>{item.caseId}</span><StatusBadge value={item.passed ? "passed" : "failed"} /></>}
          actions={<Link className="command-button" href="/runs"><ArrowLeft size={15} />{zh ? "返回运行列表" : "Back to runs"}</Link>}
        />

        <MetricStrip items={[
          { label: zh ? "分数" : "Score", value: item.score, tone: item.passed ? "pass" : "fail", detail: "A2 GradeResult" },
          { label: zh ? "严重程度" : "Severity", value: item.severity, tone: "warn" },
          { label: zh ? "Trace 事件" : "Trace events", value: timeline.length, tone: "info", detail: "A1 evidence" },
          { label: "Tool calls", value: item.toolCalls.length, tone: "cobalt" }
        ]} />

        <div className="comparison-grid">
          <section className="comparison-panel expected-panel">
            <header><span>01</span><h2>{zh ? "预期结果" : "Expected"}</h2></header>
            <p>{expectedSummary}</p>
            <div className="point-list">{array(item.expected.final_response_points).map((point, index) => <span key={`${string(point)}-${index}`}>{string(point)}</span>)}</div>
            <EvidenceDetails summary={zh ? "查看完整预期契约" : "View full expected contract"}><pre>{pretty(item.expected)}</pre></EvidenceDetails>
          </section>
          <section className="comparison-panel actual-panel">
            <header><span>02</span><h2>{zh ? "实际结果" : "Actual"}</h2></header>
            <p>{actualResponse}</p>
            <div className="actual-meta"><StatusBadge value={item.status} /><span>{item.failureClass}</span></div>
            <EvidenceDetails summary={zh ? "查看完整实际输出" : "View full actual output"}><pre>{pretty(item.actual)}</pre></EvidenceDetails>
          </section>
        </div>

        <div className="content-grid two-one">
          <Section title={zh ? "Trace 时间线" : "Trace timeline"} description={zh ? "A1 记录的消息、工具和执行事件" : "Messages, tools, and execution events captured by A1"}>
            <div className="trace-list">
              {timeline.map((event, index) => {
                const kind = string(event.event_type, string(event.type, "event"));
                const Icon = kind.includes("tool") ? Wrench : kind.includes("agent") ? Bot : MessageSquareText;
                return <article key={`${kind}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><Icon size={17} /><div><strong>{kind}</strong><p>{string(event.content, string(event.name, string(event.status)))}</p></div><small>{string(event.role, string(event.timestamp, "A1"))}</small></article>;
              })}
            </div>
          </Section>

          <Section title="Tool calls" description={zh ? "调用名称、参数与证据" : "Names, arguments, and evidence"}>
            {item.toolCalls.length ? <div className="tool-call-list">{item.toolCalls.map((call, index) => <article key={`${string(call.tool, string(call.name))}-${index}`}><Wrench size={16} /><div><strong>{string(call.tool, string(call.name, "tool"))}</strong><code>{pretty(call.args || call.arguments)}</code></div></article>)}</div> : <EmptyState title={zh ? "没有工具调用" : "No tool calls"} detail={zh ? "这个案例只包含文本执行证据。" : "This case contains text-only execution evidence."} />}
          </Section>
        </div>

        <Section title={zh ? "Judge 判定" : "Judge decisions"} description={zh ? "A2 的各评测模式与失败分析" : "A2 judge modes and failure analysis"}>
          <div className="judge-grid">
            {item.judgeResults.map((judge, index) => {
              const analysis = record(judge.failure_analysis);
              return <article key={`${string(judge.judge_mode)}-${index}`}><header><Braces size={17} /><strong>{string(judge.judge_mode)}</strong><StatusBadge value={string(judge.passed) === "true" ? "passed" : string(analysis.primary_failure_class)} /></header><b>{string(judge.score)} / {string(judge.max_score, "100")}</b><p>{string(analysis.summary)}</p><EvidenceDetails summary={zh ? "Rubric 与证据" : "Rubric and evidence"}><pre>{pretty({ rubric_scores: judge.rubric_scores, evidence: judge.evidence, remediation: analysis.remediation })}</pre></EvidenceDetails></article>;
            })}
          </div>
        </Section>
      </>
    );
  }}</DataBoundary>;
}
