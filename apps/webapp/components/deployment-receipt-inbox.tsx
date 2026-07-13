"use client";

import { type FormEvent, useMemo, useState } from "react";
import {
  CheckCircle2,
  FileCheck2,
  Inbox,
  LoaderCircle,
  RefreshCw,
  Send,
  ShieldCheck,
  XCircle
} from "lucide-react";

import { array, number, record, string, type JsonRecord } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useDashboard } from "./dashboard-provider";
import { DataTable, StatusBadge } from "./ui";

type ActionKind = "idle" | "loading" | "acknowledged" | "rejected" | "conflict" | "denied" | "failed";
type ActionState = { kind: ActionKind; message: string };

export function DeploymentReceiptInbox({ inbox, projection = {} }: { inbox: JsonRecord; projection?: JsonRecord }) {
  const { language } = useI18n();
  const { source, reload } = useDashboard();
  const zh = language === "zh-CN";
  const slots = useMemo(() => array(inbox.slots).map(record), [inbox.slots]);
  const receipts = useMemo(() => array(inbox.receipts).map(record), [inbox.receipts]);
  const readbacks = useMemo(() => array(inbox.authoritative_readbacks).map(record), [inbox.authoritative_readbacks]);
  const projectionSummary = record(projection.summary);
  const [blockerId, setBlockerId] = useState(() => string(slots[0]?.blocker_id, ""));
  const [evidenceRef, setEvidenceRef] = useState("");
  const [evidenceHash, setEvidenceHash] = useState("");
  const [capturedAt, setCapturedAt] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [action, setAction] = useState<ActionState>({ kind: "idle", message: "" });
  const selectedSlot = slots.find((slot) => string(slot.blocker_id) === blockerId) || slots[0] || {};
  const candidateId = string(inbox.candidate_id, "unknown");
  const runId = string(inbox.run_id, "unknown");
  const verifiedCount = number(inbox.production_verified_count);
  const sourcePassed = number(projection.source_passed);
  const totalChecks = number(projectionSummary.total_checks);
  const projectedPassed = number(projectionSummary.projected_passed);
  const requiresRebuild = projection.requires_acceptance_rebuild === true;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedHash = evidenceHash.trim().toLowerCase().replace(/^sha256:/, "");
    if (!/^[a-f0-9]{64}$/.test(normalizedHash)) {
      setAction({ kind: "failed", message: zh ? "SHA-256 必须是 64 位十六进制字符。" : "SHA-256 must contain 64 hexadecimal characters." });
      return;
    }
    if (!capturedAt || !Number.isFinite(Date.parse(capturedAt))) {
      setAction({ kind: "failed", message: zh ? "请选择有效的证据采集时间。" : "Select a valid evidence capture time." });
      return;
    }

    setBusyKey("submit");
    setAction({ kind: "loading", message: zh ? "正在提交回执元数据..." : "Submitting receipt metadata..." });
    try {
      const result = await postDeploymentReceipt(source, {
        blocker_id: string(selectedSlot.blocker_id),
        candidate_id: candidateId,
        run_id: runId,
        evidence_ref: evidenceRef.trim(),
        evidence_sha256: normalizedHash,
        evidence_kind: string(selectedSlot.evidence_kind),
        verifier_class: string(selectedSlot.verifier_class),
        captured_at: new Date(capturedAt).toISOString()
      });
      setAction({
        kind: "acknowledged",
        message: zh
          ? `回执 ${string(result.receipt_id)} 已进入待复核队列。`
          : `Receipt ${string(result.receipt_id)} entered the review queue.`
      });
      setEvidenceRef("");
      setEvidenceHash("");
      window.setTimeout(reload, 650);
    } catch (reason) {
      setAction(actionError(reason, zh));
    } finally {
      setBusyKey(null);
    }
  }

  async function reviewReceipt(receipt: JsonRecord, reviewAction: "acknowledge" | "reject") {
    const receiptId = string(receipt.receipt_id);
    const key = `${receiptId}:${reviewAction}`;
    setBusyKey(key);
    setAction({ kind: "loading", message: zh ? "正在保存复核结果..." : "Saving review result..." });
    try {
      const result = await postDeploymentReceiptReview(source, receiptId, {
        action: reviewAction,
        reason_code: reviewAction === "acknowledge" ? "metadata_complete" : "stale_evidence",
        expected_version: number(receipt.version)
      });
      const kind = string(result.status) === "rejected" ? "rejected" : "acknowledged";
      setAction({
        kind,
        message: kind === "rejected"
          ? (zh ? `回执 ${receiptId} 已拒绝。` : `Receipt ${receiptId} was rejected.`)
          : (zh ? `回执 ${receiptId} 已确认元数据完整。` : `Receipt ${receiptId} metadata was acknowledged.`)
      });
      window.setTimeout(reload, 650);
    } catch (reason) {
      setAction(actionError(reason, zh));
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="deployment-receipt-inbox" data-testid="deployment-receipt-inbox">
      <div className="receipt-inbox-summary">
        <div><Inbox size={22} /><span>{zh ? "回执总数" : "Receipts"}</span><strong>{number(inbox.receipt_count)}</strong></div>
        <div><FileCheck2 size={22} /><span>{zh ? "已提交或确认" : "Submitted / acknowledged"}</span><strong>{number(inbox.submitted_or_acknowledged_count)}</strong></div>
        <div><RefreshCw size={22} /><span>{zh ? "仍缺槽位" : "Missing slots"}</span><strong>{number(inbox.missing_slot_count)}</strong></div>
        <div data-state={verifiedCount > 0 ? "authoritative" : "not-authoritative"}><ShieldCheck size={22} /><span>{zh ? "生产已验证" : "Production verified"}</span><strong>{verifiedCount}</strong></div>
      </div>

      <div className="receipt-safety-boundary" role="status">
        <ShieldCheck size={19} />
        <div>
          <strong>{zh ? "回执收件箱不是生产批准器" : "The receipt inbox is not a production approver"}</strong>
          <span>{zh
            ? "提交或确认只表示元数据已收集。只有服务器权威 resolver 的只读回读可标记单项验证；原始部署验收和权威发布判定不会被网页改写。"
            : "Submit or acknowledge only records metadata. Only a server-authoritative resolver readback can verify a check; source acceptance and release authority cannot be rewritten by this page."}</span>
        </div>
      </div>

      <div className="receipt-authority-projection" data-state={requiresRebuild ? "changed" : "unchanged"} data-testid="deployment-acceptance-projection">
        <header>
          <div>
            <ShieldCheck size={19} />
            <span>SERVER-ONLY READBACK</span>
            <strong>{zh ? "权威验证与验收投影" : "Authoritative verification and acceptance projection"}</strong>
          </div>
          <StatusBadge value={string(projection.status, "blocked")} tone={projection.projected_production_accepted === true ? "pass" : "warn"} />
        </header>
        <div className="receipt-projection-metrics">
          <div><span>{zh ? "原始正式验收" : "Source acceptance"}</span><strong>{sourcePassed}/{totalChecks}</strong><small>{zh ? "保持不变" : "unchanged"}</small></div>
          <div><span>{zh ? "只读投影" : "Read-only projection"}</span><strong>{projectedPassed}/{totalChecks}</strong><small>{zh ? "不能当作封存验收" : "not sealed acceptance"}</small></div>
          <div><span>{zh ? "权威回读" : "Authoritative readbacks"}</span><strong>{readbacks.length}</strong><small>{zh ? "哈希校验通过" : "hash-valid only"}</small></div>
          <div><span>{zh ? "需要重建验收" : "Acceptance rebuild"}</span><strong>{requiresRebuild ? (zh ? "是" : "Yes") : (zh ? "否" : "No")}</strong><small>{zh ? "需后端重新封存" : "server reseal required"}</small></div>
        </div>
        <p>{zh
          ? "浏览器没有权威验证按钮。内部验证接口只接受身份平台验证过的 service account，并由服务器 resolver 读取真实证据。"
          : "There is no browser verification control. The internal verifier accepts only a platform-verified service account and reads evidence through a server resolver."}</p>
      </div>

      <form className="deployment-receipt-form" onSubmit={submit}>
        <header>
          <div><span>METADATA INTAKE</span><strong>{zh ? "登记部署回执" : "Register deployment receipt"}</strong></div>
          <StatusBadge value={string(inbox.candidate_id) === "unknown" ? "unbound" : "candidate-bound"} tone={string(inbox.candidate_id) === "unknown" ? "fail" : "info"} />
        </header>
        <div className="receipt-form-grid">
          <label>
            <span>{zh ? "阻塞项" : "Blocker"}</span>
            <select value={string(selectedSlot.blocker_id, blockerId)} onChange={(event) => setBlockerId(event.target.value)} required>
              {slots.map((slot) => <option key={string(slot.blocker_id)} value={string(slot.blocker_id)}>{string(slot.label)}</option>)}
            </select>
          </label>
          <label>
            <span>{zh ? "证据引用" : "Evidence reference"}</span>
            <input value={evidenceRef} onChange={(event) => setEvidenceRef(event.target.value)} placeholder="receipt:deployment-health:20260713-001" required />
          </label>
          <label>
            <span>SHA-256</span>
            <input value={evidenceHash} onChange={(event) => setEvidenceHash(event.target.value)} placeholder="64 hex characters" minLength={64} maxLength={71} required />
          </label>
          <label>
            <span>{zh ? "采集时间" : "Captured at"}</span>
            <input type="datetime-local" value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} required />
          </label>
        </div>
        <div className="receipt-form-binding">
          <div><span>Candidate</span><code>{shortId(candidateId)}</code></div>
          <div><span>Run</span><code>{shortId(runId)}</code></div>
          <div><span>{zh ? "证据类型" : "Evidence kind"}</span><code>{string(selectedSlot.evidence_kind)}</code></div>
          <div><span>{zh ? "验证器" : "Verifier"}</span><code>{string(selectedSlot.verifier_class)}</code></div>
        </div>
        <button className="command-button receipt-submit" type="submit" disabled={busyKey !== null || !slots.length}>
          {busyKey === "submit" ? <LoaderCircle className="spin" size={15} /> : <Send size={15} />}
          {zh ? "提交元数据" : "Submit metadata"}
        </button>
      </form>

      {action.kind !== "idle" && (
        <div className="receipt-action-state" data-state={action.kind} role="status" aria-live="polite">
          {action.kind === "loading" ? <LoaderCircle className="spin" size={18} />
            : action.kind === "rejected" || action.kind === "denied" || action.kind === "failed" || action.kind === "conflict"
              ? <XCircle size={18} /> : <CheckCircle2 size={18} />}
          <span>{action.message}</span>
        </div>
      )}

      <DataTable headers={[zh ? "回执槽位" : "Receipt slot", zh ? "收件状态" : "Intake", zh ? "权威验证" : "Authority", zh ? "最新回执" : "Latest receipt", zh ? "复核" : "Review"]} label={zh ? "部署回执收件箱" : "Deployment receipt inbox"}>
        {slots.map((slot) => {
          const latest = record(slot.latest_receipt);
          const authority = record(latest.authority_validation);
          const verification = record(latest.production_verification);
          const status = string(slot.intake_status, "missing");
          const authorityStatus = latest.receipt_id ? string(authority.status, "awaiting_authoritative_readback") : "not_requested";
          const canReview = status === "submitted";
          return <tr key={string(slot.blocker_id)} data-intake-status={status}>
            <td><strong>{string(slot.label)}</strong><small><code>{string(slot.blocker_id)}</code> · {string(slot.owner)}</small></td>
            <td><StatusBadge value={status} tone={status === "acknowledged" ? "info" : status === "missing" ? "fail" : status === "rejected" ? "fail" : "warn"} /></td>
            <td className="receipt-authority-cell">
              <StatusBadge value={authorityStatus} tone={authority.production_verified === true ? "pass" : authorityStatus === "authoritative_rejected" ? "fail" : authorityStatus === "not_requested" ? "neutral" : "warn"} />
              {authority.authoritative_readback_id
                ? <small><code>{shortId(authority.authoritative_readback_id)}</code> · {string(verification.reason_code)}</small>
                : <small>{zh ? "等待服务器回读" : "Awaiting server readback"}</small>}
            </td>
            <td>{latest.receipt_id
              ? <><strong>{string(latest.receipt_id)}</strong><small>v{number(latest.version)} · {shortId(latest.evidence_sha256)}</small></>
              : <span className="receipt-missing">{zh ? "尚未提交" : "Not submitted"}</span>}</td>
            <td>
              {canReview ? <div className="receipt-review-actions">
                <button type="button" title={zh ? "确认元数据" : "Acknowledge metadata"} aria-label={zh ? `确认 ${string(latest.receipt_id)}` : `Acknowledge ${string(latest.receipt_id)}`} disabled={busyKey !== null} onClick={() => reviewReceipt(latest, "acknowledge")}>
                  {busyKey === `${string(latest.receipt_id)}:acknowledge` ? <LoaderCircle className="spin" size={15} /> : <CheckCircle2 size={15} />}
                </button>
                <button type="button" title={zh ? "拒绝回执" : "Reject receipt"} aria-label={zh ? `拒绝 ${string(latest.receipt_id)}` : `Reject ${string(latest.receipt_id)}`} disabled={busyKey !== null} onClick={() => reviewReceipt(latest, "reject")}>
                  <XCircle size={15} />
                </button>
              </div> : <span className="receipt-review-locked">{status === "missing" ? "-" : zh ? "已处理" : "closed"}</span>}
            </td>
          </tr>;
        })}
      </DataTable>
      {receipts.length > 0 && <p className="receipt-inbox-footnote">{zh
        ? `所有记录仅包含经过净化的元数据与哈希；当前有 ${readbacks.length} 条服务器权威回读。`
        : `All records contain sanitized metadata and hashes only; ${readbacks.length} server-authoritative readback(s) are attached.`}</p>}
    </div>
  );
}

async function postDeploymentReceipt(source: string, receipt: JsonRecord) {
  return postJson(`/api/a3/deployment/receipts?source=${encodeURIComponent(source)}`, { source, receipt });
}

async function postDeploymentReceiptReview(source: string, receiptId: string, review: JsonRecord) {
  return postJson(`/api/a3/deployment/receipts/${encodeURIComponent(receiptId)}/review?source=${encodeURIComponent(source)}`, { source, review });
}

async function postJson(path: string, body: JsonRecord): Promise<JsonRecord> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: {
        "content-type": "application/json",
        "idempotency-key": browserIdempotencyKey()
      },
      body: JSON.stringify(body)
    });
  } catch {
    throw { kind: "failed" };
  }
  if (!response.ok) {
    let payload: JsonRecord = {};
    try { payload = record(await response.json()); } catch { payload = {}; }
    throw {
      kind: response.status === 409 ? "conflict" : [401, 403].includes(response.status) ? "denied" : "failed",
      status: response.status,
      code: string(payload.error, "request_failed")
    };
  }
  return record(await response.json());
}

function actionError(reason: unknown, zh: boolean): ActionState {
  const error = record(reason);
  const kind = string(error.kind, "failed") as ActionKind;
  if (kind === "conflict") return { kind, message: zh ? "回执已被其他审核更新，请刷新后重试。" : "The receipt changed during review. Refresh and try again." };
  if (kind === "denied") return { kind, message: zh ? "当前账号没有执行此操作的权限。" : "Your account is not allowed to perform this action." };
  return { kind: "failed", message: zh ? "回执操作失败，现有部署状态没有改变。" : "Receipt action failed; deployment state was not changed." };
}

function browserIdempotencyKey() {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `a3-deployment-receipt-${random}`;
}

function shortId(value: unknown) {
  const normalized = string(value, "unavailable");
  return normalized.length > 24 ? `${normalized.slice(0, 12)}...${normalized.slice(-8)}` : normalized;
}
