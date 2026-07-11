"use client";

import { CreditCard, Landmark, ReceiptText, WalletCards } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

export function BillingPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  return <DataBoundary>{(model) => {
    const admin = record(model.raw.saas_admin_console);
    const usage = record(model.raw.usage_ledger);
    const readiness = record(model.raw.billing_readiness);
    const plan = record(usage.plan);
    const quota = record(usage.quota);
    const invoice = record(readiness.invoice_preview);
    const meters = array(usage.meters).map(record);
    const lineItems = array(invoice.line_items).map(record);
    const billingAccount = record(admin.billing_account);
    return (
      <>
        <PageHeader
          eyebrow="ADMIN / USAGE & BILLING"
          title={zh ? "用量与计费" : "Usage and billing"}
          summary={zh ? "用 A1 计量事件解释账单，用 A2 风险状态解释发布影响。" : "Explain billing with A1 usage events and release impact with A2 risk state."}
          meta={<><span>{string(plan.name, string(plan.tier, "local-readonly"))}</span><StatusBadge value={string(readiness.status)} /></>}
          actions={<button type="button" className="command-button" disabled title={zh ? "等待真实支付后端" : "Requires live payment backend"}><CreditCard size={15} />{zh ? "管理套餐" : "Manage plan"}</button>}
        />

        <MetricStrip items={[
          { label: zh ? "计费单位" : "Billable units", value: number(usage.billable_unit_count), tone: "cobalt" },
          { label: zh ? "配额已用" : "Quota used", value: `${number(quota.used)} / ${number(quota.limit) || "∞"}`, tone: "warn" },
          { label: zh ? "计量项" : "Meters", value: meters.length, tone: "info" },
          { label: zh ? "超额风险" : "Overage risk", value: string(usage.overage_risk), tone: "pass" }
        ]} />

        <section className="payment-priority">
          <div><WalletCards size={24} /><span className="eyebrow">{zh ? "中国区支付优先级" : "CHINA PAYMENT PRIORITY"}</span><h2>微信支付 · 支付宝</h2><p>{zh ? "当前只展示接入顺序，不执行真实收款。" : "This view shows integration priority only and performs no live charge."}</p></div>
          <div><StatusBadge value="provider_backend_required" tone="warn" /><small>{string(billingAccount.currency, "CNY")}</small></div>
        </section>

        <div className="content-grid equal">
          <Section title={zh ? "用量明细" : "Usage meters"} description={zh ? "来自租户范围内的只读 usage ledger" : "Read-only usage ledger scoped to the tenant"}>
            <DataTable headers={[zh ? "计量项" : "Meter", zh ? "数量" : "Quantity", zh ? "计费" : "Billable", zh ? "来源" : "Source"]} label="Usage meters">{meters.map((meter, index) => <tr key={`${string(meter.meter)}-${index}`}><td><strong>{string(meter.meter, string(meter.name))}</strong></td><td>{number(meter.quantity)}</td><td><StatusBadge value={string(meter.billable, "read_only")} /></td><td>{string(meter.source, "A1/A2")}</td></tr>)}</DataTable>
          </Section>
          <Section title={zh ? "账单预览" : "Invoice preview"} description={zh ? "CNY 只读预估，不代表已结算金额" : "Read-only CNY estimate, not a settled invoice"}>
            <div className="invoice-sheet"><header><ReceiptText size={20} /><div><span>{string(invoice.invoice_id, "preview")}</span><strong>{string(invoice.total_label, string(invoice.subtotal_label, "CNY 0.00"))}</strong></div></header>{lineItems.map((item, index) => <div key={`${string(item.meter)}-${index}`}><span>{string(item.meter)}</span><b>{string(item.subtotal_label, String(number(item.quantity)))}</b></div>)}<footer><Landmark size={16} />{zh ? "未连接 provider settlement" : "Provider settlement not connected"}</footer></div>
          </Section>
        </div>
      </>
    );
  }}</DataBoundary>;
}
