# A3 Growth Auditor Round 17：服务器权威部署回执

- 日期：2026-07-13
- 审计模式：fail-closed commercial audit
- 范围：service-account verifier、readback chain、acceptance projection、API、DB、UI

## 结论

Round 16 的第 2、11 项已经实现：A3 现在可以通过服务器专用 resolver 接收并
校验外部权威回读，且严格绑定 receipt、candidate、A1 run、五层 scope、SHA-256、
verifier authority 和 blocker 专用 claims。浏览器和普通用户不能执行权威验证。

这个能力让真实生产证据“有地方安全进入系统”，但目前没有任何一条真实生产
readback，所以九个 deployment blocker、A2 同候选 authority、main required
Check 和 staging/VPC 证明仍然没有关闭。

## 20 个下一轮增长点

| # | 可执行改进 | 优先级 | 负责人 | 必需证据 |
|---:|---|---|---|---|
| 1 | 生成与 rc.2 run 和五层 scope 完全一致的 A2 Trusted Spine | blocker | A2 | snapshot、ledger record、head hash、allow/release-ready 结论 |
| 2 | 把 A2 resolver 接到真实可信服务，而非测试注入函数 | blocker | A1/A2 | service identity、mTLS/audience、same-candidate readback |
| 3 | 在 staging/VPC 部署 A1 hosted identity verifier | blocker | A1 | issuer、audience、service version、health receipt |
| 4 | 执行 PostgreSQL migration 和 RLS allow/deny probe | blocker | A1/A3 | migration digest、same-tenant allow、cross-tenant deny、backup marker |
| 5 | 接入 Queue/Worker retry、DLQ、lease recovery resolver | blocker | A1 | worker identity、attempt chain、recovery receipt |
| 6 | 接入 immutable object storage digest/retention resolver | blocker | A1/A3 | object version、digest、retention、tenant binding |
| 7 | 接入 deployment image/config/migration/health/network resolver | blocker | A1/A3 | deployment identity、digests、health、network、tenant isolation |
| 8 | 完成 upgrade/failure/rollback/restore 演练 | blocker | A1/A3 | operation chain、duration、final health、data validation |
| 9 | 安装 tenant-bound GitHub App 并接入 installation resolver | blocker | A1/A3 | installation alias、repo、app slug、Check identity |
| 10 | 强制 main required Check 并接入 policy resolver | blocker | maintainer | branch-policy readback、失败候选 merge denial |
| 11 | 给 resolver response 增加签名或 mTLS attestation 验证 | high | A1/A3 | key/cert reference、signature verification、rotation test |
| 12 | 增加 readback freshness/expiry policy | high | A2/A3 | policy version、captured/verified age、stale denial |
| 13 | 验证 resolver 超时、重试、熔断和重复 delivery | high | A1/A3 | timeout receipt、retry schedule、single-write proof |
| 14 | 建立 Postgres 并发 sequence/append-only 测试 | high | A1/A3 | transaction isolation、unique conflict、chain continuity |
| 15 | 将 readback index 纳入下一份 Audit Bundle | high | A3 | manifest entry、hash、custody event、bundle verifier |
| 16 | 重建并重新封存 Deployment Acceptance | blocker | A1/A2/A3 | source IDs、readback IDs、new acceptance hash、signature |
| 17 | 重建 Release Artifact 并保持 A2 authority 不被 A3覆盖 | blocker | A3 | manifest、candidate SHA、A2 ledger binding、production false/true 依据 |
| 18 | 增加 10k receipts/readbacks 的分页和性能验证 | medium | A1/A3 | latency、memory、query plan、tenant isolation |
| 19 | 改善 390px 下五列表格的移动 triage 体验 | medium | A3 | task completion、无页面溢出、可访问性检查 |
| 20 | 让企业 reviewer/operator 完成一次部署证据验收 | high | Product/A3 | 任务时间、错误率、authority 理解度、审计导出反馈 |

## 商业与安全边界

- 本轮交付的是可执行的验证控制面，不是客户环境部署回执。
- `production_verified` 只能来自服务器 resolver，不能来自浏览器 body。
- verified 的全部 required claims 必须为 true。
- readback 只形成只读 projection，不能原地改写封存验收。
- A3 不重算 A2 score、pass/fail、failure class、Decision 或 Release Ready。
- `.env.local`、API key、token、cookie、email、signed URL 和私有路径不进入制品。
- 当前 Draft PR 必须继续保持 blocked/non-production 表述。
