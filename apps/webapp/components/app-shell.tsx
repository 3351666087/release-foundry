"use client";

import Link from "next/link";
import {
  Activity,
  CreditCard,
  FileSearch,
  FileText,
  FolderKanban,
  Gauge,
  Languages,
  LogIn,
  SearchCheck,
  ShieldCheck,
  UserCheck,
  Users
} from "lucide-react";

import type { ProductRoute } from "@/lib/routes";
import { productRoutes } from "@/lib/routes";
import { useI18n } from "@/lib/i18n";
import { useDashboard } from "./dashboard-provider";

const icons = {
  overview: Gauge,
  projects: FolderKanban,
  runs: Activity,
  case: FileSearch,
  review: UserCheck,
  reports: FileText,
  team: Users,
  billing: CreditCard,
  trust: ShieldCheck,
  login: LogIn
};

const routeGroups = ["workspace", "evaluate", "release", "manage"] as const;

export function AppShell({ route, children }: { route: ProductRoute; children: React.ReactNode }) {
  const { language, setLanguage, t } = useI18n();
  const { model, source, setSource, loading } = useDashboard();

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link className="app-brand" href="/overview" aria-label="Ashr overview">
          <span>A3</span>
          <strong>ASHR<small>Release Console</small></strong>
        </Link>

        <nav className="app-nav" aria-label="Product navigation">
          {routeGroups.map((group) => (
            <div className="nav-section" key={group}>
              <span className="nav-section-label">{t(`group.${group}`)}</span>
              {productRoutes.filter((item) => item.group === group).map((item) => {
                const Icon = icons[item.id];
                return (
                  <Link
                    className={route === item.id ? "route-link active" : "route-link"}
                    href={`/${item.id}`}
                    key={item.id}
                    aria-current={route === item.id ? "page" : undefined}
                  >
                    <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
                    <span>{t(item.labelKey)}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-contract">
          <span><SearchCheck size={14} aria-hidden="true" /> A1 / A2</span>
          <strong>{model?.summary.totalCases ?? 0} cases</strong>
          <small>{loading ? t("common.loading") : "Capture → Judge → Operate"}</small>
        </div>
      </aside>

      <div className="app-stage">
        <header className="command-bar">
          <div className="mobile-brand"><span>A3</span><strong>ASHR</strong></div>
          <label className="source-control">
            <span>{t("shell.source")}</span>
            <select value={source} onChange={(event) => setSource(event.target.value)}>
              <option value="api-mock">A1/A2 API mock</option>
              <option value="p3-official-demo">Ashr demo 884/11926</option>
              <option value="raw-a1">Raw A1 RunResult</option>
              <option value="raw-a2">Raw A2 GradeResult</option>
            </select>
          </label>
          <div className="command-actions">
            <span className="read-only-state">{t("shell.readOnly")}</span>
            <div className="language-control" role="group" aria-label="Language">
              <Languages size={14} aria-hidden="true" />
              <button type="button" aria-pressed={language === "zh-CN"} onClick={() => setLanguage("zh-CN")}>中</button>
              <button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
            </div>
            <a className="icon-command" href={`/apps/dashboard/index.html?source=${encodeURIComponent(source)}&design=signal-form`} title={t("shell.legacy")}>
              <SearchCheck size={17} aria-hidden="true" />
            </a>
            <Link className="account-command" href="/login"><LogIn size={16} aria-hidden="true" />{t("shell.account")}</Link>
          </div>
        </header>

        <main className="route-content" data-route={route}>{children}</main>

        <nav className="mobile-route-nav" aria-label="Mobile product navigation">
          {productRoutes.filter((item) => ["overview", "runs", "case", "review", "reports"].includes(item.id)).map((item) => {
            const Icon = icons[item.id];
            return <Link href={`/${item.id}`} className={route === item.id ? "active" : ""} key={item.id}><Icon size={17} /><span>{t(item.labelKey)}</span></Link>;
          })}
        </nav>
      </div>
    </div>
  );
}
