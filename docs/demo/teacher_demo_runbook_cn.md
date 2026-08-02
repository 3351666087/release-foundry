# ReleaseFoundry 老师汇报演示手册（A1 + A2 + A3）

> 版本：2026-07-22
> 目标：用一条可重复的本地 Golden Path，向老师说明 A1、A2、A3 如何协同工作。
> 重要边界：本手册使用脱敏、确定性的本地 fixture，不把本地演示冒充成生产部署或真实 ReleaseFoundry 云端结果。

## 1. 先记住一句话

ReleaseFoundry 是一个“智能体发布前的质量与证据控制台”。它回答四个问题：

1. 智能体这次到底做了什么？
2. 它有没有按照预期完成任务？
3. 如果失败，失败在哪里、为什么失败？
4. 证据足够时，能不能让人工审核并发布？

最短的产品链路是：

```text
用户任务 -> Agent 执行 -> A1 记录事实 -> A2 评测事实 -> A3 展示、审核、报告、发布门禁
```

## 2. 三个小组分别做什么

| 部分 | 小白理解 | 主要产出 | 演示时看哪里 |
| --- | --- | --- | --- |
| A1 | 记录“运行录像” | RunResult、CaseResult、Observation、Trace、Tool Call | Runs、Case、Trace Timeline |
| A2 | 像裁判一样打分 | Scenario、Judge、GradeResult、score、pass/fail、failure class、release policy | Review、Case 中的评分与失败分析 |
| A3 | 给人使用的控制台 | Run/Case 浏览、问题分诊、人工审核、报告、发布门禁、审计证据 | Overview、Review、Reports、Delivery |

边界一定要说清楚：A3 只展示和组织 A1/A2 的结论，不重新计算 A2 的分数、通过/失败或失败分类。

## 3. 本次汇报应该演示什么

不要试图把仓库里的每个测试文件都点一遍。老师最需要看到的是一条闭环：

1. A1 跑出一次 Agent Run，并留下完整 Trace。
2. A2 对同一批案例进行 Judge，给出分数和失败原因。
3. A3 把这些数据放进页面，让人能定位问题、查看证据、生成报告。
4. 发布门禁发现风险时会阻止发布，而不是把失败改成成功。

推荐演示入口是 `a3-golden-path`，对应材料：

- `fixtures/a3/golden-path/a3_new_run_result.redacted.json`
- `fixtures/a3/golden-path/a2_new_run_judge_response.redacted.json`
- `fixtures/a3/golden-path/golden-path-status.json`
- `docs/a3/a3_release_delivery_golden_path_2026_07_12.md`

这个例子的事实是：A1 执行 3 个案例且 Trace 完整率 100%；A2 判定 1 个通过、2 个失败；A3 完成审计包和报告，但最终状态是 `blocked_by_a2`。这正好能展示系统的安全原则。

## 4. 演示前准备

### 4.1 使用哪个目录

从仓库根目录运行命令：

```text
C:\Users\yang\Documents\Agent\2026-07-02\i-am-a-beginner-explain-releasefoundry\releasefoundry-m40-07-no-go-worktree
```

汇报前先确保使用最新的 `main`，并且工作区没有未保存的修改。不要在演示机上打印或复制任何 API key、cookie、token 或 `.env.local`。

### 4.2 安装和确定性检查

PowerShell：

```powershell
npm ci
npm ci --prefix apps/webapp
python -m pip install -r requirements-ci.txt

# A1：确认本地 Runner/SDK 可以运行
python scripts/a1_fresh_setup_smoke.py

# A2：确认场景和评分 fixture 可重复生成
python scripts/a2_regenerate_fixtures.py --check

# A3：确认 Release Artifact 清单
node services/report/a3_release_delivery_cli.mjs `
  --verify-manifest fixtures/a3/golden-path/rc2/release-artifact-manifest.json `
  --verified-at 2026-07-12T14:02:06.000Z `
  --strict-exit `
  --json
```

上面任何一步失败时，不要临时修改数据。把错误截图保存下来，改用下方的静态演示和已经通过检查的截图，并在汇报中说明“这是环境问题，不是把结果伪造成通过”。

### 4.3 启动最稳妥的产品页面

先生成 Next.js 静态产品页面：

```powershell
npm run build --prefix apps/webapp
```

然后在仓库根目录启动静态服务器：

```powershell
python -m http.server 5173
```

浏览器打开：

```text
http://127.0.0.1:5173/apps/webapp/out/delivery/?source=a3-golden-path
```

这是汇报的主页面。其他常用页面只需把路径中的 `delivery` 换成：

| 页面 | 地址尾部 | 主要用途 |
| --- | --- | --- |
| 总览 | `/overview/` | 看整体健康度和入口 |
| 项目 | `/projects/` | 看项目与数据集边界 |
| 运行 | `/runs/` | 看一批运行和案例状态 |
| 案例 | `/case/` | 看单个案例的证据细节 |
| 审核 | `/review/` | 看失败、媒体证据和人工处理 |
| 报告 | `/reports/` | 看报告和分享/导出 |
| 发布 | `/delivery/?source=a3-golden-path` | 看 Golden Path 和发布门禁 |
| API 文档 | `/api-reference/` | 看产品对外 API 形状 |
| 团队 | `/team/` | 看成员、角色和团队边界 |
| 计费 | `/billing/` | 看 usage/billing 的产品形状 |
| 信任 | `/trust/` | 看审计、隔离和安全姿态 |
| 登录 | `/login/` | 看登录和邮箱验证的产品入口 |

实际完整地址前都加上：`http://127.0.0.1:5173/apps/webapp/out`。

## 5. 推荐的 8 分钟现场顺序

### 第 0 分钟：先说产品目的

可以直接照着说：

> 我们做的不是一个只显示分数的聊天页面，而是 Agent 的发布前质量控制台。A1 记录执行事实，A2 对事实做独立评测，A3 把证据、失败原因和发布决策交给团队审核。

### 第 1 分钟：Overview（总览）

打开 `/overview/`，只讲四类信号：

- 有多少次 Run、多少个 Case；
- 通过率和平均分；
- Trace 是否完整；
- 当前发布是否被阻塞。

不要逐字朗读页面上所有卡片。指出页面上的“数据来源”和“当前状态”即可。

### 第 2 分钟：Runs（运行列表）展示 A1

打开 `/runs/`，挑一个 `a3-golden-20260712-001` 运行。

讲解：

- **Run**：一次批量测试；
- **Case**：其中一个具体任务；
- A1 记录运行状态、案例数量和 Trace 完整率；
- “A1 执行完成”只代表程序跑完，不代表回答正确。

可用的一句话：

> 这里的 100% Trace 是“录像完整”，不是“考试 100 分”。正确性由 A2 再判断。

### 第 3 分钟：Case（案例详情）展示 A1 到 A2 的交接

打开 `/case/`，重点找这几个区域：

- Expected：原本希望 Agent 做什么；
- Actual：Agent 实际回复了什么；
- Tool Calls：调用了哪些工具、参数是什么、结果是什么；
- Trace Timeline：按时间顺序发生了哪些事件；
- Score / Pass / Failure Class：A2 的裁判结论。

解释工具调用时可以用电商退款例子：

> 用户说“订单 123 需要退款”。Agent 先调用 `order.lookup` 查订单，再调用 `refund.check_policy` 检查规则，最后回复能否退款。A1 把每一步记录下来；如果它漏掉了必须的检查工具，A2 就会把它判为 `missing_required_tool`。

### 第 4 分钟：Review（审核队列）展示 A2

打开 `/review/`，用当前 Golden Path 的三个案例说明：

| 案例 | A2 结论 | 分数 | 解释 |
| --- | --- | ---: | --- |
| direct answer | pass | 100 | 符合预期 |
| required web tool | fail | 71 | 缺少必需工具调用 |
| media pipeline | fail | 71 | 媒体流程缺少必需工具调用 |

重点说：

> A2 是裁判，不是 A3。A3 只是把 A2 的裁决展示出来，不能为了让页面好看而改分数。

如果页面有媒体证据区域，可以展示媒体类型、证据哈希、授权状态和审核状态；不要把私有媒体 URL 或真实账号信息投到屏幕上。

### 第 5 分钟：Failure Cluster（失败聚类）展示分诊价值

在 Case/Review 页面找到失败分类或过滤器，展示 `missing_required_tool` 聚在一起。

可以这样解释：

> 如果 30 个失败案例逐个看，定位会很慢。A3 按 A2 给出的 failure class 聚类，把同一种问题放在一起，工程师可以先修一类问题，再重新跑回归。

### 第 6 分钟：Reports（报告）展示可审计输出

打开 `/reports/`，演示 JSON、Markdown 或 CSV 导出中的任意一种。报告应包含：

- Run/Case 标识；
- Expected / Actual；
- Trace 和 Tool Call 摘要；
- A2 score、pass/fail、failure class；
- 媒体证据的脱敏元数据；
- 发布门禁和审计信息。

不要把报告说成“已经部署到云端”。当前演示重点是报告链路和证据可追溯。

### 第 7 分钟：Delivery（发布门禁）展示 fail-closed

回到 `/delivery/?source=a3-golden-path`，展示 11 个 Golden Path 阶段和当前阻塞项。

要点：

- A1 新 Run：通过；
- A2 评测：已执行，但 Trusted Spine 因失败案例阻塞发布；
- A3 Audit Bundle、签名归档和 Release Artifact：可以验证；
- 真实 staging/VPC 部署、租户 GitHub App 和 main 强制检查：尚未证明；
- 所以最终不是 `production_ready=true`，而是 `blocked_by_a2`。

最后一句可以这样说：

> 系统宁可明确告诉我们“现在不能发布”，也不会把证据不足的候选版本标成生产可用。

## 6. A1、A2、A3 的术语速记

| 术语 | 最简单的比喻 | 汇报时怎么说 |
| --- | --- | --- |
| Agent | 做题的人 | 接收任务并决定是否调用工具 |
| Scenario | 考题和规则 | 规定输入、期望行为和工具要求 |
| Run | 一次考试 | 一批案例被执行的过程 |
| Case | 一道题 | 一个具体任务 |
| Observation | 观察到的一步 | 一次输入、输出或环境事件 |
| Trace | 整段录像 | 按顺序保存的运行事件 |
| Tool Call | 考生按了一次工具按钮 | 工具名、参数、调用结果和状态 |
| Expected | 标准答案/要求 | 预期回复、工具顺序和安全规则 |
| Actual | 实际答卷 | Agent 的真实回复和真实工具行为 |
| Judge | 裁判 | A2 根据规则检查 Actual |
| Score | 分数 | 对该 Case 的质量量化 |
| Pass/Fail | 通过/失败 | 是否满足该 Scenario 的要求 |
| Failure Class | 错误归类 | 例如缺工具、输出不完整、Trace 损坏 |
| Release Gate | 发布闸门 | 证据不满足就阻止发布 |
| Audit Bundle | 证据文件夹 | 让别人能检查这次决定依据什么 |

## 7. 哪些功能必须演示，哪些只在被问到时展示

### 必须演示

- Overview：产品总览；
- Runs：A1 运行记录；
- Case：Expected/Actual、Tool Call、Trace；
- Review：A2 分数、通过/失败、失败分类；
- Reports：导出报告；
- Delivery：Golden Path、Audit Bundle、Release Gate 和阻塞原因。

### 被老师追问时再展示

- `API Reference`：说明未来如何被 SDK/其他系统接入；
- `Team` / `Trust`：说明企业团队、权限、审计、租户隔离的产品方向；
- `Billing`：说明 usage/billing 的数据形状；
- `Login`：说明登录、邮箱验证码和身份边界；
- `Review` 的媒体页面：说明图片、音频、文件、视频证据如何只保留安全元数据。

不要为了“展示功能多”而快速点完所有页面。页面多不等于闭环完整，闭环才是重点。

## 8. 现场必须诚实标注的状态

当前 Golden Path 是一个可验证的本地 Release Candidate 演示包，不是生产发布证明。以下内容不能说成已经完成：

- 真实客户租户绑定的 GitHub App 安装身份；
- `main` 分支保护一定强制执行；
- 企业 staging/VPC 中的真实部署、数据库迁移、网络和租户隔离回执；
- 生产升级、故障演练、回滚和恢复；
- A2 当前被阻塞时的 `production_ready=true`。

这样回答不会减分，反而能说明团队理解“测试通过”和“生产可用”的区别。

## 9. 常见现场问题的回答

**问：A1 通过了，为什么最后还是不能发布？**
答：A1 只证明运行完成并留下了完整事实；A2 发现两个案例缺少必需工具调用，所以发布策略仍然阻塞。

**问：A3 为什么不自己重新打分？**
答：为了保持职责隔离。A2 是唯一的评测权威，A3 只能展示、审核和打包，不能偷偷改变上游语义。

**问：这些是真实 ReleaseFoundry 云端数据吗？**
答：本次主演示使用仓库里的脱敏、确定性 fixture；它用于证明产品链路。真实 ReleaseFoundry API 校准数据另有记录，不能把两者混为一谈。

**问：为什么要保存 Trace 和 Tool Call？**
答：只看最终文字无法知道 Agent 有没有查数据、有没有越权或漏掉必要步骤；Trace 是可复盘的事实证据。

**问：你们的产品最终是什么？**
答：企业在发布 Agent 前，用它来运行测试、评测质量、定位失败、人工审核、留存审计证据，并决定是否允许发布。

## 10. 演示前一晚的清单

- [ ] 在最新 `main` 上确认页面能打开。
- [ ] A1 smoke、A2 fixture check、A3 manifest verification 都通过。
- [ ] 提前打开 `/delivery/?source=a3-golden-path`，确认能看到 `blocked_by_a2` 和 11 个阶段。
- [ ] 提前打开 `/runs/`、`/case/`、`/review/`、`/reports/`，确认浏览器没有登录跳转或空白页。
- [ ] 准备一张截图或录屏作为网络/服务器故障备用材料。
- [ ] 关闭包含 API key、`.env.local`、真实邮箱、cookie 的窗口和终端。
- [ ] 只记住四句话：A1 记录事实；A2 做评测；A3 做产品工作流；证据不足就阻止发布。

## 11. 可以放在汇报最后的一页

```text
A1：这次运行实际发生了什么？
A2：这些行为是否符合场景和质量规则？
A3：团队如何查看证据、处理失败并决定发布？

结论：我们已经把“运行 -> 评测 -> 分诊 -> 报告 -> 发布门禁”串成可重复的 Demo，
并且明确区分了本地验证与生产就绪，避免把没有证据的能力误报为已完成。
```
