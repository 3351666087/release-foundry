# A1 / A2 / A3 大型 SaaS 全量补齐方向

> 目标：把当前 `Ashr Codex Factory` 从 fixture-driven local factory / 高级原型，推进为 multi-tenant hosted large SaaS。
>
> 当前日期：2026-07-07
> 适用对象：A1、A2、A3 三条研发线
> 核心原则：A1 补生产平台能力，A2 补评测智能产品化，A3 补真实用户工作流。

---

## 0. 总体结论

如果最终目标是 **大型 SaaS**，那 A1/A2/A3 不能只继续按现在的方向堆功能。现在三条线分别像：

```text
A1 = 接入层 / 执行层 / SDK / API / 数据入口
A2 = 评测引擎 / 判断逻辑 / failure intelligence
A3 = 产品控制台 / 用户体验 / release workflow
```

如果目标变成大型 SaaS，三个人最终要补的东西可以这样分：

```text
A1 要补成：生产级平台后端 + SDK + 数据/任务基础设施
A2 要补成：可配置、可校准、可解释、可版本化的评测智能服务
A3 要补成：真实多租户产品前端 + 团队协作 + 审计/发布控制台
```

更直接地说：

## A1 要从 “local runner / SDK” 升级为

> **SaaS ingestion + execution + platform backend owner**

## A2 要从 “deterministic judge / scenarios” 升级为

> **Evaluation intelligence / policy / calibration owner**

## A3 要从 “static dashboard / report builder” 升级为

> **Customer-facing product / workflow / control tower owner**

---

## 1. 大型 SaaS 的完整形态

如果 Ashr 最终是大型 SaaS，它大概需要这些层：

```text
1. 用户与组织层
   User / Org / Team / Project / Role / API key

2. 数据接入层
   SDK / CLI / GitHub Action / API / Webhook / Upload

3. 执行与任务层
   Run ingestion / Queue / Worker / Replay / Trace processing

4. 评测智能层
   Judge / Scenario / Policy / Calibration / Regression / Semantic evaluation

5. 证据与审计层
   Evidence bundle / Audit log / Hash chain / Redaction / Retention

6. 产品控制台
   Dashboard / Triage / Release gate / Reviewer workflow / Reports

7. 商业化层
   Usage / Quota / Billing / Plans / Enterprise controls

8. 运维与合规层
   Monitoring / Alerting / Backups / Security / SSO / SOC2 readiness
```

现在 A1/A2/A3 已经摸到 2、3、4、5、6 的边，但离大型 SaaS 还要补 1、7、8，并把 2～6 从本地/fixture/mock 升级到真实生产系统。

---

# 2. A1 全量要补什么

A1 当前最接近 SaaS 底座。大型 SaaS 下，A1 应该成为 **平台后端负责人**。

---

## A1-1：真实多租户数据模型

现在项目里已经有 tenant/project/dataset/run 的影子，但大型 SaaS 要正式建模。

A1 要补：

```text
User
Organization
Workspace
Project
Environment
Dataset
Run
CaseResult
TraceEvent
Observation
Artifact
EvidenceBundle
ApiKey
WebhookEndpoint
UsageLedger
QuotaPolicy
BillingAccount
Integration
```

关键要求：

```text
所有核心表必须带 organization_id
所有 project/run/dataset 必须有权限边界
所有 API 查询必须 tenant scoped
所有 artifact 必须可追溯 owner/project/run
```

A1 要负责 DB schema、migration、索引、生命周期。

建议数据库：

```text
Postgres = 主元数据
S3/R2/GCS = trace/artifact/report 存储
Redis/Queue = 异步任务
ClickHouse/BigQuery，可选 = 大规模 trace/event 分析
```

---

## A1-2：生产级 Run Ingestion API

大型 SaaS 的入口不是上传 mock JSON，而是稳定 API。

A1 要补：

```http
POST /v1/projects
GET  /v1/projects

POST /v1/datasets
GET  /v1/datasets
GET  /v1/datasets/{dataset_id}

POST /v1/runs
GET  /v1/runs
GET  /v1/runs/{run_id}

POST /v1/runs/{run_id}/cases
POST /v1/runs/{run_id}/observations
POST /v1/runs/{run_id}/trace-events
POST /v1/runs/{run_id}/artifacts

POST /v1/runs/{run_id}/complete
POST /v1/runs/{run_id}/cancel
POST /v1/runs/{run_id}/replay

GET  /v1/evidence-bundles/{bundle_id}
POST /v1/release-gates/evaluate
```

要支持：

```text
idempotency key
pagination
rate limit
request validation
schema versioning
partial upload
large artifact upload
signed upload URL
retry-safe ingestion
batch upload
streaming trace ingestion
```

---

## A1-3：SDK 正式产品化

当前 Python/TS SDK 有基础，但大型 SaaS 需要变成真正用户入口。

A1 要补：

### Python SDK

```python
from ashr import Ashr

client = Ashr(api_key="...")

run = client.runs.create(
    project_id="proj_123",
    name="checkout-agent-v42",
    metadata={"commit": "abc123"}
)

with run.trace_case("case_001") as case:
    case.log_tool_call(...)
    case.log_observation(...)
    case.complete(output=...)

gate = client.release_gates.evaluate(run.id)
```

### TypeScript SDK

```ts
import { Ashr } from "@ashr/sdk";

const client = new Ashr({ apiKey: process.env.ASHR_API_KEY });

const run = await client.runs.create({
  projectId: "proj_123",
  name: "support-agent-v12",
});

await run.case("case_001").record({
  input,
  output,
  toolCalls,
  trace,
});

const gate = await client.releaseGates.evaluate({ runId: run.id });
```

SDK 要补：

```text
typed models
retry
timeout
idempotency
streaming upload
redaction hooks
offline cache
CI mode
local mode
hosted mode
agent framework adapters
version compatibility
```

集成目标：

```text
OpenAI Agents SDK
LangChain
LlamaIndex
CrewAI
AutoGen
Vercel AI SDK
custom Python callable
custom TS function
GitHub Actions
CI artifact upload
```

---

## A1-4：任务队列和 Worker 系统

大型 SaaS 不能同步跑所有东西。A1 要补完整 job system。

任务类型：

```text
run_ingest
trace_normalize
judge_run
generate_evidence_bundle
release_gate_eval
report_export
regression_replay
semantic_judge_call
artifact_redaction
webhook_delivery
github_check_update
billing_meter_flush
```

要支持：

```text
queued/running/succeeded/failed/cancelled
retry
dead-letter queue
lease/heartbeat
worker autoscaling
job priority
tenant quota enforcement
backpressure
job cancellation
idempotent completion
```

这块 A1 当前已有 queue/replay 影子，后面要 productionize。

---

## A1-5：Artifact Storage 和 Trace Storage

大型 SaaS 里 trace/artifact 会很大。

A1 要补：

```text
object storage abstraction
signed upload URL
signed download URL
artifact manifest
checksum
content type validation
size limit
malware scan，可选
retention policy
artifact redaction
artifact encryption
```

Trace 存储要考虑：

```text
small trace 存 Postgres JSONB
large trace 存 object storage
event summary 存 DB
搜索字段单独索引
```

---

## A1-6：API Key / Auth / Security 底座

A1 要负责机器接入安全。

要补：

```text
API key create/revoke/rotate
API key prefix
hashed secret
scoped API keys
project-level key
org-level key
read-only key
CI key
last used timestamp
IP allowlist，可选
rate limit by key
audit log by key
```

还要补：

```text
request signing，可选
webhook signing
secret scanning
redaction pipeline
PII masking
encrypted credentials
```

---

## A1-7：Usage / Quota / Billing Meter

大型 SaaS 一定要能计费。

A1 要补真实 usage ledger：

```text
run_count
case_count
trace_event_count
observation_count
artifact_bytes
stored_bytes_days
judge_invocations
semantic_judge_tokens
replay_jobs
report_exports
api_requests
webhook_deliveries
```

并支持：

```text
hard quota
soft quota
overage
trial limits
enterprise custom limits
per-project budget
per-org budget
rate limit
billing meter export
```

---

## A1-8：基础设施和部署

A1 要补：

```text
Dockerfile
docker-compose for local dev
production deployment manifests
environment config
migration command
seed command
worker command
health check
readiness check
liveness check
```

生产上至少要有：

```text
API server
worker server
scheduler
Postgres
Redis
object storage
metrics
logs
traces
error tracking
```

---

## A1 最终交付标准

A1 补完后，应该做到：

```text
用户可以通过 SDK/API 提交真实 run
系统可靠接收、排队、存储、处理
所有数据按 org/project 隔离
usage/quota 可计量
trace/artifact 可安全存储
worker 可水平扩展
API 可稳定服务外部用户
```

---

# 3. A2 全量要补什么

A2 当前是 judge / scenario / taxonomy。大型 SaaS 下，A2 要成为 **评测智能和策略引擎负责人**。

---

## A2-1：Judge Service 化

现在 A2 更像本地库。大型 SaaS 要变成服务。

A2 要补：

```http
POST /internal/judge/run
POST /internal/judge/case
POST /internal/judge/batch
POST /internal/release-policy/evaluate
POST /internal/regression/replay
POST /internal/calibration/evaluate
```

输入：

```text
run_id
project_id
scenario_pack_id
judge_policy_id
trace_ref
case_results
expected behavior
tool policy
release thresholds
```

输出：

```text
judge_results
failure_classes
scores
confidence
evidence_refs
blocking_findings
recommended_actions
```

要支持异步 job，由 A1 worker 调度。

---

## A2-2：Judge Versioning

大型 SaaS 必须能回答：

```text
这个 release gate 是用哪个 judge 版本评的？
上周分数为什么和今天不一样？
升级 judge 后历史结果怎么办？
```

A2 要补：

```text
judge_version
scenario_pack_version
taxonomy_version
policy_version
calibration_version
semantic_prompt_version
model_version
```

每个 judge result 必须记录：

```text
judge_id
judge_version
input_hash
policy_hash
output_hash
created_at
```

支持：

```text
历史重评
版本比较
judge migration
deprecation
pin version
```

---

## A2-3：可配置 Release Policy

大型 SaaS 不能只有固定 judge。不同团队规则不同。

A2 要补 policy engine：

```json
{
  "policy_id": "release_policy_prod",
  "rules": [
    {
      "failure_class": "hallucinated_tool_result",
      "severity": "critical",
      "max_allowed": 0
    },
    {
      "failure_class": "wrong_arguments",
      "severity": "major",
      "max_allowed": 2
    },
    {
      "metric": "trace_completeness",
      "min": 0.98
    }
  ]
}
```

支持：

```text
per-project policy
per-environment policy
prod/staging/dev policy
branch-specific policy
waiver policy
approval policy
risk threshold
blocking/non-blocking modes
```

---

## A2-4：Scenario Library 产品化

现在 scenario 是 JSON pack。大型 SaaS 要变成场景库。

A2 要补：

```text
scenario CRUD
scenario tags
scenario categories
scenario owners
scenario difficulty
scenario capability axis
scenario expected tools
scenario expected facts
scenario forbidden behavior
scenario media requirements
scenario version history
scenario import/export
scenario review workflow
```

场景类型：

```text
tool-use
web-search
file-read
workflow-order
data-analysis
media
voice
safety
PII
secret leakage
recovery
clarification
multi-step agent
```

还要有：

```text
scenario templates
industry packs
team custom packs
public baseline packs
private org packs
```

---

## A2-5：Ground Truth / Expected Behavior 管理

大型 SaaS 中，评测质量取决于 ground truth。

A2 要补：

```text
expected final answer
expected tool calls
expected arguments
expected order
expected facts
forbidden facts
expected citations
required clarification
allowed variance
semantic equivalence rules
```

还要支持：

```text
human-labeled ground truth
review status
golden case promotion
failed case -> regression case
auto-suggest expected behavior
```

---

## A2-6：Semantic Judge / LLM Judge 生产化

当前 A2 有 semantic judge harness，但大型 SaaS 要完整生产化。

A2 要补：

```text
provider abstraction
OpenAI / Anthropic / Gemini / local model
prompt template versioning
cost ledger
token tracking
confidence score
human review queue
judge disagreement analysis
fallback deterministic judge
model timeout/retry
redaction before model call
private prompt storage policy
```

Semantic judge 输出要规范：

```json
{
  "passed": false,
  "score": 0.42,
  "confidence": 0.86,
  "primary_failure_class": "hallucinated_tool_result",
  "rationale": "...",
  "evidence_refs": ["trace_event_123"],
  "requires_human_review": false
}
```

---

## A2-7：Calibration 系统

大型 SaaS 需要证明 judge 可信。

A2 要补：

```text
calibration dataset
expected labels
judge output comparison
precision/recall by failure class
false positive analysis
false negative analysis
inter-judge agreement
human reviewer agreement
confidence calibration
drift detection
```

指标：

```text
accuracy
precision
recall
F1
false block rate
false pass rate
judge latency
cost per case
review override rate
```

---

## A2-8：Regression Intelligence

A2 应该自动把失败变成回归资产。

要补：

```text
failed case clustering
duplicate failure detection
root cause grouping
regression pack generation
old-vs-new agent comparison
baseline comparison
trend analysis
flaky case detection
case severity scoring
case owner recommendation
```

关键功能：

```text
Run A vs Run B
Agent version v1 vs v2
Prompt version old vs new
Model gpt-x vs gpt-y
Before/after release gate diff
```

---

## A2-9：Failure Taxonomy 企业化

当前 taxonomy 已经有基础，但大型 SaaS 要更丰富。

要补：

```text
severity
business impact
recommended remediation
owner role
SLA
blocking default
waiver eligibility
example traces
dashboard copy
```

例如：

```text
hallucinated_tool_result
severity: critical
default_gate: block
recommended_action: inspect grounding, require tool output citation
waiver_allowed: false in prod
```

---

## A2-10：Human Feedback Loop

大型 SaaS 里，用户一定会说：

```text
这个 judge 判错了
这个 case 不应该 block
这个 failure class 不准确
```

A2 要补：

```text
mark judge wrong
override failure class
approve waiver
promote case to golden
edit expected behavior
send to calibration queue
track reviewer agreement
learn policy suggestions
```

这会变成 A2 的长期壁垒。

---

## A2 最终交付标准

A2 补完后，应该做到：

```text
任何 run 都能被稳定评测
评测规则可配置、可版本化、可解释
judge 质量可量化
失败能归因、聚类、转回归
用户反馈能反哺 calibration
release policy 能服务不同团队/环境
```

---

# 4. A3 全量要补什么

A3 当前最像产品，但还是 static/mock-heavy。大型 SaaS 下，A3 要成为 **用户产品和控制台负责人**。

---

## A3-1：从 Static Dashboard 变成真实 Web App

A3 要把当前静态 HTML 拆成正式 app。

建议：

```text
Next.js / React
TypeScript
Tailwind / shadcn/ui
TanStack Query
Chart library
Component tests
E2E tests
```

需要模块化：

```text
layouts
navigation
tables
charts
trace viewer
diff viewer
case drawer
release gate card
report viewer
settings pages
billing pages
```

---

## A3-2：完整信息架构

大型 SaaS 的控制台至少要有：

```text
Home
Organizations
Projects
Datasets
Runs
Cases
Traces
Judge Results
Failure Clusters
Release Gates
Regression Packs
Reports
Integrations
API Keys
Usage & Billing
Team Settings
Audit Logs
Admin
```

A3 要设计导航结构，不然功能会淹没用户。

---

## A3-3：Onboarding Flow

大型 SaaS 成败很大程度取决于用户能不能 10 分钟接入。

A3 要补：

```text
signup
create org
create project
choose integration
copy API key
install SDK
run first eval
see first report
invite teammate
connect GitHub
```

最好有三条 onboarding：

```text
1. Upload JSON
2. Use Python SDK
3. Use GitHub Action
```

---

## A3-4：Project / Dataset / Run UI

A3 要做真实数据页面。

### Project 页面

```text
project overview
recent runs
release status
failure trends
connected integrations
policy summary
team members
```

### Dataset 页面

```text
case list
scenario tags
coverage
last run status
case owner
case version
```

### Run 页面

```text
run status
commit/branch
agent version
summary score
passed/failed cases
failure classes
duration
trace completeness
release gate result
```

---

## A3-5：Case Detail / Trace Viewer

这是产品核心。

A3 要补高级 trace UI：

```text
conversation timeline
tool calls
tool args
tool outputs
expected vs actual
field-level diff
judge evidence refs
raw JSON toggle
redacted view
artifact preview
media preview
latency timeline
error stack
```

还要支持：

```text
search within trace
copy evidence link
deep link to event
collapse/expand
compare expected/actual
```

---

## A3-6：Failure Triage 工作流

大型 SaaS 不只是看分数，而是修问题。

A3 要补：

```text
failure cluster page
assign owner
status: open / triaged / fixed / waived
severity
comments
labels
linked issue
linked PR
recommended regression case
```

这会变成团队协作功能。

---

## A3-7：Release Gate UI

A3 要把 release gate 做成核心产品。

页面要显示：

```text
PASS / BLOCKED / WARNING
blocking findings
policy rules
failed thresholds
waivers
required approvals
evidence bundle
PR check status
deployment recommendation
```

还要支持：

```text
request waiver
approve release
reject release
export report
share link
compare previous release
```

---

## A3-8：Reviewer Workflow

大型 SaaS 面向团队，必须有 reviewer。

A3 要补：

```text
review queue
pending approvals
assigned reviews
waiver requests
exception approvals
review comments
sign-off history
review SLA
audit trail
```

角色：

```text
developer
reviewer
release manager
admin
auditor
```

---

## A3-9：Reports / Evidence Sharing

A3 现在有报告导出雏形，但大型 SaaS 要做成产品。

要补：

```text
hosted report page
shareable link
private/public toggle
PDF export
Markdown export
JSON export
CSV export
PR comment
Slack summary
email report
audit bundle download
```

报告要有：

```text
executive summary
technical details
failed cases
trace evidence
policy result
waivers
approval chain
hash verification
```

---

## A3-10：Settings / Billing / Admin

大型 SaaS 必须有这些页面。

A3 要补：

```text
organization settings
project settings
team members
roles
API keys
webhooks
GitHub integration
Slack integration
billing plan
usage page
quota page
invoice page
retention policy
security settings
SSO settings
audit logs
```

---

## A3-11：Design System 和 UX 质量

大型 SaaS 不能靠一个长 HTML 文件维护。

A3 要补：

```text
design tokens
component library
empty states
loading states
error states
permission states
mobile/responsive
accessibility
keyboard navigation
dark mode，可选
```

关键页面要做：

```text
fast
clear
low cognitive load
action-oriented
```

不能让用户被 evidence/schema 淹没。

---

## A3-12：E2E 和前端质量

A3 要补：

```text
Playwright E2E
visual regression
component tests
API contract mocks
accessibility checks
performance budget
error boundary
analytics events
```

关键 E2E：

```text
signup -> create project -> upload run -> see gate
SDK submitted run -> dashboard appears
failed run -> triage -> waiver -> approve
GitHub PR -> check -> report page
```

---

## A3 最终交付标准

A3 补完后，应该做到：

```text
用户能自助完成接入
团队能看懂失败、分配修复、审批发布
release gate 能嵌入真实工程流程
报告能给 reviewer/manager/auditor 看
所有重要 SaaS 设置能在 UI 中完成
```

---

# 5. 三个人还要共同补的东西

有些东西不能只归 A1/A2/A3 某一个人，必须共同定义。

---

## 5.1 统一产品数据契约

必须共同定义：

```text
RunResult
CaseResult
TraceEvent
Observation
JudgeResult
FailureClass
ReleaseGateResult
EvidenceBundle
Policy
Scenario
Artifact
```

要有：

```text
JSON Schema
TypeScript types
Python types
DB model
API response model
migration strategy
```

A1/A2/A3 必须用同一套 contract。

---

## 5.2 大型 SaaS 的 tenancy 模型

必须统一：

```text
User
Org
Workspace
Project
Environment
Role
Permission
```

否则后面会重构很痛。

建议权限模型：

```text
org.owner
org.admin
project.admin
project.developer
project.reviewer
project.viewer
auditor
billing_admin
```

---

## 5.3 CI/CD 和发布纪律

必须补：

```text
GitHub Actions
branch protection
required checks
schema compatibility check
fixture drift check
secret scan
lint
typecheck
unit tests
integration tests
E2E tests
migration tests
```

---

## 5.4 安全与合规

大型 SaaS 必须有：

```text
data encryption
secret redaction
PII policy
audit logs
data retention
data deletion
access logs
admin impersonation controls
webhook signing
SSO/SAML later
SOC2 readiness later
```

---

## 5.5 生产观测

要补：

```text
structured logs
metrics
traces
error tracking
job monitoring
queue depth
API latency
judge latency
cost metrics
tenant usage metrics
alerting
incident response
```

---

# 6. 如果按优先级排，全量补齐路线应该这样

## 第一阶段：大型 SaaS 基础骨架

负责人：

```text
A1 主导
A3 配合
A2 接 judge service
```

要补：

```text
Auth
Org/Project model
Postgres
API
Run ingestion
Worker
Object storage
Basic dashboard API
```

---

## 第二阶段：核心用户闭环

负责人：

```text
A3 主导
A1 提供 API
A2 提供 judge
```

要补：

```text
Onboarding
Project page
Run upload
Run detail
Judge result
Release gate
Report page
GitHub Action
```

---

## 第三阶段：团队 SaaS

负责人：

```text
A3/A1 共同
A2 加 policy
```

要补：

```text
Team invite
RBAC
API keys
Usage quota
Billing
Reviewer workflow
Waiver/approval
Audit log
```

---

## 第四阶段：大型 SaaS / Enterprise

负责人：

```text
三方共同
```

要补：

```text
SSO/SAML
SCIM
Enterprise audit export
Custom retention
Advanced policy engine
Regression intelligence
Large-scale trace search
Admin console
Compliance docs
SLA
```

---

# 7. 最简洁的分工表

| 方向 | A1 要补 | A2 要补 | A3 要补 |
|---|---|---|---|
| SaaS 基础 | DB、API、SDK、queue、storage、quota | judge service API | app shell、auth UI、project UI |
| 用户接入 | SDK、CLI、GitHub Action backend | scenario selection | onboarding、integration guide |
| 核心处理 | run ingestion、trace normalization | judging、failure taxonomy、policy | run detail、trace viewer、failure UI |
| 发布门禁 | release gate API、webhook | policy evaluation、risk scoring | gate page、PR report、approval UI |
| 团队协作 | org/project permissions API | reviewer feedback model | review queue、comments、assignments |
| 商业化 | usage ledger、quota、billing meter | judge cost model | billing page、usage dashboard |
| 企业化 | audit log、SSO hooks、retention backend | versioned policy/calibration | admin settings、audit export UI |
| 生产化 | deployment、workers、monitoring | judge quality metrics | E2E、UX、performance |

---

# 8. 三个人的明确任务书

## A1 的任务书

> 把 Ashr 变成一个真正可接入、可扩展、可计费、可安全存储数据的 SaaS 平台后端。

必须交付：

```text
1. Postgres schema + migrations
2. Auth/org/project/run API
3. Python/TS SDK hosted submit
4. Worker/job system
5. Trace/artifact storage
6. API key management
7. Usage/quota/billing meter
8. Webhook/GitHub integration backend
9. Production deployment
10. Security/redaction baseline
```

---

## A2 的任务书

> 把 Ashr 的判断能力变成可配置、可解释、可版本化、可校准的评测智能服务。

必须交付：

```text
1. Judge service API
2. Judge versioning
3. Scenario library
4. Release policy engine
5. Semantic judge production path
6. Calibration metrics
7. Regression intelligence
8. Failure clustering
9. Human feedback loop
10. Policy templates for teams/enterprise
```

---

## A3 的任务书

> 把 Ashr 从静态控制台变成真正用户每天使用的 SaaS 产品。

必须交付：

```text
1. Next/React SaaS app
2. Onboarding flow
3. Project/dataset/run pages
4. Trace/case detail viewer
5. Failure triage workflow
6. Release gate UI
7. Reviewer/waiver/approval workflow
8. Reports/share/export
9. Settings/API keys/billing/team pages
10. E2E tests + design system
```

---

# 9. 最终判断

如果最终目标是大型 SaaS，三个人要补的不是“更多 demo 功能”，而是：

```text
A1 补生产平台能力
A2 补评测智能产品化
A3 补真实用户工作流
```

最关键的转变是：

```text
从 fixture-driven local factory
变成 multi-tenant hosted product
```

现在项目最强的是 **内核和概念密度**。

大型 SaaS 还要补的是：

```text
真实用户系统
真实数据系统
真实权限系统
真实计费系统
真实运维系统
真实协作工作流
```

如果三个人继续按 A1/A2/A3 分工推进，最合理的主线是：

```text
A1 先打 SaaS 后端骨架
A3 立刻接真实 API 做产品闭环
A2 暂停横向扩张，服务化 judge + policy
```

这样才是从现在这个强原型走向大型 SaaS 的最短路径。
