"use client";

import {
  Braces,
  Database,
  Fingerprint,
  Gauge,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  UserRoundCheck
} from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { EvidenceDetails, StatusBadge } from "./ui";

type Props = {
  readiness: Record<string, unknown>;
  zh: boolean;
};

export function MultimodalReleaseReadinessPanel({ readiness, zh }: Props) {
  if (readiness.schema_version !== "a3.multimodal_release_readiness.v1") return null;

  const summary = record(readiness.summary);
  const cloud = record(readiness.cloud_control);
  const controls = record(readiness.control_policy);
  const safeControls = record(controls.safe_controls);
  const taxonomy = array(controls.taxonomy_assessments).map(record);
  const local = record(readiness.local_runtime);
  const repeat = record(readiness.repeat_evidence);
  const review = record(readiness.human_review);
  const persistence = record(readiness.persistence);
  const candidate = record(readiness.candidate_binding);
  const identity = record(readiness.identity_boundary);
  const status = string(readiness.status, "invalid_upstream_contract");
  const blocked = status !== "qualified_evidence_non_authoritative";
  const sensitivity = number(summary.sensitivity);
  const specificity = number(summary.specificity);

  const gates = [
    {
      icon: <ShieldAlert size={17} />,
      title: zh ? "攻击检出门槛" : "Attack sensitivity",
      state: sensitivity >= 0.8 ? "qualified" : "blocked",
      detail: zh ? `识别 ${number(summary.taxonomy_detected_count)}/${number(summary.taxonomy_eligible_count)}，最低要求 80%。` : `${number(summary.taxonomy_detected_count)}/${number(summary.taxonomy_eligible_count)} detected; minimum 80%.`
    },
    {
      icon: <Braces size={17} />,
      title: zh ? "本地结构化输出" : "Local structured output",
      state: string(local.runtime_promotion_state, "blocked"),
      detail: zh ? `${string(local.model_id)} 完成档位 ${number(local.completed_profile_count)}。` : `${string(local.model_id)} completed profiles: ${number(local.completed_profile_count)}.`
    },
    {
      icon: <UserRoundCheck size={17} />,
      title: zh ? "独立人工复核" : "Independent human review",
      state: string(review.collection_state, "pending"),
      detail: zh ? `待处理队列回执 ${number(review.pending_queue_receipt_count)}，尚无最终处置。` : `${number(review.pending_queue_receipt_count)} pending queue receipt; no terminal disposition.`
    },
    {
      icon: <Database size={17} />,
      title: zh ? "同轮 PostgreSQL 证明" : "Same-round PostgreSQL proof",
      state: string(persistence.proof_state, "blocked"),
      detail: zh ? "离线契约测试不能代替目标数据库回执。" : "Offline contract tests do not replace a target-database receipt."
    },
    {
      icon: <Fingerprint size={17} />,
      title: zh ? "同一候选绑定" : "Same-candidate binding",
      state: candidate.verified === true ? "verified" : "blocked",
      detail: zh ? `${array(candidate.blockers).length} 个版本或证据哈希仍不一致。` : `${array(candidate.blockers).length} version or evidence-hash mismatch(es) remain.`
    },
    {
      icon: <Gauge size={17} />,
      title: zh ? "企业身份客户端路由" : "Enterprise identity client route",
      state: identity.aggregate_readiness_available === true ? "available" : "not_exposed",
      detail: zh ? "运行平台已有安全运维能力，但尚未提供小程序可调用的身份就绪接口。" : "The runtime has safe operations primitives, but no mini-program identity-readiness route is exposed."
    }
  ];

  return (
    <div className="release-readiness" data-status={status}>
      <header className="release-readiness-hero">
        <div className="release-readiness-title">
          <span><ScanSearch size={21} aria-hidden="true" /></span>
          <div>
            <small>{zh ? "多模态发布校准 · ROUND 52" : "MULTIMODAL RELEASE CALIBRATION · ROUND 52"}</small>
            <h3>{blocked
              ? (zh ? "安全控制部分通过，但整体仍不可晋级" : "Safe controls passed, but promotion remains blocked")
              : (zh ? "公开证据完整，仍需权威发布裁决" : "Public evidence is complete; authoritative release approval is still required")}</h3>
            <p>{zh
              ? "没有安全误报不等于攻击识别合格；结果稳定也可能只是稳定地不合格。"
              : "Zero safe-control false positives do not prove attack sensitivity. Stable results can remain consistently unqualified."}</p>
          </div>
        </div>
        <div className="release-readiness-state">
          <StatusBadge value={status} tone={blocked ? "fail" : "warn"} />
          <code>{string(readiness.source_commit_alias, "source-unbound")}</code>
        </div>
      </header>

      <div className="release-readiness-metrics" aria-label={zh ? "多模态发布校准指标" : "Multimodal release calibration metrics"}>
        <Metric label={zh ? "安全误报" : "Safe false positives"} value={`${number(summary.safe_control_false_positive_count)}/${number(summary.safe_control_count)}`} tone="pass" />
        <Metric label={zh ? "攻击检出" : "Attack detections"} value={`${number(summary.taxonomy_detected_count)}/${number(summary.taxonomy_eligible_count)}`} tone="fail" />
        <Metric label={zh ? "特异度" : "Specificity"} value={formatPercent(specificity)} tone="pass" />
        <Metric label={zh ? "灵敏度" : "Sensitivity"} value={formatPercent(sensitivity)} tone="fail" />
        <Metric label={zh ? "结构化档位" : "Structured profiles"} value={number(summary.local_completed_profile_count)} tone="fail" />
        <Metric label={zh ? "人工复核" : "Human review"} value={string(summary.human_review_state)} tone="warn" />
      </div>

      <div className="release-readiness-analysis">
        <article className="release-readiness-control-card">
          <div className="release-readiness-card-head">
            <div><ShieldCheck size={18} /><strong>{zh ? "控制样本与攻击样本" : "Safe and attack controls"}</strong></div>
            <StatusBadge value={string(controls.quality_state)} tone="fail" />
          </div>
          <div className="release-readiness-safe-line">
            <div><span>{zh ? "安全样本" : "Safe controls"}</span><strong>{number(safeControls.eligible_count)}</strong></div>
            <div><span>{zh ? "误报" : "False positives"}</span><strong>{number(safeControls.false_positive_count)}</strong></div>
            <StatusBadge value={safeControls.passed === true ? (zh ? "通过" : "passed") : (zh ? "阻断" : "blocked")} tone={safeControls.passed === true ? "pass" : "fail"} />
          </div>
          <div className="release-readiness-taxonomy-list">
            {taxonomy.map((item) => (
              <div key={string(item.taxonomy_id)}>
                <div><strong>{taxonomyLabel(string(item.taxonomy_id), zh)}</strong><span>{number(item.detected_count)}/{number(item.eligible_count)}</span></div>
                <div className="release-readiness-meter"><i style={{ width: `${Math.min(100, number(item.sensitivity) * 100)}%` }} /></div>
                <small>{zh ? `灵敏度 ${formatPercent(number(item.sensitivity))}，门槛 ${formatPercent(number(item.minimum_sensitivity))}` : `Sensitivity ${formatPercent(number(item.sensitivity))}; threshold ${formatPercent(number(item.minimum_sensitivity))}`}</small>
              </div>
            ))}
          </div>
        </article>

        <article className="release-readiness-runtime-card">
          <div className="release-readiness-card-head">
            <div><Braces size={18} /><strong>{zh ? "本地模型晋级" : "Local runtime promotion"}</strong></div>
            <StatusBadge value={string(local.runtime_promotion_state)} tone="fail" />
          </div>
          <strong className="release-readiness-model-name">{string(local.model_id)}</strong>
          <p>{zh
            ? "Warm 延迟改善，但必需的 JSON Schema 输出仍然无效，因此不能晋级。"
            : "Warm latency improved, but required JSON Schema output remains invalid, so promotion is blocked."}</p>
          <dl>
            <div><dt>{zh ? "已完成档位" : "Completed profiles"}</dt><dd>{number(local.completed_profile_count)}</dd></div>
            <div><dt>{zh ? "质量状态" : "Quality"}</dt><dd>{string(repeat.quality_state)}</dd></div>
            <div><dt>{zh ? "稳定性" : "Stability"}</dt><dd>{string(repeat.stability_state)}</dd></div>
            <div><dt>{zh ? "允许晋级" : "Promotion"}</dt><dd>{repeat.promotion_eligible === true ? (zh ? "是" : "yes") : (zh ? "否" : "no")}</dd></div>
          </dl>
        </article>
      </div>

      <div className="release-readiness-gates">
        {gates.map((gate) => <article key={gate.title} data-state={gate.state}>
          <span>{gate.icon}</span>
          <div><strong>{gate.title}</strong><p>{gate.detail}</p></div>
          <StatusBadge value={gate.state} tone={["qualified", "verified", "available"].includes(gate.state) ? "pass" : gate.state === "pending" ? "warn" : "fail"} />
        </article>)}
      </div>

      <div className="release-readiness-boundary">
        <ShieldAlert size={18} aria-hidden="true" />
        <div>
          <strong>{zh ? "职责边界保持不变" : "Authority boundaries remain unchanged"}</strong>
          <p>{zh
            ? "运行平台负责身份与生产运行；评测服务负责质量和晋级；产品控制台只校验、保存、展示和导出公开安全摘要。"
            : "The runtime owns identity and production operations; evaluation owns quality and promotion; the console only validates, stores, displays, and exports the public-safe summary."}</p>
        </div>
      </div>

      <EvidenceDetails summary={zh ? "查看 Round 52 公开安全投影" : "View the Round 52 public-safe projection"}>
        <pre>{JSON.stringify(readiness, null, 2)}</pre>
      </EvidenceDetails>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone: "pass" | "warn" | "fail" }) {
  return <div data-tone={tone}><span>{label}</span><strong>{value}</strong></div>;
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function taxonomyLabel(value: string, zh: boolean) {
  if (value === "cross_modal_conflict") return zh ? "跨模态冲突" : "Cross-modal conflict";
  return value;
}
