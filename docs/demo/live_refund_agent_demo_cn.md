# Docker 真实 Agent 退款演示

## 这条演示证明什么

这不是把一份预先写好的 JSON 换个名字展示。运行命令后会现场完成：

1. Docker 启动 Ollama 本地模型。
2. `OllamaRefundAgent` 通过 Python SDK 的 `ProviderNeutralModelAdapter` 调用模型。
3. 模型决定调用 `refund_order_sandbox`。
4. 沙盒工具只修改内存中的模拟订单，不连接真实订单、银行或付款系统。
5. A1 `run_agent_batch` 记录 RunResult、Observation、Tool Call 和 Trace 投影。
6. A2 `grade_run` 使用五个现有 Judge 对同一个 `run_id/case_id` 评分。
7. A3 Report Builder 导出 JSON、Markdown、CSV，并将 A1/A2 结果导入 Dashboard。

固定的 `refund-demo` 仍然保留。它用于现场网络、Docker 或模型下载失败时兜底；`live-refund-demo` 才是动态真实模型演示。

## 第一次运行

先打开 Docker Desktop，看到 Engine running 后，在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-live-refund-demo.ps1
```

第一次会下载 Ollama 镜像和 `qwen2.5:0.5b` 模型，耗时取决于网络。后续运行会复用 Docker volume 中的模型。

演示页面默认是：

```text
http://127.0.0.1:4175/apps/webapp/out/overview/?source=live-refund-demo
```

动态证据和报告保存在 `.demo-output/live-refund/`。该目录已被 Git 忽略。

## 汇报时怎么讲

先打开固定演示 `refund-demo`，说明 Expected 与 Actual 不一致时如何被阻断。然后运行一键命令，切换到 `live-refund-demo`：

1. 在 Runs 页面指出这是刚生成的新 `run_id`。
2. 在 Case Detail 中展示真实模型回复。
3. 在 Trace Timeline 中依次指出用户消息、工具调用、工具回执、Agent 回复。
4. 在 Judge 区域说明五个评分器来自 A2，A3 没有自行改分。
5. 在报告中展示同一运行导出的 JSON、Markdown、CSV 和本地 Hosted Report 回执。

## 安全边界

- 不读取或提交 API key。
- 不调用 Ashr 云 API。
- 不连接真实电商、订单、微信、支付宝或银行系统。
- 只有 `order_demo_123` 和 42 元被沙盒允许。
- 输出中明确记录 `external_payment_mutated=false`。
- 动态模型失败时如实生成失败 RunResult，不会伪造成功。
