# A3 服务器权威部署回执验证器

- 日期：2026-07-13
- 范围：A3 Deployment Receipt、服务器验证边界、验收投影、审计与产品展示
- 新增契约：`a3.deployment_receipt_authoritative_readback.v1`
- 新增投影：`a3.deployment_acceptance_projection.v1`
- 当前生产状态：仍然阻塞，真实生产验证回执为 0

## 1. 这轮解决了什么

上一轮已经可以收集和人工复核部署回执元数据，但 `submitted` 和
`acknowledged` 永远不能代表真实生产验证。这轮补上两者之间缺失的服务器边界：

```text
外部系统产生真实证据
  -> 浏览器只提交净化后的引用和 SHA-256
  -> reviewer 只确认元数据完整
  -> A1 验证过的 service account 调用内部接口
  -> 服务器 resolver 读取真实外部状态
  -> A3 严格校验 receipt/candidate/run/scope/hash/authority/claims
  -> 写入不可变、哈希串联的 authoritative readback
  -> Dashboard 生成只读 Deployment Acceptance projection
  -> 后续仍需重建并重新封存正式 Deployment Acceptance
```

因此，A3 现在具备“接收真实验证结果”的受控通道，但仓库仍没有九类真实外部
回执。实现验证通道不等于已经完成生产部署。

## 2. 服务器权限边界

内部路由：

```text
POST /internal/a3/deployment/receipts/:receiptId/verify
```

它必须同时满足：

1. 运行在 `hosted_enforced` 模式。
2. principal 由 A1 服务端验证，类型必须是 `service_account`。
3. principal 必须拥有 `deployment:verify`。
4. 服务器必须注入 trusted resolver。
5. 请求必须带 `Idempotency-Key` 和当前 `expected_version`。
6. 浏览器伪造的 role、service-account header 或验证结果均不能生效。

请求体只是触发器。客户端不能提交 `production_verified`、claims、证据内容、
verifier authority、attestation 或 readback。发现这些字段时，API 返回净化后的
HTTP 400；demo/header 伪造身份返回 HTTP 403；resolver 不可用返回 HTTP 503；
resolver 输出无效返回 HTTP 502。

## 3. 严格绑定与 blocker 专用 claims

每条 readback 必须与原回执完全匹配：

- `receipt_id`
- `blocker_id`
- `candidate_id`
- A1 `run_id`
- organization/tenant/workspace/project/environment 五层 scope
- `evidence_sha256`
- `verifier_class`
- blocker 指定的 `verifier_authority`

九类 blocker 使用不同 authority 和 claims。例如：

| Blocker | Authority | verified 时必须全部为 true |
|---|---|---|
| `a2_release_authority` | `a2_trusted_service` | same candidate、integrity、decision allow、release ready |
| `deployment_health` | `a1_a3_deployment_verifier` | image/config/migration、health、network policy、tenant isolation |
| `github_app_installation` | `a1_github_installation_service` | tenant installation、repository、Check identity |
| `required_check_enforcement` | `github_repository_policy_service` | required context、failing merge denied、maintainer readback |

resolver 声称 `verified` 时，只要一个必需 claim 缺失、类型错误或为 false，整条
readback 都会被拒绝，不能写成生产验证。

## 4. 不可变存储、幂等与审计

Migration `018_deployment_receipt_readbacks` 新增五层租户作用域表。每条记录包含：

- readback ID、receipt ID、candidate、run 和 blocker；
- verifier class、authority、evidence hash 和 attestation hash；
- verification status 与 reason code；
- sequence、previous readback hash 和当前 readback hash；
- 净化后的 JSON payload。

同一幂等请求重放不会再次调用 resolver。成功或拒绝的权威回读都会写入：

- append-only audit event；
- `event_outbox`；
- usage meter `deployment_receipt_authoritative_verifications`；
- Memory、JSON-file 和 SQLite 状态。

SQLite restart 测试证明 receipt 和 readback 均可恢复。原始证据、secret、token、
cookie、email、signed URL 和本地路径不会进入表、事件或公开 fixture。

## 5. 验收投影为什么不是正式通过

`a3.deployment_acceptance_projection.v1` 把哈希有效的 verified readback 投影到原
Deployment Acceptance 上，但不会修改原对象。

它同时返回：

- `source_passed`：原始正式验收通过数；
- `projected_passed`：加入权威回读后的只读推演值；
- `changed_check_ids`：哪些 check 被 readback 覆盖；
- `requires_acceptance_rebuild`：是否需要后端重新构建并封存；
- `production_accepted=false`：投影本身永远不是正式生产验收。

测试中，一条合成的 `deployment_health` readback 会把投影从 `8/17` 变为 `9/17`，
同时原始 Deployment Acceptance 仍为 `8/17`。这只证明代码逻辑，不是现实部署
回执。默认 `a3-golden-path-rc2` 仍然是 `8/17 -> 8/17`。

## 6. Dashboard 产品行为

Delivery 页面现在分开展示：

1. 回执是否已提交。
2. reviewer 是否确认元数据。
3. 服务器 authority 是否已验证或拒绝。
4. 原始正式验收与只读投影分别是多少。
5. 是否需要重新构建正式验收制品。

浏览器没有“权威验证”按钮，也不会调用内部 verify 路由。它只能提交/复核元数据
并读取服务器已经产生的 readback。这避免了前端把一个布尔值改成 true 就伪造
生产证明。

## 7. A1/A2 权威保持不变

- A1 仍负责可信身份、运行事实及部署/存储/队列/GitHub 外部 verifier。
- A2 仍负责 score、pass/fail、failure class、Decision Ledger 和 Release Ready。
- A3 只验证绑定、保存 readback、生成投影和展示工作流。
- A3 不重算 A2，不把历史 sealed `block` 当作当前同候选 authority。

当前真实状态仍为：

```text
Golden Path: 7/11
Deployment Acceptance source: 8/17
Deployment Acceptance projection: 8/17
Current authority: integrity_invalid
Current A2 decision: unknown
Historical sealed decision: block
Production verified receipts: 0
```

## 8. 验证证据

本轮聚焦验证已通过：

- workflow、Store、HTTP、RBAC、幂等、resolver、hash chain、projection、tenant
  isolation 和 SQLite restart；
- OpenAPI 运行时权限路由 parity `57/57`；
- TypeScript typecheck；
- Dashboard 源码断言证明不存在浏览器内部 verifier 调用；
- secret/path 安全规则保持开启。

完整 A3/A2/Next.js/Playwright/CL 验证结果记录在本轮 worklog，不能用本地测试
代替真实 staging/VPC 回执。

## 9. 仍未完成

1. A2 需要为 `a3-golden-20260712-002` 和相同五层 scope 产生新的 Trusted Spine。
2. A1/A3 需要把九类 resolver 接到真实 staging/VPC、PostgreSQL、Queue、Object
   Storage、GitHub App 和 repository policy readback。
3. Repository maintainer 需要证明 main required Check 强制执行并拒绝失败候选。
4. 收到真实 readback 后必须重建/reseal Deployment Acceptance、Release Artifact
   和新的 run-specific Audit Bundle。

封存的 rc.2 bundle、archive、manifest 和 authority 结论没有被修改。
