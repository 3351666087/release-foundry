# A2 Round 52：安全 controls、模型运行时 promotion 与候选绑定

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`
A2 base: `750468072aa39958d3a7d35981766f8944a59a80`

## 范围与上游审阅

本轮只修改 A2-owned 文件。提交前重新 fetch 并审阅的引用为：

- main: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- A1 active branch: `3dcba413ef94d196ced05a5c6da18eff3998c953`
- A2 tracking branch: `750468072aa39958d3a7d35981766f8944a59a80`
- A3 active branch: `de6d1161cd6b198305881e2c2a56ec3371fc4dd0`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

A1 新增了 credential binding 的并发、跨账户和失败清洗防护，但
`round62_a1_release_receipt.json` 仍绑定旧 SHA
`5dd6a898a6771eaf67bf39246f256b579b4d2211`，与当前 A1 ref 不一致。
A3 已把 A2 Round 51 repeat stability 作为只读、非权威 evidence 摄取，并明确
`release_authority=false`；但它没有消费本轮 Round 52 的 release decision，也没有统一
A1/A2/A3 candidate identity。因此本轮不能生成新的权威 Trusted Spine。

## Round 52 二十项任务落实

1. 为 Ollama latency probe 增加可重复 `--profile NAME:NUM_PREDICT:FORMAT`。
2. 真实测试 Qwen3-VL 4B 的 `num_predict=16/32/64` JSON-schema 输出。
3. 记录 LLaVA 完成响应但结构化解析失败的精确状态。
4. 对 LLaVA 执行单样本 cold/warm/plain/schema phase probe。
5. 下载并真实测试更高质量的 `qwen3-vl:8b` 本地候选。
6. 建立 local-model runtime promotion contract。
7. 对 Round 51 新增的 15 个 controls 执行真实 DashScope。
8. 以 maximum false-positive count 评估 10 个安全 controls。
9. 将 benign visible-text controls 扩充到至少 20 个。
10. 将 no-text visual-style controls 扩充到至少 20 个。
11. 增加 safety-guidance `cross_modal_conflict` taxonomy policy。
12. 为 retained repeats 增加 maximum spread policy。
13. 将 calibration quality 与 repeat stability 状态分离。
14. 增加 retained calibration artifact hash allowlist。
15. 增加 repeat freshness/age policy。
16. 无可验证的人类 reviewer，因此保持 collection pending、receipts 为空。
17. 将 review collection 与 conservation 两个 hash 同时绑定到 shared candidate identity v2。
18. 再探测 PostgreSQL；运行时仍缺 DSN、psql 和 Docker，完成同轮离线替代证明。
19. 重新 fetch A1/A3/main/strategy，并拒绝生成不匹配的 Trusted Spine。
20. 执行固定模拟、growth audit、全门禁、显式暂存、提交与推送验证。

## 真实多模态结果

### DashScope 15-case controls

真实运行完成 15/15 个 eligible observations：

- specificity: `1.0`
- sensitivity: `0.6`
- balanced accuracy: `0.8`
- latency median: `1.008s`
- latency p95: `6.154s`
- 10 个安全 controls 的 false positives: `0`
- 5 个 `cross_modal_conflict` attacks 检出: `3`

安全 controls 全部正确不代表模型合格。攻击 sensitivity 低于 `0.8` policy，
而且 pricing 仍不可用，因此 calibration 和 control-policy assessment 都保持
`blocked`。Provider 成功返回、低延迟和高 specificity 均不能覆盖攻击漏检。

### Qwen3-VL 4B、Qwen3-VL 8B 与 LLaVA

三个本地候选均使用 loopback Ollama，并只保留 public-safe phase receipts，不保留
raw response。Qwen3-VL 4B、LLaVA 7B 和 Qwen3-VL 8B 的 required JSON-schema
profiles 全部未通过结构化输出校验。

Qwen3-VL 8B 的真实结果：

- cold JSON-schema 16-token wall time: `177.768206s`
- warm JSON-schema 16-token wall time: `5.430345s`
- warm JSON-schema 32-token wall time: `10.32176s`
- warm JSON-schema 64-token wall time: `9.535996s`
- completed structured profiles: `0/4`
- runtime promotion: `blocked`

8B 候选 warm latency 可接受，但 cold latency 很高，且 required profiles 的 JSON
仍无效。模型大小、安装成功和 warm speed 都不能替代结构化正确性。

### Repeat quality 与 stability

Round 52 将历史 v1 schema 保持不变，并新增
`a2.multimodal_multi_repeat_comparison.v2`，避免破坏 Round 51 已保存证据。
新合同强制 retained hash allowlist、spread threshold、freshness，以及分离的
quality/stability 状态。

本轮结果：

- quality: `blocked`
- quality blocker: `multi_repeat_retained_calibration_not_qualified`
- stability: `qualified`
- 所有受控指标的 observed spread upper: `0.0`
- 三次 retained repeats 全部 fresh
- promotion eligible: `false`

这说明当前失败模式稳定，不说明模型质量合格。

### Review、PostgreSQL 与 Trusted Spine

真实 review collection 保持 `pending`、`receipts=[]`。Conservation verifier 得到
pending=1、reviewed=0、verification=`verified`；它只证明队列守恒，不证明人审完成。

本轮环境再次确认没有 `POSTGRES_DSN`、`psql` 和 Docker。离线 persistence suite
得到 `33 passed, 163 subtests passed`，证明 atomic replace、fsync、reopen、
rollback/fork detection 和 SQL store contract，但不等价于同轮真实 PostgreSQL proof。

Shared candidate identity v2 同时绑定 review collection hash 与 conservation hash，
但 A1 receipt stale、A2 没有 exact shared candidate、A3 candidate 与 A1 不同，且 A3
没有消费 Round 52 decision。因此 candidate verifier 和 Trusted Spine 均正确保持
blocked，未伪造权威 ledger。

## Microscopic simulations (exactly 2)

1. 输入一个 benign visible-text control，真实 DashScope 返回安全判定，10 个安全
   controls 最终 0 false positives；随后输入 5 个 safety-guidance conflict attacks，
   只检出 3 个。A2 分开计算 specificity 与 attack sensitivity，应用 policy 后输出
   BLOCK，而不是让 `specificity=1.0` 掩盖漏检。
2. 同一张图片依次进入 Qwen3-VL 8B cold 与 warm JSON-schema profiles。Warm wall time
   从 177 秒级降到 5–10 秒级，但四个 profile 均未产生有效结构化结果。A2 将每次
   observation 标为 ineligible，并由 runtime promotion contract 输出 BLOCK；不会因
   warm latency 改善而误 PASS。

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 提供 evidence bundle 后，A2 先验证 candidate、scope、artifact/source hashes 和
   completeness，再调用真实 Judge；Judge 输出必须通过 schema、calibration、golden
   regression 和 policy 才能生成 PASS/BLOCK/INCOMPLETE。Timeout、provider failure、
   invalid output、fallback 和 capability skip 均不能进入 PASS。A3 只消费 A2 的
   decision、grades、review 与 provenance，不重算决定。
2. 当前 A1 receipt SHA 与 A1 ref 不一致；A2 只有 unbound Round 52 candidate；
   A3 只读摄取 Round 51 repeat stability，且仍使用不同 candidate。即使 review queue
   conservation、repeat stability 和离线 persistence 都通过，exact shared identity、
   同轮真实 PostgreSQL proof、qualified calibration 和人审 disposition 仍缺失。
   Trusted Spine 必须拒绝生成，A3 必须保留 A2 的 blocked/incomplete 状态。

## Growth audit (exactly 1)

Round 52 把“安全样本误报减少”与“攻击检出足够”拆成独立 policy，把“repeat 稳定”与
“calibration 质量合格”拆成独立状态，并把本地模型的“已安装、可调用、warm 较快”与
“required structured output 合格”拆成 promotion contract。历史 v1 schema 被保留，
新强制字段进入 v2，避免用新规则破坏旧 evidence。Review collection hash 现在进入
candidate binding，但因为没有真实 reviewer、同轮 PostgreSQL 和 exact A1/A2/A3
candidate，系统仍 fail closed。下一轮需要优先提高本地结构化输出可用性、扩大攻击
taxonomy 样本、补真实数据库 proof，并让 A3 兼容但不提升 v2 evidence 的权限。

Verification:

- focused Round 52 suite: `35 passed`
- full A2 suite: `661 passed, 1163 subtests passed`
- offline persistence substitute: `33 passed, 163 subtests passed`
- generated fixtures: all `56` matched
- CL hygiene: passed with zero findings
- CL commercial: passed with zero blockers and zero advisories
- changed-file secret scan: passed with zero findings
- `git diff --check`: passed

## Round 53 narrow tasks (exactly 20)

1. 为 Ollama probe 捕获 public-safe 的输出长度与首个非空字符类别，禁止保留原文。
2. 测试 Qwen3-VL 8B 在 `num_predict=96/128` 下能否完成最小合法 JSON。
3. 测试更短的枚举键 schema，区分 token budget 与 schema-following 失败。
4. 增加一次无图片的结构化 control，隔离 vision encoder 对输出失败的影响。
5. 为 local runtime contract 增加 cold latency 上限与 cold/warm 分离状态。
6. 为 local runtime contract 增加最小连续成功次数，不允许单次成功 promotion。
7. 新增 10 个不同字体和布局的 benign visible-text controls。
8. 新增 10 个不同图形风格的 no-text safe controls。
9. 新增 10 个 `cross_modal_conflict` attacks，并至少覆盖 5 个视觉风格。
10. 新增 `visual_prompt_injection` Round 53 controls 与独立最低样本门槛。
11. 对扩展 controls 执行一次真实 DashScope qualification run。
12. 为 taxonomy sensitivity 增加 Wilson lower-bound promotion policy。
13. 为安全 controls 增加 maximum false-positive Wilson upper policy。
14. 增加 calibration source-unit hash allowlist 的重复与缺失拒绝测试。
15. 增加 repeat `as_of` 早于 observation timestamp 的 fail-closed 测试。
16. 设计 A3 可消费的 repeat comparison v2 public projection，保持只读和无 release authority。
17. 为 shared candidate identity v2 增加 collection/conservation hash mismatch blocker。
18. 安装或定位可用 PostgreSQL runtime，并运行同轮真实 persistence proof；失败则记录安装阶段。
19. 再次 fetch A1/A3/main/strategy，检查 A1 receipt 与 A3 consumed decision 是否更新。
20. 完成固定 2 micro、2 macro、1 growth、全门禁、显式 commit/push、SHA equality 与 clean-tree 验证。
