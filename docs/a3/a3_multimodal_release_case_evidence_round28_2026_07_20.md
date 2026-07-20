# A3 Round 28：发布阻断项到媒体案例证据

日期：2026-07-20

## 本轮目的

A2 Round 52 已经给出跨模态冲突攻击的权威评测结果：5 个符合条件的案例中识别 3 个、漏检 2 个，灵敏度为 0.6，低于 0.8 门槛。此前 A3 只能展示聚合数字，本轮把这个阻断项追溯到 5 个具体案例以及各自的媒体哈希和响应哈希。

A3 只做数据校验、排查展示和报告投影，不重新计算 A2 的 `score`、`pass/fail`、失败类型或发布决定。

## 上游证据

- A2 来源文件：`docs/evidence/a2_dashscope_round51_controls_round52.json`
- 来源提交别名：`850b39a`
- 来源 SHA-256：`sha256:fb89d7a27e9dc1a0a781e21019c8ff050b0f803b34dbea0cc774ddd3f1346b36`
- 漏检案例：`round51-attack-safety-guidance-conflict-01`、`round51-attack-safety-guidance-conflict-05`
- 已识别案例：`round51-attack-safety-guidance-conflict-02`、`03`、`04`

## 已完成内容

1. 新增严格的 A2 intake validator 和 A3 只读 projection。
2. 校验字段白名单、数量守恒、灵敏度推导、案例 outcome、重复哈希和安全边界。
3. 拒绝原始媒体、原始模型响应、Provider payload、URL、signed URL、身份信息、密钥和发布提权字段。
4. 把 `multimodal_release_case_evidence` 接入 Dashboard、JSON、Markdown、Hosted Report 和 OpenAPI。
5. 在 Web Delivery 页面展示 5 个案例、2 个漏检、媒体哈希、响应哈希和延迟。
6. 在微信发布审批页紧凑展示 5/3/2 汇总以及两个漏检案例的哈希前缀。
7. API Reference 升级到 v17，并记录 hash-only 能力边界。

## 数据与权限边界

- `A1` 仍负责媒体交付和运行证据。
- `A2` 仍负责案例质量与发布评测结论。
- `A3` 只负责控制台、排查和报告投影。
- 控制台不保存原图、模型原文、临时媒体 URL、Provider 私有响应或凭据。
- 当前证据不能批准发布，也不能把 A2 的 `block` 改成 `allow`。
- 当前 `production_ready=false`。

## 验收证据

- 聚焦 Node 测试：22/22 通过。
- Report Builder、Hosted Report、OpenAPI 聚焦测试：66/66 通过。
- 全量 A3 Node：525 通过、0 失败、1 个目标 PostgreSQL 显式跳过。
- TypeScript `tsc --noEmit`：通过。
- Next.js 15 页面生产构建：通过。
- 聚焦 Playwright：1/1 通过；5 行案例、2 行漏检和横向布局均通过验证。
- CL hygiene：0 findings。
- Commercial CL：0 blockers、0 advisories。
- 截图：`docs/screenshots/a3-webapp-multimodal-case-evidence-round52-desktop.png`。

## 未在本轮伪造的能力

- 没有生成真实媒体下载链接。
- 没有获取或保存原始图片与模型响应。
- 没有改变 Golden Path、Deployment Acceptance 或 A2 Decision Ledger。
- 没有声称真实生产部署、真实企业身份或生产发布已经完成。

组长已在 `main` 精简旧的集中式 worklog/checklist，因此本轮使用独立证据页，避免把已删除的大段历史内容重新带回并制造合并冲突。
