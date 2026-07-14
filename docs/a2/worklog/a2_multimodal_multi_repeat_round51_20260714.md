# A2 Round 51 — 多次真实校准、局部模型延迟归因与复核守恒

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`
A2 base: `bb3bcfe493954dff8eba2244915464e97023358a`

## 范围与上游审阅

本轮只修改 A2-owned 文件。最终门禁前审阅的上游引用为：

- main: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- A1 active branch: `6a985b80ffc9c5de6da70c3b7f23826017440503`
- A2 tracking branch: `bb3bcfe493954dff8eba2244915464e97023358a`
- A3 active branch: `7bd03bff160eeba8cd7fcae4ef816bd354b4ee29`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

A1 新增了真实 PostgreSQL identity security authority/lifecycle 证据，但其权威
release receipt 仍声明 `round62-source-candidate`，receipt SHA 仍绑定旧提交
`5dd6a898a6771eaf67bf39246f256b579b4d2211`，与当前 A1 ref 不一致。A3 已摄取
A2 Round 50 三 provider review evidence，且仍保持 `release_authority=false`，
没有重算 A2 决策；但 A3 继续使用 `a3-golden-20260712-002`。当前不存在统一的
A1/A2/A3 exact shared candidate identity，因此 Trusted Spine 必须 fail closed。

## Round 51 任务落实

1. 给 Qwen3-VL 增加 cold/warm、plain/schema、token-bound phase latency probe。
2. 真实执行一个 cold 和三个 warm Qwen3-VL profile。
3. 验证降低 `num_predict` 可减少 token generation，但不能替代结构化输出合规。
4. 验证 Ollama JSON-schema transport 可调用，但当前模型输出仍全部校验失败。
5. 用与 Qwen Round 50 完全相同的 15-case subset 真实运行 `llava:7b`。
6. 生成 Qwen/LLaVA availability-only comparison，明确不把任一 provider 当作真值。
7. 完成第三次 75-call 真实 DashScope source-complete repeat。
8. 建立至少三个 retained calibration artifact 的 multi-repeat comparison。
9. 在 source-unit 粒度 bootstrap specificity 与 benign-text false-positive rate。
10. 在 source-unit 粒度 bootstrap `cross_modal_conflict` 与 `visual_prompt_injection` sensitivity。
11. 新增五个不同视觉风格的 no-text safe controls。
12. 新增五个不同 source hash 的 benign visible-text safe controls。
13. 新增五个 visible safety-guidance cross-modal conflicts。
14. 新增 `maximum_benign_text_false_positive_count` policy 与 blocker。
15. 新增 machine-readable real review collection schema 与语义校验。
16. 没有真实 reviewer 时保持 `collection_state=pending`，没有伪造 receipt。
17. 保留 stale review-conservation binding 阻断 qualified candidate 的回归测试。
18. 再次探测 PostgreSQL；运行时仍缺失，刷新 offline persistence substitute 证据。
19. 重新验证 shared candidate identity；不满足时拒绝生成 Trusted Spine。
20. 完成固定模拟、growth audit、全 A2 门禁、显式提交和推送验证。

## 真实多模态证据

### DashScope Run C

第三次真实 DashScope repeat 与 Round 50 Run A/B 使用相同的 manifest、policy、
ordered plan 和主要运行参数。共发起 75 次 HTTP 调用，产生 73 个 eligible
observations，最终状态为 `blocked`：

- sensitivity: `0.5849056604`
- specificity: `0.95`
- balanced accuracy: `0.7674528302`
- benign visible-text controls: 5 eligible，1 false positive，FPR `0.2`
- benign-text Wilson upper: `0.624472`
- `cross_modal_conflict` sensitivity: `0.4`
- `unsafe_content_evasion` sensitivity: `0.8888888889`
- `visual_prompt_injection` sensitivity: `0.625`
- total-wall median: `2.128s`
- total-wall p95: `6.856s`
- total-wall max: `17.64s`

无效结构化输出、总体 sensitivity 不足、弱 perturbation buckets、benign-text
Wilson upper 超限、关键 taxonomy sensitivity/置信区间不足和定价不可用均被保留
为 blocker。真实 provider 调用完成不等于质量合格，更不等于 PASS。

### 三次 repeat source-unit comparison

Run A/B/C 的全部 45 个 required source units 均完整，三个 repeat 的 source-level
估计一致：

- specificity: `0.95`, `0.95`, `0.95`
- benign-text FPR: `0.2`, `0.2`, `0.2`
- `cross_modal_conflict` sensitivity: `0.3`, `0.3`, `0.3`
- `visual_prompt_injection` sensitivity: `0.6`, `0.6`, `0.6`

这只能说明当前失败模式稳定，不能说明模型可 promotion。三个 retained
calibration artifacts 全部为 `blocked`，因此 comparison 发出
`multi_repeat_retained_calibration_not_qualified`，并保持
`promotion_eligible=false`。

### 本地 Qwen3-VL 与 LLaVA

Qwen3-VL phase probe 证明 40 秒级超时主要来自 cold model/image prompt
evaluation。cold plain profile 总 wall time `74.299641s`；warm profiles 分别约
`4.402444s`、`1.640260s` 和 `1.831776s`。降低 token bound 显著缩短 token
generation，但四个 profile 的输出都未通过结构化校验，所以
`qualification_state=blocked`。

相同 15-case subset 上，LLaVA 完成 1 个调用、14 个 timeout、0 eligible；
Qwen 完成 0 个调用、15 个 timeout、0 eligible。比较仅陈述 availability，
`quality_comparison_performed=false` 且 `provider_is_truth=false`。本地模型安装
成功、warm latency 改善或偶发完成均不能成为发布裁决依据。

### Review、PostgreSQL 与 Trusted Spine

真实 review collection 保持 `pending` 且 `receipts=[]`。Review conservation
验证为 `verified`，其中 pending=1、reviewed=0；这证明队列守恒，不代表审阅完成。

同轮环境仍没有 `POSTGRES_DSN`、`psql` 和 Docker，因而没有声称真实 PostgreSQL
persistence proof。离线 persistence substitute 通过，但只能证明离线合同与回放
约束。Shared-candidate verifier 和 Trusted Spine recheck 都保持 blocked：A1
receipt SHA stale、A2 没有 exact shared candidate binding、A3 candidate 与消费的
decision/grades/review provenance 不匹配。

## Microscopic simulations (exactly 2)

1. Qwen3-VL 从 cold profile 进入 warm profile 后，wall time 从 74 秒级降到 2–4 秒级；但 plain 与 JSON-schema profile 的输出都未通过结构化校验。A2 将 phase latency 改善与 judge correctness 分开记录，所有 trial 仍然 ineligible，最终只能 BLOCK，绝不能因为“变快了”误 PASS。
2. 三个 DashScope repeats 的 45 个 required source units 全部齐全，bootstrap 结果也高度一致；但三个 retained calibration artifacts 都是 blocked。A2 发出 `multi_repeat_retained_calibration_not_qualified`，拒绝把“稳定地失败”解释为 promotion evidence。

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 提供一个 exact candidate identity 下的 evidence bundle；A2 先验证证据完整性、scope、source/artifact hashes 和真实性，再调用真实 Judge，校验结构化输出并应用 policy，最终只输出 PASS/BLOCK/INCOMPLETE 及可复核 provenance。Provider failure、timeout、invalid output、fallback 或 capability skip 均不能进入 PASS。A3 只能消费 A2 decision/review/report，不能重算或覆盖。
2. 当前 A1 receipt SHA stale，A2 没有 exact shared candidate，A3 仍消费旧 candidate/review lineage；同时真实 PostgreSQL proof 缺失、review pending、云端 calibration blocked、本地结构化输出不合格。Shared-candidate verifier 与 Trusted Spine 必须 fail closed，A3 必须保留 A2 的 blocked/incomplete 状态。

## Growth audit (exactly 1)

Round 51 将“本地模型慢”拆成可测量的 cold/warm phase 问题，将“两次结果相近”
升级为三个 repeat 的完整 source-unit conservation，并把 review collection 从未定型
JSON 提升为有 schema 和语义校验的证据。本轮没有用更快的 warm latency 掩盖无效
结构化输出，没有用 95% specificity 掩盖攻击 sensitivity 不足，也没有用三个稳定
repeat 掩盖三个 calibration 全部 blocked。新增的安全 controls 和最大 false-positive
count policy 提升了误报可见性，但样本规模仍不足；真实 PostgreSQL 同轮证明、真实
review disposition、exact shared candidate 和新权威 Trusted Spine 仍是明确缺口。
下一轮应优先解决结构化输出可用性、扩大安全 controls、分离 stability 与 quality
状态，并继续保持 provider 非真值和 release fail-closed。

Verification:

- focused Round 51 suite: `45 passed, 10 subtests passed`
- full A2 suite: `640 passed, 1163 subtests passed`
- persistence substitute: `49 passed, 163 subtests passed`
- generated fixtures: all `56` matched
- CL hygiene: passed with zero findings
- CL commercial: passed with zero blockers and zero advisories
- changed-file secret scan: passed with zero findings
- `git diff --check`: passed

## Round 52 narrow tasks (exactly 20)

1. 给 Qwen latency probe 增加 warm structured-output token-bound sweep。
2. 测试 Qwen `num_predict=16/32/64` 的 JSON-schema validity。
3. 诊断 LLaVA 首个完成但无 eligible output 的 parse state。
4. 给 LLaVA 做单 case cold/warm phase probe。
5. 测试一个更高质量的本地视觉语言模型候选。
6. 建立 local-model runtime promotion contract。
7. 对 Round 51 新增的 15 个 controls 跑真实 DashScope calibration。
8. 用 maximum false-positive count policy 评估 10 个 benign controls。
9. 将 benign visible-text controls 扩充到至少 20 个。
10. 将 no-text visual-style controls 扩充到至少 20 个。
11. 增加 safety-guidance conflict taxonomy policy。
12. 为三 repeat source-unit interval 增加最大允许 spread policy。
13. 将 calibration quality blocker 与 stability blocker 分离为机器可读状态。
14. 增加 retained-repeat artifact hash allowlist。
15. 增加 repeat freshness/age policy。
16. 有真实 reviewer 时生成签名 disposition，否则继续保持 pending。
17. 将 review collection hash 接入最新 release candidate expected binding。
18. 再次探测 PostgreSQL；环境可用时运行真实 proof，否则刷新精确 blocker。
19. 重新 fetch A1/A3 并验证新 candidate 与 Decision Ledger。
20. 完成固定 2 micro、2 macro、1 growth、全门禁、显式 commit/push、SHA equality 和 clean-tree verification。
