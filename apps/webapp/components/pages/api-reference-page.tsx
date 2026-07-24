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
          ? "以运行与身份契约、评测契约和产品 API 为准的公开安全参考。"
          : "A public-safe reference grounded in runtime, identity, evaluation, and product contracts."}
        meta={<><span>{zh ? "校准版本" : "Calibrated"}</span><StatusBadge value={apiReferenceMeta.calibratedAt} tone="info" /></>}
      />

      <section className={styles.releaseBand} aria-label={zh ? "契约状态" : "Contract status"}>
        <div><span>{zh ? "接口条目" : "Endpoints"}</span><strong>{apiEndpoints.length}</strong></div>
        <div><span>{zh ? "已实现" : "Implemented"}</span><strong>{implemented}</strong></div>
        <div><span>{zh ? "本地草案" : "Local draft"}</span><strong>{draft}</strong></div>
        <div><span>{zh ? "契约阻塞" : "Contract blocker"}</span><strong>{blocked}</strong></div>
        <div className={styles.authority}>
          <ShieldCheck size={18} />
          <span>{zh ? "权威边界" : "Authority"}</span>
          <strong>{zh ? "运行平台 · 评测策略 · 产品工作流" : "Runtime · Evaluation · Product workflow"}</strong>
        </div>
      </section>

      <section className={styles.upstreamDelta} aria-label={zh ? "上游契约更新" : "Upstream contract delta"}>
        <header>
          <span>UPSTREAM A1 INTEGRATION / 2026-07-24</span>
          <strong>{zh ? "邮箱注册登录已接入 A3；首次 OAuth、登录态读取与退出仍未完成" : "Email registration and sign-in are integrated into A3; initial OAuth, session identity read, and logout remain incomplete"}</strong>
        </header>
        <div>
          <article>
            <span>{zh ? "运行与身份平台" : "Runtime and identity"} · {apiReferenceMeta.a1Sha}</span>
            <strong>{zh ? "安全浏览器会话" : "Secure browser session"}</strong>
            <p>{zh ? "邮箱注册和登录会返回短期 challenge/intent，并通过同源 303 签发双 HttpOnly Cookie。Google/GitHub 生产首次登录、Cookie 版 /v1/me 和 logout 仍是明确缺口。" : "Email registration and sign-in return short-lived challenge/intent handles and issue paired HttpOnly cookies through a same-origin 303 handoff. Production Google/GitHub first login, cookie-based /v1/me, and logout remain explicit gaps."}</p>
            <StatusBadge value={zh ? "A3 分支已集成" : "Integrated in A3 branch"} tone="pass" />
          </article>
          <article>
            <span>{zh ? "评测与决策服务" : "Evaluation and decision"} · {apiReferenceMeta.a2Sha}</span>
            <strong>{zh ? "可信证据与决策账本" : "Trusted evidence and decision ledger"}</strong>
            <p>{zh ? "可信链会直接校验运行结果、五层作用域与 validation_errors；产品控制台只读取 decision、provenance hash 和 chain 状态。" : "The trusted spine directly validates run results, five-level scope, and validation_errors; the product console only reads decision, provenance hash, and chain state."}</p>
            <div className={styles.schemaTags}>
              <code>{apiReferenceMeta.a2EvidenceSnapshotSchema}</code>
              <code>{apiReferenceMeta.a2DecisionLedgerSchema}</code>
              <code>{apiReferenceMeta.a2TrustedSpineSchema}</code>
              {apiReferenceMeta.a2RequiredScope.map((field) => <code key={field}>{field}</code>)}
            </div>
            <StatusBadge value={zh ? "main 已集成" : "Integrated in main"} tone="pass" />
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
                    <span className={styles.owner}>{ownerDisplay(endpoint.owner, zh)}</span>
                    <StatusBadge value={statusLabel(endpoint.status, zh)} tone={statusTone(endpoint.status)} />
                  </div>
                  <h2>{zh ? endpoint.title.zh : endpoint.title.en}</h2>
                  <p>{productCopy(zh ? endpoint.description.zh : endpoint.description.en, zh)}</p>
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
                <div><dt>{zh ? "负责人" : "Owner"}</dt><dd>{ownerDisplay(endpoint.owner, zh)}</dd></div>
                <div><dt>{zh ? "认证" : "Authentication"}</dt><dd>{productCopy(zh ? endpoint.auth.zh : endpoint.auth.en, zh)}</dd></div>
                <div><dt>{zh ? "契约来源" : "Contract source"}</dt><dd>{productCopy(endpoint.source, zh)}</dd></div>
              </dl>

              <div className={styles.payloadGrid}>
                {endpoint.request !== undefined && (
                  <PayloadBlock title={zh ? "请求示例" : "Request example"} value={endpoint.request} />
                )}
                <PayloadBlock title={zh ? "响应示例" : "Response example"} value={endpoint.response} />
              </div>

              <section className={styles.notes}>
                <span>{zh ? "边界与注意事项" : "Boundaries and notes"}</span>
                <ul>{endpoint.notes.map((note) => <li key={note.en}>{productCopy(zh ? note.zh : note.en, zh)}</li>)}</ul>
              </section>
            </article>
          )}
        </div>
      </section>

      <footer className={styles.sourceFooter}>
        <span>main {apiReferenceMeta.mainSha}</span>
        <span>{zh ? "运行平台" : "Runtime"} {apiReferenceMeta.a1LatestPeerSha} · merged into A3</span>
        <span>{zh ? "评测服务" : "Evaluation"} {apiReferenceMeta.a2Sha} · merged to main</span>
        <span>{zh ? "不包含 key、token、cookie 或真实账号数据" : "No keys, tokens, cookies, or real account data"}</span>
      </footer>
    </>
  );
}

function ownerDisplay(owner: string, zh: boolean): string {
  const labels: Record<string, [string, string]> = {
    A1: ["运行与身份平台", "Runtime and identity"],
    A2: ["评测与决策服务", "Evaluation and decision"],
    A3: ["产品工作流", "Product workflow"],
    "A1/A2/A3": ["跨服务契约", "Cross-service contract"]
  };
  const value = labels[owner];
  return value ? value[zh ? 0 : 1] : owner;
}

function productCopy(value: string, zh: boolean): string {
  const labels: Array<[RegExp, string, string]> = [
    [/A1\/A2\/A3/g, "跨服务契约", "cross-service contract"],
    [/A1\/A3/g, "平台与产品", "platform and product"],
    [/A1\/A2/g, "执行与评测", "execution and evaluation"],
    [/\bA1\b/g, "运行与身份平台", "runtime and identity platform"],
    [/\bA2\b/g, "评测与决策服务", "evaluation and decision service"],
    [/\bA3\b/g, "产品工作流", "product workflow"]
  ];
  return labels.reduce((copy, [pattern, chinese, english]) => copy.replace(pattern, zh ? chinese : english), value);
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
    draft: zh ? "本地草案" : "Local draft",
    blocked: zh ? "契约阻塞" : "Contract blocked"
  } as const;
  return labels[status];
}

function statusTone(status: ApiStatus): "pass" | "warn" | "fail" {
  if (status === "implemented") return "pass";
  if (status === "draft") return "warn";
  return "fail";
}
