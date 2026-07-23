"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bot, Braces, CheckCircle2, Cpu, MessageSquareText, ReceiptText, SearchCheck, ShieldCheck, Wrench, XCircle } from "lucide-react";

import { array, number, pretty, record, string } from "@/lib/api";
import { failureClassLabel, judgeLabel, rubricLabel, traceEventLabel } from "@/lib/evidence-labels";
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
    const actualMetadata = record(item.actual.metadata);
    const modelName = string(actualMetadata.model, "local model");
    const firstToolCall = record(item.toolCalls[0]);
    const toolArguments = record(firstToolCall.arguments || firstToolCall.args);
    const toolOutput = record(firstToolCall.output);
    const latencySeconds = Math.max(1, Math.round(number(item.actual.latency_ms) / 1000));
    const userRequest = string(record(timeline[0]).content, "请处理这笔模拟退款。仅允许沙盒操作。");

    return (
      <>
        <PageHeader
          eyebrow={`CASE / ${item.scenarioId}`}
          title={item.title}
          summary={item.failureSummary}
          meta={<><span>{item.caseId}</span><StatusBadge value={item.passed ? "passed" : "failed"} /></>}
          actions={<Link className="command-button" href={{ pathname: "/runs", query: { source: model.source } }}><ArrowLeft size={15} />{zh ? "返回运行列表" : "Back to runs"}</Link>}
        />

        {model.source === "refund-demo" && (
          <section className="demo-story" aria-label={zh ? "退款案例讲解" : "Refund demo explanation"}>
            <div className="demo-story-lead">
              <span><SearchCheck size={21} aria-hidden="true" /></span>
              <div>
                <small>{zh ? "一条案例看懂证据链" : "ONE CASE, ONE EVIDENCE CHAIN"}</small>
                <h2>{zh ? "问题不在回答好不好听，而在退款根本没有被执行" : "The answer sounds right, but the refund never ran"}</h2>
                <p>{zh ? "顺着下面三步讲：A1 记录执行过程，A2 根据规则判失败，A3 把证据和发布阻断展示给人看。" : "Follow three steps: A1 captures execution, A2 grades it, and A3 presents the evidence and release block."}</p>
              </div>
            </div>
            <ol>
              <li><span>01</span><strong>A1 · Trace</strong><p>{zh ? "没有发现 refund_order 工具调用。" : "No refund_order call was observed."}</p></li>
              <li><span>02</span><strong>A2 · Judge</strong><p>{zh ? "判定缺少必需工具，得分 42，结果失败。" : "Missing required tool: score 42, failed."}</p></li>
              <li><span>03</span><strong>A3 · Triage</strong><p>{zh ? "展示差异并阻止未经证实的退款版本发布。" : "Show the mismatch and block an unverified release."}</p></li>
            </ol>
          </section>
        )}

        {model.source === "live-refund-demo" && (
          <section className="live-demo-proof" aria-label={zh ? "7B 大模型真实运行证据" : "7B real-model run evidence"}>
            <header className="live-demo-proof-hero">
              <span className="live-proof-icon"><Cpu size={26} strokeWidth={1.8} aria-hidden="true" /></span>
              <div>
                <small>{zh ? "真实运行证据 / 不是预先写好的截图" : "REAL RUN EVIDENCE / NOT A PREWRITTEN SCREENSHOT"}</small>
                <h2>{zh ? `${modelName} 完成了一次退款 Agent 测试` : `${modelName} completed a refund Agent test`}</h2>
                <p>{zh ? "模型在 Docker 中真实推理，自己选择工具；退款工具只操作模拟订单，不连接真实资金。" : "The model performed real inference in Docker and selected its tool. The tool only touches a synthetic order."}</p>
              </div>
              <div className="live-proof-verdict" data-status={item.passed ? "passed" : "failed"}>
                {item.passed ? <CheckCircle2 size={22} aria-hidden="true" /> : <XCircle size={22} aria-hidden="true" />}
                <span><strong>{item.passed ? "PASS" : "FAIL"}</strong><small>{zh ? `得分 ${item.score}` : `Score ${item.score}`}</small></span>
              </div>
            </header>

            <div className="live-proof-facts">
              <div><span>{zh ? "真实模型" : "Model"}</span><strong>{modelName}</strong><small>{zh ? "Docker Ollama 本地推理" : "Docker Ollama inference"}</small></div>
              <div><span>{zh ? "本次运行编号" : "Run ID"}</span><strong>{item.runId}</strong><small>{zh ? "可追踪到同一次运行" : "Binds the same run"}</small></div>
              <div><span>{zh ? "推理用时" : "Inference time"}</span><strong>{latencySeconds} {zh ? "秒" : "sec"}</strong><small>{zh ? "真实等待，不是静态结果" : "Observed runtime latency"}</small></div>
              <div><span>{zh ? "真实资金变化" : "Real payment mutation"}</span><strong>{toolOutput.external_payment_mutated === true ? (zh ? "是" : "Yes") : (zh ? "没有" : "None")}</strong><small>{zh ? "全程沙盒" : "Sandbox only"}</small></div>
            </div>

            <ol className="live-proof-flow">
              <li>
                <span>01</span><MessageSquareText size={20} aria-hidden="true" />
                <div><small>{zh ? "用户提出任务" : "User request"}</small><strong>{zh ? "请求退款" : "Request a refund"}</strong><p>{userRequest}</p></div>
              </li>
              <li>
                <span>02</span><Bot size={20} aria-hidden="true" />
                <div><small>{zh ? "大模型作出决定" : "Model decision"}</small><strong>{zh ? "需要调用退款工具" : "Call the refund tool"}</strong><p>{zh ? `${modelName} 读取请求后选择了工具，而不是只回复一段文字。` : `${modelName} selected a tool after reading the request.`}</p></div>
              </li>
              <li>
                <span>03</span><Wrench size={20} aria-hidden="true" />
                <div><small>{zh ? "工具真实执行" : "Tool execution"}</small><strong>{string(firstToolCall.name, "refund_order_sandbox")}</strong><p>{zh ? `订单 ${string(toolArguments.order_id)}，金额 ${string(toolArguments.amount)} 元。` : `Order ${string(toolArguments.order_id)}, amount ${string(toolArguments.amount)}.`}</p></div>
              </li>
              <li>
                <span>04</span><ReceiptText size={20} aria-hidden="true" />
                <div><small>{zh ? "收到沙盒回执" : "Sandbox receipt"}</small><strong>{string(toolOutput.status, "approved").toUpperCase()}</strong><p>{zh ? "工具确认模拟退款成功，同时证明真实支付没有变化。" : "The tool approved the simulation and recorded no real payment mutation."}</p></div>
              </li>
              <li>
                <span>05</span><ShieldCheck size={20} aria-hidden="true" />
                <div><small>{zh ? "评测系统验收" : "Evaluation"}</small><strong>{item.judgeResults.length} {zh ? "个 Judge，得分" : "Judges, score"} {item.score}</strong><p>{zh ? "工具、参数、安全边界和最终回复全部通过检查。" : "Tool, arguments, safety boundary, and response passed review."}</p></div>
              </li>
            </ol>

            <div className="live-proof-answer">
              <span><Bot size={18} aria-hidden="true" />{zh ? "模型最后说了什么" : "Final model response"}</span>
              <blockquote>{actualResponse}</blockquote>
              <p><ShieldCheck size={15} aria-hidden="true" />{zh ? "真实的是模型推理、工具调用和评测记录；模拟的是订单和退款资金。" : "The inference, tool call, and evaluation are real; the order and payment are synthetic."}</p>
            </div>
          </section>
        )}

        <MetricStrip items={[
          { label: zh ? "分数" : "Score", value: item.score, tone: item.passed ? "pass" : "fail", detail: zh ? "评测结论" : "evaluation result" },
          { label: zh ? "严重程度" : "Severity", value: item.severity, tone: "warn" },
          { label: zh ? "Trace 事件" : "Trace events", value: timeline.length, tone: "info", detail: zh ? "执行证据" : "execution evidence" },
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
            <div className="actual-meta"><StatusBadge value={item.status} /><span title={item.failureClass}>{failureClassLabel(item.failureClass, zh)}</span></div>
            <EvidenceDetails summary={zh ? "查看完整实际输出" : "View full actual output"}><pre>{pretty(item.actual)}</pre></EvidenceDetails>
          </section>
        </div>

        <div className="content-grid two-one">
          <Section title={zh ? "Trace 时间线" : "Trace timeline"} description={zh ? "运行平台记录的消息、工具和执行事件" : "Messages, tools, and execution events captured by the runtime"}>
            <div className="trace-list">
              {timeline.map((event, index) => {
                const kind = string(event.event_type, string(event.type, "event"));
                const Icon = kind.includes("tool") ? Wrench : kind.includes("agent") ? Bot : MessageSquareText;
                const observation = record(event.observation);
                return <article key={`${kind}-${index}`} data-status={string(event.status, string(observation.status, "ok"))}><span>{String(index + 1).padStart(2, "0")}</span><Icon size={17} /><div><strong>{traceEventLabel(kind, zh)}</strong><code>{kind}</code><p>{string(event.content, string(observation.text, string(event.name, string(event.status))))}</p></div><small>{string(event.role, string(event.timestamp, zh ? "运行平台" : "runtime"))}</small></article>;
              })}
            </div>
          </Section>

          <Section title={zh ? "实际工具调用" : "Actual tool calls"} description={zh ? "这里只展示 Agent 真正执行过的工具" : "Only tools actually executed by the agent appear here"}>
            {item.toolCalls.length ? <div className="tool-call-list">{item.toolCalls.map((call, index) => <article key={`${string(call.tool, string(call.name))}-${index}`}><Wrench size={16} /><div><strong>{string(call.tool, string(call.name, "tool"))}</strong><code>{pretty(call.args || call.arguments)}</code></div></article>)}</div> : <EmptyState title={zh ? "没有工具调用" : "No tool calls"} detail={zh ? "这个案例只包含文本执行证据。" : "This case contains text-only execution evidence."} />}
            {!item.toolCalls.length && array(item.expected.tool_calls).length > 0 && (
              <div className="missing-tool-proof"><XCircle size={18} aria-hidden="true" /><div><strong>{zh ? "这正是失败证据" : "This absence is the failure evidence"}</strong><p>{zh ? `规则要求 ${string(record(array(item.expected.tool_calls)[0]).name)}，实际调用数量为 0。` : `The contract required ${string(record(array(item.expected.tool_calls)[0]).name)}, but the actual call count is 0.`}</p></div></div>
            )}
          </Section>
        </div>

        <Section title={zh ? "Judge 判定" : "Judge decisions"} description={zh ? "评测服务的各评测模式与失败分析" : "Evaluation modes and failure analysis"}>
          <div className="judge-grid">
            {item.judgeResults.map((judge, index) => {
              const analysis = record(judge.failure_analysis);
              const label = judgeLabel(judge.judge_mode, zh);
              const passed = string(judge.passed) === "true";
              return <article key={`${label.id}-${index}`}>
                <header>{passed ? <CheckCircle2 size={17} /> : <Braces size={17} />}<div className="judge-title"><strong>{label.title}</strong><code>{label.id}</code></div><StatusBadge value={passed ? "passed" : string(analysis.primary_failure_class)} /></header>
                <b>{string(judge.score)} / {string(judge.max_score, "100")}</b>
                <p className="judge-purpose">{label.detail}</p>
                <p>{string(analysis.summary)}</p>
                <EvidenceDetails summary={zh ? "查看评分细项与修复建议" : "View rubric and remediation"}>
                  <div className="rubric-list">
                    {array(judge.rubric_scores).map((value, rubricIndex) => {
                      const rubric = record(value);
                      return <div key={`${string(rubric.class)}-${rubricIndex}`}><span><strong>{rubricLabel(rubric.class, zh)}</strong><code>{string(rubric.class)}</code></span><b>{Math.round(Number(rubric.score) * 100)}%</b><p>{string(rubric.rationale)}</p></div>;
                    })}
                  </div>
                  <pre>{pretty({ evidence: judge.evidence, remediation: analysis.remediation })}</pre>
                </EvidenceDetails>
              </article>;
            })}
          </div>
        </Section>
      </>
    );
  }}</DataBoundary>;
}
