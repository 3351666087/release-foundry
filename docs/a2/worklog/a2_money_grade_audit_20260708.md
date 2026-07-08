# A2 Money-Grade Audit 2026-07-08

角色：A2 Growth-Auditor / Money-Grade Auditor
范围：public-safe 商业审计；不读取 secrets，不读取 `docs/evidence/private_refs/`，不修改 A2 主逻辑，不触碰 A3 generated fixtures。
依据：当前 `dev/g3-a2-calibration` worktree、GitHub main 分支 `docs/strategy/large-saas-a1-a2-a3-full-plan.md`、A2 public fixtures/schemas/tests/docs。

## 0. 本轮状态核对

- 本地分支：`dev/g3-a2-calibration`
- 本地 HEAD：`508cde400a860a14f75957f36b206a2d6c005263`
- 远端 A2 分支：`508cde400a860a14f75957f36b206a2d6c005263`
- GitHub main：`3738f70b325d485e428b92096491afdcf015bcd9`
- `git fetch origin --prune`：失败，原因是 GitHub HTTPS connection reset；已用 `gh api` 校验 main、A2 分支、PR 和 strategy 文件。
- 当前 open PR：
  - #18 `[codex] Add A3 GitHub evidence and audit archive sealing`
  - #17 `[codex] Add A3 GitHub publish evidence exports`
- 远端分支：`main`、`dev/g3-a2-calibration`、`dev/a2-scenario-judge`、`codex/a1-local-sdk-runner`、多个 A3 分支。

结论：A2 分支与远端同步，但本地 `origin/main` 不是最新；本轮商业审计以 GitHub main 上的 strategy 文件为准。

## 1. Strategy 对 A2 的商业裁决

main strategy 把 Ashr 定义为 `Agent Release OS`：发布门禁、评测平台、证据系统、审计系统和团队协作后台。A2 的定位不是单纯 judge owner，而是：

```text
Evaluation Intelligence / Policy / Calibration / Regression / Security Verification owner
```

结合用户最新边界，本轮对 A2 的裁决是：

- A2 不需要补大量 SQL、TypeScript runtime、hosted infra 或完整 dev environment。
- A2 应继续深挖 Python judge/eval/calibration/regression/policy。
- JSON Schema、OpenAPI、public-safe artifact contract 是 A2 应该做的边界。
- A1 owns hosted API/runtime/storage/DB/usage ledger。
- A3 owns dashboard/workflow/report/GitHub evidence UI。
- A2 必须输出稳定、可解释、可阻断、可审计、可版本化的 release evidence。

## 2. 当前最接近能卖钱的 A2 能力

### 2.1 Enterprise Release Gate

证据：`fixtures/a2/results/a2_release_gate_report.json`

当前 release gate 已经具备商业产品的核心形态：

- `decision: block`
- `exit_code: 2`
- `risk_score: 100`
- hard gates：C0-C5
- `blocking_gate_count: 3`
- `evidence_blocker_count: 4`
- A3 可消费 PR annotations
- reviewer workflow boundary
- private evidence boundary

商业意义：客户愿意为“阻断危险 agent 发布”付费，而不是为 benchmark 分数付费。A2 当前最像真产品的部分就是它敢 block，并能解释为什么 block。

### 2.2 Per-Project Scenario Selection

证据：`fixtures/a2/results/a2_scenario_selection_report.json`

当前 enterprise prod selection 已能选择 12 个项目相关 scenarios：

- `policy_id: release_policy_enterprise_prod`
- `judge_policy_id: judge_policy_a2_enterprise_prod`
- `environment: prod`
- selected scenario count：12
- selected failure classes：8
- selected media scenarios：2
- minimums ready：true

商业意义：这让 A2 从“通用测试包”变成“按客户项目/环境/风险选择评测包”。这是 SaaS 化和客单价提升的关键。

### 2.3 Public-Safe Result Persistence

证据：`fixtures/a2/results/a2_result_persistence_manifest.json`

当前 public-safe manifest 有 162 条 records：

- `judge_result: 160`
- `release_gate: 1`
- `scenario_selection: 1`

商业意义：企业买家需要可审计记录，不只需要一次性分数。A2 已有 public-safe audit record 底座，可以服务 enterprise audit bundle。

### 2.4 OpenAPI Internal Judge Service Contract

证据：`docs/a2/openapi/a2_judge_service.openapi.json`

当前 OpenAPI 覆盖 8 个 internal endpoints，包括 judge、batch、release policy、regression replay、calibration、scenario selection、result persistence。

商业意义：A2 不需要自己做 hosted server，但必须让 A1 能挂载、A3 能消费。这个 contract 是从本地 Python judge 走向平台服务的必要桥。

### 2.5 Evidence Readiness And Official API Shape Awareness

证据：

- `fixtures/a2/results/a2_evidence_readiness_report.json`
- `docs/a1/api_calibration/real_api_evidence_index.json`
- `docs/evidence/a2_real_api_smoke.json`

当前 public-safe evidence readiness 显示：

- external collection ready：true
- six calibration cases ready：true
- Ashr grading case map covers 6/6：true
- official SDK read-only smoke：6/6 ok
- A1 real API evidence total records：368
- real record count：241
- real read ok count：172
- quota block count：43
- create_request quota gate currently blocked：true

商业意义：A2 已经能引用真实 API 行为的 public-safe summary，但还没有把 reviewed server-side grading 合并成 C3 completion evidence。

### 2.6 Regression Replay Seed

证据：

- `fixtures/a2/results/a2_case_book.json`
- `fixtures/a2/results/a2_regression_replay_report.json`

当前 C5 状态：

- case book regression count：1
- replay case count：1
- replay ready：true
- maturity status：seed
- target replay cases：3
- missing replay cases：2
- reviewed external evidence：0/3

商业意义：production incident -> regression replay 是大钱方向，但当前还只是 seed，不能卖成 mature regression intelligence。

## 3. 新增或已形成的可卖能力

本轮审计确认 A2 已形成以下可卖能力雏形：

1. Release gate 可以 block PR/release，而不是只给报告。
2. Blocker 能拆到 C3/C4/C5 和 evidence gates，具备管理层签字前的解释力。
3. Enterprise prod 项目能自动选出 12 个高风险 scenarios。
4. Python/TypeScript SDK parity 已保留在证据链里，避免 Python-only 偏差。
5. Result persistence manifest 已能保存 public-safe judge/release/selection audit records。
6. OpenAPI internal contract 已能让 A1/A3 对接，而不要求 A2 承担 hosted backend。
7. Official API evidence index 已进入 A2 release gate 判断，但 raw private refs 没有进入 public artifact。
8. C5 replay 已可执行，具备把事故/分歧转成 regression asset 的骨架。

本轮新增的 public-safe 产物是本审计文件本身：它把 A2 可卖能力、风险和下一轮并行增长点固定成可审阅 worklog。

## 4. 仍有玩具风险的部分

### 4.1 C3 仍不是 reviewed official grading

当前 `ashr_grading` public rows：0/6。
风险：如果没有 reviewed Ashr grading，A2 的 release gate 会被认为是 local-only 规则系统，商业可信度不足。
升级方式：用 private evidence 跑 scanner/import/merge，公开只提交 reviewed summary。

### 4.2 C4 仍是 offline semantic reference

当前 semantic coverage 是 6/6，但 audited live evidence 是 0/6。
风险：客户会质疑 semantic judge 是否真的运行过、成本和置信度是否可追踪。
升级方式：导入 reviewed live model-call summaries，保留 provider/model/prompt hash/response hash/cost/confidence/review status。

### 4.3 C5 仍是 seed maturity

当前 case book 只有 1 个 replayable disagreement seed。
风险：它像“样例回放”，不像 production incident regression system。
升级方式：把至少 2 个 incident/disagreement candidates 晋升为 reviewed replay cases，达到 3 个 maturity target。

### 4.4 Policy 仍缺客户套餐感

当前已有 enterprise prod policy，但还不够像可销售的 plan 套餐。
风险：销售时难解释不同客户为什么买更高价。
升级方式：输出 `startup_ci_basic`、`team_prod`、`regulated_saas_strict`、`enterprise_audit_strict` 等策略模板。

### 4.5 Reviewer workflow 还不是完整闭环

当前 release gate 有 reviewer workflow boundary，但没有完整 human feedback queue。
风险：企业上线流程需要“谁批准、为什么批准、豁免多久、证据在哪”。
升级方式：把 waiver/approval/reviewer notes/adjudication 输出为 public-safe schema 和 result persistence record。

## 5. 客户为什么愿意付费

客户付费不是因为 A2 有很多 scenarios，而是因为 A2 可以进入真实发布流程：

1. 在 PR/release 前阻断高风险 agent。
2. 告诉团队是 C3/C4/C5 哪一类证据不足。
3. 把失败原因归到 canonical failure taxonomy。
4. 把线上事故转成 regression asset。
5. 保留 judge/policy/scenario/version/hash，支持事后追责。
6. 生成 A3 可展示、A1 可挂载的 public-safe artifacts。
7. 支持 enterprise prod profile，而不是所有客户同一套评测。
8. 不把 API key、raw prompt、account payload、private evidence 泄露到 public repo。

## 6. 如何提高客单价

最直接提高客单价的 A2 能力：

| 能力 | 客单价影响 | 原因 |
|---|---:|---|
| Enterprise strict release gate | 高 | 进入客户上线审批流，预算来自风险控制 |
| Reviewed official grading diff | 高 | 证明本地 judge 贴近真实产品行为 |
| Audited semantic judge with cost ledger | 高 | 支持复杂 agent 行为和 false-positive review |
| Production incident -> regression | 高 | 直接减少重复事故 |
| Public-safe evidence bundle feed | 高 | 服务审计、合规和管理层签字 |
| Per-project scenario selection | 中高 | 支持多项目、多环境、多团队售卖 |
| Policy templates by plan | 中高 | 形成 Free/Team/Pro/Enterprise 差异 |
| Judge version/policy hash history | 中高 | 支持企业变更管理和追责 |

## 7. 如何降低客户上线风险

当前 A2 已降低的风险：

- tool misuse：required/forbidden/wrong tool/wrong order
- hallucinated tool result：工具输出与最终回答不一致
- argument fidelity：工具参数错误
- safety/privacy：secret leak、unsafe response
- recovery：tool error 后恢复不当
- trace/evidence：缺失工具调用、忽略工具结果
- media grounding：A2-S031 覆盖 media/tool-output grounding

仍需补强的上线风险：

- official server-side grading mismatch
- live semantic judge false positive/false negative
- request lifecycle pending/failed/error 状态进入 release gate
- usage/quota blocked 后继续 mutating call
- reviewer waiver 过期或审批人不合法
- production incident 自动晋升 regression
- per-tenant policy drift

## 8. Enterprise / Self-Host / Audit / Compliance 支撑度

### 已有支撑

- public-safe evidence boundary：raw private evidence 不进入 public artifact。
- result persistence manifest：有 hash 和 record 概念。
- release gate：能 fail CI-style gate。
- OpenAPI：能被 A1 mount，被 A3 consume。
- local-lite check：可低资源本地验证。
- C3/C4 import/merge workflow：把 private reviewed evidence 转成 public summary。

### 不足

- 还没有完整 self-host bundle manifest。
- 还没有 tenant-level cost ledger。
- 还没有 reviewer adjudication schema。
- 还没有 waiver/approval expiry enforcement 的完整 public fixture。
- 还没有 production trace ingestion 到 regression promotion 的完整闭环。
- 还没有 signed bundle 或 immutable audit export；这主要会和 A1/A3 协同。

## 9. 哪些地方还不像真产品

1. C3/C4/C5 仍是 block 状态，说明最关键的外部证据链没闭合。
2. `create_request` quota gate blocked 后，mutating calibration 不能继续伪装成完整。
3. Regression replay 只有 1 个成熟前 seed，无法代表真实事故库。
4. Reviewer workflow 目前更像字段边界，还不像客户审批系统。
5. Cost ledger 有雏形，但未按 tenant/project/run 汇总。
6. Scenario selection 已像 SaaS，但还没有行业 pack/plan pack 的商业包装。
7. API calibration 与 judge calibration 仍分散在 A1/A2 public summaries，缺少统一 customer-facing evidence story。
8. A2 还没有把 official frontend empty/error/loading/usage/quota 文案系统化转成 policy cases。

## 10. 下一轮至少 20 个增长点

这些增长点应尽量并行推进，但必须保持 A2 边界：Python 深度、JSON Schema/OpenAPI/public artifact，不扩 SQL/TS hosted runtime。

| # | 增长点 | 产物类型 | 商业价值 |
|---:|---|---|---|
| 1 | 导入 6 条 reviewed Ashr grading observations | calibration fixture + tests | 让 C3 从 partial 走向可签字 |
| 2 | 导入 6 条 audited live semantic judge summaries | calibration fixture + tests | 让 C4 从 offline reference 走向 live evidence |
| 3 | 晋升 2 个 incident/disagreement 为 replay regression | case book + replay fixture | 让 C5 达到 mature target |
| 4 | 生成 C3/C4/C5 unblock checklist artifact | report/schema | 让客户知道如何解除 block |
| 5 | 增加 enterprise policy template set | config + policy tests | 支持更高价 plan |
| 6 | 增加 waiver expiry/invalid approver cases | fixtures + unit tests | 支持企业审批合规 |
| 7 | 增加 reviewer adjudication schema | JSON Schema + sample | 支持 human feedback loop |
| 8 | 增加 failure cluster report | Python report + fixture | 从 pass/fail 升级为 root-cause intelligence |
| 9 | 增加 calibration drift metrics | Python report + tests | 证明 judge 质量随时间可监控 |
| 10 | 增加 per-tenant/project cost ledger summary | fixture + schema | 支持 usage/billing 对接 |
| 11 | 增加 official API error shape policy cases | scenarios + fixtures | 减少真实 API 语义偏差 |
| 12 | 增加 quota-block release policy scenario | policy tests | 防止超额付费或失败发布 |
| 13 | 增加 request lifecycle pending/failed/error gate | policy tests + report | 更贴近真实 Ashr request 状态 |
| 14 | 扩展 media/tool-output grounding 到多个 scenarios | scenarios + run fixtures | 覆盖媒体方向商业场景 |
| 15 | 增加 API key safety scenario pack | scenarios + safety tests | 支持 enterprise security buyer |
| 16 | 增加 trust publishability policy | release policy fixture | 防止无证据发布 trust claim |
| 17 | 增加 scenario pack marketplace metadata | schema + fixture | 把 A2 变成可售 pack inventory |
| 18 | 增加 self-host local audit bundle summary | report + local-lite check | 服务 enterprise/self-host buyer |
| 19 | 增加 judge version comparison report | Python report + fixture | 支持变更追责 |
| 20 | 增加 production incident promotion command | script + tests | 把事故复盘产品化 |
| 21 | 增加 A3 dashboard contract summary for C3/C4/C5 | schema + public fixture | 帮 A3 做可销售 UI |
| 22 | 增加 A1 evidence index diff sanity check | tests + report | 防止真实 API evidence drift |
| 23 | 增加 redaction gate regression tests | tests | 防止 private evidence 泄露 |
| 24 | 增加 policy hash history in persistence manifest | fixture + tests | 支持 enterprise audit |
| 25 | 增加 PR annotation owner hints | release gate fixture + tests | 让 gate 更能进入工程流程 |

## 11. 必须并行推进项

下一轮最应该并行的不是随机 20 项，而是四条高杠杆主线：

1. Calibration lane：C3 reviewed Ashr grading + C4 live semantic summaries + drift metrics。
2. Regression lane：case book maturity + incident promotion + replay maturity。
3. Policy lane：enterprise templates + waiver/approval validity + quota/request lifecycle gates。
4. Evidence lane：public-safe persistence + redaction gates + self-host audit bundle summary。

这四条线互相补强：calibration 提升可信度，regression 降低复发风险，policy 进入上线流程，evidence 支持审计和销售。

## 12. 最接近大钱的方向

排序如下：

1. Enterprise PR / Release Gate
2. Production Incident -> Regression Replay
3. Enterprise Audit Evidence Bundle
4. Judge Calibration / Drift Intelligence
5. Review Workflow / Waiver Governance
6. Billing / Usage Cost Ledger
7. Self-Host Verification Bundle
8. API Platform Integration
9. Trace Ingestion
10. Report Center / Dashboard Consumption

本轮 Money-Grade 判断：A2 当前最接近大钱的方向是：

```text
Enterprise PR/Release Gate
+ Reviewed Official/Semantic Calibration
+ Mature Regression Replay
+ Public-Safe Audit Evidence
```

原因：

- 它能进入客户真实上线流程。
- 它能阻断高风险 release。
- 它能把事故变成长期 regression asset。
- 它能生成审计证据，让负责人敢签字。
- 它能自然带出 enterprise/self-host/compliance/billing 的高价合同。

## 13. Growth-Auditor 裁决

A2 当前不是玩具，但还不是商业终局。它处于“强原型 + 可销售骨架”阶段：

- C0-C2 已扎实。
- C3-C5 是当前最关键商业缺口。
- Release gate、scenario selection、persistence、OpenAPI 已经足够支撑 A1/A3 继续产品化。
- 下一轮不应继续横向堆静态 scenarios，而应把 reviewed evidence、live semantic judge、mature replay、policy workflow、audit persistence 打穿。

最终裁决：

```text
A2 的商业突破口不是更多本地测试。
A2 的商业突破口是让客户相信：
没有 reviewed grading、live semantic evidence、mature regression replay 和 public-safe audit evidence 的 agent release，不能上线。
```
