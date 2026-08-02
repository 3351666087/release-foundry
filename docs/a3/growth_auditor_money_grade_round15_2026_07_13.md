# A3 Growth Auditor Round 15：候选完整性与部署交接

- 日期：2026-07-13
- 审计模式：fail-closed commercial audit
- 范围：current authority、candidate binding、deployment handoff、API、UI、审计与商业闭环

## 结论

本轮关闭了一个高风险展示问题：历史封存包的 `block` 不再被误当成当前
权威结论。A3 后端发现 A1 run 与 A2 Trusted Spine 不属于同一 candidate
后，页面明确显示 `integrity_invalid` 和 `unknown`。这提升了企业客户对
发布证据链的可信度，但没有增加任何生产部署证明。

## 20 个增长审计点

| # | 可执行改进 | 优先级 | 负责人 | 完成证据 |
|---:|---|---|---|---|
| 1 | 为 `a3-golden-20260712-002` 和同一五级 scope 生成 A2 Trusted Spine | blocker | A2 | evidence snapshot、ledger record、head hash、scope receipt |
| 2 | 将 A1 run、A2 ledger、A3 artifact 和 candidate SHA 固定为一个 candidate ID | blocker | A1/A2/A3 | end-to-end candidate binding 全部 5/5 |
| 3 | 部署 A1 hosted identity verifier | blocker | A1 | deployment identity、issuer/audience、version、health |
| 4 | 建立真实 PostgreSQL migration 与 RLS | blocker | A1/A3 | migration digest、跨租户 deny、同租户 allow、backup marker |
| 5 | 建立 durable queue worker | blocker | A1 | enqueue、retry、dead-letter、lease recovery、health |
| 6 | 把 Audit Bundle 写入 immutable object storage | blocker | A1/A3 | object version、digest、retention、tenant scope、readback |
| 7 | 部署真实 staging/VPC candidate | blocker | A1/A3 | image/config/migration digest、health、network、tenant isolation |
| 8 | 完成 upgrade 与 rollback 演练 | blocker | A1/A3 | failure trigger、rollback id、duration、恢复健康 |
| 9 | 完成 backup 与 restore 演练 | blocker | A1/A3 | backup id、restore id、数据校验、恢复后健康 |
| 10 | 安装 tenant-bound GitHub App | blocker | A1/A3 | tenant、installation、app slug、permission、repo binding |
| 11 | 对 main 强制 required Check | blocker | maintainer | policy readback 与失败候选 merge denial |
| 12 | 把当前 authority 与 sealed history 做成 API 兼容测试矩阵 | high | A3 | old client/new client contract tests |
| 13 | 为 handoff 增加 owner acknowledgement | high | A3 | 负责人、时间、comment、不可篡改 audit event |
| 14 | 为 required receipt 增加上传、校验和拒绝流程 | high | A3 | typed receipt、redaction、hash、review state |
| 15 | 增加 candidate rebinding CLI 的 dry-run 模式 | high | A3 | 不写数据的 mismatch report 与退出码 |
| 16 | 对 10k checks/runs 验证 Handoff 页面性能 | medium | A3 | pagination/virtualization、Web Vitals、内存回执 |
| 17 | 为移动端四列表格增加列选择或摘要视图 | medium | A3 | 390px 可完成主要 triage，不依赖完整横向滚动 |
| 18 | 为 GitHub App webhook 增加签名、重放与幂等校验 | high | A1/A3 | signature、delivery ID、replay denial、outbox receipt |
| 19 | 将 SBOM、SCA 与 build provenance 纳入 Release Artifact | high | A3 | signed SBOM、scanner receipt、provenance digest |
| 20 | 由真实客户角色完成一次 Golden Path 可用性验收 | high | A3/Product | 操作时长、错误率、阻塞理解度、审计导出反馈 |

## 商业解释

企业购买的不是一张“测试通过”截图，而是可以回答以下问题的控制面：

- 这个结论属于哪个客户、项目、环境、run 和 Git SHA？
- A1 执行事实与 A2 裁决是否来自同一个 candidate？
- 当前结论与历史封存结论是否被混淆？
- 哪个团队负责下一步，必须提交什么回执？
- 合同、本地模拟、真实外部回读和生产证明是否清楚分级？

本轮已经把这些问题变成可读 API 和产品页面。真正可收费的企业部署仍需
完成前 11 个 blocker，尤其是 A2 同候选裁决、tenant GitHub App、main
门禁和真实 staging/VPC 基础设施。

## 安全结论

- A3 没有重算 A2 score、pass/fail、failure class 或 Release Ready。
- 历史封存包没有覆盖当前后端 verifier。
- 页面和 OpenAPI 没有 secret、token、cookie、email、OTP 或私有路径。
- `.env.local` 不参与构建、测试、截图或提交。
- 本轮没有生产升级、回滚或部署授权，因此没有声称 production ready。
