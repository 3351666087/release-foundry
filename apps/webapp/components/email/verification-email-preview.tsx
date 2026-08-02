import { ArrowRight, LockKeyhole, PackageCheck, ShieldCheck } from "lucide-react";

import styles from "./verification-email-preview.module.css";

export function VerificationEmailPreview({ zh }: { zh: boolean }) {
  return (
    <article className={styles.email} aria-label={zh ? "验证码邮件设计预览" : "Verification email design preview"}>
      <header className={styles.header}>
        <div className={styles.brand}><span><PackageCheck size={16} strokeWidth={1.9} aria-hidden="true" /></span><strong>RELEASEFOUNDRY</strong></div>
        <span className={styles.security}><ShieldCheck size={13} /> SECURITY MESSAGE</span>
      </header>
      <div className={styles.body}>
        <span className={styles.eyebrow}>IDENTITY / EMAIL VERIFICATION</span>
        <h3>{zh ? "确认你的邮箱" : "Confirm your email"}</h3>
        <p>{zh ? "使用下面的验证码完成 ReleaseFoundry 工作区注册。" : "Use this code to complete your ReleaseFoundry workspace registration."}</p>
        <div className={styles.code} aria-label={zh ? "示例验证码" : "Example verification code"}>
          {["8", "4", "2", "9", "1", "7"].map((digit, index) => <span key={`${digit}-${index}`}>{digit}</span>)}
        </div>
        <div className={styles.expiry}><LockKeyhole size={14} /><span>{zh ? "10 分钟内有效 · 仅可使用一次" : "Expires in 10 minutes · Single use"}</span></div>
        <span className={styles.action}>{zh ? "打开安全验证页" : "Open secure verification"}<ArrowRight size={15} /></span>
      </div>
      <footer>
        <strong>{zh ? "不是你本人操作？" : "Wasn't you?"}</strong>
        <span>{zh ? "忽略这封邮件即可。ReleaseFoundry 不会在邮件中索要密码或 API key。" : "Ignore this email. ReleaseFoundry never asks for passwords or API keys by email."}</span>
      </footer>
    </article>
  );
}
