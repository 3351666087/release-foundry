import { createHash } from "node:crypto";

const DEFAULT_API_BASE_URL = "https://api.github.com";
const DEFAULT_MARKER_PREFIX = "ashr-plus-plus:release-gate";
const DEFAULT_GITHUB_API_VERSION = "2022-11-28";

export function buildGitHubCheckRunRequest(gatePayload = {}, options = {}) {
  const repo = normalizeRepo(options.repo);
  const checkRun = gatePayload.github_check_run || {};
  const headSha = options.headSha;
  if (!repo.owner || !repo.repo) {
    throw new Error("repo must be in owner/name form.");
  }
  if (!headSha || headSha === "[set-by-ci]") {
    throw new Error("headSha is required for GitHub check run requests.");
  }
  const body = {
    name: checkRun.name || "Ashr++ Release Gate",
    head_sha: headSha,
    status: checkRun.status || "completed",
    conclusion: checkRun.conclusion || "neutral",
    details_url: options.detailsUrl || checkRun.details_url || "",
    output: {
      title: checkRun.output?.title || "Ashr++ Release Gate",
      summary: checkRun.output?.summary || "Release gate completed.",
      text: checkRun.output?.text || "",
      annotations: normalizeAnnotations(checkRun.output?.annotations || [])
    }
  };
  return {
    schema_version: "a3.github_check_request.v1",
    mode: options.checkRunId ? "update_check_run" : "create_check_run",
    method: options.checkRunId ? "PATCH" : "POST",
    url: options.checkRunId
      ? `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/check-runs/${options.checkRunId}`
      : `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/check-runs`,
    repo,
    requires_token_scope: "checks:write",
    body,
    safety: {
      dry_run_only: true,
      token_included: false,
      secret_values_allowed: false
    }
  };
}

export function buildPrCommentUpsertPlan(gatePayload = {}, options = {}) {
  const repo = normalizeRepo(options.repo);
  const pullNumber = Number(options.pullNumber);
  if (!repo.owner || !repo.repo) {
    throw new Error("repo must be in owner/name form.");
  }
  if (!Number.isInteger(pullNumber) || pullNumber <= 0) {
    throw new Error("pullNumber must be a positive integer.");
  }
  const runId = gatePayload.summary?.lastRunId || "unknown-run";
  const marker = buildPrCommentMarker(options.marker || `${DEFAULT_MARKER_PREFIX}:${runId}`);
  const body = `${marker}\n${gatePayload.pr_comment_markdown || gatePayload.release_workflow?.pr_comment_markdown || "## Ashr++ Release Gate\n\nNo PR comment body was generated."}`;
  const existingComment = findExistingGateComment(options.existingComments || [], marker);
  return {
    schema_version: "a3.github_pr_comment_upsert.v1",
    mode: existingComment ? "update_existing_comment" : "create_new_comment",
    marker,
    find_existing: {
      method: "GET",
      url: `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/issues/${pullNumber}/comments`,
      match: "body contains marker"
    },
    request: existingComment
      ? {
          method: "PATCH",
          url: `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/issues/comments/${existingComment.id}`,
          body: { body }
        }
      : {
          method: "POST",
          url: `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/issues/${pullNumber}/comments`,
          body: { body }
        },
    repo,
    pull_number: pullNumber,
    existing_comment_id: existingComment?.id || null,
    requires_token_scope: "pull-requests:write",
    safety: {
      dry_run_only: true,
      token_included: false,
      secret_values_allowed: false
    }
  };
}

export function buildBranchProtectionRequiredCheckPlan(options = {}) {
  const repo = normalizeRepo(options.repo);
  const branch = options.branch || "main";
  const checkName = options.checkName || "Ashr++ Release Gate";
  if (!repo.owner || !repo.repo) {
    throw new Error("repo must be in owner/name form.");
  }
  if (!branch) {
    throw new Error("branch is required for branch protection plans.");
  }
  return {
    schema_version: "a3.github_required_check_plan.v1",
    mode: "plan_required_check",
    repo,
    branch,
    check_name: checkName,
    required_for_commercial_gate: true,
    inspect_current: {
      method: "GET",
      url: `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/branches/${encodeURIComponent(branch)}/protection/required_status_checks`
    },
    request: {
      method: "PATCH",
      url: `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/branches/${encodeURIComponent(branch)}/protection/required_status_checks`,
      body: {
        strict: options.strict !== false,
        contexts: options.existingContexts || [],
        checks: dedupeChecks([
          ...(Array.isArray(options.existingChecks) ? options.existingChecks : []),
          { context: checkName, app_id: options.appId || null }
        ])
      }
    },
    requires_token_scope: "administration:write",
    safety: {
      dry_run_only: true,
      token_included: false,
      secret_values_allowed: false,
      maintainer_approval_required: true
    },
    redacted_summary: `Plan only: require the '${checkName}' check on ${repo.owner}/${repo.repo}@${branch}.`
  };
}

export function buildGitHubCheckReadbackReceipt(publishReceipt = {}, options = {}) {
  const expected = expectedCheckRunFields(publishReceipt, options);
  const observed = sanitizeCheckRunReadback(options.checkRun || options.observedCheckRun || {});
  const httpStatus = numberOrNull(options.httpStatus);
  const matches = {
    check_run_id: expected.check_run_id_alias && observed.check_run_id_alias
      ? expected.check_run_id_alias === observed.check_run_id_alias
      : null,
    name: expected.check_name && observed.check_name ? expected.check_name === observed.check_name : null,
    head_sha: expected.head_sha_alias && observed.head_sha_alias ? expected.head_sha_alias === observed.head_sha_alias : null,
    conclusion: expected.conclusion && observed.conclusion ? expected.conclusion === observed.conclusion : null,
    output_hash: expected.output_hash && observed.output_hash ? expected.output_hash === observed.output_hash : null
  };
  const readbackStatus = classifyReadbackStatus({
    explicitStatus: options.readbackStatus,
    httpStatus,
    observedPresent: Boolean(observed.check_run_id_alias),
    expectedExternalIdPresent: Boolean(expected.check_run_id_alias),
    hasMismatch: Object.values(matches).some((value) => value === false),
    posted: publishReceipt.posted === true,
    dryRun: publishReceipt.dry_run === true || publishReceipt.request?.safety?.dry_run_only === true
  });
  const payloadForHash = { expected, observed, matches, readbackStatus, httpStatus };
  return {
    schema_version: "a3.github_check_readback_receipt.v1",
    provider: "github",
    resource_kind: "check_run",
    readback_id: `ghcrb_${sha256(stableJson(payloadForHash)).slice(0, 16)}`,
    readback_status: readbackStatus,
    readback_confirmed: readbackStatus === "readback_confirmed",
    posted: publishReceipt.posted === true || readbackStatus === "readback_confirmed",
    stale: readbackStatus === "stale",
    missing: readbackStatus === "missing",
    deleted: readbackStatus === "deleted",
    http_status: httpStatus,
    github_request_id: sanitizeGitHubRequestId(options.githubRequestId),
    expected,
    observed,
    matches,
    sanitized_error_class: errorClassForReadback(readbackStatus, options.errorMessage),
    payload_hash: sha256(stableJson(payloadForHash)),
    checked_at: options.checkedAt || null,
    safety: readbackSafety(options)
  };
}

export function buildPrCommentReadbackReceipt(publishReceipt = {}, options = {}) {
  const expected = expectedPrCommentFields(publishReceipt, options);
  const observedComment = options.comment || findExistingGateComment(options.comments || [], expected.marker || "");
  const observed = sanitizePrCommentReadback(observedComment || {});
  const httpStatus = numberOrNull(options.httpStatus);
  const markerMatch = expected.marker && observed.body_marker_present !== null
    ? observed.body_marker_present === true
    : null;
  const bodyHashMatch = expected.body_hash && observed.body_hash
    ? expected.body_hash === observed.body_hash
    : null;
  const commentIdMatch = expected.comment_id_alias && observed.comment_id_alias
    ? expected.comment_id_alias === observed.comment_id_alias
    : null;
  const headShaMatch = expected.head_sha_alias && observed.head_sha_alias
    ? expected.head_sha_alias === observed.head_sha_alias
    : null;
  const matches = {
    comment_id: commentIdMatch,
    marker: markerMatch,
    body_hash: bodyHashMatch,
    head_sha: headShaMatch
  };
  const readbackStatus = classifyReadbackStatus({
    explicitStatus: options.readbackStatus,
    httpStatus,
    observedPresent: Boolean(observed.comment_id_alias),
    expectedExternalIdPresent: Boolean(expected.comment_id_alias),
    hasMismatch: Object.values(matches).some((value) => value === false),
    posted: publishReceipt.posted === true,
    dryRun: publishReceipt.dry_run === true || publishReceipt.plan?.safety?.dry_run_only === true
  });
  const payloadForHash = { expected, observed, matches, readbackStatus, httpStatus };
  return {
    schema_version: "a3.github_pr_comment_readback_receipt.v1",
    provider: "github",
    resource_kind: "pr_comment",
    readback_id: `ghprb_${sha256(stableJson(payloadForHash)).slice(0, 16)}`,
    readback_status: readbackStatus,
    readback_confirmed: readbackStatus === "readback_confirmed",
    posted: publishReceipt.posted === true || readbackStatus === "readback_confirmed",
    stale: readbackStatus === "stale",
    missing: readbackStatus === "missing",
    deleted: readbackStatus === "deleted",
    http_status: httpStatus,
    github_request_id: sanitizeGitHubRequestId(options.githubRequestId),
    expected,
    observed,
    matches,
    marker_match: markerMatch,
    body_hash_match: bodyHashMatch,
    sanitized_error_class: errorClassForReadback(readbackStatus, options.errorMessage),
    payload_hash: sha256(stableJson(payloadForHash)),
    checked_at: options.checkedAt || null,
    safety: readbackSafety(options)
  };
}

export function buildRequiredCheckProof(plan = {}, options = {}) {
  const repo = normalizeRepo(options.repo || repoToString(plan.repo));
  const branch = options.branch || plan.branch || "main";
  const checkName = options.checkName || plan.check_name || "Ashr++ Release Gate";
  const protection = options.branchProtection || options.requiredStatusChecks || {};
  const checks = Array.isArray(protection.checks) ? protection.checks : [];
  const contexts = Array.isArray(protection.contexts) ? protection.contexts : [];
  const matchedCheck = checks.find((item) => (
    item?.context === checkName
    || item?.name === checkName
    || item?.check_name === checkName
  )) || null;
  const matchedContext = contexts.includes(checkName) ? checkName : null;
  const httpStatus = numberOrNull(options.httpStatus);
  const hasProtectionReadback = Boolean(options.branchProtection || options.requiredStatusChecks);
  const present = Boolean(matchedCheck || matchedContext);
  let readbackStatus = options.readbackStatus || "plan_only";
  if (!options.readbackStatus) {
    if (httpStatus === 401 || httpStatus === 403) {
      readbackStatus = "permission_denied";
    } else if (httpStatus === 404) {
      readbackStatus = "missing";
    } else if (httpStatus && httpStatus >= 400) {
      readbackStatus = "failed";
    } else if (hasProtectionReadback && present) {
      readbackStatus = "readback_confirmed";
    } else if (hasProtectionReadback) {
      readbackStatus = "missing";
    }
  }
  const enforced = readbackStatus === "readback_confirmed" && present;
  const payloadForHash = {
    repo,
    branch,
    checkName,
    readbackStatus,
    matchedCheck: matchedCheck ? sanitizeRequiredCheckMatch(matchedCheck) : null,
    matchedContext,
    httpStatus
  };
  return {
    schema_version: "a3.github_required_check_proof.v1",
    provider: "github",
    resource_kind: "required_check",
    proof_id: `ghrcp_${sha256(stableJson(payloadForHash)).slice(0, 16)}`,
    plan_available: hasReleasePlan(plan),
    repo,
    branch,
    check_name: checkName,
    enforcement_readback_status: readbackStatus,
    readback_status: readbackStatus,
    enforced,
    plan_only_must_not_claim_enforcement: !enforced,
    required_for_commercial_gate: plan.required_for_commercial_gate === true || options.requiredForCommercialGate === true,
    matched_check: matchedCheck ? sanitizeRequiredCheckMatch(matchedCheck) : null,
    matched_context: matchedContext,
    checked_count: checks.length + contexts.length,
    strict: protection.strict === true,
    http_status: httpStatus,
    github_request_id: sanitizeGitHubRequestId(options.githubRequestId),
    sanitized_error_class: errorClassForReadback(readbackStatus, options.errorMessage),
    payload_hash: sha256(stableJson(payloadForHash)),
    checked_at: options.checkedAt || null,
    safety: {
      ...readbackSafety(options),
      maintainer_approval_required: plan.safety?.maintainer_approval_required === true,
      branch_protection_mutation_performed: false
    }
  };
}

export async function readGitHubCheckRun(publishReceipt = {}, options = {}) {
  if (options.dryRun !== false) {
    return buildGitHubCheckReadbackReceipt(publishReceipt, {
      ...options,
      readbackStatus: publishReceipt.posted === true ? "posted" : "generated"
    });
  }
  const repo = normalizeRepo(options.repo || repoToString(publishReceipt.request?.repo));
  const checkRunId = options.checkRunId || publishReceipt.check_run?.id;
  if (!repo.owner || !repo.repo) {
    throw new Error("repo must be in owner/name form for GitHub check readback.");
  }
  if (!checkRunId) {
    throw new Error("checkRunId is required for GitHub check readback.");
  }
  const token = runtimeToken(options);
  if (!token) {
    throw new Error("GitHub token is required when dryRun is false.");
  }
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required for GitHub check readback.");
  }
  const response = await githubFetch(fetchImpl, `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/check-runs/${checkRunId}`, {
    method: "GET",
    token,
    githubApiVersion: options.githubApiVersion
  });
  return buildGitHubCheckReadbackReceipt(publishReceipt, {
    ...options,
    httpStatus: response.status,
    githubRequestId: response.requestId,
    checkRun: response.ok ? response.json : null,
    errorMessage: response.json?.message || response.statusText
  });
}

export async function readPrCommentReadback(publishReceipt = {}, options = {}) {
  if (options.dryRun !== false) {
    return buildPrCommentReadbackReceipt(publishReceipt, {
      ...options,
      readbackStatus: publishReceipt.posted === true ? "posted" : "generated"
    });
  }
  const plan = publishReceipt.plan || {};
  const repo = normalizeRepo(options.repo || repoToString(plan.repo));
  const pullNumber = Number(options.pullNumber || plan.pull_number);
  if (!repo.owner || !repo.repo) {
    throw new Error("repo must be in owner/name form for GitHub PR comment readback.");
  }
  if (!Number.isInteger(pullNumber) || pullNumber <= 0) {
    throw new Error("pullNumber must be a positive integer for GitHub PR comment readback.");
  }
  const token = runtimeToken(options);
  if (!token) {
    throw new Error("GitHub token is required when dryRun is false.");
  }
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required for GitHub PR comment readback.");
  }
  const url = plan.find_existing?.url || `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/issues/${pullNumber}/comments`;
  const response = await githubFetch(fetchImpl, url, {
    method: "GET",
    token,
    githubApiVersion: options.githubApiVersion
  });
  return buildPrCommentReadbackReceipt(publishReceipt, {
    ...options,
    httpStatus: response.status,
    githubRequestId: response.requestId,
    comments: response.ok && Array.isArray(response.json) ? response.json : [],
    errorMessage: response.json?.message || response.statusText
  });
}

export async function readRequiredCheckProof(plan = {}, options = {}) {
  if (options.dryRun !== false) {
    return buildRequiredCheckProof(plan, {
      ...options,
      readbackStatus: "plan_only"
    });
  }
  const repo = normalizeRepo(options.repo || repoToString(plan.repo));
  const branch = options.branch || plan.branch || "main";
  if (!repo.owner || !repo.repo) {
    throw new Error("repo must be in owner/name form for required-check readback.");
  }
  const token = runtimeToken(options);
  if (!token) {
    throw new Error("GitHub token is required when dryRun is false.");
  }
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required for required-check readback.");
  }
  const url = plan.inspect_current?.url || `${apiBaseUrl(options)}/repos/${repo.owner}/${repo.repo}/branches/${encodeURIComponent(branch)}/protection/required_status_checks`;
  const response = await githubFetch(fetchImpl, url, {
    method: "GET",
    token,
    githubApiVersion: options.githubApiVersion
  });
  return buildRequiredCheckProof(plan, {
    ...options,
    repo: `${repo.owner}/${repo.repo}`,
    branch,
    httpStatus: response.status,
    githubRequestId: response.requestId,
    branchProtection: response.ok ? response.json : null,
    errorMessage: response.json?.message || response.statusText
  });
}

export function buildGitHubActionWorkflowExample(options = {}) {
  const runFixture = options.runFixture || "fixtures/a3/mock_run_results.json";
  const gradeFixture = options.gradeFixture || "fixtures/a3/mock_grade_results.json";
  const coverageFixture = options.coverageFixture || "fixtures/a2/results/a2_g3_coverage_report.json";
  const thresholdsFixture = options.thresholdsFixture || "fixtures/a3/release_gate_thresholds.json";
  return [
    "name: Ashr++ Release Gate",
    "",
    "on:",
    "  pull_request:",
    "    types: [opened, synchronize, reopened, ready_for_review]",
    "",
    "jobs:",
    "  ashr-release-gate:",
    "    runs-on: ubuntu-latest",
    "    permissions:",
    "      contents: read",
    "    steps:",
    "      - uses: actions/checkout@v4",
    "      - uses: actions/setup-node@v4",
    "        with:",
    "          node-version: 22",
    "      - name: Build Ashr++ gate artifacts",
    "        run: |",
    `          node services/report/a3_gate_cli.mjs --runs ${runFixture} --grades ${gradeFixture} --coverage ${coverageFixture} --thresholds ${thresholdsFixture} --release-version pr-\${{ github.event.pull_request.number }} --source github-actions --head-sha \${{ github.event.pull_request.head.sha }} --details-url \${{ github.server_url }}/\${{ github.repository }}/actions/runs/\${{ github.run_id }} --annotation-path docs/a3/p3_gate_cli_growth_2026_07_07.md --output-json artifacts/ashr-gate.json --output-md artifacts/ashr-gate.md --output-check artifacts/ashr-check.json --output-pr-comment artifacts/ashr-pr-comment.md --no-fail --json`,
    "      - name: Upload Ashr++ gate artifacts",
    "        uses: actions/upload-artifact@v4",
    "        with:",
    "          name: ashr-release-gate",
    "          path: artifacts/",
    "      - name: Plan Ashr++ GitHub Check",
    "        run: |",
    `          node services/report/a3_github_publish_cli.mjs --gate artifacts/ashr-gate.json --repo \${{ github.repository }} --head-sha \${{ github.event.pull_request.head.sha }} --details-url \${{ github.server_url }}/\${{ github.repository }}/actions/runs/\${{ github.run_id }} --output-receipt artifacts/ashr-github-check-receipt.json --dry-run --json`,
    "      - name: Plan Ashr++ PR Comment",
    "        run: |",
    `          node services/report/a3_github_publish_cli.mjs --gate artifacts/ashr-gate.json --repo \${{ github.repository }} --pull-number \${{ github.event.pull_request.number }} --pr-comment --output-receipt artifacts/ashr-pr-comment-receipt.json --dry-run --json`,
    "      - name: Enforce local gate result",
    "        run: |",
    "          node -e \"const fs=require('fs'); const gate=JSON.parse(fs.readFileSync('artifacts/ashr-gate.json','utf8')); process.exit(gate.exit_code_hint || 0);\"",
    ""
  ].join("\n");
}

export async function publishGitHubCheckRun(gatePayload = {}, options = {}) {
  const request = buildGitHubCheckRunRequest(gatePayload, options);
  const dryRun = options.dryRun !== false;
  const receiptBase = {
    schema_version: "a3.github_check_publish_receipt.v1",
    mode: request.mode,
    dry_run: dryRun,
    posted: false,
    request: redactCheckRunRequestForReceipt(request),
    safety: {
      token_included: false,
      token_source: options.token ? "provided_runtime_option" : options.tokenEnvName ? "environment_variable" : "not_required_for_dry_run",
      response_body_sanitized: true,
      secret_values_allowed: false
    }
  };
  if (dryRun) {
    return {
      ...receiptBase,
      status: "planned",
      http_status: null,
      github_request_id: null,
      check_run: null,
      redacted_summary: "Dry run only; no GitHub API request was sent."
    };
  }

  const token = runtimeToken(options);
  if (!token) {
    throw new Error("GitHub token is required when dryRun is false.");
  }
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required to publish a GitHub check run.");
  }
  assertTrustedLiveGitHubUrl(request.url, options);

  const response = await fetchImpl(request.url, {
    method: request.method,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "user-agent": "ashr-plus-plus-a3-release-gate",
      "x-github-api-version": options.githubApiVersion || DEFAULT_GITHUB_API_VERSION
    },
    body: JSON.stringify(request.body)
  });
  const responseJson = await safeResponseJson(response);
  return {
    ...receiptBase,
    dry_run: false,
    posted: Boolean(response.ok),
    status: response.ok ? "posted" : "failed",
    http_status: response.status,
    github_request_id: response.headers?.get?.("x-github-request-id") || null,
    check_run: sanitizeCheckRunResponse(responseJson),
    redacted_summary: response.ok
      ? "GitHub Check Run was published with sanitized receipt fields only."
      : sanitizeErrorMessage(responseJson?.message || response.statusText || "GitHub Check Run publish failed.")
  };
}

export async function publishPrCommentUpsert(gatePayload = {}, options = {}) {
  const dryRun = options.dryRun !== false;
  if (dryRun) {
    const plan = buildPrCommentUpsertPlan(gatePayload, options);
    return {
      schema_version: "a3.github_pr_comment_publish_receipt.v1",
      mode: plan.mode,
      dry_run: true,
      posted: false,
      plan: redactPrCommentPlanForReceipt(plan),
      http_status: null,
      github_request_id: null,
      comment: null,
      safety: {
        token_included: false,
        token_source: options.token ? "provided_runtime_option" : options.tokenEnvName ? "environment_variable" : "not_required_for_dry_run",
        response_body_sanitized: true,
        secret_values_allowed: false
      },
      status: "planned",
      redacted_summary: "Dry run only; no GitHub PR comment request was sent."
    };
  }

  const token = runtimeToken(options);
  if (!token) {
    throw new Error("GitHub token is required when dryRun is false.");
  }
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required to publish a GitHub PR comment.");
  }

  const lookupPlan = buildPrCommentUpsertPlan(gatePayload, { ...options, existingComments: [] });
  assertTrustedLiveGitHubUrl(lookupPlan.find_existing.url, options);
  const commentsResponse = await githubFetch(fetchImpl, lookupPlan.find_existing.url, {
    method: "GET",
    token,
    githubApiVersion: options.githubApiVersion
  });
  if (!commentsResponse.ok) {
    return {
      schema_version: "a3.github_pr_comment_publish_receipt.v1",
      mode: "lookup_failed",
      dry_run: false,
      posted: false,
      plan: redactPrCommentPlanForReceipt(lookupPlan),
      lookup: {
        http_status: commentsResponse.status,
        github_request_id: commentsResponse.requestId,
        matched_existing_comment: false,
        inspected_comment_count: 0
      },
      http_status: commentsResponse.status,
      github_request_id: commentsResponse.requestId,
      comment: null,
      safety: {
        token_included: false,
        token_source: options.token ? "provided_runtime_option" : options.tokenEnvName ? "environment_variable" : "environment_variable",
        response_body_sanitized: true,
        secret_values_allowed: false
      },
      status: "failed",
      redacted_summary: sanitizeErrorMessage(commentsResponse.json?.message || commentsResponse.statusText || "GitHub PR comment lookup failed.")
    };
  }
  const comments = Array.isArray(commentsResponse.json) ? commentsResponse.json : [];
  const plan = buildPrCommentUpsertPlan(gatePayload, { ...options, existingComments: comments });
  assertTrustedLiveGitHubUrl(plan.request.url, options);
  const response = await githubFetch(fetchImpl, plan.request.url, {
    method: plan.request.method,
    token,
    githubApiVersion: options.githubApiVersion,
    body: plan.request.body
  });
  return {
    schema_version: "a3.github_pr_comment_publish_receipt.v1",
    mode: plan.mode,
    dry_run: false,
    posted: Boolean(response.ok),
    plan: redactPrCommentPlanForReceipt(plan),
    lookup: {
      http_status: commentsResponse.status,
      github_request_id: commentsResponse.requestId,
      matched_existing_comment: Boolean(plan.existing_comment_id),
      inspected_comment_count: comments.length
    },
    http_status: response.status,
    github_request_id: response.requestId,
    comment: sanitizeCommentResponse(response.json),
    safety: {
      token_included: false,
      token_source: options.token ? "provided_runtime_option" : options.tokenEnvName ? "environment_variable" : "environment_variable",
      response_body_sanitized: true,
      secret_values_allowed: false
    },
    status: response.ok ? "posted" : "failed",
    redacted_summary: response.ok
      ? "GitHub PR comment was upserted with sanitized receipt fields only."
      : sanitizeErrorMessage(response.json?.message || response.statusText || "GitHub PR comment publish failed.")
  };
}

function normalizeAnnotations(annotations = []) {
  return annotations.slice(0, 50).map((item) => ({
    path: item.path || "ashr-gate-report.md",
    start_line: positiveInteger(item.start_line, 1),
    end_line: positiveInteger(item.end_line, positiveInteger(item.start_line, 1)),
    annotation_level: ["notice", "warning", "failure"].includes(item.annotation_level) ? item.annotation_level : "warning",
    title: String(item.title || "Ashr++ gate finding").slice(0, 255),
    message: String(item.message || "Review Ashr++ gate evidence.").slice(0, 64000),
    raw_details: item.raw_details || ""
  }));
}

function redactCheckRunRequestForReceipt(request = {}) {
  return {
    schema_version: request.schema_version,
    mode: request.mode,
    method: request.method,
    url: request.url,
    repo: request.repo,
    requires_token_scope: request.requires_token_scope,
    body: request.body,
    safety: {
      ...request.safety,
      token_included: false,
      secret_values_allowed: false
    }
  };
}

function redactPrCommentPlanForReceipt(plan = {}) {
  return {
    schema_version: plan.schema_version,
    mode: plan.mode,
    marker: plan.marker,
    find_existing: plan.find_existing,
    request: plan.request,
    repo: plan.repo,
    pull_number: plan.pull_number,
    existing_comment_id: plan.existing_comment_id,
    requires_token_scope: plan.requires_token_scope,
    safety: {
      ...plan.safety,
      token_included: false,
      secret_values_allowed: false
    }
  };
}

function runtimeToken(options = {}) {
  if (options.token) {
    return String(options.token);
  }
  if (options.tokenEnvName) {
    if (!["GITHUB_TOKEN", "GH_TOKEN"].includes(options.tokenEnvName)) {
      throw new Error("Only fixed GitHub token environment references are allowed.");
    }
    return process.env[options.tokenEnvName];
  }
  return process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
}

function assertTrustedLiveGitHubUrl(value, options = {}) {
  const url = new URL(value);
  const trustedOrigins = new Set([
    new URL(DEFAULT_API_BASE_URL).origin,
    ...(Array.isArray(options.trustedApiOrigins) ? options.trustedApiOrigins : [])
  ]);
  if (url.protocol !== "https:" || !trustedOrigins.has(url.origin)) {
    throw new Error("Live GitHub requests require a server-approved HTTPS API origin.");
  }
}

async function safeResponseJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return { message: text.slice(0, 500) };
  }
}

async function githubFetch(fetchImpl, url, options = {}) {
  const response = await fetchImpl(url, {
    method: options.method,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${options.token}`,
      "content-type": "application/json",
      "user-agent": "ashr-plus-plus-a3-release-gate",
      "x-github-api-version": options.githubApiVersion || DEFAULT_GITHUB_API_VERSION
    },
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  const json = await safeResponseJson(response);
  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    requestId: response.headers?.get?.("x-github-request-id") || null,
    json
  };
}

function sanitizeCheckRunResponse(value = {}) {
  if (!value || typeof value !== "object") {
    return null;
  }
  return {
    id: value.id ?? null,
    name: value.name || null,
    status: value.status || null,
    conclusion: value.conclusion || null,
    html_url: value.html_url || null,
    details_url: value.details_url || null,
    head_sha: value.head_sha || null,
    started_at: value.started_at || null,
    completed_at: value.completed_at || null
  };
}

function sanitizeCommentResponse(value = {}) {
  if (!value || typeof value !== "object") {
    return null;
  }
  return {
    id: value.id ?? null,
    html_url: value.html_url || null,
    issue_url: value.issue_url || null,
    created_at: value.created_at || null,
    updated_at: value.updated_at || null,
    author_association: value.author_association || null
  };
}

function sanitizeErrorMessage(message = "") {
  return String(message)
    .replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [REDACTED]")
    .replace(/gh[pousr]_[A-Za-z0-9_]+/g, "[REDACTED_GITHUB_TOKEN]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
    .slice(0, 500);
}

function expectedCheckRunFields(publishReceipt = {}, options = {}) {
  const requestBody = objectOr(publishReceipt.request?.body);
  const checkRun = objectOr(publishReceipt.check_run);
  const output = objectOr(requestBody.output);
  return {
    repo: options.repo || repoToString(publishReceipt.request?.repo) || "unknown",
    check_run_id_alias: options.checkRunId || checkRun.id || null,
    check_name: options.checkName || requestBody.name || checkRun.name || "Ashr++ Release Gate",
    head_sha_alias: options.headSha || requestBody.head_sha || checkRun.head_sha || null,
    conclusion: options.conclusion || requestBody.conclusion || checkRun.conclusion || null,
    output_hash: options.skipOutputHash === true ? null : hashCheckOutput(output)
  };
}

function sanitizeCheckRunReadback(value = {}) {
  if (!value || typeof value !== "object") {
    return {};
  }
  const output = objectOr(value.output);
  return {
    check_run_id_alias: value.id ?? null,
    check_name: value.name || null,
    status: value.status || null,
    conclusion: value.conclusion || null,
    head_sha_alias: value.head_sha || null,
    html_url: value.html_url || null,
    details_url: value.details_url || null,
    output_title: output.title || null,
    output_hash: hashCheckOutput(output),
    app_id_alias: Number.isInteger(Number(value.app?.id)) ? Number(value.app.id) : null,
    app_slug: value.app?.slug || null,
    app_owner_type: value.app?.owner?.type || null,
    started_at: value.started_at || null,
    completed_at: value.completed_at || null
  };
}

function expectedPrCommentFields(publishReceipt = {}, options = {}) {
  const plan = objectOr(publishReceipt.plan);
  const request = objectOr(plan.request);
  const body = request.body?.body || "";
  return {
    repo: options.repo || repoToString(plan.repo) || "unknown",
    pull_number: numberOrNull(options.pullNumber || plan.pull_number),
    comment_id_alias: options.commentId || publishReceipt.comment?.id || plan.existing_comment_id || null,
    marker: options.marker || plan.marker || null,
    body_hash: body ? sha256(body) : null,
    head_sha_alias: options.headSha || null
  };
}

function sanitizePrCommentReadback(value = {}) {
  if (!value || typeof value !== "object") {
    return {};
  }
  const body = typeof value.body === "string" ? value.body : "";
  return {
    comment_id_alias: value.id ?? null,
    html_url: value.html_url || null,
    issue_url: value.issue_url || null,
    created_at: value.created_at || null,
    updated_at: value.updated_at || null,
    author_association: value.author_association || null,
    body_marker_present: body ? /<!--\s*ashr-plus-plus:release-gate:[^>]+-->/.test(body) : null,
    body_hash: body ? sha256(body) : null,
    head_sha_alias: extractHeadShaAlias(body)
  };
}

function classifyReadbackStatus(options = {}) {
  if (options.explicitStatus) {
    return options.explicitStatus;
  }
  if (options.httpStatus === 401 || options.httpStatus === 403) {
    return "permission_denied";
  }
  if (options.httpStatus === 410) {
    return "deleted";
  }
  if (options.httpStatus === 404) {
    return options.expectedExternalIdPresent ? "deleted" : "missing";
  }
  if (options.httpStatus && options.httpStatus >= 400) {
    return "failed";
  }
  if (options.observedPresent && options.hasMismatch) {
    return "stale";
  }
  if (options.observedPresent) {
    return "readback_confirmed";
  }
  if (options.httpStatus && options.httpStatus >= 200 && options.httpStatus < 400) {
    return "missing";
  }
  if (options.posted) {
    return "posted";
  }
  return options.dryRun ? "generated" : "missing";
}

function errorClassForReadback(status, message = "") {
  if (status === "permission_denied") {
    return "permission_denied";
  }
  if (status === "deleted") {
    return "deleted";
  }
  if (status === "missing") {
    return "missing";
  }
  if (status === "failed") {
    return sanitizeErrorMessage(message || "readback_failed").slice(0, 80) || "failed";
  }
  return null;
}

function readbackSafety(options = {}) {
  return {
    token_included: false,
    token_source: options.token ? "provided_runtime_option" : options.tokenEnvName ? "environment_variable" : "not_recorded",
    response_body_sanitized: true,
    raw_body_stored: false,
    secret_values_allowed: false,
    live_mutation_performed: false
  };
}

function sanitizeRequiredCheckMatch(value = {}) {
  return {
    context: value.context || value.name || value.check_name || null,
    app_id: value.app_id ?? null
  };
}

function hasReleasePlan(plan = {}) {
  return Boolean(plan?.check_name || plan?.request || plan?.inspect_current);
}

function sanitizeGitHubRequestId(value) {
  return typeof value === "string" && value.length <= 120 ? value : null;
}

function extractHeadShaAlias(body = "") {
  const match = String(body).match(/\b[0-9a-f]{7,40}\b/i);
  return match ? match[0] : null;
}

function hashCheckOutput(output = {}) {
  const normalized = {
    title: output.title || "",
    summary: output.summary || "",
    text: output.text || ""
  };
  return normalized.title || normalized.summary || normalized.text ? sha256(stableJson(normalized)) : null;
}

function findExistingGateComment(comments = [], marker = "") {
  return comments.find((comment) => (
    Number.isInteger(Number(comment.id))
    && typeof comment.body === "string"
    && comment.body.includes(marker)
  )) || null;
}

function buildPrCommentMarker(marker) {
  const safeMarker = String(marker || DEFAULT_MARKER_PREFIX).replaceAll("--", "-");
  return `<!-- ${safeMarker} -->`;
}

function dedupeChecks(checks = []) {
  const seen = new Set();
  const result = [];
  for (const check of checks) {
    const context = String(check.context || check.name || "").trim();
    if (!context || seen.has(context)) {
      continue;
    }
    seen.add(context);
    result.push({
      context,
      app_id: check.app_id ?? null
    });
  }
  return result;
}

function normalizeRepo(repo = "") {
  const [owner, name] = String(repo).split("/");
  return {
    owner: owner || "",
    repo: name || ""
  };
}

function repoToString(repo = {}) {
  return repo?.owner && repo?.repo ? `${repo.owner}/${repo.repo}` : "";
}

function apiBaseUrl(options = {}) {
  return options.apiBaseUrl || DEFAULT_API_BASE_URL;
}

function objectOr(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function numberOrNull(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, sortForStableJson(item)])
    );
  }
  return value;
}

function positiveInteger(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}
