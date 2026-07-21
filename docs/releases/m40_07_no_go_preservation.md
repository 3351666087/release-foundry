# M40-07 Authoritative NO-GO Preservation

## 目标

Customer Agent Release 只有在以下四类权威条件全部独立通过时，才允许返回
`approve_customer_agent_release`：

1. Product Release 已批准。
2. A2 Decision Ledger 允许发布，并明确标记 `release_ready=true`。
3. A3 release gate 与 delivery 都已通过，且交付证据完整。
4. 人工审批回执有效并绑定同一个 release、candidate 和 source commit。

## 合同矩阵

下表使用本地合成合同数据验证控制流，不代表真实生产批准：

| 条件状态 | 预期 Customer 结论 | 必须出现的 blocker |
| --- | --- | --- |
| 四类条件全部通过 | `approve_customer_agent_release` | 无 |
| 仅 Product 未批准 | `block_customer_agent_release` | `product_release_not_approved` |
| 仅 A2 阻止且未 ready | `block_customer_agent_release` | `a2_release_blocked`, `a2_release_not_ready` |
| 仅 A3 gate 阻止 | `block_customer_agent_release` | `a3_gate_blocked` |
| 仅 A3 delivery 未 ready | `block_customer_agent_release` | `a3_delivery_not_ready` |
| 仅人工审批缺失 | `block_customer_agent_release` | `human_approval_missing` |

合同测试要求每个 NO-GO 场景的 blocker 集合精确匹配，避免某个权威条件被其他条件
掩盖。测试同时确认 A3 始终报告 A2 的结论，不会重算 A2。

## 当前真实 rc.3 状态

当前 `a3-golden-agent@0.2.0-rc.3` 的 candidate、run、SHA 和版本已经对齐，
但真实结论仍为 `block_customer_agent_release`。当前权威 blocker 是：

- `product_release_not_approved`
- `a2_release_blocked`
- `a2_release_not_ready`
- `a3_gate_blocked`
- `a3_delivery_not_ready`
- `a3_ci_tested_sha_missing`
- `human_approval_missing`

这些 blocker 保持原样。本轮没有修改 A2 Decision Ledger、没有生成真人审批、没有声明
生产部署，也没有把 NO-GO 改名为 GO。

## 验证

```powershell
python -B -m pytest tests/release/test_customer_agent_release_contract.py -q -p no:cacheprovider
python -B -m pytest tests/release -q -p no:cacheprovider
python scripts/build_m40_rc3_customer_verification.py --check --json
```

只有真实 Product、A2、A3 delivery 与人工审批分别提供有效回执后，才能重新构建新的
Customer Release 候选。合成测试的全通过行不能作为生产 GO 证据。
