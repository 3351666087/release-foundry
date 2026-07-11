"use client";

import type { ReactNode } from "react";
import { AlertTriangle, ArrowUpRight, RefreshCw } from "lucide-react";

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
  const { t } = useI18n();
  if (loading && !model) {
    return (
      <div className="loading-state" aria-live="polite">
        <span className="loading-mark" aria-hidden="true" />
        <strong>{t("common.loading")}</strong>
        <div className="loading-lines"><i /><i /><i /></div>
      </div>
    );
  }
  if (error && !model) {
    return (
      <div className="error-state" role="alert">
        <AlertTriangle size={22} aria-hidden="true" />
        <strong>{error}</strong>
        <button type="button" className="command-button" onClick={reload}>
          <RefreshCw size={15} aria-hidden="true" /> {t("common.retry")}
        </button>
      </div>
    );
  }
  if (!model) return null;
  return children(model);
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
