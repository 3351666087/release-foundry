# P3 Frontend Relogin Observation Checklist

## 目的

这份清单用于下一次重新登录 Ashr Lab 后继续观察真实前端 detail 页面。

当前状态是：

- 本地 `ASHR_API_KEY` 只读 API 校准可用。
- Chrome 里的 Ashr Lab session 已经过期，前端请求返回 `401`。
- A3 已经有 API 证据，但还缺 UI-visible populated run 的真实前端页面证据。

## 开始前必须满足

- 用户已经手动登录 Ashr Lab。
- 页面不是 sign-in 页面。
- 页面没有显示 `Your session has expired`。
- 不需要验证码或二次验证。
- 不需要 Codex 输入密码、验证码、API key、支付信息或邀请信息。
- 不需要创建、删除、提交、发布、邀请、升级、生成 key。

如果不满足这些条件，就停止，只记录原因。

## 安全规则

Codex 可以做：

- 只读观察页面结构。
- 只读记录 URL path。
- 只读记录页面模块和字段名。
- 只读记录网络请求路径和 HTTP status。
- 保存 redacted / sanitized 证据。

Codex 不可以做：

- 保存 cookie。
- 保存 token。
- 保存 raw authorization header。
- 保存真实 email、用户名、账号 ID。
- 保存真实 signed URL。
- 点击会创建、删除、提交、发布或邀请的按钮。
- 生成新的 API key。
- 提交 New Dataset wizard。
- 截图含有私人账号信息的页面。

## 优先观察顺序

1. Datasets / Analysis 页面
   - URL path
   - 是否有 dataset row
   - dataset row 展示字段
   - filter / sort / group 当前状态

2. Dataset detail
   - detail URL path
   - dataset name / type 字段名
   - scenario / case / action 列表字段
   - request provenance 是否出现
   - media/action metadata 是否出现

3. Runs / Run detail
   - run id 字段
   - status 字段
   - pass/fail 字段
   - score 字段
   - aggregate metrics 字段
   - case list 字段

4. Case detail
   - case id
   - scenario title
   - expected
   - actual
   - score
   - passed / failed
   - failure reason
   - failure class label 如果有

5. Trace / Timeline
   - trace event 名称
   - observation 名称
   - tool call 名称
   - tool arguments 是否展示
   - tool result 是否展示
   - 时间戳 / duration 是否展示

6. Expected vs Actual
   - expected response
   - actual response
   - expected tool calls
   - actual tool calls
   - diff / mismatch label

7. Media Evidence
   - audio / file / image / video 是否出现
   - output path 是否出现
   - signed URL 是否出现
   - 是否是 link、download、preview、proxy
   - 是否有 expiry / access 提示

8. Report / Export / Trust
   - 是否能从 run/case 进入 report
   - report 显示哪些 metrics
   - 是否有 public certificate / trust page
   - A3 MVP 是否应该复制

## 需要保存的证据

优先保存文档，不优先保存截图。

建议更新：

- `docs/a3/p3_frontend_page_map.md`
- `docs/a3/p3_frontend_workflow_notes.md`
- `docs/a3/p3_frontend_field_mapping.md`
- `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- `docs/a3/p3_worklog.md`
- `docs/a3/worklog.md`

如果拿到安全的 redacted API/前端样本，可以新增：

- `fixtures/a3/p3/ashr_frontend_run_detail.redacted.json`
- `fixtures/a3/p3/ashr_frontend_case_detail.redacted.json`
- `fixtures/a3/p3/ashr_frontend_trace_detail.redacted.json`
- `fixtures/a3/p3/ashr_frontend_media_detail.redacted.json`

如果截图安全，可以保存到：

- `docs/screenshots/ashr-frontend-redacted-run-detail.png`
- `docs/screenshots/ashr-frontend-redacted-case-detail.png`

如果截图包含账号、email、真实数据、token、key、signed URL，就不要保存截图。

## 观察完成后要回答的问题

1. 前端 run detail 的 URL path 是什么？
2. 前端 case detail 的 URL path 是什么？
3. 前端是否展示 expected vs actual？
4. 前端是否展示 tool calls？
5. 前端是否展示 trace/timeline？
6. 前端是否有原生 failure class？
7. 前端是否展示 signed media URL？
8. 哪些页面适合 A3 MVP 复制？
9. 哪些页面只适合记录，不适合学生 MVP？
10. 是否有任何安全风险？

## 停止条件

遇到以下情况就停止观察并记录：

- session expired
- 401 / 403
- captcha
- 二次验证
- 需要输入密码
- 需要创建或提交真实数据
- 页面显示真实 secret
- 页面显示不可打码的账号隐私

## 当前最小成功标准

下一轮前端观察最小成功标准不是“把所有页面都看完”。

最小成功标准是：

- 登录有效
- 找到一个 UI-visible populated run
- 观察 run detail
- 观察一个 case detail
- 记录 expected vs actual / trace / tool call / failure label 是否存在
- 保存 redacted 文档证据
