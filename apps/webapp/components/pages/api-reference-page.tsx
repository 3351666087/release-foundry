"use client";

import { useMemo, useState } from "react";
import { Check, Copy, FileJson2, Search, ShieldCheck } from "lucide-react";

import { apiEndpoints, apiGroups, apiReferenceMeta, type ApiEndpoint, type ApiStatus } from "@/lib/api-reference";
import { useI18n } from "@/lib/i18n";
import { PageHeader, StatusBadge } from "../ui";
import styles from "./api-reference-page.module.css";

type GroupFilter = (typeof apiGroups)[number]["id"];

export function ApiReferencePage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [group, setGroup] = useState<GroupFilter>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(apiEndpoints[0].id);
  const [copied, setCopied] = useState(false);

  const visibleEndpoints = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return apiEndpoints.filter((endpoint) => {
      const inGroup = group === "all" || endpoint.group === group;
      const searchable = `${endpoint.method} ${endpoint.path} ${endpoint.owner} ${endpoint.title.zh} ${endpoint.title.en} ${endpoint.description.zh} ${endpoint.description.en} ${JSON.stringify(endpoint.response)}`.toLowerCase();
      return inGroup && (!normalized || searchable.includes(normalized));
    });
  }, [group, query]);

  const endpoint = visibleEndpoints.find((item) => item.id === selectedId) || visibleEndpoints[0] || null;
  const implemented = apiEndpoints.filter((item) => item.status === "implemented").length;
  const draft = apiEndpoints.filter((item) => item.status === "draft").length;
  const blocked = apiEndpoints.filter((item) => item.status === "blocked").length;

  async function copyPath(value: string) {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <>
      <PageHeader
        eyebrow="DEVELOPER / API REFERENCE"
        title={zh ? "API 文档与参考" : "API docs and reference"}
        summary={zh
          ? "以 A1 执行与身份契约、A2 评测契约、A3 产品 API 为准的公开安全参考。"
          : "A public-safe reference grounded in A1 execution and identity, A2 judging, and A3 product contracts."}
        meta={<><span>{zh ? "校准版本" : "Calibrated"}</span><StatusBadge value={apiReferenceMeta.calibratedAt} tone="info" /></>}
      />

      <section className={styles.releaseBand} aria-label={zh ? "契约状态" : "Contract status"}>
        <div><span>{zh ? "接口条目" : "Endpoints"}</span><strong>{apiEndpoints.length}</strong></div>
        <div><span>{zh ? "已实现" : "Implemented"}</span><strong>{implemented}</strong></div>
        <div><span>{zh ? "草案分支" : "Draft branch"}</span><strong>{draft}</strong></div>
        <div><span>{zh ? "契约阻塞" : "Contract blocker"}</span><strong>{blocked}</strong></div>
        <div className={styles.authority}>
          <ShieldCheck size={18} />
          <span>{zh ? "权威边界" : "Authority"}</span>
          <strong>A1 Capture · A2 Judge · A3 Operate</strong>
        </div>
      </section>

      <section className={styles.upstreamDelta} aria-label={zh ? "上游契约更新" : "Upstream contract delta"}>
        <header>
          <span>UPSTREAM DRAFT DELTA / 2026-07-11</span>
          <strong>{zh ? "A1 会话链与 A2 判定链已经前进，首次 OAuth 登录仍未完成" : "A1 session and A2 decision chains advanced; initial OAuth sign-in remains incomplete"}</strong>
        </header>
        <div>
          <article>
            <span>A1 · {apiReferenceMeta.a1Sha}</span>
            <strong>{zh ? "安全浏览器会话" : "Secure browser session"}</strong>
            <p>{zh ? "邮箱 login/recovery 可签发双 HttpOnly Cookie，并支持同源轮换、幂等重放和复用检测。Google/GitHub 仍只有账号绑定。" : "Email login/recovery can issue paired HttpOnly cookies with same-origin rotation, idempotent replay, and reuse detection. Google/GitHub remain account-linking only."}</p>
            <StatusBadge value={zh ? "Draft 已实现" : "Draft implemented"} tone="warn" />
          </article>
          <article>
            <span>A2 · {apiReferenceMeta.a2Sha}</span>
            <strong>{zh ? "可信证据与决策账本" : "Trusted evidence and decision ledger"}</strong>
            <p>{zh ? "新增多模态 evidence snapshot 与 append-only decision ledger；A3 只能读取 decision、provenance hash 和 chain 状态。" : "Adds a multimodal evidence snapshot and append-only decision ledger; A3 may only read the decision, provenance hash, and chain state."}</p>
            <div className={styles.schemaTags}>
              <code>{apiReferenceMeta.a2EvidenceSnapshotSchema}</code>
              <code>{apiReferenceMeta.a2DecisionLedgerSchema}</code>
            </div>
            <StatusBadge value={zh ? "Draft 已实现" : "Draft implemented"} tone="warn" />
          </article>
        </div>
      </section>

      <section className={styles.referenceTool}>
        <header className={styles.toolbar}>
          <label className={styles.searchBox}>
            <Search size={16} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={zh ? "搜索路径、方法或负责人" : "Search path, method, or owner"}
              aria-label={zh ? "搜索 API" : "Search APIs"}
            />
          </label>
          <div className={styles.groupControl} role="group" aria-label={zh ? "接口分类" : "API groups"}>
            {apiGroups.map((item) => (
              <button
                type="button"
                key={item.id}
                aria-pressed={group === item.id}
                onClick={() => setGroup(item.id)}
              >
                {zh ? item.label.zh : item.label.en}
              </button>
            ))}
          </div>
        </header>

        <div className={styles.referenceLayout}>
          <nav className={styles.endpointRail} aria-label={zh ? "API 端点" : "API endpoints"}>
            <div className={styles.railHeading}>
              <span>{zh ? "端点目录" : "Endpoint index"}</span>
              <strong>{visibleEndpoints.length}</strong>
            </div>
            {visibleEndpoints.map((item) => (
              <button
                type="button"
                key={item.id}
                className={endpoint?.id === item.id ? styles.endpointActive : styles.endpointButton}
                onClick={() => setSelectedId(item.id)}
              >
                <span className={`${styles.method} ${styles[`method${item.method}`]}`}>{item.method}</span>
                <span><strong>{zh ? item.title.zh : item.title.en}</strong><small>{item.path}</small></span>
                <i data-status={item.status} aria-label={statusLabel(item.status, zh)} />
              </button>
            ))}
            {visibleEndpoints.length === 0 && (
              <div className={styles.noResults}>{zh ? "没有匹配的接口" : "No matching endpoints"}</div>
            )}
          </nav>

          {endpoint && (
            <article className={styles.endpointDetail}>
              <header className={styles.detailHeader}>
                <div>
                  <div className={styles.detailMeta}>
                    <span className={`${styles.method} ${styles[`method${endpoint.method}`]}`}>{endpoint.method}</span>
                    <span className={styles.owner}>{endpoint.owner}</span>
                    <StatusBadge value={statusLabel(endpoint.status, zh)} tone={statusTone(endpoint.status)} />
                  </div>
                  <h2>{zh ? endpoint.title.zh : endpoint.title.en}</h2>
                  <p>{zh ? endpoint.description.zh : endpoint.description.en}</p>
                </div>
                <button
                  type="button"
                  className={styles.copyButton}
                  onClick={() => copyPath(`${endpoint.method} ${endpoint.path}`)}
                  title={zh ? "复制方法和路径" : "Copy method and path"}
                >
                  {copied ? <Check size={17} /> : <Copy size={17} />}
                  <span>{copied ? (zh ? "已复制" : "Copied") : (zh ? "复制" : "Copy")}</span>
                </button>
              </header>

              <div className={styles.pathBar}>
                <FileJson2 size={17} aria-hidden="true" />
                <code>{endpoint.path}</code>
              </div>

              <dl className={styles.contractFacts}>
                <div><dt>{zh ? "负责人" : "Owner"}</dt><dd>{endpoint.owner}</dd></div>
                <div><dt>{zh ? "认证" : "Authentication"}</dt><dd>{zh ? endpoint.auth.zh : endpoint.auth.en}</dd></div>
                <div><dt>{zh ? "契约来源" : "Contract source"}</dt><dd>{endpoint.source}</dd></div>
              </dl>

              <div className={styles.payloadGrid}>
                {endpoint.request !== undefined && (
                  <PayloadBlock title={zh ? "请求示例" : "Request example"} value={endpoint.request} />
                )}
                <PayloadBlock title={zh ? "响应示例" : "Response example"} value={endpoint.response} />
              </div>

              <section className={styles.notes}>
                <span>{zh ? "边界与注意事项" : "Boundaries and notes"}</span>
                <ul>{endpoint.notes.map((note) => <li key={note.en}>{zh ? note.zh : note.en}</li>)}</ul>
              </section>
            </article>
          )}
        </div>
      </section>

      <footer className={styles.sourceFooter}>
        <span>main {apiReferenceMeta.mainSha}</span>
        <span>A1 {apiReferenceMeta.a1Sha} · open draft</span>
        <span>A2 {apiReferenceMeta.a2Sha}</span>
        <span>{zh ? "不包含 key、token、cookie 或真实账号数据" : "No keys, tokens, cookies, or real account data"}</span>
      </footer>
    </>
  );
}

function PayloadBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <section className={styles.payloadBlock}>
      <header><span>{title}</span><small>application/json</small></header>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

function statusLabel(status: ApiStatus, zh: boolean) {
  const labels = {
    implemented: zh ? "已实现" : "Implemented",
    draft: zh ? "草案分支" : "Draft branch",
    blocked: zh ? "契约阻塞" : "Contract blocked"
  } as const;
  return labels[status];
}

function statusTone(status: ApiStatus): "pass" | "warn" | "fail" {
  if (status === "implemented") return "pass";
  if (status === "draft") return "warn";
  return "fail";
}
