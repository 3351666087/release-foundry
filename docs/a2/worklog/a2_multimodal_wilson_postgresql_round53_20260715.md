# A2 Round 53：多模态 Wilson 门槛、运行时证明与 PostgreSQL 持久化

Date: 2026-07-15  
Branch: `dev/g3-a2-calibration`  
A2 base: `850b39a666ae638f68501e8997b1a0641de2823c`

## 范围与上游审阅

本轮只修改 A2-owned 文件。提交前重新 fetch 并审阅的引用为：

- main: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- A1 active branch: `566a13d82809114505d1beaa43fdf11b4dba7d7c`
- A2 tracking branch: `850b39a666ae638f68501e8997b1a0641de2823c`
- A3 active branch: `ec8abe2df6ae1d94d166713b31f7a265255cd327`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

A1 已继续前进，但 `round62_a1_release_receipt.json` 仍绑定
`5dd6a898a6771eaf67bf39246f256b579b4d2211`，与当前 A1 ref 不一致。A3
已经只读消费 A2 Round 52 的公开多模态 readiness，并保持
`release_authority=false`；它尚未消费 Round 53 release decision，也没有与
A1、A2 形成 exact shared candidate。A2 因此继续拒绝生成新的权威 Trusted
Spine。

## Round 53 二十项任务落实

1. Ollama probe 新增 public-safe 输出通道、长度和首字符类别诊断，不保存 raw response。
2. 对 Qwen3-VL 8B 执行扩大 token budget 的真实结构化输出 probe。
3. 使用更短结构化合同区分 token budget 与 schema-following 失败。
4. 增加 text-only structured control，隔离视觉编码器影响。
5. local runtime contract v2 增加 cold latency 上限和独立 blocker。
6. local runtime contract v2 增加 required consecutive successes。
7. 新增 10 个不同字体和布局的 benign visible-text controls。
8. 新增 10 个不同视觉风格的 no-text safe controls。
9. 新增 10 个 `cross_modal_conflict` attack controls。
10. 新增 10 个 `visual_prompt_injection` controls 和独立 taxonomy 门槛。
11. 对 40 个新增 controls 执行真实 DashScope qualification run。
12. taxonomy sensitivity 改用 Wilson lower-bound promotion policy。
13. 安全 controls 改用 false-positive Wilson upper policy。
14. repeat source-unit hash allowlist 增加 unexpected 与 expected-missing 双向拒绝。
15. repeat freshness 校验覆盖 `as_of` 早于 observation timestamp 的 fail-closed 路径。
16. 增加 A3 可只读消费的 repeat comparison v2 public projection。
17. shared candidate identity v2 校验 collection/conservation hash mismatch。
18. 使用 PostgreSQL 17.10 执行同轮真实 reopen persistence 与 rollback proof。
19. 重新 fetch A1、A3、main 和 strategy，并刷新 candidate 与 Trusted Spine blockers。
20. 执行固定 simulations、growth audit、全门禁、显式 commit/push 和 SHA equality 检查。

## 真实多模态结果

### DashScope Round 53 controls

真实运行完成 `40/40`：

- safe controls: `20/20` correct
- specificity: `1.0`
- false-positive Wilson upper: `0.161125`
- total attack sensitivity: `0.5`
- `cross_modal_conflict`: `3/10`, Wilson lower `0.107791`
- `visual_prompt_injection`: `7/10`, Wilson lower `0.396778`

安全样本误报问题在本轮 controls 上得到改善，但两个攻击 taxonomy 的 Wilson
lower bound 均未达到 promotion policy。A2 输出 `blocked`，不会让 provider
调用成功、低延迟、总体 specificity 或部分攻击检出掩盖 taxonomy 漏检。

### Qwen3-VL 8B 输出通道

Ollama 的正式 `response` 为空，候选结构化内容只出现在 `thinking` 通道。A2
不把隐藏 reasoning 自动提升为正式模型输出，也不保存 raw text。image 和
text-only required structured profiles 的 completed count 均为 `0`，local
runtime promotion 保持 `blocked`。cold 和 warm latency 采用不同 blocker，
避免把 cold 超限误报成 warm 超限。

### Repeat quality、stability 与 A3 projection

repeat comparison v2 现在要求 observed source units 与 hash allowlist 完整双向
相等：未知 source 和预期 source 缺失都会 fail closed。A3 public projection
schema 约束 qualified/blocked 状态与 blocker 数组一致，并要求
`promotion_eligible=true` 时 quality、stability 均 qualified 且 blocker 为空。
该 projection 只携带 public-safe readiness，始终没有 release authority。
Round 53 已被真实 provider 评估的 PNG 作为不可变 canonical artifacts 保存；
generator 在不同主机字体环境中不会重写这些已存在文件，避免 Linux CI 使用不同
fallback font 后悄悄改变 artifact hash 和 evidence binding。

## PostgreSQL 与 Trusted Spine

本轮在 PostgreSQL `17.10` 上完成两个真实测试：

- hash-only candidate record commit 后断开重连仍存在；
- 非法 decision 触发 CHECK violation，事务回滚后没有 partial record。

结果为 `2 passed`。离线 persistence suite 结果为 `49 passed`。公开 evidence
不包含 DSN、账号或 secret。该证明只说明同轮数据库持久化合同已验证，不会单独
解锁 release。

shared candidate verification 仍正确 blocked。主要原因是 A1 receipt SHA stale、
A2 没有 exact shared candidate、A3 candidate 与 A1 不同、A3 消费的是 Round 52
而非 Round 53 decision，且 consumed decision/grades hashes 不匹配。最新
Trusted Spine recheck 因 exact A1/A2/A3 binding、合格多模态 calibration 和真实
human review 均未具备而拒绝生成 ledger。

## Microscopic simulations (exactly 2)

1. 输入 20 个安全 control 和 20 个攻击 control。Judge 完成全部调用，安全样本
   为 `20/20`，但两个攻击 taxonomy 分别只检出 `3/10` 和 `7/10`。A2 同时计算
   false-positive Wilson upper 与 taxonomy Wilson lower；安全门槛通过不能覆盖
   攻击门槛失败，最终必须输出 BLOCK，不能因 provider 成功而误 PASS。
2. 同一 Qwen3-VL 8B 候选分别执行 image、text-only、cold 和 warm structured
   profiles。即使隐藏 `thinking` 中出现类似 JSON 的内容，只要正式 `response`
   为空，observation 就保持 ineligible；cold latency 超限使用 cold blocker，
   structured completion 为零则 runtime promotion 输出 BLOCK。

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 提供 evidence bundle 后，A2 先验证 candidate identity、scope、完整性和
   artifact/source hashes，再调用真实 Judge。Judge 输出必须通过 schema、
   calibration、golden regression、taxonomy policy 和必要人审，A2 才能生成
   PASS/BLOCK/INCOMPLETE。provider failure、timeout、invalid output、fallback
   和 capability skip 均不能进入 PASS；A3 只读消费 A2 decision、grades、
   provenance 和 review，不重算 release decision。
2. 当前 A1 ref 已前进但 release receipt 仍 stale；A2 Round 53 没有 exact shared
   candidate；A3 只读消费 Round 52，candidate、decision 和 grades hashes 仍未
   对齐。即使本轮 PostgreSQL proof、repeat stability 和 public projection 都
   通过，A2 仍必须拒绝 Trusted Spine，A3 必须保留 blocked/incomplete 状态。

## Growth audit (exactly 1)

Round 53 把多模态样本数量扩展到 40 个，并用 Wilson 区间替代仅看点估计或最大
误报数的 promotion 判断；把 cold/warm latency、正式 response/hidden thinking、
repeat quality/stability、expected/observed source allowlist，以及 A3 projection
状态一致性分别建模。真实 PostgreSQL proof 补齐了 Round 52 的环境缺口，但没有
被误用为 release 解锁条件。增长审计确认当前主要风险已经从“安全样本全误报”
转为“攻击 taxonomy sensitivity 不足、正式结构化输出为空、human review 和
三项目 exact binding 缺失”。下一轮应优先提高可复核攻击覆盖、明确模型输出
通道合同，并让 A1/A2/A3 对同一候选和同轮 decision/grades 完成只读绑定。

Verification:

- focused Round 53 and compatibility suite: `47 passed`
- full A2 suite: `686 passed, 2 skipped`
- offline persistence suite: `49 passed`
- real PostgreSQL persistence proof: `2 passed`
- generated historical fixtures: all `56` matched
- Round 53 canonical artifact rewrite regression: passed
- CL hygiene: passed with zero findings
- CL commercial: passed with zero blockers and zero advisories
- changed-file secret scan: passed with zero findings
- changed JSON parse check: `20` files passed
- `git diff --check`: passed

## Round 54 narrow tasks (exactly 20)

1. 为 Ollama `thinking` 与正式 `response` 建立明确、版本化且 fail-closed 的通道合同。
2. 增加只输出长度、hash 和 parse state 的 auxiliary thinking diagnostics。
3. 验证至少一个正式 `response` 可返回 JSON 的本地多模态候选。
4. 为每个本地模型执行至少三次连续 structured success/failure repeat。
5. 为 cold、warm latency 分别增加 p50、p95 和样本量门槛。
6. 扩充 10 个低对比度 benign visible-text controls。
7. 扩充 10 个多语言 benign visible-text controls。
8. 扩充 10 个无文字但高复杂度 safe controls。
9. 扩充 10 个细粒度 `cross_modal_conflict` attacks。
10. 扩充 10 个多语言 `visual_prompt_injection` attacks。
11. 为每个 attack taxonomy 设定最低 20-case qualification 门槛。
12. 为 Wilson 门槛增加边界相等、少一例和多一例的回归测试。
13. 固化 Round 53 图片生成字体 provenance，消除跨 OS byte drift。
14. 为 generated controls 增加内容 manifest 与像素 hash 双重校验。
15. 执行第二次独立 DashScope repeat 并比较 taxonomy spread。
16. 为 A3 projection 增加 Round 53 consumer compatibility fixture。
17. 在 A1 receipt 更新后重跑 exact candidate identity verification。
18. 在 A3 消费 Round 53 后重跑 decision/grades hash binding。
19. 使用 fresh PostgreSQL database 重复 reopen、rollback 和 schema migration proof。
20. 完成固定 2 micro、2 macro、1 growth、全门禁、显式 commit/push、SHA equality 与 clean-tree 验证。
