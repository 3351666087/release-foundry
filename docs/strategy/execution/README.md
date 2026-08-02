# ReleaseFoundry Modular Execution Index

本目录是长周期开发的执行入口。产品总战略仍以
`docs/strategy/large-saas-a1-a2-a3-full-plan.md` 为准；本索引只负责把战略拆成可勾选、可验证、可恢复的模块。

## Current Pointer

- Current module: `M50 SaaS Control Plane`
- Current item: `M50-03`
- Checklist: `docs/strategy/execution/M50-saas-control-plane.md`
- Baseline commit: `1d292047e991995fdf52f0545ffff410ee19a171`
- Current candidate: `a3-golden-agent@0.2.0-rc.3`
- Current A1 run: `a3-golden-20260720-003`
- Current A2 authority: `e21ebcb1b09b2a709f5381e02f89933477453d82`
- Current A2 decision: `block` at `sha256:93343a7920b06dc0f232aee7b3eb82b793010ca8c2061043682b4e7ebc088797`
- Current A2 grades: `sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304`
- Last audit date: `2026-07-21`

每完成一项，必须先更新对应模块中的证据，再把 `[ ]` 改成 `[x]`。完成当前模块后，才允许修改这里的 Current Pointer。

## Context Loading Rule

每轮默认只读取以下内容：

1. 本文件。
2. Current Pointer 指向的一个模块文件。
3. 当前任务直接涉及的代码、测试和 A1/A2/A3 handoff。
4. `git status -sb`、最新 `main` SHA 和相关 CI 状态。

不要默认加载全部 worklog、全部历史截图或全部 strategy 文档。需要历史证据时按模块文件中的路径定点读取。

## Checkbox Protocol

- 每项使用稳定 ID，例如 `M40-03`，不得重编号已存在条目。
- `[x]` 表示已有代码或文档、验证命令通过、证据路径已记录。
- 只有页面、mock、fixture 或 contract 时，不得勾成 production complete。
- 外部权限、商户资质、客户环境或人工审批缺失时，保持 `[ ]` 并记录 `BLOCKED:`。
- 一轮只主攻一个未完成项；顺手修复必须与该项直接相关。
- 每轮结束必须更新模块的 Evidence Log、Current Pointer 和提交状态。
- A3 不得重算或覆盖 A2 Decision Ledger；A1 运行成功也不等于 A2 release allow。
- 所有发布结论必须来自最新 `main`、同一 candidate identity 和可重算证据。

## Module Index

| Module | Scope | State |
| --- | --- | --- |
| [M00](M00-execution-control.md) | Goal、清单、上下文与证据纪律 | done |
| [M10](M10-platform-runtime.md) | A1 SDK、Runner、API、数据与基础设施 | maintenance |
| [M20](M20-evaluation-policy.md) | A2 Scenario、Judge、Calibration、Decision Ledger | maintenance |
| [M30](M30-product-console.md) | A3 Product Console、Review、Report、Admin UI | maintenance |
| [M40](M40-cross-lane-trusted-release.md) | A1/A2/A3 同候选绑定与发布权威 | current |
| [M50](M50-saas-control-plane.md) | Identity、Tenant、RBAC、数据库与 hosted control plane | queued |
| [M60](M60-commercial-integrations.md) | Usage、Billing、国内支付与外部集成 | queued |
| [M70](M70-release-distribution.md) | 双 Release、制品、供应链与发布自动化 | maintenance |
| [M80](M80-production-acceptance.md) | Staging/VPC、运维、安全与生产验收 | queued |

## Resume Template

新窗口或上下文压缩后，先执行：

```text
读取 docs/strategy/execution/README.md。
只加载 Current Pointer 指向的模块清单和该条目的直接证据。
以最新 main 为准，核对 A1/A2/A3 handoff。
只处理当前未勾选项；验证通过后更新 Evidence Log 并打勾。
不要凭历史对话宣称完成，不要跳过 A2 权威或生产回执。
```
