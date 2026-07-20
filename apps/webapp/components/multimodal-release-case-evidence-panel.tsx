"use client";

import { CheckCircle2, CircleX, FileWarning, Hash, Image, LockKeyhole } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { EvidenceDetails, StatusBadge } from "./ui";

type Props = {
  evidence: Record<string, unknown>;
  zh: boolean;
};

export function MultimodalReleaseCaseEvidencePanel({ evidence, zh }: Props) {
  if (evidence.schema_version !== "a3.multimodal_release_case_evidence.v1") return null;

  const summary = record(evidence.summary);
  const cases = array(evidence.affected_cases).map(record);
  const missedCount = number(summary.missed_count);
  const status = string(evidence.status, "invalid_upstream_case_evidence");

  return (
    <div className="release-case-evidence" data-status={status}>
      <header className="release-case-evidence-hero">
        <div className="release-case-evidence-heading">
          <span><FileWarning size={21} aria-hidden="true" /></span>
          <div>
            <small>{zh ? "案例级证据 · HASH ONLY" : "CASE-LEVEL EVIDENCE · HASH ONLY"}</small>
            <h3>{zh
              ? `${missedCount} 个跨模态攻击漏检，已绑定案例证据`
              : `${missedCount} cross-modal attacks were missed and bound to case evidence`}</h3>
            <p>{zh
              ? "聚合灵敏度现在可以追溯到具体案例；原图、模型原文和签名链接均未进入控制台。"
              : "Aggregate sensitivity is now traceable to concrete cases; raw images, model text, and signed links remain excluded."}</p>
          </div>
        </div>
        <div className="release-case-evidence-verdict">
          <StatusBadge value={status} tone={missedCount ? "fail" : "warn"} />
          <code>{string(evidence.source_commit_alias, "source-unbound")}</code>
        </div>
      </header>

      <div className="release-case-evidence-metrics" aria-label={zh ? "案例证据指标" : "Case evidence metrics"}>
        <EvidenceMetric label={zh ? "攻击案例" : "Attack cases"} value={number(summary.eligible_count)} />
        <EvidenceMetric label={zh ? "已识别" : "Detected"} value={number(summary.detected_count)} tone="pass" />
        <EvidenceMetric label={zh ? "漏检" : "Missed"} value={missedCount} tone="fail" />
        <EvidenceMetric label={zh ? "灵敏度" : "Sensitivity"} value={formatPercent(number(summary.sensitivity))} tone="fail" />
        <EvidenceMetric label={zh ? "最低门槛" : "Minimum"} value={formatPercent(number(summary.minimum_sensitivity))} />
      </div>

      <div className="release-case-evidence-list">
        {cases.map((item, index) => {
          const media = record(item.media_evidence);
          const response = record(item.response_evidence);
          const missed = string(item.outcome) === "missed";
          return (
            <article key={string(item.case_id, `case-${index}`)} data-outcome={missed ? "missed" : "detected"}>
              <span className="release-case-evidence-media"><Image size={18} aria-hidden="true" /></span>
              <div className="release-case-evidence-case">
                <div>
                  <strong>{string(item.case_id)}</strong>
                  <StatusBadge value={missed ? (zh ? "漏检" : "missed") : (zh ? "已识别" : "detected")} tone={missed ? "fail" : "pass"} />
                </div>
                <p>{zh ? "跨模态冲突" : "Cross-modal conflict"} · {number(item.latency_seconds).toFixed(3)}s · repeat {number(item.repeat)}</p>
                <dl>
                  <div title={string(media.artifact_hash)}>
                    <dt><Hash size={12} />{zh ? "图片证据" : "Media"}</dt>
                    <dd>{hashPrefix(string(media.artifact_hash))}</dd>
                  </div>
                  <div title={string(response.response_hash)}>
                    <dt><Hash size={12} />{zh ? "响应证据" : "Response"}</dt>
                    <dd>{hashPrefix(string(response.response_hash))}</dd>
                  </div>
                </dl>
              </div>
              <span className="release-case-evidence-outcome" aria-hidden="true">
                {missed ? <CircleX size={20} /> : <CheckCircle2 size={20} />}
              </span>
            </article>
          );
        })}
      </div>

      <div className="release-case-evidence-boundary">
        <LockKeyhole size={18} aria-hidden="true" />
        <div>
          <strong>{zh ? "媒体访问仍由运行数据面控制" : "Media access remains controlled by the runtime data plane"}</strong>
          <p>{zh
            ? "控制台只保存公开安全哈希。需要查看原图时，必须由运行平台签发短期访问并留下租户审计；本轮没有伪造该能力。"
            : "The console stores public-safe hashes only. Raw media requires short-lived runtime access and tenant audit; that capability is not fabricated here."}</p>
        </div>
      </div>

      <EvidenceDetails summary={zh ? "查看案例证据契约" : "View case-evidence contract"}>
        <pre>{JSON.stringify(evidence, null, 2)}</pre>
      </EvidenceDetails>
    </div>
  );
}

function EvidenceMetric({ label, value, tone = "neutral" }: {
  label: string;
  value: number | string;
  tone?: "neutral" | "pass" | "fail";
}) {
  return <div data-tone={tone}><span>{label}</span><strong>{value}</strong></div>;
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function hashPrefix(value: string) {
  return value.length > 22 ? `${value.slice(0, 18)}...` : value || "missing";
}
