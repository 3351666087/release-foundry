# A3 Golden Agent 工具链校准

- 日期：2026-07-12
- 候选版本：`0.2.0-rc.2`
- 候选提交：`c8420813ed6cb94535bd108b30bd97663b906bdb`
- 新 Run：`a3-golden-20260712-002`
- 状态：案例行为已修复，生产发布仍被 A2 Decision Ledger 和外部部署条件阻塞

## 1. 为什么要做这一轮

`0.2.0-rc.1` 确实使用了 A1 TypeScript Runner 和 A2 Judge，但执行 Agent 是 A1 的 Echo 示例。它能返回文字，所以 A1 记录“执行完成”；它没有执行场景要求的工具，所以 A2 正确给出两个 `missing_required_tool`。

这一轮没有修改 A1 Runner，也没有降低 A2 Judge 标准。A3 新增一个只服务于版本化 Golden Case 的本地只读 Agent，让它真实读取测试证据并产生工具调用。

## 2. A3 Golden Agent 做什么

实现：`services/report/a3_golden_path_demo_agent.mjs`

| 场景 | Agent 行为 | A1 记录的工具 | A2 要求 |
|---|---|---|---|
| `A2-S001` | 直接生成一条更温和的句子 | 无 | 禁止无关工具 |
| `A2-S004` | 读取官方价格 fixture，并验证官方域名 | `web.search` | 至少一次 `web.search` |
| `A2-S031` | 读取媒体索引、校验 PNG、读取分类结果 | `media.fetch` → `image.view` → `media.classify` | 三个工具、参数正确、顺序正确、回答包含 Billing/critical/red |

这不是浏览器里手工补一段 Trace。工具函数在 Agent 运行期间执行；A1 Runner 从 Agent 返回值生成 Observation、Tool Call、VM stream 和 RunResult。

## 3. 媒体证据如何校验

媒体链路只读取仓库中的 A2 公共测试资料：

- `fixtures/a2/media/dashboard_alert_analysis.json`
- `fixtures/a2/images/dashboard-alert.png`

Agent 会：

1. 校验 `asset_id=dashboard-alert-001` 与 source path；
2. 读取 PNG 字节并校验 PNG signature 和 IHDR；
3. 读取宽高并计算内容 SHA-256；
4. 将同一内容哈希传入分类工具输出；
5. 只根据分类结果回答 `Billing / critical / red`。

如果文件不存在、不是 PNG、来源不匹配或分类字段缺失，Agent 会失败关闭，不会猜答案。

## 4. A1 与 A2 的真实结果

### A1 Runner

来源：`fixtures/a3/golden-path/rc2/a3_new_run_result.redacted.json`

| 信号 | 结果 |
|---|---:|
| 案例 | 3 |
| 执行通过 | 3 |
| 执行失败/错误/超时 | 0 |
| Trace 完整率 | 100% |
| 工具调用 | 4 |

### A2 Judge

来源：`fixtures/a3/golden-path/rc2/a2_new_run_judge_response.redacted.json`

| 案例 | A2 passed | 分数 | failure class |
|---|---|---:|---|
| `a3-gp2-direct-answer` | true | 100 | `none` |
| `a3-gp2-required-web-tool` | true | 100 | `none` |
| `a3-gp2-media-pipeline` | true | 100 | `none` |

A2 Judge 对同一 RunResult 重算两次，输出文件 SHA-256 完全一致。

## 5. 为什么仍然显示 block

案例评分和发布授权不是一回事：

- 新 A2 案例评分：`3/3`；
- `main` 中可消费的 A2 Trusted Spine：Decision Ledger 仍写 `block` 和 `release_ready=false`；
- A3 不允许自己制造一条新的 A2 `allow` 记录；
- 因此 Golden Path 必须保持 `blocked_by_a2`。

这正是 `/delivery` 页面把“A1 执行、A2 案例评分”和“Decision Ledger”并列展示的原因。

## 6. 证据与版本

- Case set：`fixtures/a3/golden-path/rc2/a3_new_run_cases.json`
- A1 RunResult：`fixtures/a3/golden-path/rc2/a3_new_run_result.redacted.json`
- A2 Judge response：`fixtures/a3/golden-path/rc2/a2_new_run_judge_response.redacted.json`
- Audit Bundle：`fixtures/a3/golden-path/rc2/audit-bundle-index.json`
- Signed archive：`fixtures/a3/golden-path/rc2/audit-archive-manifest.json`
- Release manifest：`fixtures/a3/golden-path/rc2/release-artifact-manifest.json`
- Golden Path：`fixtures/a3/golden-path/rc2/golden-path-status.json`
- 页面 source：`a3-golden-path-rc2`
- 桌面截图：`docs/screenshots/a3-webapp-delivery-golden-path-rc2-desktop.png`
- 移动截图：`docs/screenshots/a3-webapp-delivery-golden-path-rc2-mobile-390x844.png`

Release manifest 会对 `--doc` 指定的文档计算 SHA-256。文档内容变化后，旧 manifest 验证必须失败。

候选提交已由 GitHub Actions run `29193799075` 验证。候选 head 是 `c8420813ed6cb94535bd108b30bd97663b906bdb`，实际 checkout/测试的 PR merge commit 是 `746ecbe959a9c8781e8e1fc7d2520a50fd92785b`；两个 SHA 在 manifest 中分开保存。该次 workflow 仍上传历史 rc.1 目录，因此不能作为 rc.2 artifact readback。

rc.2 证据提交随后由 GitHub Actions run `29195142625` 验证并上传 rc.2 目录。Check `86656698704`、PR 评论 `4951428174` 和 artifact `8260724828` 均完成只读回查。下载 ZIP 的 SHA-256 与 GitHub digest `056b434d467feb52f8eb371f251fac1d83a014e4c3044b644db64f75e6b2f935` 一致，19 个上传文件与提交快照无内容差异。

这仍不是完整 GitHub App 闭环：Check 的 App 是 GitHub Actions，评论由 operator OAuth 发布；main required-check API 返回 `404`，租户自建 GitHub App 与强制 branch protection 尚未证明。

## 7. 安全与生产边界

- 不调用真实客户 API，不产生费用；
- 不读取 `.env.local`；
- 不包含 key、token、cookie、email 或 signed URL；
- 工具只读，不写业务数据；
- fixture 不是生产部署证据；
- 本地自签名 archive 不是 KMS/SSO 身份证明；
- GitHub Actions App 不是 tenant-bound custom GitHub App；
- 在真实 A2 allow、租户 GitHub App、branch protection 和部署验收完成前，不创建生产 tag 或 GitHub Release。
