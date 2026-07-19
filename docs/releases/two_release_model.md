# Ashr 的两套 Release

Ashr 有两个完全不同的发布对象。它们必须独立编号、独立生成证据、独立测试，并分别给出 `GO / NO-GO`。

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

因此，不能用“某个客户 Agent 通过评测”证明 Ashr 产品可以发布；也不能用“Ashr 安装和单测通过”证明某个客户 Agent 可以上线。

## 3. 独立判定

最终报告必须同时给出：

```text
Ashr Product Release: GO / NO-GO
Customer Agent Release: GO / NO-GO
```

其中任一通过都不会自动改变另一项的结论。
