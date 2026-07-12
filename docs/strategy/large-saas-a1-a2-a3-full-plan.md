# 企业级 Agent Release OS 总战略

> 本文是 A1、A2、A3 唯一的产品与工程战略总线。
> 首要交付形态：**部署到企业自有云、专有云或 VPC 的版本化 Release**

---

## 0. 战略转向

项目不再围绕 Ashr 官方 API 构建。

已确认的供应风险是：账号充值后仍显示免费额度，额度没有自动增加，且申诉流程无法为服务可用性提供确定保障。这个问题证明了一个根本风险：**付款成功、账户状态、可用额度和实际服务能力不能被假定为同一件事**。任何单一模型厂商的配额、计费、可用性或商业政策，都不能成为本项目的开发前提、CI 前提或企业交付前提。

因此立即确立以下原则：

1. Ashr 官方 API 降级为**可选校准 Provider**，不是必需依赖。
2. A2 必须支持 Ollama、vLLM、OpenAI-compatible API、客户自建模型端点和任意合规厂商。
3. 企业部署必须存在完全离线或无外部模型 API 的工作路径。
4. Provider 超时、限流、额度耗尽、付款状态异常都不能产生“通过”。
5. 平台必须拥有真实的模型后端、模型注册、路由、容量治理和回滚能力，不能停留在笔记本上的模型调用脚本。
6. 从系统设计起建立合规的数据闭环，为评测、回归、偏好学习和受治理的强化学习提供可追溯数据，但不得把“使用产品”等同于“同意训练”。

这不是缩小目标，而是把项目从单厂商依赖中解放出来，向真正可交付的企业产品靠近。

---

## 1. 产品终局

项目的终局不是网页复刻、Prompt 集合、模型 API 包装器或通用聊天应用，而是：

```text
Agent Release OS
```

它回答企业在 AI Agent 上线前后最关键的问题：

```text
如何接入运行事实？
如何保存证据与调用链？
如何评价正确性、安全性和业务风险？
如何让人工审核、例外审批和事故复盘进入同一条证据链？
如何阻断危险版本？
如何把真实使用反馈变成回归资产和受治理的学习数据？
如何在企业自己的云或 VPC 中安装、升级、回滚、恢复和审计？
```

最终商业交付不是“给客户一个仓库”，而是：

> 一套签名、版本化、可安装、可升级、可回滚、可恢复、可观测、可审计的企业 Release。

---

## 2. 能力基线与 Release 缺口

战略判断只以仓库中可执行代码、自动化测试、契约、迁移和部署资产为依据，不绑定易失的版本快照或分支状态。能力描述必须可由持续验证重复证明；一旦实现与描述不一致，以验证结果为准并收紧对外承诺。

### 已经真实具备

- A1：本地 Runner、Python/TypeScript SDK、Go ingress、Trace/Evidence、API Key/路由/配额/计费账本契约、PostgreSQL 切片、Queue/Worker/Dead Letter、本地对象存储、Compose/Terraform 自托管脚手架。
- A2：60 个 G3 场景、32 个 Golden Case、确定性 Judge、语义 Provider Gateway、校准、失败分类、回归重放、Release Policy/Gate、Evidence Snapshot、Decision Ledger、SQL 持久化契约、Ollama smoke。
- A3：Next.js 产品界面、Run/Case/Report/Reviewer/Admin 页面、商业 OpenAPI 契约、Hosted Report 生命周期、RBAC 元数据、Fail-closed 写路径规则、Event Outbox、通知控制面、GitHub Check/PR Comment dry-run、Waiver/Approval/Audit Bundle/Verifier/Artifact Registry。
- 基础设施：Docker Compose、运行时镜像、PostgreSQL migration、MinIO smoke、Worker recovery、支付对账 scheduler、Terraform 自托管模块。

### 尚未形成生产证明

- 没有正式 Git tag 和 GitHub Release。
- 没有客户环境中的生产部署证据。
- 没有完整的企业 SSO、SCIM、多租户强隔离和生产授权闭环。
- 没有经负载、故障、恢复验证的生产数据面。
- 没有完整的模型服务调度、GPU 容量治理和模型上线/回滚系统。
- 没有生产级多模态提取服务。
- 没有真实微信/支付宝商户收款闭环。
- 没有完整的安装、升级、回滚、备份、恢复和离线交付包。
- 没有成熟的 SLO、告警、值班、渗透测试和供应链签名体系。

### 状态术语

| 状态 | 准确定义 |
|---|---|
| 已实现 | 可执行代码存在，并且有对应测试。 |
| 契约支撑 | Schema、API、Fixture、Migration 或本地参考实现存在。 |
| 生产验证 | 已在类客户环境中部署、运维、压测、故障恢复并通过安全验证。 |

禁止把“契约支撑”写成“生产验证”，禁止把页面存在写成后端能力已经闭环。

---

## 3. 国内优先与企业交付原则

### 3.1 国内用户优先

产品默认考虑：

- 中文界面、文档、错误信息和运维手册；
- 中国大陆网络条件和镜像源；
- 国内云厂商与客户私有基础设施；
- 微信支付、支付宝和企业合同付款；
- 企业微信、钉钉、飞书、GitHub/GitLab 等集成；
- 数据驻留、审计、私有化和离线交付需求。

国内优先不等于绑定国内单一厂商。所有身份、支付、模型、对象存储、消息通知和云基础设施都必须经由 Adapter 或稳定契约接入。

### 3.2 主体资质约束

在项目主体不具备营业执照及对应平台资质的条件下，无法按正常商业路径申请并生产使用：

- 微信开放平台登录；
- QQ 互联登录；
- 支付宝登录；
- 微信支付商户；
- 支付宝商户收款。

这不是企业 Release 的阻塞项，因为私有化交付可以优先使用：

- 客户自己的 OIDC/SAML/LDAP/企业身份系统；
- 本地管理员初始化；
- 邮箱密码或密码无关登录；
- 服务账号和 Scoped API Key；
- 企业合同、人工开票/对账或客户自有支付系统。

但不得伪造微信、QQ、支付宝生产能力。资质就绪前只允许：

- 定义 Provider Contract；
- 提供 Sandbox/Mock Adapter；
- 编写回调、签名、幂等、对账和安全测试；
- 在取得主体、AppID、商户号和正式密钥后完成生产接入。

### 3.3 支付优先级

商业支付路线：

1. **企业私有化**：合同、采购、License、人工账单和客户内部结算优先。
2. **国内托管版**：微信支付、支付宝为主要在线支付方式。
3. **海外或特殊客户**：通过可插拔 Provider 支持 Stripe 或其他方式。

支付成功必须由服务端验签，并与订单、账单、权益和可用额度独立对账。任何支付 Provider 的异常都不得丢失客户数据、破坏审计记录或阻止合法数据导出。

---

## 4. 三条 Lane 的权责

| Lane | 定位 | 核心责任 |
|---|---|---|
| A1 | Platform / Runtime / Identity / Infra | SDK、执行接入、API、身份后端、租户、存储、队列、Worker、部署、观测、Usage、Billing Ledger |
| A2 | Evaluation / Learning / Policy | 多模态接入、标准化、提取、Provider、模型、Judge、校准、审核语义、回归、学习数据、Release Policy |
| A3 | Product / Workflow / Commercial UI | 产品控制台、审核、报告、发布工作流、管理后台、身份 UI、计费 UI、集成与客户体验 |

共同主键至少包括：

```text
organization_id
tenant_id
project_id
environment_id
actor_id
service_account_id
run_id
case_id
artifact_id
evidence_snapshot_id
decision_id
release_gate_id
request_id
trace_id
```

### 不可逾越的边界

- A1 运行成功不等于 A2 评测成功。
- A2 是评测语义和 Release Decision 的权威。
- A3 只能展示或请求 A2 决策，不能自行重算分数。
- 没有有效 Decision Ledger 记录，不得显示 Release Ready。
- 人工 Override 必须追加新记录，不能删除机器原始决策。

---

## 5. A1：执行、平台与企业基础设施

### 5.1 A1 的目标结构

```text
a1/
  sdk/                Python、TypeScript，并按明确客户需求扩展
  ingress/            API、Batch、Stream、Webhook、CI 接入
  runtime/            Agent/Skill 执行与本地/远程 Runner
  identity/           用户、身份绑定、会话、SSO、服务账号
  tenancy/            组织、项目、环境、RBAC/ABAC
  artifacts/          上传、校验、对象存储、保留与导出
  queue/              作业、重试、幂等、死信与恢复
  usage/              调用、Token、存储、模型和 Worker 计量
  billing/            订单、账单、权益、支付与对账
  audit/              不可抵赖操作记录与证据索引
  deploy/             Compose、Helm、Terraform、离线包
  observability/      Logs、Metrics、Traces、SLO、Alert
```

### 5.2 A1 可验证基础

- 已经有跨 Python/TypeScript/Go 的接入和运行骨架。
- 已经有 Trace/Evidence、本地 API facade、API Key、配额、Usage/Billing Ledger 契约。
- 已经有 PostgreSQL、Queue/Worker/Dead Letter、对象存储和自托管脚手架切片。
- 已经形成公开安全校准与较强测试纪律。

### 5.3 A1 Release 缺口

#### 身份与租户

- 密码、邮箱验证、找回、MFA、Session Revocation 仍未形成完整生产闭环。
- 同一用户绑定 GitHub、Google、Microsoft、企业 IdP 等多个身份的冲突处理和防接管流程不完整。
- 在主体资质不满足时无法生产接入微信、QQ、支付宝登录；必须保留 Adapter 边界但不得假装可用。
- OIDC/SAML、SCIM、服务账号、Workload Identity 和 Break-glass 管理未完成生产验证。
- RBAC 已存在大量契约和元数据，但尚需把授权落实到每条 API、DB Row/Object 和异步 Worker。

#### 数据面

- PostgreSQL 还不是所有核心路径的唯一权威存储。
- SQLite/内存/本地文件参考路径必须退出企业生产主链。
- 缺少完整的 Migration 兼容矩阵、PITR、备份恢复演练和灾难恢复指标。
- Queue 的多实例并发、消息去重、顺序、Backpressure、Poison Message 和跨版本恢复尚未充分验证。
- 对象存储缺少完整的租户隔离、保留、删除、Legal Hold、不可变策略和跨区域策略。

#### 执行与 SDK

- SDK 需要统一事件 Envelope、离线缓冲、断线续传、幂等、批处理、采样和 Backpressure。
- 调用记录必须同时覆盖平台使用和 SDK 使用，并区分运行遥测、计费事实、评测证据和学习许可。
- 需要真实的高并发、长任务、取消、超时、重试、资源配额和隔离验证。
- 需要明确支持 Agent、Skill、Tool、Model、Prompt、Build 和 Environment 版本。

#### 运维与交付

- Compose 和 Terraform 的定位仍是脚手架，不是完整企业安装器。
- 缺 Helm 生产参考、离线镜像包、预检、安装验证、升级、回滚和 Support Bundle。
- 缺完整 SLI/SLO、告警、容量规划、值班和事故 Runbook。
- 缺签名镜像、SBOM、Provenance、依赖/容器扫描和漏洞响应流程。

#### 商业系统

- Usage Event、账本、Quota、Entitlement、Invoice 和 Payment 之间还未形成严格对账闭环。
- 微信/支付宝商户接入受主体资质阻塞，资质就绪前只能完成契约、Sandbox 和安全测试。
- 企业 License、离线授权、续期、宽限期、撤销和数据导出政策需要实装。

### 5.4 A1 Release 验收

- 客户能在干净 VPC 安装并通过预检。
- 本地管理员或企业 IdP 能完成登录、组织初始化和服务账号创建。
- SDK 能在网络中断后安全续传并避免重复计量。
- Postgres、对象存储和队列在多实例下保持租户隔离和一致性。
- 备份、PITR、恢复、升级和回滚演练通过。
- 所有写路径有 Actor、Request、Trace 和 Audit。
- Usage、账单和 Entitlement 可重放、可对账、可解释。

---

## 6. A2：独立评测、学习与发布智能

### 6.1 A2 的目标结构

```text
a2/
  ingestion/          多模态输入、平台/SDK Trace、批量与流式接入
  normalization/      Evidence 标准化、校验、脱敏、分类和 Lineage
  extractors/         OCR、ASR、文档解析、压缩包、视频关键帧
  providers/          本地、云端、OpenAI-compatible、Ollama、vLLM、Ashr
  models/             模型注册、服务配置、路由、容量和生命周期
  judges/             规则、语义、安全、多模态和 Ensemble Judge
  calibration/        一致率、漂移、偏差、误报和漏报
  review/             人工审核、仲裁、Override、Waiver、双人审批
  regression/         Golden、事故重放、晋级和复发检测
  release/            Evidence 完整性、Policy 与 Release Gate
  learning/           数据集、偏好、Reward、训练编排和模型晋级
  persistence/        结果、历史、Ledger、Dataset 和 Retention
  api/                内外部服务契约与健康接口
  workers/            提取、Judge、Replay 和 Training Job
  observability/      质量、成本、容量、Trace 和 SLO
```

这些是稳定的职责边界，不要求先创建空目录。每个模块必须随可执行纵向切片、Schema、测试、持久化、观测和回滚一起进入主干。

### 6.2 A2 可验证基础

- 已有 60 场景、Golden Case、确定性 Judge 和失败分类。
- 已有校准、回归重放、Release Policy/Gate 和 Fail-closed 语义。
- 已有 Evidence Snapshot、Decision Ledger、Provider Gateway/Runtime、Model Registry 和 SQL Store 契约。
- 已有 Ollama smoke，Provider Independence 已具备起点。

### 6.3 A2 Release 缺口

#### Ingestion 与多模态

- 尚未形成生产级 Upload/Batch/Stream/SDK 统一接入。
- OCR、ASR、文档解析、压缩包隔离和视频关键帧仍缺完整 Worker 服务。
- 缺 Malware Scan、Decompression Bomb、Parser Sandbox、Prompt Injection 标签和提取完整性指标。
- Extractor 失败必须与 Agent 失败分离，仍需端到端证明。

#### Provider 与真实模型后端

- Ashr API 配额不可依赖，所有 CI 和 Release Gate 必须可在禁用 Ashr 时通过。
- Ollama 只能作为开发和小型部署后端，不能代表生产模型平台。
- 需要 vLLM 或等价高吞吐参考后端，以及客户自建 OpenAI-compatible Endpoint。
- 缺 GPU/CPU Profile、Scheduler、Admission Control、Warm Pool、Backpressure、Canary、Shadow、Drain 和 Rollback。
- 缺模型 Artifact 校验、许可证、Tokenizer、量化、硬件兼容、SBOM 和离线安装。

#### Judge 与 Calibration

- 语义 Judge 需要更多真实人工标注和 Holdout，而不只是 Fixture。
- 必须测量 Precision、Recall、误报、漏报、Abstain 质量和机器/人工一致率。
- 多 Judge 不能只按数量投票，必须分析 Provider、模型家族、Prompt Lineage 和失败相关性。
- 阈值变化必须作为版本化 Policy，先重放 Golden、事故和滚动窗口样本。

#### Review 与 Regression

- Reviewer 身份、资质、冲突、双人审批和 Override 质量控制尚未生产闭环。
- Override 不能自动成为 Gold Label。
- 事故进入 Regression 的晋级、数据许可、复现和责任人机制仍需完善。
- 客户私有 Regression Pack 和公共基准必须物理/逻辑隔离。

#### 学习与强化学习

- 在缺少训练、评估、晋级、回滚和安全证据时，不得宣称拥有 RLHF 或生产强化学习。
- 必须先收集有授权、有 Lineage 的修正、偏好、接受/拒绝、编辑、重试、比较和审核数据。
- 需要支持 SFT、Preference Dataset、Reward Model、DPO 等离线优化路线。
- 可通过 TRL-compatible Trainer、Ray 或其他受治理框架适配分布式训练，但不绑定单一框架。
- 在线 Bandit 或环境 RL 只能在安全、回滚、因果测量和 Reward Hacking 测试完成后启用。

#### Persistence

- PostgreSQL、对象存储和 Durable Queue 必须成为权威数据面。
- Dataset、Label、Checkpoint 和 Decision 必须不可变版本化并保留完整 Lineage。
- 跨租户训练默认禁止；企业私有学习必须能完全在客户 VPC 内进行。

### 6.4 设计内生的数据闭环

必须收集但必须分层治理：

```text
平台 UI/API 使用事件
SDK 调用、Trace、Tool Call、模型和 Provider 记录
延迟、重试、错误、Token、成本和容量
用户选择模型、接受、拒绝、编辑、重试、显式评分
Reviewer Label、分歧、Override、Waiver 和理由
Release Decision、上线后事故和回归结果
```

每条事件至少绑定：

```text
tenant/project/environment/user-or-service/session/run/request
source/schema_version/idempotency_key/causal_parent/integrity_hash
agent/skill/tool/model/provider/prompt/policy/build version
purpose/consent/data_class/residency/retention/deletion class
artifact reference，而不是不安全的私有内容内联
```

强制规则：

- 使用平台不等于授权训练。
- 运行遥测、计费事实、评测证据和学习数据必须分开。
- 跨租户聚合或训练必须有明确合同与授权。
- Secret、支付数据和禁止的 PII 不得进入 Evidence 或 Dataset。
- 企业能导出自己的 Evidence、Decision、Audit 和 Dataset。

### 6.5 A2 Release 验收

- 禁用 Ashr 后完整评测和 Release Gate 仍可运行。
- 同一评测包可在本地模型和云 Provider 上执行并保留可比 Provenance。
- Provider 宕机、额度耗尽和容量不足不会制造假 Pass。
- 至少一个多模态 Case 从接入到提取、Judge、Review、Decision、Regression 全链路可重放。
- 每个 Judge 版本有准确率、召回率、误报、漏报、漂移和相关性指标。
- 人工审核事故能进入版本化 Dataset/Regression，并可生成候选模型后重新过 Gate。

---

## 7. A3：产品控制台、审核与商业工作流

### 7.1 A3 的目标结构

```text
a3/
  onboarding/         安装后初始化、组织、项目和环境向导
  identity-ui/        登录、验证、MFA、账号绑定、SSO 设置
  console/            Run、Case、Trace、Evidence、Model、Provider
  review/             队列、仲裁、Override、Waiver、Approval
  release/            Gate、War Room、GitHub/GitLab、通知
  reports/            Report、Share、Revoke、Expiry、Export
  datasets/           Golden、Regression、Label 和 Learning Data
  admin/              Tenant、RBAC、Audit、Health、Retention
  billing/            Plan、Usage、Entitlement、订单、账单、支付
  deploy/             安装状态、Migration、Backup、Upgrade、Support Bundle
  integrations/       企业微信、钉钉、飞书、GitHub/GitLab、Webhook
```

### 7.2 A3 可验证基础

- 已有 Next.js 产品壳和主要业务页面。
- 已有 Review、Report、Share/Revoke/Denied、Admin 和商业 API 契约。
- 已有 GitHub Gate dry-run、Waiver、Approval、Audit Bundle、Verifier、Artifact Registry。
- 已有 Fail-closed 写路径规则、RBAC 元数据和 Event Outbox 契约。

### 7.3 A3 Release 缺口

#### UI 与真实后端

- 多数页面仍需要从 Fixture/本地 Store 迁移到真实 A1/A2 API。
- 每个按钮都必须对应真实授权、幂等、审计、加载、失败、重试和并发冲突状态。
- 禁止 Dashboard 自行拼装 Release Ready；必须读取 A2 Decision。
- 需要把“契约存在”“本地可用”“生产可用”在 UI 中清楚标记。

#### 身份体验

- 需要完整的注册/邀请、邮箱验证、密码重置、MFA、Session 管理和设备/会话撤销。
- 同账号绑定多个平台必须有重新认证、唯一性冲突、解绑保护和接管风险提示。
- 企业私有化优先支持客户 OIDC/SAML；微信/QQ/支付宝登录必须标记为“需主体资质”，不得出现在生产可用清单中。
- 需要组织、团队、项目、环境、Role Binding 和服务账号的管理界面。

#### 审核与发布

- Reviewer Queue 需要分配、锁定、超时、转交、双人审批和冲突处理。
- Override/Waiver 要显示作用域、有效期、风险和原始机器结论。
- Release War Room 需要真实状态流、阻断原因、变更历史和回滚入口。
- GitHub 之外还需按企业需求支持 GitLab、Webhook，以及企业微信/钉钉/飞书通知。

#### Report 与 Evidence

- Share Token 必须有签名、权限、过期、撤销、下载控制和审计。
- Report 必须能展示 Evidence 完整性、模型/Provider/Judge/Policy 版本和人工动作。
- Export 必须防止 Secret、PII、跨租户引用、CSV Injection 和失效 Signed URL。
- Audit Bundle 的生成、签名、验证和下载必须连接真实存储与权限。

#### 商业与部署体验

- Usage、Quota、Entitlement、订单、账单和支付状态尚未形成端到端真实 UI。
- 微信/支付宝 Checkout 需等待主体和商户资质；资质就绪前采用企业 License/合同交付。
- 管理后台需要真实部署健康、队列深度、模型容量、Migration、Backup、Restore 和 Support Bundle。
- 需要中文优先的安装、错误诊断、运维和安全配置体验。

#### 产品质量

- 需要系统化无障碍、响应式、国际化、浏览器兼容和大数据量性能测试。
- Playwright 需要覆盖真实身份、权限拒绝、审核、发布、报告分享、升级和故障恢复关键流程。
- 视觉美观不能掩盖状态不真实；所有高风险操作必须清楚、可撤销或需确认。

### 7.4 A3 Release 验收

- 新企业管理员能完成安装后的组织初始化、IdP 配置、项目创建和 SDK 接入。
- 不同角色只能看到并执行被授权的动作。
- Reviewer 可完成分配、审核、Override/Waiver 和双人审批。
- Release Gate 能真实阻断 CI/CD，并把原因送达代码平台和国内协作工具。
- Report 可安全分享、撤销、过期、导出和审计。
- 管理员能看到服务、队列、模型、存储、备份、Migration 和 License 状态。

---

## 8. 企业 Release 的标准内容

### 8.1 必须交付

- Web、API、A1、A2、Worker、Model Serving 等签名 OCI 镜像。
- Helm Chart 作为生产参考，Docker Compose 作为开发/试用参考。
- Terraform 模块和 Bring Your Own Infrastructure 文档。
- PostgreSQL Migration、兼容矩阵、预检、升级、回滚、备份和恢复命令。
- 对象存储、Queue、Ingress、TLS、DNS、IdP、SMTP、KMS、Observability、Provider 和模型配置模板。
- Readiness/Liveness/Startup、Migration、Queue、Model Capacity 和依赖诊断。
- SBOM、镜像签名、Provenance、漏洞报告、许可证和校验和。
- 离线镜像/模型包与私有 Registry 指南。
- 默认拒绝的网络策略、最小权限服务身份和 Secret Reference。
- Seeded Smoke、Golden Pack、安装验证和自动脱敏 Support Bundle。
- 中文优先的 Operator、Admin、Reviewer、SDK、API、安全、容量和事故手册。
- Release Note、Known Limitations、支持版本政策和生产证据。

### 8.2 部署档位

1. **Developer**：单机 Compose，可选 Ollama。
2. **Evaluation**：小型 Kubernetes/VPC，Postgres、对象存储、Queue 和一个受治理模型后端。
3. **Enterprise HA**：多实例、托管依赖、Worker/Model 自动扩缩容、SSO、KMS、备份恢复和完整观测。
4. **受限/离线**：不要求公网 Provider，离线镜像与模型、私有 Registry、客户 IdP 和受控升级包。

“开箱即用”必须包含预检、安装、Migration、Seed、Smoke、健康报告和可操作错误，不是用一个不透明脚本隐藏不可逆操作。

---

## 9. 技术裁决

| 层 | 主技术 | 原则 |
|---|---|---|
| Web/Product | TypeScript + React + Next.js | A3 主线，严格 Typed API，Playwright E2E |
| SDK | TypeScript + Python | A1 主线，统一 Event Contract |
| Platform API/Ingress | Go | 高并发接入、授权、计量和 Worker |
| Evaluation/Learning | Python | A2 Judge、Extractor、Provider、Training |
| 数据库 | PostgreSQL/PLpgSQL | 权威存储、Migration、RLS Defense-in-depth |
| 对象存储 | S3-compatible/MinIO | Evidence、Dataset、Report、Bundle、Model |
| Queue/Workflow | Durable Queue，复杂流程可用 Temporal | 幂等、重试、恢复、Backpressure |
| Model Serving | Ollama 开发；vLLM 或等价后端生产参考 | Provider-neutral |
| Observability | OpenTelemetry + Metrics/Logs/Traces | 全链路 Tenant/Request/Trace |
| Deploy | Docker + Helm + Terraform | VPC、自托管、离线优先 |

Rust 只用于安全敏感的签名、验证或 Sandbox；其他语言只有在客户/生态有明确需求时进入核心路径。

---

## 10. 身份、授权与账号绑定

### 无外部主体资质依赖的交付优先级

```text
企业 OIDC / SAML
本地管理员初始化
邮箱密码或密码无关登录
服务账号
Scoped API Key
MFA
```

### 具备主体资质与平台审批后的可选接入

```text
微信开放平台登录
QQ 互联登录
支付宝登录
微信支付
支付宝支付
```

内部身份模型必须将 `user` 与 `identity` 分离，一个用户可绑定多个已验证身份。绑定/解绑必须重新认证、防 CSRF、校验 Provider Subject 唯一性、处理邮箱冲突，并记录完整审计。

权限模型至少支持：

```text
organization owner
organization admin
security admin
billing admin
project admin
developer
reviewer
auditor
read-only viewer
service account
```

RBAC 决定基本权限，ABAC 结合组织、项目、环境、资源、数据分类和发布策略作最终授权。

---

## 11. 数据、安全与隐私底线

- 所有 Tenant-owned 数据必须带组织/租户主键。
- 所有写操作必须带 Actor 或 Service Account。
- 外部请求必须有 Request ID，关键链路必须有 Trace ID。
- Customer Payload 默认不进入日志。
- Secret 只存 Hash 或加密引用。
- Evidence、Label、Dataset、Decision 和 Model 有独立 Retention。
- 客户数据默认不跨租户，不用于训练，不离开客户 VPC。
- 需要支持 KMS、密钥轮换、TLS、RLS Defense-in-depth、Signed Webhook、Signed Bundle。
- 上传内容必须防 Malware、SSRF、压缩炸弹、Parser Escape 和 Prompt Injection。
- Export 必须防 Secret/PII 泄露、CSV Injection 和跨租户对象引用。
- 安全扫描覆盖依赖、SAST、容器、SBOM 和供应链 Provenance。

---

## 12. 面向 Release 的能力建设路径

### 路线与契约治理

- Ashr 全面可选化，禁用后 CI 与评测可运行。
- 冻结 Event、Evidence Snapshot、Provider、Decision Ledger、Review、Dataset Lineage 和 Release Decision 契约。
- 对全部能力标注“已实现/契约支撑/生产验证”。
- 在扩大数据收集前冻结 Consent、Purpose、Retention、Deletion 和 Tenant 默认策略。

### 完整纵向主链

```text
SDK/Platform -> A1 Ingestion -> A2 Normalize/Extract
-> Judge -> Decision -> Review -> Release Gate -> A3
```

- PostgreSQL、对象存储和 Durable Queue 成为权威路径。
- 一个多模态 Case 可端到端重放。
- 所有失败严格 Fail Closed。

### Provider 与模型后端

- 生产化 Ollama、vLLM、OpenAI-compatible 和客户自建 Endpoint。
- 完成 Model Registry、路由、健康、Quota、成本、Circuit Breaker、Shadow、Canary 和 Rollback。
- 交付至少一个本地/离线模型 Profile。

### 身份、审核与国内企业体验

- 完成企业 OIDC/SAML、本地登录、MFA、账号绑定、服务账号和真实 RBAC。
- 完成 Reviewer、Override、Waiver、双人审批和 Audit。
- 完成企业微信/钉钉/飞书及代码平台集成优先路径。
- 微信/QQ/支付宝身份与支付保持 Ready-to-integrate，等待主体资质。

### 数据闭环与学习

- 将事故、人工修正和偏好变成版本化 Golden/Regression/Dataset。
- 建立一个可复现的 SFT/Preference Training 参考流程。
- 候选模型必须重新通过 A2 Gate 才能晋级。

### 企业 Release 制品与验证

- 完成 Helm/Terraform、签名镜像、SBOM、离线包、预检、安装验证、升级、回滚、备份、恢复和 Support Bundle。
- 在类客户 VPC 完成 Load、Soak、Failure、Restore 和 Restricted-network Drill。
- 形成 SLO、告警和事故响应。

### 生产证明

- 设计合作企业试点。
- 安全评审与渗透测试闭环。
- 发布容量、恢复、升级和评测质量证据。
- 建立支持版本、漏洞响应和 Release Cadence。

---

## 13. Main 合并与 Release 门禁

任何进入 `main` 的变更必须：

```text
基于目标 main 的远端 HEAD，并在合并前完成同步验证
diff --check clean
触及 Lane 的单元/契约/集成测试通过
跨 Lane Fixture 和 Schema 兼容
无 Secret、私有证据和禁止支付数据泄露
Migration 可升级且有回滚/兼容说明
Artifact Registry 和 Bundle 在需要时重封
文档不把契约能力冒充生产能力
明确 Tenant/Auth/RBAC/Usage/Audit/Retention 影响
```

正式 Release 还必须：

```text
版本 Tag
不可变制品
镜像签名、SBOM、Provenance
Migration 与兼容矩阵
安装/升级/回滚/备份/恢复验证
安全扫描
Seeded Smoke 与 Golden Gate
Known Limitations
Support Bundle
生产或类生产演练证据
```

---

## 14. 最终验收标准

项目只有同时满足以下闭环，才能被定义为企业可发布版本：

- 企业能在自己的云/VPC 中安装、升级、回滚和恢复。
- 不依赖 Ashr 或任意单一外部 Provider。
- SDK 与平台调用能安全、合规、可追溯地进入证据和计量系统。
- 多模态 Evidence 有完整提取、质量和安全状态。
- Judge 有可量化准确率、误报、漏报、漂移和人工一致率。
- Reviewer、Override、Waiver、Approval 和 Release Gate 完整可审计。
- 真实 RBAC、SSO、服务账号和租户隔离生效。
- Report、Share、Export、Bundle 和 Verifier 连接真实数据面。
- Usage、Entitlement、账单和 License 可对账。
- 国内企业可先通过合同/License 交付；取得主体后接入微信/支付宝收款。
- 数据闭环能够产生有授权、有 Lineage 的 Regression、Preference 和 Training Dataset。
- 模型训练、晋级、部署和回滚全部经过 A2 评测门禁。
- SLO、告警、备份恢复、事故响应和供应链安全可验证。

任何未满足上述闭环的构建都只能作为开发、验证或试点制品，不得标记为成熟商业 Release。

---

## 15. 不做什么

- 不做依赖单一 Ashr API 的产品。
- 不做 Dify 式通用工作流或聊天壳。
- 不把 Ollama 当作完整生产模型平台。
- 不因为收集了反馈就宣称拥有 RLHF。
- 不把用户使用产品视为训练授权。
- 不在没有主体资质时宣称微信、QQ、支付宝登录或支付已上线。
- 不把 Fixture、Mock、OpenAPI、页面或 Terraform 形状当作生产证明。
- 不为了炫酷界面牺牲真实状态、权限、审计和失败语义。
- 不交付无法升级、回滚、恢复和支持的“单次安装脚本”。

---

## 16. 系统不变量

- A1 运行成功不等于 A2 评测成功。
- Evidence 缺失、无效、隔离或不支持绝不变成 Pass。
- Provider 失败、额度耗尽和支付不一致绝不变成 Pass。
- 禁用 Ashr 不影响开发、CI、Release Gate 和企业运行。
- A3 不重算 A2 分数或 Release Decision。
- 没有 Decision Ledger 就没有 Release Ready。
- 人工 Override 保留机器原始决策。
- 每个 Release Decision 绑定 Evidence、Extractor、Judge、Model、Provider、Prompt、Rubric、Scenario、Dataset 和 Policy 版本。
- 每个学习样本绑定 Tenant、Purpose、Consent、Source 和 Label Lineage。
- 私有证据、Credential 和禁止支付数据不得进入公共 Fixture、日志、报告、Support Bundle 或跨租户 Dataset。
- 企业自有云/VPC 是第一交付目标。
- 不能复现安装、升级、回滚、恢复、安全与运维证据，就不能称为企业 Release。
