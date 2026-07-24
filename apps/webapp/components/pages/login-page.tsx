"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BookOpenText,
  Building2,
  Check,
  GitFork,
  Languages,
  LockKeyhole,
  Mail,
  PackageCheck,
  ShieldAlert,
  ShieldCheck,
  UserRound
} from "lucide-react";

import {
  AuthApiError,
  authContractCapabilities,
  beginEmailLogin,
  beginEmailRegistration,
  completeEmailLogin,
  completeEmailRegistration,
  getAuthRuntimeConfig,
} from "@/lib/auth-api";
import { useI18n } from "@/lib/i18n";
import { VerificationEmailPreview } from "../email/verification-email-preview";
import styles from "./login-page.module.css";

type AuthMode = "signin" | "signup";
type Notice = { tone: "info" | "success" | "warning" | "error"; text: string } | null;

export function LoginPage() {
  const router = useRouter();
  const { language, setLanguage } = useI18n();
  const zh = language === "zh-CN";
  const config = useMemo(() => getAuthRuntimeConfig(), []);
  const [mode, setMode] = useState<AuthMode>("signin");
  const [workspace, setWorkspace] = useState("示例企业 / 发布工作区");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [intentId, setIntentId] = useState("");
  const [challengeExpiresAt, setChallengeExpiresAt] = useState("");
  const [consent, setConsent] = useState(false);
  const [verificationRequested, setVerificationRequested] = useState(false);
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState<"email" | "verify" | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  function selectMode(nextMode: AuthMode) {
    setMode(nextMode);
    setChallengeId("");
    setIntentId("");
    setChallengeExpiresAt("");
    setCode("");
    setVerificationRequested(false);
    setVerified(false);
    setNotice(null);
  }

  async function handleVerificationRequest(event: FormEvent) {
    event.preventDefault();
    setBusy("email");
    setNotice(null);
    try {
      const challenge = mode === "signup"
        ? await beginEmailRegistration(email)
        : await beginEmailLogin(email);
      setChallengeId(challenge.challenge_id);
      setIntentId(challenge.intent_id);
      setChallengeExpiresAt(challenge.expires_at);
      setVerificationRequested(true);
      setNotice({
        tone: "success",
        text: zh
          ? "验证码请求已由身份服务接收。请查看邮箱；页面只暂存本次验证编号，不保存验证码。"
          : "The identity service accepted the challenge. Check your email; this page keeps only the short-lived challenge handles."
      });
      if (config.apiBaseUrl === "https://localhost:4443") {
        window.open("http://127.0.0.1:18025", "ashr-local-inbox");
      }
    } catch (error) {
      setNotice({ tone: "error", text: authErrorText(error, zh) });
    } finally {
      setBusy(null);
    }
  }

  async function handleVerificationComplete(event: FormEvent) {
    event.preventDefault();
    setBusy("verify");
    setNotice(null);
    try {
      if (mode === "signup") {
        await completeEmailRegistration({ challengeId, intentId, code, displayName });
      } else {
        await completeEmailLogin({ challengeId, intentId, code });
      }
      setVerified(true);
      setCode("");
      setNotice({
        tone: "success",
        text: zh
          ? "身份服务已签发安全登录 Cookie，正在进入控制台。页面和脚本都无法读取 HttpOnly Cookie。"
          : "The identity service issued secure session cookies. Entering the console without exposing HttpOnly cookie values."
      });
      router.push("/overview?source=api-mock&login=complete");
    } catch (error) {
      setNotice({ tone: "error", text: authErrorText(error, zh) });
    } finally {
      setBusy(null);
    }
  }

  const configLabel = config.configured
    ? (zh ? "身份服务已配置" : "Identity service configured")
    : (zh ? "身份服务未连接" : "Identity service not connected");
  const oauthInitialLoginReady = config.configured && authContractCapabilities.oauthInitialLogin;
  const beginDisabled = !config.configured
    || !email.trim()
    || (mode === "signup" && (!displayName.trim() || !consent))
    || busy !== null;
  const completeDisabled = !challengeId
    || !intentId
    || code.length !== 6
    || (mode === "signup" && !displayName.trim())
    || busy !== null;

  const emailIdentityFlow = !verificationRequested ? (
    <form onSubmit={handleVerificationRequest}>
      {mode === "signup" && (
        <label>
          <span>{zh ? "你的名字" : "Display name"}</span>
          <div className="input-with-icon"><UserRound size={17} /><input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder={zh ? "用于团队审核记录" : "Shown in team review records"} /></div>
        </label>
      )}
      <label>
        <span>{zh ? "工作邮箱" : "Work email"}</span>
        <div className="input-with-icon"><Mail size={17} /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="student@example.com" /></div>
      </label>
      {mode === "signup" && (
        <label className={styles.consent}>
          <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
          <span>{zh ? "我同意创建 Ashr 账号，并接受验证码与安全通知邮件。" : "I agree to create an Ashr account and receive verification and security messages."}</span>
        </label>
      )}
      <button className="login-submit" type="submit" disabled={beginDisabled}>
        {busy === "email"
          ? (zh ? "正在请求..." : "Requesting...")
          : mode === "signup"
            ? (zh ? "发送注册验证码" : "Send registration code")
            : (zh ? "发送登录验证码" : "Send sign-in code")}<ArrowRight size={18} />
      </button>
    </form>
  ) : verified ? (
    <div className={styles.verifiedState}>
      <span><Check size={21} /></span>
      <h3>{zh ? "安全会话已建立" : "Secure session established"}</h3>
      <p>{zh ? "身份服务已完成 303 /console 交接，正在进入产品控制台。" : "The identity service completed the trusted 303 /console handoff."}</p>
    </div>
  ) : (
    <form onSubmit={handleVerificationComplete}>
      <div className={styles.codeHeading}>
        <span><Mail size={17} /></span>
        <div>
          <strong>{zh ? "查看你的邮箱" : "Check your email"}</strong>
          <small>{zh ? "输入 6 位验证码" : "Enter the six-digit code"}</small>
        </div>
      </div>
      {mode === "signup" && (
        <label>
          <span>{zh ? "你的名字" : "Display name"}</span>
          <div className="input-with-icon"><UserRound size={17} /><input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></div>
        </label>
      )}
      <label>
        <span>{zh ? "验证邮箱" : "Email being verified"}</span>
        <div className="input-with-icon"><Mail size={17} /><input type="email" value={email} readOnly /></div>
      </label>
      <label>
        <span>{zh ? "验证码" : "Verification code"}</span>
        <input className={styles.codeInput} inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" />
      </label>
      <div className={styles.boundaryNote}>
        <LockKeyhole size={15} />
        <p>{zh
          ? `本次验证上下文已安全接收${challengeExpiresAt ? `，有效期至 ${new Date(challengeExpiresAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}` : ""}。验证码不会写入本地存储或日志。`
          : "The short-lived challenge context is ready. The code is never written to local storage or logs."}</p>
      </div>
      <button className="login-submit" type="submit" disabled={completeDisabled}>
        {busy === "verify"
          ? (zh ? "正在验证..." : "Verifying...")
          : mode === "signup"
            ? (zh ? "验证并创建账号" : "Verify and create account")
            : (zh ? "验证并登录" : "Verify and sign in")}<ArrowRight size={18} />
      </button>
      <button type="button" className={styles.textButton} onClick={() => { setVerificationRequested(false); setChallengeId(""); setIntentId(""); setCode(""); setNotice(null); }}>{zh ? "更换邮箱" : "Use another email"}</button>
    </form>
  );

  return (
    <main className={`login-page ${styles.page}`}>
      <section className={`login-signal ${styles.signal}`} aria-label="Ashr Release Console">
        <div className="login-brand"><span><PackageCheck size={20} strokeWidth={1.9} aria-hidden="true" /></span><strong>ASHR</strong></div>
        <div className="login-statement">
          <span className="eyebrow">AGENT RELEASE OS / PRODUCT CONSOLE</span>
          <h1>{zh ? <>发布<br />之前，<br />先看证据。</> : <>Evidence<br />before<br />release.</>}</h1>
          <p>{zh ? "运行、评测、审核和审计，在一个发布工作区内完成。" : "Run, evaluate, review, and audit in one release workspace."}</p>
        </div>
        <div className="login-signal-footer">
          <span><ShieldCheck size={15} /> {zh ? "执行证据" : "Execution"}</span>
          <span><ShieldCheck size={15} /> {zh ? "评测结论" : "Evaluation"}</span>
          <span><ShieldCheck size={15} /> {zh ? "发布治理" : "Release"}</span>
        </div>
      </section>

      <section className={`login-panel ${styles.panel}`}>
        <div className="login-toolbar">
          <Link className={styles.docsLink} href="/api-reference" title={zh ? "API 文档" : "API docs"}>
            <BookOpenText size={15} /> <span>{zh ? "API 参考" : "API reference"}</span>
          </Link>
          <div className="language-control" role="group" aria-label="Language">
            <Languages size={14} />
            <button type="button" aria-pressed={zh} onClick={() => setLanguage("zh-CN")}>中</button>
            <button type="button" aria-pressed={!zh} onClick={() => setLanguage("en")}>EN</button>
          </div>
        </div>

        <div className={`login-form ${styles.authSurface}`}>
          <header className={styles.heading}>
            <span className="eyebrow">IDENTITY / WORKSPACE ACCESS</span>
            <h2>{zh ? "进入工作区" : "Enter workspace"}</h2>
            <p>{zh ? "使用受支持的身份方式，或先进入只读产品预览。" : "Use a supported identity provider or enter the read-only product preview."}</p>
          </header>

          <Link className="preview-quickstart" href={{ pathname: "/overview", query: { source: "refund-demo" } }}>
            <span className="preview-quickstart-icon"><PackageCheck size={18} aria-hidden="true" /></span>
            <span>
              <strong>{zh ? "一键进入退款案例演示" : "Open the refund demo"}</strong>
              <small>{zh ? "无需登录 · 一条案例看懂 A1、A2、A3" : "No sign-in · One case explains execution, evaluation, and review"}</small>
            </span>
            <ArrowRight size={17} aria-hidden="true" />
          </Link>

          <div className={styles.modeSwitch} role="tablist" aria-label={zh ? "身份模式" : "Identity mode"}>
            <button type="button" role="tab" aria-selected={mode === "signin"} onClick={() => selectMode("signin")}>
              {zh ? "登录" : "Sign in"}
            </button>
            <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => selectMode("signup")}>
              {zh ? "邮箱注册" : "Create account"}
            </button>
          </div>

          <div className={`auth-roadmap ${styles.runtimeState}`} data-ready={config.configured}>
            {config.configured ? <Check size={15} /> : <ShieldAlert size={15} />}
            <span>{configLabel}</span>
            <small>IDENTITY {authContractCapabilities.sourceSha} · {config.configured ? "configured" : config.reason}</small>
          </div>

          {mode === "signin" ? (
            <div className={styles.signInFlow} role="tabpanel">
              <div className={styles.providerGrid}>
                <button type="button" className={styles.providerButton} disabled={!oauthInitialLoginReady || busy !== null} title={zh ? "协调器已完成，本地尚未配置 Provider 与 Vault" : "Coordinator ready; local Provider and Vault configuration is missing"}>
                  <span className={styles.googleMark} aria-hidden="true">G</span>
                  <span><strong>{zh ? "Google 登录待配置" : "Google sign-in needs configuration"}</strong><small>{zh ? "协调器已就绪 · 缺少本地 Provider/Vault" : "Coordinator ready · local Provider/Vault missing"}</small></span>
                  <ArrowRight size={16} />
                </button>
                <button type="button" className={styles.providerButton} disabled={!oauthInitialLoginReady || busy !== null} title={zh ? "协调器已完成，本地尚未配置 Provider 与 Vault" : "Coordinator ready; local Provider and Vault configuration is missing"}>
                  <GitFork size={19} aria-hidden="true" />
                  <span><strong>{zh ? "GitHub 登录待配置" : "GitHub sign-in needs configuration"}</strong><small>{zh ? "协调器已就绪 · 缺少本地 Provider/Vault" : "Coordinator ready · local Provider/Vault missing"}</small></span>
                  <ArrowRight size={16} />
                </button>
              </div>

              <div className={styles.boundaryNote}>
                <LockKeyhole size={15} />
                <p>{zh
                  ? "邮箱注册和邮箱登录已接入 A1 的安全 Cookie 闭环。Google/GitHub 首次登录协调器已实现，但本地 Provider、Vault 和回调部署尚未配置，因此按钮继续关闭。"
                  : "Email registration and sign-in use A1's secure cookie handoff. The Google/GitHub first-login coordinator is implemented, but local Provider, Vault, and callback deployment are not configured, so the buttons remain disabled."}</p>
              </div>

              {emailIdentityFlow}

              <details className={styles.previewEntry}>
                <summary><span><strong>READ-ONLY DEMO IDENTITY</strong><small>{zh ? "不创建账号，不保存邮箱或凭据" : "This preview does not create an account or store email or credentials."}</small></span><ArrowRight size={15} /></summary>
                <form onSubmit={(event) => { event.preventDefault(); router.push("/overview?source=refund-demo"); }}>
                  <label>
                    <span>{zh ? "工作区" : "Workspace"}</span>
                    <div className="input-with-icon"><Building2 size={17} /><input value={workspace} onChange={(event) => setWorkspace(event.target.value)} /></div>
                  </label>
                  <label>
                    <span>{zh ? "访问模式" : "Access mode"}</span>
                    <div className="input-with-icon"><LockKeyhole size={17} /><input value={zh ? "审计员 / 只读" : "Auditor / read only"} readOnly /></div>
                  </label>
                  <button className="login-submit" type="submit" disabled={!workspace.trim()}>{zh ? "进入只读预览" : "Open read-only preview"}<ArrowRight size={18} /></button>
                </form>
              </details>
            </div>
          ) : (
            <div className={styles.signUpFlow} role="tabpanel">
              {emailIdentityFlow}

              <details className={styles.emailPreview}>
                <summary>{zh ? "查看验证邮件设计稿" : "Preview verification email"}</summary>
                <div><VerificationEmailPreview zh={zh} /></div>
                <p>{zh ? "这是 HTML 邮件模板设计稿；当前身份服务的 SMTP 仍发送纯文本。" : "This is the HTML email template preview; the identity service currently sends plain text."}</p>
              </details>
            </div>
          )}

          {notice && <div className={styles.notice} data-tone={notice.tone} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}
        </div>
      </section>
    </main>
  );
}

function authErrorText(error: unknown, zh: boolean) {
  const code = error instanceof AuthApiError ? error.code : "identity_request_failed";
  const known: Record<string, [string, string]> = {
    api_base_missing: ["当前构建没有配置身份 API 地址。", "This build has no identity API base URL."],
    api_base_invalid: ["身份 API 地址不安全或格式不正确。", "The identity API base URL is invalid or unsafe."],
    browser_origin_insecure: ["真实注册登录必须通过本机 HTTPS 入口使用。当前 HTTP 页面仅提供只读演示。", "Real registration and sign-in require the local HTTPS entry. This HTTP page is read-only."],
    browser_origin_mismatch: ["网页与身份 API 必须使用同一个 HTTPS 地址。", "The webapp and identity API must use the same HTTPS origin."],
    project_missing: ["当前构建没有配置 project_id。", "This build has no project_id."],
    tenant_missing: ["当前构建没有配置 tenant_id。", "This build has no tenant_id."],
    identity_service_unreachable: ["无法连接身份服务；请确认服务已启动并允许 Webapp 来源。", "The identity service is unreachable; confirm it is running and allows the webapp origin."],
    identity_service_timeout: ["身份服务响应超时。", "The identity service timed out."],
    identity_session_same_origin_required: ["浏览器会话轮换要求 Webapp 与身份 API 使用同一个 HTTPS 来源。", "Browser session refresh requires the Webapp and identity API to use the same HTTPS origin."],
    identity_session_required: ["服务端要求可信身份会话，当前浏览器尚未建立。", "A trusted identity session is required and this browser does not have one."],
    google_oauth_unavailable: ["尚未配置 Google OAuth。", "Google OAuth is not configured."],
    github_oauth_unavailable: ["尚未配置 GitHub OAuth。", "GitHub OAuth is not configured."],
    verification_challenge_missing: ["缺少安全验证上下文。", "Secure verification context is missing."],
    verification_code_invalid: ["验证码必须是 6 位数字。", "The verification code must contain six digits."],
    display_name_missing: ["注册时需要填写显示名称。", "A display name is required for registration."],
    identity_handoff_invalid: ["身份服务没有完成可信控制台跳转。", "The identity service did not complete the trusted console handoff."],
    email_invalid: ["请输入有效邮箱。", "Enter a valid email address."]
  };
  const selected = known[code];
  if (selected) return selected[zh ? 0 : 1];
  if (error instanceof AuthApiError && error.status === 401) return zh ? "服务端要求可信身份会话。" : "A trusted identity session is required.";
  if (error instanceof AuthApiError && error.status === 429) return zh ? "请求过于频繁，请稍后再试。" : "Too many attempts. Try again later.";
  return zh ? "身份请求未完成。请查看 API 参考中的能力状态。" : "The identity request did not complete. Check capability status in API reference.";
}
