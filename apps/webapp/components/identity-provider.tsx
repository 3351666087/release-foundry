"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AuthApiError,
  CurrentIdentity,
  getAuthRuntimeConfig,
  getCurrentIdentity,
  logoutIdentity
} from "@/lib/auth-api";

type IdentityState = {
  mode: "demo" | "loading" | "authenticated" | "unauthenticated" | "error";
  identity: CurrentIdentity | null;
  logout: () => Promise<void>;
};

const IdentityContext = createContext<IdentityState | null>(null);

export function IdentityProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [mode, setMode] = useState<IdentityState["mode"]>("loading");
  const [identity, setIdentity] = useState<CurrentIdentity | null>(null);

  useEffect(() => {
    let active = true;
    const config = getAuthRuntimeConfig();
    if (!config.configured) {
      setMode("demo");
      return () => { active = false; };
    }
    getCurrentIdentity().then((value) => {
      if (!active) return;
      setIdentity(value);
      setMode("authenticated");
    }).catch((error) => {
      if (!active) return;
      setIdentity(null);
      setMode(error instanceof AuthApiError && error.status === 401 ? "unauthenticated" : "error");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (mode === "unauthenticated") router.replace("/login");
  }, [mode, router]);

  const value = useMemo<IdentityState>(() => ({
    mode,
    identity,
    logout: async () => {
      await logoutIdentity();
      setIdentity(null);
      setMode("unauthenticated");
      router.replace("/login");
    }
  }), [identity, mode, router]);

  if (mode === "loading") {
    return <main className="identity-gate-state"><strong>正在确认安全登录状态</strong><span>Checking the secure A1 session...</span></main>;
  }
  if (mode === "unauthenticated") {
    return <main className="identity-gate-state"><strong>需要登录</strong><span>Redirecting to the identity page...</span></main>;
  }
  if (mode === "error") {
    return <main className="identity-gate-state"><strong>身份服务暂时不可用</strong><span>请重新启动 Ashr Real Login 本地服务。</span></main>;
  }
  return <IdentityContext.Provider value={value}>{children}</IdentityContext.Provider>;
}

export function useIdentity() {
  const value = useContext(IdentityContext);
  if (!value) throw new Error("IdentityProvider is missing");
  return value;
}
