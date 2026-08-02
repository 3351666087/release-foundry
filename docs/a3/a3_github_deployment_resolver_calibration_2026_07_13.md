# A3 GitHub 部署验证器真实校准

- 日期：2026-07-13
- 仓库：`3351666087/release-foundry`
- 校准 head：`8d82fd4f1a23032f796a6a2149f51732ef3abe7e`
- 范围：GitHub App installation、Check identity、main required-check policy
- 操作模式：只读，没有修改分支保护、没有尝试合并、没有发布新 Check

## 1. 这轮补上的真实链路

此前 A3 已有通用的服务器权威回执入口，但 GitHub 两类 blocker 还没有具体
resolver。现在新增：

1. 仓库 installation 只读回读和净化；
2. Check Run 身份回读，区分 `github-actions` 与 tenant custom App；
3. main required status check 回读；
4. A1 tenant-installation binding 回执校验；
5. failing-merge denial 与 maintainer policy 回执哈希校验；
6. candidate、Run、五层租户 scope 和 evidence SHA-256 绑定；
7. 通过内部 HTTP verify 路由持久化可信 `rejected` readback 的集成测试。

resolver 的 GitHub 目标由服务器固定。回执中的 selector、repo、branch、URL 或
token 不能改变实际读取目标。

## 2. 真实 GitHub 结果

| 项目 | 真实结果 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 当前 head Check | HTTP 200，名称/head/conclusion 匹配 | CI 确实运行并成功 | 不是 tenant custom App |
| Check App | `github-actions`，App ID `15368` | 当前 Check 由 GitHub Actions 发布 | 不能充当客户 tenant 绑定身份 |
| Repository installation | HTTP 401 `permission_denied` | 当前 operator OAuth 无权读取 installation | 不能据此断言仓库绝对没有安装 |
| main required check | HTTP 404，`enforced=false` | 当前凭据读取不到已启用的 required-check policy | 不能声称失败候选一定无法合并 |

对应脱敏证据：

- `fixtures/a3/p3/a3_github_check_head_8d82fd4_live_readback.redacted.json`
- `fixtures/a3/p3/a3_github_repository_installation_live_readback_20260713.redacted.json`
- `fixtures/a3/p3/a3_github_main_required_check_live_readback_20260713.redacted.json`
- `fixtures/a3/p3/a3_github_deployment_verifier_calibration_20260713.redacted.json`

## 3. 为什么结果必须是 rejected

### GitHub App installation

三项 claim 必须同时为真：

- `tenant_installation_bound`
- `repository_bound`
- `check_identity_verified`

当前没有 A1 tenant-installation binding receipt，installation 回读为 401，并且
真实 Check App 是 `github-actions`。因此三项都不能通过，resolver 必须返回
`rejected / policy_not_satisfied`。

### Required check enforcement

三项 claim 必须同时为真：

- `required_context_enforced`
- `failing_merge_denied`
- `maintainer_readback_verified`

当前 main policy 回读为 404，也没有哈希有效的 failing-merge denial 和 maintainer
policy receipt。因此同样只能返回 `rejected / policy_not_satisfied`。

## 4. 已验证的服务端闭环

自动化测试已走通以下路径：

```text
提交 metadata receipt
  -> reviewer acknowledge
  -> A1-verified service account 调用 internal verify
  -> GitHub resolver 读取 provider state
  -> A3 生成 rejected authoritative readback
  -> Store + audit event + outbox 持久化
  -> Dashboard inbox 仍显示 production_verified_count = 0
  -> Deployment Acceptance 仍为 8/17
```

这证明失败也能被可信记录，而不是把 API 错误吞掉或伪造成成功。真实校准 fixture
本身没有写入 Store，所以它明确标记 `authoritative_store_readback_persisted=false`。

## 5. 当前准确状态

- Golden Path：`7/11`
- Deployment Acceptance：`8/17`
- current authority：`integrity_invalid`
- current A2 decision：`unknown`
- historical A2 decision：`block`
- production verified receipts：`0`
- production ready：`false`

## 6. 还需要外部人员完成什么

1. A1/平台侧创建并安装真正的 tenant-bound custom GitHub App，提供哈希有效的
   tenant-installation binding receipt，并让 release Check 由该 App 发布。
2. 仓库 maintainer 在 main 启用 required check，并提供失败候选被拒绝与策略审批
   的权威回执。
3. 用同一 candidate ID、最新 Git SHA、A1 evidence、A2 Trusted Spine、A3 artifact
   重新生成和封存完整 Release packet。

本轮没有改写 sealed rc.2 bundle、archive、manifest 或 A2 决策。
