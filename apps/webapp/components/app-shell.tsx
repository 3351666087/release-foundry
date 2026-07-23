"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  BookOpenText,
  CreditCard,
  ChevronDown,
  ChevronRight,
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

const groupDetails = {
  workspace: {
    index: "01",
    hint: { zh: "项目与数据", en: "Projects & data" },
    icon: FolderKanban
  },
  evaluate: {
    index: "02",
    hint: { zh: "运行与证据", en: "Runs & evidence" },
    icon: Activity
  },
  release: {
    index: "03",
    hint: { zh: "审核与交付", en: "Review & delivery" },
    icon: PackageCheck
  },
  developer: {
    index: "04",
    hint: { zh: "接口与接入", en: "API & integration" },
    icon: BookOpenText
  },
  manage: {
    index: "05",
    hint: { zh: "成员与治理", en: "Team & governance" },
    icon: ShieldCheck
  }
} as const;

const routeHints: Record<string, { zh: string; en: string }> = {
  overview: { zh: "整体状态", en: "Health overview" },
  projects: { zh: "项目边界", en: "Project boundary" },
  runs: { zh: "运行批次", en: "Run batches" },
  case: { zh: "单个证据", en: "Single case" },
  review: { zh: "人工决策", en: "Human decisions" },
  reports: { zh: "导出与分享", en: "Export & share" },
  delivery: { zh: "发布门禁", en: "Release gate" },
  "api-reference": { zh: "接口契约", en: "API contracts" },
  team: { zh: "成员权限", en: "Members & roles" },
  billing: { zh: "用量账单", en: "Usage & billing" },
  trust: { zh: "审计隔离", en: "Audit & isolation" },
  login: { zh: "身份入口", en: "Identity entry" }
};

const journey = [
  { route: "projects", zh: "准备项目", en: "Set up project" },
  { route: "runs", zh: "运行 Agent", en: "Run the agent" },
  { route: "review", zh: "检查质量", en: "Review quality" },
  { route: "delivery", zh: "决定发布", en: "Decide release" }
] as const;

export function AppShell({ route, children }: { route: ProductRoute; children: React.ReactNode }) {
  const { language, setLanguage, t } = useI18n();
  const { model, source, setSource, loading } = useDashboard();
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    developer: true,
    manage: true
  });
  const activeRoute = productRoutes.find((item) => item.id === route);
  const activeGroup = activeRoute?.group && routeGroups.includes(activeRoute.group as typeof routeGroups[number])
    ? activeRoute.group as typeof routeGroups[number]
    : "workspace";

  useEffect(() => {
    setCollapsedGroups((current) => ({ ...current, [activeGroup]: false }));
  }, [activeGroup]);

  const currentRouteHint = routeHints[route] || routeHints.overview;

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link className="app-brand" href={{ pathname: "/overview", query: { source } }} aria-label="Ashr overview">
          <span className="brand-emblem"><PackageCheck size={20} strokeWidth={1.9} aria-hidden="true" /></span>
          <strong>ASHR<small>Release Console</small></strong>
        </Link>

        <nav className="app-nav" aria-label="Product navigation">
          {routeGroups.map((group) => (
            <section className={`nav-section ${collapsedGroups[group] ? "is-collapsed" : "is-open"} ${activeGroup === group ? "is-active" : ""}`} key={group}>
              {(() => {
                const GroupIcon = groupDetails[group].icon;
                const isOpen = !collapsedGroups[group];
                const items = productRoutes.filter((item) => item.group === group);
                const visibleItems = isOpen ? items : items.filter((item) => item.id === route);
                return (
                  <>
                    <button
                      className="nav-section-toggle"
                      type="button"
                      aria-expanded={isOpen}
                      aria-controls={`nav-group-${group}`}
                      onClick={() => setCollapsedGroups((current) => ({ ...current, [group]: isOpen }))}
                    >
                      <span className="nav-section-index">{groupDetails[group].index}</span>
                      <GroupIcon size={16} strokeWidth={1.9} aria-hidden="true" />
                      <span className="nav-section-heading-copy">
                        <span className="nav-section-label">{t(`group.${group}`)}</span>
                        <small>{language === "zh-CN" ? groupDetails[group].hint.zh : groupDetails[group].hint.en}</small>
                      </span>
                      <span className="nav-section-count">{items.length}</span>
                      <ChevronDown className="nav-section-chevron" size={16} strokeWidth={2} aria-hidden="true" />
                    </button>
                    <div className="nav-section-links" id={`nav-group-${group}`}>
                      {visibleItems.map((item) => {
                const Icon = icons[item.id];
                const hint = routeHints[item.id] || routeHints.overview;
                return (
                    <Link
                    className={route === item.id ? "route-link active" : "route-link"}
                    href={{ pathname: `/${item.id}`, query: { source } }}
                    key={item.id}
                    aria-current={route === item.id ? "page" : undefined}
                    title={language === "zh-CN" ? hint.zh : hint.en}
                  >
                    <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
                    <span className="route-link-copy">
                      <span className="route-link-label">{t(item.labelKey)}</span>
                      <small>{language === "zh-CN" ? hint.zh : hint.en}</small>
                    </span>
                    {route === item.id && <span className="route-link-current">{language === "zh-CN" ? "当前" : "Current"}</span>}
                    <ChevronRight className="route-link-arrow" size={15} strokeWidth={1.9} aria-hidden="true" />
                  </Link>
                );
                      })}
                    </div>
                  </>
                );
              })()}
            </section>
          ))}
        </nav>

        <div className="sidebar-guide" aria-label={language === "zh-CN" ? "首次使用指南" : "First-use guide"}>
          <span>{language === "zh-CN" ? "第一次使用" : "FIRST SESSION"}</span>
          <strong>{language === "zh-CN" ? "从项目开始" : "Start with a project"}</strong>
          <small>{language === "zh-CN" ? "项目 → 运行 → 审核 → 发布" : "Project → Run → Review → Release"}</small>
        </div>

        <div className="sidebar-contract">
          <span><SearchCheck size={14} aria-hidden="true" /> {language === "zh-CN" ? "证据链" : "Evidence spine"}</span>
          <strong>{model?.summary.totalCases ?? 0} {language === "zh-CN" ? "个案例" : "cases"}</strong>
          <small>{loading ? t("common.loading") : language === "zh-CN" ? "执行 → 评测 → 发布" : "Run → Evaluate → Release"}</small>
        </div>
      </aside>

      <div className="app-stage">
        <header className="command-bar">
          <div className="mobile-brand"><span className="brand-emblem"><PackageCheck size={18} strokeWidth={1.9} aria-hidden="true" /></span><strong>ASHR</strong></div>
          <div className="command-context" aria-label={language === "zh-CN" ? "当前位置" : "Current location"}>
            <span className="command-context-label">{language === "zh-CN" ? "当前位置" : "CURRENT"}</span>
            <span>{t(`group.${activeGroup}`)}</span>
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" />
            <strong>{activeRoute ? t(activeRoute.labelKey) : t("nav.overview")}</strong>
            <small>{language === "zh-CN" ? currentRouteHint.zh : currentRouteHint.en}</small>
          </div>
          <label className="source-control">
            <span>{t("shell.source")}</span>
            <select value={source} onChange={(event) => setSource(event.target.value)}>
              <option value="live-refund-demo">{language === "zh-CN" ? "现场演示 · Docker 本地模型退款" : "Live demo · Docker local-model refund"}</option>
              <option value="refund-demo">{language === "zh-CN" ? "新手演示 · 电商退款失败" : "Beginner demo · Refund failure"}</option>
              <option value="api-mock">{language === "zh-CN" ? "API 聚合证据" : "API evidence projection"}</option>
              <option value="p3-media">{language === "zh-CN" ? "多模态分歧校准" : "Multimodal disagreement calibration"}</option>
              <option value="p3-a2-round50">{language === "zh-CN" ? "三方模型复核 · Round 50" : "Three-provider review · Round 50"}</option>
              <option value="p3-a2-round51">{language === "zh-CN" ? "多模态稳定性与就绪度 · Round 51" : "Multimodal stability & readiness · Round 51"}</option>
              <option value="p3-a2-round52">{language === "zh-CN" ? "多模态控制与运行时 · Round 52" : "Multimodal controls & runtime · Round 52"}</option>
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

        <div className="orientation-strip" aria-label={language === "zh-CN" ? "使用顺序" : "Suggested workflow"}>
          <span className="orientation-label">{language === "zh-CN" ? "建议顺序" : "SUGGESTED PATH"}</span>
          <div className="orientation-steps">
            {journey.map((step, index) => {
              const isCurrent = route === step.route;
              return (
                <span className={isCurrent ? "orientation-step current" : "orientation-step"} key={step.route}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <Link href={{ pathname: `/${step.route}`, query: { source } }}>{language === "zh-CN" ? step.zh : step.en}</Link>
                  {index < journey.length - 1 && <ChevronRight size={13} aria-hidden="true" />}
                  {isCurrent && <small>{language === "zh-CN" ? "你在这里" : "You are here"}</small>}
                </span>
              );
            })}
          </div>
          {route !== "overview" && (() => {
            const currentIndex = journey.findIndex((step) => step.route === route);
            const next = currentIndex >= 0 ? journey[currentIndex + 1] : undefined;
            return next ? <span className="orientation-next">{language === "zh-CN" ? "下一步" : "NEXT"} → {language === "zh-CN" ? next.zh : next.en}</span> : null;
          })()}
        </div>

        <main className="route-content" data-route={route}>{children}</main>

        <nav className="mobile-route-nav" aria-label="Mobile product navigation">
          {productRoutes.filter((item) => ["overview", "runs", "review", "delivery", "reports"].includes(item.id)).map((item) => {
            const Icon = icons[item.id];
            return <Link href={{ pathname: `/${item.id}`, query: { source } }} className={route === item.id ? "active" : ""} key={item.id}><Icon size={17} /><span>{t(item.labelKey)}</span></Link>;
          })}
        </nav>
      </div>
    </div>
  );
}
