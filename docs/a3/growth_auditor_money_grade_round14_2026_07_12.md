# A3 Growth Auditor Round 14: Golden Agent Repair

- Date: 2026-07-12
- Review mode: independent fail-closed audit
- Scope: real local tool execution, A1/A2 re-evaluation, rc.2 evidence, UI provenance, documentation custody

## Verdict

本轮关闭了 Round 13 的媒体工具执行缺口，并发现、修复了两个会误导审计的 A3 问题：未经过 CI 时伪填 CI SHA，以及同一 Tool Call 在 UI 中重复计数。rc.2 的案例质量明显提升，但企业仍不能据此签字上线，因为 A2 Decision Ledger、部署、租户 GitHub App 和仓库策略没有闭环。

## Newly Sellable Workflow

研发人员现在可以看到一个可复现的修复过程：rc.1 的 Echo Agent 被 A2 拒绝，rc.2 真正执行价格和媒体工具后获得 A2 3/3；负责人同时看到 Decision Ledger 仍是 block。这个对比能证明平台不会用“测试通过”冒充“发布批准”。

## Growth Points

| # | 增长点 | 优先级 | 当前证据 | 下一步证明 |
|---:|---|---|---|---|
| 1 | 新 A2 allow Decision Ledger | blocker | 案例 3/3，但旧 ledger block | A2 为 run `002` 生成并持久化 allow 记录 |
| 2 | rc.2 GitHub CI readback | high | candidate run `29193799075` 已通过并绑定 merge SHA；rc.2 packet Check 尚未发布 | evidence commit 后回读 rc.2 Check |
| 3 | rc.2 Actions artifact readback | blocker | 本地制品 | 下载 artifact，验证 digest 和内部 manifest |
| 4 | 租户 GitHub App | blocker | 未安装 | installation/repo/permission receipt |
| 5 | main required check | blocker | branch protection 未启用 | 严格 readback 证明 check 被强制要求 |
| 6 | 真实 staging health | blocker | deployment probe not_proven | version/health/dependency readback |
| 7 | PostgreSQL/RLS | blocker | contract only | migration + cross-tenant denial receipt |
| 8 | durable queue | blocker | contract only | retry/dedupe/dead-letter/worker health |
| 9 | immutable object storage | blocker | local bundle | object version、retention、hash readback |
| 10 | upgrade/rollback | blocker | 未演练 | install → upgrade → rollback receipt |
| 11 | backup/restore | blocker | 未演练 | backup id、restore target、data verification |
| 12 | A1/A2 branch contract adoption | high | 只读观察 A1 `f956249`、A2 `db12d21` | 等 main 合并后重新生成 typed client 和 compatibility report |
| 13 | 真实 GitHub App webhook | high | 无 webhook | signature、delivery id、replay/idempotency proof |
| 14 | GitLab release status | high | 未实现 | project binding、commit status、readback |
| 15 | 企业微信通知 | high | contract shell | sandbox app、签名、真实消息 readback |
| 16 | 飞书/钉钉通知 | medium | contract shell | tenant-scoped channel and delivery receipts |
| 17 | KMS/SSO archive signer | high | local self-signed Ed25519 | key id、principal、verification receipt |
| 18 | SBOM and provenance | high | 未纳入 artifact | SPDX/CycloneDX + signed build provenance |
| 19 | container/SCA scan | high | npm audit 独立 | scan receipt hashed into release manifest |
| 20 | full Golden regression | high | 3-case slice | A1 执行完整 Golden/Incident pack，A2 全量判定 |
| 21 | tool implementation registry | medium | Agent 内置 4 个工具 | versioned tool capability + permission manifest |
| 22 | media extractor isolation | high | 本地进程读取 PNG | A2 合并后采用隔离 worker、qualification、artifact authorization |
| 23 | large-run virtualization | medium | 3 cases | 10k case pagination/virtualization/performance receipt |
| 24 | report signer download UX | medium | 页面只读 | authenticated download、expiry、revoke、audit |
| 25 | release comparison UI | medium | source 下拉可切 rc.1/rc.2 | 显式 old-vs-new diff 和 regression explanation |
| 26 | CI provenance UI | medium | `not bound` 文本 | 展示 candidate SHA、merge SHA、workflow URL、artifact digest |
| 27 | deployment probe collector | high | 手工 not_proven JSON | A1 API collector + signed receipt + retry state |
| 28 | support bundle | medium | 本地 evidence packet | 自动脱敏、加密、下载控制、customer support workflow |

## Audit Conclusions

- 真能力：A1 Runner 实际执行 Agent；Agent 实际读取测试资料和 PNG；A2 Judge 实际重算；bundle/archive/manifest 实际验哈希。
- 契约能力：GitHub App、PostgreSQL、queue、object storage、deployment 等仍只有字段和 fail-closed 检查。
- 生产验证：本轮没有新增生产部署证明。
- 商业价值：最强新增价值是“修复前后可解释、A2 不被绕过、Decision Ledger 独立”的 Release Review 故事。
- 下一轮主线：先完成 rc.2 packet GitHub 回读；网络条件允许后再处理 GitHub App/branch protection；同时等待 A2 主分支提供 run `002` 对应的权威 Decision Ledger。
