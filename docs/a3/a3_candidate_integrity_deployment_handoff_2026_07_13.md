# A3 候选完整性与部署交接

- 日期：2026-07-13
- 页面：`/delivery/?source=a3-golden-path-rc2`
- API：`GET /api/a3/dashboard`
- 当前结论：`integrity_invalid`
- 发布状态：`production_ready=false`

## 1. 本轮修正的问题

rc.2 的封存交付包记录了当时的 A2 结论 `block`。但是 A3 后端用当前
请求的五级租户作用域重新校验时，发现最新 A1 run、当前 A2 Trusted
Spine 与 rc.2 制品并不属于同一个 candidate：

| 对象 | 实际值 |
|---|---|
| A3 期望 A1 run | `a3-golden-20260712-002` |
| A2 evidence run | `a2_trusted_spine_demo` |
| A2 decision run | `a2_trusted_spine_demo` |
| A3 project/environment | `project-local` / `staging` |
| A2 project/environment | `a2_g3_calibration` / `local` |

所以，封存包里的历史 `block` 只能作为历史事实展示，不能当作当前权威
裁决。当前后端必须 fail closed：

```text
status = integrity_invalid
integrity_verified = false
upstream_decision = unknown
release_ready = false
reason_code = evidence_scope_mismatch
```

A3 没有重算 A2 的 score、pass/fail、failure class 或 Release Ready。

## 2. 新增数据契约

### `a3.release_comparison_runtime_authority.v1`

该对象把当前后端 A2 Trusted Spine 校验附加到历史 rc.1/rc.2 对比上：

- `status`、`integrity_verified`、`upstream_decision` 来自后端 verifier；
- `historical_candidate_decision` 保留封存包的历史结论；
- `current_release_authorized` 只有在完整性通过、A2 为 `allow` 且
  `release_ready=true` 时才可能为 true；
- `runtime_authority_recomputed=false`，明确 A3 不创造 A2 结论。

### `a3.deployment_handoff.v1`

该对象把 17 项 Deployment Acceptance 变成可执行交接，而不只是状态表：

- 5 个责任组：A2、A1、A1/A3、A3、Repository maintainer；
- 9 个阻塞或未证明项目；
- 每项都有 `next_action`；
- 每项都有 `required_receipt`；
- 单独校验 tenant scope、run ID、Release Artifact、Golden Path 与 A2
  Trusted Spine 是否绑定同一 candidate。

当前责任分布：

| 负责人 | 通过/总数 | 当前状态 |
|---|---:|---|
| A2 | 1/2 | blocked |
| A1 | 1/3 | blocked |
| A1/A3 | 0/5 | blocked |
| A3 | 6/6 | passed |
| Repository maintainer | 0/1 | blocked |

## 3. 页面变化

Delivery 页面现在按以下顺序展示：

1. 当前后端权威状态：`integrity_invalid`，而不是历史 `block`。
2. A1 执行、A2 案例评分、Trace 和 Tool Calls，保持事实分离。
3. 同一候选绑定：对比期望 A3 run/scope 与实际 A2 run/scope。
4. 历史封存结论与当前运行时结论并列展示。
5. rc.1 与 rc.2 质量变化：A2 `1/3 -> 3/3`、Tool Calls `0 -> 4`。
6. 5 个责任组和 9 个必须补齐的真实回执。
7. Golden Path、GitHub 回读、17 项明细和 Release Artifact。

页面支持中文优先与英文切换。桌面和 390 x 844 手机布局都经过
Playwright 检查，没有整页横向溢出。移动端的四列表格使用局部横向滚动。

## 4. API 与权限边界

OpenAPI 的 `DashboardSnapshot` 新增必需字段 `deployment_handoff`，并新增：

- `DeploymentHandoff`
- `DeploymentHandoffCheck`
- `CandidateBindingHandoff`
- `ReleaseComparisonRuntimeAuthority`

读取仍走现有 A1 服务端身份、A3 RBAC 和五级租户作用域。新对象只包含
ID、hash、scope、状态、计数和脱敏回执要求，不包含 key、token、cookie、
email、OTP、signed URL 或原始客户证据。

## 5. 当前 9 个真实阻塞

1. A2 为本 candidate 生成并校验 Trusted Spine。
2. A1 hosted identity verifier 的部署回执。
3. PostgreSQL migration 与 RLS allow/deny 回执。
4. durable queue、retry、dead-letter 和 worker health 回执。
5. immutable object storage 写入、retention 与 readback 回执。
6. staging/VPC identity、image、config、migration、health 与 network 回执。
7. upgrade、故障触发、rollback、backup、restore 与恢复健康回执。
8. tenant-bound GitHub App installation 与权限回执。
9. main required Check 和失败候选不可合并的治理回执。

这些项目没有真实回执前，A3 不会显示生产可用。

## 6. 验证证据

已完成的聚焦验证：

- Deployment Handoff 与 Release Comparison Node 测试；
- Commercial OpenAPI 与 API Reference 测试；
- Next.js TypeScript 检查与 15 页面 production export；
- Delivery 中文/英文、桌面/手机 Playwright；
- 2 项绑定通过、3 项绑定失败、5 个责任组、9 个阻塞项的精确断言。

截图：

- `docs/screenshots/a3-webapp-candidate-binding-rc2-desktop.png`
- `docs/screenshots/a3-webapp-candidate-binding-rc2-mobile-390x844.png`
- `docs/screenshots/a3-webapp-deployment-handoff-rc2-desktop.png`
- `docs/screenshots/a3-webapp-deployment-handoff-rc2-mobile-390x844.png`

## 7. 封存边界

本轮没有修改 rc.2 封存 manifest、Golden Agent 记录、rc.2 release note、
Round 14 Growth Auditor 或它们引用的策略输入。本轮是 post-seal 产品和
API 修正，不是新 Release，也没有声称完成真实 staging 或 production 部署。
