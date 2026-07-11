"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

type Language = "zh-CN" | "en";

const copy = {
  "nav.overview": ["总览", "Overview"],
  "nav.projects": ["项目", "Projects"],
  "nav.runs": ["运行", "Runs"],
  "nav.case": ["案例详情", "Case detail"],
  "nav.review": ["人工审核", "Review"],
  "nav.reports": ["报告", "Reports"],
  "nav.apiReference": ["API 参考", "API reference"],
  "nav.team": ["团队", "Team"],
  "nav.billing": ["用量与计费", "Usage & billing"],
  "nav.trust": ["信任与审计", "Trust & audit"],
  "nav.login": ["登录", "Sign in"],
  "group.workspace": ["工作区", "Workspace"],
  "group.evaluate": ["评测", "Evaluate"],
  "group.release": ["发布", "Release"],
  "group.developer": ["开发者", "Developer"],
  "group.manage": ["管理", "Manage"],
  "shell.readOnly": ["只读预览", "Read-only preview"],
  "shell.source": ["证据来源", "Evidence source"],
  "shell.account": ["预览身份", "Preview identity"],
  "shell.legacy": ["完整证据检查器", "Full evidence inspector"],
  "common.loading": ["正在读取 A1/A2 证据", "Loading A1/A2 evidence"],
  "common.retry": ["重新加载", "Retry"],
  "common.details": ["查看证据详情", "View evidence details"],
  "common.open": ["打开", "Open"],
  "common.blocked": ["阻塞", "Blocked"],
  "common.ready": ["就绪", "Ready"],
  "common.unknown": ["未知", "Unknown"]
} as const;

type CopyKey = keyof typeof copy;
type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: CopyKey) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("zh-CN");

  useEffect(() => {
    const stored = window.localStorage.getItem("a3.webapp.language");
    const requested = new URLSearchParams(window.location.search).get("lang");
    const next = requested === "en" || stored === "en" ? "en" : "zh-CN";
    setLanguageState(next);
  }, []);

  const setLanguage = (next: Language) => {
    setLanguageState(next);
    window.localStorage.setItem("a3.webapp.language", next);
    const url = new URL(window.location.href);
    url.searchParams.set("lang", next);
    window.history.replaceState(null, "", url);
  };

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dataset.language = language === "en" ? "en" : "zh";
  }, [language]);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    setLanguage,
    t: (key) => copy[key][language === "en" ? 1 : 0]
  }), [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside I18nProvider");
  return context;
}
