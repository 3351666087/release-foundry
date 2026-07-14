# A2 多轮校准稳定性接入 - Round 25

日期：2026-07-14

## 一句话说明

A3 现在可以把 A2 的多轮多模态校准结果作为一个原子、只读、可审计的数据包接入控制台，展示
“结果是否稳定复现”和“质量是否达到门槛”这两个不同问题。当前真实结论是：三轮数据完整且数值
一致，但三轮都被 A2 阻断，因此页面必须显示“完整且稳定，但质量未达标”，绝不能显示 PASS。

## 校准基线

- authoritative `origin/main`: `ccf6ce5`
- latest A1 peer: `81f7e9e`
- exact A2 Round 51 source: `7504680`
- A3 previous head: `7f1b76b`
- product strategy: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- Draft PR: `#35`

2026-07-14 最终 `git fetch origin --prune` 后，A2 peer 分支指向 `7504680`。它仍未进入 main，
所以只作为非权威校准数据使用。A3 fixture 是由四份公开安全 A2 契约组合成的原子 intake envelope，
不是把原始 Provider 响应、私有媒体或真人身份复制进 A3。

A1 peer `81f7e9e` 新增了注册和登录分离、服务端单次 proof receipt、账号绑定再认证与 CSRF 等身份
强化。A3 已更新 API Reference 的 peer 元数据，但仍以 main 的身份能力为产品权威，不提前启用或
宣称 peer-only 注册能力已经生产可用。

## A2 真实事实

| 项目 | Round 51 事实 | A3 解释 |
|---|---:|---|
| 重复轮次 | 3 | 三次独立 retained calibration |
| 每轮必需单元 | 45 | 三轮都是 45/45，缺失数都是 0 |
| retained 状态 | blocked / blocked / blocked | 3 个阻塞轮次，0 个合格轮次 |
| 特异性 | 95% / 95% / 95% | 数值稳定，不代表达到 A2 门槛 |
| 良性文本误报率 | 20% / 20% / 20% | 稳定地存在误报，越低越好 |
| 跨模态冲突识别 | 30% / 30% / 30% | 稳定但识别能力不足 |
| 视觉提示注入识别 | 60% / 60% / 60% | 稳定但仍有明显漏检 |
| 真人 review collection | pending | 真实回执 0 条，不能伪造 disposition |
| review conservation | verified | 队列 1、pending 1、reviewed 0，数量守恒 |
| shared candidate | false | 仍有 7 个候选版本绑定 blocker |
| release authority | false | 不能修改 score、pass/fail 或发布决定 |

四项指标三轮完全相同，因此 `stable_observation=true`。三轮 retained 状态都不是 `qualified`，因此
`quality_qualified=false`。这两个布尔值必须同时展示，避免把“问题稳定可复现”误解成“模型正确”。

## 原子 intake 与严格验证

新增公开安全 intake：

- `a3.a2_multimodal_repeat_stability_intake.v1`
- `a2.multimodal_multi_repeat_comparison.v1`
- `a2.multimodal_real_review_collection.v1`
- `a2.multimodal_review_conservation.v1`
- shared-candidate verification object

验证器执行以下 fail-closed 检查：

1. 每一层对象使用精确字段 allowlist，未知字段直接拒绝；
2. repeat count、calibration hash、状态数组和每轮计数必须长度一致；
3. 45 个必需单元、eligible count、missing count 和 completeness 必须守恒；
4. success count、eligible count、estimate 和 bootstrap interval 必须自洽；
5. review queue、pending、reviewed 与 latest receipt hash 数量必须守恒；
6. Provider、模型、region、manifest、policy、prompt、schema 和 case plan 绑定必须完整；
7. release authority、provider-is-truth、raw payload flags 必须保持 false；
8. secret、token、cookie、email、URL、signed URL、DSN 和本地账号路径会被拒绝。

A2 当前只发布了空真人回执集合，没有发布 A3 可安全消费的精确非空 receipt 对象 schema。因此任何
非空 `receipts` 会失败关闭，而不是由 A3 猜字段或创造真人结论。

## A3 投影

有效 Round 51 envelope 生成 `a3.multimodal_repeat_stability.v1`：

- `status=blocked_stable_repeat`
- `available=true`
- `integrity.status=passed`
- `repeat_count=3`
- `retained_blocked_count=3`
- `retained_qualified_count=0`
- `all_required_units_complete=true`
- `stable_observation=true`
- `quality_qualified=false`
- `human_review.receipt_count=0`
- `candidate_binding.verified=false`
- `release_authority=false`
- `a2_decision_recomputed=false`
- `production_ready=false`

完整性通过只证明 A3 收到的数据包内部自洽，不证明 Provider 正确、真人已经审核或候选版本已经绑定。

## Store、API 与租户边界

新增 source：`p3-a2-round51`。

新增受保护接口：

```text
POST /api/a3/import/a2-multimodal-repeat-stability
GET  /api/a3/review/multimodal-repeat-stability
```

- import 要求服务端验证的 principal、`project:ingest`、五级 scope 和 header-only `Idempotency-Key`；
- read 要求服务端验证的 principal、`release:review` 和五级 scope；
- import 记录 metadata-only audit、Event Outbox 和 usage meter；
- 跨租户读取返回脱敏 404；
- Memory、JSON-file 和 SQLite 均可保存并在重启后恢复该投影；
- SQLite 继续使用受控 Dashboard snapshot，不新增一套绕过现有存储边界的平行数据库。

OpenAPI runtime parity 从 `65/65` 增加到 `67/67`，商业 API contract 从 44 个端点增加到 46 个端点，
API Reference 升级到 v14。

## Dashboard 与报告

Review 页面新增中文优先的“多轮校准 / 稳定性证据”区：

- 3 个重复轮次、每轮 45 个必需样本、3 个阻塞轮次、0 个真人结论；
- 四项指标的三轮并排数值；
- “完整且稳定，但质量未达标”的主结论；
- 真人复核 pending、候选版本未绑定和无发布权提示；
- A2 blocker 原因码，但不暴露 Provider 原始响应、身份或媒体 URL。

同一安全投影已接入 Dashboard snapshot、JSON、Markdown 和 Hosted Report。对外报告只保留聚合指标、
状态、计数、哈希和原因码，不导出原始 Provider payload、真人身份、URL、signed URL 或私有媒体。

## 视觉证据

- `docs/screenshots/a3-webapp-repeat-stability-round51-desktop.png`
- `docs/screenshots/a3-webapp-repeat-stability-round51-mobile-390x844.png`

两张截图均已人工检查。桌面和手机标题正常换行，指标卡没有重叠，390 x 844 页面没有 document-level
横向溢出；产品区域没有面向客户显示 A1/A2/A3 内部分组标签。

## 验证结果

- A3 Node: `505` passed, `0` failed, `1` target-PostgreSQL opt-in skip；
- current-main A2: `186` passed plus `1050` subtests；
- Next.js TypeScript: passed；
- Next.js production build: passed, `15` static pages；
- Playwright: `45/45` passed with one worker；
- OpenAPI runtime parity: `67/67`；
- CL hygiene: `0` findings；
- Commercial CL: `0` blockers, `0` advisories；
- root/Webapp production dependency audit: `0` vulnerabilities；
- GitHub Actions feature commit `456a193`: CL Gate run `29329313569` passed every applicable check；
  TypeScript SDK、Go SDK 和 Rust verifier 依照 path plan 跳过，不是失败；
- `.env.local`: ignored and absent from Git status。

## 仍未完成

- A2 尚未提供真实非空 human-review receipt 和最终 disposition；
- 三轮指标虽然稳定，但 A2 质量门槛仍未达到；
- A1 evidence、A2 Decision Ledger 与 A3 artifact 尚未绑定到同一个最新 candidate；
- A1 peer 身份强化尚未合并 main，也没有 hosted identity / SSO 生产回执；
- target PostgreSQL、object storage、KMS 与 VPC 部署回执仍缺失；
- tenant-bound GitHub App required check、真实 merge denial、生产升级与回滚仍缺失。

因此事实状态不变：Golden Path `7/11`，Deployment Acceptance `8/17`，当前 authority
`integrity_invalid`，当前 A2 decision `unknown`，历史 A2 decision `block`，production receipts
`0`，`production_ready=false`。
