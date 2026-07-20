# 多模态审核分配历史与签名包 - 2026-07-14

## 一句话说明

上一轮解决了审核任务如何领取、续期、转交和释放。本轮解决的是：这些操作以后发生争议时，
企业如何证明操作历史没有被悄悄修改。

本轮把领取历史做成可校验的审核包，再作为 `review_record` 放入现有 Audit Bundle，最后由
现有 Ed25519 Audit Archive 签名和验证。它证明人员协作历史，不代表 A2 已经给出真人裁决。

## 本轮校准基线

- `origin/main`: `ccf6ce5`
- A1 peer: `2307231`
- A2 peer: `1553562`
- A2 仍没有可公开安全消费的真实真人审核凭证。
- A2 Round 49 仍为 `blocked`；本轮没有修改 A2 分数、风险、Pass/Fail、失败类型或 Decision Ledger。

## 数据流

```text
A2 公开安全多模态比较
  + A3 append-only 领取事件
  -> 审核分配历史包
  -> 包根哈希和事件链验证
  -> Gate CLI review_record
  -> Audit Bundle 根哈希与 custody chain
  -> Ed25519 Audit Archive 签名
  -> 离线验证
```

## 审核历史包

Schema：`a3.multimodal_review_assignment_packet.v1`

每条事件只保留：

- queue/case/comparison 绑定；
- 五层 tenant scope；
- claim、renew、transfer、release 或过期后重新领取；
- 连续版本号；
- 审核员哈希别名和角色；
- lease 起止时间；
- reason code；
- event id 和 SHA-256 event hash。

不保存：

- 姓名、邮箱和账号；
- 原始模型输出和私有媒体；
- signed URL；
- key、token、cookie；
- 真人 disposition；
- 发布权限。

## 完整性验证

`verifyA3MultimodalReviewAssignmentPacket(...)` 会失败关闭地检查：

1. schema version；
2. packet root hash；
3. 每条 event id 和 event hash；
4. 版本必须从 1 连续增长；
5. 前后 reviewer 状态必须衔接；
6. 时间不能倒退；
7. queue/case/comparison 必须一致；
8. 五层 tenant scope 必须一致；
9. release 事件必须清空 reviewer；
10. 不能自称已通过 Audit Archive 签名；
11. 不能携带 secret、邮箱、URL 或本地账号路径；
12. 所有 authority 字段必须保持 false。

## 签名边界

审核包自己只有根哈希，不能自称“已签名”。Gate CLI 只有在包验证通过后，才允许通过：

```text
--multimodal-review-packet <packet.json>
```

把它加入 Audit Bundle。随后 `a3_audit_archive.mjs` 对包含该文件精确 SHA-256 和 byte size 的
清单做 Ed25519 签名。归档验证器会重新检查：

- bundle index；
- 审核包文件哈希和大小；
- runs/grades 输入；
- archive root hash；
- Ed25519 signature。

当前样本 signer 为 `self_signed_local_key_not_sso_bound`，只证明本地签名链工作，不是企业 KMS、
HSM、OIDC、SSO 或生产服务身份回执。

## CLI

生成审核包：

```text
node services/report/a3_multimodal_review_packet_cli.mjs \
  --comparison fixtures/a3/p3/a2_multimodal_comparison_v3_564d4b0_sample.redacted.json \
  --events fixtures/a3/p3/a3_multimodal_review_assignment_events.redacted.json \
  --generated-at 2026-07-14T12:05:00.000Z \
  --output fixtures/a3/p3/a3_multimodal_review_assignment_packet.redacted.json \
  --output-verification fixtures/a3/p3/a3_multimodal_review_assignment_packet_verification.redacted.json
```

离线验证：

```text
node services/report/a3_multimodal_review_packet_cli.mjs \
  --verify fixtures/a3/p3/a3_multimodal_review_assignment_packet.redacted.json \
  --json
```

## 产品接入

- Dashboard 返回 `multimodal_review_assignment_packet`。
- Review 页面显示内部完整性、事件数量、包根哈希和归档签名待办。
- 每个队列项可用键盘展开操作历史。
- JSON、Markdown 和 Hosted Report 保留 metadata-only history。
- Artifact Registry 新增 `multimodal_review_assignment_packet`。
- 新增 `multimodal_review_packet` packet preset。
- API Reference 升级为 v11。

## 证据

- `fixtures/a3/p3/a3_multimodal_review_assignment_events.redacted.json`
- `fixtures/a3/p3/a3_multimodal_review_assignment_packet.redacted.json`
- `fixtures/a3/p3/a3_multimodal_review_assignment_packet_verification.redacted.json`
- `fixtures/a3/p3/a3_multimodal_review_assignment_bundle.redacted.json`
- `fixtures/a3/p3/a3_multimodal_review_assignment_archive.redacted.json`
- `docs/screenshots/a3-webapp-multimodal-review-queue-desktop.png`
- `docs/screenshots/a3-webapp-multimodal-review-queue-mobile-390x844.png`
- `tests/a3/a3_multimodal_review_packet.test.mjs`

## 当前仍未完成

- 没有 A2 真实真人 disposition 和完整 review chain。
- 没有同 candidate 的有效 Decision Ledger。
- 没有 A1 hosted browser identity、CSRF 和企业 reviewer directory。
- 没有目标 staging/VPC 的 KMS/SSO signer、PostgreSQL RLS 和对象存储回执。
- 没有证明 packet 已由客户 tenant 绑定的生产服务身份签名。
- Golden Path 仍为 `7/11`，Deployment Acceptance 仍为 `8/17`，production ready 仍为 false。
