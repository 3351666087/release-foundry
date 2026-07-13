"use client";

import Link from "next/link";
import {
  Archive,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  CloudCog,
  Database,
  ExternalLink,
  GitBranch,
  HardDriveDownload,
  LockKeyhole,
  MessageSquareText,
  PackageCheck,
  ReceiptText,
  ServerCog,
  ShieldAlert,
  TrendingUp,
  UsersRound,
  Wrench,
  Workflow
} from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, EvidenceDetails, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";
import { DeploymentReceiptInbox } from "../deployment-receipt-inbox";
import { SelfHostSandboxPanel } from "../self-host-sandbox-panel";

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
    const historicalAuthority = record(path.authoritative_release);
    const runtimeAuthority = record(model.raw.trusted_release_authority);
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
    const runtimeValidation = record(comparison.runtime_authority_validation);
    const handoff = record(model.raw.deployment_handoff);
    const deploymentReceiptInbox = record(model.raw.deployment_receipt_inbox);
    const deploymentAcceptanceProjection = record(model.raw.deployment_acceptance_projection);
    const handoffSummary = record(handoff.summary);
    const candidateBinding = record(handoff.candidate_binding);
    const expectedBinding = record(candidateBinding.expected);
    const observedA2 = record(candidateBinding.observed_a2);
    const bindingRuntime = record(candidateBinding.runtime_authority);
    const historicalPacket = record(candidateBinding.historical_packet);
    const ownerGroups = array(handoff.owner_groups).map(record);
    const blockingItems = array(handoff.blocking_items).map(record);
    const bindingChecks = array(candidateBinding.checks).map(record);
    const resolvedToolFailure = array(comparison.resolved_failure_classes)
      .map(record)
      .find((item) => string(item.failure_class, "") === "missing_required_tool");
    const stages = array(path.stages).map(record);
    const checks = array(acceptance.checks).map(record);
    const toolCallCount = number(runMetrics.total_tool_calls);
    const currentStatus = string(runtimeAuthority.status, string(comparisonAuthority.current_status));
    const integrityVerified = runtimeAuthority.integrity_verified === true;
    const currentDecision = integrityVerified ? string(runtimeAuthority.upstream_decision) : "unknown";
    const productionReady = integrityVerified
      && runtimeAuthority.release_ready === true
      && path.production_ready === true;
    const bindingValid = candidateBinding.same_candidate_bound === true;
    const hasReleaseComparison = comparison.schema_version === "a3.release_comparison.v1";
    const hasDeploymentHandoff = handoff.schema_version === "a3.deployment_handoff.v1";
    const hasDeploymentReceiptInbox = deploymentReceiptInbox.schema_version === "a3.deployment_receipt_inbox.v1";

    return (
      <>
        <PageHeader
          eyebrow="RELEASE / DELIVERY / GOLDEN PATH"
          title={zh ? "交付闭环" : "Release delivery"}
          summary={zh
            ? "把 A1 运行事实、A2 权威裁决、A3 制品和 GitHub 回读放在同一条可审计证据链中。"
            : "One auditable chain for A1 runtime facts, A2 authority, A3 artifacts, and GitHub readback."}
          meta={<><span>{string(release.version, string(path.release_version))}</span><StatusBadge value={currentStatus} tone={productionReady ? "pass" : "fail"} /></>}
        />

        <section className={productionReady ? "delivery-signal ready" : "delivery-signal blocked"} data-status={currentStatus}>
          <div className="delivery-signal-copy">
            <span className="eyebrow">{zh ? "当前后端权威校验" : "CURRENT BACKEND AUTHORITY"}</span>
            <h2>{productionReady
              ? (zh ? "所有交付证据已闭环" : "Delivery evidence is complete")
              : currentStatus === "integrity_invalid"
                ? (zh ? "候选证据绑定无效" : "Candidate evidence binding is invalid")
                : (zh ? "候选版本保持阻塞" : "Release candidate remains blocked")}</h2>
            <p>{zh
              ? `当前状态：${currentStatus}；A2 决策：${currentDecision}；原因：${string(runtimeAuthority.reason_code)}。Golden Path 通过 ${number(progress.passed)}/${number(progress.total)}，部署验收通过 ${number(acceptanceSummary.passed)}/${number(acceptanceSummary.total_checks)}。`
              : `Current status: ${currentStatus}; A2 decision: ${currentDecision}; reason: ${string(runtimeAuthority.reason_code)}. Golden Path ${number(progress.passed)}/${number(progress.total)} and deployment acceptance ${number(acceptanceSummary.passed)}/${number(acceptanceSummary.total_checks)}.`}</p>
            <div className="delivery-signal-actions">
              <Link href="/review">{zh ? "处理审核" : "Open review"}<ArrowRight size={15} /></Link>
              <Link href="/reports">{zh ? "查看制品" : "View artifacts"}<PackageCheck size={15} /></Link>
            </div>
          </div>
          <div className="delivery-progress" aria-label={zh ? "交付进度" : "Delivery progress"}>
            <strong>{number(progress.percent)}%</strong>
            <span>{zh ? "Golden Path 已验证" : "Golden Path verified"}</span>
            <div><i style={{ width: `${Math.min(100, Math.max(0, number(progress.percent)))}%` }} /></div>
          </div>
        </section>

        <MetricStrip items={[
          { label: "Golden Path", value: `${number(progress.passed)}/${number(progress.total)}`, tone: productionReady ? "pass" : "warn", detail: string(path.status) },
          { label: zh ? "部署检查" : "Deploy checks", value: `${number(acceptanceSummary.passed)}/${number(acceptanceSummary.total_checks)}`, tone: "info", detail: string(acceptance.status) },
          { label: zh ? "候选绑定" : "Candidate binding", value: bindingValid ? (zh ? "已绑定" : "bound") : (zh ? "无效" : "invalid"), tone: bindingValid ? "pass" : "fail", detail: string(candidateBinding.status) },
          { label: zh ? "阻塞项" : "Blockers", value: number(handoffSummary.blocked_or_not_proven, blockingItems.length), tone: blockingItems.length ? "fail" : "pass", detail: zh ? "需要回执" : "receipts required" }
        ]} />

        <Section
          title={zh ? "新 Run 证据" : "New-run evidence"}
          description={zh
            ? "案例执行和发布授权是两套独立证据。A3 只并列展示，不把案例通过换算成发布批准。"
            : "Case execution and release authorization are independent. A3 displays both without converting passing cases into approval."}
        >
          <div className="release-artifact-band">
            <div><span>{zh ? "A1 执行" : "A1 execution"}</span><strong>{number(runFixture.passed)}/{number(runFixture.total_cases)}</strong></div>
            <div><span>{zh ? "A2 案例评分" : "A2 case grades"}</span><strong>{model.summary.passed}/{model.summary.totalCases}</strong></div>
            <div><span>{zh ? "Trace 完整率" : "Trace completeness"}</span><strong>{number(model.summary.traceCompleteness)}%</strong></div>
            <div><span>{zh ? "工具调用" : "Tool calls"}</span><strong>{toolCallCount}</strong></div>
            <div><span>{zh ? "当前 A2 决策" : "Current A2 decision"}</span><strong>{currentDecision}</strong></div>
          </div>
        </Section>

        {hasDeploymentHandoff && (
          <Section
            className="candidate-binding-section"
            title={zh ? "同一候选绑定校验" : "Same-candidate binding"}
            description={zh
              ? "最新 Git SHA、A1 Run、A2 证据与裁决、A3 制品必须属于同一个 candidate，缺一项就 fail closed。"
              : "The latest Git SHA, A1 run, A2 evidence and decision, and A3 artifact must bind one candidate or fail closed."}
          >
            <div className="candidate-binding-hero" data-status={string(candidateBinding.status)}>
              <div>
                <span>{zh ? "期望的 A3 候选" : "EXPECTED A3 CANDIDATE"}</span>
                <strong>{string(expectedBinding.run_id)}</strong>
                <small>{scopeLabel(record(expectedBinding.tenant_scope))}</small>
              </div>
              <div className="candidate-binding-connector">
                <ArrowRight size={24} aria-hidden="true" />
                <StatusBadge value={string(candidateBinding.status)} tone={bindingValid ? "pass" : "fail"} />
              </div>
              <div>
                <span>{zh ? "实际的 A2 证据" : "OBSERVED A2 EVIDENCE"}</span>
                <strong>{string(observedA2.evidence_run_id)}</strong>
                <small>{scopeLabel(record(observedA2.tenant_scope))}</small>
              </div>
            </div>

            <div className="candidate-binding-checks" aria-label={zh ? "候选绑定检查" : "Candidate binding checks"}>
              {bindingChecks.map((item) => {
                const passed = item.passed === true;
                return <article key={string(item.id)} data-status={passed ? "passed" : "failed"}>
                  {passed ? <CheckCircle2 size={18} /> : <ShieldAlert size={18} />}
                  <div><strong>{bindingCheckLabel(string(item.id), zh)}</strong><small>{string(item.requirement)}</small></div>
                  <StatusBadge value={string(item.status)} tone={passed ? "pass" : "fail"} />
                </article>;
              })}
            </div>

            <div className="authority-now-history">
              <article data-state="current">
                <span>{zh ? "当前运行时校验" : "CURRENT RUNTIME VALIDATION"}</span>
                <strong>{string(bindingRuntime.status)}</strong>
                <p>{zh ? "当前 A2 决策只能显示为" : "Current A2 decision must be"} <code>{string(bindingRuntime.upstream_decision)}</code></p>
                <small>{string(bindingRuntime.reason_code)}</small>
              </article>
              <article data-state="historical">
                <span>{zh ? "历史封存包" : "HISTORICAL SEALED PACKET"}</span>
                <strong>{string(historicalPacket.decision)}</strong>
                <p>{zh ? "仅用于说明当时结果，不是当前授权。" : "Historical evidence only; not current authorization."}</p>
                <small>{historicalPacket.integrity_marker === true ? "sealed integrity marker: true" : "integrity marker unavailable"}</small>
              </article>
            </div>
          </Section>
        )}

        {hasReleaseComparison && (
          <Section
            className="release-comparison-section"
            title={zh ? "版本对比：rc.1 → rc.2" : "Release comparison: rc.1 → rc.2"}
            description={zh
              ? "A1/A2 权威字段说明修复了什么；当前后端校验说明这份历史包为什么还不能授权发布。"
              : "A1/A2 authority fields show what improved; runtime validation explains why the historical packet cannot authorize release."}
          >
            <div className="release-comparison-hero">
              <div className="release-comparison-copy">
                <span>{zh ? "本轮最重要的变化" : "MOST IMPORTANT CHANGE"}</span>
                <h3>{zh ? "案例质量已修复，当前候选绑定无效" : "Case quality repaired; current candidate binding invalid"}</h3>
                <p>{zh
                  ? "rc.2 补齐了真实工具链，A2 案例评分从 1/3 提升到 3/3。但当前 A2 Trusted Spine 属于另一条 run 和 scope，因此后端返回 integrity_invalid。"
                  : "rc.2 adds the required tool chain and moves A2 case grades from 1/3 to 3/3. The current A2 Trusted Spine belongs to another run and scope, so the backend returns integrity_invalid."}</p>
              </div>
              <div className="release-comparison-verdict" data-state={currentStatus}>
                <ShieldAlert size={23} aria-hidden="true" />
                <span>{zh ? "历史封存 → 当前校验" : "SEALED HISTORY → CURRENT VALIDATION"}</span>
                <strong>{string(runtimeValidation.historical_candidate_decision, string(comparisonAuthority.candidate_decision))} <ArrowRight size={18} aria-hidden="true" /> {currentStatus}</strong>
                <small>{zh ? "质量提升不等于发布批准" : "Quality improvement is not release approval"}</small>
              </div>
            </div>

            <div className="release-comparison-history">
              <span>{zh ? "封存版本记录" : "SEALED VERSION HISTORY"}</span>
              <strong>rc.1 {string(comparisonAuthority.baseline_decision)} <ArrowRight size={16} /> rc.2 {string(comparisonAuthority.candidate_decision)}</strong>
              <small>{zh ? "这条记录不会覆盖当前运行时完整性校验。" : "This record never overrides current runtime integrity validation."}</small>
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
                <strong>{zh ? "仍需重新绑定" : "Rebinding required"}</strong>
                <small>{zh ? "同一 run/scope 的 A2 Spine、部署和仓库治理" : "Same-run A2 Spine, deployment, and repository governance"}</small>
              </div>
            </div>

            <EvidenceDetails summary={zh ? "查看版本对比原始契约" : "View raw comparison contract"}>
              <pre>{JSON.stringify(comparison, null, 2)}</pre>
            </EvidenceDetails>
          </Section>
        )}

        {hasDeploymentHandoff && (
          <Section
            className="deployment-handoff-section"
            title={zh ? "部署交接：按负责人拆分" : "Deployment handoff by owner"}
            description={zh
              ? "17 项验收拆成 5 个责任组。A3 已完成产品证据组，其余工作需要对应负责人提供可回读的真实回执。"
              : "Seventeen checks are grouped across five owners. A3 product evidence is complete; remaining owners must attach live receipts."}
          >
            <div className="deployment-owner-grid">
              {ownerGroups.map((group) => {
                const groupStatus = string(group.status);
                return <article key={string(group.id)} data-status={groupStatus}>
                  <header>
                    {ownerIcon(string(group.owner))}
                    <div><span>{string(group.owner)}</span><strong>{ownerGroupLabel(string(group.id), zh, string(group.label))}</strong></div>
                    <StatusBadge value={groupStatus} tone={groupStatus === "passed" ? "pass" : "fail"} />
                  </header>
                  <div className="deployment-owner-count"><strong>{number(group.passed)}/{number(group.total)}</strong><span>{zh ? "项已通过" : "checks passed"}</span></div>
                  <div className="deployment-owner-bar"><i style={{ width: `${number(group.total) ? number(group.passed) / number(group.total) * 100 : 0}%` }} /></div>
                  <p>{array(group.blocking_ids).length
                    ? `${zh ? "阻塞" : "Blocked"}: ${array(group.blocking_ids).map((item) => string(item)).join(", ")}`
                    : (zh ? "本组证据已完成。" : "Evidence for this owner group is complete.")}</p>
                </article>;
              })}
            </div>

            <div className="deployment-blocker-heading">
              <div><ReceiptText size={20} /><div><strong>{zh ? `${blockingItems.length} 项仍需真实回执` : `${blockingItems.length} live receipts still required`}</strong><span>{zh ? "合同或本地模拟不能冒充生产证明" : "Contracts and local simulations are not production proof"}</span></div></div>
              <StatusBadge value={`${number(handoffSummary.passed)}/${number(handoffSummary.total_checks)}`} tone="warn" />
            </div>

            <DataTable headers={[zh ? "阻塞项" : "Blocker", zh ? "负责人" : "Owner", zh ? "下一步" : "Next action", zh ? "必须回执" : "Required receipt"]} label={zh ? "部署阻塞与回执" : "Deployment blockers and receipts"}>
              {blockingItems.map((item) => <tr key={string(item.id)}>
                <td><strong>{string(item.label)}</strong><small><code>{string(item.id)}</code> · {string(item.blocked_reason)}</small></td>
                <td><StatusBadge value={string(item.owner)} tone="neutral" /></td>
                <td>{string(item.next_action)}</td>
                <td>{string(item.required_receipt)}</td>
              </tr>)}
            </DataTable>

            <EvidenceDetails summary={zh ? "查看部署交接原始契约" : "View raw deployment handoff contract"}>
              <pre>{JSON.stringify(handoff, null, 2)}</pre>
            </EvidenceDetails>
          </Section>
        )}

        {hasDeploymentReceiptInbox && (
          <Section
            className="deployment-receipt-section"
            title={zh ? "部署回执收件箱" : "Deployment receipt inbox"}
            description={zh
              ? "按候选版本和 Run 收集 9 类回执，并分别展示收件状态、服务器权威回读、原始验收和只读投影；A2 裁决保持不变。"
              : "Collects nine receipt classes for one candidate and run, separating intake, server readback, source acceptance, and read-only projection while preserving A2 authority."}
          >
            <DeploymentReceiptInbox inbox={deploymentReceiptInbox} projection={deploymentAcceptanceProjection} />
          </Section>
        )}

        <Section
          className="self-host-sandbox-section"
          title={zh ? "自托管沙箱校准" : "Self-host sandbox calibration"}
          description={zh
            ? "直接运行 A1 本地控制面、Worker 和对象存储契约；沙箱证据与生产部署回执严格分层。"
            : "Runs A1 local control-plane, worker, and object-storage contracts while keeping sandbox and production receipts separate."}
        >
          <SelfHostSandboxPanel
            source={model.source}
            acceptancePassed={number(acceptanceSummary.passed)}
            acceptanceTotal={number(acceptanceSummary.total_checks)}
          />
        </Section>

        <Section
          title={zh ? "Golden Path 阶段" : "Golden path stages"}
          description={zh ? "每一步都绑定负责人、状态和证据引用。" : "Every stage is bound to an owner, state, and evidence reference."}
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
            ? "区分真实外部回读、操作员身份和生产门禁；成功的 CI 不会覆盖 A2 的发布阻塞。"
            : "Separates live external readback, operator identity, and production enforcement; successful CI never overrides A2."}
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
              <p>{zh ? "这是 GitHub Actions App 的真实 CI 证据；不是 tenant GitHub App，也不是发布批准。" : "Live GitHub Actions App CI evidence; it is neither a tenant GitHub App nor release approval."}</p>
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
                : (zh ? "ZIP digest 和上传文件已验证；tenant GitHub App 仍未证明。" : "ZIP digest and uploaded files were verified; tenant GitHub App remains unproven.")}</p>
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
            title={zh ? "部署验收明细" : "Deployment acceptance details"}
            description={zh ? "没有真实环境回读就不会标记为通过。" : "A check cannot pass without live environment readback."}
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
            description={zh ? "A3 只编排，不改写上游结论。" : "A3 orchestrates without rewriting upstream decisions."}
          >
            <div className="delivery-authority-list">
              <article><CloudCog size={18} /><div><span>A1</span><strong>{zh ? "运行、身份、部署事实" : "Runtime, identity, deploy facts"}</strong></div></article>
              <article><ShieldAlert size={18} /><div><span>A2</span><strong>{zh ? "评分与发布裁决" : "Scores and release decision"}</strong></div></article>
              <article><Archive size={18} /><div><span>A3</span><strong>{zh ? "工作流、报告、证据包" : "Workflow, reports, bundles"}</strong></div></article>
              <article><GitBranch size={18} /><div><span>GitHub</span><strong>{zh ? "Check、PR、分支策略" : "Checks, PR, branch policy"}</strong></div></article>
            </div>
          </Section>
        </div>

        <Section
          title={zh ? "版本化 Release Artifact" : "Versioned release artifact"}
          description={zh ? "制品只在哈希、版本和兼容矩阵可验证后进入交付。" : "Artifacts enter delivery only after hashes, versions, and compatibility are verifiable."}
        >
          <div className="release-artifact-band">
            <div><span>{zh ? "版本" : "Version"}</span><strong>{string(release.version, "not sealed")}</strong></div>
            <div><span>{zh ? "候选 SHA" : "Candidate SHA"}</span><strong>{string(release.git_sha_alias, "not bound")}</strong></div>
            <div><span>{zh ? "CI 测试 SHA" : "CI tested SHA"}</span><strong>{string(release.ci_tested_sha_alias, "not bound")}</strong></div>
            <div><span>{zh ? "制品数" : "Artifacts"}</span><strong>{number(record(artifact.artifact_set).artifact_count)}</strong></div>
            <div><span>{zh ? "生产发布" : "Production"}</span><strong>{release.production_release === true ? "yes" : "no"}</strong></div>
          </div>
          <EvidenceDetails summary={zh ? "查看交付状态原始证据" : "View raw delivery evidence"}>
            <pre>{JSON.stringify({ delivery_golden_path: path, deployment_acceptance: acceptance, trusted_release_authority: runtimeAuthority, release_artifact_manifest: artifact }, null, 2)}</pre>
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

function ownerIcon(owner: string) {
  if (owner === "A2") return <ShieldAlert size={19} />;
  if (owner === "A1") return <ServerCog size={19} />;
  if (owner === "A1/A3") return <Database size={19} />;
  if (owner === "A3") return <Archive size={19} />;
  return <UsersRound size={19} />;
}

function ownerGroupLabel(id: string, zh: boolean, fallback: string) {
  const labels: Record<string, [string, string]> = {
    decision_authority: ["裁决权威", "Decision authority"],
    runtime_identity: ["运行与身份", "Runtime and identity"],
    platform_delivery: ["平台交付", "Platform delivery"],
    product_evidence: ["产品与证据", "Product and evidence"],
    repository_governance: ["仓库治理", "Repository governance"]
  };
  return labels[id]?.[zh ? 0 : 1] || fallback;
}

function bindingCheckLabel(id: string, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    tenant_scope: ["五级租户作用域", "Five-level tenant scope"],
    run_id: ["A1/A2 Run ID", "A1/A2 run ID"],
    release_artifact_run: ["Release Artifact 绑定", "Release Artifact binding"],
    golden_path_run: ["Golden Path 绑定", "Golden Path binding"],
    a2_integrity: ["A2 Trusted Spine 完整性", "A2 Trusted Spine integrity"]
  };
  return labels[id]?.[zh ? 0 : 1] || id;
}

function scopeLabel(scope: Record<string, unknown>) {
  return [scope.organization_id, scope.tenant_id, scope.workspace_id, scope.project_id, scope.environment_id]
    .map((item) => string(item, "-"))
    .join(" / ");
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
