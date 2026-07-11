# A3 Signal/Form 双版本视觉重构与中英双语

日期：2026-07-11

## 这轮做了什么

这轮没有破坏性删除已经通过测试的 A3 产品逻辑，而是在同一套 A1/A2
数据、DOM id、API client、report builder 和交互组件上提供两套完全隔离的
视觉实现：

- 方案 A：`Release Intelligence`，保留上一轮黑白、紧凑、发布治理风格。
- 方案 B：`Signal/Form Operations`，使用纸张色、黑色和少量 ember 橙，强调
  12 栏网格、编号章节、密集信息与不对称排版。
- 对比页：同时加载 A 和 B，并支持并排、只看 A、只看 B。

这样做的原因是用户需要看到两版差异。如果直接删除 A，就无法客观比较，
也会失去已经通过 A1/A2 和浏览器回归的稳定基线。

## 打开方式

本地静态服务启动后：

- A：`/apps/dashboard/index.html?source=api-mock`
- B：`/apps/dashboard/index.html?source=api-mock&design=signal-form`
- A/B 对比：`/apps/dashboard/design-compare.html`

`design=signal-form` 只切换 CSS，不切换数据和业务逻辑。缺少该参数时始终回到
方案 A，因此旧链接和旧测试的默认行为不变。

## A 与 B 的区别

| 维度 | 方案 A | 方案 B |
|---|---|---|
| 视觉定位 | 发布治理与审计控制台 | 信号分析与运营工作台 |
| 主色 | 黑、白、冷灰 | 纸张色、黑、ember 橙、moss 绿 |
| 首屏 | 大留白、线性结构 | 不对称 masthead、程序化纹理、12 栏网格 |
| 信息密度 | 稳健、相对舒展 | 更紧凑，运行指标与产品入口更容易扫描 |
| 导航 | 六个折叠产品域 | 同样六个产品域，使用编号和橙色活动信号 |
| 数据逻辑 | A1/A2 API-backed 数据 | 与 A 完全相同 |
| 推荐用途 | 稳定基线与回退方案 | 下一轮产品视觉候选 |

## 中文优先与中英双语

两套方案共享 `apps/dashboard/src/i18n.js`：

- 第一次打开默认中文。
- 右上角 `中文 / EN` 分段控件可即时切换。
- 语言选择写入 `localStorage`，刷新后保持。
- URL 同步 `lang=zh-CN` 或 `lang=en`，不会丢失 `source` 和 `design`。
- MutationObserver 会翻译后续由 A3 组件动态插入的界面文案。
- JSON、run id、case id、trace、tool-call 参数、score、failure class 原始值不翻译，
  防止破坏 A1/A2 契约和审计证据。

已覆盖的核心中文界面包括总览、评测、审核、报告、管理、信任与合规、运行列表、
案例详情、预期与实际、Trace 时间线、失败聚类、媒体、登录/团队、用量/配额、
API 密钥、计费、云端管理和发布证据。

## Signal/Form 来源与边界

输入文件是项目团队提供的 `signal-form-pattern-library-v1.0.zip`。

- SHA-256：`88832F6A8DB6D5C3307A27BBA808B5A0322D6871CE50E53AD03823F896DF1D6B`
- 上游代码许可：MIT，Copyright (c) 2026 Signal/Form contributors。
- 上游 `public/assets/` 程序化位图许可：CC0 1.0。
- A3 只复用了高层设计令牌、网格原则和一张 CC0 程序化 `polar.png`。
- A3 没有复制 112 个 pattern catalog，也没有引入上游运行时代码、外部网络调用、
  品牌素材或第三方账号数据。
- 位图来源记录在 `apps/dashboard/assets/signal-form/SOURCE.md`。

方案 B 的 CSS 是围绕当前 A3 DOM 和产品语义独立编写的，不 `@import` 方案 A 的
`styles.css`。这保证两版可以真正比较，而不是在 A 上叠一层颜色覆盖。

## A1/A2 对接不变

两版都读取相同的 32 个 API-backed A1/A2 案例，并显示同一个 Evidence Spine：

1. A1 负责 RunResult、Observation、Trace 和 ToolCall。
2. A2 负责 GradeResult、score、pass/fail、failure class 和 release gate。
3. A3 只负责展示、分诊、审核、报告和审计，不重新计算 A2 判定。

本轮只修改 A3 owned directories，没有修改 A1 runner 或 A2 judge 语义。

## 浏览器证据

- `docs/screenshots/a3-design-a-release-intelligence.png`
- `docs/screenshots/a3-design-b-signal-form.png`
- `docs/screenshots/a3-design-b-signal-form-mobile.png`
- `docs/screenshots/a3-design-compare.png`

专项 Playwright 验证覆盖：

- A 默认加载 `styles.css`，B 只加载 `signal-form.css`。
- A 和 B 都显示 32 个案例和 A1/A2/A3 Evidence Spine。
- B 的 ember accent 解析为 `rgb(240, 77, 47)`。
- B 无 CSS gradient、非零 letter spacing 或大于 8 px 的圆角。
- 390 x 844 下无页面级横向溢出，标题、导航、数据源和导出控件均在边界内。
- 中文默认、英文切换、刷新保持和 URL 参数保持均通过。
- 对比页双 iframe 和三个显示模式均通过。

最终回归结果：

- A3 全量 Node：`325 pass / 0 fail`。
- 全量 Playwright：`25 pass / 0 fail`。
- A1/A2 聚焦兼容：`157 pass / 0 fail`，`987 subtests pass`。
- Commercial CL guard：0 blocker，0 advisory。
- Hygiene CL guard：0 finding。
- `polar.png`：`1200 x 800`，24 x 24 网格抽样得到 142 种颜色，非空白图。
- `git diff --check`：通过，仅有仓库已有 CRLF/LF 提示。

## 当前建议

优先把方案 B 作为下一轮演示候选，同时保留方案 A 作为稳定基线。方案 B 已经适合
学生项目演示，但 A3 仍是很高的单页控制台；后续应按总计划迁移为 React/Next.js
路由级页面，而不是继续向一个 HTML 页面里堆更多模块。
