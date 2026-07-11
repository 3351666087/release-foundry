"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Building2, Languages, LockKeyhole, ShieldCheck } from "lucide-react";

import { useI18n } from "@/lib/i18n";

export function LoginPage() {
  const router = useRouter();
  const { language, setLanguage } = useI18n();
  const [workspace, setWorkspace] = useState("A3 Local Organization");
  const zh = language === "zh-CN";

  return (
    <main className="login-page">
      <section className="login-signal" aria-label="Ashr Release Console">
        <div className="login-brand"><span>A3</span><strong>ASHR</strong></div>
        <div className="login-statement">
          <span className="eyebrow">AGENT RELEASE OS / PRODUCT CONSOLE</span>
          <h1>{zh ? <>发布<br />之前，<br />先看证据。</> : <>Evidence<br />before<br />release.</>}</h1>
          <p>{zh ? "运行、评测、审核和审计，在一个发布工作区内完成。" : "Run, evaluate, review, and audit in one release workspace."}</p>
        </div>
        <div className="login-signal-footer">
          <span><ShieldCheck size={15} /> A1 Capture</span>
          <span><ShieldCheck size={15} /> A2 Judge</span>
          <span><ShieldCheck size={15} /> A3 Operate</span>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-toolbar">
          <div className="language-control" role="group" aria-label="Language">
            <Languages size={14} />
            <button type="button" aria-pressed={zh} onClick={() => setLanguage("zh-CN")}>中</button>
            <button type="button" aria-pressed={!zh} onClick={() => setLanguage("en")}>EN</button>
          </div>
        </div>
        <form className="login-form" onSubmit={(event) => { event.preventDefault(); router.push("/overview"); }}>
          <div>
            <span className="eyebrow">{zh ? "只读演示身份" : "READ-ONLY DEMO IDENTITY"}</span>
            <h2>{zh ? "进入工作区" : "Enter workspace"}</h2>
            <p>{zh ? "当前入口不会创建账号，也不会保存邮箱或凭据。" : "This entry does not create an account or store email or credentials."}</p>
          </div>
          <label>
            <span>{zh ? "工作区" : "Workspace"}</span>
            <div className="input-with-icon"><Building2 size={17} /><input value={workspace} onChange={(event) => setWorkspace(event.target.value)} /></div>
          </label>
          <label>
            <span>{zh ? "访问模式" : "Access mode"}</span>
            <div className="input-with-icon"><LockKeyhole size={17} /><input value={zh ? "审计员 / 只读" : "Auditor / read only"} readOnly /></div>
          </label>
          <button className="login-submit" type="submit" disabled={!workspace.trim()}>
            {zh ? "进入只读预览" : "Open read-only preview"}<ArrowRight size={18} />
          </button>
          <div className="auth-roadmap">
            <span>{zh ? "待接入" : "Planned"}</span>
            <strong>Google OAuth · Enterprise SSO · WeChat Open Platform</strong>
          </div>
        </form>
      </section>
    </main>
  );
}
