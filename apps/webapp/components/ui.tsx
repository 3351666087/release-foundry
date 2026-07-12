"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowUpRight, FileQuestion, LogIn, RefreshCw, ShieldX } from "lucide-react";

import type { DashboardModel } from "@/lib/api";
import { useDashboard } from "./dashboard-provider";
import { useI18n } from "@/lib/i18n";

export function PageHeader({
  eyebrow,
  title,
  summary,
  meta,
  actions
}: {
  eyebrow: string;
  title: string;
  summary: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-heading-copy">
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{summary}</p>
        <span className="page-heading-signal" aria-hidden="true" />
      </div>
      {(meta || actions) && (
        <div className="page-heading-side">
          {meta && <div className="page-meta">{meta}</div>}
          {actions && <div className="page-actions">{actions}</div>}
        </div>
      )}
    </header>
  );
}

export function Section({
  title,
  description,
  action,
  children,
  className = ""
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`page-section ${className}`.trim()}>
      <header className="section-heading">
        <div className="section-heading-copy">
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function MetricStrip({ items }: { items: Array<{ label: string; value: ReactNode; tone?: string; detail?: string }> }) {
  return (
    <div className="metric-strip">
      {items.map((item) => (
        <div className={`metric-cell tone-${item.tone || "neutral"}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          {item.detail && <small>{item.detail}</small>}
        </div>
      ))}
    </div>
  );
}

export function StatusBadge({ value, tone }: { value: string; tone?: "pass" | "fail" | "warn" | "info" | "neutral" }) {
  const normalized = tone || statusTone(value);
  return <span className={`status-badge status-${normalized}`}>{value}</span>;
}

export function DataTable({ headers, children, label }: { headers: string[]; children: ReactNode; label: string }) {
  return (
    <div className="table-scroll" role="region" aria-label={label} tabIndex={0}>
      <table>
        <thead>
          <tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function EvidenceDetails({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="evidence-details">
      <summary>{summary}<ArrowUpRight size={14} aria-hidden="true" /></summary>
      <div className="evidence-detail-body">{children}</div>
    </details>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <AlertTriangle size={20} aria-hidden="true" />
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

export function DataBoundary({ children }: { children: (model: DashboardModel) => ReactNode }) {
  const { model, loading, error, reload } = useDashboard();
  const { language, t } = useI18n();
  const zh = language === "zh-CN";

  if (loading) {
    return (
      <div className="loading-state" aria-live="polite">
        <span className="loading-mark" aria-hidden="true" />
        <strong>{t("common.loading")}</strong>
        <div className="loading-lines"><i /><i /><i /></div>
      </div>
    );
  }

  if (error?.kind === "unauthenticated") {
    return (
      <BoundaryState
        kind="unauthenticated"
        icon={<LogIn size={22} aria-hidden="true" />}
        title={zh ? "请先登录" : "Sign in required"}
        detail={zh ? "登录后才能读取此工作区的证据。" : "Sign in to read evidence for this workspace."}
        action={(
          <Link className="command-button" href="/login">
            <LogIn size={15} aria-hidden="true" /> {zh ? "前往登录" : "Go to sign in"}
          </Link>
        )}
      />
    );
  }

  if (error?.kind === "denied") {
    return (
      <BoundaryState
        kind="denied"
        icon={<ShieldX size={22} aria-hidden="true" />}
        title={zh ? "无权访问" : "Access denied"}
        detail={zh ? "当前账号没有此工作区的读取权限。重新加载不会改变权限，请联系管理员。" : "Your account cannot read this workspace. Reloading will not change access; contact an administrator."}
      />
    );
  }

  if (error?.kind === "not_found") {
    return (
      <BoundaryState
        kind="not-found"
        icon={<FileQuestion size={22} aria-hidden="true" />}
        title={zh ? "未找到证据数据" : "Evidence not found"}
        detail={zh ? "该来源或工作区没有可读取的控制台数据。" : "No dashboard data is available for this source or workspace."}
      />
    );
  }

  if (error) {
    const networkFailure = error.kind === "network";
    return (
      <BoundaryState
        kind="failed"
        icon={<AlertTriangle size={22} aria-hidden="true" />}
        title={networkFailure
          ? (zh ? "无法连接服务" : "Service unreachable")
          : (zh ? "证据加载失败" : "Evidence failed to load")}
        detail={networkFailure
          ? (zh ? "请检查网络连接后重试。" : "Check your network connection and try again.")
          : (zh ? "服务暂时无法返回可用数据。" : "The service could not return usable data.")}
        action={error.retryable ? (
          <button type="button" className="command-button" onClick={reload}>
            <RefreshCw size={15} aria-hidden="true" /> {t("common.retry")}
          </button>
        ) : undefined}
      />
    );
  }

  if (!model) {
    return (
      <BoundaryState
        kind="failed"
        icon={<AlertTriangle size={22} aria-hidden="true" />}
        title={zh ? "证据加载失败" : "Evidence failed to load"}
        detail={zh ? "当前没有可显示的数据，请重新加载。" : "There is no data to display. Try loading it again."}
        action={(
          <button type="button" className="command-button" onClick={reload}>
            <RefreshCw size={15} aria-hidden="true" /> {t("common.retry")}
          </button>
        )}
      />
    );
  }

  const empty = model.runs.length === 0 && model.cases.length === 0;
  const content = empty ? (
    <EmptyState
      title={zh ? "暂无可验证的证据数据" : "No verified evidence yet"}
      detail={zh ? "当前作用域没有可展示的运行或案例。" : "This scope has no runs or cases that can be displayed."}
    />
  ) : children(model);
  if (model.aggregateScopeStatus.status === "partial") {
    return (
      <>
        <div className="partial-data-state" role="status" aria-live="polite">
          <AlertTriangle size={20} aria-hidden="true" />
          <div>
            <strong>{zh ? "当前仅显示可验证的部分数据" : "Only verified scoped data is shown"}</strong>
            <span>{zh
              ? `${model.aggregateScopeStatus.excludedRecordCount} 条当前来源中的旧记录缺少完整五级作用域，因此未计入本页。`
              : `${model.aggregateScopeStatus.excludedRecordCount} legacy records from this source lacked complete five-level scope and were omitted.`}</span>
            <small>{zh ? "处理方式：" : "Recovery: "}{model.aggregateScopeStatus.retry}</small>
          </div>
        </div>
        {content}
      </>
    );
  }

  if (empty) return content;
  return content;
}

function BoundaryState({
  kind,
  icon,
  title,
  detail,
  action
}: {
  kind: "unauthenticated" | "denied" | "not-found" | "failed";
  icon: ReactNode;
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="error-state" data-boundary-state={kind} role="alert">
      {icon}
      <strong>{title}</strong>
      <span>{detail}</span>
      {action}
    </div>
  );
}

export function formatDuration(milliseconds: number) {
  if (!milliseconds) return "-";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

export function formatDate(value: string) {
  if (!value || value === "unknown") return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false });
}

function statusTone(value: string): "pass" | "fail" | "warn" | "info" | "neutral" {
  const normalized = value.toLowerCase();
  if (["pass", "passed", "ready", "active", "complete", "healthy", "allowed"].some((item) => normalized.includes(item))) return "pass";
  if (["fail", "block", "deny", "error", "expired", "revoked"].some((item) => normalized.includes(item))) return "fail";
  if (["warn", "wait", "required", "review", "planned", "due"].some((item) => normalized.includes(item))) return "warn";
  if (["info", "preview", "read_only", "readonly", "mock"].some((item) => normalized.includes(item))) return "info";
  return "neutral";
}
