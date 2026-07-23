"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bot, Braces, CheckCircle2, Cpu, MessageSquareText, ReceiptText, SearchCheck, ShieldCheck, Wrench, XCircle } from "lucide-react";

import { array, number, pretty, record, string } from "@/lib/api";
import { failureClassLabel, judgeLabel, rubricLabel, traceEventLabel } from "@/lib/evidence-labels";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, EmptyState, EvidenceDetails, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

const liveTechnicalSteps = [
  {
    index: "01",
    file: "scripts/run-live-refund-demo.ps1:44-58",
    zhTitle: "启动 7B 模型任务",
    enTitle: "Start the 7B model run",
    zhDetail: "PowerShell 把模型名交给 Docker，并启动一次全新的 demo-runner 容器。",
    enDetail: "PowerShell passes the model name into a fresh demo-runner container.",
    code: `$env:OLLAMA_MODEL = $Model\nInvoke-DockerCompose -Arguments @(\n  "run", "--rm", "-e",\n  "OLLAMA_MODEL=$Model", "demo-runner"\n)`
  },
  {
    index: "02",
    file: "infra/docker/docker-compose.refund-agent-demo.yml:25-26",
    zhTitle: "Docker 连接 Ollama",
    enTitle: "Connect Docker to Ollama",
    zhDetail: "Agent 容器通过 Docker 内网访问 Ollama，不需要云端 API key。",
    enDetail: "The Agent reaches Ollama over the Docker network without a cloud API key.",
    code: `OLLAMA_BASE_URL: http://ollama:11434\nOLLAMA_MODEL: \${OLLAMA_MODEL:-qwen2.5:0.5b}`
  },
  {
    index: "03",
    file: "examples/agents/ollama_refund_agent.py:60-66,123-128",
    zhTitle: "把消息和工具交给模型",
    enTitle: "Send messages and tools to the model",
    zhDetail: "Python SDK 创建 Ollama 适配器，再把系统规则、用户请求和工具 Schema 一起发送。",
    enDetail: "The Python SDK creates the Ollama adapter and sends rules, request, and tool schema.",
    code: `self.adapter = ProviderNeutralModelAdapter.for_ollama(\n  model=model_name, base_url=endpoint\n)\nresponse = self.adapter.complete(\n  messages, tools=[_refund_tool_schema()]\n)`
  },
  {
    index: "04",
    file: "packages/sdk/ashr_clone/model_adapter.py:286-321",
    zhTitle: "SDK 调用 Ollama /api/chat",
    enTitle: "SDK calls Ollama /api/chat",
    zhDetail: "适配器编码 JSON 请求，通过 HTTP POST 调用本地模型，并解析文字与 Tool Call。",
    enDetail: "The adapter posts JSON to the local model and parses text and tool calls.",
    code: `url = self.base_url + "/api/chat"\nresponse = self._transport(\n  "POST", url, headers, body, timeout, stream\n)`
  },
  {
    index: "05",
    file: "examples/agents/ollama_refund_agent.py:76-89",
    zhTitle: "校验参数并执行沙盒工具",
    enTitle: "Validate and execute the sandbox tool",
    zhDetail: "程序只接受指定模拟订单和 42 元；拿到回执后，再让模型生成最终中文回复。",
    enDetail: "Only the allowlisted order and amount are accepted; the receipt is used for the final response.",
    code: `decision, decision_attempts = self._decide(prompt)\nreceipt = self.sandbox.refund(\n  order_id=order_id, amount=amount\n)\nfinal_text, final_repaired = self._summarize(prompt, receipt)`
  },
  {
    index: "06",
    file: "scripts/demo/run_live_refund_pipeline.py:65-91",
    zhTitle: "A1 记录，A2 评分",
    enTitle: "A1 captures and A2 grades",
    zhDetail: "同一个 case 先经过 A1 Runner 形成 Trace，再交给 A2 的五个 Judge。",
    enDetail: "The same case becomes an A1 Trace and is then evaluated by five A2 Judges.",
    code: `run_result = run_agent_batch(agent, [build_case()])\ngrade = grade_run(\n  SCENARIO_ID, run_result["cases"][0],\n  pack_path=SCENARIO_PACK\n)`
  },
  {
    index: "07",
    file: "services/report/a3_demo_report_cli.mjs:20-22",
    zhTitle: "A3 生成页面和报告",
    enTitle: "A3 builds the page and reports",
    zhDetail: "A3 读取 A1 与 A2 的结果，生成 JSON、Markdown、CSV，并导入当前 Dashboard。",
    enDetail: "A3 reads A1/A2 evidence, exports three formats, and imports the Dashboard.",
    code: `buildJsonReport(runFixture, gradeFixture)\nbuildMarkdownReport(runFixture, gradeFixture)\nbuildCsvReport(runFixture, gradeFixture)`
  }
] as const;

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

        {model.source === "live-refund-demo" && (
          <section className="live-technical-evidence" aria-label={zh ? "大模型调用代码证据" : "Model invocation code evidence"}>
            <header className="live-technical-header">
              <div>
                <small>{zh ? "代码证据 / 从命令到报告" : "CODE EVIDENCE / COMMAND TO REPORT"}</small>
                <h2>{zh ? "它到底是怎么运行起来的？" : "How did this run actually happen?"}</h2>
                <p>{zh ? "下面每一段都来自仓库中的真实文件。文件名和行号保留在标题旁，老师可以继续打开源码核对。" : "Every excerpt comes from a real repository file, with its source path and line number shown."}</p>
              </div>
              <Braces size={28} strokeWidth={1.6} aria-hidden="true" />
            </header>

            <div className="live-model-processing">
              <div><span>1</span><strong>{zh ? "系统规则 + 用户请求" : "Rules + request"}</strong><small>{zh ? "限制只能操作模拟订单" : "Synthetic order only"}</small></div>
              <b>→</b>
              <div><span>2</span><strong>{zh ? "文字转换为 Token" : "Text to tokens"}</strong><small>{zh ? "由 Ollama/Qwen 运行时完成" : "Handled by Ollama/Qwen"}</small></div>
              <b>→</b>
              <div><span>3</span><strong>{zh ? "7B 模型生成决定" : "7B model decision"}</strong><small>{zh ? "输出结构化 Tool Call" : "Structured tool call"}</small></div>
              <b>→</b>
              <div><span>4</span><strong>{zh ? "Python 校验参数" : "Python validates"}</strong><small>{zh ? "订单号和金额必须匹配" : "Order and amount match"}</small></div>
              <b>→</b>
              <div><span>5</span><strong>{zh ? "沙盒工具返回回执" : "Sandbox receipt"}</strong><small>{zh ? "真实资金保持不变" : "No real payment mutation"}</small></div>
              <b>→</b>
              <div><span>6</span><strong>{zh ? "模型根据回执回答" : "Response from receipt"}</strong><small>{zh ? "再进入评测与报告" : "Then evaluation and report"}</small></div>
            </div>
            <p className="live-processing-boundary"><ShieldCheck size={15} aria-hidden="true" />{zh ? "我们记录输入、Tool Call、工具回执和最终回答，不伪造也不展示模型不可验证的隐藏思维链。" : "We record inputs, tool calls, receipts, and outputs without inventing hidden chain-of-thought."}</p>

            <div className="live-code-grid">
              {liveTechnicalSteps.map((step) => (
                <article key={step.index}>
                  <header><span>{step.index}</span><div><strong>{zh ? step.zhTitle : step.enTitle}</strong><code>{step.file}</code></div></header>
                  <p>{zh ? step.zhDetail : step.enDetail}</p>
                  <pre><code>{step.code}</code></pre>
                </article>
              ))}
            </div>

            <div className="live-runtime-receipt">
              <header><ReceiptText size={18} aria-hidden="true" /><div><strong>{zh ? "本次真实运行回执" : "Actual runtime receipt"}</strong><small>{zh ? "这些值来自刚才生成的 RunResult 和 GradeResult" : "Read from the generated RunResult and GradeResult"}</small></div></header>
              <pre><code>{`COMMAND     scripts/run-live-refund-demo.ps1 -Model ${modelName}\nMODEL       ${modelName}\nRUN_ID      ${item.runId}\nHTTP        POST http://ollama:11434/api/chat\nLATENCY     ${number(item.actual.latency_ms)} ms\nTOOL_CALL   ${string(firstToolCall.name, "refund_order_sandbox")}(${JSON.stringify(toolArguments)})\nTOOL_RESULT ${string(toolOutput.status, "approved")} / external_payment_mutated=${String(toolOutput.external_payment_mutated === true)}\nA1_TRACE    ${timeline.length} events\nA2_JUDGES   ${item.judgeResults.length}\nA2_SCORE    ${item.score}\nVERDICT     ${item.passed ? "PASS" : "FAIL"}`}</code></pre>
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
