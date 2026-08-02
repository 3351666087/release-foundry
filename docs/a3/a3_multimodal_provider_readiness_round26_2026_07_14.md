# 多模态 Provider 就绪度诊断接入 - Round 26

日期：2026-07-14

## 一句话说明

A3 现在可以把 A2 的“模型可用性比较”和“阶段延迟诊断”作为一个原子、公开安全、租户隔离的
证据包接入控制台。页面会诚实显示：30 次尝试只有 1 次完成，29 次失败或超时，0 个合格输出，
4 个结构化输出档位全部失败。warm 延迟从冷启动的 74.3 秒降到最快 1.64 秒，只能帮助排障，
不能被解释成 Provider 可用、模型质量合格或允许发布。

## 校准基线

- authoritative `origin/main`: `ccf6ce5`
- latest A1 peer: `f3071aa`
- exact A2 Round 51 source: `7504680`
- A3 previous head: `de6d116`
- product strategy: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- Draft PR: `#35`

A2 `7504680` 仍是 peer-branch 证据，不是 main 或生产权威。A3 只消费公开安全的聚合计数、状态、
原因码、阶段耗时和 SHA-256，不复制 Provider endpoint、Secret、原始回复、模型二进制或私有媒体。

A1 `f3071aa` 增加 `IdentityCredentialLinkCoordinator` 原子账号凭据绑定契约，但其统一 identity
`link_start` / `link_complete` 路由仍为 `proposed` 且 `client_callable=false`。API Reference 已更新
peer 元数据并明确该边界，没有提前启用或宣称接口已上线。

## 真实诊断事实

### 可用性比较

| 模型 | 尝试 | 完成 | 失败 | 超时 | 合格输出 | A2 qualification |
|---|---:|---:|---:|---:|---:|---|
| `llava:7b` | 15 | 1 | 14 | 14 | 0 | blocked |
| `qwen3-vl:4b` | 15 | 0 | 15 | 15 | 0 | blocked |
| 合计 | 30 | 1 | 29 | 29 | 0 | 0 个 qualified Provider |

- `quality_comparison_performed=false`
- `provider_is_truth=false`
- `release_authority=false`
- 两个模型使用相同 case set；A3 校验尝试数、完成数、失败数、超时数和合格数守恒。

### Qwen 阶段延迟探针

| Profile | Wall time | Structured output | 结果 |
|---|---:|---|---|
| `cold_plain_32` | 74.299641s | invalid | failed |
| `warm_plain_32` | 4.402444s | invalid | failed |
| `warm_plain_8` | 1.640260s | invalid | failed |
| `warm_json_schema_8` | 1.831776s | invalid | failed |

四个 profile 都未完成有效结构化输出，所以 `completed_profile_count=0`，
`valid_structured_profile_count=0`，最终状态必须是 `blocked_provider_readiness`。模型加载变快只说明
warmup 可能是冷启动延迟的重要部分；输出仍然无效，因此不能声称 Provider 可用。

## 权威边界

| 事实 | 权威负责人 | A3 可以做什么 | A3 不能做什么 |
|---|---|---|---|
| 生产路由、容量、运行健康 | A1 | 展示 A1 后续提供的公开安全回执 | 由本地安装或延迟推断生产健康 |
| 评测、质量、资格 | A2 | 校验并展示 A2 状态 | 重算 score、pass/fail 或 qualification |
| 产品展示、报告、审核协调 | A3 | 持久化、筛选、导出、审计、提醒 | 生成发布权或覆盖上游结论 |

所有投影都固定：

- `release_authority=false`
- `a2_decision_recomputed=false`
- `release_decision_changed=false`
- `production_ready=false`
- `operational_health_verified=false`
- `routing_ready=false`
- `capacity_verified=false`

## 原子 intake 与严格验证

新增契约：

- `a3.a2_multimodal_provider_readiness_intake.v1`
- `a2.local_multimodal_availability_comparison.v1`
- `a2.ollama_multimodal_latency_probe.v1`
- `a3.multimodal_provider_readiness.v1`

验证器执行以下 fail-closed 检查：

1. 每层对象使用精确字段 allowlist，未知字段直接拒绝；
2. availability 与 latency probe 必须在同一个原子 envelope 中通过，不能部分导入；
3. 每个 Provider 的 `completed + failed = attempted`；
4. `eligible <= completed`，`timeout <= failed`；
5. 相同 case set 下每个模型的 attempted count 必须一致；
6. median、p95 和 maximum 延迟必须单调；
7. latency probe 的 model ID 必须出现在 availability comparison；
8. 四个 profile 必须唯一且完整；
9. caller wall time、Provider total time 和 transport/client residual 必须自洽；
10. artifact、model、prompt、schema 和 response hash 必须符合 SHA-256 契约；
11. release authority、Provider truth、raw payload 和 Secret flags 必须保持安全值；
12. URL、signed URL、token、cookie、email、DSN、本地账号路径和原始响应会被拒绝。

## Store、数据库与 API

`p3-a2-round51` 现在同时承载多轮稳定性和 Provider 就绪度诊断。新增受保护接口：

```text
POST /api/a3/import/a2-multimodal-provider-readiness
GET  /api/a3/providers/multimodal-readiness
```

- import 要求服务端验证 principal、`project:ingest`、五级 tenant scope 和请求头
  `Idempotency-Key`；
- read 要求服务端验证 principal、`release:review` 和完整五级 scope；
- 跨租户读取返回脱敏 404；
- Memory、JSON-file 与 SQLite 都可保存并在重启后恢复；
- import 生成 metadata-only access audit、domain audit、Event Outbox 和 usage meter；
- 同一个 idempotency key + 同一个 payload 安全 replay，变化后的 payload 返回冲突；
- SQLite 继续使用既有 scoped Dashboard snapshot，不绕过 SQL/RLS 产品边界。

商业 API 增加：

```text
POST /v1/providers/multimodal/readiness
GET  /v1/providers/multimodal/readiness
```

商业端点总数由 46 增加到 48。OpenAPI runtime operation parity 由 `67/67` 增加到 `69/69`。

## OpenAPI 与 API Reference

OpenAPI 新增四组严格 schema：

- `A2MultimodalProviderReadinessEnvelope`
- `MultimodalProviderReadinessImportRequest`
- `MultimodalProviderReadinessIngestReceipt`
- `MultimodalProviderReadiness`

两个 route 都记录五级 scope、RBAC、auth、usage、audit、request boundary、evidence boundary 和
authority boundary。Dashboard schema 也把 `multimodal_provider_readiness` 声明为正式字段。

API Reference 升级到 `a3.api_reference.v15`，新增两个 Provider 接口的中英文说明、请求/响应示例、
30/1/29/0 和 0/4 的真实脱敏事实，并更新 A1 peer 到 `f3071aa`。Reference 明确：A1 的原子
credential-link coordinator 已定义，但对应统一 identity 路由仍 proposed、不可由客户端调用。

## Dashboard 与报告

同一 Provider 投影已接入：

- Dashboard snapshot：`multimodal_provider_readiness`
- Review queue：`multimodal_review_queue.provider_readiness`
- JSON report
- Markdown report
- Hosted Report payload 与 HTML

报告只导出聚合计数、状态、原因码、阶段耗时和哈希，不导出 endpoint、Secret、raw response、
model binary、private media 或 signed media URL。

## Delivery 产品界面

Delivery 页面新增独立 React 组件 `MultimodalProviderReadinessPanel`，不是继续扩大单个页面 blob。
中文优先界面展示：

- 主结论：`Provider 尚未达到可用门槛`；
- 明示：`变快不等于可用，安装成功不等于质量合格`；
- 30 次尝试、1 次完成、29 次失败、29 次超时、0 个合格输出、0/4 有效档位；
- 两个模型的完成、失败、超时和合格计数；
- cold 74.3 秒与 fastest warm 1.64 秒；
- 四个 profile 的耗时和 `invalid_structured_output`；
- 运行平台、评测服务、产品控制台的权威职责说明；
- 未导入时的明确 empty state，不把缺数据推断为 ready。

客户界面没有使用 A1/A2/A3 lane badge；内部 owner 和 source metadata 只保留在契约与审计证据中。

## 视觉证据


两张截图已人工检查。桌面信息密度可读；390 x 844 先显示阻塞结论和指标，再进入模型明细；页面没有
document/body 横向溢出，标题与状态没有重叠，长模型 ID 和状态标签没有冲出容器。

## 本地验证结果

- focused Provider/OpenAPI/API Reference: `28` passed, `0` failed；
- full A3 Node: `513` passed, `0` failed, `1` target-PostgreSQL opt-in skip；
- current-main A2: `186/186` passed；
- Next.js TypeScript: passed；
- Next.js production build: passed, `15` static pages；
- Playwright: `46/46` passed with one worker；
- OpenAPI runtime parity: `69/69`；
- Commercial API endpoints: `48`；
- CL hygiene: `0` findings；
- Commercial CL: `0` blockers, `0` advisories；
- root/Webapp production dependency audit: `0` vulnerabilities；
- GitHub Actions feature commit `1809513`: CL Gate run `29338036122` passed Plan/Hygiene,
  A3 Node, Next.js/Playwright, Python A1/A2, pinned evidence, Golden Path artifact and final summary；
- TypeScript SDK、Go SDK 与 Rust verifier 按 changed-path plan 跳过，不是失败；
- CI advisory: GitHub 官方 actions 仍声明 Node 20 runtime，runner 已强制使用 Node 24；这是后续维护项，
  没有改变本轮成功结论；
- `.env.local`: ignored and absent from Git status。

## 仍未完成

- Provider 可用性仍被 A2 真实诊断阻塞；当前不是质量合格状态；
- 尚无 A1 生产 Provider routing、capacity、health 和 failover 回执；
- 尚无真实 hosted Provider workload identity、endpoint attestation 或容量压测；
- A2 specificity、良性文本误报率和多模态敏感度仍未达到发布门槛；
- 真实 non-empty human-review receipt 和 terminal disposition 仍缺失；
- 最新 A1 run、A2 Decision Ledger 与 A3 artifact 尚未绑定同一个 candidate；
- A1 `f3071aa` 原子 credential-link 仍是 peer-only proposed route；
- tenant-bound GitHub App、main required check、真实 merge denial 仍未证明；
- staging/VPC、target PostgreSQL、object storage、tenant KMS、升级和回滚回执仍缺失。

因此事实状态不变：Golden Path `7/11`，Deployment Acceptance `8/17`，当前 authority
`integrity_invalid`，当前 A2 decision `unknown`，历史 A2 decision `block`，production receipts
`0`，`production_ready=false`。
