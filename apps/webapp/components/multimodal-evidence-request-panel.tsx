"use client";

import { type FormEvent, useMemo, useState } from "react";
import { Ban, Check, ChevronDown, Clock3, FileInput, Plus, RefreshCw, Send, ShieldAlert, X } from "lucide-react";

import { array, number, record, string, type JsonRecord } from "@/lib/api";
import { useDashboard } from "./dashboard-provider";
import { EmptyState, formatDate, StatusBadge } from "./ui";

type ActionState = {
  kind: "idle" | "loading" | "success" | "denied" | "conflict" | "failed";
  message: string;
};

type PanelProps = {
  source: string;
  tenantScope: JsonRecord;
  queueItems: JsonRecord[];
  summary: JsonRecord;
  zh: boolean;
};

const evidenceKinds = [
  "a1_run_trace",
  "a1_tool_call",
  "a1_artifact",
  "a2_judge_receipt",
  "a2_review_receipt",
  "media_evidence",
  "provider_identity",
  "candidate_binding"
] as const;

const reasonOptions = [
  "execution_evidence_required",
  "evaluation_evidence_required",
  "media_evidence_required",
  "provider_identity_required",
  "candidate_binding_required"
] as const;

export function MultimodalEvidenceRequestPanel({ source, tenantScope, queueItems, summary, zh }: PanelProps) {
  const { reload } = useDashboard();
  const [creatingFor, setCreatingFor] = useState<string | null>(null);
  const [ownerLane, setOwnerLane] = useState("execution");
  const [requiredKinds, setRequiredKinds] = useState<string[]>(["a1_run_trace"]);
  const [reasonCode, setReasonCode] = useState<string>(reasonOptions[0]);
  const [dueAt, setDueAt] = useState(defaultDueAt);
  const [action, setAction] = useState<ActionState>({ kind: "idle", message: "" });
  const requests = useMemo(() => queueItems.flatMap((item) => (
    array(item.evidence_requests).map(record).map((request) => ({ item, request }))
  )), [queueItems]);

  async function createRequest(event: FormEvent<HTMLFormElement>, queueId: string) {
    event.preventDefault();
    if (!requiredKinds.length) {
      setAction({ kind: "failed", message: zh ? "至少选择一种证据" : "Select at least one evidence kind." });
      return;
    }
    const parsedDueAt = new Date(dueAt);
    if (Number.isNaN(parsedDueAt.getTime())) {
      setAction({ kind: "failed", message: zh ? "截止时间无效" : "The deadline is invalid." });
      return;
    }
    await mutate(
      `/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/evidence-requests?source=${encodeURIComponent(source)}`,
      {
        source,
        ...tenantScope,
        evidence_request: {
          expected_version: 0,
          owner_lane: ownerLane,
          required_evidence_kinds: requiredKinds,
          due_at: parsedDueAt.toISOString(),
          reason_code: reasonCode
        }
      },
      zh ? "补证请求已创建" : "Evidence request created."
    );
  }

  async function reviewRequest(queueId: string, requestId: string, version: number, reviewAction: "accept" | "reject" | "cancel") {
    const reason = {
      accept: "evidence_hashes_verified",
      reject: "evidence_binding_incomplete",
      cancel: "evidence_request_cancelled"
    }[reviewAction];
    await mutate(
      `/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/evidence-requests/${encodeURIComponent(requestId)}/review?source=${encodeURIComponent(source)}`,
      {
        source,
        ...tenantScope,
        review: { expected_version: version, action: reviewAction, reason_code: reason }
      },
      zh ? "补证状态已更新" : "Evidence-request state updated."
    );
  }

  async function mutate(path: string, body: JsonRecord, successMessage: string) {
    setAction({ kind: "loading", message: zh ? "正在提交..." : "Submitting..." });
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
      setAction({ kind: "failed", message: zh ? "网络连接失败，请重试" : "Network request failed. Retry." });
      return;
    }
    if (response.ok) {
      setAction({ kind: "success", message: successMessage });
      setCreatingFor(null);
      reload();
      return;
    }
    if (response.status === 401 || response.status === 403) {
      setAction({ kind: "denied", message: zh ? "当前账号没有执行此操作的权限" : "Your account cannot perform this action." });
      return;
    }
    if (response.status === 409) {
      setAction({ kind: "conflict", message: zh ? "数据已被其他人更新，请刷新后重试" : "The request changed. Refresh and retry." });
      return;
    }
    setAction({ kind: "failed", message: zh ? "操作失败，请稍后重试" : "The action failed. Retry later." });
  }

  return (
    <div className="evidence-request-workflow" data-state={action.kind}>
      <div className="evidence-request-heading">
        <div>
          <span className="eyebrow">EVIDENCE REQUESTS / HASH-ONLY</span>
          <h3>{zh ? "审核补证" : "Review evidence requests"}</h3>
        </div>
        <div className="evidence-request-totals" aria-label={zh ? "补证请求统计" : "Evidence-request totals"}>
          <span>{zh ? "总计" : "Total"}<strong>{number(summary.evidence_request_count)}</strong></span>
          <span>{zh ? "待补" : "Open"}<strong>{number(summary.evidence_request_open_count)}</strong></span>
          <span>{zh ? "超期" : "Overdue"}<strong>{number(summary.evidence_request_overdue_count)}</strong></span>
          <span>{zh ? "待验" : "Submitted"}<strong>{number(summary.evidence_request_submitted_count)}</strong></span>
          <span>{zh ? "已收" : "Accepted"}<strong>{number(summary.evidence_request_accepted_count)}</strong></span>
        </div>
      </div>

      {action.kind !== "idle" && (
        <div className="evidence-request-notice" role="status" data-kind={action.kind}>
          {action.kind === "loading" ? <RefreshCw className="spin" size={15} /> : <ShieldAlert size={15} />}
          <span>{action.message}</span>
          {["denied", "conflict", "failed"].includes(action.kind) && (
            <button type="button" onClick={reload} title={zh ? "重新加载" : "Reload"}><RefreshCw size={14} /></button>
          )}
        </div>
      )}

      <div className="evidence-request-queue">
        {queueItems.map((item) => {
          const queueId = string(item.queue_id);
          const operational = record(item.operational_state);
          const itemRequests = array(item.evidence_requests).map(record);
          const canRequest = string(operational.status) === "claimed";
          return (
            <article key={queueId} className="evidence-request-case">
              <header>
                <div><small>{zh ? "案例" : "Case"}</small><strong>{string(item.case_id)}</strong></div>
                <StatusBadge value={assignmentLabel(operational.status, zh)} tone={canRequest ? "pass" : "warn"} />
                <button
                  type="button"
                  className="evidence-request-create-toggle"
                  disabled={!canRequest || action.kind === "loading"}
                  onClick={() => setCreatingFor((current) => current === queueId ? null : queueId)}
                >
                  <Plus size={15} />{zh ? "请求补证" : "Request evidence"}<ChevronDown size={14} />
                </button>
              </header>

              {creatingFor === queueId && (
                <form className="evidence-request-form" onSubmit={(event) => createRequest(event, queueId)}>
                  <label><span>{zh ? "责任通道" : "Owner lane"}</span><select value={ownerLane} onChange={(event) => setOwnerLane(event.target.value)}><option value="execution">{zh ? "执行平台" : "Execution"}</option><option value="evaluation">{zh ? "评测策略" : "Evaluation"}</option><option value="customer_operator">{zh ? "客户运营" : "Customer operator"}</option></select></label>
                  <label><span>{zh ? "截止时间" : "Deadline"}</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
                  <label><span>{zh ? "原因" : "Reason"}</span><select value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>{reasonOptions.map((reason) => <option value={reason} key={reason}>{reasonLabel(reason, zh)}</option>)}</select></label>
                  <fieldset><legend>{zh ? "所需证据" : "Required evidence"}</legend><div>{evidenceKinds.map((kind) => <label key={kind}><input type="checkbox" checked={requiredKinds.includes(kind)} onChange={() => setRequiredKinds((current) => current.includes(kind) ? current.filter((value) => value !== kind) : [...current, kind])} /><span>{evidenceKindLabel(kind, zh)}</span></label>)}</div></fieldset>
                  <div className="evidence-request-form-actions"><button type="button" onClick={() => setCreatingFor(null)}><X size={15} />{zh ? "取消" : "Cancel"}</button><button type="submit" disabled={action.kind === "loading"}><Send size={15} />{zh ? "发送请求" : "Send request"}</button></div>
                </form>
              )}

              {itemRequests.length ? (
                <div className="evidence-request-list">
                  {itemRequests.map((request) => {
                    const status = string(request.status, "open");
                    const requestId = string(request.request_id);
                    const refs = array(request.evidence_refs).map(record);
                    return (
                      <div className="evidence-request-item" key={requestId} data-status={status}>
                        <div className="evidence-request-state">
                          <StatusBadge value={requestStatusLabel(status, zh)} tone={requestStatusTone(status)} />
                          <strong>{ownerLaneLabel(request.owner_lane, zh)}</strong>
                          <span><Clock3 size={13} />{formatDate(string(request.due_at))}</span>
                          <code title={requestId}>{hashPrefix(requestId)}</code>
                        </div>
                        <div className="evidence-kind-list">{array(request.required_evidence_kinds).map((kind) => <span key={string(kind)}>{evidenceKindLabel(string(kind), zh)}</span>)}</div>
                        {refs.length ? <div className="evidence-hash-list">{refs.map((reference, index) => <div key={`${string(reference.kind)}-${index}`}><FileInput size={13} /><span>{evidenceKindLabel(string(reference.kind), zh)}</span><code title={string(reference.evidence_hash)}>{hashPrefix(string(reference.evidence_hash))}</code></div>)}</div> : <span className="evidence-awaiting">{zh ? "等待责任方提交哈希证据" : "Waiting for hash evidence"}</span>}
                        <div className="evidence-request-item-actions">
                          {status === "submitted" && <><button type="button" disabled={action.kind === "loading"} onClick={() => reviewRequest(queueId, requestId, number(request.version), "accept")}><Check size={14} />{zh ? "接受" : "Accept"}</button><button type="button" disabled={action.kind === "loading"} onClick={() => reviewRequest(queueId, requestId, number(request.version), "reject")}><X size={14} />{zh ? "退回" : "Reject"}</button></>}
                          {["open", "overdue", "submitted"].includes(status) && <button type="button" disabled={action.kind === "loading"} onClick={() => reviewRequest(queueId, requestId, number(request.version), "cancel")}><Ban size={14} />{zh ? "取消请求" : "Cancel request"}</button>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="evidence-request-empty">
                  <FileInput size={17} aria-hidden="true" />
                  <div><strong>{zh ? "暂无补证请求" : "No evidence requests"}</strong><span>{zh ? "当前案例没有待补充的执行、评测或媒体证据。" : "No outstanding execution, evaluation, or media evidence."}</span></div>
                </div>
              )}
            </article>
          );
        })}
      </div>

      {!queueItems.length && <EmptyState title={zh ? "暂无可审核案例" : "No review cases"} detail={zh ? "接入多模态分歧队列后可创建补证请求。" : "Ingest a multimodal disagreement queue before requesting evidence."} />}
      <div className="evidence-request-boundary"><ShieldAlert size={15} /><span>{zh ? "接受补证只确认材料完整，不代表真人裁决，也不会改变评分或发布状态。" : "Accepting evidence confirms material completeness only; it is not a human disposition and cannot change grading or release state."}</span></div>
    </div>
  );
}

function defaultDueAt() {
  const value = new Date(Date.now() + 24 * 60 * 60 * 1000);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
}

function browserIdempotencyKey() {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? `web-${crypto.randomUUID()}`
    : `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function requestStatusTone(value: string): "pass" | "warn" | "fail" {
  if (value === "accepted") return "pass";
  if (value === "overdue") return "fail";
  return "warn";
}

function requestStatusLabel(value: string, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    open: ["待补充", "open"],
    overdue: ["已超期", "overdue"],
    submitted: ["待验收", "submitted"],
    accepted: ["已接收", "accepted"],
    cancelled: ["已取消", "cancelled"]
  };
  return labels[value]?.[zh ? 0 : 1] || value;
}

function assignmentLabel(value: unknown, zh: boolean) {
  return string(value) === "claimed" ? (zh ? "审核中" : "claimed") : (zh ? "未领取" : "unassigned");
}

function ownerLaneLabel(value: unknown, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    execution: ["执行平台", "Execution"],
    evaluation: ["评测策略", "Evaluation"],
    customer_operator: ["客户运营", "Customer operator"]
  };
  const key = string(value);
  return labels[key]?.[zh ? 0 : 1] || key;
}

function evidenceKindLabel(value: string, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    a1_run_trace: ["运行链路", "Run trace"],
    a1_tool_call: ["工具调用", "Tool call"],
    a1_artifact: ["执行产物", "Execution artifact"],
    a2_judge_receipt: ["评测回执", "Judge receipt"],
    a2_review_receipt: ["真人复核回执", "Human-review receipt"],
    media_evidence: ["媒体证据", "Media evidence"],
    provider_identity: ["模型来源", "Provider identity"],
    candidate_binding: ["候选版本绑定", "Candidate binding"]
  };
  return labels[value]?.[zh ? 0 : 1] || value;
}

function reasonLabel(value: string, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    execution_evidence_required: ["补充执行证据", "Execution evidence required"],
    evaluation_evidence_required: ["补充评测证据", "Evaluation evidence required"],
    media_evidence_required: ["补充媒体证据", "Media evidence required"],
    provider_identity_required: ["确认模型来源", "Provider identity required"],
    candidate_binding_required: ["确认候选版本", "Candidate binding required"]
  };
  return labels[value]?.[zh ? 0 : 1] || value;
}

function hashPrefix(value: string) {
  return value.length > 22 ? `${value.slice(0, 18)}...` : value;
}
