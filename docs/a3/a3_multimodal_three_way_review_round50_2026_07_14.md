# 多模态三方模型复核接入 - A2 Round 50

日期：2026-07-14

## 一句话说明

以前 A3 只能把两个模型的观察放在一起比较。A2 Round 50 首次发布了真实、公开安全的
`a2.multimodal_three_way_comparison.v2`，因此本轮让 A3 能严格校验、导入、持久化和展示
三个 provider 对同一媒体证据的观察，并把真实分歧交给现有人工审核领取流程。

这仍然不是人工裁决。A2 Round 50 明确记录一项待复核、零项真人完成；A3 没有补写结论。

## 本轮校准基线

- `origin/main`: `ccf6ce5`
- A1 peer: `770ccc8`
- A2 peer: `bb3bcfe`
- A3 previous head: `a13e9ae`
- Enterprise strategy: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`

常规 `git fetch origin --prune` 在 HTTPS 传输阶段长时间无响应，本轮终止了挂起进程，随后用
认证 GitHub API 确认以上远程 SHA、PR 和 CI 状态。没有把本地旧 remote-tracking ref 当成最新值。

A1 `770ccc8` 新增了真实 PostgreSQL identity lifecycle 证明。它仍在 Draft PR #36，A3 只把它
视作身份能力校准，不把 peer-only 能力写成 main 或生产能力。

## A2 原始事实

A2 Round 50 完整三方 artifact 有 74 个案例：

- `pairwise_agreement_with_unavailable`: 72
- `semantic_disagreement`: 1
- `unavailable`: 1
- `three_way_agreement`: 0
- human review queue receipt: 1
- real human-review receipt: 0
- release authority: false

三个 provider key 是：

- `dashscope_run_a`
- `dashscope_run_b`
- `qwen3vl_local`

公开 artifact 没有提供可安全消费的 provider/model 身份绑定，所以 A3 只展示 provider key，
不会推断 model id、版本、账号或私有 endpoint。

## 提交的脱敏样本

`fixtures/a3/p3/a2_multimodal_three_way_v2_bb3bcfe_sample.redacted.json` 是完整 Round 50
artifact 的代表性投影，不是完整 74 行原件。它保留三个真实代表案例：

1. 一项 pairwise agreement with unavailable；
2. 一项 semantic disagreement；
3. 一项 unavailable。

样本保留原始 comparison artifact hash、evidence hashes、案例 artifact hashes 和唯一 queue
receipt，删除无关案例后重新计算样本内部 summary 与三组 pairwise summary。样本文件本身不声称
与完整上游 artifact 逐字节同哈希。

## 严格校验

`services/report/a3_multimodal_review_queue.mjs` 新增三方 v2 fail-closed 校验：

1. 顶层和每层对象使用字段 allowlist；
2. evidence/partial journal/provider states 必须使用完全相同的三个 provider key；
3. evidence、artifact、comparison 和 receipt 引用必须是 SHA-256；
4. eligible provider 必须有 boolean risk，不可用 provider 的 risk 必须为 null；
5. `eligible_provider_count` 必须和三路状态一致；
6. A3 从三路状态重算 comparison state，只用于完整性检查；
7. A3 重算四类 summary，只用于防篡改；
8. A3 重算三组 pairwise summary；
9. 每个 required review 必须恰好有一张匹配 case/artifact/repeat 的 queue receipt；
10. receipt 必须绑定顶层 comparison artifact hash；
11. raw payload、URL、email、secret、signed URL 和本地账号路径继续禁止；
12. 所有 release authority 字段必须为 false。

完整性重算不是 A2 风险或发布决策重算。A3 只验证上游对象自洽。

除提交的三案例投影外，本轮还通过认证 GitHub API 把完整 74 案例 artifact 临时下载到操作系统
临时目录，并直接运行同一个校验器。结果为 `valid=true`、`error_count=0`、provider count 3、
review required 1、queue item 1；summary 精确还原 72/1/1/0。验证后临时文件已删除。

## 产品数据流

```text
A2 Round 50 public-safe three-way v2
  -> A3 strict contract validator
  -> tenant-scoped Store / API / SQLite
  -> review queue projection
  -> reviewer assignment lease
  -> Dashboard / JSON / Markdown / Hosted Report
  -> assignment packet / Audit Archive boundary
```

新增数据源：`p3-a2-round50`。

Webapp Review 页面现在动态渲染 provider 数量。双路 v1/v3 继续显示模型 pair；三方 v2 显示三路
provider key、可用数量、每路 risk/availability 和 parse state tooltip。旧接口和旧报告保持兼容。

## API、权限和状态

- Import: `POST /api/a3/import/a2-multimodal-comparison`
- Read: `GET /api/a3/review/multimodal-queue`
- Assignment: `POST /api/a3/review/multimodal-queue/:queueId/assignment`
- Import permission: `project:ingest`
- Review permission: `release:review`
- Tenant scope: organization/tenant/workspace/project/environment 五层
- Mutation: Idempotency-Key、server identity、optimistic version、lease、audit、outbox
- Cross-tenant: fail closed，不回显 case/provider/evidence hash

Loading、Empty、Invalid、Denied、Conflict 和 Retry 继续走现有 DataBoundary、route access 和 Store
错误状态。新 schema 没有绕开任何写路径保护。

## 报告和审计

JSON/Markdown/Hosted Report 新增：

- `provider_set`
- `provider_count`
- `three_way_agreement`
- `pairwise_agreement_with_unavailable`
- 每个 queue item 的 `provider_observations`

assignment packet 继续只封存人员领取历史。它不会把三路比较变成人工 disposition，也不会把
本地 Ed25519 自签名变成 KMS/SSO 生产签名。

## 视觉证据

- `docs/screenshots/a3-webapp-three-provider-review-mobile-390x844.png`

Playwright 验证了 source 选择、3/1/1 摘要、三个 provider、2 个 eligible、三种风险展示、
release authority 边界，以及 390 x 844 无 document-level 横向溢出。

## 仍未完成

- A2 真实真人审核 receipt 和完整 review chain；
- 同 candidate 的有效 Decision Ledger 和 Trusted Spine；
- A1 hosted reviewer directory、qualification、conflict 和 CSRF；
- 完整 74 案例 artifact 的受控对象存储导入与分页；
- target PostgreSQL/VPC/KMS/SSO 生产回执；
- Golden Path `7/11` 与 Deployment Acceptance `8/17` 没有变化；
- production ready 仍为 false。
