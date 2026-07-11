"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { type DashboardModel, fetchDashboard } from "@/lib/api";

type DashboardContextValue = {
  model: DashboardModel | null;
  loading: boolean;
  error: string;
  source: string;
  setSource: (source: string) => void;
  reload: () => void;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [model, setModel] = useState<DashboardModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSourceState] = useState("api-mock");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("source");
    if (requested) setSourceState(requested);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchDashboard(source, controller.signal)
      .then(setModel)
      .catch((reason) => {
        if (reason?.name !== "AbortError") setError(reason instanceof Error ? reason.message : "Dashboard API failed");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [source, version]);

  const setSource = useCallback((next: string) => {
    setSourceState(next);
    const url = new URL(window.location.href);
    url.searchParams.set("source", next);
    window.history.replaceState(null, "", url);
  }, []);

  const value = useMemo<DashboardContextValue>(() => ({
    model,
    loading,
    error,
    source,
    setSource,
    reload: () => setVersion((current) => current + 1)
  }), [model, loading, error, source, setSource]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboard must be used inside DashboardProvider");
  return context;
}
