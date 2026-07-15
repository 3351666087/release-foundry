# 多模态发布校准接入 - Round 27

日期：2026-07-15

## 一句话结论

A3 已把最新 A2 Round 52 的公开安全多模态摘要和最新 A1 Round 68 身份边界接入产品控制台、报告和微信小程序。页面现在可以准确解释：10 个安全控制样本没有误报，但 5 个跨模态攻击只检出 3 个；本地高质量候选的结构化档位完成数为 0；重复结果的稳定性合格，但质量仍被阻断。因此稳定、低延迟或零安全误报都不能被解释为允许晋级或发布。

## 校准基线

- authoritative `origin/main`: `ccf6ce5`
- latest A1 peer: `566a13d`
- latest A2 peer: `850b39a`
- previous A3 head: `f085ad0`
- product strategy: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`
- Draft PR: `#35`

A1/A2 peer 分支都没有被 A3 合并。A3 只复制公开安全的聚合事实、哈希、状态和原因码，不复制 Provider endpoint、Secret、原始模型文本、身份 receipt、proof、cookie、token 或私有媒体。

## 最新 A1 对接事实

A1 `566a13d` 保留 Round 67 的 replay-retention 能力，并在 Round 68 补全授权凭据绑定回归：

- 完成 credential-link replay 的 30 天保留期限；
- lookup key 退役预检；
- 有界、幂等、带审计聚合回执的过期 replay 清理；
- PostgreSQL forced RLS、撤销直接表访问与固定 search path；
- 不返回 receipt digest、proof ciphertext、subject/email fingerprint 或 key material。
- 凭据绑定只能经过带近期会话、`credential_bind` step-up 和 mutation ticket 的授权包装器；
- 旧 direct binding function 与 receipt 表的直接 runtime mutation 保持拒绝；
- 失败回滚、并发唯一写入、精确 replay、跨 scope 拒绝和未消费授权保留均有 PostgreSQL 测试覆盖。

A3 当前只记录安全边界：

- `capability=authorized_credential_binding_regression`
- `a3_client_route_status=not_exposed_in_peer_evidence`
- `aggregate_readiness_available=false`
- `raw_identity_receipt_included=false`
- `production_identity_verified=false`

这意味着 A1 已有更强的身份安全运维原语，但 A3 登录页和微信小程序不能把它当作已上线身份 API。

## A2 Round 52 真实公开事实

### Cloud controls

| 指标 | 真实结果 |
|---|---:|
| eligible observations | 15 |
| specificity | 1.0 |
| sensitivity | 0.6 |
| balanced accuracy | 0.8 |
| median latency | 1.008s |
| p95 latency | 6.154s |
| qualification | blocked |

### 安全与攻击控制

- 安全 controls：10 个 eligible，0 个 false positive，安全样本门槛通过。
- `cross_modal_conflict`：5 个 eligible，检出 3 个，sensitivity `0.6`。
- policy minimum sensitivity：`0.8`。
- control-policy quality：`blocked`。

### 本地候选

- 模型：`qwen3-vl:8b`
- runtime promotion：`blocked`
- required structured profiles completed：`0`
- Warm 延迟改善不能覆盖 invalid structured output。

### Repeat、Review、Persistence 与 Candidate

- repeat quality：`blocked`
- repeat stability：`qualified`
- all repeats fresh：`true`
- promotion eligible：`false`
- human review：`pending`
- pending queue receipt：`1`
- same-round real PostgreSQL verified：`false`
- shared candidate verified：`false`
- candidate blocker：`7`

## 严格适配器

新增：

- `services/report/a3_multimodal_release_readiness.mjs`
- `fixtures/a3/p3/a2_multimodal_release_readiness_round52_850b39a.redacted.json`
- source：`p3-a2-round52`

适配器 fail closed 校验：

1. 每层 exact field allowlist；
2. SHA-256、Git alias、时间和安全 identifier；
3. cloud eligible count 与 controls case 数守恒；
4. sensitivity 必须等于 detected / eligible；
5. balanced accuracy 必须与 specificity/sensitivity 自洽；
6. safe-control pass 必须与样本数和 false-positive policy 自洽；
7. quality、stability、runtime promotion 和 blocker 必须对应；
8. pending review 必须保留 pending receipt；
9. PostgreSQL proof state 与 verified flag 必须一致；
10. shared candidate verified 与 blocker 必须一致；
11. A1 raw identity receipt 必须保持禁止；
12. URL、DSN、email、token、cookie、本地账号路径和 Secret 一律拒绝。

## Dashboard、报告与小程序

Dashboard 新增正式字段：

```text
multimodal_release_readiness
```

同一投影已进入：

- `/api/a3/dashboard?source=p3-a2-round52`
- Delivery 页面 `MultimodalReleaseReadinessPanel`
- JSON report
- Markdown report
- Hosted Report payload 与 HTML
- 微信小程序发布工作台
- OpenAPI `DashboardSnapshot`
- API Reference v16

客户界面不显示内部 lane badge。Web 和小程序使用“运行平台、评测服务、产品控制台、攻击检出、本地结构化输出”等产品术语。

## 日期漂移修复

完整回归在 2026-07-15 暴露一个既有时钟传播问题：审核 assignment 写入使用注入时钟，但 Dashboard 读取使用真实系统日期，导致固定测试租约在午夜后从 `claimed` 变成 `expired`。

修复：

- `dashboardSecurityContext` 把 `serverNow(options)` 传给 Store；
- `getDashboardSnapshot` 把 `requestOptions.now` 传给 Dashboard builder；
- 写入和读取现在共享同一个服务端时钟。

## 视觉证据

- `docs/screenshots/a3-webapp-multimodal-release-readiness-round52-desktop.png`
- `docs/screenshots/a3-webapp-multimodal-release-readiness-round52-mobile-390x844.png`
- `docs/screenshots/a3-wechat-workbench-mobile.png`

桌面与 390 x 844 页面无 document/body 横向溢出，标题、状态、指标和模型 ID 没有重叠。微信小程序保持四页信息架构、固定底部导航和客户术语。

## 验证

- focused Node/API/OpenAPI/report/WeChat：`137` passed, `0` failed
- full A3 Node：`519` passed, `0` failed, `1` explicit target-PostgreSQL opt-in skip
- current-main A2：`186/186` passed, `1050` subtests passed
- Next.js TypeScript：passed
- Next.js production build：passed, `15` static pages
- Playwright：`47/47` passed with one worker
- CL hygiene：`0` findings
- Commercial CL：`0` blockers, `0` advisories
- root/Webapp production dependency audit：`0` vulnerabilities
- `git diff --check`：passed

A2 peer 自己的 Round 52 worklog 报告 `661 passed, 1163 subtests passed`；A3 没有在自己的工作树中重新执行 peer 分支全套测试，因此该数字只作为上游声明，不升级为 A3 独立验证。A1 Round 68 worklog 报告原有 authority 回归已修复且完整 Python suite 为 `1394 passed, 2 skipped`；A3 同样只把它作为上游测试声明，不把 Docker/PostgreSQL 回归测试写成真实生产身份回执或客户端登录接口。

## 权威状态没有变化

- Golden Path：`7/11`
- Deployment Acceptance：`8/17`
- current authority：`integrity_invalid`
- current A2 decision：`unknown`
- historical A2 decision：`block`
- production receipts：`0`
- `production_ready=false`

## 下一步 Top 3

1. A2 修复攻击 sensitivity 和本地 structured output，并发布新的 qualified 或明确 blocked Decision Ledger。
2. A1/A2/A3 使用同一个 Candidate ID、Git SHA、run、grades、review hashes 和 artifact 重新绑定 Trusted Spine。
3. 获得真实 PostgreSQL、人工审核、tenant-bound GitHub App 和 staging/VPC 回执，再评估发布状态。
