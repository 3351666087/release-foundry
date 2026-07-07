const DEFAULT_API_BASE_URL = "https://api.github.com";
const DEFAULT_MARKER_PREFIX = "ashr-plus-plus:release-gate";

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
    "      checks: write",
    "      pull-requests: write",
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
    "      - name: Enforce local gate result",
    "        run: |",
    "          node -e \"const fs=require('fs'); const gate=JSON.parse(fs.readFileSync('artifacts/ashr-gate.json','utf8')); process.exit(gate.exit_code_hint || 0);\"",
    ""
  ].join("\n");
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

function normalizeRepo(repo = "") {
  const [owner, name] = String(repo).split("/");
  return {
    owner: owner || "",
    repo: name || ""
  };
}

function apiBaseUrl(options = {}) {
  return options.apiBaseUrl || DEFAULT_API_BASE_URL;
}

function positiveInteger(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}
