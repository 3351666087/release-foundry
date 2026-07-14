# 多模态人工审核领取与锁定 - 2026-07-14

## 一句话解释

上一轮已经能把“两个模型意见不一致”的案例放进审核队列。这一轮解决的是：
**多人一起工作时，谁负责哪条、会不会两个人同时修改、超时后怎么交给别人。**

它只管理人的工作分配，不判断哪个模型正确，也不改变评分或发布决定。

## 本轮先校准了什么

- `main`: `ccf6ce5`
- A1 peer: `2307231`
- A2 peer: `1553562`
- A2 Round 49 做了 50 次真实 DashScope 多模态请求：49 次完成、1 次失败、48 条可评估。
- 实测 sensitivity `0.6364`、specificity `0.9333`、balanced accuracy `0.7848`。
- 延迟 median `2.585s`、P95 `10.373s`、max `17.184s`。
- 结果仍是 `blocked`，原因包括结构化输出失败、Provider 失败、灵敏度、P95、扰动样本来源和价格缺失。
- A2 有真人复核 schema 和测试 fixture，但没有可公开安全消费的真实真人复核凭证。

校准证据保存在：
`fixtures/a3/p3/a2_multimodal_round49_calibration_1553562.redacted.json`。

## 为什么不能直接写“审核通过”

A2 现有公开样本中的 `reviewer_identity_class` 是 `test_review_fixture`，意思是测试数据，
不是某位真实审核员完成工作的证明。A3 如果把它显示成真人结论，就会制造假证据。

所以本轮只实现 A3 自己有权负责的“工作领取状态”。真正改变发布状态仍必须同时具备：

1. A2 的真实人工复核凭证；
2. 连续、无篡改的复核凭证链；
3. 同一个 candidate 的 A2 Decision Ledger；
4. A2 明确给出的权威发布结论。

## 状态机

```text
未领取 --claim--> 处理中 --renew--> 处理中
处理中 --transfer--> 另一位审核员处理中
处理中 --release--> 未领取
处理中 --超时--> 锁已过期 --claim--> 重新领取
```

每次操作都必须提交 `expected_version`。例如当前版本是 3，而旧页面仍提交版本 2，
服务端返回 HTTP 409，不允许旧页面覆盖新操作。

## 实现内容

### 核心与 API

- 新增 append-only 事件模型，不覆盖旧记录。
- 支持 `claim`、`renew`、`release`、`transfer`。
- 锁默认 900 秒，允许 60 到 3600 秒。
- 新增 `POST /api/a3/review/multimodal-queue/:queueId/assignment`。
- 只接受请求头 `Idempotency-Key`，请求体里的键不能授权写入。
- 操作者哈希来自服务端认证上下文，不能由业务 payload 冒充。
- 跨租户查找返回 404，不泄露 case、model 或 hash。

### 数据库与审计

- Memory Store、JSON File Store、SQLite 均能保存并恢复领取状态。
- 新增 migration `021_multimodal_review_assignment_events`。
- 新增 migration `022_multimodal_review_assignment_scope_hardening`。
- PostgreSQL 契约启用五级 scope RLS；SQLite 是本地参考实现。
- 每次操作写 metadata-only audit 与 event outbox。
- 不保存原始姓名、邮箱、媒体、模型回答、签名 URL 或 secret。

### 产品与报告

- 审核页显示正在处理、等待领取、锁已过期数量。
- 每个案例显示领取状态、审核员哈希别名、版本和到期时间。
- JSON、Markdown、Hosted Report 导出领取状态和事件数量。
- API Reference 升级为 v10，OpenAPI 增加请求、回执和并发契约。

## A1 / A2 对接边界

- A1 仍负责可信登录、服务端 reviewer identity、Hosted PostgreSQL 与审计执行环境。
- A2 仍负责模型风险、score、pass/fail、failure class、人工处置语义和 Decision Ledger。
- A3 只负责队列、人员协作、页面、报告、API 权限与审计投影。
- 领取、转交或释放均固定 `release_authority=false`、`a2_decision_recomputed=false`。

## 当前仍未完成

- 没有真实 A2 人工复核凭证，因此不能显示“真人已确认风险/安全”。
- 没有同 candidate Trusted Spine，因此当前 authority 仍为 `integrity_invalid`。
- 没有 A1 Hosted 身份和 CSRF 闭环，因此网页暂时只展示领取状态，写操作通过受保护 API 验证。
- 没有目标 staging/VPC PostgreSQL 回执，本轮 SQLite 成功不等于生产部署成功。
- Golden Path 仍为 `7/11`，Deployment Acceptance 仍为 `8/17`，production ready 仍为 false。

## 主要文件

- `services/report/a3_multimodal_review_assignment.mjs`
- `services/report/a3_store.mjs`
- `services/report/a3_api_server.mjs`
- `services/report/a3_sql_migrations.mjs`
- `services/report/a3_sqlite_store.mjs`
- `apps/webapp/components/pages/review-page.tsx`
- `docs/a3/openapi/a3_commercial_api.openapi.json`
- `tests/a3/a3_multimodal_review_assignment.test.mjs`
- `tests/a3/a3_multimodal_review_api.test.mjs`
- `tests/a3/a3_multimodal_review_store.test.mjs`
