# 微信小程序企业发布助手

## 本轮结论

微信小程序已从两个英文静态页面升级为中文优先的四页产品切片：

1. **发布工作台**：查看当前候选版本、质量指标、证据链和待办。
2. **发布审批**：查看发布决策、证据阶段、阻断项和下一步，并执行权限 `preflight`。
3. **风险告警**：筛选风险案例，查看事件时间线、证据状态和处置建议。
4. **账户与连接**：诊断企业 API、身份、客户端安全和生产能力状态。

客户界面使用“执行证据、评测结论、发布决策、人工审批”等产品术语，不显示内部 A1/A2/A3 分工标志。内部 contract 仍保存来源信息，确保 A3 能继续消费 A1 RunResult、A1 Trace、A2 GradeResult 和 A2 ReleaseGate，而不改写上游语义。

## 两种运行模式

### `preview`

- 默认模式，使用 `apps/wechat-miniprogram/data/preview.js` 的明确演示数据。
- 页面会显示“演示数据”或“未连接企业环境”。
- 审批按钮只解释流程，不调用 API，不写入审批结果。
- 使用 `touristappid`，不宣称真实微信登录、支付、订阅消息或企业身份已上线。

### `connected`

- 通过微信小程序 `extConfig.apiBaseUrl` 接收企业 HTTPS API 地址。
- 地址必须是 HTTPS，不能包含用户名、密码、query、fragment 或非法端口。
- 客户端只允许访问白名单内的发布中心 API。
- 请求不嵌入 `Authorization` header，不持久化 token、cookie、API key 或 session。
- 服务器响应只要出现 secret、password、token、原始 key、签名 URL 或类似敏感材料，客户端就拒绝渲染。

## 页面与数据流

```text
运行平台的执行事实
        ↓
评测服务的评分与发布判定
        ↓
服务端脱敏产品投影
        ↓
工作台 → 审批 → 告警 → 账户诊断
```

A3 does not alter A1 runner semantics or A2 judge semantics。页面不根据通过率自行推导“可发布”，只读取服务端发布决策；字段缺失、身份不可信、范围不一致或响应未脱敏时保持 fail closed。

## API Contract

当前小程序实际使用：

- `GET /api/a3/health`
- `GET /api/a3/dashboard?source=api-ingest`
- `GET /api/a3/releases/:releaseId/evidence-summary?version=2`
- `GET /api/a3/releases/:releaseId/readbacks`
- `POST /api/a3/ui-actions/preflight`

`preflight` 只检查动作、企业范围、角色和证据引用，不执行批准或拒绝。动作名与服务端保持一致：

- `reviewer.approve`
- `reviewer.deny`

请求可携带哈希化证据引用，但禁止携带原始运行内容、邮件、token、cookie、API key、Authorization header 和 signed URL。

## A1 / A2 对接

内部来源契约保留：

- A1 RunResult
- A1 Trace
- A1 ToolCall
- A1 Observation
- A2 GradeResult
- A2 ReleaseGate
- A2 FailureTaxonomy
- A2 DecisionLedger

客户页面映射为：

| 内部来源 | 客户界面 |
|---|---|
| 运行、Trace、Tool Call | 执行证据 |
| Grade、Judge、Failure | 评测结论 |
| ReleaseGate、DecisionLedger | 发布决策 |
| Review workflow | 人工审批 |

服务端 `source_artifacts` 中合法的 SHA-256 会映射为审批预检的 `a1` / `a2` evidence refs；缺少有效哈希时不伪造引用，预检保持阻断。

### 2026-07-15 最新 peer 校准

- A1 peer 已从 `f3071aa` 前进到 `566a13d`。Round 67 增加账号凭据回放的 30 天保留、旧 lookup key 退役预检与审计清理能力；Round 68 证明凭据绑定必须经过近期会话、step-up receipt 与 mutation ticket 保护的授权包装器。它仍没有提供小程序可调用的统一身份就绪路由，小程序继续显示“待服务端接入”，不读取原始 receipt、digest、proof 或 key material。
- A2 peer 已从 `7504680` 前进到 `850b39a`。Round 52 的公开安全摘要通过 `multimodal_release_readiness` 进入 Dashboard：安全样本 10 个、误报 0 个，攻击样本检出 3/5、灵敏度 0.6，本地候选结构化档位完成 0 个，repeat quality 为 blocked、stability 为 qualified，人审 pending、同轮 PostgreSQL proof blocked、shared candidate 未验证。
- 工作台把上述事实显示为“多模态晋级受阻”。稳定性合格不会覆盖质量阻断；小程序不重算 A2 决策，也不把 peer branch 证据提升为 main 或生产权威。

## 已实现状态

- 加载、ready、partial、empty、error 和 retry。
- 四页下拉刷新。
- 发布证据阶段和阻断项。
- 告警筛选、选中详情、时间线与处置建议。
- HTTPS URL 校验、API route allowlist、请求/响应敏感材料拒绝。
- 演示态与企业连接态的明确区分。
- 审批按钮只做服务端权限预检。
- 客户 WXML 不出现 A1/A2/A3 内部标志。
- Web 控制台的品牌入口、来源选择和主要页面改用企业职责名称。

## 仍未实现的生产能力

- 正式微信 AppID 和主体资质。
- 微信登录与企业身份会话闭环。
- 服务端真实批准、拒绝、豁免写入。
- 微信订阅消息。
- 微信支付或支付宝支付。
- 微信开发者工具真机编译、上传、审核和发布回执。

这些不是本轮伪装完成的内容。取得资质、正式 AppID、后端身份和目标环境后，才能进入生产验收。

## 验证

```text
node --test tests/a3/a3_wechat_mini_program_client_surface.test.mjs
npm.cmd run typecheck --prefix apps/webapp
npm.cmd run build --prefix apps/webapp
```

视觉预览使用独立静态预览和 390 x 844 Playwright 检查；它验证排版，不等同于微信开发者工具或真机发布证明。
