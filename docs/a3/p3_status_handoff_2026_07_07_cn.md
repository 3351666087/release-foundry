# A3 P3 状态交接说明 - 2026-07-07

## 一句话结论

A3 现在已经不是“没有真实例子”。我们已经在真实 ReleaseFoundry 里有 dataset `884`，并且创建了一个更接近官方前端结构的真实 run `11926`。本地 A3 dashboard 已经能用这个 run 展示 5 个退款测试案例、2 个通过、3 个失败、40% 通过率、56.4 平均分、expected vs actual、tool-call 对比、媒体证据和报告导出。

## 今天解决了什么问题

之前的 run `11925` 是能从 API 拿到的，但它主要是我们本地 clone 的 `result.cases[]` 结构。后来我们发现官方 ReleaseFoundry 前端更像是在读 `result.tests[].action_results[]`。

所以今天重新做了一次更像官方前端的数据结构：

- dataset: `884`
- 新 run: `11926`
- 结构: `result.tests[].action_results[]`
- 测试数: 5
- pass: 2
- fail: 3
- pass rate: 40%
- average score: 56.4

这说明我们已经有一个“官方 API 可接受、前端 API 风格也能列出来”的真实结果。

## 做了哪些文件

新增或更新的关键证据：

- `fixtures/a3/p3/releasefoundry_dataset_884_demo_run_result.official_ui_tests.synthetic.json`
- `fixtures/a3/p3/releasefoundry_dataset_884_create_run_ui_tests_plan.redacted.json`
- `fixtures/a3/p3/releasefoundry_dataset_884_create_run_ui_tests_real.redacted.json`
- `fixtures/a3/p3/releasefoundry_dataset_884_run_11926_ui_tests_detail.redacted.json`
- `fixtures/a3/p3/releasefoundry_dataset_884_list_runs_ui_tests_after_create.redacted.json`
- `fixtures/a3/p3/releasefoundry_dataset_884_list_runs_summary_ui_tests_after_create.redacted.json`

更新的代码：

- `apps/dashboard/index.html`
- `services/report/report_builder.mjs`
- `tests/a3/p3_releasefoundry_mapper.test.mjs`
- `tests/a3/dashboard_wiring.test.mjs`
- `tests/a3/report_builder.test.mjs`

更新的文档：

- `docs/a3/p3_worklog.md`
- `docs/a3/worklog.md`
- `docs/a3/acceptance_checklist.md`
- `docs/a3/p3_field_mapping.md`
- `docs/a3/p3_api_frontend_visibility_gap.md`
- `docs/a3/p3_official_dashboard_gap_analysis.md`
- `docs/a3/p3_frontend_page_map.md`
- `docs/a3/p3_frontend_workflow_notes.md`
- `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- `docs/a3/p3_a3_mvp_recommendations.md`

## 怎么跟组长解释

可以这样说：

我们 A3 之前已经能展示本地 mock 和真实 API 样本，但官方前端 Results 一直看不到结果。今天我们发现原因可能是字段结构不一样：旧 run `11925` 用的是 `cases[]`，官方前端更像用 `tests[].action_results[]`。

所以我们创建了一个新的真实 ReleaseFoundry run `11926`，它使用官方前端更可能识别的 `tests[]` 结构。API 验证成功，`get_run(11926)` 能拿到 5 个测试，`list_runs(dataset_id=884, summary_only=true)` 也能列出 `11926`。这一步比之前更接近官方 Results 页面真正需要的数据。

本地 A3 dashboard 已经切换到 `11926`，能展示 5 个退款案例、2 pass、3 fail、expected vs actual、tool call diff、failure cluster、media evidence 和 report export。测试也全过了。

现在唯一还没确认的是：官方 ReleaseFoundry 网页 Results tab 视觉上会不会显示 `11926`。因为这次内置浏览器没有登录，只看到 sign-in 页面，所以还需要之后用已经登录的 ReleaseFoundry 浏览器刷新 dataset `884` 页面确认。

## 验证结果

测试命令：

```text
node --test tests/a3/p3_releasefoundry_mapper.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

结果：

```text
tests 41
pass 41
fail 0
```

本地 dashboard 验证：

```text
http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo
```

页面确认：

- run `11926`
- 5 cases
- 40% pass rate
- 56.4 average score
- 5 media-evidence cases

## 还差什么

只差一个外部视觉确认：

1. 用已经登录的 ReleaseFoundry 浏览器打开 `https://app.releasefoundry.example/?tab=analysis&dataset=884`
2. 进入 Results
3. 看 run `11926` 是否出现
4. 如果出现，再观察官方 run detail / case detail / expected vs actual / tool calls / trace UI

## 安全状态

- 没有打印 API key
- 没有提交 `.env.local`
- 没有保存 cookie/token/header
- 保存的真实 ReleaseFoundry 输出都是 redacted JSON
- 没有做删除、邀请、计费、发布、API key 管理等危险操作
