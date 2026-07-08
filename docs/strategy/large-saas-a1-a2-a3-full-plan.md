# Ashr Commercial SaaS Endgame Architecture Bus

> 本文件不是阶段计划。
>
> 本文件定义 Ashr 的商业终局、生长环境、技术栈、服务边界、接口契约、数据模型、安全底线和 Codex agent 生长规则。
>
> 所有分支、goal、sub-agent、测试、文档、fixture、API、UI、SDK 都必须向这个终局收敛。

---

## 0. 终局定义

Ashr 的终局不是复刻一个网页产品，也不是堆一个学生项目。

Ashr 的终局是：

```text
Agent Release OS
```

它面向真实公司、真实团队、真实发布流程、真实账单、真实安全风险。

它要解决的问题是：

```text
AI Agent 在上线前，能否被接入、运行、记录、评测、复盘、阻断、审计、协作、计费、追责。
```

一句话：

```text
Ashr = AI Agent 的发布门禁、评测平台、证据系统、审计系统和团队协作后台。
```

商业化描述：

```text
Upload or connect your agent.
Run production-grade evaluation.
Inspect traces and tool calls.
Block risky releases.
Generate audit evidence.
Integrate with GitHub and enterprise identity.
Bill by usage.
```

---

## 1. 生长环境原则

我们不是按时间一步一步做。

我们搭建一个让 Codex 可以持续生长的商业平台环境。

每个 Codex goal 必须回答：

```text
1. 我属于哪个 lane？
2. 我修改哪个服务边界？
3. 我使用哪种语言和框架？
4. 我新增或修改哪些 API / DB / event / artifact contract？
5. 我如何验证 tenant/auth/RBAC/usage/audit/redaction？
6. 我如何和其他 lane 的输出拼接？
7. 我如何把工作日志写入本地？
8. 我如何在开始、中途、结束时读取历史 worklog？
9. 我如何让 Bus-Auditor 审核方向、接口、测试和证据链？
10. 我是否把生成物接入 artifact bundle 自动重封机制？
```

禁止的生长方式：

```text
只做 demo 页面
只做 mock shell
只加无服务边界的函数
只写不能接入 auth/tenant/audit 的业务逻辑
只写不能进入 API/SDK/DB/event contract 的代码
只写不能被测试和证据链验证的功能
```

允许的生长方式：

```text
从真实商业系统的边界反推代码
从接口契约反推实现
从数据库模型反推 API
从审计证据反推工作流
从安全威胁反推权限模型
从 billing/usage 反推资源计量
从部署运维反推服务拆分
从 GitHub/SSO/支付/对象存储等真实平台反推适配层
```

---

## 2. 语言裁决

语言不是越多越好。

语言必须绑定商业职责。

| 语言 | Ashr 中的职责 | 是否主力 |
|---|---|---|
| TypeScript | Web app、SDK、edge/client、dashboard、admin console、GitHub integration、React Native/PWA | 是 |
| Python | Judge、eval、model calling、calibration、data tooling、research scripts、offline analysis | 是 |
| Go | API gateway、ingestion service、worker service、queue consumer、high concurrency backend、webhook delivery | 是 |
| SQL / PLpgSQL | Postgres schema、RLS、migration、tenant policy、audit trigger、usage rollup | 是 |
| Bash | CI/devops glue only | 辅助 |
| C / C++ | sandbox runtime、native runner、WASM host、high-performance trace parser，只有出现明确瓶颈才启用 | 否 |
| C# | Microsoft enterprise SDK / .NET customer integration，只有客户或生态要求时启用 | 否 |
| Swift / Kotlin | 原生 iOS/Android，只有 PWA/React Native 不够时启用 | 否 |
| Rust | security-sensitive signer/verifier/sandbox，可选，不作为当前主线 | 否 |

裁决：

```text
主干只承认 TypeScript + Python + Go + SQL/PLpgSQL。
其他语言必须证明商业必要性，否则不得进入核心路径。
```

---

## 3. 框架裁决

### 3.1 Product Web

目标：

```text
从当前 dashboard 进化为真实 SaaS product console。
```

裁决：

```text
TypeScript + React + Next.js
```

不采用 Vue/Nuxt 作为主线。

原因：

```text
React/Next 更适合和 Vercel AI SDK、enterprise dashboard、React Native、组件生态、GitHub examples、AI SaaS 模板结合。
Vue 可以做局部实验，但不能成为主产品主线。
```

UI 约束：

```text
shadcn/ui 或 Radix primitives
Tailwind 作为 utility layer
TanStack Query 管理 server state
TanStack Table 管理 run/case/report tables
Zod 管理 client schema validation
Playwright 做 E2E
Storybook 可选，只有组件复杂度上来后启用
```

### 3.2 Backend API

目标：

```text
承载真实 tenant、auth、run ingestion、artifact、worker dispatch、usage、billing、audit。
```

裁决：

```text
Go + chi/gin/fiber 之一
OpenAPI first
Postgres first
Redis/Valkey for cache and short locks
Temporal for durable workflow when job complexity上升
```

TypeScript/NestJS 可用于 BFF 或 admin API，但不作为高吞吐 ingestion 的最终主线。

Python 不作为主 API gateway，只做 judge/eval service。

### 3.3 Judge Service

目标：

```text
让 A2 从本地 judge 变成可配置、可审计、可版本化、可计费的评测智能服务。
```

裁决：

```text
Python + FastAPI
Pydantic models
OpenAPI schema
async model providers
pytest contracts
```

Judge service 只通过 API、queue job、artifact ref 和 DB record 与平台交互。

### 3.4 Workers

目标：

```text
长期运行、可重试、可取消、可恢复、可观测。
```

裁决：

```text
Go workers: ingestion, artifact, webhook, billing, bundle sealing
Python workers: judge, semantic eval, calibration, regression replay
Temporal workflows: durable multi-step release/evidence jobs
Redis/Valkey queues: early local/dev fallback
```

### 3.5 Storage

目标：

```text
真实多租户数据和大文件证据存储。
```

裁决：

```text
Postgres = source of truth
S3/R2/MinIO = artifact/trace/report/audit bundle storage
Redis/Valkey = cache, rate limit, ephemeral locks
ClickHouse = later analytics/event warehouse
OpenSearch = later full-text and trace search
```

### 3.6 Mobile / Client

目标：

```text
让用户能在手机上看 release gate、审批、告警、报告，而不是把移动端当主工作台。
```

裁决：

```text
第一主线：PWA
第二主线：React Native / Expo
中国商业场景：微信小程序归入 A3 client surface
原生 Swift/Kotlin：只有 App Store/企业客户要求时才做
```

### 3.7 Development Environment

开发环境不是个人偏好。

它是代码树继续生长时的统一土壤。

默认裁决：

| Layer | Decision | Owner | Purpose |
|---|---|---|---|
| Runtime OS | macOS for local dev, Linux containers for service runtime | A1 | 保证本机可跑、容器可复现、云端可部署 |
| Node.js | Node 24 LTS line | A3 primary, A1 SDK support | Next.js、TypeScript SDK、CLI、Playwright、dashboard |
| Package manager | pnpm workspace | A3 primary | monorepo JS/TS dependency control |
| TypeScript | strict mode, ESM first, Zod at boundaries | A3 primary, A1 SDK support | 前端、SDK、typed API client、integration scripts |
| Python | Python 3.13 line | A2 primary | judge、semantic eval、calibration、model provider adapters |
| Python tooling | uv + pytest + ruff + mypy optional | A2 primary | 快速环境恢复、测试、静态检查 |
| Go | Go 1.26 line | A1 primary | API gateway、ingestion、workers、webhooks、billing backend |
| SQL | PostgreSQL 17+ dialect, PLpgSQL allowed | A1 primary, A2 policy review | tenant isolation、RLS、audit、usage rollup |
| Containers | Docker Compose for local, Kubernetes-ready manifests later | A1 primary | Postgres、Redis/Valkey、MinIO、Temporal、OpenTelemetry |
| Cache / Queue | Redis or Valkey | A1 primary | rate limit、short lock、local queue fallback |
| Object Storage | MinIO locally, S3/R2 compatible contract | A1 primary | evidence、trace、report、bundle artifacts |
| Workflow Engine | Temporal for durable jobs | A1 primary, A2 judge jobs | long-running release/eval/artifact workflows |
| Browser tests | Playwright | A3 primary | login、dashboard、review、billing、report flow |
| API contract | OpenAPI + generated clients | A1 primary, A3 client consumer | backend/frontend/SDK 拼接边界 |
| Observability | OpenTelemetry + structured logs | A1 primary | trace_id、request_id、tenant_id 全链路追踪 |
| CI | GitHub Actions | A1 primary | test matrix、bundle reseal check、contract drift check |

本地开发必须能一条命令启动核心依赖：

```text
Postgres
Redis/Valkey
MinIO
Temporal
OpenTelemetry Collector
local API gateway
judge service
web console
worker service
```

仓库必须逐步收敛到这些标准入口：

```text
make dev
make test
make lint
make typecheck
make db-up
make db-migrate
make seed
make bundle-reseal
make smoke
```

环境变量必须以 contract 形式出现：

```text
DATABASE_URL
REDIS_URL
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY_ID
OBJECT_STORAGE_SECRET_ACCESS_KEY
TEMPORAL_ADDRESS
OTEL_EXPORTER_OTLP_ENDPOINT
ASHR_API_BASE_URL
ASHR_PUBLIC_WEB_URL
ASHR_JUDGE_SERVICE_URL
ASHR_SECRET_ENCRYPTION_KEY_REF
OPENAI_API_KEY
ANTHROPIC_API_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
MICROSOFT_CLIENT_ID
MICROSOFT_CLIENT_SECRET
WECHAT_APP_ID
WECHAT_APP_SECRET
QQ_CLIENT_ID
QQ_CLIENT_SECRET
```

环境变量规则：

```text
本地只允许 .env.local / .env.dev。
提交仓库的只能是 .env.example。
任何真实 secret 不得进入 git。
所有 provider key 必须由 service boundary 消费，不能散落在 UI 或脚本里。
所有 Codex goal 新增 env 时必须同步更新 .env.example、docs、tests。
```

A1/A2/A3 的环境边界：

| Lane | 必须能独立启动 | 必须能独立验证 | 不得绕过 |
|---|---|---|---|
| A1 | API、DB、storage、queue、worker、auth backend | API tests、migration tests、contract tests、smoke tests | tenant/auth/audit/usage |
| A2 | judge service、model adapters、scenario packs、calibration jobs | pytest、golden tests、semantic judge regression、policy tests | evidence integrity/redaction/cost policy |
| A3 | web console、SDK examples、client workflows、E2E tests | Playwright、component tests、typed client tests、report rendering tests | API contract/RBAC/billing state |

Codex 默认环境权限：

```text
Codex 可以安装缺失的本地工具、语言运行时、包管理器、数据库客户端、容器组件和测试依赖。
如果需要管理员权限，Codex 必须明确说明要安装什么、为什么安装、会影响哪里。
Codex 不能因为环境缺失而把商业目标降级成 mock。
环境缺失时，应优先补环境，其次补 adapter，最后才允许临时 fake，并且 fake 必须被标注为待替换。
```

---

## 4. 平台 lane 定义

真实商业平台需要 identity、infra、security、billing、mobile、integrations。

但团队只有 3 个人，所以组织结构不能扩成 8 条人力 lane。

终局必须压缩为 3 条超级 lane。

| Lane | 名称 | 吸收能力 | 责任 |
|---|---|---|
| A1 | Platform / Identity / Infra | 后端、身份、部署、计量底座 | API、SDK、DB、object storage、queue、workers、auth backend、RBAC backend、deployment、observability、usage source、billing ledger |
| A2 | Evaluation / Policy / Security | 评测、策略、安全验证、证据正确性 | judge、policy、scenario、calibration、regression、semantic eval、security verification、privacy validation、abuse detection、bundle verifier correctness |
| A3 | Product / Workflow / Commercial UI | 产品、协作、商业界面、客户端和集成体验 | web app、dashboard、report center、review workflow、GitHub/Slack/Teams、auth UI、admin UI、billing UI、PWA、React Native、WeChat mini program |

能力压缩规则：

```text
Identity/Auth/RBAC:
  A1 owns backend/session/token/provider adapters.
  A2 owns auth/security tests and abuse rules.
  A3 owns login/account/team/admin UI.

Infra/Deploy/Observability:
  A1 owns Docker/K8s/Terraform/CI runtime/telemetry pipelines.
  A2 owns service health semantics for judge/policy.
  A3 owns status UI and incident-facing surfaces.

Security/Privacy/Abuse:
  A1 owns technical enforcement.
  A2 owns verification, policy, threat cases, redaction correctness.
  A3 owns user-visible trust, privacy, audit, and admin controls.

Billing/Usage/Payment:
  A1 owns usage events, quota, billing ledger, payment provider backend.
  A2 owns cost/risk policy for judge/model usage.
  A3 owns pricing, checkout, invoice, plan, and usage UI.

Mobile/Integrations:
  A1 owns integration APIs and webhooks.
  A2 owns integration policy checks.
  A3 owns PWA, React Native, WeChat mini program, Slack/Teams/GitHub user workflows.
```

所有超级 lane 必须共享同一套 contract：

```text
tenant_id
organization_id
project_id
environment_id
run_id
case_id
artifact_id
evidence_bundle_id
release_gate_id
audit_event_id
actor_id
api_key_id
request_id
trace_id
```

---

## 5. 终局服务拓扑

```text
web-console [A3]
  Next.js product app
  dashboard / reports / admin / settings / billing / review

api-gateway [A1]
  Go public API
  auth middleware
  tenant middleware
  rate limit
  OpenAPI

identity-service [A1 primary, A3 UI, A2 security verification]
  OIDC/OAuth provider adapters
  email/phone login
  WebAuthn/passkeys
  session/token lifecycle
  RBAC/ABAC

ingestion-service [A1]
  runs
  cases
  trace events
  observations
  artifact manifests
  SDK and CI uploads

judge-service [A2]
  deterministic judges
  semantic judges
  policy evaluation
  calibration
  regression replay

artifact-service [A1 primary, A2 redaction/verifier rules, A3 report surface]
  signed upload/download
  object metadata
  checksum
  redaction
  malware scan hook
  retention

release-service [A3 primary, A2 policy, A1 persistence/events]
  release gate
  reviewer workflow
  waiver/approval
  GitHub check
  PR comment
  Slack/Teams notification

bundle-service [A1 storage/sealing, A2 verification correctness, A3 export UI]
  evidence bundle
  manifest
  root hash
  signature
  verifier
  immutable audit export

billing-service [A1 ledger/provider backend, A3 billing UI, A2 usage risk policy]
  usage meter
  quota
  plan
  invoice
  payment provider adapter

worker-service [A1 primary, A2 judge workers]
  background jobs
  Temporal workflows
  queue consumers
  retries
  dead letter

observability-stack [A1 primary, A2/A3 domain dashboards]
  OpenTelemetry
  metrics
  logs
  traces
  alerts
  incidents
```

---

## 6. 终局数据模型

Postgres 是 source of truth。

所有核心表必须 tenant scoped。

核心表：

```text
users
identities
sessions
organizations
organization_members
teams
team_members
roles
permissions
role_bindings
projects
environments
api_keys
service_accounts
datasets
scenarios
scenario_packs
runs
run_cases
trace_events
observations
tool_calls
judge_runs
judge_results
release_policies
release_gates
review_workflows
review_assignments
waivers
approvals
artifacts
artifact_manifests
evidence_bundles
bundle_signatures
audit_events
usage_events
usage_rollups
quota_policies
billing_customers
billing_subscriptions
billing_invoices
webhooks
webhook_deliveries
integrations
notifications
incidents
worker_jobs
```

Postgres 约束：

```text
所有 tenant-owned tables 必须有 organization_id
所有 project-owned tables 必须有 project_id
所有 write path 必须带 actor_id 或 service_account_id
所有外部请求必须带 request_id
所有 release/audit/artifact path 必须可追溯 trace_id
所有 secret 只存 hash 或 encrypted reference
所有 customer payload 默认不能进入 logs
```

PLpgSQL / RLS 终局：

```text
Row Level Security 默认开启
tenant isolation 在 DB 层和 API 层双重执行
audit trigger 记录关键 mutation
usage rollup 可用 DB job 或 worker job 生成
retention policy 可由 scheduled worker 执行
```

---

## 7. 终局 Auth / Identity / RBAC

Ashr 不能只做 API key。

商业平台必须支持：

```text
Email magic link
Email/password with strong policy, optional
Phone OTP, region-dependent
Google OAuth / OIDC
Microsoft Entra ID / OIDC
GitHub OAuth
QQ OAuth2
WeChat Open Platform login
SAML SSO for enterprise
OIDC enterprise provider
WebAuthn / passkeys
MFA
Service accounts
Scoped API keys
```

账号绑定模型：

```text
user
  id
  primary_email
  primary_phone
  status

identity
  provider
  provider_subject
  provider_union_id
  verified_email
  verified_phone
  profile_snapshot
  linked_user_id
  risk_score
```

权限模型：

```text
organization owner
organization admin
billing admin
security admin
project admin
developer
reviewer
auditor
read-only viewer
service account
```

权限判断必须支持：

```text
RBAC: role grants permission
ABAC: action depends on org/project/env/resource attributes
policy: enterprise custom release approval rules
```

所有 auth code 必须有测试：

```text
CSRF state
PKCE
redirect URI validation
token exchange error handling
account linking conflict
session fixation protection
refresh token rotation
logout / revoke
MFA challenge
```

---

## 8. 终局 API Contract

所有 public API 使用：

```text
/v1
JSON
OpenAPI
idempotency key
pagination
rate limit headers
request_id
error code contract
tenant scoped auth
```

### 8.1 Core Public API

```http
GET  /v1/me
GET  /v1/organizations
POST /v1/organizations
GET  /v1/projects
POST /v1/projects
GET  /v1/projects/{project_id}
PATCH /v1/projects/{project_id}

POST /v1/api-keys
GET  /v1/api-keys
POST /v1/api-keys/{api_key_id}/rotate
POST /v1/api-keys/{api_key_id}/revoke

POST /v1/datasets
GET  /v1/datasets
GET  /v1/datasets/{dataset_id}
POST /v1/datasets/{dataset_id}/cases

POST /v1/runs
GET  /v1/runs
GET  /v1/runs/{run_id}
POST /v1/runs/{run_id}/cases
POST /v1/runs/{run_id}/trace-events
POST /v1/runs/{run_id}/observations
POST /v1/runs/{run_id}/complete
POST /v1/runs/{run_id}/cancel

POST /v1/artifacts/upload-url
POST /v1/artifacts/complete
GET  /v1/artifacts/{artifact_id}

POST /v1/release-gates/evaluate
GET  /v1/release-gates/{release_gate_id}
POST /v1/release-gates/{release_gate_id}/waivers
POST /v1/release-gates/{release_gate_id}/approvals

GET  /v1/evidence-bundles/{bundle_id}
POST /v1/evidence-bundles/{bundle_id}/verify

GET  /v1/reports
GET  /v1/reports/{report_id}
POST /v1/reports/{report_id}/share

GET  /v1/usage
GET  /v1/billing/subscription
POST /v1/billing/checkout
POST /v1/billing/portal
```

### 8.2 Internal API

```http
POST /internal/judge/case
POST /internal/judge/run
POST /internal/judge/batch
POST /internal/policy/evaluate
POST /internal/regression/replay
POST /internal/bundles/seal
POST /internal/artifacts/redact
POST /internal/usage/rollup
POST /internal/webhooks/deliver
POST /internal/github/check
POST /internal/github/pr-comment
```

### 8.3 Event Contract

所有跨服务事件必须有 schema。

```text
run.created
run.completed
run.failed
trace.ingested
artifact.uploaded
judge.completed
policy.evaluated
release_gate.blocked
release_gate.approved
review.assigned
review.approved
bundle.sealed
bundle.verified
usage.recorded
quota.exceeded
billing.subscription_changed
webhook.delivered
github.check_published
security.secret_detected
auth.login_succeeded
auth.login_failed
```

事件字段：

```text
event_id
event_type
schema_version
organization_id
project_id
actor_id
request_id
trace_id
resource_type
resource_id
created_at
payload_ref
redaction_status
```

---

## 9. 终局 Evidence / Artifact / Bundle

Ashr 的护城河是证据链。

所有重要输出都必须进入 artifact registry。

Artifact 类型：

```text
run_result
trace_event_batch
case_result
judge_result
release_gate_report
markdown_report
csv_export
json_export
pr_comment
github_check
waiver
approval
audit_bundle_index
bundle_verification
screen_capture
model_call_summary
redaction_report
usage_rollup
invoice_snapshot
```

Evidence bundle 必须包含：

```text
input artifact hashes
generated artifact hashes
release decision
judge versions
policy versions
actor approvals
waiver record
chain of custody
root hash
signature
retention policy
verification command
```

自动重封规则：

```text
任何 source artifact 改变
任何 generated artifact 改变
任何 waiver/approval 改变
任何 release gate threshold 改变
任何 judge/policy version 改变
都必须触发 bundle reseal
```

CI 规则：

```text
如果 bundle index hash drift，CI fail
如果 verifier fail，CI fail
如果 public artifact 泄露 secret，CI fail
如果 artifact 没有 registry record，CI fail
```

---

## 10. 终局 Security / Privacy

安全不是后补功能。

每个 lane 都必须按安全模型生长。

安全基线：

```text
OWASP ASVS as verification checklist
HTTPS only
secure cookies
CSRF protection
PKCE for OAuth
MFA support
WebAuthn support
rate limiting
brute-force protection
audit log
secret redaction
encrypted credentials
KMS envelope encryption
least privilege
tenant isolation
RLS defense in depth
signed webhook
signed artifact bundle
dependency scanning
SAST
container scanning
security headers
```

隐私基线：

```text
PII classification
data retention policy
data deletion workflow
export user/org data
customer payload never logged raw
private prompt/response redaction
region-aware storage, later
```

防攻击重点：

```text
OAuth redirect attack
CSRF
session fixation
IDOR
broken tenant isolation
API key leakage
prompt/trace secret leakage
artifact poisoning
webhook replay
billing abuse
rate limit bypass
SSRF through artifact URL
malicious uploaded files
SQL injection
XSS in report/dashboard
CSV injection
dependency supply-chain attack
```

---

## 11. 终局 Billing / Usage

Ashr 必须能收钱。

Usage meter：

```text
api_requests
run_count
case_count
trace_event_count
observation_count
artifact_bytes_uploaded
artifact_bytes_stored_days
judge_invocations
semantic_judge_tokens
model_cost_usd
replay_jobs
report_exports
webhook_deliveries
github_check_publishes
team_members
retention_days
```

Plan：

```text
free
student
team
pro
enterprise
self-host enterprise
```

Payment provider abstraction：

```text
Stripe
WeChat Pay
Alipay
manual invoice
enterprise contract
```

Billing service 只接收 usage event，不直接读取业务私密 payload。

---

## 12. 终局 Deploy / Ops

生产环境必须可部署、可恢复、可观测。

部署：

```text
Docker
docker-compose for local integration
Kubernetes for production
Terraform for cloud resources
Helm charts or Kustomize
GitHub Actions CI/CD
staging / production separation
preview environment
```

运行：

```text
api deployment
web deployment
judge deployment
worker deployment
scheduler
Postgres
Redis/Valkey
object storage
OpenTelemetry collector
metrics backend
log backend
error tracking
```

运维能力：

```text
health check
readiness check
liveness check
db migration command
rollback command
backup restore drill
incident runbook
SLO
alert rules
on-call notification
```

---

## 13. Codex 生长协议

每个 goal 必须粘贴这段协议。

```text
You are growing Ashr toward the commercial SaaS endgame defined in:
docs/strategy/large-saas-a1-a2-a3-full-plan.md

You have full local environment, software, library, runtime, browser, network, and repository access.
If administrator permission is required, ask explicitly.

Do not build isolated demos.
Every change must declare:
- lane
- language/framework
- service boundary
- API/DB/event/artifact contract
- tenant/auth/RBAC/usage/audit implications
- tests
- local worklog path
- bundle/artifact reseal impact

Spawn six sub-agents inside the current A1/A2/A3 lane.
These are not people or new ownership lanes.
They are internal reviewers used to make one person's Codex window behave like a small production team:

- Bus-Auditor: continuously checks this strategy bus, detects drift, suggests toolchain/environment/goal corrections.
- Contract-Agent: API/DB/event/schema compatibility.
- Security-Agent: auth/RBAC/tenant/privacy/abuse/security tests.
- Evidence-Agent: artifact registry, redaction, bundle sealing, verifier.
- Test-Agent: unit/integration/E2E/fixture regeneration.
- Integration-Agent: reads other branches, pulls others' work, distinguishes own changes from others' changes.

Main agent must periodically ask Bus-Auditor what changed and must write progress to local worklog.
Before final answer, reread worklog and summarize what changed, what passed, what failed, and what should grow next.
```

禁止 goal：

```text
只写页面
只写 README
只写 mock
只写没有测试的模块
只写没有 contract 的服务
只写不能拼进 main 的分支
```

合格 goal：

```text
能够自己发现当前 repo 状态
能够读取其他 branch
能够拉取别人代码分析
能够运行测试
能够补齐 contract
能够写 worklog
能够给出 merge risk
能够说明是否需要 bundle reseal
```

---

## 14. Main 合并门禁

任何分支进入 main 前必须满足：

```text
git status clean
origin/main is ancestor
Python tests for touched lane pass
Node/TS tests for touched lane pass
diff --check clean
no secret leakage
README and strategy bus not accidentally corrupted
artifact registry updated if artifacts changed
bundle resealed if bundle inputs changed
worklog updated
merge summary names own work vs others' work
```

如果修改这些路径，必须额外验证：

```text
fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json
fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json
fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json
fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json
fixtures/a3/p3/a3_gate_cli_github_check.redacted.json
fixtures/a3/p3/a3_gate_cli_report.redacted.md
fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md
```

必须运行：

```text
node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --strict-exit --json
node --test tests/a3/a3_gate_cli.test.mjs
```

---

## 15. 当前 A1/A2/A3 的终局定位

### A1

A1 不只是 runner owner。

A1 是：

```text
Platform API / SDK / Storage / Worker / Identity Backend / Infra / Usage Ledger owner
```

A1 每次生长都必须问：

```text
这个能力能否被真实 SDK/API 用户调用？
这个数据是否能进入 Postgres/object storage？
这个流程是否支持 tenant isolation？
这个登录、API key、RBAC、session、provider adapter 是否能被后端强制执行？
这个操作是否有 usage event？
这个服务是否能部署、观测、回滚？
这个 artifact 是否可审计？
```

### A2

A2 不只是 judge owner。

A2 是：

```text
Evaluation Intelligence / Policy / Calibration / Regression / Security Verification owner
```

A2 每次生长都必须问：

```text
这个 judge 是否可版本化？
这个 policy 是否可配置？
这个结果是否可解释？
这个 blocker 是否能进入 release gate？
这个失败是否能变成 regression asset？
这个安全/隐私/滥用风险是否有测试样本？
这个 redaction、bundle verifier、policy gate 是否能抓 drift？
```

### A3

A3 不只是 dashboard owner。

A3 是：

```text
Product Console / Review Workflow / Report Center / GitHub Gate / Commercial UI / Client owner
```

A3 每次生长都必须问：

```text
这个页面是否对应真实 API？
这个操作是否有权限和审计？
这个报告是否可分享、撤销、过期？
这个 release decision 是否能进入 GitHub/Slack/Teams？
这个 UI 是否让用户完成真实工作流？
这个登录、团队、billing、usage、mobile/PWA/小程序体验是否让商业用户能用？
```

---

## 16. 终局验收标准

Ashr 触碰商业级别，不是因为代码行数，而是因为这些闭环同时成立：

```text
真实用户可注册/登录/绑定账号
组织和项目可管理
API key 可创建、验证、撤销、限流
SDK 可提交真实 run 和 trace
Postgres 持久化核心数据
Object storage 持久化大 artifact
Worker 长期运行并可恢复
Judge service 可配置、可版本化、可审计
Release gate 可阻断危险发布
Reviewer workflow 可审批/拒绝/豁免
GitHub check / PR comment 可发布
Report Center 可分享、撤销、过期
Evidence bundle 可重封、签名、验证
Usage 可计量
Billing 可收款
Tenant isolation 可测试
Security baseline 可验证
CI/CD 可稳定部署
Observability 可定位事故
Mobile/PWA 可处理审批和告警
```

如果这些没有闭环，Ashr 仍然是高级原型。

如果这些闭环成立，Ashr 就不再是学生项目，而是商业 SaaS 的 early production system。

---

## 17. 最终裁决

不要再把 Ashr 当成一个复现项目设计。

要把 Ashr 当成一个真实公司要卖的系统设计。

从现在开始，所有生长都必须遵守：

```text
语言有职责
框架有边界
接口有契约
数据有租户
权限有证明
证据有哈希
报告有出处
计费用 usage
部署有环境
故障有观测
合并有门禁
Codex 有总线
```

这就是 Ashr 的终局生长环境。
