"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  DashboardApiError,
  type DashboardModel,
  fetchDashboard,
  isAbortError,
  toDashboardError
} from "@/lib/api";

type DashboardContextValue = {
  model: DashboardModel | null;
  loading: boolean;
  error: DashboardApiError | null;
  source: string;
  setSource: (source: string) => void;
  reload: () => void;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [model, setModel] = useState<DashboardModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<DashboardApiError | null>(null);
  const [source, setSourceState] = useState("api-mock");
  const [sourceReady, setSourceReady] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("source");
    if (requested) setSourceState(requested);
    setSourceReady(true);
  }, []);

  useEffect(() => {
    if (!sourceReady) return;

    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(null);
    setModel(null);
    fetchDashboard(source, controller.signal)
      .then((nextModel) => {
        if (active) setModel(nextModel);
      })
      .catch((reason) => {
        if (active && !isAbortError(reason)) setError(toDashboardError(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [source, sourceReady, version]);

  const setSource = useCallback((next: string) => {
    setModel(null);
    setError(null);
    setLoading(true);
    setSourceState(next);
    const url = new URL(window.location.href);
    url.searchParams.set("source", next);
    window.history.replaceState(null, "", url);
  }, []);

  const reload = useCallback(() => {
    setModel(null);
    setError(null);
    setLoading(true);
    setVersion((current) => current + 1);
  }, []);

  const value = useMemo<DashboardContextValue>(() => ({
    model,
    loading,
    error,
    source,
    setSource,
    reload
  }), [model, loading, error, source, setSource, reload]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboard must be used inside DashboardProvider");
  return context;
}
