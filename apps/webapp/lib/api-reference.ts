export type ApiOwner = "A1" | "A2" | "A3" | "A1/A2/A3";
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
  schemaVersion: "a3.api_reference.v16",
  calibratedAt: "2026-07-15",
  mainSha: "ccf6ce5",
  a1Sha: "c784163",
  a2Sha: "8cd1d4f",
  a1SourceState: "merged_to_main",
  a2SourceState: "merged_to_main",
  a1IdentityPeerSha: "6a985b8",
  a1IdentityPeerState: "peer_branch_identity_authority_readiness_not_merged",
  a1LatestPeerSha: "566a13d",
  a1LatestPeerState: "peer_branch_round68_authorized_credential_binding_regression_not_client_callable",
  a1AtomicCredentialLinkContract: "IdentityCredentialLinkCoordinator",
  a1AtomicCredentialLinkRouteLifecycle: "proposed",
  a1AtomicCredentialLinkClientCallable: false,
  a1CredentialLinkReplayRetentionDays: 30,
  a1CredentialLinkReadinessRouteAvailable: false,
  a2MultimodalPeerSha: "bb3bcfe",
  a2MultimodalPeerState: "peer_branch_contract_not_merged",
  a2LatestPeerSha: "850b39a",
  a2LatestPeerState: "peer_branch_round52_controls_runtime_public_summary_ingested_non_authoritatively",
  a2CurrentRemoteSha: "850b39a",
  a2CurrentRemoteState: "peer_branch_round52_current_not_main_authority",
  a2MultimodalSupportedSchemas: [
    "a2.multimodal_cross_provider_comparison.v1",
    "a2.multimodal_cross_provider_comparison.v3",
    "a2.multimodal_three_way_comparison.v2"
  ],
  a2MultimodalRepeatSchema: "a2.multimodal_multi_repeat_comparison.v2",
  a2MultimodalRepeatSupportedSchemas: [
    "a2.multimodal_multi_repeat_comparison.v1",
    "a2.multimodal_multi_repeat_comparison.v2"
  ],
  a2MultimodalReleaseReadinessSummarySchema: "a2.multimodal_public_summary.round52.v1",
  a3MultimodalReleaseReadinessSchema: "a3.multimodal_release_readiness.v1",
  secretValuesIncluded: false,
  a1BrowserSession: "implemented",
  a1OAuthInitialLogin: "not_implemented",
  a2TrustedSpine: "implemented",
  a2EvidenceSnapshotSchema: "a2.evidence_snapshot.v1",
  a2DecisionLedgerSchema: "a2.decision_ledger.v1",
  a2TrustedSpineSchema: "a2.trusted_spine_handoff.v1",
  a2RequiredScope: ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"],
  a2ValidationErrors: true,
  a3ReleaseCandidate: "0.2.0-rc.2"
} as const;

const exampleSha256 = `sha256:${"0".repeat(64)}`;

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
      { zh: "A3 不接收或保存 client secret、authorization code、token。", en: "A3 never receives or stores client secrets, authorization codes, or tokens." },
      { zh: "A1 peer 566a13d 已证明凭据绑定只能经过带近期会话、step-up 和 mutation ticket 的授权包装器，并保留 Round 67 的 30 天 replay 清理能力；统一 identity 客户端路由仍未暴露。", en: "A1 peer 566a13d proves credential binding can only use the authorized wrapper with a recent session, step-up receipt, and mutation ticket while retaining Round 67's 30-day replay cleanup; the unified-identity client route remains unexposed." }
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
    id: "a3-multimodal-comparison-import",
    group: "judge",
    owner: "A1/A2/A3",
    method: "POST",
    path: "/api/a3/import/a2-multimodal-comparison",
    title: { zh: "导入多模态模型比较", en: "Import multimodal model comparison" },
    description: {
      zh: "接收公开安全的跨模型比较和人工复核排队回执，绑定到服务端验证的五层租户范围。",
      en: "Ingest a public-safe cross-model comparison and human-review queue receipts into a server-verified five-level tenant scope."
    },
    auth: { zh: "服务端验证身份 + project:ingest + Idempotency-Key", en: "Server-verified principal, project:ingest, and Idempotency-Key" },
    status: "implemented",
    source: "评测服务 564d4b0 双路 v3 契约校准 / 产品 OpenAPI",
    request: {
      source: "api-ingest",
      comparison: {
        schema_version: "a2.multimodal_cross_provider_comparison.v3",
        comparison_artifact_hash: exampleSha256,
        left_evidence_hash: exampleSha256,
        right_evidence_hash: exampleSha256,
        left_binding: { provider_id: "provider-left", model_id: "model-left", model_version: "version-left", prompt_hash: exampleSha256 },
        right_binding: { provider_id: "provider-right", model_id: "model-right", model_version: "version-right", prompt_hash: exampleSha256 },
        comparisons: [{
          case_id: "case-media-001",
          artifact_hash: exampleSha256,
          repeat: 1,
          left_state: "valid_json",
          right_state: "valid_json",
          left_observed_risk: true,
          right_observed_risk: false,
          comparison_state: "semantic_disagreement",
          human_review_required: true
        }],
        summary: { agreement: 0, semantic_disagreement: 1, unavailable: 0 },
        aggregate_comparisons: [],
        aggregate_summary: { agreement: 0, semantic_disagreement: 0, unavailable: 0, internally_unstable: 0 },
        human_review_queue_receipts: [{
          receipt_id: exampleSha256,
          comparison_artifact_hash: exampleSha256,
          comparison_hash: exampleSha256,
          artifact_hash: exampleSha256,
          case_id: "case-media-001",
          review_scope: "repeat",
          queue_state: "awaiting_human_review",
          reviewer_role: "multimodal_safety_reviewer",
          release_authority: false
        }],
        release_authority: false,
        raw_payload_included: false,
        public_safe: true
      }
    },
    response: {
      schema_version: "a3.a2_multimodal_comparison_ingest.v1",
      comparison_count: 1,
      review_required_count: 1,
      upstream_release_authority: false,
      candidate_binding_verified: false,
      release_decision_changed: false
    },
    notes: [
      { zh: "服务端拒绝原始模型载荷、URL、Secret、错误摘要、孤立队列回执和伪造发布权。", en: "The server rejects raw model payloads, URLs, secrets, inconsistent summaries, orphan receipts, and fabricated release authority." },
      { zh: "当前向后兼容双路 v1，支持双路 v3 的重复观察、聚合不稳定和回执守恒，并已根据 A2 Round 50 的公开安全实物接入三路 v2；四路 v1 仍等待可复现样本。", en: "The adapter remains backward-compatible with two-way v1, supports v3 repeats, aggregate instability, and receipt conservation, and now consumes three-way v2 from the real public-safe A2 Round 50 artifact; four-way v1 still awaits a reproducible sample." },
      { zh: "导入只形成可审计的审核队列投影，不会改写分数、风险或发布决定。", en: "Import creates an auditable review-queue projection and never rewrites scores, risk, or release decisions." }
    ]
  },
  {
    id: "a3-multimodal-repeat-stability-import",
    group: "judge",
    owner: "A1/A2/A3",
    method: "POST",
    path: "/api/a3/import/a2-multimodal-repeat-stability",
    title: { zh: "导入多轮校准稳定性", en: "Import multi-repeat calibration stability" },
    description: {
      zh: "原子接收多轮比较、真人复核守恒状态和同一候选版本校验，生成只读稳定性证据。",
      en: "Atomically ingest multi-repeat comparison, human-review conservation, and same-candidate verification into read-only stability evidence."
    },
    auth: { zh: "服务端验证身份 + project:ingest + Idempotency-Key", en: "Server-verified principal, project:ingest, and Idempotency-Key" },
    status: "implemented",
    source: "评测服务 Round 51 公开安全样本 / 产品 OpenAPI",
    request: {
      source: "api-ingest",
      stability_evidence: {
        schema_version: "a3.a2_multimodal_repeat_stability_intake.v1",
        source_commit_alias: "7504680",
        comparison: {
          schema_version: "a2.multimodal_multi_repeat_comparison.v1",
          repeat_count: 3,
          all_required_units_complete: true,
          retained_calibration_states: ["blocked", "blocked", "blocked"],
          promotion_eligible: false,
          release_authority: false
        },
        review_collection: { collection_state: "pending", receipts: [], release_authority: false },
        shared_candidate_verification: { verified: false, blockers: ["shared_candidate_id_mismatch"] },
        release_authority: false,
        public_safe: true
      }
    },
    response: {
      schema_version: "a3.a2_multimodal_repeat_stability_ingest.v1",
      repeat_count: 3,
      retained_blocked_count: 3,
      all_required_units_complete: true,
      human_review_receipt_count: 0,
      shared_candidate_verified: false,
      upstream_release_authority: false,
      a2_decision_recomputed: false,
      release_decision_changed: false
    },
    notes: [
      { zh: "只接受哈希、聚合指标、计数、状态和原因码；原始模型内容、URL、签名媒体地址和身份会被拒绝。", en: "Only hashes, aggregate metrics, counts, states, and reason codes are accepted; raw provider content, URLs, signed media links, and identity are rejected." },
      { zh: "三轮结果完全一致只说明问题稳定可复现，不代表质量合格。", en: "Three identical repeats prove stable reproducibility, not qualified quality." },
      { zh: "当前真人回执对象的精确契约尚未发布，因此非空回执会失败关闭。", en: "Non-empty human receipts fail closed until their exact authoritative object schema is published." }
    ]
  },
  {
    id: "a3-multimodal-repeat-stability-read",
    group: "judge",
    owner: "A3",
    method: "GET",
    path: "/api/a3/review/multimodal-repeat-stability",
    title: { zh: "读取多轮校准稳定性", en: "Read multi-repeat calibration stability" },
    description: {
      zh: "返回租户范围内的多轮指标、质量阻塞、真人复核待办和候选版本绑定状态。",
      en: "Return tenant-scoped repeat metrics, quality blockers, human-review backlog, and candidate-binding state."
    },
    auth: { zh: "服务端验证身份 + release:review + 五层租户范围", en: "Server-verified principal, release:review, and five-level tenant scope" },
    status: "implemented",
    source: "docs/a3/openapi/a3_commercial_api.openapi.json",
    response: {
      schema_version: "a3.multimodal_repeat_stability.v1",
      status: "blocked_stable_repeat",
      summary: {
        repeat_count: 3,
        required_source_unit_count: 45,
        stable_observation: true,
        quality_qualified: false,
        promotion_eligible: false
      },
      metrics: [
        { metric_id: "specificity", repeat_estimates: [0.95, 0.95, 0.95] },
        { metric_id: "visual_prompt_injection_sensitivity", repeat_estimates: [0.6, 0.6, 0.6] }
      ],
      human_review: { collection_state: "pending", receipt_count: 0, pending_queue_receipt_count: 1 },
      candidate_binding: { verified: false },
      authority_boundary: { release_authority: false, a2_decision_recomputed: false, production_ready: false }
    },
    notes: [
      { zh: "产品结论是“完整且稳定，但质量未达标”，而不是通过。", en: "The product conclusion is complete and stable, but quality is not qualified, never a pass." },
      { zh: "该接口不能创建真人处置、重算评分或改变发布决定。", en: "This endpoint cannot create a human disposition, recompute grading, or change release state." },
      { zh: "跨租户读取返回 404，不泄露指标、哈希或阻塞原因。", en: "Cross-tenant reads return 404 without exposing metrics, hashes, or blocker reasons." }
    ]
  },
  {
    id: "a3-multimodal-provider-readiness-import",
    group: "judge",
    owner: "A1/A2/A3",
    method: "POST",
    path: "/api/a3/import/a2-multimodal-provider-readiness",
    title: { zh: "导入多模态 Provider 就绪度诊断", en: "Import multimodal provider readiness diagnostics" },
    description: {
      zh: "原子接收 A2 的模型可用性比较和阶段延迟诊断，并生成公开安全、租户隔离的产品投影。",
      en: "Atomically ingest A2 model-availability comparison and phase-latency diagnostics into a public-safe, tenant-scoped product projection."
    },
    auth: { zh: "服务端验证身份 + project:ingest + Idempotency-Key", en: "Server-verified principal, project:ingest, and Idempotency-Key" },
    status: "implemented",
    source: "评测服务 Round 51 Provider 证据源 7504680 / 产品 OpenAPI",
    request: {
      source: "api-ingest",
      provider_readiness_evidence: {
        schema_version: "a3.a2_multimodal_provider_readiness_intake.v1",
        source_commit_alias: "7504680",
        availability_comparison: {
          schema_version: "a2.local_multimodal_availability_comparison.v1",
          same_case_set: true,
          providers: {
            "llava:7b": { attempted_count: 15, completed_count: 1, failed_count: 14, timeout_case_count: 14, eligible_count: 0, qualification_state: "blocked" },
            "qwen3-vl:4b": { attempted_count: 15, completed_count: 0, failed_count: 15, timeout_case_count: 15, eligible_count: 0, qualification_state: "blocked" }
          },
          quality_comparison_performed: false,
          provider_is_truth: false,
          release_authority: false
        },
        latency_probe: {
          schema_version: "a2.ollama_multimodal_latency_probe.v1",
          provider_id: "ollama-local",
          model_id: "qwen3-vl:4b",
          completed_profile_count: 0,
          qualification_state: "blocked",
          release_authority: false
        },
        release_authority: false,
        public_safe: true,
        raw_provider_payload_included: false
      }
    },
    response: {
      schema_version: "a3.a2_multimodal_provider_readiness_ingest.v1",
      provider_count: 2,
      attempted_count: 30,
      completed_count: 1,
      failed_count: 29,
      timeout_case_count: 29,
      eligible_count: 0,
      completed_profile_count: 0,
      valid_structured_profile_count: 0,
      upstream_release_authority: false,
      quality_comparison_performed: false,
      operational_health_verified: false,
      release_decision_changed: false
    },
    notes: [
      { zh: "可用性比较和阶段延迟必须作为一个原子信封导入；任一部分不合法都会整包拒绝。", en: "Availability and phase latency must arrive in one atomic envelope; any invalid part rejects the whole import." },
      { zh: "安装成功、偶尔完成或 warm 延迟变快都不等于运行健康、质量合格或发布批准。", en: "Installation, an occasional completion, or faster warm latency does not prove operational health, qualified quality, or release approval." },
      { zh: "A1 继续拥有生产路由、容量和运行健康；A2 拥有评测与资格；A3 只验证、展示、导出和协调。", en: "A1 retains production routing, capacity, and health; A2 owns evaluation and qualification; A3 validates, displays, exports, and coordinates." }
    ]
  },
  {
    id: "a3-multimodal-provider-readiness-read",
    group: "judge",
    owner: "A3",
    method: "GET",
    path: "/api/a3/providers/multimodal-readiness",
    title: { zh: "读取多模态 Provider 就绪度", en: "Read multimodal provider readiness" },
    description: {
      zh: "返回模型尝试、完成、失败、超时、合格输出和阶段延迟的租户范围诊断。",
      en: "Return tenant-scoped model attempts, completions, failures, timeouts, eligible outputs, and phase-latency diagnostics."
    },
    auth: { zh: "服务端验证身份 + release:review + 五层租户范围", en: "Server-verified principal, release:review, and five-level tenant scope" },
    status: "implemented",
    source: "docs/a3/openapi/a3_commercial_api.openapi.json",
    response: {
      schema_version: "a3.multimodal_provider_readiness.v1",
      status: "blocked_provider_readiness",
      summary: {
        provider_count: 2,
        attempted_count: 30,
        completed_count: 1,
        failed_count: 29,
        timeout_case_count: 29,
        eligible_count: 0,
        profile_count: 4,
        completed_profile_count: 0,
        valid_structured_profile_count: 0,
        quality_comparison_performed: false,
        operational_health_verified: false,
        routing_ready: false,
        capacity_verified: false
      },
      latency_diagnostic: { cold_wall_seconds: 74.299641, fastest_warm_wall_seconds: 1.64026 },
      authority_boundary: { routing_or_capacity_authority: "A1", evaluation_and_qualification_authority: "A2", release_authority: false, production_ready: false }
    },
    notes: [
      { zh: "当前真实校准结论是 blocked_provider_readiness：30 次尝试只有 1 次完成、29 次失败或超时、0 个合格输出。", en: "The current real calibration is blocked_provider_readiness: 1 completion, 29 failures or timeouts, and 0 eligible outputs across 30 attempts." },
      { zh: "四个阶段诊断档位都没有通过结构化输出校验，因此冷启动与 warm 延迟差异只能用于排障。", en: "All four phase profiles failed structured-output validation, so cold versus warm latency is diagnostic only." },
      { zh: "响应不含 endpoint URL、Secret、原始回复、模型二进制或私有媒体。", en: "The response excludes endpoint URLs, secrets, raw responses, model binaries, and private media." }
    ]
  },
  {
    id: "a3-multimodal-review-queue",
    group: "judge",
    owner: "A3",
    method: "GET",
    path: "/api/a3/review/multimodal-queue",
    title: { zh: "读取多模态分歧审核队列", en: "Read multimodal disagreement queue" },
    description: {
      zh: "为 Reviewer 返回租户范围内的模型分歧、媒体证据哈希和非权威排队状态。",
      en: "Return tenant-scoped model disagreements, media-evidence hashes, and non-authoritative queue state for reviewers."
    },
    auth: { zh: "服务端验证身份 + release:review + 五层租户范围", en: "Server-verified principal, release:review, and five-level tenant scope" },
    status: "implemented",
    source: "docs/a3/openapi/a3_commercial_api.openapi.json",
    response: {
      schema_version: "a3.multimodal_review_queue.v1",
      status: "human_review_required",
      source_contract: "a2.multimodal_three_way_comparison.v2",
      summary: { comparison_count: 3, provider_count: 3, semantic_disagreement: 1, review_required_count: 1, assignment_event_count: 1 },
      provider_set: {
        provider_count: 3,
        providers: [
          { provider_key: "dashscope_run_a", provider_identity_included: false, model_identity_included: false },
          { provider_key: "dashscope_run_b", provider_identity_included: false, model_identity_included: false },
          { provider_key: "qwen3vl_local", provider_identity_included: false, model_identity_included: false }
        ]
      },
      authority_boundary: { can_change_release_decision: false, candidate_binding_verified: false },
      items: []
    },
    notes: [
      { zh: "跨租户请求返回 404 或空结果，不泄露模型、案例或证据哈希。", en: "Cross-tenant requests return 404 or no records without revealing models, cases, or evidence hashes." },
      { zh: "每个案例可以返回仅含哈希别名、版本、时间、原因码和事件哈希的 assignment_history；不包含原始身份。", en: "Each case may return assignment_history containing hash aliases, versions, times, reason codes, and event hashes only; raw identity is excluded." },
      { zh: "只有权威人工复核结果与同一候选版本的 Decision Ledger 才可能改变发布状态。", en: "Only an authoritative human resolution and a same-candidate Decision Ledger may change release state." }
    ]
  },
  {
    id: "a3-multimodal-review-assignment",
    group: "judge",
    owner: "A3",
    method: "POST",
    path: "/api/a3/review/multimodal-queue/{queueId}/assignment",
    title: { zh: "管理多模态审核领取", en: "Manage multimodal review assignment" },
    description: {
      zh: "让审核员领取、续期、释放或转交一个分歧案例，并用版本号防止多人同时覆盖。",
      en: "Claim, renew, release, or transfer one disagreement case with optimistic concurrency."
    },
    auth: {
      zh: "服务端验证身份 + release:review + Idempotency-Key 请求头",
      en: "Server-verified principal, release:review, and Idempotency-Key header"
    },
    status: "implemented",
    source: "A2 bb3bcfe three-way queue contract / A3 append-only lease workflow",
    request: {
      source: "api-ingest",
      assignment: {
        action: "claim",
        expected_version: 0,
        lease_seconds: 900,
        reason_code: "manual_review_claim"
      }
    },
    response: {
      schema_version: "a3.multimodal_review_assignment_receipt.v1",
      action: "claim",
      status: "claimed",
      version: 1,
      assigned_reviewer_hash: "reviewer_hash_[REDACTED]",
      release_authority: false,
      a2_decision_recomputed: false,
      release_decision_changed: false
    },
    notes: [
      { zh: "操作者身份来自服务端会话；请求体不能提交原始姓名、邮箱、处置结论、分数或发布权限。", en: "Reviewer identity comes from the server session; the body cannot submit raw identity, disposition, score, or release authority." },
      { zh: "锁默认 15 分钟，支持过期回收；expected_version 过旧时返回 409。", en: "Leases default to 15 minutes, can be reclaimed after expiry, and stale expected_version writes return 409." },
      { zh: "完整历史可生成 a3.multimodal_review_assignment_packet.v1，先通过根哈希校验，再作为 review_record 进入 Ed25519 签名的 Audit Archive。", en: "Complete history can produce a3.multimodal_review_assignment_packet.v1, pass root-hash verification, and enter the Ed25519-signed Audit Archive as a review_record." },
      { zh: "这是人员协作状态，不是 A2 的真人复核凭证，也不会改变发布决定。", en: "This is human coordination state, not an A2 review receipt, and it cannot change the release decision." }
    ]
  },
  {
    id: "a3-multimodal-evidence-request-list",
    group: "judge",
    owner: "A1/A2/A3",
    method: "GET",
    path: "/api/a3/review/multimodal-queue/{queueId}/evidence-requests",
    title: { zh: "读取审核补证请求", en: "Read review evidence requests" },
    description: {
      zh: "查看某个多模态分歧案例还缺哪些执行、评测、媒体或候选版本证据，以及补证是否超期。",
      en: "Read missing execution, evaluation, media, or candidate evidence and deadline state for one multimodal disagreement."
    },
    auth: { zh: "服务端验证身份 + release:review + 五级租户范围", en: "Server-verified principal, release:review, and five-level scope" },
    status: "implemented",
    source: "A3 OpenAPI 2026-07-14 / hash-only evidence request workflow",
    response: {
      schema_version: "a3.multimodal_review_evidence_request_list.v1",
      summary: { total_count: 1, open_count: 1, overdue_count: 0, accepted_count: 0 },
      requests: [{
        request_id: "mmreq_[REDACTED_HASH]",
        status: "open",
        version: 1,
        owner_lane: "execution",
        required_evidence_kinds: ["a1_run_trace"],
        evidence_refs: [],
        release_authority: false
      }]
    },
    notes: [
      { zh: "只返回哈希引用和状态元数据，不返回原始图片、音频、视频、URL、邮箱或身份。", en: "Returns hash references and state metadata only, never raw media, URLs, email, or identity." },
      { zh: "跨租户读取返回脱敏 404，不泄露 request ID 或证据哈希。", en: "Cross-tenant reads return a sanitized 404 without request IDs or evidence hashes." }
    ]
  },
  {
    id: "a3-multimodal-evidence-request-create",
    group: "judge",
    owner: "A1/A2/A3",
    method: "POST",
    path: "/api/a3/review/multimodal-queue/{queueId}/evidence-requests",
    title: { zh: "创建审核补证请求", en: "Create review evidence request" },
    description: {
      zh: "由当前领取该案例的审核人指定责任通道、证据种类和截止时间。",
      en: "Let the active assignment owner specify the owner lane, evidence kinds, and deadline."
    },
    auth: { zh: "release:review + 当前审核租约所有者 + Idempotency-Key 请求头", en: "release:review, active lease ownership, and Idempotency-Key header" },
    status: "implemented",
    source: "A3 append-only evidence request workflow / migration 023-024",
    request: {
      source: "api-ingest",
      evidence_request: {
        expected_version: 0,
        owner_lane: "execution",
        required_evidence_kinds: ["a1_run_trace", "a1_tool_call"],
        due_at: "2026-07-15T21:00:00.000Z",
        reason_code: "execution_evidence_required"
      }
    },
    response: {
      schema_version: "a3.multimodal_review_evidence_request_receipt.v1",
      event_type: "requested",
      status: "open",
      version: 1,
      authoritative_human_disposition_recorded: false,
      release_authority: false,
      release_decision_changed: false
    },
    notes: [
      { zh: "截止时间必须在未来 30 天内；原因只允许受控 reason_code，不接收自由文本。", en: "Deadline must be within 30 days; only a controlled reason_code is accepted, not free text." },
      { zh: "创建请求不会修改 A2 分数、风险、pass/fail 或发布决定。", en: "Creating a request never changes A2 score, risk, pass/fail, or release decision." }
    ]
  },
  {
    id: "a3-multimodal-evidence-submit",
    group: "judge",
    owner: "A1/A2/A3",
    method: "POST",
    path: "/api/a3/review/multimodal-queue/{queueId}/evidence-requests/{requestId}/submissions",
    title: { zh: "提交审核证据哈希", en: "Submit review evidence hashes" },
    description: {
      zh: "由执行、评测或客户运营接入方提交所有被要求的证据哈希和可选绑定哈希。",
      en: "Submit all requested evidence hashes and optional binding hashes from execution, evaluation, or customer operations."
    },
    auth: { zh: "project:ingest + Idempotency-Key 请求头", en: "project:ingest and Idempotency-Key header" },
    status: "implemented",
    source: "A3 OpenAPI / A1-A2 hash-addressed evidence boundary",
    request: {
      source: "api-ingest",
      submission: {
        expected_version: 1,
        owner_lane: "execution",
        evidence_refs: [
          { kind: "a1_run_trace", evidence_hash: exampleSha256, binding_hash: exampleSha256 },
          { kind: "a1_tool_call", evidence_hash: exampleSha256, binding_hash: exampleSha256 }
        ],
        reason_code: "execution_evidence_submitted"
      }
    },
    response: {
      schema_version: "a3.multimodal_review_evidence_request_receipt.v1",
      event_type: "submitted",
      status: "submitted",
      version: 2,
      submitted_evidence_kinds: ["a1_run_trace", "a1_tool_call"],
      release_authority: false
    },
    notes: [
      { zh: "只接受白名单种类和 sha256 引用；URL、Signed URL、本地路径、原始媒体和额外字段会被拒绝。", en: "Only allowlisted kinds and SHA-256 refs are accepted; URLs, signed URLs, local paths, raw media, and extra fields are rejected." },
      { zh: "必须一次覆盖该请求的全部证据种类，缺项返回 409。", en: "A submission must cover every requested kind; incomplete submissions return 409." }
    ]
  },
  {
    id: "a3-multimodal-evidence-review",
    group: "judge",
    owner: "A1/A2/A3",
    method: "POST",
    path: "/api/a3/review/multimodal-queue/{queueId}/evidence-requests/{requestId}/review",
    title: { zh: "审核补充证据", en: "Review submitted evidence" },
    description: {
      zh: "当前审核租约所有者可以接受、退回或取消补证请求，并保留完整事件链。",
      en: "The active assignment owner may accept, reject, or cancel the request while preserving the event chain."
    },
    auth: { zh: "release:review + 当前审核租约所有者 + expected_version + Idempotency-Key", en: "release:review, active lease ownership, expected_version, and Idempotency-Key" },
    status: "implemented",
    source: "A3 append-only evidence review / audit and event outbox",
    request: {
      source: "api-ingest",
      review: { expected_version: 2, action: "accept", reason_code: "evidence_hashes_verified" }
    },
    response: {
      schema_version: "a3.multimodal_review_evidence_request_receipt.v1",
      event_type: "accepted",
      status: "accepted",
      version: 3,
      evidence_accepted: true,
      authoritative_human_disposition_recorded: false,
      release_authority: false,
      a2_decision_recomputed: false,
      release_decision_changed: false
    },
    notes: [
      { zh: "这里的 accepted 只表示补充材料通过检查，不等于 A2 的真人裁决。", en: "Accepted means the supplemental material passed inspection; it is not an A2 human disposition." },
      { zh: "退回后请求重新打开；过期状态由服务器时间投影，不伪造一条过期操作事件。", en: "Rejection reopens the request; overdue is projected from server time without fabricating an action event." }
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
      trusted_release_authority: { status: "integrity_invalid", integrity_verified: false, upstream_decision: "unknown", release_ready: false },
      delivery_golden_path: { status: "blocked_by_a2", production_ready: false },
      multimodal_review_assignment_packet: {
        schema_version: "a3.multimodal_review_assignment_packet.v1",
        integrity: { status: "passed", event_count: 1 },
        archive_binding: { audit_archive_signature_required: true, audit_archive_signature_verified: false },
        authority_boundary: { authoritative_human_review_included: false, release_authority: false }
      },
      deployment_acceptance: { status: "blocked", production_accepted: false },
      deployment_handoff: {
        schema_version: "a3.deployment_handoff.v1",
        status: "blocked",
        summary: { passed: 8, total_checks: 17, owner_group_count: 5, candidate_binding_status: "integrity_invalid" },
        candidate_binding: { expected: { run_id: "a3-golden-20260712-002" }, observed_a2: { evidence_run_id: "a2_trusted_spine_demo" } }
      },
      deployment_receipt_inbox: {
        schema_version: "a3.deployment_receipt_inbox.v1",
        candidate_id: "candidate-head-sha",
        run_id: "a3-golden-20260712-002",
        blocker_slot_count: 9,
        receipt_count: 0,
        production_verified_count: 0
      },
      deployment_acceptance_projection: {
        schema_version: "a3.deployment_acceptance_projection.v1",
        source_passed: 8,
        status: "blocked",
        production_accepted: false,
        projected_production_accepted: false,
        requires_acceptance_rebuild: false
      },
      release_artifact_manifest: { release: { version: "0.2.0-rc.2", git_sha_alias: "candidate-head-sha", ci_tested_sha_alias: "tested-merge-sha", production_release: false } },
      release_comparison: {
        schema_version: "a3.release_comparison.v1",
        baseline: { version: "0.2.0-rc.1", a2_evaluation: { passed: 1, total_cases: 3 } },
        candidate: { version: "0.2.0-rc.2", a2_evaluation: { passed: 3, total_cases: 3 } },
        authority_boundary: { baseline_decision: "block", candidate_decision: "block", current_status: "integrity_invalid", current_upstream_decision: "unknown" },
        runtime_authority_validation: { historical_candidate_decision: "block", status: "integrity_invalid", current_release_authorized: false }
      },
      multimodal_release_readiness: {
        schema_version: "a3.multimodal_release_readiness.v1",
        status: "blocked_multimodal_release_readiness",
        summary: { safe_control_false_positive_count: 0, safe_control_count: 10, taxonomy_detected_count: 3, taxonomy_eligible_count: 5, sensitivity: 0.6, repeat_quality_state: "blocked", repeat_stability_state: "qualified" },
        authority_boundary: { release_authority: false, a2_decision_recomputed: false, production_ready: false }
      }
    },
    notes: [
      { zh: "这是当前 Next.js Webapp 默认消费的只读 API。", en: "This is the read-only API consumed by the current Next.js webapp." },
      { zh: "当前运行时校验与历史封存结论分开返回；A3 不重算 A2 分数、pass/fail、failure class 或发布决定。", en: "Current runtime validation is separate from sealed historical decisions; A3 does not recompute A2 scores, pass/fail, failure class, or release decisions." },
      { zh: "deployment_handoff 把 17 项验收拆给 A1、A2、A1/A3、A3 和仓库管理员，并说明每个阻塞项需要什么真实回执。", en: "deployment_handoff assigns 17 checks to A1, A2, A1/A3, A3, and the repository maintainer, with a required receipt for every blocker." },
      { zh: "Round 52 投影明确区分安全误报、攻击灵敏度、运行时结构化输出、重复质量与稳定性；稳定性合格不能覆盖质量阻断。", en: "The Round 52 projection separates safe false positives, attack sensitivity, runtime structured output, repeat quality, and stability; qualified stability cannot override blocked quality." }
    ]
  },
  {
    id: "a3-self-host-sandbox-calibration",
    group: "console",
    owner: "A1/A2/A3",
    method: "GET",
    path: "/api/a3/deployment/sandbox-calibration",
    title: { zh: "读取自托管沙箱校准", en: "Read self-host sandbox calibration" },
    description: {
      zh: "读取 A1 本地控制面、Worker 重试/死信、租约恢复和对象完整性检查的净化回执。",
      en: "Read a sanitized receipt for A1 local control-plane, worker retry/dead-letter, lease recovery, and object-integrity checks."
    },
    auth: { zh: "A1 可信身份 + deployment:read + 五层租户范围", en: "Trusted A1 principal, deployment:read, and five-level tenant scope" },
    status: "implemented",
    source: "services/report/a3_self_host_sandbox.mjs",
    response: {
      schema_version: "a3.self_host_sandbox_calibration.v1",
      status: "sandbox_verified",
      summary: { passed: 4, total_checks: 4, production_gap_count: 5 },
      authority_boundary: {
        production_verified: false,
        deployment_acceptance_mutated: false,
        a2_decision_recomputed: false,
        a2_release_decision_authority: "A2"
      },
      production_gaps: [
        { id: "postgres_rls_tenant_isolation", status: "not_run" },
        { id: "container_image_identity", status: "not_run" },
        { id: "vpc_network_policy", status: "not_run" },
        { id: "upgrade_rollback_recovery", status: "not_run" }
      ],
      postgres_qualification: {
        schema_version: "a3.postgres_rls_qualification.v1",
        status: "postgres_rls_verified",
        target_class: "local_ephemeral_postgres",
        database: {
          engine: "postgresql",
          migration_id: "019_to_020_self_host_sandbox_rls",
          migration_ids: ["019_self_host_sandbox_calibrations", "020_self_host_sandbox_scope_hardening"],
          migration_apply_count: 2,
          migration_statement_count: 2,
          rls_enabled: true,
          rls_forced: true
        },
        tenant_isolation: {
          same_scope_read_count: 1,
          cross_scope_read_count: 0,
          missing_scope_read_count: 0,
          same_scope_write_allowed: true,
          cross_scope_write_denied: true
        },
        authority_boundary: { production_verified: false, target_customer_environment_verified: false }
      }
    },
    notes: [
      { zh: "这是实际执行的本地 A1 行为证据，但不是客户环境或生产部署证明。", en: "This is executed local A1 behavior evidence, not customer-environment or production deployment proof." },
      { zh: "PostgreSQL 17.9 已真实执行 migration 019→020 链两次并通过五层 RLS 正反向测试，但仍属于本机资格验证。", en: "PostgreSQL 17.9 applied the migration 019-to-020 chain twice and passed five-level RLS allow/deny checks, but remains a local qualification." },
      { zh: "沙箱 4/4 不会把 Deployment Acceptance 从 8/17 提高，也不能生成 Release Ready。", en: "Sandbox 4/4 does not raise Deployment Acceptance beyond 8/17 or create Release Ready." },
      { zh: "A2 仍是评分、失败分类和 Release Decision 的唯一权威。", en: "A2 remains the sole authority for scores, failure classes, and Release Decision." }
    ]
  },
  {
    id: "a3-deployment-receipt-list",
    group: "console",
    owner: "A3",
    method: "GET",
    path: "/api/a3/deployment/receipts",
    title: { zh: "读取部署回执收件箱", en: "Read deployment receipt inbox" },
    description: {
      zh: "按同一 candidate、Run 和五层租户作用域列出 9 类部署阻塞回执槽位。",
      en: "List nine deployment blocker receipt slots for one candidate, run, and five-level tenant scope."
    },
    auth: { zh: "A1 可信身份 + deployment:read", en: "Trusted A1 principal with deployment:read" },
    status: "implemented",
    source: "services/report/a3_deployment_receipt_workflow.mjs",
    response: {
      schema_version: "a3.deployment_receipt_inbox.v1",
      candidate_id: "candidate-head-sha",
      run_id: "run-example",
      blocker_slot_count: 9,
      missing_slot_count: 9,
      production_verified_count: 0
    },
    notes: [
      { zh: "收件状态不修改 Deployment Acceptance，也不重算 A2 裁决。", en: "Intake state does not mutate Deployment Acceptance or recompute A2 authority." }
    ]
  },
  {
    id: "a3-deployment-receipt-submit",
    group: "console",
    owner: "A3",
    method: "POST",
    path: "/api/a3/deployment/receipts",
    title: { zh: "提交部署回执元数据", en: "Submit deployment receipt metadata" },
    description: {
      zh: "提交证据引用、SHA-256、证据类型和采集时间；原始文件、secret 和 signed URL 会被拒绝。",
      en: "Submit an evidence reference, SHA-256, evidence kind, and capture time; raw files, secrets, and signed URLs are rejected."
    },
    auth: { zh: "A1 可信身份 + deployment:submit + Idempotency-Key", en: "Trusted A1 principal, deployment:submit, and Idempotency-Key" },
    status: "implemented",
    source: "services/report/a3_store.mjs",
    request: {
      source: "candidate-source",
      receipt: {
        blocker_id: "deployment_health",
        candidate_id: "candidate-head-sha",
        run_id: "run-example",
        evidence_ref: "receipt:deployment-health:example",
        evidence_sha256: "sha256:[REDACTED_HASH]",
        evidence_kind: "deployment_health_receipt",
        verifier_class: "deployment_probe",
        captured_at: "2026-07-13T06:00:00.000Z"
      }
    },
    response: {
      schema_version: "a3.deployment_receipt.v1",
      receipt_id: "dpr_example",
      status: "submitted",
      version: 1,
      authority_validation: { production_verified: false },
      acceptance_effect: { changes_deployment_acceptance: false, changes_release_ready: false }
    },
    notes: [
      { zh: "submitted 只代表元数据通过本地校验，不是生产证明。", en: "submitted means metadata passed local validation; it is not production proof." }
    ]
  },
  {
    id: "a3-deployment-receipt-review",
    group: "console",
    owner: "A3",
    method: "POST",
    path: "/api/a3/deployment/receipts/{receipt_id}/review",
    title: { zh: "复核部署回执元数据", en: "Review deployment receipt metadata" },
    description: {
      zh: "审核者确认、拒绝或替换回执，并用 expected_version 防止并发覆盖。",
      en: "A reviewer acknowledges, rejects, or supersedes a receipt with expected_version concurrency control."
    },
    auth: { zh: "A1 可信身份 + deployment:review + Idempotency-Key", en: "Trusted A1 principal, deployment:review, and Idempotency-Key" },
    status: "implemented",
    source: "services/report/a3_deployment_receipt_workflow.mjs",
    request: {
      source: "candidate-source",
      review: { action: "acknowledge", reason_code: "metadata_complete", expected_version: 1 }
    },
    response: {
      schema_version: "a3.deployment_receipt.v1",
      receipt_id: "dpr_example",
      status: "acknowledged",
      version: 2,
      authority_validation: { status: "awaiting_authoritative_readback", production_verified: false }
    },
    notes: [
      { zh: "版本冲突返回 HTTP 409；acknowledged 仍不会改写 A2 Release Ready。", en: "Version conflicts return HTTP 409; acknowledged still cannot change A2 Release Ready." }
    ]
  },
  {
    id: "a3-deployment-receipt-authoritative-verify",
    group: "console",
    owner: "A1/A2/A3",
    method: "POST",
    path: "/internal/a3/deployment/receipts/{receipt_id}/verify",
    title: { zh: "服务器权威验证部署回执", en: "Authoritatively verify a deployment receipt" },
    description: {
      zh: "仅允许 A1 验证过的 service account 触发。验证状态、证明项和 attestation 必须来自服务器 resolver，客户端不能提交。",
      en: "Only an A1-verified service account may trigger this route. Status, claims, and attestation come from the server resolver, never the client."
    },
    auth: { zh: "A1 service account + deployment:verify + Idempotency-Key", en: "A1 service account, deployment:verify, and Idempotency-Key" },
    status: "implemented",
    source: "services/report/a3_deployment_receipt_workflow.mjs",
    request: { source: "candidate-source", expected_version: 2 },
    response: {
      schema_version: "a3.deployment_receipt_authoritative_readback.v1",
      readback_id: "dprv_example",
      receipt_id: "dpr_example",
      blocker_id: "github_app_installation",
      verification_status: "rejected",
      reason_code: "policy_not_satisfied",
      production_verified: false,
      claims: { tenant_installation_bound: false, repository_bound: false, check_identity_verified: false },
      binding_validation: { all_passed: true, required_claims: false },
      safety: { trusted_server_resolver: true, client_supplied_verification_result_used: false }
    },
    notes: [
      { zh: "GitHub App 与 required-check resolver 已接入只读真实回读；401、404、github-actions 身份或外部权威回执缺失都会形成可信 rejected，而不是伪造通过。", en: "GitHub App and required-check resolvers now use live read-only provider state; 401, 404, github-actions identity, or missing authority receipts produce a trusted rejection." },
      { zh: "该 readback 只进入只读 Acceptance projection；仍需重建并重新封存正式 Deployment Acceptance。", en: "The readback enters a read-only acceptance projection; the formal Deployment Acceptance must still be rebuilt and resealed." }
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
