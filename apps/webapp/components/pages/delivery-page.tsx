"use client";

import Link from "next/link";
import {
  Archive,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  CloudCog,
  ExternalLink,
  GitBranch,
  HardDriveDownload,
  LockKeyhole,
  MessageSquareText,
  PackageCheck,
  ShieldAlert,
  TrendingUp,
  Wrench,
  Workflow
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
    const checkReadback = record(model.raw.github_check_readback);
    const checkObserved = record(checkReadback.observed);
    const commentReadback = record(model.raw.github_pr_comment_readback);
    const commentObserved = record(commentReadback.observed);
    const artifactReadback = record(model.raw.github_actions_artifact_readback);
    const artifactCalibration = record(artifactReadback.calibration);
    const requiredCheck = record(model.raw.github_required_check_proof);
    const comparison = record(model.raw.release_comparison);
    const comparisonBaseline = record(comparison.baseline);
    const comparisonCandidate = record(comparison.candidate);
    const baselineA1 = record(comparisonBaseline.a1_execution);
    const candidateA1 = record(comparisonCandidate.a1_execution);
    const baselineA2 = record(comparisonBaseline.a2_evaluation);
    const candidateA2 = record(comparisonCandidate.a2_evaluation);
    const comparisonQuality = record(comparison.quality);
    const comparisonAuthority = record(comparison.authority_boundary);
    const resolvedToolFailure = array(comparison.resolved_failure_classes)
      .map(record)
      .find((item) => string(item.failure_class, "") === "missing_required_tool");
    const stages = array(path.stages).map(record);
    const checks = array(acceptance.checks).map(record);
    const blockers = checks.filter((item) => string(item.status) !== "passed");
    const toolCallCount = number(runMetrics.total_tool_calls);
    const productionReady = path.production_ready === true;
    const hasReleaseComparison = comparison.schema_version === "a3.release_comparison.v1";

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

        {hasReleaseComparison && (
          <Section
            className="release-comparison-section"
            title={zh ? "版本对比：rc.1 → rc.2" : "Release comparison: rc.1 → rc.2"}
            description={zh
              ? "同一套 A1/A2 权威字段说明修复前后发生了什么，以及为什么测试全过仍不能发布"
              : "The same authoritative A1/A2 fields show what changed and why passing tests still do not authorize release"}
          >
            <div className="release-comparison-hero">
              <div className="release-comparison-copy">
                <span>{zh ? "本轮最重要的变化" : "MOST IMPORTANT CHANGE"}</span>
                <h3>{zh ? "案例质量已修复，发布授权仍未通过" : "Case quality repaired; release authority unchanged"}</h3>
                <p>{zh
                  ? "rc.2 补齐了真实工具链，A2 评分从 1/3 提升到 3/3；但 A2 Decision Ledger 仍是 block，所以 A3 必须继续显示不可发布。"
                  : "rc.2 adds the required tool chain and moves A2 case grades from 1/3 to 3/3. The A2 Decision Ledger still says block, so A3 must keep release disabled."}</p>
              </div>
              <div className="release-comparison-verdict" data-state={string(comparisonAuthority.candidate_decision)}>
                <ShieldAlert size={23} aria-hidden="true" />
                <span>{zh ? "A2 发布授权" : "A2 RELEASE AUTHORITY"}</span>
                <strong>{string(comparisonAuthority.baseline_decision)} <ArrowRight size={18} aria-hidden="true" /> {string(comparisonAuthority.candidate_decision)}</strong>
                <small>{zh ? "质量提升不等于发布批准" : "Quality improvement is not release approval"}</small>
              </div>
            </div>

            <div className="release-comparison-metrics" aria-label={zh ? "rc.1 与 rc.2 指标对比" : "rc.1 and rc.2 metric comparison"}>
              <article data-tone="quality">
                <header><span>A2</span><strong>{zh ? "评分通过" : "Cases passed"}</strong></header>
                <div><b>{number(baselineA2.passed)}/{number(baselineA2.total_cases)}</b><ArrowRight size={17} /><b>{number(candidateA2.passed)}/{number(candidateA2.total_cases)}</b></div>
                <p>+{number(comparisonQuality.a2_passed_case_delta)} {zh ? "例" : "cases"}</p>
                <small>{zh ? `通过率提升 ${number(comparisonQuality.a2_pass_rate_point_delta)} 个百分点` : `Pass rate +${number(comparisonQuality.a2_pass_rate_point_delta)} points`}</small>
              </article>
              <article data-tone="resolved">
                <header><span>A2</span><strong>missing_required_tool</strong></header>
                <div><b>{number(resolvedToolFailure?.before)}</b><ArrowRight size={17} /><b>{number(resolvedToolFailure?.after)}</b></div>
                <p>-{number(resolvedToolFailure?.resolved)} {zh ? "例失败" : "failures"}</p>
                <small>{zh ? "失败分类由 A2 原样提供" : "Failure classes are copied from A2"}</small>
              </article>
              <article data-tone="tools">
                <header><span>A1</span><strong>{zh ? "工具调用" : "Tool calls"}</strong></header>
                <div><b>{number(baselineA1.tool_call_count)}</b><ArrowRight size={17} /><b>{number(candidateA1.tool_call_count)}</b></div>
                <p>+{number(comparisonQuality.tool_call_delta)} {zh ? "次调用" : "calls"}</p>
                <small>{zh ? "web.search + 媒体工具链" : "web.search + media tool chain"}</small>
              </article>
              <article data-tone="evidence">
                <header><span>A3</span><strong>{zh ? "发布制品" : "Release artifacts"}</strong></header>
                <div><b>{number(comparisonBaseline.artifact_count)}</b><ArrowRight size={17} /><b>{number(comparisonCandidate.artifact_count)}</b></div>
                <p>+{number(comparisonCandidate.artifact_count) - number(comparisonBaseline.artifact_count)} {zh ? "份证据" : "artifacts"}</p>
                <small>{zh ? "版本化、哈希绑定、可回读" : "Versioned, hash-bound, readable"}</small>
              </article>
            </div>

            <div className="release-comparison-boundary">
              <div data-state="improved">
                <TrendingUp size={20} aria-hidden="true" />
                <span>{zh ? "质量层" : "QUALITY LAYER"}</span>
                <strong>{zh ? "已经改善" : "Improved"}</strong>
                <small>{zh ? "A1 工具事实 + A2 案例评分" : "A1 tool facts + A2 case grades"}</small>
              </div>
              <ArrowRight className="release-comparison-boundary-arrow" size={22} aria-hidden="true" />
              <div data-state="blocked">
                <Wrench size={20} aria-hidden="true" />
                <span>{zh ? "交付层" : "DELIVERY LAYER"}</span>
                <strong>{zh ? "仍需外部闭环" : "Still needs closure"}</strong>
                <small>{zh ? "A2 allow、部署、GitHub App 与分支门禁" : "A2 allow, deployment, GitHub App, branch policy"}</small>
              </div>
            </div>

            <EvidenceDetails summary={zh ? "查看版本对比原始契约" : "View raw comparison contract"}>
              <pre>{JSON.stringify(comparison, null, 2)}</pre>
            </EvidenceDetails>
          </Section>
        )}

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

        <Section
          title={zh ? "GitHub 真实回读" : "Live GitHub readback"}
          description={zh
            ? "区分真实外部回读、操作员身份和生产门禁；成功的 CI 不会覆盖 A2 的发布阻塞"
            : "Separates live external readback, operator identity, and production enforcement; successful CI does not override the A2 release block"}
        >
          <div className="github-readback-grid">
            <article data-state={checkReadback.readback_confirmed === true ? "confirmed" : "blocked"}>
              <div className="github-readback-head">
                <Workflow size={18} />
                <div><span>CHECK RUN</span><strong>{string(checkObserved.check_name, "A3 golden path release artifact")}</strong></div>
                <StatusBadge value={checkReadback.readback_confirmed === true ? (zh ? "已回读" : "confirmed") : string(checkReadback.readback_status)} tone={checkReadback.readback_confirmed === true ? "pass" : "fail"} />
              </div>
              <dl>
                <div><dt>{zh ? "提供方" : "Provider"}</dt><dd>{string(checkObserved.app_slug, "unavailable")}</dd></div>
                <div><dt>{zh ? "结论" : "Conclusion"}</dt><dd>{string(checkObserved.conclusion)}</dd></div>
                <div><dt>Check ID</dt><dd>{string(checkObserved.check_run_id_alias)}</dd></div>
                <div><dt>Head SHA</dt><dd><code>{shortHash(checkObserved.head_sha_alias)}</code></dd></div>
              </dl>
              <p>{zh ? "GitHub Actions App 的真实 CI 证据；不是 tenant GitHub App，也不是发布批准。" : "Live GitHub Actions App CI evidence; it is neither a tenant GitHub App nor release approval."}</p>
              <SafeGitHubLink href={checkObserved.html_url} label={zh ? "查看 Check" : "Open Check"} />
            </article>

            <article data-state={commentReadback.readback_confirmed === true ? "confirmed" : "blocked"}>
              <div className="github-readback-head">
                <MessageSquareText size={18} />
                <div><span>PR COMMENT</span><strong>{zh ? "发布阻塞评论" : "Release-block comment"}</strong></div>
                <StatusBadge value={commentReadback.readback_confirmed === true ? (zh ? "已回读" : "confirmed") : string(commentReadback.readback_status)} tone={commentReadback.readback_confirmed === true ? "pass" : "fail"} />
              </div>
              <dl>
                <div><dt>{zh ? "身份" : "Authority"}</dt><dd>{string(record(commentReadback.calibration).authority_class)}</dd></div>
                <div><dt>Comment ID</dt><dd>{string(commentObserved.comment_id_alias)}</dd></div>
                <div><dt>{zh ? "标记匹配" : "Marker match"}</dt><dd>{commentReadback.marker_match === true ? "yes" : "no"}</dd></div>
                <div><dt>{zh ? "正文匹配" : "Body match"}</dt><dd>{commentReadback.body_hash_match === true ? "yes" : "no"}</dd></div>
              </dl>
              <p>{zh ? "由 operator OAuth 发布并校验候选 SHA；不能代表租户 GitHub App。" : "Published through operator OAuth and bound to the candidate SHA; it does not represent a tenant GitHub App."}</p>
              <SafeGitHubLink href={commentObserved.html_url} label={zh ? "查看评论" : "Open comment"} />
            </article>

            <article data-state={artifactReadback.readback_confirmed === true ? "confirmed" : "blocked"}>
              <div className="github-readback-head">
                <HardDriveDownload size={18} />
                <div><span>ACTIONS ARTIFACT</span><strong>{string(artifactReadback.artifact_name, zh ? "未发现制品" : "Artifact unavailable")}</strong></div>
                <StatusBadge value={artifactReadback.digest_match === true ? (zh ? "哈希匹配" : "digest matched") : string(artifactReadback.readback_status)} tone={artifactReadback.digest_match === true ? "pass" : "fail"} />
              </div>
              <dl>
                <div><dt>Artifact ID</dt><dd>{string(artifactReadback.artifact_id_alias)}</dd></div>
                <div><dt>{zh ? "上传文件" : "Uploaded files"}</dt><dd>{number(artifactReadback.downloaded_file_count)}</dd></div>
                <div><dt>{zh ? "大小" : "Size"}</dt><dd>{formatBytes(number(artifactReadback.size_in_bytes))}</dd></div>
                <div><dt>SHA-256</dt><dd><code>{shortHash(artifactReadback.download_sha256)}</code></dd></div>
              </dl>
              <p>{artifactCalibration.custom_tenant_github_app_proven === true
                ? (zh ? "已证明 tenant GitHub App。" : "Tenant GitHub App is proven.")
                : (zh ? "ZIP digest 和 19 个上传文件已验证；tenant GitHub App 仍未证明。" : "ZIP digest and 19 uploaded files were verified; tenant GitHub App remains unproven.")}</p>
              <SafeGitHubLink href={artifactReadback.workflow_url} label={zh ? "查看 Workflow" : "Open workflow"} />
            </article>

            <article data-state={requiredCheck.enforced === true ? "confirmed" : "blocked"}>
              <div className="github-readback-head">
                <LockKeyhole size={18} />
                <div><span>MAIN POLICY</span><strong>{zh ? "Required Check 强制策略" : "Required-check enforcement"}</strong></div>
                <StatusBadge value={requiredCheck.enforced === true ? (zh ? "已强制" : "enforced") : (zh ? "未强制" : "not enforced")} tone={requiredCheck.enforced === true ? "pass" : "fail"} />
              </div>
              <dl>
                <div><dt>{zh ? "分支" : "Branch"}</dt><dd>{string(requiredCheck.branch, "main")}</dd></div>
                <div><dt>HTTP</dt><dd>{number(requiredCheck.http_status)}</dd></div>
                <div><dt>{zh ? "回读状态" : "Readback"}</dt><dd>{string(requiredCheck.readback_status)}</dd></div>
                <div><dt>{zh ? "检查数量" : "Checks found"}</dt><dd>{number(requiredCheck.checked_count)}</dd></div>
              </dl>
              <p>{zh ? "main 返回 404，branch protection 未启用；A3 没有把计划冒充强制门禁。" : "main returned 404 and branch protection is absent; A3 does not present a plan as enforced policy."}</p>
            </article>
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

function SafeGitHubLink({ href, label }: { href: unknown; label: string }) {
  const safeHref = trustedGitHubUrl(href);
  if (!safeHref) return null;
  return <a className="github-readback-link" href={safeHref} target="_blank" rel="noreferrer">{label}<ExternalLink size={14} /></a>;
}

function trustedGitHubUrl(value: unknown) {
  try {
    const url = new URL(string(value, ""));
    return url.protocol === "https:" && url.hostname === "github.com" ? url.toString() : null;
  } catch {
    return null;
  }
}

function shortHash(value: unknown) {
  const normalized = string(value, "unavailable").replace(/^sha256:/, "");
  return normalized.length > 18 ? `${normalized.slice(0, 10)}...${normalized.slice(-8)}` : normalized;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  return `${(value / 1024).toFixed(1)} KB`;
}
