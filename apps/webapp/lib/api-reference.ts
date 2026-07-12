export type ApiOwner = "A1" | "A2" | "A3";
export type ApiMethod = "GET" | "POST" | "DELETE";
export type ApiStatus = "implemented" | "draft" | "blocked";

export type LocalizedText = {
  zh: string;
  en: string;
};

export type ApiEndpoint = {
  id: string;
  group: "identity" | "evidence" | "judge" | "console";
  owner: ApiOwner;
  method: ApiMethod;
  path: string;
  title: LocalizedText;
  description: LocalizedText;
  auth: LocalizedText;
  status: ApiStatus;
  source: string;
  request?: unknown;
  response: unknown;
  notes: LocalizedText[];
};

export const apiReferenceMeta = {
  schemaVersion: "a3.api_reference.v3",
  calibratedAt: "2026-07-12",
  mainSha: "ccf6ce5",
  a1Sha: "c784163",
  a2Sha: "8cd1d4f",
  a1SourceState: "merged_to_main",
  a2SourceState: "merged_to_main",
  secretValuesIncluded: false,
  a1BrowserSession: "implemented",
  a1OAuthInitialLogin: "not_implemented",
  a2TrustedSpine: "implemented",
  a2EvidenceSnapshotSchema: "a2.evidence_snapshot.v1",
  a2DecisionLedgerSchema: "a2.decision_ledger.v1",
  a2TrustedSpineSchema: "a2.trusted_spine_handoff.v1",
  a2RequiredScope: ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"],
  a2ValidationErrors: true,
  a3ReleaseCandidate: "0.2.0-rc.1"
} as const;

export const apiGroups = [
  { id: "all", label: { zh: "全部接口", en: "All endpoints" } },
  { id: "identity", label: { zh: "身份与 OAuth", en: "Identity & OAuth" } },
  { id: "evidence", label: { zh: "运行与证据", en: "Runs & evidence" } },
  { id: "judge", label: { zh: "评测与发布", en: "Judge & release" } },
  { id: "console", label: { zh: "控制台与报告", en: "Console & reports" } }
] as const;

export const apiEndpoints: ApiEndpoint[] = [
  {
    id: "a1-health",
    group: "identity",
    owner: "A1",
    method: "GET",
    path: "/v1/healthz",
    title: { zh: "服务健康检查", en: "Service health check" },
    description: {
      zh: "在发送登录或验证码请求前确认 A1 Go API 是否在线。",
      en: "Confirm that the A1 Go API is reachable before auth or verification requests."
    },
    auth: { zh: "公开，不需要密钥", en: "Public; no API key" },
    status: "implemented",
    source: "packages/go/ashrclone/server.go",
    response: { status: "ok" },
    notes: [
      { zh: "健康检查成功不代表 OAuth Provider、SMTP 或身份存储已经配置。", en: "A healthy process does not prove that OAuth, SMTP, or identity storage is configured." }
    ]
  },
  {
    id: "a1-google-start",
    group: "identity",
    owner: "A1",
    method: "POST",
    path: "/v1/projects/{project_id}/oauth/google/start",
    title: { zh: "连接 Google 凭据", en: "Connect Google credential" },
    description: {
      zh: "为已经登录的 Ashr 账号创建带 state、PKCE 和 nonce 的 Google 绑定事务。",
      en: "Create a state, PKCE, and nonce protected Google linking transaction for an already signed-in Ashr account."
    },
    auth: { zh: "需要 A1 可信身份会话与租户范围", en: "Requires a trusted A1 identity session and tenant scope" },
    status: "implemented",
    source: "A1 c784163 / oauth_provider_http.go",
    request: { tenant_id: "tenant_example" },
    response: {
      schema_version: "ashr.oauth.google.v1",
      provider: "google",
      authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?...",
      expires_at: "2026-07-11T12:10:00Z"
    },
    notes: [
      { zh: "该账号绑定能力已随 A1 c784163 合并到 main；它仍不等于首次 Google 登录。", en: "This account-linking capability entered main with A1 c784163; it is still not initial Google sign-in." },
      { zh: "这是账号绑定接口，不是首次 Google 登录入口；A3 登录页保持关闭。", en: "This is account linking, not an initial Google sign-in endpoint; A3 keeps it disabled on the login page." },
      { zh: "A3 不接收或保存 client secret、authorization code、token。", en: "A3 never receives or stores client secrets, authorization codes, or tokens." }
    ]
  },
  {
    id: "a1-github-start",
    group: "identity",
    owner: "A1",
    method: "POST",
    path: "/v1/projects/{project_id}/oauth/github/start",
    title: { zh: "连接 GitHub 凭据", en: "Connect GitHub credential" },
    description: {
      zh: "为已经登录的 Ashr 账号创建 GitHub 凭据绑定事务。",
      en: "Create a GitHub credential-linking transaction for an already signed-in Ashr account."
    },
    auth: { zh: "需要 A1 可信身份会话与租户范围", en: "Requires a trusted A1 identity session and tenant scope" },
    status: "implemented",
    source: "A1 c784163 / oauth_provider_http.go",
    request: { tenant_id: "tenant_example" },
    response: {
      schema_version: "ashr.oauth.github.v1",
      provider: "github",
      authorize_url: "https://github.com/login/oauth/authorize?...",
      expires_at: "2026-07-11T12:10:00Z"
    },
    notes: [
      { zh: "浏览器只跳转到 A1 返回的 GitHub 官方域名。", en: "The browser may redirect only to the official GitHub provider host returned by A1." },
      { zh: "这是账号绑定接口，不是首次 GitHub 登录入口；A3 登录页保持关闭。", en: "This is account linking, not an initial GitHub sign-in endpoint; A3 keeps it disabled on the login page." },
      { zh: "调用方不能用 account_id 把 Provider 凭据绑到别人的账号。", en: "A caller-supplied account_id cannot bind a provider credential to another account." }
    ]
  },
  {
    id: "a1-oauth-callback",
    group: "identity",
    owner: "A1",
    method: "GET",
    path: "/oauth/{provider}/callback",
    title: { zh: "OAuth 回调", en: "OAuth callback" },
    description: {
      zh: "由 Google 或 GitHub 回调 A1，A1 校验 state、交换 token 并建立统一身份凭据。",
      en: "Google or GitHub calls A1, which validates state, exchanges the code, and binds a unified identity credential."
    },
    auth: { zh: "公开回调入口；state/PKCE/nonce 由 A1 校验", en: "Public callback; A1 validates state, PKCE, and nonce" },
    status: "implemented",
    source: "A1 c784163 / oauth_provider_http.go",
    response: {
      schema_version: "ashr.oauth_connection.v1",
      provider: "google",
      connection: { account_id: "account_example", provider_subject_present: true, email_present: true }
    },
    notes: [
      { zh: "当前回调返回 JSON；生产产品还需要 A1 设置安全会话并跳回 Webapp。", en: "The current callback returns JSON; production still needs A1 to establish a secure session and redirect to the webapp." }
    ]
  },
  {
    id: "a1-verification-start",
    group: "identity",
    owner: "A1",
    method: "POST",
    path: "/v1/identity-verification/challenges",
    title: { zh: "请求邮箱验证码", en: "Request email verification" },
    description: {
      zh: "请求发送 6 位邮箱验证码。公开响应始终保持一致，避免泄露邮箱是否已经注册。",
      en: "Request a six-digit email code. The public response stays uniform to prevent account enumeration."
    },
    auth: { zh: "注册用途公开；绑定用途需要可信会话", en: "Public for registration; trusted session required for credential binding" },
    status: "implemented",
    source: "A1 c784163 / identity_verification_http.go",
    request: {
      channel: "email",
      identifier: "student@example.test",
      purpose: "binding",
      tenant_id: "tenant_example"
    },
    response: {
      schema_version: "ashr.identity_verification_security.v1",
      status: "accepted",
      message: "If the request is eligible, verification instructions will be sent."
    },
    notes: [
      { zh: "响应不会返回 challenge_id，这是 A1 的防枚举设计。", en: "The response intentionally omits challenge_id as an anti-enumeration control." },
      { zh: "A3 不在日志、localStorage 或文档中记录邮箱与验证码。", en: "A3 does not persist email addresses or codes in logs, localStorage, or documentation." }
    ]
  },
  {
    id: "a1-verification-complete",
    group: "identity",
    owner: "A1",
    method: "POST",
    path: "/v1/identity-verification/verify",
    title: { zh: "完成邮箱验证", en: "Complete email verification" },
    description: {
      zh: "校验一次性验证码并创建账号或绑定已验证邮箱凭据。",
      en: "Verify a single-use code and create an account or bind a verified email credential."
    },
    auth: { zh: "需要验证码和服务端签发的 challenge 上下文", en: "Requires the code and server-issued challenge context" },
    status: "blocked",
    source: "A1 c784163 / identity_verification_http.go",
    request: {
      challenge_id: "challenge_from_secure_mail_context",
      code: "123456",
      channel: "email",
      identifier: "student@example.test",
      purpose: "binding",
      tenant_id: "tenant_example",
      display_name: "Example student"
    },
    response: {
      schema_version: "ashr.identity_verification.v1",
      credential_created: true,
      account: { account_id: "account_example", status: "active" },
      credential: { kind: "email", verified: true }
    },
    notes: [
      { zh: "当前 A1 纯文本邮件没有 challenge_id，浏览器无法闭环；A3 已提交 contract change request。", en: "The current A1 plaintext email omits challenge_id, so the browser flow cannot close; A3 has filed a contract change request." },
      { zh: "A1 c784163 已能在 login/recovery 验证成功后签发 Secure、HttpOnly、SameSite=Strict 的访问与刷新 Cookie；binding 注册仍不会创建登录会话。", en: "A1 c784163 can issue Secure, HttpOnly, SameSite=Strict access and refresh cookies after login/recovery verification; binding registration still does not create a signed-in session." },
      { zh: "在 A1 修复前，A3 只会展示真实阻塞状态，不伪造注册成功。", en: "Until A1 closes the contract, A3 shows the real blocker and never fakes successful registration." }
    ]
  },
  {
    id: "a1-session-refresh",
    group: "identity",
    owner: "A1",
    method: "POST",
    path: "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh",
    title: { zh: "轮换浏览器会话", en: "Rotate browser session" },
    description: {
      zh: "使用 HttpOnly 刷新 Cookie 原子轮换访问与刷新凭据，并检测旧凭据重复使用。",
      en: "Atomically rotate access and refresh credentials through HttpOnly cookies and detect reuse of an old refresh credential."
    },
    auth: { zh: "同源 HTTPS、访问/刷新 Cookie、Idempotency-Key", en: "Same-origin HTTPS, access/refresh cookies, and Idempotency-Key" },
    status: "implemented",
    source: "A1 c784163 / identity_verification_http.go",
    request: {
      "$headers": { "Idempotency-Key": "a3-refresh-example-id" },
      "$body": null
    },
    response: {
      schema_version: "ashr.identity_session_refresh.v1",
      status: "rotated"
    },
    notes: [
      { zh: "A3 只能触发轮换，不能读取 HttpOnly Cookie 或 bearer 内容。", en: "A3 may trigger rotation but cannot read HttpOnly cookies or bearer material." },
      { zh: "A1 要求请求 Origin 与 API Host 完全一致；跨域静态预览不能调用。", en: "A1 requires the request Origin and API Host to match exactly; a cross-origin static preview cannot call this route." },
      { zh: "该能力已随 A1 c784163 进入 main；跨域静态预览仍不能执行同源 Cookie 轮换。", en: "This capability entered main with A1 c784163; a cross-origin static preview still cannot rotate same-origin cookies." }
    ]
  },
  {
    id: "a1-run-submit",
    group: "evidence",
    owner: "A1",
    method: "POST",
    path: "/v1/projects/{project_id}/runs/submit",
    title: { zh: "提交 Agent 运行", en: "Submit an agent run" },
    description: {
      zh: "由 A1 接收运行、案例、Observation、TraceEvent 和 ToolCall 的事实证据。",
      en: "Let A1 ingest run, case, Observation, TraceEvent, and ToolCall facts."
    },
    auth: { zh: "项目 API key 与 run 写权限", en: "Project API key with run write scope" },
    status: "implemented",
    source: "docs/a1/schemas/run_result.schema.json",
    request: { run_id: "run_example", status: "completed", cases: [{ case_id: "case_refund_001", trace_events: [] }] },
    response: { accepted: true, run_id: "run_example" },
    notes: [
      { zh: "A1 是执行事实的唯一权威；A3 只读取并展示。", en: "A1 is the authority for execution facts; A3 only reads and presents them." }
    ]
  },
  {
    id: "a1-trace-events",
    group: "evidence",
    owner: "A1",
    method: "POST",
    path: "/v1/projects/{project_id}/runs/{run_id}/trace-events",
    title: { zh: "追加 Trace 事件", en: "Append trace events" },
    description: {
      zh: "追加按顺序排列的 Agent 响应、工具调用和工具结果事件。",
      en: "Append ordered agent-response, tool-call, and tool-result events."
    },
    auth: { zh: "项目 API key 与 trace 写权限", en: "Project API key with trace write scope" },
    status: "implemented",
    source: "docs/a1/schemas/trace_event.schema.json",
    request: { event_id: "trace_001", seq: 1, event_type: "tool_call", observation: { kind: "tool_call", status: "ok" } },
    response: { accepted: true },
    notes: [
      { zh: "媒体证据只保存对象引用或签名 URL 元数据，不内嵌私有二进制。", en: "Media evidence uses object references or signed-URL metadata, never embedded private binaries." }
    ]
  },
  {
    id: "a2-judge-case",
    group: "judge",
    owner: "A2",
    method: "POST",
    path: "/internal/judge/case",
    title: { zh: "评判单个案例", en: "Grade one case" },
    description: {
      zh: "A2 根据 Scenario 和 Rubric 对 A1 案例证据给出 score、pass/fail 与 failure class。",
      en: "A2 grades A1 case evidence against a Scenario and Rubric, producing score, pass/fail, and failure class."
    },
    auth: { zh: "仅内部服务调用", en: "Internal service only" },
    status: "implemented",
    source: "A2 8cd1d4f / a2_judge_service.openapi.json",
    request: { case_id: "case_refund_001", scenario_id: "refund_policy_001", expected: {}, actual: {}, trace_events: [] },
    response: { case_id: "case_refund_001", passed: false, score: 0.42, primary_failure_class: "missing_required_tool" },
    notes: [
      { zh: "A2 是评分和发布判定的唯一权威；A3 不重新计算分数。", en: "A2 is the sole authority for grading and release decisions; A3 does not recalculate scores." },
      { zh: "A2 8cd1d4f 的 public-safe evidence snapshot 会校验 A1 RunResult、五层作用域和 validation_errors。", en: "A2 8cd1d4f validates the A1 RunResult, five-level scope, and validation_errors in its public-safe evidence snapshot." }
    ]
  },
  {
    id: "a2-release-policy",
    group: "judge",
    owner: "A2",
    method: "POST",
    path: "/internal/release-policy/evaluate",
    title: { zh: "评估发布策略", en: "Evaluate release policy" },
    description: {
      zh: "把批量评测结果转成 allow、review 或 block 的发布门禁决定。",
      en: "Turn batch grades into an allow, review, or block release-gate decision."
    },
    auth: { zh: "仅内部服务调用", en: "Internal service only" },
    status: "implemented",
    source: "A2 8cd1d4f / a2_judge_service.openapi.json",
    request: { grade_results: [], policy_id: "default_release_policy" },
    response: { schema_version: "a2.release_gate.v1", decision: "block", risk_score: 88, blockers: [] },
    notes: [
      { zh: "人工批准、拒绝或 waiver 必须保留 A2 原始决定和证据来源。", en: "Human approval, denial, or waiver must preserve the original A2 decision and evidence provenance." },
      { zh: "A2 8cd1d4f 的 append-only decision ledger 绑定完整五层作用域；A3 只能展示 decision、record hash 和链验证状态，不能改写账本。", en: "A2 8cd1d4f binds the full five-level scope into its append-only decision ledger; A3 may display the decision, record hash, and chain status but may not rewrite it." }
    ]
  },
  {
    id: "a3-dashboard",
    group: "console",
    owner: "A3",
    method: "GET",
    path: "/api/a3/dashboard",
    title: { zh: "读取控制台快照", en: "Read dashboard snapshot" },
    description: {
      zh: "把 A1 执行证据和 A2 判定组合成 A3 可读的产品视图。",
      en: "Compose A1 execution evidence and A2 decisions into the A3 product view."
    },
    auth: { zh: "A1 服务端验证身份 + A3 RBAC + 五层租户范围", en: "A1 server-verified principal, A3 RBAC, and five-level tenant scope" },
    status: "implemented",
    source: "docs/a3/openapi/a3_commercial_api.openapi.json",
    response: {
      source: "api-mock",
      summary: { totalRuns: 4, totalCases: 32, passed: 18, failed: 14 },
      a1_a2_evidence_spine: { a1_authority: "execution facts", a2_authority: "grade and release decision" },
      delivery_golden_path: { status: "blocked_by_a2", production_ready: false },
      deployment_acceptance: { status: "blocked", production_accepted: false },
      release_artifact_manifest: { release: { version: "0.2.0-rc.1", production_release: false } }
    },
    notes: [
      { zh: "这是当前 Next.js Webapp 默认消费的只读 API。", en: "This is the read-only API consumed by the current Next.js webapp." },
      { zh: "交付闭环字段只汇总 A1/A2 权威证据；A3 不重算 A2 分数或发布决定。", en: "Delivery fields summarize authoritative A1/A2 evidence; A3 does not recompute A2 scores or release decisions." }
    ]
  },
  {
    id: "a3-report-share",
    group: "console",
    owner: "A3",
    method: "POST",
    path: "/api/a3/reports/share",
    title: { zh: "创建分享报告", en: "Create a shared report" },
    description: {
      zh: "通过脱敏防火墙后生成可过期、可撤销并带审计记录的报告链接。",
      en: "Create an expiring, revocable, audited report link after redaction checks."
    },
    auth: { zh: "报告写权限与租户范围", en: "Report write role and tenant scope" },
    status: "draft",
    source: "docs/a3/openapi/a3_commercial_api.openapi.json",
    request: { report_id: "report_example", expires_in_seconds: 86400 },
    response: { report_id: "report_example", status: "active", share_url: "https://reports.example.test/r/redacted" },
    notes: [
      { zh: "本地已经有契约和存储测试；真实托管域名与对象存储仍需云端部署。", en: "Local contracts and storage tests exist; a hosted domain and object storage still require deployment." }
    ]
  }
];
