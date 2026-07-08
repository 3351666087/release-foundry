# A2 Growth Audit 2026-07-07

角色：Growth-Auditor / Money-Grade Auditor
服务对象：Kay / A2
范围：只评估 A2 是否更接近大型 SaaS / enterprise release intelligence 产品，不读取 secret，不提交 private evidence。

## 0. 本轮判断

A2 已经不是简单复现 demo。当前系统已经具备 deterministic judges、60 个 scenario、golden cases、failure taxonomy、SDK parity、scenario selection、release gate、result persistence、SaaS control plane summary 等基础能力。

但它离“能卖给企业做上线阻断”的产品仍差三类关键证据：

- C3：reviewed Ashr grading observations 仍未公开安全汇入主校准矩阵。
- C4：semantic judge 仍以 offline reference 为主，缺少 audited live observations。
- C5：regression replay / case book 仍偏 seed maturity，缺少足够 reviewed incident/disagreement 回归案例。

商业结论：A2 的架构已经有平台雏形，短板不在“有没有代码”，而在“证据是否能支撑企业级 release gate 签字”。

## 1. 已有可卖能力

### 1.1 Deterministic Judge Core

`services/judge/runner.py` 能把 A1/Ashr 风格的 run shape 规整为 A2 内部结构，并用五类 judge 评分：

- tool policy judge
- output contract judge
- trace integrity judge
- grounding judge
- safety boundary judge

这可以卖给两类早期客户：

- 需要 CI / PR gate 的 agent 团队。
- 需要在生产上线前阻断危险 agent 行为的工程负责人。

### 1.2 Scenario Coverage And Case Book Base

当前 A2 已满足组长硬性要求：

- 60 scenarios
- 5 rubric classes
- 5 judges
- 20+ golden cases
- 12 failure classes

这说明 A2 覆盖面不是几条 smoke tests，而是一个可以审计的 scenario pack。尤其是 tool use、workflow、trace、safety、grounding、media/tool-output grounding 都已有入口。

### 1.3 Python + TypeScript SDK Parity

`a2_sdk_parity_report` 已覆盖 Python 和 TypeScript 两条链路。这个点很关键，因为 Ashr 官方文档也明确有 Python SDK 和 TypeScript SDK。A2 不能退化成 Python-only 评测，否则无法支撑大型 SaaS 客户的真实接入形态。

### 1.4 Service Boundary

`services/judge/service_wrapper.py` 已有内部 service wrapper 合同：

- `/internal/judge/case`
- `/internal/judge/run`
- `/internal/judge/batch`
- `/internal/release-policy/evaluate`
- `/internal/regression/replay`
- `/internal/calibration/evaluate`
- `/internal/scenarios/select`
- `/internal/results/persist`

它还不是 hosted backend，但已经形成 A1 可调用、A3 可消费的服务边界。

### 1.5 Release Gate

`a2_release_gate_report` 能明确输出 block / warn / pass、exit code、risk score、blockers、warnings、required evidence、A3 consumption contract。能真的 block 才是企业 release gate 的核心价值。

### 1.6 Public-Safe Result Persistence

`a2_result_persistence_manifest` 已能记录 public-safe audit records、hash、policy trace 和 judge version 信息，并避免 raw private evidence / secrets 进入公开产物。这是 enterprise audit bundle 的底座。

### 1.7 Per-Project Scenario Selection

`a2_scenario_selection_report` 已能针对 enterprise SaaS prod profile 选出高风险 scenario pack，包含 tenant、project、environment、policy profile、minimums、A3 consumption summary。这是从“通用测试集”走向“每个客户项目不同 release policy”的关键。

## 2. 仍像玩具的部分

### 2.1 Semantic Harness 还不是 live evidence backed

当前 semantic harness 的主要价值是离线参考。下一步必须把 audited live observations 通过 public-safe bridge 汇入，而不是继续堆 prompt 变体。

### 2.2 Ashr Grading 仍未 reviewed merge

A2 已有 collection / scanner / import / merge 的架构，但 C3 不能因为架构存在就标记完成。必须有 6-case reviewed Ashr grading rows，并确认 private evidence 不泄漏后才可公开汇入。

### 2.3 Case Book 成熟度不足

case book 目前更像 seed。企业客户更关心“生产事故或 judge disagreement 能不能变成长期 regression”。下一步应把至少 2 个 incident/disagreement candidate 提升为 replayable regression case。

### 2.4 Policy Template 不够像客户套餐

当前 policy profile 可用，但还需要更像 SaaS 产品的模板：

- startup CI basic
- regulated SaaS prod
- enterprise audit strict

每个模板应该明确 blocker、waiver、reviewer、evidence retention、A3 dashboard copy。

## 3. 对付费最有影响的方向

| 能力 | 付费意愿 | 客单价 | 上线风险降低 | Enterprise audit |
|---|---|---|---|---|
| Release gate block/warn/pass | 高 | 高 | 极高 | 高 |
| Public-safe audit manifest | 中 | 高 | 中 | 极高 |
| SDK parity Python + TypeScript | 高 | 中 | 中 | 中 |
| Per-project scenario selection | 高 | 高 | 高 | 高 |
| Reviewed Ashr grading evidence | 高 | 高 | 高 | 极高 |
| Audited semantic judge evidence | 高 | 高 | 高 | 极高 |
| Mature regression replay | 高 | 高 | 极高 | 高 |
| Waiver / approval policy | 高 | 高 | 高 | 极高 |
| Judge versioning / policy hash | 中 | 高 | 中 | 极高 |

最近的大钱方向是：

**Enterprise Agent Release Gate + Audit Evidence Bundle**

原因：

1. 客户不是为 benchmark 付钱，而是为“高风险 agent 不上线、上线后可追责、审计能过”付钱。
2. A2 已有 release gate、scenario selection、judge、persistence、policy hash 的基础。
3. 当前缺口明确：C3 reviewed grading、C4 audited semantic evidence、C5 mature regression replay。
4. A1 可以提供真实 API/runtime evidence，A3 可以提供 dashboard/report/reviewer workflow。

## 4. 下一轮至少 20 个增长点

1. 完成 6-case reviewed Ashr grading collection，并公开安全汇入 C3。
2. 完成 6-case audited semantic judge observations，并将 C4 从 offline reference 推到 evidence-backed。
3. 将 case book 从 1 个 seed 扩到至少 3 个 reviewed regression cases。
4. 生成 enterprise audit bundle manifest。
5. 给 release gate 增加 A1 output policy evidence blocker。
6. 增加 3 套 release policy template：CI basic、SaaS prod、enterprise strict。
7. 增加 waiver policy fixture：approved、expired、missing approval、invalid approver。
8. 增加 public-safe API key safety scenario。
9. 增加 usage/quota stop scenario，禁止 quota blocked 后继续 mutating paid calls。
10. 增加 HTTP 200 + `status:error` 的 API body-status scenario。
11. 增加 request_input_schema docs/runtime divergence scenario。
12. 增加 dashboard shell vs populated run detail 的 grounding scenario。
13. 增加 dataset wizard planning scenario，对应 Basic Info / Agent / Inputs / Tools / Context / Test Config / Behaviors / Review。
14. 增加 observability feature-gated scenario。
15. 增加 VM stream explicit evidence scenario。
16. 给 failure taxonomy 增加 business impact、waiver eligibility、owner role。
17. 给 result persistence 增加 JSONL export / checksum manifest。
18. 给 A3 增加 release gate card payload fixture。
19. 增加 project baseline comparison：current run vs last passing run。
20. 增加 calibration cost ledger 聚合字段，记录 provider/model/case/source 成本。
21. 增加 tenant/project policy hash history。
22. 增加 human reviewer adjudication schema。
23. 增加 incident -> regression promotion workflow。
24. 增加 release unblock checklist，明确 C3/C4/C5 owner 和命令。
25. 增加 official frontend surface tags：usage-quota、api-key-admin、team-admin、trust-compliance、dataset-wizard、dashboard-analytics。

## 5. 并行推进建议

### 5.1 C3 / C4 / C5 并行

这三项共同决定 A2 是否能从 C2 推向更可信的商业 release gate：

- C3：reviewed Ashr grading observations
- C4：audited semantic judge observations
- C5：reviewed regression replay maturity

### 5.2 Service Contract / A3 Payload 并行

A2 应继续稳定 service wrapper 和 JSON schema；A3 应同步消费 release gate、scenario selection、audit record count、policy profile、evidence gaps。

### 5.3 Policy Template / Waiver Workflow 并行

release gate 只会 block 还不够，企业需要 reviewer workflow 和 waiver policy。A2 应输出可审计的 waiver 状态，而不是只输出 failure list。

### 5.4 Official Frontend Mapping 并行

前端镜像里的 API Keys、Team、Trust、Usage、CreateRequestModal、RequestDetailDrawer 可用于补 A2 的 SaaS 场景词汇和 evidence requirements。不要把前端源码直接提交；应把它转成 public-safe mapping、scenario tags 和 judge policy。

## 6. 本轮结论

A2 当前商业成熟度：强原型，C2 已实，C3-C5 卡在 reviewed evidence，不是卡在基础架构。

下一步不应继续横向堆大量静态 scenario，而应把现有能力升级为：

```text
C3 reviewed Ashr grading
+ C4 audited semantic judge
+ C5 mature regression replay
+ enterprise strict release policy
+ public-safe audit bundle
= enterprise-grade agent release gate
```

这条路线最符合大型 SaaS / enterprise 产品方向，也最能服务 A1 和 A3 的协同。
