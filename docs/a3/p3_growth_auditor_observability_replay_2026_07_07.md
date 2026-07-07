# A3 Growth Auditor - Observability / Production Replay Matrix - 2026-07-07

## 审计边界

角色：A3 Growth-Auditor / Money-Grade Auditor。

本轮主题：A3 Observability / Production Replay Matrix。目标是把 A1 trace/tool-call、A2 judge failure、official Observability code crawl、media evidence、review workflow 打包成能卖钱的生产事故复盘和上线阻断能力。

执行边界：

- 只审计本地仓库证据。
- 未读取 `.env.local`。
- 未调用真实 Ashr、GitHub 或其他外部 API。
- 未打印、保存或生成 API key、token、cookie、header、邮箱、账号值、原始 signed URL 或 secret。
- 未修改代码、fixture、截图、测试、worklog 或既有文档。
- 只新增本文档：`docs/a3/p3_growth_auditor_observability_replay_2026_07_07.md`。

## 核心判断

A3 下一轮最能卖钱的方向不是“再做一个 Observability 页面”，而是把 Observability 变成生产复盘和上线阻断矩阵：

> Production Replay Matrix = 每个高风险 agent 失败，都必须同时回答：发生了什么 trace/tool-call 事实，A2 怎么判失败，官方 Observability 产品逻辑如何映射，媒体/VM 证据是否安全，谁负责复盘，是否阻断上线，审计包能否事后验证。

这条线比单独的 Incident Replay Queue 更接近大钱，因为它把“复现一个 case”升级成“生产事故复盘控制面”：

| 维度 | 当前 A3 能力 | Matrix 化后的商业能力 |
|---|---:|---:|
| 上线阻断 | Release Gate / PR Gate 能 block | block 原因可追到 trace、tool-call、judge、media、review owner |
| 事故复盘 | Incident Replay Queue 有 top-risk cases | 每个 incident 有时间线、证据、复现状态、RCA lane、审计 hash |
| 官方可信度 | code crawl parity 有 Observability 信号 | official Observability 逻辑成为 A3 replay/trace 产品路线依据 |
| enterprise | 有 waiver/approval/audit bundle/verifier | 可卖成 release governance + incident RCA + retained evidence |
| self-host | A1 本地 queue/replay、A3 verifier 有基础 | 可承诺 offline replay matrix 和 bundle verification |
| 客单价 | dashboard/report 工具 | 进入 release control、compliance、postmortem、audit budget |

一句话卖点：

> A3 不只是告诉你 agent eval 失败了。A3 把失败变成可复现、可指派、可阻断上线、可审计留存的 production replay matrix。

## 新增可卖能力

| 可卖能力 | 买家得到什么 | 现有证据锚点 |
|---|---|---|
| Production Replay Matrix | 高风险失败按 case/run/release/environment 进入矩阵，显示 trace、tool-call、judge、media、review、gate 状态。 | `a3.incident_replay_queue.v1`、`a3.release_war_room.v1`、`a3.reviewer_workflow_board.v1` |
| Trace-backed RCA | 每个失败能追到 A1 trace events、observations、final response、status history。 | A1 README、`docs/a1/schemas/trace_event.schema.json`、A3 trace timeline |
| Tool-call forensic diff | 缺失工具、错误工具、参数错误、顺序错误都有 expected-vs-actual diff 和 A2 judge evidence。 | `docs/a3/p3_tool_call_diff.md`、`tool_call_diffs`、dashboard diff panel |
| Judge failure binding | A2 score、failure class、judge mode、coverage、regression replay 进入 replay decision。 | A2 README、`fixtures/a2/results/a2_g3_grade_results.json`、A3 judge drilldown |
| Official Observability parity lane | 官方 code crawl 已确认 `ObservabilityPage`、trace、latency、errors、tool_calls、audio/voice 等信号，A3 可合法映射到自有 replay 产品。 | `fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json` |
| Media-safe incident evidence | media action、output_path、audio tags、VM stream、signed_url metadata 进入复盘，但 live signed URL 继续 fail-closed。 | `docs/a3/p3_media_calibration.md`、`docs/a3/p3_signed_media_url_coverage.md` |
| Review workflow ownership | 失败不只是列表，而是进入 reviewer lane、missing artifact、waiver state、approval readiness。 | `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md` |
| Release War Room decision packet | 管理层看到 no-go、revenue risk、merge block、waiver required、top replay cases、audit artifacts。 | `docs/a3/p3_release_war_room_growth_2026_07_07.md` |
| Audit bundle replay evidence | 复盘矩阵、replay result、review disposition、artifact hash 进入 bundle index 和 verifier。 | `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`、`docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md` |
| Self-host offline RCA | 本地 queue/replay/export 和 verifier 支持不依赖 hosted API 的 regulated pilot。 | A1 local queue/replay/export commands、A3 `--verify-index` |

买家能听懂的升级文案：

> Before a risky agent release ships, A3 builds a production replay matrix: the trace, the tool-call diff, the judge failure, the media evidence, the reviewer owner, and the audit bundle all point to the same incident.

## 玩具风险

当前 A3 很接近付费 pilot，但 Production Replay Matrix 还不能过度宣称。主要玩具风险如下：

| 风险 | 现在像玩具的地方 | Money-grade 要求 |
|---|---|---|
| Matrix 还不是一等 schema | 已有 incident queue、war room、reviewer board，但不是统一 `a3.production_replay_matrix.v1`。 | 定义矩阵 schema，绑定 release/run/case/trace/judge/media/review/gate/audit。 |
| Observability 仍是 partial | 官方 account feature flag 曾显示 observability disabled；A3 主要用 run observations/action_results 派生 timeline。 | 明确区分 `local_trace_available`、`official_observability_blocked`、`production_trace_enabled`。 |
| Trace 没有生产级查询 | dashboard 能显示 trace timeline，但没有 trace id 搜索、latency/error 聚合、span hierarchy。 | 增加 trace/span/error/latency/search/filter fields，不要只靠 case detail。 |
| Tool-call diff 还偏 eval | diff 很强，但还缺生产 incident 语境：environment、deploy version、head SHA、customer impact。 | 每个 diff row 绑定 release context、impact、policy failure、owner。 |
| Judge evidence 没有 dispute workflow | A2 有 case book/regression replay seed，但 A3 还没有 judge disagreement review lane。 | Matrix 增加 `judge_disposition`: accepted、disputed、needs calibration、regression seed。 |
| Media 只能 metadata-only | 这是安全正确的，但 demo 时容易被质疑“看不到证据”。 | 加 redacted preview policy、expiry proof、safe thumbnail/proxy roadmap；继续禁止 raw signed URL。 |
| Review board 不持久 | 当前是 report/dashboard 派生对象，不是 durable workflow backend。 | owner、state transition、history、SLA、RBAC、SSO、storage contract。 |
| Gate 和 replay 未硬绑定 | Release Gate 能 block，Incident Replay 能列 case，但 matrix freshness 不一定控制 gate。 | 高风险 unreplayed/stale/missing evidence 必须影响 gate conclusion。 |
| Audit bundle 还缺 matrix artifact | bundle/verifier 已有，但 replay matrix 不是必选 artifact。 | bundle index 必须收录 matrix JSON、replay result、review disposition、trace/judge hash。 |
| Official crawl 还偏 keyword summary | code crawl 是 clean-room keyword/count summary，不是 route/API/state parity diff。 | 增加 official observability parity spec：route、state、API group、A3 decision、evidence hash。 |
| Enterprise 身份缺口 | waiver/approval 有文件校验，但没有真实 SSO/RBAC identity。 | 区分 file-backed validation 与 enterprise identity roadmap。 |
| 真实集成缺口 | GitHub check/PR comment 是 dry-run，Jira/Slack/PagerDuty 还没有。 | 先做 dry-run payload，再做 live integration；不要宣称 live enforcement。 |

最大玩具风险：

> A3 看起来有很多漂亮面板，但没有一个机器可验证的 `trace -> judge -> replay -> review -> gate -> audit` 链路。

下一轮必须把它变成一个稳定产品对象，而不是更多 UI 文案。

## 提高客单价

Production Replay Matrix 能提高 ACV 的原因是它进入了三个更贵的预算池：release governance、incident RCA、compliance retention。

| 包装 | 为什么能涨价 |
|---|---|
| Enterprise Release Governance | Matrix 状态可以阻断 merge/release，进入平台工程和变更管理预算。 |
| Production Incident RCA Pack | 失败从 eval report 变成事故复盘证据：timeline、tool-call、judge、owner、fix verification。 |
| Audit Bundle Pro | Matrix artifact hash、custody events、verifier result 能用于审计和客户问责。 |
| Self-host Compliance Edition | 本地 replay、离线 verifier、retention/legal hold 是 regulated buyer 的付费点。 |
| Reviewer Workflow Seats | release owner、safety reviewer、judge reviewer、audit reviewer、executive approver 可按 seat/role 定价。 |
| PR Required Check Add-on | 一旦进入 required check，就不再是 dashboard，而是上线控制。 |
| Replay Usage Metering | 按 replay case、trace bytes、stored evidence、verifier run、retention day 收费。 |
| Official Observability Parity Report | 用 official code crawl 映射证明 A3 不是随便做 UI，适合采购/管理层评估。 |
| Media Evidence Governance | 多模态 agent 的证据安全、signed URL redaction、VM stream retention 可单独高价。 |
| Incident Recurrence Analytics | 跨 release 检测 repeated failure/new failure/fixed/regressed，适合安全质量团队。 |

建议商业分层：

- Team：本地 dashboard、JSON/Markdown/CSV export、trace/tool-call diff、A2 judge drilldown。
- Pro：Release Gate、Incident Replay Queue、Reviewer Workflow Board、Release War Room、PR comment/check dry-run。
- Enterprise：Production Replay Matrix、required checks、audit bundle verifier、self-host storage、RBAC/SSO binding、retention/legal hold、offline verification。

## 降低上线风险

Production Replay Matrix 的上线价值是把“是否能上线”从主观讨论变成证据状态机。

| 上线风险 | Matrix 控制点 |
|---|---|
| 高风险失败未复现就放行 | production/high severity item 必须 `replayed` 或有 exceptional waiver。 |
| 工程师无法复现 | 附 A1 trace events、observations、tool calls、final response、status history、replay command。 |
| 工具调用回归被忽略 | tool-call diff 必须显示 missing/wrong/extra/reordered/wrong_arguments。 |
| judge 失败被当成 UI noise | A2 score、failure class、judge mode、coverage、regression replay status 必须进入 gate risk。 |
| 官方 Observability 方向走偏 | official code crawl 的 Observability signals 映射到 A3 trace/latency/error/replay backlog。 |
| 媒体证据泄漏 signed URL | media evidence 只保留 metadata/redacted value，live rendering blocked。 |
| waiver 绕过修复 | waiver 必须绑定 matrix item、release version、run id、artifact hash、expiry、required approver。 |
| 旧复盘证据批准新 release | stale check 绑定 head SHA、release version、dataset id、run id、policy version。 |
| reviewer 不知道自己缺什么 | review board 显示 missing artifact、owner lane、next action、approval readiness。 |
| 审计后无法证明 | audit bundle index/verifier 必须验证 matrix artifact、hash、custody chain。 |

上线阻断规则建议：

1. `critical/high` severity 且 `release_blocker=true` 的 matrix item 未 replay：block release。
2. A1 trace/tool-call evidence 缺失：block 或 require exceptional waiver。
3. A2 judge evidence 缺失但 case failed：mark `judge_unavailable`，不能显示 approval-ready。
4. media item 包含 raw signed URL：fail verification。
5. replay result release context stale：block release。
6. waiver/approval artifact hash 不匹配：block release。
7. official Observability parity status 为 blocked 时：不能宣称 production observability parity，只能宣称 local trace replay。

## Enterprise / Self-host / Audit / Compliance

### Enterprise

Enterprise 需要 Matrix 表达组织责任和发布策略：

- release owner、incident owner、reviewer lane、required approver；
- environment、release version、repo、PR、branch、head SHA；
- policy version、threshold version、waiver rule；
- severity、customer impact、revenue risk、merge block；
- SLA、due time、escalation state；
- separation-of-duties；
- review disposition history；
- required artifacts and missing artifacts；
- GitHub/Jira/Slack/PagerDuty dry-run payload；
- final decision：ship、block、waive、rollback、needs replay、needs calibration。

可以宣称：

> A3 has the local evidence model for enterprise production replay governance.

不要宣称：

> A3 already has durable enterprise incident management, SSO/RBAC, live required checks, and immutable storage.

### Self-host

Self-host 需要离线、可恢复、可验证：

- 从本地 A1/A2/A3 fixtures 生成 matrix；
- A1 queue state 可以 snapshot/reload/replay/export；
- 不依赖 hosted Ashr API；
- workspace-relative/bundle-relative paths；
- no raw user path、token、cookie、signed URL；
- SQLite/Postgres metadata contract；
- filesystem/S3-compatible artifact storage；
- backup/restore verification；
- retention days、legal hold、delete-after；
- offline `ashr gate verify --index` 扩展到 matrix artifact。

Self-host 的最佳卖法：

> Regulated teams can reproduce and audit risky agent releases inside their own environment without sending traces, media metadata, or release evidence to a hosted service.

### Audit

Audit 需要 Matrix 可 hash、可复核、可追责。最低字段：

- `schema_version: a3.production_replay_matrix.v1`
- matrix id、release id、environment、generated_at；
- source artifacts：A1 run fixture、A2 grade fixture、coverage、thresholds、official crawl summary；
- item id：release/run/case/failure-class stable id；
- A1：trace hash、tool-call hash、final-response hash、observation hash、status-history hash；
- A2：grade result id、score、passed、failure class、judge mode、coverage status、grade hash；
- official Observability：parity target、code-crawl evidence id、A3 decision；
- media：media type、output_path presence、signed_url redaction status、VM stream metadata；
- review：owner lane、review state、missing artifacts、waiver state、approval readiness；
- replay：command/ref、result status、result hash、staleness check；
- gate：release decision、risk score、merge block、waiver required；
- custody events and root hash；
- verifier result。

### Compliance

Compliance 需要 export hygiene 和 fail-closed 行为：

- DLP scan：no secrets、cookies、tokens、emails、raw signed URLs；
- media live rendering disabled until expiry/access/safe preview is proven；
- mutating official API/admin flows out of scope；
- billing/key/team/OAuth flows disabled in A3 MVP；
- approval/waiver expiry and revocation；
- separation-of-duties；
- retained evidence policy；
- generated reports must not include local absolute user paths；
- missing evidence must never render as approval-ready。

## 哪些不像真产品

这些缺口会让买家觉得还不是生产产品：

- 没有 `a3.production_replay_matrix.v1` schema。
- 没有 Matrix 作为 Gate CLI 的一等输出。
- 没有 Matrix artifact 纳入 audit bundle index 的 required artifact。
- 没有 verifier 对 Matrix 做 required-field、hash、stale、DLP、media leak 检查。
- 没有 release context stale check：head SHA、release version、policy version、run id。
- 没有 production trace search、span tree、latency/error aggregation。
- 没有 official Observability parity spec，只是 code crawl summary。
- 没有 live production observability traces；当前 account observability feature 曾是 disabled。
- 没有 durable reviewer state/history。
- 没有 SSO/RBAC identity。
- 没有 live GitHub required check。
- 没有 Jira/Slack/PagerDuty handoff。
- 没有 immutable archive/package verifier。
- 没有 self-host storage/retention backend。
- 没有 recurring incident detection across releases。
- 没有 judge disagreement/dispute workflow。
- 没有 matrix-level pricing/metering object。
- 没有 safe media preview/proxy strategy。
- 没有 customer-facing RCA report packet。
- 没有 management sign-off packet 把 War Room、Matrix、approval、bundle root 合成一个签字材料。

真实产品最低门槛：

> 每个高风险 release decision 都能追到同一个 Matrix item，并且这个 item 同时指向 A1 trace/tool-call evidence、A2 judge failure、official Observability parity decision、media safety status、review owner、gate decision 和 audit bundle hash。

## 下一轮至少 20 个增长点

| ID | 增长点 | 为什么重要 | 赛道 |
|---|---|---|---|
| PRM-01 | 定义 `a3.production_replay_matrix.v1`。 | 把 replay/observability 从面板变成产品对象。 | Schema |
| PRM-02 | 定义 stable matrix item id。 | 防止 incident 只靠 case id 文本漂移。 | Schema |
| PRM-03 | 生成 Matrix from Release Gate top-risk cases。 | 让上线阻断和复盘对象一致。 | Gate |
| PRM-04 | 绑定 A1 trace hash、observation hash、status-history hash。 | 复盘能证明 agent 实际发生了什么。 | A1 |
| PRM-05 | 绑定 A1 tool-call diff rows。 | 工具调用错误是 agent 上线风险核心。 | A1 |
| PRM-06 | 绑定 A1 final response hash。 | 复盘保留用户可见错误输出。 | A1 |
| PRM-07 | 绑定 A2 grade result id、score、failure class、judge mode。 | judge 失败进入 release decision。 | A2 |
| PRM-08 | 绑定 A2 coverage health 和 regression replay status。 | 防止低覆盖证据被过度解释。 | A2 |
| PRM-09 | 增加 judge dispute/disposition workflow。 | 支持企业评审 judge disagreement。 | Review |
| PRM-10 | 定义 official Observability parity spec。 | 把 code crawl 变成 trace/latency/error/replay 产品路线。 | Parity |
| PRM-11 | 区分 local trace、official run action_results、production observability trace。 | 避免误称已具备生产 Observability。 | Evidence |
| PRM-12 | 增加 trace/span/error/latency 字段。 | 更像生产事故复盘，而非 eval case viewer。 | Observability |
| PRM-13 | 增加 replay command / replay pack ref per item。 | 每行都能变成可执行复现工作。 | Replay |
| PRM-14 | 增加 replay result status/hash。 | 修复验证和审计留存需要结果 hash。 | Replay |
| PRM-15 | 增加 stale replay detection。 | 旧证据不能批准新 release。 | Risk |
| PRM-16 | 增加 recurrence detection across runs/releases。 | 区分新失败、重复失败、已修复、回归。 | RCA |
| PRM-17 | 增加 owner、SLA、escalation、review lane。 | 企业 workflow 需要责任人和时限。 | Workflow |
| PRM-18 | Matrix 状态影响 Release Gate conclusion。 | 未复盘高风险失败必须 block 或 waiver。 | Gate |
| PRM-19 | War Room 增加 Matrix health summary。 | 管理层看到 top blockers、stale items、owners。 | War Room |
| PRM-20 | Reviewer Workflow Board 消费 Matrix item。 | reviewer 不再看散落 evidence。 | Review |
| PRM-21 | PR comment/check dry-run 增加 Matrix summary。 | 进入工程合并流程。 | PR Gate |
| PRM-22 | Audit bundle index 收录 Matrix JSON 和 replay results。 | 形成可验证证据链。 | Audit |
| PRM-23 | Verifier 校验 Matrix hashes、required fields、stale status。 | 让 Matrix 可被审计。 | Verifier |
| PRM-24 | DLP test：禁止 raw signed URL、token、cookie、email、absolute user path。 | enterprise/compliance 必需。 | Compliance |
| PRM-25 | Media-safe preview policy。 | 为未来多模态证据展示铺路。 | Media |
| PRM-26 | self-host storage contract。 | regulated buyer 的采购门槛。 | Self-host |
| PRM-27 | retention/legal hold fields。 | 进入 compliance records 管理。 | Compliance |
| PRM-28 | immutable archive / zip verifier roadmap。 | 事后审计和客户问责需要。 | Audit |
| PRM-29 | Jira/Slack/PagerDuty dry-run handoff payload。 | 企业事故复盘协作入口。 | Integrations |
| PRM-30 | pricing meters：matrix items、replay runs、trace bytes、verifier runs、retention days、reviewer seats。 | 支持涨价和 usage-based packaging。 | Billing |
| PRM-31 | customer-facing RCA report packet。 | 销售和客户成功能拿去讲事故复盘价值。 | GTM |
| PRM-32 | management sign-off packet。 | 把 War Room、Matrix、approval、bundle root 变成签字材料。 | Executive |

## 并行推进建议

这些工作应该并行推进，不能先做完整 UI 再回头补 evidence contract。

| 并行线 | 第一交付物 | 必须并行对象 |
|---|---|---|
| Matrix schema | `a3.production_replay_matrix.v1` redacted fixture | A1/A2 binding、gate、audit |
| A1 binding | trace/tool-call/final-response/status-history hashes | replay command、verifier |
| A2 binding | grade/failure/judge/coverage/regression fields | reviewer workflow、gate risk |
| Official Observability parity | `a3.official_observability_parity.v1` | code crawl fixture、dashboard wording、safety claims |
| Gate integration | matrix-required/replayed/stale summary fields | waiver、approval、PR check |
| Review workflow | matrix item owner/disposition/missing artifact | War Room、audit bundle |
| War Room | matrix health and top blockers | gate、review、executive packet |
| Audit/verifier | matrix artifact hash and required field checks | bundle index、negative tests |
| Media safety | metadata-only matrix fields and DLP tests | dashboard、verifier、compliance |
| Self-host | local storage/retention contract | verifier、backup/restore、pricing |
| Integrations | Jira/Slack/PagerDuty dry-run payloads | reviewer workflow、incident RCA |
| GTM/pricing | packaging and meter draft | product schema、audit proof |

关键顺序：

1. 先定义 Matrix JSON contract。
2. 同时接 A1/A2 evidence、official Observability parity、media safety。
3. 再让 Release Gate、War Room、Reviewer Workflow、PR Gate 消费 Matrix。
4. 最后加 dashboard polish 和 customer-facing RCA report。

不要先做“好看的 Observability 页面”。买家要的是能阻断上线和复盘事故的证据链。

## 最接近大钱方向

最接近大钱的方向是：

> Enterprise Production Replay Governance = Production Replay Matrix + Release War Room + Required Gate + Verifiable Audit Bundle + Self-host Retention。

原因：

- A1 trace/tool-call 证明 agent 实际做了什么。
- A2 judge failure 证明为什么这是质量/安全失败。
- Official Observability crawl 证明 A3 的 trace/replay 方向不是自嗨 UI。
- Media evidence 让多模态 agent 的复盘有证据，但保持安全边界。
- Reviewer Workflow 让失败有 owner、state、missing artifact 和 approval readiness。
- Release Gate / PR Gate 把 Matrix 变成上线阻断。
- Audit Bundle / Verifier 把复盘变成事后可证明的 retained evidence。
- Self-host / retention / legal hold 让 regulated buyer 能采购。

最大钱不是单卖 Observability，也不是单卖 replay queue。最大钱是卖：

> A3 gives enterprises a verifiable control plane for risky agent releases: production replay, reviewer accountability, release blocking, exception approval, and offline audit evidence.

## 下一轮验收证据

下一轮至少应交付：

1. `a3.production_replay_matrix.v1` redacted fixture。
2. Matrix item 绑定 release version、environment、run id、dataset id、case id、scenario id。
3. Matrix item 绑定 A1 trace/tool-call/final-response/status-history evidence hashes。
4. Matrix item 绑定 A2 score、failure class、judge mode、coverage、regression replay status。
5. Matrix item 绑定 official Observability parity target 和 code-crawl evidence id。
6. Matrix item 绑定 media metadata/redaction status/VM stream metadata。
7. Matrix item 绑定 owner lane、review state、missing artifact、waiver state、approval readiness。
8. Matrix item 包含 replay command/ref、replay status、result hash、stale status。
9. Release Gate 输出 matrix-required、matrix-replayed、matrix-stale、matrix-blocking counts。
10. War Room 输出 Matrix health、top blockers、owners、next action。
11. Reviewer Workflow Board 从 Matrix item 派生 reviewer items。
12. PR comment/check dry-run 输出 Matrix summary。
13. Audit bundle index 收录 Matrix JSON 和 replay result artifact。
14. Verifier 校验 Matrix artifact hash、required evidence、stale status。
15. Negative tests 覆盖 missing trace、missing judge、stale replay、raw signed URL leak、hash mismatch。
16. Dashboard 只消费 Matrix JSON，不硬编码 Matrix 文案。
17. Markdown/print report 包含 Production Replay Matrix section。
18. DLP result 显示 no secrets/cookies/tokens/raw signed URLs/absolute user paths。
19. Self-host storage/retention/legal hold draft。
20. Pricing/metering draft。

## 最终审计结论

A3 已经具备 Production Replay Matrix 的核心材料：A1 trace/tool-call/replay、A2 judge failure、tool-call diff、media evidence、official code crawl Observability signals、Incident Replay Queue、Reviewer Workflow Board、Release War Room、PR Gate、audit bundle index 和 verifier。

下一轮不要继续把这些材料散落成更多 panel。最值钱的动作是定义一个统一、可验证、可阻断上线的 Matrix contract，然后让 Gate、War Room、Review、Audit、Dashboard 都消费它。

克制可宣称：

> A3 can turn risky agent-release failures into a local, evidence-backed production replay matrix for release review and audit.

暂时不要宣称：

> A3 has live production observability, durable enterprise incident management, SSO/RBAC, real required checks, safe live media rendering, or immutable self-host retention.

## 改了什么

- 新增本文档：`docs/a3/p3_growth_auditor_observability_replay_2026_07_07.md`。
- 没有修改任何代码、fixture、截图、测试、既有文档或环境文件。

## 跑了什么

本轮只运行本地只读审计命令和目标文件存在性检查，未运行真实 API，未运行 mutating command：

- `Get-ChildItem -LiteralPath .`
- `rg --files -g '!*.env*' -g '!node_modules' -g '!dist' -g '!build'`
- `git status --short`
- `Test-Path -LiteralPath docs\a3\p3_growth_auditor_observability_replay_2026_07_07.md`
- `Get-Content` 读取 A1/A2/A3 相关公开文档和 redacted fixtures
- `rg -n "observability|trace|tool-call|tool call|incident_replay|release_war_room|reviewer_workflow|media_evidence" services apps tests docs/a3 -g '!*.env*'`

未运行测试，因为本轮是文档审计，且不改代码路径。

## 证据在哪

核心证据：

- `docs/a1/README.md`
- `docs/a2/README.md`
- `docs/a3/p3_tool_call_diff.md`
- `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`
- `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md`
- `docs/a3/p3_release_war_room_growth_2026_07_07.md`
- `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`
- `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`
- `docs/a3/p3_media_calibration.md`
- `docs/a3/p3_signed_media_url_coverage.md`
- `docs/a3/p3_field_mapping.md`
- `docs/a3/acceptance_checklist.md`

Redacted fixture 证据：

- `fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json`
- `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`
- `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`
- `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`

代码/测试证据：

- `services/report/report_builder.mjs`
- `services/report/a3_gate_cli.mjs`
- `services/report/p3_ashr_mapper.mjs`
- `apps/dashboard/index.html`
- `tests/a3/report_builder.test.mjs`
- `tests/a3/dashboard_wiring.test.mjs`
- `tests/a3/a3_gate_cli.test.mjs`
- `tests/a3/p3_ashr_mapper.test.mjs`

截图证据：

- `docs/screenshots/a3-dashboard-incident-replay-queue.png`
- `docs/screenshots/a3-dashboard-reviewer-workflow-board.png`
- `docs/screenshots/a3-dashboard-release-war-room.png`
- `docs/screenshots/a3-dashboard-official-code-crawl-parity.png`
- `docs/screenshots/a3-p3-tool-call-diff.png`
- `docs/screenshots/a3-dashboard-media-evidence-queue.png`
