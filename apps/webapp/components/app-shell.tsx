"use client";

import Link from "next/link";
import {
  Activity,
  BookOpenText,
  CreditCard,
  FileSearch,
  FileText,
  FolderKanban,
  Gauge,
  Languages,
  PackageCheck,
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
  delivery: PackageCheck,
  "api-reference": BookOpenText,
  team: Users,
  billing: CreditCard,
  trust: ShieldCheck,
  login: LogIn
};

const routeGroups = ["workspace", "evaluate", "release", "developer", "manage"] as const;

export function AppShell({ route, children }: { route: ProductRoute; children: React.ReactNode }) {
  const { language, setLanguage, t } = useI18n();
  const { model, source, setSource, loading } = useDashboard();

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link className="app-brand" href="/overview" aria-label="Ashr overview">
          <span className="brand-emblem"><PackageCheck size={20} strokeWidth={1.9} aria-hidden="true" /></span>
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
          <span><SearchCheck size={14} aria-hidden="true" /> {language === "zh-CN" ? "证据链" : "Evidence spine"}</span>
          <strong>{model?.summary.totalCases ?? 0} {language === "zh-CN" ? "个案例" : "cases"}</strong>
          <small>{loading ? t("common.loading") : language === "zh-CN" ? "执行 → 评测 → 发布" : "Run → Evaluate → Release"}</small>
        </div>
      </aside>

      <div className="app-stage">
        <header className="command-bar">
          <div className="mobile-brand"><span className="brand-emblem"><PackageCheck size={18} strokeWidth={1.9} aria-hidden="true" /></span><strong>ASHR</strong></div>
          <label className="source-control">
            <span>{t("shell.source")}</span>
            <select value={source} onChange={(event) => setSource(event.target.value)}>
              <option value="api-mock">{language === "zh-CN" ? "API 聚合证据" : "API evidence projection"}</option>
              <option value="p3-media">{language === "zh-CN" ? "多模态分歧校准" : "Multimodal disagreement calibration"}</option>
              <option value="p3-a2-round50">{language === "zh-CN" ? "三方模型复核 · Round 50" : "Three-provider review · Round 50"}</option>
              <option value="p3-official-demo">{language === "zh-CN" ? "官方校准样本 884/11926" : "Official calibration sample 884/11926"}</option>
              <option value="raw-a1">{language === "zh-CN" ? "执行证据原始样本" : "Raw execution evidence"}</option>
              <option value="raw-a2">{language === "zh-CN" ? "评测结论原始样本" : "Raw evaluation evidence"}</option>
              <option value="a3-golden-path-rc2">{language === "zh-CN" ? "发布候选 rc.2 · 3/3" : "Release candidate rc.2 · 3/3"}</option>
              <option value="a3-golden-path">{language === "zh-CN" ? "发布候选 rc.1 · 历史" : "Release candidate rc.1 · history"}</option>
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
          {productRoutes.filter((item) => ["overview", "runs", "review", "delivery", "reports"].includes(item.id)).map((item) => {
            const Icon = icons[item.id];
            return <Link href={`/${item.id}`} className={route === item.id ? "active" : ""} key={item.id}><Icon size={17} /><span>{t(item.labelKey)}</span></Link>;
          })}
        </nav>
      </div>
    </div>
  );
}
