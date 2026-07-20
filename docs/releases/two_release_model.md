# Ashr 的两套 Release

Ashr 有两个完全不同的发布对象。它们必须独立编号、独立生成证据、独立测试，并分别给出 `GO / NO-GO`。

这不是“同一个 Release 的两个阶段”，而是两个不同的可交付物：

| 发布域 | 谁发布 | 交付给谁 | 交付物 |
| --- | --- | --- | --- |
| Ashr Product Release | Ashr 产品团队 | 部署/采购 Ashr 的企业 | OCI 镜像、Docker 安装器、Web、SDK、策略、迁移、运维手册、SBOM、签名、provenance 和 Product receipts |
| Customer Agent Release | 使用 Ashr 的客户组织 | 该组织的 Agent 上线审批方和业务使用方 | 指定 Agent 版本、A1 执行证据、A2 评测证据、人工审批、A3 报告/门禁/回写、签名证据包和 Agent receipts |

## 1. Ashr Product Release

发布对象是 **Ashr 产品本身**，规范 ID：

```text
ashr-product@<semver>
```

第一版企业交付目标：

```text
ashr-product@1.0.0
```

Product Release 证明的是：

- 仅依赖 Docker 的 Linux/Windows 一键安装；
- 管理员初始化、迁移、健康检查和重启后持久化；
- 邮箱注册、验证、登录、忘记/重置/修改密码；
- Google/GitHub OAuth、同账户绑定、TOTP 2FA、恢复码和设备会话撤销；
- Stripe Test Mode、国内支付 Provider 合同和 entitlement 强制执行；
- Python、TypeScript、Go SDK 的真实 Hosted 调用链；
- 多租户隔离和 RBAC；
- 备份/恢复、升级、回滚、日志/指标/审计；
- Web 注册登录、SDK quickstart、报告和审核；
- Web 生产界面的 UTF-8、字号、控件尺寸和禁止 mock/fixture/只读预览回退静态门禁；
- A1/A2/A3 的产品级真实集成 smoke；
- 多模态、安全策略和签名报告导出；
- OCI 镜像 digest、SBOM、签名和 provenance。

执行入口：

```powershell
python scripts/verify_product_release.py `
  --manifest dist/releases/ashr-product-1.0.0/manifest.json `
  --repo-root . `
  --output dist/releases/ashr-product-1.0.0/verification.json
```

Verifier 是 fail-closed 的。缺失、失败、mock、fixture、dry-run、digest 不匹配、脏源码、未固定镜像或缺少供应链证据都会产生 `block_product_release`。

验证成功后产生两个必须长期保存的绑定值：

```text
product_release_id
product_release_manifest_sha256
```

## 2. Customer Agent Release

发布对象是 **客户交给 Ashr 评测并准备上线的某个真实 Agent**，规范 ID：

```text
agent-release:<org>/<agent>@<version>
```

Customer Agent Release 证明的是：

- 客户、组织、项目和 Agent 候选版本身份确定；
- A1 使用真实隔离执行生成不可变运行证据；
- A2 使用真实评测、多模态、安全策略和校准证据作出判断；
- 人工审核、override、waiver 和 approval 可审计；
- A3 生成报告、门禁和发布回写；
- 最终证据包完整、可验证并已签名；
- 任何证据缺失或来源不可信时 fail-closed。

每个 Customer Agent Release 必须绑定：

```text
product_release_id
product_release_manifest_sha256
```

绑定关系是单向的：Customer Agent Release 必须依赖一个已经 `GO` 的
Product Release；Product Release 不依赖任何单个客户 Agent 的评测结果。
若产品发布不存在、不是 `GO`、ID 不匹配或 manifest 摘要不匹配，Customer
Agent Release 必须直接 `NO-GO`。

因此，不能用“某个客户 Agent 通过评测”证明 Ashr 产品可以发布；也不能用“Ashr 安装和单测通过”证明某个客户 Agent 可以上线。

## 3. 独立判定

最终报告必须同时给出：

```text
Ashr Product Release: GO / NO-GO
Customer Agent Release: GO / NO-GO
```

其中任一通过都不会自动改变另一项的结论。

## 4. 双制品构建与验证

从同一个已测试且干净的提交生成两套候选制品：

```powershell
python scripts/build_dual_release_candidates.py
```

重新验证上传索引：

```powershell
python scripts/build_dual_release_candidates.py `
  --verify-index dist/releases/dual-release-index.json
```

单独验证 Customer Agent Release：

```powershell
python scripts/verify_customer_agent_release.py `
  --manifest dist/releases/agent-release-demo-a3-golden-agent-0.2.0-rc.2/manifest.json `
  --release-root dist/releases/agent-release-demo-a3-golden-agent-0.2.0-rc.2
```

构建成功只证明资产完整、摘要一致，不等于 `GO`。GitHub 上传和 Product/Customer 发布判定彼此独立；任何 `NO-GO` 候选只能作为 prerelease，并必须保留阻断原因。完整发布和下载回读步骤见 `docs/releases/github_dual_release_runbook.md`。
