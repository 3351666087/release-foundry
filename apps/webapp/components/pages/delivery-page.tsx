"use client";

import Link from "next/link";
import {
  Archive,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  CloudCog,
  GitBranch,
  PackageCheck,
  ShieldAlert
} from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, EvidenceDetails, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function DeliveryPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";

  return <DataBoundary>{(model) => {
    const path = record(model.raw.delivery_golden_path);
    const progress = record(path.progress);
    const acceptance = record(model.raw.deployment_acceptance);
    const acceptanceSummary = record(acceptance.summary);
    const artifact = record(model.raw.release_artifact_manifest);
    const release = record(artifact.release);
    const authority = record(path.authoritative_release);
    const runFixture = record(model.raw.run_fixture);
    const runMetrics = record(runFixture.aggregate_metrics);
    const stages = array(path.stages).map(record);
    const checks = array(acceptance.checks).map(record);
    const blockers = checks.filter((item) => string(item.status) !== "passed");
    const toolCallCount = number(runMetrics.total_tool_calls);
    const productionReady = path.production_ready === true;

    return (
      <>
        <PageHeader
          eyebrow="RELEASE / DELIVERY / GOLDEN PATH"
          title={zh ? "交付闭环" : "Release delivery"}
          summary={zh
            ? "从 A1 新运行、A2 判定，到制品、部署验收和 GitHub 回读的同一条证据链。"
            : "One evidence chain from a new A1 run and A2 decision through packaging, deployment acceptance, and GitHub readback."}
          meta={<><span>{string(release.version, string(path.release_version))}</span><StatusBadge value={string(path.status)} tone={productionReady ? "pass" : "fail"} /></>}
        />

        <section className={productionReady ? "delivery-signal ready" : "delivery-signal blocked"}>
          <div className="delivery-signal-copy">
            <span className="eyebrow">{zh ? "当前发布结论" : "CURRENT RELEASE VERDICT"}</span>
            <h2>{productionReady
              ? (zh ? "所有交付证据已闭环" : "Delivery evidence is complete")
              : (zh ? "候选版本保持阻塞" : "Release candidate remains blocked")}</h2>
            <p>{zh
              ? `A2 判定：${string(authority.upstream_decision)}；部署验收：${string(acceptance.status)}；通过 ${number(progress.passed)}/${number(progress.total)} 个步骤。`
              : `A2 decision: ${string(authority.upstream_decision)}; deployment acceptance: ${string(acceptance.status)}; ${number(progress.passed)}/${number(progress.total)} stages passed.`}</p>
            <div className="delivery-signal-actions">
              <Link href="/review">{zh ? "处理审核" : "Open review"}<ArrowRight size={15} /></Link>
              <Link href="/reports">{zh ? "查看制品" : "View artifacts"}<PackageCheck size={15} /></Link>
            </div>
          </div>
          <div className="delivery-progress" aria-label={zh ? "交付进度" : "Delivery progress"}>
            <strong>{number(progress.percent)}%</strong>
            <span>{zh ? "已验证步骤" : "verified stages"}</span>
            <div><i style={{ width: `${Math.min(100, Math.max(0, number(progress.percent)))}%` }} /></div>
          </div>
        </section>

        <MetricStrip items={[
          { label: zh ? "Golden Path" : "Golden path", value: `${number(progress.passed)}/${number(progress.total)}`, tone: productionReady ? "pass" : "warn", detail: string(path.status) },
          { label: zh ? "部署检查" : "Deploy checks", value: `${number(acceptanceSummary.passed)}/${number(acceptanceSummary.total_checks)}`, tone: "info", detail: string(acceptance.status) },
          { label: zh ? "阻塞项" : "Blockers", value: blockers.length, tone: blockers.length ? "fail" : "pass", detail: zh ? "必须有证据" : "evidence required" },
          { label: zh ? "Release 版本" : "Release version", value: string(release.version, "unsealed"), tone: "cobalt", detail: string(release.channel) }
        ]} />

        <Section
          title={zh ? "新 Run 证据" : "New-run evidence"}
          description={zh
            ? "案例执行与发布授权是两套独立证据；A3 只并列展示，不把案例通过换算成发布批准"
            : "Case execution and release authorization are independent evidence; A3 displays both without converting passing cases into approval"}
        >
          <div className="release-artifact-band">
            <div><span>{zh ? "A1 执行" : "A1 execution"}</span><strong>{number(runFixture.passed)}/{number(runFixture.total_cases)}</strong></div>
            <div><span>{zh ? "A2 案例评分" : "A2 case grades"}</span><strong>{model.summary.passed}/{model.summary.totalCases}</strong></div>
            <div><span>{zh ? "Trace 完整率" : "Trace completeness"}</span><strong>{number(model.summary.traceCompleteness)}%</strong></div>
            <div><span>{zh ? "工具调用" : "Tool calls"}</span><strong>{toolCallCount}</strong></div>
            <div><span>{zh ? "Decision Ledger" : "Decision ledger"}</span><strong>{string(authority.upstream_decision, "unknown")}</strong></div>
          </div>
        </Section>

        <Section
          title={zh ? "Golden Path 阶段" : "Golden path stages"}
          description={zh ? "每一步都绑定负责人、状态和证据引用" : "Every stage is bound to an owner, state, and evidence reference"}
        >
          <div className="delivery-stage-list">
            {stages.map((item, index) => {
              const passed = string(item.status) === "passed";
              return (
                <article key={`${string(item.id)}-${index}`} data-status={string(item.status)}>
                  <span className="delivery-stage-index">{String(index + 1).padStart(2, "0")}</span>
                  {passed ? <CheckCircle2 size={19} /> : <CircleDashed size={19} />}
                  <div><strong>{string(item.label)}</strong><small>{string(item.owner)}</small></div>
                  <StatusBadge value={string(item.status)} tone={passed ? "pass" : "fail"} />
                  {!passed && <p>{string(item.blocked_reason)}</p>}
                </article>
              );
            })}
          </div>
        </Section>

        <div className="content-grid two-one">
          <Section
            title={zh ? "Deployment Acceptance" : "Deployment acceptance"}
            description={zh ? "没有真实环境回读就不会标记为通过" : "A check cannot pass without live environment readback"}
          >
            <DataTable headers={[zh ? "检查" : "Check", zh ? "负责人" : "Owner", zh ? "证据等级" : "Evidence", zh ? "状态" : "Status"]} label="Deployment acceptance checks">
              {checks.map((item, index) => <tr key={`${string(item.id)}-${index}`}>
                <td><strong>{string(item.label)}</strong><small>{string(item.blocked_reason, string(item.evidence_ref, "verified"))}</small></td>
                <td>{string(item.owner)}</td>
                <td><code>{string(item.evidence_class)}</code></td>
                <td><StatusBadge value={string(item.status)} tone={string(item.status) === "passed" ? "pass" : "fail"} /></td>
              </tr>)}
            </DataTable>
          </Section>

          <Section
            title={zh ? "权威边界" : "Authority boundary"}
            description={zh ? "A3 只编排，不改写上游结论" : "A3 orchestrates without rewriting upstream decisions"}
          >
            <div className="delivery-authority-list">
              <article><CloudCog size={18} /><div><span>A1</span><strong>{zh ? "运行、身份、部署" : "Runtime, identity, deploy"}</strong></div></article>
              <article><ShieldAlert size={18} /><div><span>A2</span><strong>{zh ? "评分与发布判定" : "Scores and release decision"}</strong></div></article>
              <article><Archive size={18} /><div><span>A3</span><strong>{zh ? "工作流、报告、证据包" : "Workflow, reports, bundles"}</strong></div></article>
              <article><GitBranch size={18} /><div><span>GitHub</span><strong>{zh ? "Check、PR、分支策略" : "Checks, PR, branch policy"}</strong></div></article>
            </div>
          </Section>
        </div>

        <Section
          title={zh ? "版本化 Release Artifact" : "Versioned release artifact"}
          description={zh ? "制品只在哈希、版本和兼容矩阵可验证后进入交付" : "Artifacts enter delivery only after hashes, versions, and compatibility are verifiable"}
        >
          <div className="release-artifact-band">
            <div><span>{zh ? "版本" : "Version"}</span><strong>{string(release.version, "not sealed")}</strong></div>
            <div><span>{zh ? "候选 SHA" : "Candidate SHA"}</span><strong>{string(release.git_sha_alias, "not bound")}</strong></div>
            <div><span>{zh ? "CI 测试 SHA" : "CI tested SHA"}</span><strong>{string(release.ci_tested_sha_alias, "not bound")}</strong></div>
            <div><span>{zh ? "制品数" : "Artifacts"}</span><strong>{number(record(artifact.artifact_set).artifact_count)}</strong></div>
            <div><span>{zh ? "生产发布" : "Production"}</span><strong>{release.production_release === true ? "yes" : "no"}</strong></div>
          </div>
          <EvidenceDetails summary={zh ? "查看交付状态原始证据" : "View raw delivery evidence"}>
            <pre>{JSON.stringify({ delivery_golden_path: path, deployment_acceptance: acceptance, release_artifact_manifest: artifact }, null, 2)}</pre>
          </EvidenceDetails>
        </Section>
      </>
    );
  }}</DataBoundary>;
}
