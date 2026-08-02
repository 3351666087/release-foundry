# 多模态审核补证闭环 - Round 24

日期：2026-07-14

## 一句话说明

审核员看到 A2 多模态分歧案例后，如果发现执行链、工具调用、媒体证据、Judge 回执、Provider
身份或候选版本绑定不完整，现在可以在 A3 中发起一条有责任方、有截止时间、有版本和审计链的
“补证请求”。执行端或评测端只能提交 SHA-256 证据引用，审核员随后可以验收、退回或取消。

这里的“验收”只表示补交材料通过检查。它不是 A2 真人裁决，不会修改 score、pass/fail、
failure class、Decision Ledger 或 release status。

## 校准基线

- authoritative `origin/main`: `ccf6ce5`
- A1 peer: `6a985b8`
- A2 latest peer: `7504680`
- exact A2 Round 50 three-way source: `bb3bcfe`
- A3 previous head: `7bd03bf`
- product strategy: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`

本轮沿用 A2 Round 50 的真实公开安全三方比较和 queue receipt。A2 仍记录一项待人工复核、
零项真实人工复核完成；A3 没有伪造 disposition。A1 的执行、工具调用、artifact 和身份能力只通过
哈希引用与服务端 principal 边界接入，A3 不接管原始 trace、媒体或 provider secret。

A1 `6a985b8` 在 peer branch 新增 identity-authority readiness：runtime 不能是 superuser 或
bypass-RLS，不能创建 public schema 对象，PUBLIC/运行角色不能直接读取安全表或调用内部函数，
security-definer 函数的 `search_path` 也进一步收紧。该提交尚未进入 main，因此 A3 只记录能力
校准，仍把当前本地 reviewer principal 视为非生产身份，不宣称 hosted identity 已完成。

A2 `7504680` Round 51 新增 `a2.multimodal_multi_repeat_comparison.v1` 和真实 review collection
contract。三次 retained calibration 都是 `blocked`；真实 review collection 仍为 `pending`、
`receipts=[]`；shared-candidate verification 为 false，Trusted Spine 没有生成。本轮只完成 peer
校准，不把这个新 schema 写成已接入；当前三方队列仍精确消费 Round 50 `bb3bcfe`。这些新事实
不会改变补证状态机，也不会赋予 A3 release authority。

## 为什么需要这一步

上一轮已经解决“谁领取这个案例”，但领取后若证据不足，只能线下口头追问，系统无法回答：

1. 缺的究竟是执行证据还是评测证据；
2. 应由哪个责任通道补交；
3. 什么时候到期；
4. 补交了哪些内容；
5. 谁检查了补交材料；
6. 请求是否被篡改、重复提交或并发覆盖。

Round 24 把这段协作过程变成可查询、可持久化、可导出和可审计的状态机。

## 状态机

| 操作 | 前置状态 | 结果状态 | 关键限制 |
|---|---|---|---|
| create | 无 | `open` | 当前审核租约所有者；截止时间在未来 30 天内 |
| time projection | `open` | `overdue` | 由服务器时间计算，不伪造一条“过期事件” |
| submit | `open` / `overdue` | `submitted` | `project:ingest`；一次覆盖全部必需证据种类 |
| accept | `submitted` | `accepted` | 当前审核租约所有者；仅验收材料 |
| reject | `submitted` | `open` / `overdue` | 保留 `rejected` 事件，允许重新补交 |
| cancel | `open` / `overdue` / `submitted` | `cancelled` | 当前审核租约所有者 |

每次写操作都要求 `expected_version`，并使用请求头 `Idempotency-Key`。旧版本写入返回脱敏
`409`；同一幂等键重复请求返回原收据，不会生成第二条业务事件。

## 证据类型与跨组边界

只允许以下受控类型：

| evidence kind | 主要来源 | A3 如何使用 |
|---|---|---|
| `a1_run_trace` | A1 Runner/Trace | 引用一次执行链的 SHA-256 |
| `a1_tool_call` | A1 ToolCall | 引用工具调用证据 SHA-256 |
| `a1_artifact` | A1 artifact custody | 引用执行产物 SHA-256 |
| `a2_judge_receipt` | A2 Judge | 引用评测回执 SHA-256 |
| `a2_review_receipt` | A2 human-review service | 只引用真实回执；当前没有就保持缺失 |
| `media_evidence` | A1/A2 media pipeline | 引用图片、音频或视频证据哈希，不存媒体本体 |
| `provider_identity` | A1/A2 identity evidence | 引用经过验证的 Provider 身份绑定 |
| `candidate_binding` | Trusted Spine | 引用同一候选版本绑定证据 |

每条引用只允许 `kind`、`evidence_hash` 和可选 `binding_hash`。原始图片、音频、视频、文本、
URL、signed URL、本地路径、email、账号身份、cookie、token、secret 和额外自由字段都会 fail closed。

## 数据与完整性

核心 schema：

- `a3.multimodal_review_evidence_request_event.v1`
- `a3.multimodal_review_evidence_request.v1`
- `a3.multimodal_review_evidence_request_receipt.v1`

事件链验证覆盖：

- event id 与 event hash 重算；
- 连续 version；
- `previous_event_hash`；
- 合法生命周期转换；
- 时间单调性；
- organization/tenant/workspace/project/environment 五级范围；
- queue、case、comparison 和 request 绑定；
- owner、截止时间和必需证据种类不可变。

发现链损坏时，请求显示 `integrity=failed` 并拒绝继续写入。该校验只证明 A3 协作事件自洽，
不是 A2 Judge 正确性或生产签名证明。

## API 与权限

新增四个受保护接口：

```text
GET  /api/a3/review/multimodal-queue/:queueId/evidence-requests
POST /api/a3/review/multimodal-queue/:queueId/evidence-requests
POST /api/a3/review/multimodal-queue/:queueId/evidence-requests/:requestId/submissions
POST /api/a3/review/multimodal-queue/:queueId/evidence-requests/:requestId/review
```

- read/create/review: `release:review`
- submit: `project:ingest`
- create/review: 还必须拥有当前 active assignment lease
- all routes: server-verified principal、五级 scope、脱敏 401/403/404/409
- mutations: metadata-only audit、Event Outbox 和 usage meter

跨租户访问返回脱敏 404，不暴露 request id、case id 或 evidence hash。

## 持久化

- Memory Store：单进程功能与单元测试；
- JSON-file Store：重启后恢复完整 accepted history；
- SQLite：事件逐行持久化并验证重启恢复；
- PostgreSQL contract：migration 023 建表，migration 024 启用并强制五级 RLS。

迁移 023/024 目前是经过测试的 SQL 契约，不是目标 staging PostgreSQL 已执行的生产回执。

## Dashboard 与报告

Review 页面新增中文优先“审核补证”区：

- 总计、待补、超期、待验、已收统计；
- 按案例创建补证请求；
- 责任通道、证据种类、截止时间和受控原因；
- 请求历史、SHA-256 前缀和完整性状态；
- accept、reject、cancel；
- loading、success、denied、conflict、failed、retry 和 empty 状态。

同一投影已经接入 Dashboard snapshot、JSON、Markdown 和 Hosted Report。导出只包含哈希和状态
元数据，不包含原始证据或可访问媒体的 URL。

## 视觉证据


两张截图均已人工检查；关键内容没有重叠，390 x 844 页面没有 document-level 横向溢出。

## 验证结果

- A3 Node: `498` passed, `0` failed, `1` target-PostgreSQL opt-in skip；
- current-main A2: `186/186` passed plus `1050` subtests；
- Next.js TypeScript: passed；
- Next.js production build: passed, `15` static pages；
- Playwright: `44/44` passed；
- OpenAPI runtime parity: `65/65`；
- CL hygiene: `0` findings；
- Commercial CL: `0` blockers, `0` advisories；
- root/Webapp production dependency audit: `0` vulnerabilities；
- GitHub Actions feature commit `565cec7`: run `29322903320` passed every applicable check；
  TypeScript SDK、Go SDK 和 Rust verifier 依照 path plan 跳过，不是失败。

## 仍未完成

- 真实 A2 human-review receipt 和最终 disposition；
- 同 candidate 的 A1 evidence、A2 Decision Ledger 与 A3 artifact 重新绑定；
- A1 hosted reviewer identity、qualification、conflict-of-interest 和浏览器 CSRF；
- target PostgreSQL、object storage、KMS/SSO 与 staging restart/RLS 回执；
- 高风险媒体双人审核、SLA escalation 和通知 worker；
- tenant-bound GitHub App required check 与真实 merge denial；
- 真实生产部署、升级和回滚回执。

因此事实状态不变：Golden Path `7/11`，Deployment Acceptance `8/17`，当前 authority
`integrity_invalid`，当前 A2 decision `unknown`，历史 A2 decision `block`，production receipts
`0`，`production_ready=false`。
