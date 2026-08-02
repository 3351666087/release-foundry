"use client";

import { useState } from "react";
import { KeyRound, LockKeyhole, UserPlus, Users } from "lucide-react";

import { array, number, record, string } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DataBoundary, DataTable, MetricStrip, PageHeader, Section, StatusBadge } from "../ui";

type TeamTab = "members" | "rbac" | "keys";

export function TeamPage() {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [tab, setTab] = useState<TeamTab>("members");
  return <DataBoundary>{(model) => {
    const admin = record(model.raw.saas_admin_console);
    const organization = record(admin.organization);
    const team = record(admin.team);
    const seats = record(team.seat_management);
    const rbac = record(admin.rbac);
    const apiKeys = record(admin.api_keys);
    const members = array(team.members).map(record);
    const roles = array(rbac.permission_matrix).map(record);
    const keys = array(apiKeys.keys).map(record);
    return (
      <>
        <PageHeader
          eyebrow="ADMIN / IDENTITY & ACCESS"
          title={zh ? "团队与权限" : "Team and access"}
          summary={zh ? "成员、角色和 API Key 共享同一个租户安全边界。" : "Members, roles, and API keys share one tenant security boundary."}
          meta={<><span>{string(organization.display_name)}</span><StatusBadge value={string(team.status)} /></>}
          actions={<button type="button" className="command-button" disabled title={zh ? "等待 hosted auth 与邮件服务" : "Requires hosted auth and email service"}><UserPlus size={15} />{zh ? "邀请成员" : "Invite member"}</button>}
        />

        <MetricStrip items={[
          { label: zh ? "已购席位" : "Purchased seats", value: number(seats.purchased_seats), tone: "info" },
          { label: zh ? "计费席位" : "Billable seats", value: number(seats.assigned_billable_seats), tone: "cobalt" },
          { label: zh ? "审计席位" : "Audit seats", value: number(seats.free_audit_seats), tone: "pass" },
          { label: zh ? "待处理邀请" : "Pending invites", value: number(seats.pending_invites), tone: "warn" }
        ]} />

        <div className="page-tabs" role="tablist" aria-label="Team controls">
          {[{ id: "members", label: zh ? "成员" : "Members", icon: Users }, { id: "rbac", label: "RBAC", icon: LockKeyhole }, { id: "keys", label: "API Keys", icon: KeyRound }].map((item) => <button type="button" role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id as TeamTab)} key={item.id}><item.icon size={16} />{item.label}</button>)}
        </div>

        {tab === "members" && <Section title={zh ? "成员目录" : "Member directory"} description={zh ? "仅展示脱敏身份和席位状态" : "Only redacted identity and seat state are shown"}>
          <DataTable headers={[zh ? "成员" : "Member", zh ? "角色" : "Role", zh ? "状态" : "Status", zh ? "席位" : "Seat"]} label="Team members">{members.map((member, index) => <tr key={`${string(member.member_id)}-${index}`}><td><strong>{string(member.display_name)}</strong><small>{string(member.member_id)}</small></td><td>{string(member.role)}</td><td><StatusBadge value={string(member.status)} /></td><td>{string(member.seat_state)}</td></tr>)}</DataTable>
        </Section>}

        {tab === "rbac" && <Section title={zh ? "权限矩阵" : "Permission matrix"} description={zh ? "真实执行仍需托管身份中间件" : "Live enforcement still requires hosted identity middleware"}>
          <div className="role-grid">{roles.map((role, index) => <article key={`${string(role.role)}-${index}`}><header><LockKeyhole size={17} /><h3>{string(role.role)}</h3><b>{number(role.permission_count)}</b></header><div>{array(role.permissions).map((permission) => <span key={string(permission)}>{string(permission)}</span>)}</div></article>)}</div>
        </Section>}

        {tab === "keys" && <Section title="API Keys" description={zh ? "只展示名称、前缀、范围和轮换状态，永不展示真实 secret" : "Show name, prefix, scope, and rotation only; never reveal a real secret"} action={<button type="button" className="command-button" disabled>+ {zh ? "创建 Key" : "Create key"}</button>}>
          <DataTable headers={["Key", zh ? "范围" : "Scopes", zh ? "状态" : "Status", zh ? "轮换" : "Rotation"]} label="API keys">{keys.map((key, index) => <tr key={`${string(key.key_id)}-${index}`}><td><strong>{string(key.name)}</strong><small>{string(key.prefix)}</small></td><td>{array(key.scopes).map((scope) => string(scope)).join(" · ")}</td><td><StatusBadge value={string(key.status)} /></td><td><StatusBadge value={string(key.rotation_state)} /></td></tr>)}</DataTable>
        </Section>}
      </>
    );
  }}</DataBoundary>;
}
