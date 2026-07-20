"use client";

import { Activity, AlertTriangle, Gauge, ServerOff, TimerReset } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { EvidenceDetails, StatusBadge } from "./ui";

type Props = {
  readiness: Record<string, unknown>;
  zh: boolean;
};

export function MultimodalProviderReadinessPanel({ readiness, zh }: Props) {
  if (readiness.schema_version !== "a3.multimodal_provider_readiness.v1") {
    return (
      <div className="provider-readiness-empty" data-state="empty" role="status">
        <ServerOff size={22} aria-hidden="true" />
        <div>
          <strong>{zh ? "尚无 Provider 就绪度证据" : "Provider readiness evidence is unavailable"}</strong>
          <p>{zh
            ? "等待评测服务导入同一批次的可用性比较与阶段延迟诊断。没有证据时保持未知，不推断为可用。"
            : "Waiting for one atomic availability and phase-latency diagnostic import. Missing evidence remains unknown, never ready."}</p>
        </div>
        <StatusBadge value={zh ? "未导入" : "not ingested"} tone="neutral" />
      </div>
    );
  }

  const summary = record(readiness.summary);
  const availability = record(readiness.availability);
  const latency = record(readiness.latency_diagnostic);
  const providers = array(availability.providers).map(record);
  const profiles = array(latency.profiles).map(record);
  const status = string(readiness.status, "invalid_upstream_contract");
  const blocked = status !== "diagnostic_ready_non_authoritative";
  const coldSeconds = number(latency.cold_wall_seconds);
  const fastestWarmSeconds = number(latency.fastest_warm_wall_seconds);
  const profileMaxSeconds = Math.max(1, ...profiles.map((profile) => number(record(profile.phase_seconds).caller_wall_seconds)));

  return (
    <div className="provider-readiness" data-status={status}>
      <header className="provider-readiness-hero">
        <div className="provider-readiness-heading">
          <span className="provider-readiness-icon"><Activity size={21} aria-hidden="true" /></span>
          <div>
            <span>{zh ? "多模态运行诊断" : "MULTIMODAL RUNTIME DIAGNOSTIC"}</span>
            <h3>{blocked
              ? (zh ? "Provider 尚未达到可用门槛" : "Providers have not reached the readiness threshold")
              : (zh ? "诊断数据完整，但不具备发布权" : "Diagnostics are complete but non-authoritative")}</h3>
            <p>{zh
              ? "变快不等于可用，安装成功不等于质量合格。当前证据只用于定位失败阶段。"
              : "Faster does not mean ready, and installed does not mean qualified. This evidence is diagnostic only."}</p>
          </div>
        </div>
        <div className="provider-readiness-verdict">
          <StatusBadge value={status} tone={blocked ? "fail" : "warn"} />
          <code>{string(readiness.source_commit_alias, "source-unbound")}</code>
        </div>
      </header>

      <div className="provider-readiness-metrics" aria-label={zh ? "Provider 就绪度核心指标" : "Provider readiness metrics"}>
        <ReadinessMetric label={zh ? "总尝试" : "Attempts"} value={number(summary.attempted_count)} />
        <ReadinessMetric label={zh ? "完成" : "Completed"} value={number(summary.completed_count)} tone="caution" />
        <ReadinessMetric label={zh ? "失败" : "Failed"} value={number(summary.failed_count)} tone="danger" />
        <ReadinessMetric label={zh ? "超时" : "Timeouts"} value={number(summary.timeout_case_count)} tone="danger" />
        <ReadinessMetric label={zh ? "合格输出" : "Eligible"} value={number(summary.eligible_count)} tone="danger" />
        <ReadinessMetric
          label={zh ? "结构化档位" : "Valid profiles"}
          value={`${number(summary.valid_structured_profile_count)}/${number(summary.profile_count)}`}
          tone="danger"
        />
      </div>

      <div className="provider-readiness-grid">
        <div className="provider-readiness-models">
          <div className="provider-readiness-subhead">
            <div><ServerOff size={17} /><span>{zh ? "模型可用性" : "Model availability"}</span></div>
            <small>{providers.length} {zh ? "个模型" : "models"}</small>
          </div>
          <div className="provider-readiness-model-list">
            {providers.map((provider) => {
              const attempts = number(provider.attempted_count);
              const completed = number(provider.completed_count);
              const completionPercent = attempts > 0 ? Math.round((completed / attempts) * 100) : 0;
              return (
                <article key={string(provider.model_id)} data-state={string(provider.qualification_state)}>
                  <div className="provider-readiness-model-title">
                    <div><strong>{string(provider.model_id)}</strong><small>{zh ? "资格状态" : "Qualification"}</small></div>
                    <StatusBadge value={string(provider.qualification_state)} tone="fail" />
                  </div>
                  <div className="provider-readiness-model-meter" aria-label={`${string(provider.model_id)} completion ${completionPercent}%`}>
                    <i style={{ width: `${Math.max(0, Math.min(100, completionPercent))}%` }} />
                  </div>
                  <dl>
                    <div><dt>{zh ? "完成" : "Done"}</dt><dd>{completed}/{attempts}</dd></div>
                    <div><dt>{zh ? "失败" : "Failed"}</dt><dd>{number(provider.failed_count)}</dd></div>
                    <div><dt>{zh ? "超时" : "Timeout"}</dt><dd>{number(provider.timeout_case_count)}</dd></div>
                    <div><dt>{zh ? "合格" : "Eligible"}</dt><dd>{number(provider.eligible_count)}</dd></div>
                  </dl>
                </article>
              );
            })}
          </div>
        </div>

        <div className="provider-readiness-latency">
          <div className="provider-readiness-subhead">
            <div><TimerReset size={17} /><span>{zh ? "阶段延迟诊断" : "Phase latency diagnostic"}</span></div>
            <small>{string(latency.model_id)}</small>
          </div>
          <div className="provider-readiness-latency-compare">
            <div><span>{zh ? "冷启动" : "Cold"}</span><strong>{formatSeconds(coldSeconds)}</strong></div>
            <Gauge size={18} aria-hidden="true" />
            <div><span>{zh ? "最快 warm" : "Fastest warm"}</span><strong>{formatSeconds(fastestWarmSeconds)}</strong></div>
          </div>
          <div className="provider-readiness-profile-list">
            {profiles.map((profile) => {
              const wallSeconds = number(record(profile.phase_seconds).caller_wall_seconds);
              return (
                <article key={string(profile.profile)}>
                  <div><strong>{string(profile.profile)}</strong><small>{string(profile.parse_state)}</small></div>
                  <div className="provider-readiness-profile-meter"><i style={{ width: `${Math.max(2, (wallSeconds / profileMaxSeconds) * 100)}%` }} /></div>
                  <span>{formatSeconds(wallSeconds)}</span>
                </article>
              );
            })}
          </div>
        </div>
      </div>

      <div className="provider-readiness-boundary">
        <AlertTriangle size={18} aria-hidden="true" />
        <div>
          <strong>{zh ? "这不是生产健康证明，也不是质量比较" : "This is neither production health proof nor a quality comparison"}</strong>
          <p>{zh
            ? "运行平台负责生产路由、容量和运行健康；评测服务负责质量与资格；产品控制台只做校验、展示、导出和流程协调。"
            : "The runtime platform owns production routing, capacity, and health; the evaluation service owns quality and qualification; the console validates, displays, exports, and coordinates."}</p>
        </div>
      </div>

      <EvidenceDetails summary={zh ? "查看 Provider 诊断原始契约" : "View raw provider diagnostic contract"}>
        <pre>{JSON.stringify(readiness, null, 2)}</pre>
      </EvidenceDetails>
    </div>
  );
}

function ReadinessMetric({ label, value, tone = "neutral" }: {
  label: string;
  value: number | string;
  tone?: "neutral" | "caution" | "danger";
}) {
  return <div data-tone={tone}><span>{label}</span><strong>{value}</strong></div>;
}

function formatSeconds(value: number) {
  return `${value.toFixed(value >= 10 ? 1 : 2)}s`;
}
