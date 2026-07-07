# P3 / A3 当前状态交接说明

## 一句话结论

A3 已经完成了真实 Ashr API 字段校准、失败 run 校准、Dashboard/Triage/Report 的本地复现、前端顶层页面观察、API 与前端可见性差异说明、signed media URL 覆盖审计。

现在剩下的不是 A3 本地功能没做，而是还需要外部证据：

1. 重新登录 Ashr 前端，并拿到一个 UI 里可见的 populated run。
2. 拿到 audio / image / video 的 signed URL 样本。

## 我们这个项目在做什么

我们是在复现 Ashr 的核心产品逻辑。

Ashr 的核心不是普通网页，而是一个用来测试 AI agent 的平台。它会让一个 agent 跑很多 scenario，然后记录：

- 这个 agent 做了什么
- 每个 case 期望它做什么
- 实际它做了什么
- 有没有调用工具
- 工具调用对不对
- 最后回答对不对
- 分数是多少
- pass 还是 fail
- 如果 fail，应该归到什么 failure class
- 最后能不能生成 report 给人看

A3 负责的是 Dashboard / Triage / Report。

也就是说，A3 不负责 agent 怎么跑，也不负责 judge 怎么打分。A3 负责把 A1/A2/真实 Ashr 产出的数据变成一个能看的产品控制台。

## A3 已经做了什么

### 1. Dashboard 基础功能

A3 dashboard 已经能展示：

- Run List
- Case Detail
- Expected vs Actual
- Trace Timeline
- Tool Call Diff
- Failure Cluster
- Triage Queue
- Media Evidence
- Request Provenance
- Coverage Health
- Report Center
- JSON / CSV / Markdown / Print-PDF export

### 2. 真实 Ashr API 校准

我们已经安全使用 `.env.local` 里的 `ASHR_API_KEY` 做过只读校准。

确认可以拿到：

- datasets
- runs
- requests
- run detail
- request detail
- failed run detail
- dataset detail

重要证据文件在：

- `fixtures/a3/p3/ashr_frontend_api_objects.redacted.json`
- `fixtures/a3/p3/ashr_run_trace_sample.redacted.json`
- `fixtures/a3/p3/ashr_failed_run_detail.redacted.json`
- `fixtures/a3/p3/ashr_failed_request_detail.redacted.json`
- `fixtures/a3/p3/ashr_dataset_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_run_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_request_probe_after_frontend_empty.redacted.json`

这些都是 redacted 文件，不包含真实 key。

### 3. 真实 failed run 校准

我们找到了一个真实 failed run。

确认字段包括：

- `run.result.status`
- `run.result.cases[]`
- `cases[].status`
- `cases[].grade.passed`
- `cases[].grade.score`
- `cases[].grade.reason`
- `cases[].grade.metrics`

结论：

真实 Ashr failed run 里有 grade / score / reason / metrics，但是当前样本没有看到一个直接叫 `failure_class` 的字段。

所以 A3 现在的做法是正确的：用 grade metrics、expected vs actual、tool evidence 推导 failure class。

### 4. 真实 Ashr 前端观察

我们通过 Chrome/CDP 观察过真实 Ashr Lab 的顶层页面。

确认过这些 tab：

- Datasets
- Agents
- Folders
- Analytics
- Usage
- Trust
- API Keys
- Team

也确认过 New Dataset 是 8 步 wizard：

- Basic Info
- Agent
- Inputs
- Tools
- Context
- Test Config
- Behaviors
- Review

但是当前前端还有两个限制：

- 前端 UI 里没有显示 populated run / case detail。
- 后来 Chrome 登录 session 过期了，前端请求返回 `401`。

所以如果还要继续观察真实前端 detail 页面，需要重新手动登录。

### 5. API 和前端不一致的问题

我们已经证明：

- API 能看到 3 个 datasets、2 个 runs、5 个 requests。
- 前端 Datasets / Analytics 当时显示 0。

这说明现在的问题不是 API 没数据，而是前端可见性问题。

可能原因包括：

- 前端 filter
- workspace / repo scope
- API calibration object 和 Lab UI object 不完全共用展示层
- 浏览器 session 过期

我们没有猜隐藏路由，也没有乱造结论。

文档在：

- `docs/a3/p3_api_frontend_visibility_gap.md`

### 6. signed media URL 审计

我们扫描了 18 个 redacted P3 fixture。

结论：

- 找到 2 个 `signed_url`
- 都是 file-like action
- 没有确认 audio signed URL
- 没有确认 image signed URL
- 没有确认 video signed URL

所以 A3 现在不应该渲染真实 signed media link。

正确做法是：

- 可以展示 redacted metadata
- 可以展示 media type、action tags、output_path、audio tags、VM stream
- 不能展示 live signed link

文档在：

- `docs/a3/p3_signed_media_url_coverage.md`

## 组长问我时可以怎么说

可以这样回答：

我们 A3 这边已经完成了本地 Dashboard/Triage/Report 的主要逻辑，也完成了真实 Ashr API 的字段校准。真实 API 里 datasets、runs、requests、failed run、request detail 都能拿到，并且都保存成 redacted fixture 了。

我们还验证了一个真实 failed run。这个 failed run 有 score、passed、reason、metrics，但是没有看到原生 `failure_class` 字段，所以 A3 现在继续用 metrics 和 expected-vs-actual 推导 failure class。

前端方面，我们已经观察过 Ashr Lab 的顶层页面和 New Dataset 的 8 步流程。但是现在还没有观察到 populated run detail / case detail，因为前端 UI 没显示这些对象，而且后面 Chrome session 过期了，前端请求返回 401。要继续看真实前端 detail，需要重新登录，并且最好有一个 UI 里可见的 run。

signed media URL 方面，我们只确认了 file 类型的 `signed_url`，audio/image/video 还没有样本，所以 A3 暂时不渲染 live signed link，只保留 redacted metadata。

## 当前剩余事项

真正剩下的只有外部证据项：

1. 重新登录 Ashr 前端。
2. 找到或创建一个 UI 里可见的 populated run。
3. 观察 run detail / case detail / trace timeline / expected vs actual 的真实前端页面。
4. 拿到 audio / image / video signed URL 的 redacted 样本。

下一次重新登录后，按照这个清单观察：

- `docs/a3/p3_frontend_relogin_observation_checklist.md`

## 现在不建议继续做什么

不建议继续盲目扩 A3 功能。

现在 A3 本地功能已经够完整，继续堆功能容易偏题。更有价值的是等真实前端重新登录和更多真实样本，然后补证据。

不建议做：

- API key 管理页面
- Team 管理页面
- Billing / Upgrade
- Trust public publishing
- 完整 New Dataset 8 步创建器
- live signed URL 渲染

这些都不是学生 MVP 的核心。

## 验证状态

最近一次 A3 测试：

```text
tests 33
pass 33
fail 0
```

安全状态：

- `.env.local` 被 git ignore
- 没有提交真实 key
- 没有保存 cookie
- 没有保存 token
- 没有保存真实账号信息
- 所有真实 Ashr 样本都以 redacted fixture 保存
