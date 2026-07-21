# M40-06 rc.3 Customer Verification

## 本轮结论

Customer Agent Release 已经重新绑定到同一个 rc.3 候选：

| 字段 | 值 |
| --- | --- |
| Candidate | `a3-golden-agent@0.2.0-rc.3` |
| Run | `a3-golden-20260720-003` |
| Evidence version | `0.2.0-rc.3` |
| Release package commit | `35ffd3bed3f5d37bdceeb4c0bec5067801c631f5` |
| A1 candidate source | `1d292047e991995fdf52f0545ffff410ee19a171` |
| A2 authority | `d3529c356e49ce8502c050f0dad44020031ee0dd` |
| A3 delivery implementation | `a0b427257c5cd80fbe3394b4a406fa21f50bae37` |
| A2 Decision Ledger head | `sha256:af84d7e9e3143f4da06341f2e20f3402c8f44ed5efc8221b18c8ef2869747a4e` |
| A2 grades | `sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304` |

验证结果：

- `identity_alignment = passed`
- `mismatch_reasons = []`
- Customer decision = `block_customer_agent_release`
- Product decision = `block_product_release`
- A2 decision = `block`

## 为什么仍然是 NO-GO

身份对齐通过，只代表 Product、A1、A2、A3 正在讨论同一个候选，不代表它已经满足上线条件。当前仍有七个真实阻塞：

1. Product Release 尚未批准。
2. A2 Decision Ledger 仍为 `block`。
3. A2 `release_ready` 仍为 `false`。
4. A3 gate 仍为 `block_release`。
5. A3 delivery 仍为 `production_ready=false`。
6. 当前 packet 没有 candidate-bound CI tested SHA receipt。
7. 没有真实人工批准回执。

A3 没有重算 A2，也没有把 NO-GO 改名为 GO。要得到正式 GO，必须由对应 owner 分别补齐这些证据。

## 证据

- Customer packet：`fixtures/releases/m40-06/agent-release-demo-a3-golden-agent-0.2.0-rc.3`
- Check receipt：`fixtures/releases/m40-06/customer-verification-receipt.json`
- Builder/checker：`scripts/build_m40_rc3_customer_verification.py`
- Contract tests：`tests/release/test_m40_customer_verification.py`

## 验证命令

```powershell
python scripts/build_m40_rc3_customer_verification.py --check --json
python -B -m pytest tests/release -q -p no:cacheprovider
```

该证据包只用于 M40-06 的可重算验证；它不是生产签名、人工批准或正式 GO 回执。
