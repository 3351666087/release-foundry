"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Box,
  DatabaseZap,
  FileQuestion,
  HardDrive,
  LoaderCircle,
  Network,
  RefreshCw,
  RotateCcw,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Workflow
} from "lucide-react";

import { array, number, record, string, type JsonRecord } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataTable, EvidenceDetails, StatusBadge } from "./ui";

type LoadKind = "loading" | "ready" | "empty" | "partial" | "failed" | "denied";

type LoadState = {
  kind: LoadKind;
  payload: JsonRecord | null;
  retryable: boolean;
};

export function SelfHostSandboxPanel({
  source,
  acceptancePassed,
  acceptanceTotal
}: {
  source: string;
  acceptancePassed: number;
  acceptanceTotal: number;
}) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>({ kind: "loading", payload: null, retryable: false });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setState({ kind: "loading", payload: null, retryable: false });
    fetchSandboxCalibration(source, controller.signal)
      .then((payload) => {
        if (!active) return;
        const checks = array(payload.checks);
        const failed = checks.filter((item) => string(record(item).status) === "failed").length;
        if (!checks.length) setState({ kind: "empty", payload, retryable: true });
        else if (payload.status !== "sandbox_verified" || failed > 0) setState({ kind: "partial", payload, retryable: true });
        else setState({ kind: "ready", payload, retryable: true });
      })
      .catch((reason) => {
        if (!active || reason?.name === "AbortError") return;
        const kind = reason?.kind === "denied" ? "denied" : reason?.kind === "empty" ? "empty" : "failed";
        setState({ kind, payload: null, retryable: kind === "failed" || kind === "empty" });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [source, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  if (state.kind === "loading") return <SandboxLoading zh={zh} />;
  if (state.kind === "denied") return <SandboxBoundary kind="denied" zh={zh} retry={retry} retryable={false} />;
  if (state.kind === "failed") return <SandboxBoundary kind="failed" zh={zh} retry={retry} retryable />;
  if (state.kind === "empty") return <SandboxBoundary kind="empty" zh={zh} retry={retry} retryable={state.retryable} />;

  return (
    <SandboxEvidence
      payload={state.payload || {}}
      partial={state.kind === "partial"}
      acceptancePassed={acceptancePassed}
      acceptanceTotal={acceptanceTotal}
      retry={retry}
      zh={zh}
    />
  );
}

function SandboxEvidence({
  payload,
  partial,
  acceptancePassed,
  acceptanceTotal,
  retry,
  zh
}: {
  payload: JsonRecord;
  partial: boolean;
  acceptancePassed: number;
  acceptanceTotal: number;
  retry: () => void;
  zh: boolean;
}) {
  const summary = record(payload.summary);
  const authority = record(payload.authority_boundary);
  const integrity = record(payload.evidence_integrity);
  const access = record(payload.access_contract);
  const postgres = record(payload.postgres_qualification);
  const checks = array(payload.checks).map(record);
  const gaps = array(payload.production_gaps).map(record);
  const passed = number(summary.passed);
  const total = number(summary.total_checks);
  const observedAt = useMemo(() => formatObservedAt(payload.observed_at), [payload.observed_at]);

  return (
    <div className="self-host-sandbox" data-sandbox-state={partial ? "partial" : "ready"}>
      <div className="sandbox-verdict">
        <div className="sandbox-verdict-copy">
          <div className="sandbox-verdict-mark">{partial ? <AlertTriangle size={24} /> : <ShieldCheck size={24} />}</div>
          <div>
            <span>{zh ? "A1 本地运行时回执" : "A1 LOCAL RUNTIME RECEIPT"}</span>
            <h3>{partial
              ? (zh ? "沙箱校准仅部分通过" : "Sandbox calibration is partial")
              : (zh ? "沙箱行为已验证" : "Sandbox behavior verified")}</h3>
            <p>{zh
              ? "真实执行了健康检查、Worker 重试与死信、过期租约恢复、对象写入与篡改检测。"
              : "Executed real health, worker retry/dead-letter, expired-lease recovery, and object tamper checks."}</p>
          </div>
        </div>
        <div className="sandbox-verdict-score">
          <strong>{passed}<small>/{total}</small></strong>
          <span>{zh ? "本地检查通过" : "local checks passed"}</span>
          <StatusBadge value={string(payload.status)} tone={partial ? "warn" : "pass"} />
        </div>
      </div>

      <div className="sandbox-production-boundary" role="status">
        <ShieldAlert size={21} aria-hidden="true" />
        <div>
          <strong>{zh ? "这不是生产部署证明" : "This is not production deployment proof"}</strong>
          <span>{zh
            ? `沙箱 ${passed}/${total} 不会改变部署验收 ${acceptancePassed}/${acceptanceTotal}，也不会重算 A2 裁决。`
            : `Sandbox ${passed}/${total} does not change deployment acceptance ${acceptancePassed}/${acceptanceTotal} or recompute A2.`}</span>
        </div>
        <StatusBadge value={zh ? "生产验证 0" : "production proof 0"} tone="fail" />
      </div>

      {Object.keys(postgres).length > 0 && <PostgresQualification payload={postgres} zh={zh} />}

      <div className="sandbox-check-grid" aria-label={zh ? "A1 沙箱检查" : "A1 sandbox checks"}>
        {checks.map((check) => {
          const passedCheck = string(check.status) === "passed";
          return <article key={string(check.id)} data-status={string(check.status)}>
            <header>
              {checkIcon(string(check.id))}
              <StatusBadge value={string(check.status)} tone={passedCheck ? "pass" : "fail"} />
            </header>
            <strong>{checkLabel(string(check.id), zh, string(check.label))}</strong>
            <p>{observedSummary(check, zh)}</p>
            <small>{string(check.evidence_level)} · {string(check.contract_source)}</small>
          </article>;
        })}
      </div>

      <div className="sandbox-gap-heading">
        <div><Network size={19} /><div><strong>{zh ? "尚未执行的生产验证" : "Production verification not run"}</strong><span>{zh ? "缺少目标环境就保持 not_run" : "Remains not_run without a target environment"}</span></div></div>
        <button type="button" className="icon-command" onClick={retry} title={zh ? "重新读取校准" : "Reload calibration"} aria-label={zh ? "重新读取校准" : "Reload calibration"}><RefreshCw size={16} /></button>
      </div>

      <DataTable headers={[zh ? "生产缺口" : "Production gap", zh ? "为什么没跑" : "Why not run", zh ? "需要什么证据" : "Required evidence", zh ? "状态" : "State"]} label={zh ? "生产验证缺口" : "Production verification gaps"}>
        {gaps.map((gap) => <tr key={string(gap.id)}>
          <td><strong>{gapLabel(string(gap.id), zh)}</strong><small><code>{string(gap.id)}</code></small></td>
          <td>{string(gap.reason)}</td>
          <td>{string(gap.required_evidence)}</td>
          <td><StatusBadge value={string(gap.status)} tone="warn" /></td>
        </tr>)}
      </DataTable>

      <div className="sandbox-evidence-footer">
        <span><Workflow size={15} />{zh ? "来源" : "Source"}: <code>{string(payload.source)}</code></span>
        <span><ShieldCheck size={15} />{zh ? "权限" : "Permission"}: <code>{string(access.required_permission)}</code></span>
        <span><HardDrive size={15} />{zh ? "摘要" : "Digest"}: <code>{shortDigest(integrity.probe_payload_sha256)}</code></span>
        <span><ServerCog size={15} />{zh ? "时间" : "Observed"}: {observedAt}</span>
      </div>

      <EvidenceDetails summary={zh ? "查看安全边界与校准元数据" : "View safety boundary and calibration metadata"}>
        <pre>{JSON.stringify({
          authority_boundary: authority,
          evidence_integrity: integrity,
          access_contract: access,
          safety: payload.safety
        }, null, 2)}</pre>
      </EvidenceDetails>
    </div>
  );
}

function PostgresQualification({ payload, zh }: { payload: JsonRecord; zh: boolean }) {
  const database = record(payload.database);
  const isolation = record(payload.tenant_isolation);
  const authority = record(payload.authority_boundary);
  return (
    <div className="sandbox-postgres-qualification" data-postgres-state={string(payload.status)}>
      <header>
        <div className="sandbox-postgres-title">
          <span className="sandbox-postgres-mark"><DatabaseZap size={22} /></span>
          <div>
            <small>{zh ? "真实本地数据面回执" : "REAL LOCAL DATA-PLANE RECEIPT"}</small>
            <strong>{zh ? "PostgreSQL 五层租户隔离已验证" : "PostgreSQL five-level isolation verified"}</strong>
            <p>{zh
              ? "migration 019→020 链在 PostgreSQL 17 上重复执行，并由非超级用户、不可绕过 RLS 的角色完成正反向检查。"
              : "The migration 019-to-020 chain ran twice on PostgreSQL 17 and was tested with a non-superuser, non-bypass RLS role."}</p>
          </div>
        </div>
        <StatusBadge value={string(payload.status)} tone="pass" />
      </header>
      <div className="sandbox-postgres-metrics">
        <article><span>{zh ? "数据库" : "Database"}</span><strong>PostgreSQL {string(database.server_version)}</strong><small>{string(payload.target_class)}</small></article>
        <article><span>{zh ? "迁移" : "Migration"}</span><strong>{string(database.migration_id)}</strong><small>{zh ? `幂等执行 ${number(database.migration_apply_count)} 次` : `applied ${number(database.migration_apply_count)} times`}</small></article>
        <article><span>{zh ? "RLS 策略" : "RLS policy"}</span><strong>{database.rls_enabled === true && database.rls_forced === true ? "ENABLED + FORCED" : "INCOMPLETE"}</strong><small>{number(database.policy_count)} policy</small></article>
        <article><span>{zh ? "跨租户负向测试" : "Cross-tenant negative"}</span><strong>{isolation.cross_scope_write_denied === true ? (zh ? "写入已拒绝" : "write denied") : (zh ? "未证明" : "unproven")}</strong><small>{zh ? `读取 ${number(isolation.cross_scope_read_count)} 行 · 无 scope ${number(isolation.missing_scope_read_count)} 行` : `read ${number(isolation.cross_scope_read_count)} rows · no scope ${number(isolation.missing_scope_read_count)} rows`}</small></article>
      </div>
      <footer>
        <ShieldAlert size={17} />
        <span>{zh
          ? "这证明本机 PostgreSQL/RLS 行为，不证明客户 VPC、备份恢复或生产身份；部署验收仍为 8/17。"
          : "This proves local PostgreSQL/RLS behavior, not customer VPC, backup/restore, or production identity; deployment acceptance remains 8/17."}</span>
        <StatusBadge value={authority.production_verified === true ? "production" : "sandbox only"} tone="warn" />
      </footer>
    </div>
  );
}

function SandboxLoading({ zh }: { zh: boolean }) {
  return (
    <div className="sandbox-boundary-state" data-sandbox-state="loading" role="status" aria-live="polite">
      <LoaderCircle className="spin" size={23} />
      <div><strong>{zh ? "正在读取 A1 沙箱回执" : "Loading A1 sandbox receipt"}</strong><span>{zh ? "验证结果和生产缺口会分别展示。" : "Results and production gaps will remain separate."}</span></div>
      <div className="sandbox-loading-lines"><i /><i /><i /></div>
    </div>
  );
}

function SandboxBoundary({
  kind,
  zh,
  retry,
  retryable
}: {
  kind: "empty" | "failed" | "denied";
  zh: boolean;
  retry: () => void;
  retryable: boolean;
}) {
  const copy = {
    empty: {
      icon: <FileQuestion size={23} />,
      title: zh ? "暂无沙箱校准回执" : "No sandbox calibration receipt",
      detail: zh ? "请先运行 A1 本地沙箱探针，再重新读取。" : "Run the local A1 sandbox probe, then reload."
    },
    failed: {
      icon: <AlertTriangle size={23} />,
      title: zh ? "沙箱校准读取失败" : "Sandbox calibration failed to load",
      detail: zh ? "现有部署状态没有改变，可以安全重试。" : "Deployment state is unchanged and the read can be retried safely."
    },
    denied: {
      icon: <ShieldX size={23} />,
      title: zh ? "无权查看部署校准" : "Deployment calibration access denied",
      detail: zh ? "需要 deployment:read 权限；重新加载不会改变权限。" : "deployment:read is required; reloading will not change access."
    }
  }[kind];
  return (
    <div className="sandbox-boundary-state" data-sandbox-state={kind} role="alert">
      {copy.icon}
      <div><strong>{copy.title}</strong><span>{copy.detail}</span></div>
      {retryable && <button type="button" className="command-button" onClick={retry}><RefreshCw size={15} />{zh ? "重试" : "Retry"}</button>}
    </div>
  );
}

async function fetchSandboxCalibration(source: string, signal: AbortSignal): Promise<JsonRecord> {
  const url = new URL("/api/a3/deployment/sandbox-calibration", window.location.origin);
  url.searchParams.set("source", source);
  let response: Response;
  try {
    response = await fetch(url, { credentials: "include", signal });
  } catch (reason) {
    if (reason && typeof reason === "object" && "name" in reason && reason.name === "AbortError") throw reason;
    throw { kind: "failed" };
  }
  if (response.status === 401 || response.status === 403) throw { kind: "denied" };
  if (response.status === 404) throw { kind: "empty" };
  if (!response.ok) throw { kind: "failed" };
  const payload = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw { kind: "failed" };
  return payload as JsonRecord;
}

function checkIcon(id: string) {
  if (id.includes("health")) return <ServerCog size={20} />;
  if (id.includes("retry")) return <RotateCcw size={20} />;
  if (id.includes("lease")) return <Workflow size={20} />;
  if (id.includes("storage")) return <DatabaseZap size={20} />;
  return <Box size={20} />;
}

function checkLabel(id: string, zh: boolean, fallback: string) {
  const labels: Record<string, [string, string]> = {
    a1_control_plane_health: ["控制面健康", "Control-plane health"],
    a1_worker_retry_dead_letter: ["重试与死信", "Retry and dead letter"],
    a1_worker_expired_lease_recovery: ["过期租约恢复", "Expired-lease recovery"],
    a1_local_object_storage_integrity: ["对象完整性", "Object integrity"]
  };
  return labels[id]?.[zh ? 0 : 1] || fallback;
}

function observedSummary(check: JsonRecord, zh: boolean) {
  const id = string(check.id);
  const observed = record(check.observed);
  if (id === "a1_control_plane_health") return zh ? `HTTP ${number(observed.http_status)}，服务 ${string(observed.service_status)}` : `HTTP ${number(observed.http_status)}, service ${string(observed.service_status)}`;
  if (id === "a1_worker_retry_dead_letter") return zh ? `${number(observed.attempts)} 次尝试，${number(observed.dead_letter_count)} 个死信` : `${number(observed.attempts)} attempts, ${number(observed.dead_letter_count)} dead letter`;
  if (id === "a1_worker_expired_lease_recovery") return zh ? `第 ${number(observed.recovery_attempt)} 次租约成功接管` : `Recovered on lease attempt ${number(observed.recovery_attempt)}`;
  if (id === "a1_local_object_storage_integrity") return zh ? `${number(observed.size_bytes)} B 写入回读，篡改已识别` : `${number(observed.size_bytes)} B write/readback, tamper detected`;
  return zh ? "已返回净化后的本地证据。" : "Sanitized local evidence returned.";
}

function gapLabel(id: string, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    postgres_rls_tenant_isolation: ["PostgreSQL / RLS 租户隔离", "PostgreSQL / RLS isolation"],
    container_image_identity: ["容器镜像身份", "Container image identity"],
    vpc_network_policy: ["VPC 网络策略", "VPC network policy"],
    upgrade_rollback_recovery: ["升级、回滚与恢复", "Upgrade, rollback, recovery"],
    production_a2_release_authority: ["生产 A2 发布裁决", "Production A2 release authority"]
  };
  return labels[id]?.[zh ? 0 : 1] || id;
}

function shortDigest(value: unknown) {
  const digest = string(value, "unavailable").replace(/^sha256:/, "");
  return digest.length > 20 ? `${digest.slice(0, 10)}...${digest.slice(-8)}` : digest;
}

function formatObservedAt(value: unknown) {
  const date = new Date(string(value, ""));
  return Number.isNaN(date.getTime()) ? "unavailable" : date.toLocaleString("zh-CN", { hour12: false });
}
