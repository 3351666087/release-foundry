# A3 Lane 新 Goal 与 Main 战略对齐记录

日期：2026-07-12

## 结论

本轮收到的新 A3 Lane Goal 与仓库唯一战略总线一致，可以直接作为后续
A3 工作的执行约束，不需要另起一套产品方向。

- 远端 `main`：`ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- 当前 A3 分支起点：`0b0e0cf1cdeeaf87c95d497dbe89b4dca948ca8e`
- 战略文件：`docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- 本地与 GitHub `main` 战略文件 SHA：
  `575b31b80981542fc96f9a9310e66a9318974abb`
- Git HTTPS 本轮一次 `fetch` 被连接重置；官方 GitHub 连接器随后确认
  `main` 仍为 `ccf6ce5`，因此没有使用过期或第三方镜像状态。

## A3 到底负责什么

A3 不是“多做几个页面”，而是把两个上游 Lane 的真实结果组织成企业
用户可以理解、审核、签字、发布和持续运维的产品工作流：

```text
A1 运行事实、身份、租户、Usage、Deploy
             +
A2 Evidence、Judge、Review、Decision Ledger、Release Gate
             ↓
A3 Console、Review、War Room、Report、Admin、Billing UX、Integrations
```

A3 稳定拥有的产品范围：

- Onboarding 与 Identity UX；
- Run / Case / Trace / Tool Call / Replay / Diff 控制台；
- Evidence Explorer；
- Reviewer Queue、Override、Waiver、Approval 与仲裁；
- Release War Room、GitHub/GitLab Gate 与通知；
- Report、Share、Revoke、Expiry、Export 与 Audit Bundle；
- Team、RBAC、Usage、Billing、License、Deploy 与 Self-host 管理体验；
- 企业微信、钉钉、飞书及代码平台集成体验。

## 不可越过的权责边界

- Run、Trace、Tool Call、Usage、Entitlement、Deployment Health 来自 A1。
- Grade、Score、Pass/Fail、Failure Class、Evidence Snapshot、Review 原始记录、
  Decision Ledger 与 Release Decision 来自 A2。
- A3 不重算 A2 分数，不拼装 `release_ready`，不删除原始机器结论。
- 没有有效 A2 Decision Ledger，不显示 Release Ready，不允许发布。
- 浏览器提供的 role、tenant、session 布尔值或任意 header 都不是可信身份。
- 真实高风险写操作必须经过服务端 Auth、RBAC/ABAC、幂等、并发控制、
  Audit 和可恢复执行器。

## 本轮为什么先做安全闭环

新 Goal 要求所有高风险状态来自真实后端。上一轮代码审计发现两条会直接
破坏企业可信度的路径：

1. 请求已通过五层 scope 检查，但 `source` 或资源 ID 仍可能选中另一租户
   的快照，再被请求 scope 重新贴标签。
2. 公开报告访问如果接受客户端 `viewed_at`，过期 token 可以尝试把时间
   倒退到过期前。

因此本轮优先完成：

- hosted 模式精确查找 `source`，不存在时不再回退第一份快照；
- organization / tenant / workspace / project / environment 五层资源匹配；
- 同 ID 的两租户 run、case、report 碰撞测试；
- 报告重复 ID 的 scope-aware 内部存储键；
- share token 只使用服务端时钟；
- hosted principal 必须明确 trusted、authenticated、active、expiry、
  effective permissions 和 actor/subject reference；
- hosted API 只接受每请求 principal resolver，不接受静态主体对象；
- 未注册 hosted 路由也持久化 metadata-only 拒绝审计；
- 运行时 401/403 与 OpenAPI closed schemas 对齐；
- demo 模式无论客户端怎样伪造 session/service-account，都不能执行
  live GitHub mutation。

## 当前能力分级

### 已实现并有本轮自动化验证

- A3 hosted route guard 与五层本地资源隔离参考实现；
- 同 ID 跨租户读隔离测试；
- metadata-only access audit 的 memory/SQLite 持久化参考实现；
- share-token 过期与撤销状态、服务端时间回归测试；
- demo GitHub live mutation 技术禁用；
- Next.js 401/403 中文状态和 stale-data 清理；
- A1/A2 数据只读消费，A2 `release_ready=false` 保持不变。

### 契约支撑，但不是生产完成

- A1 verified session / service-account principal 接口；
- 商业 OpenAPI、RBAC 路由表、PostgreSQL migration 形状；
- Usage/Billing/Admin/Deploy/Notification 页面与本地 API 形状；
- GitHub publish/readback、Report Share、Audit Bundle 的本地或 dry-run 链路。

### 尚未生产验证

- 部署后的真实 A1 principal resolver；
- A3 权威 PostgreSQL Store 与强制 RLS；
- 多实例事务、Queue/Outbox、对象存储和 KMS；
- 客户 OIDC/SAML、生产 RBAC/ABAC、SCIM；
- 真实 GitHub App Worker 和 required-check 阻断；
- 客户 VPC 安装、升级、回滚、备份、恢复、负载与故障演练；
- 生产微信/支付宝登录或支付。资质就绪前只能是 ready-to-integrate。

## 本轮验证证据

- A3 Node：`364 pass / 0 fail`。
- Webapp TypeScript + Next.js production build：通过，14 个静态页面。
- Playwright fresh port / one worker：`32 pass / 0 fail`。
- A1 TypeScript session lifecycle：`35 pass / 0 fail`。
- A2 trusted spine：`7 pass / 0 fail`。
- CL hygiene：通过，0 findings。
- CL commercial：通过，0 blockers，0 advisories。
- changed-file secret scan：0 matches。
- `.env.local`：由 `.gitignore` 的 `.env.*` 规则忽略。
- `git diff --check`：通过。

这些结果证明当前分支的本地实现和合同没有已知回归，不等于生产部署、
生产多租户、生产身份或生产 Release 已完成。
