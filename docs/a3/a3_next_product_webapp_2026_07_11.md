# A3 Next.js 多页面产品控制台

日期：2026-07-11

## 1. 这轮解决了什么

旧的 apps/dashboard 是一个功能完整的证据检查器，但所有内容集中在一个超长页面中。它适合开发者核对字段，不适合真实用户按工作流程操作。

这轮新增 apps/webapp，把产品拆成可独立访问的页面：

    登录 -> 总览 -> 项目 -> Runs -> Case Detail -> Review -> Reports -> Team / Billing / Trust

旧 dashboard 没有删除。它继续作为完整证据检查器和兼容基线；新 webapp 是面向产品操作的主线。

## 2. 技术边界

| 项目 | 选择 |
|---|---|
| Lane | A3 Product Console / Review Workflow / Report Center / Commercial UI |
| 语言 | TypeScript |
| 框架 | React 19 + Next.js 16 |
| 图标 | lucide-react |
| 样式 | 本地 Signal/Form 设计系统 + PostCSS/Tailwind 工具链 |
| 数据 | GET /api/a3/dashboard |
| 构建 | Next.js static export |
| E2E | Playwright TypeScript |

这轮没有修改 A1 runner，也没有修改 A2 judge 或 release-gate 语义。

## 3. 页面清单

| 路由 | 主要用途 | 关键数据 |
|---|---|---|
| /login/ | 只读演示身份入口 | 明确真实 auth 尚未接入 |
| /overview/ | 先看发布结论和风险 | A1/A2 evidence spine、pass rate、failure clusters |
| /projects/ | 查看组织、项目和接入状态 | product console、tenant scope、onboarding |
| /runs/ | 搜索、筛选和分页查看案例 | A1 RunResult + A2 GradeResult |
| /case/ | 对比 Expected / Actual | trace、tool calls、judge results |
| /review/ | 查看阻塞项和人工审核记录 | A2 release authority + A3 review workflow |
| /reports/ | 导出和查看报告制品 | report center、artifact registry |
| /team/ | 查看成员、RBAC 和 API Key 元数据 | SaaS admin console |
| /billing/ | 查看 usage、quota 和账单预览 | A1 usage ledger、billing readiness |
| /trust/ | 查看审计、信任制品和发布阻塞 | provenance、enterprise readiness |

所有页面默认中文，并支持切换英文。ID、trace、tool-call、failure class 和 A2 判定值保持原始值，不做翻译或重新计算。

## 4. A1 / A2 / A3 如何对接

    A1 RunResult / Trace / Tool Call
                  |
                  v
           A3 read-only adapter
                  ^
                  |
    A2 GradeResult / Failure / Release Gate

- A1 仍是运行、trace、observation 和 tool call 的事实来源。
- A2 仍是 score、pass/fail、failure class 和 release gate 的判定来源。
- A3 只负责规范化、关联和展示。
- 缺字段时页面显示 unknown、empty 或 blocked，不伪造成功值。
- review 页面不会绕过 A2 重新批准发布。

## 5. 视觉和信息层级

这轮针对“没有重点、下方像文字墙”的问题做了以下调整：

- 总览首屏把发布结论作为最强视觉信号。
- 页面标题、摘要和数据来源形成固定三级层级。
- 每个长章节增加编号，方便快速定位。
- 表头改为高对比深色锚点。
- 正文、表格和说明字号整体提高。
- Runs 每页显示 10 条，避免一次铺开 32 条。
- Expected / Actual 在 Case 页同屏对比，完整 JSON 放进折叠证据区。
- 页面切换有短入场动画，并支持 reduced-motion。
- 390 x 844 使用底部主导航，隐藏桌面侧栏。
- 无渐变、无负字距、圆角不超过 8 px。

## 6. 安全和商业写操作

当前登录页是只读演示入口，不会创建账号，也不会保存邮箱、密码或 session。

以下操作仍然禁用：

- 真实 approve / deny / waiver
- 创建或撤销托管报告
- 邀请成员和创建 API Key
- 真实套餐变更和微信支付 / 支付宝收款

它们必须等待 A1 提供 hosted auth、可信 session、RBAC、持久化 API、usage/audit 写入；A2 还需要验证当前 evidence 和 policy 状态。禁用按钮是 fail-closed 行为，不是遗漏。

## 7. 测试与 CI

本轮验证：

    npm run check --prefix apps/webapp
    node --test tests/a3/*.mjs
    npx playwright test
    python -B -m pytest tests/a1 tests/a2 tests/integration/test_a1_large_saas_migration.py -q -p no:cacheprovider
    npm audit --prefix apps/webapp --omit=dev

结果：

- Next.js typecheck + static export：通过，13 个静态页面生成成功。
- A3 Node：329 passed。
- Playwright：30 passed。
- A1/A2 Python：571 passed、5 skipped、1013 subtests passed。
- npm production audit：0 vulnerabilities。

CL Gate 新增 a3-webapp job，会在 GitHub 上重新安装依赖、typecheck、build，并运行 route-level Playwright。

## 8. 截图证据

- docs/screenshots/a3-webapp-overview-desktop.png
- docs/screenshots/a3-webapp-runs-desktop.png
- docs/screenshots/a3-webapp-case-detail-desktop.png
- docs/screenshots/a3-webapp-login-desktop.png
- docs/screenshots/a3-webapp-overview-mobile-390x844.png

截图只使用公开安全的 mock / redacted A1/A2 数据，不含 key、token、cookie、email 或真实账号信息。

## 9. 还没有声称完成的内容

- 真实注册、OAuth、SSO、微信登录和 session 生命周期。
- 真实多租户 Postgres、对象存储和云端部署。
- 真实 reviewer 写操作和 GitHub publish executor。
- 真实 hosted report URL、撤销、过期和审计后端。
- 真实微信支付、支付宝、发票和结算。

这些属于下一阶段的后端闭环，不应由前端假装已经完成。

## 10. Artifact / Bundle 影响

本轮新增页面源码、测试和公开安全截图，没有修改已封存 audit bundle 的输入 fixture、release decision 或签名记录，因此不触发已有 bundle reseal。若未来把这些截图纳入正式 evidence bundle，需要先注册为 screen_capture artifact，再重新封存。
