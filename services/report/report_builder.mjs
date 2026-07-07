export function normalizeScore(score) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return 0;
  }
  return score <= 1 ? Math.round(score * 1000) / 10 : Math.round(score * 10) / 10;
}

export function scoreBand(score) {
  const normalized = normalizeScore(score);
  if (normalized >= 90) {
    return "90-100";
  }
  if (normalized >= 70) {
    return "70-89";
  }
  if (normalized > 0) {
    return "1-69";
  }
  return "0";
}

const CANONICAL_FAILURE_CLASSES = new Set([
  "wrong_intent",
  "missing_required_tool",
  "unnecessary_tool_call",
  "forbidden_tool_call",
  "wrong_tool",
  "wrong_arguments",
  "wrong_tool_order",
  "missing_clarification",
  "hallucinated_tool_result",
  "ignored_tool_result",
  "unsafe_or_policy_violation",
  "poor_failure_recovery"
]);

const LOCAL_FAILURE_CLASS_MAP = new Map([
  ["bad_final_response", "wrong_intent"],
  ["output_schema_invalid", "wrong_intent"],
  ["unknown_failure", "wrong_intent"]
]);

const MEDIA_CHANNEL_ORDER = ["audio", "files", "images", "video", "vm_stream"];

export function canonicalPrimaryFailureClass(value, passed = false) {
  const failureClass = typeof value === "string" ? value.trim() : "";
  if (failureClass === "none") {
    return passed ? "none" : "wrong_intent";
  }
  if (CANONICAL_FAILURE_CLASSES.has(failureClass)) {
    return failureClass;
  }
  if (LOCAL_FAILURE_CLASS_MAP.has(failureClass)) {
    return LOCAL_FAILURE_CLASS_MAP.get(failureClass);
  }
  return passed ? "none" : "wrong_intent";
}

export function getGradeByCase(gradeFixture = {}) {
  const grades = Array.isArray(gradeFixture.grade_results) ? gradeFixture.grade_results : [];
  return new Map(grades.map((grade) => [grade.case_id, grade]));
}

function selectFailureAnalysis(grade = {}, primaryFailureClass = "none", passed = false) {
  const judgeResults = Array.isArray(grade.judge_results) ? grade.judge_results : [];
  const analyses = judgeResults
    .map((judge) => judge.failure_analysis)
    .filter((analysis) => analysis && typeof analysis === "object");

  if (passed) {
    return analyses.find((analysis) => analysis.primary_failure_class !== "none") || null;
  }

  const matchingPrimary = analyses.find((analysis) => (
    analysis.primary_failure_class
    && analysis.primary_failure_class !== "none"
    && canonicalPrimaryFailureClass(analysis.primary_failure_class, false) === primaryFailureClass
  ));
  if (matchingPrimary) {
    return matchingPrimary;
  }

  const failedJudge = judgeResults.find((judge) => (
    judge.passed === false
    && judge.failure_analysis
    && judge.failure_analysis.primary_failure_class !== "none"
  ));
  if (failedJudge) {
    return failedJudge.failure_analysis;
  }

  return analyses.find((analysis) => analysis.primary_failure_class !== "none") || null;
}

export function normalizeCases(runFixture = {}, gradeFixture = {}) {
  const gradeByCase = getGradeByCase(gradeFixture);
  const runs = Array.isArray(runFixture.runs)
    ? runFixture.runs
    : runFixture.run_id
      ? [runFixture]
      : [];

  return runs.flatMap((run) => {
    const cases = Array.isArray(run.cases) ? run.cases : [];
    return cases.map((caseResult) => {
      const grade = gradeByCase.get(caseResult.case_id) || caseResult.grade || {};
      const passed = typeof grade.passed === "boolean"
        ? grade.passed
        : caseResult.status === "passed";
      const rawPrimaryFailureClass = grade.primary_failure_class
        || caseResult.primary_failure_class
        || "";
      const primaryFailureClass = canonicalPrimaryFailureClass(rawPrimaryFailureClass, passed);
      const failureAnalysis = selectFailureAnalysis(grade, primaryFailureClass, passed);
      const failureSummary = caseResult.failure_summary
        || failureAnalysis?.summary
        || (passed ? "Passed." : "Failure requires triage.");

      return {
        ...caseResult,
        run_id: run.run_id,
        dataset_id: run.dataset_id,
        runner_id: run.runner_id,
        run_status: run.status,
        passed,
        score: normalizeScore(grade.score ?? caseResult.score),
        primary_failure_class: primaryFailureClass,
        raw_primary_failure_class: rawPrimaryFailureClass,
        failure_summary: failureSummary,
        severity: caseResult.severity
          || failureAnalysis?.severity
          || (passed ? "none" : "major"),
        judge_results: grade.judge_results || [],
        judge_modes: (grade.judge_results || []).map((judge) => judge.judge_mode).filter(Boolean),
        score_band: scoreBand(grade.score ?? caseResult.score),
        grade
      };
    });
  });
}

export function getFilterOptions(cases = []) {
  const uniqueSorted = (values) => [...new Set(values.filter(Boolean))].sort();
  return {
    statuses: ["passed", "failed"],
    families: uniqueSorted(cases.map((item) => item.family)),
    failureClasses: uniqueSorted(cases.map((item) => item.primary_failure_class)),
    runIds: uniqueSorted(cases.map((item) => item.run_id)),
    severities: uniqueSorted(cases.map((item) => item.severity)),
    scoreBands: ["90-100", "70-89", "1-69", "0"],
    judgeModes: uniqueSorted(cases.flatMap((item) => item.judge_modes || []))
  };
}

export function filterCases(cases = [], filters = {}) {
  const {
    status = "all",
    family = "all",
    failureClass = "all",
    runId = "all",
    severity = "all",
    scoreBand: selectedScoreBand = "all",
    judgeMode = "all"
  } = filters;

  return cases.filter((item) => {
    const caseStatus = item.passed ? "passed" : "failed";
    return (status === "all" || caseStatus === status)
      && (family === "all" || item.family === family)
      && (failureClass === "all" || item.primary_failure_class === failureClass)
      && (runId === "all" || item.run_id === runId)
      && (severity === "all" || item.severity === severity)
      && (selectedScoreBand === "all" || item.score_band === selectedScoreBand)
      && (judgeMode === "all" || (item.judge_modes || []).includes(judgeMode));
  });
}

export function buildDashboardSummary(runFixture = {}, gradeFixture = {}) {
  const runs = Array.isArray(runFixture.runs)
    ? runFixture.runs
    : runFixture.run_id
      ? [runFixture]
      : [];
  const cases = normalizeCases(runFixture, gradeFixture);
  const totalCases = cases.length;
  const passed = cases.filter((item) => item.passed).length;
  const failed = totalCases - passed;
  const mediaEvidenceCases = cases.filter(hasMediaEvidence).length;
  const vmStreamCases = cases.filter((item) => (item.media_evidence?.vm_streams || []).length > 0).length;
  const avgScore = totalCases
    ? Math.round((cases.reduce((sum, item) => sum + normalizeScore(item.score), 0) / totalCases) * 10) / 10
    : 0;

  return {
    totalRuns: runs.length,
    totalCases,
    passed,
    failed,
    passRate: totalCases ? Math.round((passed / totalCases) * 1000) / 10 : 0,
    avgScore,
    traceCompleteness: runs.length
      ? Math.round((runs.reduce((sum, run) => sum + (run.trace_completeness || 0), 0) / runs.length) * 1000) / 10
      : 0,
    mediaEvidenceCases,
    vmStreamCases,
    lastRunId: runs[0]?.run_id || "none"
  };
}

export function summarizeCoverage(coverageFixture = {}) {
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const available = isObject(coverageFixture) && Object.keys(coverageFixture).length > 0;
  const missing = (value) => Array.isArray(value) ? value : [];
  const mapping = (value) => isObject(value) ? value : {};
  const countKeys = (value) => Object.keys(mapping(value)).length;

  return {
    available,
    schema_version: available ? coverageFixture.schema_version || "unknown" : "none",
    pack_id: available ? coverageFixture.pack_id || "unknown" : "none",
    meets_assignment_minimums: coverageFixture.meets_assignment_minimums === true,
    assignment_checks: mapping(coverageFixture.assignment_checks),
    scenario_count: coverageFixture.scenario_count || 0,
    scenario_dimension_minimums: mapping(coverageFixture.scenario_dimension_minimums),
    scenario_dimension_checks: mapping(coverageFixture.scenario_dimension_checks),
    scenario_dimension_counts: mapping(coverageFixture.scenario_dimension_counts),
    scenario_dimension_scenarios: mapping(coverageFixture.scenario_dimension_scenarios),
    thin_scenario_dimensions: mapping(coverageFixture.thin_scenario_dimensions),
    scenario_quality_targets: mapping(coverageFixture.scenario_quality_targets),
    scenario_quality_warnings: missing(coverageFixture.scenario_quality_warnings),
    scenario_quality_warning_count: missing(coverageFixture.scenario_quality_warnings).length,
    difficulty_counts: mapping(coverageFixture.difficulty_counts),
    action_count_counts: mapping(coverageFixture.action_count_counts),
    multi_turn_scenario_count: coverageFixture.multi_turn_scenario_count || 0,
    environment_counts: mapping(coverageFixture.environment_counts),
    tag_counts: mapping(coverageFixture.tag_counts),
    tool_policy_shape_counts: mapping(coverageFixture.tool_policy_shape_counts),
    required_tool_counts: mapping(coverageFixture.required_tool_counts),
    optional_tool_counts: mapping(coverageFixture.optional_tool_counts),
    forbidden_tool_counts: mapping(coverageFixture.forbidden_tool_counts),
    ordered_tool_count: coverageFixture.ordered_tool_count || 0,
    ordered_tool_pairs: mapping(coverageFixture.ordered_tool_pairs),
    fixture_scenario_count: coverageFixture.fixture_scenario_count || 0,
    fixture_type_counts: mapping(coverageFixture.fixture_type_counts),
    fixture_ref_counts_by_scenario: mapping(coverageFixture.fixture_ref_counts_by_scenario),
    rubric_class_count: Array.isArray(coverageFixture.rubric_classes) ? coverageFixture.rubric_classes.length : 0,
    judge_mode_count: Array.isArray(coverageFixture.judge_modes) ? coverageFixture.judge_modes.length : 0,
    primary_failure_class_count: countKeys(coverageFixture.primary_failure_class_counts),
    golden_case_count: coverageFixture.golden_case_count || 0,
    golden_failure_class_count: countKeys(coverageFixture.golden_failure_class_counts),
    golden_failure_class_cases: mapping(coverageFixture.golden_failure_class_cases),
    golden_failure_classes_missing: missing(coverageFixture.golden_failure_classes_missing),
    thin_golden_failure_classes: mapping(coverageFixture.thin_golden_failure_classes),
    executable_run_case_count: coverageFixture.executable_run_case_count || 0,
    executable_failure_class_count: countKeys(coverageFixture.executable_failure_class_counts),
    executable_failure_class_cases: mapping(coverageFixture.executable_failure_class_cases),
    executable_failure_classes_missing: missing(coverageFixture.executable_failure_classes_missing),
    thin_executable_failure_classes: mapping(coverageFixture.thin_executable_failure_classes),
    executable_media_case_count: coverageFixture.executable_media_case_count || 0,
    executable_tool_output_grounding_case_count: coverageFixture.executable_tool_output_grounding_case_count || 0,
    executable_media_expected_class_counts: mapping(coverageFixture.executable_media_expected_class_counts),
    executable_media_case_refs: missing(coverageFixture.executable_media_case_refs),
    executable_tool_output_grounding_case_refs: missing(coverageFixture.executable_tool_output_grounding_case_refs),
    coverage_warnings: missing(coverageFixture.coverage_warnings),
    coverage_warning_count: missing(coverageFixture.coverage_warnings).length
  };
}

export function summarizeEvidenceReadiness(evidenceFixture = {}) {
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const available = isObject(evidenceFixture) && Object.keys(evidenceFixture).length > 0;
  const missing = (value) => Array.isArray(value) ? value : [];
  const mapping = (value) => isObject(value) ? value : {};
  const ashr = mapping(evidenceFixture.ashr_grading_preflight);
  const semantic = mapping(evidenceFixture.semantic_judge_preflight);
  const redaction = mapping(evidenceFixture.redaction_policy);

  return {
    available,
    schema_version: available ? evidenceFixture.schema_version || "unknown" : "none",
    status: available ? evidenceFixture.status || "unknown" : "none",
    ready_for_external_collection: evidenceFixture.ready_for_external_collection === true,
    calibration_case_count: evidenceFixture.calibration_case_count || 0,
    readiness_checks: mapping(evidenceFixture.readiness_checks),
    ashr_current_missing: ashr.current_missing || 0,
    ashr_expected_observation_count: ashr.expected_observation_count || 0,
    ashr_case_map_covers_all_calibration_cases: ashr.case_map_covers_all_calibration_cases === true,
    semantic_offline_reference_only: semantic.offline_reference_only === true,
    semantic_expected_reviewed_observation_count: semantic.expected_reviewed_observation_count || 0,
    semantic_required_fields: missing(semantic.required_fields),
    required_sdk_languages: missing(semantic.required_sdk_languages),
    covered_sdk_languages: missing(semantic.covered_sdk_languages),
    batch_plan_refs: missing(evidenceFixture.batch_plan_refs),
    private_raw_path: redaction.raw_private_path || "",
    never_commit: missing(redaction.never_commit)
  };
}

export function summarizeRequestProvenance(requestFixture = {}) {
  const requests = extractRequestObjects(requestFixture);
  const statusCounts = requests.reduce((counts, request) => {
    const status = request.request_status || request.status || "unknown";
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});
  const latestRequest = [...requests].sort((left, right) => (
    Date.parse(right.created_at || right.completed_at || "") - Date.parse(left.created_at || left.completed_at || "")
  ))[0] || null;

  if (!latestRequest) {
    return {
      available: false,
      total_requests: 0,
      status_counts: {},
      latest_request: null
    };
  }

  const requestBody = latestRequest.request || {};
  const acceptedInputs = objectOr(requestBody.agent?.accepted_inputs);
  const generationOptions = objectOr(requestBody.generation_options);
  const testConfig = objectOr(requestBody.test_config);
  const tools = Array.isArray(requestBody.agent?.tools)
    ? requestBody.agent.tools
    : Array.isArray(latestRequest.request_input_schema?.tools)
      ? latestRequest.request_input_schema.tools
      : [];

  return {
    available: true,
    total_requests: requests.length,
    status_counts: statusCounts,
    latest_request: {
      request_id: firstText(latestRequest.id, latestRequest.request_id, "unknown_request"),
      request_name: firstText(latestRequest.request_name, requestBody.metadata?.dataset_name, "unnamed request"),
      request_status: firstText(latestRequest.request_status, latestRequest.status, "unknown"),
      created_at: latestRequest.created_at || "",
      completed_at: latestRequest.completed_at || "",
      actual_duration_s: numberOrNull(latestRequest.actual_duration_s),
      estimated_duration_s: numberOrNull(latestRequest.estimated_duration_s),
      has_failure: Boolean(requestBody._failure) || latestRequest.request_status === "failed",
      accepted_input_types: truthyKeys(acceptedInputs),
      generation_outputs: truthyKeys(generationOptions),
      test_strategy: firstText(testConfig.strategy, "unknown"),
      num_variations: numberOrNull(testConfig.num_variations),
      coverage: objectOr(testConfig.coverage),
      tool_count: tools.length,
      output_format: firstText(requestBody.agent?.output_format?.type, "unknown"),
      context_keys: Object.keys(objectOr(requestBody.context)).sort()
    }
  };
}

export function summarizeUsageQuota(usageFixture = {}, usageApiProbe = {}) {
  const frontendModules = Array.isArray(usageFixture.frontend_known_modules)
    ? usageFixture.frontend_known_modules
    : [];
  const apiPaths = objectOr(usageFixture.api_paths);
  const apiProbeCalls = objectOr(usageApiProbe.calls);
  const apiProbeFieldPaths = objectOr(usageApiProbe.field_paths);
  const apiFunctions = Array.isArray(usageApiProbe.frontend_source_functions)
    ? usageApiProbe.frontend_source_functions
    : [];
  const channels = uniqueSorted([
    ...frontendModules,
    ...Object.keys(apiPaths),
    ...Object.keys(apiProbeFieldPaths)
  ].flatMap((value) => usageQuotaChannelsFromText(value)));
  const apiCallStatuses = Object.fromEntries(Object.entries(apiProbeCalls).map(([name, call]) => [
    name,
    {
      ok: call?.ok === true,
      status_code: numberOrNull(call?.status_code),
      error: firstText(call?.error?.message, "")
    }
  ]));
  const directApiAccessible = Object.values(apiCallStatuses).some((call) => call.ok);
  const oauthOnlyFunctions = Object.entries(apiCallStatuses)
    .filter(([, call]) => call.status_code === 403 && /oauth/i.test(call.error))
    .map(([name]) => name)
    .sort();

  return {
    available: frontendModules.length > 0 || Object.keys(apiPaths).length > 0 || Object.keys(apiProbeCalls).length > 0,
    frontend_modules: frontendModules,
    channels,
    api_confirmed: usageFixture.api_confirmed === true || Object.keys(apiPaths).length > 0,
    api_path_count: Object.keys(apiPaths).length + Object.keys(apiProbeFieldPaths).length,
    frontend_source_functions: uniqueSorted([...apiFunctions, ...Object.keys(apiProbeCalls)]),
    direct_api_accessible: directApiAccessible,
    oauth_only_functions: oauthOnlyFunctions,
    api_call_statuses: apiCallStatuses,
    guidance: directApiAccessible
      ? "Usage/quota fields can be mapped from the API probe."
      : oauthOnlyFunctions.length
        ? "Usage/quota counters are visible in the official frontend, but direct API-key access is OAuth-gated."
        : "Usage/quota remains a frontend-confirmed product concept without a direct API-key sample."
  };
}

export function summarizeMediaReadiness(runFixture = {}, gradeFixture = {}, usageFixture = {}, mediaSignedUrlFixture = {}) {
  const cases = normalizeCases(runFixture, gradeFixture);
  const mediaCases = cases.filter(hasMediaEvidence);
  const evidenceItems = mediaCases.flatMap((item) => item.media_evidence?.evidence_items || []);
  const vmStreams = mediaCases.flatMap((item) => item.media_evidence?.vm_streams || []);
  const usageChannels = summarizeUsageQuota(usageFixture, {}).channels;
  const signedUrlByType = objectOr(mediaSignedUrlFixture.signed_url_by_nearest_type);
  const outputPathByType = objectOr(mediaSignedUrlFixture.output_path_by_nearest_type);
  const acceptedInputFlags = objectOr(mediaSignedUrlFixture.accepted_input_flags);
  const generationOutputFlags = objectOr(mediaSignedUrlFixture.generation_output_flags);
  const conclusion = objectOr(mediaSignedUrlFixture.conclusion);
  const rawMediaTypes = [
    ...usageChannels,
    ...mediaCases.flatMap((item) => item.media_evidence?.media_types || []),
    ...mediaCases.map((item) => item.media_evidence?.primary_media_type),
    ...evidenceItems.map((item) => item.type),
    ...Object.keys(signedUrlByType),
    ...Object.keys(outputPathByType),
    ...Object.keys(acceptedInputFlags),
    ...Object.keys(generationOutputFlags).map((key) => key.replace(/^generate_/, "").replace(/s$/, ""))
  ].filter(Boolean);
  const channels = sortMediaChannels(rawMediaTypes.map(canonicalMediaChannel).filter(Boolean));
  const confirmedSignedUrlTypes = sortMediaChannels(Object.entries(signedUrlByType)
    .filter(([, count]) => Number(count) > 0)
    .map(([type]) => canonicalMediaChannel(type))
    .filter(Boolean));
  const outputPathTypes = sortMediaChannels(Object.entries(outputPathByType)
    .filter(([, count]) => Number(count) > 0)
    .map(([type]) => canonicalMediaChannel(type))
    .filter(Boolean));
  const signedUrlKeyCount = numberOrNull(mediaSignedUrlFixture.signed_url_key_count) ?? countObjectValues(signedUrlByType);
  const outputPathKeyCount = numberOrNull(mediaSignedUrlFixture.output_path_key_count) ?? countObjectValues(outputPathByType);
  const renderLiveLinks = conclusion.render_live_signed_links_in_a3 === true;
  const unconfirmedSignedUrlTypes = ["audio", "images", "video"].filter((type) => (
    channels.includes(type) && !confirmedSignedUrlTypes.includes(type)
  ));
  const channelMatrix = buildMediaChannelMatrix({
    channels,
    usageChannels,
    mediaCases,
    outputPathTypes,
    confirmedSignedUrlTypes,
    unconfirmedSignedUrlTypes,
    renderLiveLinks
  });
  const evidenceQueue = buildMediaEvidenceQueue(mediaCases, {
    confirmedSignedUrlTypes,
    unconfirmedSignedUrlTypes,
    renderLiveLinks
  });

  return {
    available: mediaCases.length > 0 || channels.length > 0 || signedUrlKeyCount > 0 || outputPathKeyCount > 0,
    media_case_count: mediaCases.length,
    evidence_item_count: evidenceItems.length,
    vm_stream_count: vmStreams.length,
    channels,
    output_path_key_count: outputPathKeyCount,
    output_path_types: outputPathTypes,
    signed_url_key_count: signedUrlKeyCount,
    signed_url_confirmed_types: confirmedSignedUrlTypes,
    signed_url_unconfirmed_types: unconfirmedSignedUrlTypes,
    live_rendering_allowed: renderLiveLinks,
    values_redacted: mediaSignedUrlFixture.signed_url_values_saved === false || mediaSignedUrlFixture.safety?.signed_url_values_saved === false,
    safety: objectOr(mediaSignedUrlFixture.safety),
    channel_matrix: channelMatrix,
    evidence_queue: evidenceQueue,
    evidence_queue_count: evidenceQueue.length,
    guidance: renderLiveLinks
      ? "Live signed media links can be rendered from the current evidence."
      : "Render media metadata only. Do not render live signed URLs until audio/image/video signed URL and expiry behavior are confirmed.",
    known_gaps: uniqueSorted([
      ...mediaCases.flatMap((item) => item.media_evidence?.known_gaps || []),
      ...unconfirmedSignedUrlTypes.map((type) => `${type} signed URL behavior is unconfirmed.`),
      confirmedSignedUrlTypes.length === 1 && confirmedSignedUrlTypes[0] === "files"
        ? "Only file-like signed_url fields are confirmed in the redacted sample."
        : "",
      conclusion.reason || ""
    ])
  };
}

export function summarizeCloudConsoleShell(authFixture = {}, frontendFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}) {
  const authOk = authFixture.auth_ok === true || authFixture.calls?.init?.ok === true || authFixture.calls?.health_check?.ok === true;
  const frontendAuth = objectOr(frontendFixture.auth_state);
  const frontendSessionValid = frontendAuth.frontend_session_valid === true;
  const pages = Array.isArray(frontendFixture.pages) ? frontendFixture.pages : [];
  const pageNames = pages.map((page) => page.page).filter(Boolean);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const observedPageCount = pageNames.length;

  const sections = [
    {
      area: "Auth session",
      status: authOk || frontendSessionValid ? "observed" : "mock-only",
      detail: authOk && frontendSessionValid
        ? "API-key auth and manual frontend session were both observed with redacted evidence."
        : authOk
          ? "API-key auth was observed; frontend session state is not loaded for this source."
          : "No auth fixture is loaded; keep this as a local mock shell."
    },
    {
      area: "Workspace / tenant",
      status: authOk ? "redacted" : "mock-only",
      detail: authOk
        ? "Tenant/user existence was confirmed, but names, ids, plan, and email stay redacted."
        : "Show workspace shape only; do not store account values."
    },
    {
      area: "Datasets / runs",
      status: requestProvenance.available ? "read-only samples" : "local fixtures",
      detail: requestProvenance.available
        ? "Request and dataset provenance can be shown from redacted samples."
        : "Mock fixtures cover the evaluation flow without cloud access."
    },
    {
      area: "Usage / billing",
      status: usageQuota.oauth_only_functions.length ? "OAuth-gated" : usageQuota.available ? "frontend-confirmed" : "known gap",
      detail: usageQuota.available
        ? usageQuota.guidance
        : "Keep billing/usage as a product shell until a safe source is available."
    },
    {
      area: "API keys",
      status: "disabled",
      detail: "Do not copy create/revoke/show-secret flows. Only show setup status and safety policy."
    },
    {
      area: "Team",
      status: "disabled",
      detail: "Do not copy invites or member administration in the A3 MVP."
    },
    {
      area: "Trust / report",
      status: "report-only",
      detail: "A3 uses local export/print reports instead of public certificate publishing."
    },
    {
      area: "Cloud mutations",
      status: "disabled",
      detail: "No create, delete, publish, invite, billing, or key-management actions are wired."
    }
  ];
  const actions = buildCloudActionGuardrails({
    authOk,
    frontendSessionValid,
    requestProvenance,
    usageQuota,
    observedPageCount
  });

  return {
    available: authOk || frontendSessionValid || observedPageCount > 0 || requestProvenance.available || usageQuota.available,
    auth_observed: authOk,
    frontend_session_observed: frontendSessionValid,
    observed_page_count: observedPageCount,
    observed_pages: pageNames,
    real_mutations_enabled: false,
    secret_values_allowed: false,
    sections,
    actions,
    recommendation: "Mimic the official cloud console as a read-only shell: show workspace, auth, usage, API-key, team, and trust status, but do not implement real account or cloud mutations."
  };
}

export function summarizeOfficialAshrGap(runFixture = {}, gradeFixture = {}, coverageFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const hasFailures = summary.failed > 0;
  const hasExpectedActual = cases.some((item) => isObject(item.expected) || isObject(item.actual));
  const hasToolDiffs = cases.some((item) => buildToolCallDiffs(item).length > 0);
  const hasMediaEvidence = summary.mediaEvidenceCases > 0;

  const copied = [
    gapItem("Runs", summary.totalRuns > 0, "Run list and execution-batch summary are available."),
    gapItem("Case detail", summary.totalCases > 0, "Selected case view shows status, score, judge evidence, and trace."),
    gapItem("Expected vs actual", hasExpectedActual, "Expected response/tool calls can be compared against actual output."),
    gapItem("Tool-call inspection", hasToolDiffs, "Tool-call diff shows wrong, missing, extra, reordered, and argument-level mismatches."),
    gapItem("Failure triage", hasFailures, "Failure clusters and triage queue turn raw failures into debugging work."),
    gapItem("Report export", true, "JSON, CSV, Markdown, and print/PDF flows are wired."),
    gapItem("Media evidence", hasMediaEvidence, "A3 preserves media metadata when redacted Ashr samples provide it.")
  ].filter((item) => item.confirmed);

  const partial = [
    gapItem("Datasets", summary.totalRuns > 0, "A3 shows dataset identity and joined titles, but not the full official dataset generator."),
    gapItem("Analytics", summary.totalCases > 0, "A3 has pass-rate, score, coverage, and failure analytics, but not official charts by account."),
    gapItem("Requests", requestProvenance.available, "A3 can show generation provenance from redacted request samples."),
    gapItem("Usage / quota", usageQuota.available, usageQuota.guidance),
    gapItem("Coverage health", coverage.available, "A3 shows A2 scenario and failure-class coverage instead of official hosted analytics."),
    gapItem("Frontend run detail", false, "Hosted run 11926 is API-retrievable and list_runs(summary_only) visible, but visual Results-page confirmation still needs a logged-in browser pass.")
  ];

  const blocked = [
    {
      area: "Populated official run detail",
      reason: "The official demo run 11926 exists through the API with result.tests[] and appears in the same summary_only list_runs shape used by the frontend, but the in-app browser was not logged in for visual Results-page verification.",
      next_step: "Refresh the logged-in Ashr Lab dataset 884 Results page and confirm whether run 11926 is visible in the official UI."
    },
    {
      area: "Native failure class",
      reason: "The real failed-run sample exposed score, passed, reason, and metrics, but no named backend failure_class field.",
      next_step: "Keep A3 failure classes derived until a future sample proves a native field."
    },
    {
      area: "Live signed media rendering",
      reason: "Only redacted file-like signed_url coverage is confirmed; audio/image/video signed URL behavior is not complete.",
      next_step: "Keep live media URLs out of the dashboard until access/redaction rules are clear."
    }
  ];

  const outOfScope = [
    "OAuth/login implementation",
    "API key creation or revocation",
    "Team invites and account administration",
    "Billing, upgrades, and usage enforcement",
    "Full 8-step dataset generation wizard",
    "Public Trust/certificate publishing",
    "Destructive hosted cloud operations"
  ];

  const officialPages = [
    officialPage("Datasets", "?tab=analysis", "partial", "Copy list/filter mental model; keep A3 focused on runs and cases."),
    officialPage("Dataset / Results Detail", "?tab=analysis&dataset=884", "api-summary confirmed, visual pending", "A3 can show run 11926 locally; official API summary lists it, while visual Results confirmation still needs a logged-in frontend pass."),
    officialPage("Agents", "?tab=agents", "metadata only", "Use agent as a label/filter, not a full agent registry."),
    officialPage("Folders", "?tab=folders", "not needed", "Skip folder management for the student MVP."),
    officialPage("Analytics", "?tab=analytics", "partial", "Use summary metrics, pass rate, failures, and coverage; skip account-level charts."),
    officialPage("Usage", "?tab=usage", usageQuota.available ? "partial" : "known gap", "Show quota/media state as read-only calibration evidence."),
    officialPage("Trust", "?tab=trust", "report-only", "Keep printable reports; skip public certificate publishing."),
    officialPage("API Keys", "?tab=api-keys", "out of scope", "Do not copy secret/key management."),
    officialPage("Team", "?tab=team", "out of scope", "Do not copy member invites or account administration.")
  ];

  return {
    available: true,
    copied_count: copied.length,
    partial_count: partial.filter((item) => item.confirmed).length,
    blocked_count: blocked.length,
    out_of_scope_count: outOfScope.length,
    official_pages: officialPages,
    copied,
    partial,
    blocked,
    out_of_scope: outOfScope,
    recommendation: "Keep A3 as a local read-only triage console. Copy official Ashr's navigation and evidence-review logic, but do not copy account, billing, key, team, or hosted mutation flows."
  };
}

export function summarizeOfficialFrontendMirror(mirrorFixture = {}) {
  const navigation = Array.isArray(mirrorFixture.navigation) ? mirrorFixture.navigation : [];
  const apiMethodGroups = Array.isArray(mirrorFixture.api_method_groups) ? mirrorFixture.api_method_groups : [];
  const labChunks = Array.isArray(mirrorFixture.lab_chunks) ? mirrorFixture.lab_chunks : [];
  const confirmedLabels = Array.isArray(mirrorFixture.confirmed_labels) ? mirrorFixture.confirmed_labels : [];
  const mvpRecommendations = Array.isArray(mirrorFixture.mvp_recommendations) ? mirrorFixture.mvp_recommendations : [];
  const safety = objectOr(mirrorFixture.safety);
  const available = navigation.length > 0 || apiMethodGroups.length > 0 || labChunks.length > 0;

  const pages = navigation.map((item) => {
    const decision = String(item.a3_decision || "");
    return {
      tab_id: item.tab_id || "unknown",
      label: item.label || item.tab_id || "Unknown",
      chunk: item.chunk || "unknown",
      a3_status: classifyOfficialMirrorDecision(decision),
      a3_decision: decision || "No A3 decision recorded."
    };
  });

  const groups = apiMethodGroups.map((item) => {
    const methods = Array.isArray(item.methods) ? item.methods : [];
    const decision = String(item.a3_decision || "");
    return {
      group: item.group || "unknown",
      method_count: methods.length,
      methods,
      a3_status: classifyOfficialMirrorDecision(decision),
      a3_decision: decision || "No A3 decision recorded."
    };
  });

  const statusCounts = countOfficialMirrorStatuses([...pages, ...groups]);

  return {
    available,
    source_archive: mirrorFixture.source_archive || "unknown",
    clean_room_boundary: mirrorFixture.copyright_boundary || "Clean-room summary only. Do not copy official source, styles, assets, cookies, or secrets.",
    total_files: numberOrNull(mirrorFixture.file_counts?.total_files) ?? 0,
    html_file_count: numberOrNull(mirrorFixture.file_counts?.html) ?? 0,
    javascript_file_count: numberOrNull(mirrorFixture.file_counts?.javascript) ?? 0,
    lab_chunk_count: labChunks.length,
    page_count: pages.length,
    api_group_count: groups.length,
    api_method_count: groups.reduce((sum, group) => sum + group.method_count, 0),
    confirmed_label_count: confirmedLabels.length,
    confirmed_labels: confirmedLabels,
    pages,
    api_method_groups: groups,
    copied_count: statusCounts.copy,
    partial_count: statusCounts.partial,
    future_count: statusCounts.future,
    out_of_scope_count: statusCounts.out_of_scope,
    unknown_count: statusCounts.unknown,
    safety: {
      official_source_committed: safety.official_source_committed === true,
      secret_values_allowed: safety.secret_values_allowed === true,
      raw_cookies_allowed: safety.raw_cookies_allowed === true,
      raw_tokens_allowed: safety.raw_tokens_allowed === true,
      raw_signed_urls_allowed: safety.raw_signed_urls_allowed === true
    },
    recommendation: mvpRecommendations[0] || "Use official frontend structure as product reference only, then implement A3-owned dashboard views with redacted fixtures."
  };
}

export function summarizeOfficialParityRoadmap(
  runFixture = {},
  gradeFixture = {},
  coverageFixture = {},
  requestFixture = {},
  usageFixture = {},
  usageApiProbe = {},
  mediaSignedUrlFixture = {},
  frontendMirrorFixture = {}
) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const officialGap = summarizeOfficialAshrGap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe);
  const mirror = summarizeOfficialFrontendMirror(frontendMirrorFixture);
  const media = summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, mediaSignedUrlFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const copiedPages = mirror.pages.filter((page) => page.a3_status === "copy");
  const partialPages = mirror.pages.filter((page) => page.a3_status === "partial");
  const futurePages = mirror.pages.filter((page) => page.a3_status === "future");
  const outOfScopePages = mirror.pages.filter((page) => page.a3_status === "out_of_scope");
  const priorities = [
    parityAction("Results review", "copy_now", summary.totalRuns > 0, "Keep run list, case detail, expected vs actual, score, pass/fail, and failed-case triage as the A3 core."),
    parityAction("Trace / observability", media.vm_stream_count > 0 ? "copy_now" : "next", summary.traceCompleteness >= 90, "Use official Observability as inspiration for trace timeline, replay, latency, and tool-error review."),
    parityAction("Media evidence", media.available ? "copy_now" : "next", media.available, media.guidance),
    parityAction("Usage / quota", usageQuota.available ? "read_only" : "next", usageQuota.available, "Show quota and billing-adjacent signals as read-only evidence; do not copy checkout or enforcement."),
    parityAction("Trust / audit", "copy_as_report", true, "Use official Trust ideas through local audit bundle, verifier, print/PDF, and release sign-off reports."),
    parityAction("API keys / team / billing", "do_not_copy", false, "Keep OAuth, key creation, team invites, billing portal, and destructive cloud mutations out of the student MVP.")
  ];
  const mediaActions = [
    ...media.signed_url_unconfirmed_types.map((channel) => parityAction(`${channel} signed URL`, "calibrate_next", false, `Collect a redacted ${channel} sample before rendering live previews.`)),
    media.evidence_queue_count > 0
      ? parityAction("Media evidence queue", "copy_now", true, `${media.evidence_queue_count} media case(s) can be reviewed with metadata-only previews.`)
      : parityAction("Media evidence queue", "next", false, "Add redacted audio/image/video/file examples before claiming official media parity.")
  ];

  return {
    schema_version: "a3.official_parity_roadmap.v1",
    available: officialGap.available || mirror.available || media.available,
    official_gap_blocked_count: officialGap.blocked_count,
    official_gap_blocked_areas: officialGap.blocked.map((item) => item.area),
    official_pages_observed: mirror.page_count,
    copied_page_count: copiedPages.length,
    partial_page_count: partialPages.length,
    future_page_count: futurePages.length,
    out_of_scope_page_count: outOfScopePages.length,
    copied_pages: copiedPages.map((page) => page.label),
    partial_pages: partialPages.map((page) => page.label),
    future_pages: futurePages.map((page) => page.label),
    out_of_scope_pages: outOfScopePages.map((page) => page.label),
    priorities,
    media_actions: mediaActions,
    cloud_admin_boundaries: [
      "Do not implement OAuth/login for A3 MVP.",
      "Do not implement API-key creation, reveal, revoke, or storage.",
      "Do not implement billing checkout, portal, upgrade, or quota enforcement.",
      "Do not implement team invites or account administration.",
      "Keep cloud/admin concepts as read-only product shell evidence."
    ],
    next_build_order: [
      "Official Results-page visual confirmation for run 11926.",
      "Trace/Observability replay lane for top-risk cases.",
      "Redacted audio/image/video media samples and metadata-only previews.",
      "Trust/audit report improvements tied to bundle verifier.",
      "Self-host/enterprise shell that proves no secrets or cloud mutations are required."
    ],
    recommendation: "Use official Ashr for product workflow parity, but keep A3 focused on local release intelligence: results, case detail, trace, failure analysis, media evidence, reports, and audit."
  };
}

export function summarizeReleaseGate(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, options = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const media = summarizeMediaReadiness(runFixture, gradeFixture, {}, mediaSignedUrlFixture);
  const clusters = clusterFailures(runFixture, gradeFixture);
  const thresholds = normalizeReleaseGateThresholds(options.thresholds || options);
  const failedCases = cases.filter((item) => !item.passed);
  const criticalCases = failedCases.filter((item) => ["critical", "blocker"].includes(item.severity));
  const policyCases = failedCases.filter((item) => [
    "unsafe_or_policy_violation",
    "forbidden_tool_call"
  ].includes(item.primary_failure_class));
  const missingToolCases = failedCases.filter((item) => item.primary_failure_class === "missing_required_tool");
  const traceOk = summary.traceCompleteness >= thresholds.trace_completeness_min;
  const passRateOk = summary.passRate >= thresholds.pass_rate_min;
  const coverageOk = !coverage.available || coverage.meets_assignment_minimums;
  const mediaSafe = !media.live_rendering_allowed;
  const checks = [
    gateCheck("pass_rate", passRateOk, `${summary.passRate}% pass rate`, `Minimum commercial gate is ${thresholds.pass_rate_min}% before release sign-off.`),
    gateCheck("critical_failures", criticalCases.length === 0, `${criticalCases.length} critical/blocker case(s)`, "Critical or blocker failures stop release."),
    gateCheck("policy_failures", policyCases.length === 0, `${policyCases.length} safety/policy case(s)`, "Unsafe or forbidden-tool failures require safety review."),
    gateCheck("required_tool_coverage", missingToolCases.length === 0, `${missingToolCases.length} missing required tool case(s)`, "Missing required tools can hide production incident risk."),
    gateCheck("trace_evidence", traceOk, `${summary.traceCompleteness}% trace completeness`, `Release evidence needs at least ${thresholds.trace_completeness_min}% trace coverage for replay and audit.`),
    gateCheck("coverage_minimums", coverageOk, coverage.available ? `A2 coverage minimums ${coverage.meets_assignment_minimums ? "met" : "not met"}` : "coverage fixture absent", "A2 scenario coverage must be healthy when available."),
    gateCheck("media_safety", mediaSafe, media.available ? `${media.signed_url_key_count} signed URL key(s), live rendering blocked` : "no media evidence", "A3 must not render live signed media until URL safety is confirmed.")
  ];
  const failedChecks = checks.filter((check) => !check.passed);
  const hardBlock = criticalCases.length > 0
    || policyCases.length > 0
    || summary.passRate < thresholds.hard_block_pass_rate_min
    || summary.traceCompleteness < thresholds.hard_block_trace_completeness_min;
  const decision = hardBlock
    ? "block_release"
    : failedChecks.length > 0
      ? "needs_review"
      : "approve_release";
  const riskScore = Math.min(100, Math.round(
    (100 - summary.passRate)
    + criticalCases.length * 25
    + policyCases.length * 20
    + missingToolCases.length * 10
    + Math.max(0, 90 - summary.traceCompleteness)
    + (coverage.available && !coverage.meets_assignment_minimums ? 10 : 0)
  ));
  const topRiskCases = failedCases
    .sort((left, right) => releaseGateCaseWeight(right) - releaseGateCaseWeight(left) || left.score - right.score)
    .slice(0, 5)
    .map((item) => ({
      case_id: item.case_id,
      title: item.title,
      primary_failure_class: item.primary_failure_class,
      severity: item.severity,
      score: item.score,
      summary: item.failure_summary
    }));
  const requiredApprovers = unique([
    "Release owner",
    failedChecks.length ? "A3 triage owner" : null,
    policyCases.length ? "Safety reviewer" : null,
    missingToolCases.length ? "A1 runner/tooling owner" : null,
    coverage.available && !coverage.meets_assignment_minimums ? "A2 judge owner" : null,
    !traceOk ? "Evidence owner" : null,
    media.available ? "Media/security reviewer" : null
  ]);

  return {
    available: summary.totalCases > 0,
    decision,
    decision_label: decision === "approve_release" ? "Approve release" : decision === "needs_review" ? "Needs review" : "Block release",
    risk_score: riskScore,
    summary: decision === "approve_release"
      ? "Release gate passed for the loaded evidence package."
      : decision === "needs_review"
        ? "Release needs human review before sign-off."
        : "Release is blocked by high-risk evidence.",
    checks,
    failed_check_count: failedChecks.length,
    failed_checks: failedChecks.map((check) => check.id),
    thresholds,
    required_approvers: requiredApprovers,
    top_risk_cases: topRiskCases,
    pr_gate: {
      status: decision,
      github_check_name: "Ashr++ Release Gate",
      blocks_merge: decision === "block_release",
      warning_only: decision === "needs_review",
      audit_artifacts: ["json_report", "markdown_report", "print_pdf", "case_evidence"]
    },
    commercial_value: "Blocks risky agent releases, creates reviewer sign-off evidence, and gives enterprise buyers a concrete release-control artifact."
  };
}

export function summarizeReleaseWorkflow(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, options = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const gate = summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options.thresholds ? { thresholds: options.thresholds } : {});
  const runId = summary.lastRunId || "unknown-run";
  const releaseVersion = options.release_version || `candidate-${runId}`;
  const environment = options.environment || "staging";
  const owner = options.owner || "Release owner";
  const conclusion = gate.decision === "approve_release"
    ? "success"
    : gate.decision === "needs_review"
      ? "neutral"
      : "failure";
  const topRiskLines = gate.top_risk_cases.map((item) => (
    `- ${item.case_id}: ${item.primary_failure_class} / ${item.severity} / ${item.score}`
  ));
  const checkTextLines = [
    `Run: ${runId}`,
    `Release: ${releaseVersion}`,
    `Environment: ${environment}`,
    `Pass rate: ${summary.passRate}%`,
    `Average score: ${summary.avgScore}`,
    `Trace completeness: ${summary.traceCompleteness}%`,
    `Failed checks: ${gate.failed_checks.join(", ") || "none"}`,
    "",
    "Top risk cases:",
    ...(topRiskLines.length ? topRiskLines : ["- none"])
  ];
  const waiverAllowed = gate.decision === "needs_review";
  const blockWaiverExceptional = gate.decision === "block_release";
  const requiredApprovers = gate.required_approvers.length ? gate.required_approvers : [owner];

  return {
    available: gate.available,
    release_version: releaseVersion,
    environment,
    owner,
    github_check: {
      name: "Ashr++ Release Gate",
      status: "completed",
      conclusion,
      blocks_merge: gate.pr_gate.blocks_merge,
      output: {
        title: `${gate.decision_label}: ${runId}`,
        summary: `${gate.decision_label} with risk score ${gate.risk_score} and ${gate.failed_check_count} failed check(s).`,
        text: checkTextLines.join("\n")
      }
    },
    pr_comment_markdown: buildReleasePrCommentMarkdown(gate, summary, {
      release_version: releaseVersion,
      environment,
      owner
    }),
    waiver_policy: {
      required: gate.decision !== "approve_release",
      allowed: waiverAllowed,
      exceptional_only: blockWaiverExceptional,
      expiry_max_days: blockWaiverExceptional ? 1 : waiverAllowed ? 7 : 0,
      required_fields: [
        "waiver_owner",
        "business_reason",
        "risk_acceptance",
        "expiry_date",
        "follow_up_issue"
      ],
      blocked_checks: gate.failed_checks,
      guidance: blockWaiverExceptional
        ? "Blocked releases require an explicit executive exception and a one-day expiry."
        : waiverAllowed
          ? "Review releases can be waived with owner, reason, expiry, and follow-up evidence."
          : "No waiver is required for an approved release."
    },
    reviewer_workflow: {
      state: gate.decision === "approve_release" ? "ready_to_merge" : "waiting_for_review",
      required_approvers: requiredApprovers,
      review_lanes: unique([
        "Release owner",
        gate.failed_checks.includes("policy_failures") ? "Safety reviewer" : null,
        gate.failed_checks.includes("required_tool_coverage") ? "Runner/tooling owner" : null,
        gate.failed_checks.includes("coverage_minimums") ? "Judge owner" : null,
        gate.failed_checks.includes("trace_evidence") ? "Evidence owner" : null,
        "A3 triage owner"
      ]),
      next_actions: buildReleaseNextActions(gate)
    },
    audit_bundle: {
      manifest_version: "a3.audit_bundle.v1",
      redaction_policy: "No API keys, cookies, tokens, emails, or live signed media URLs are allowed in exported artifacts.",
      artifacts: [
        auditArtifact("json_report", "a3-dashboard-report.json", true, "Machine-readable release gate, cases, tool diffs, media readiness, and cloud safety evidence."),
        auditArtifact("markdown_report", "a3-dashboard-report.md", true, "Human PR/release note summary with failed checks and top risks."),
        auditArtifact("print_pdf", "browser-print-report.pdf", true, "Executive sign-off packet generated from the local print view."),
        auditArtifact("case_evidence", "normalized_cases[].tool_call_diffs", true, "Case-level expected vs actual, tool-call comparison, and judge evidence."),
        auditArtifact("redacted_fixtures", "fixtures/a3/p3/*.redacted.json", true, "Sanitized Ashr API/frontend calibration evidence."),
        auditArtifact("screenshots", "docs/screenshots/a3-dashboard-*.png", false, "Visual QA evidence with sensitive account details avoided.")
      ]
    },
    incident_replay: {
      enabled: gate.top_risk_cases.length > 0,
      case_ids: gate.top_risk_cases.map((item) => item.case_id),
      replay_mode: "failed_cases_first",
      purpose: "Let reviewers reproduce the highest-risk failures before approving a release."
    },
    commercial_value: "Turns A3 output into a PR gate, reviewer workflow, waiver policy, and audit bundle that can sit in an enterprise release process."
  };
}

export function summarizeReleaseWarRoom(
  runFixture = {},
  gradeFixture = {},
  coverageFixture = {},
  mediaSignedUrlFixture = {},
  requestFixture = {},
  usageFixture = {},
  usageApiProbe = {},
  frontendMirrorFixture = {},
  options = {}
) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const gate = summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options.thresholds ? { thresholds: options.thresholds } : {});
  const workflow = summarizeReleaseWorkflow(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const mediaReadiness = summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, mediaSignedUrlFixture);
  const officialMirror = summarizeOfficialFrontendMirror(frontendMirrorFixture);
  const incidentCaseCount = workflow.incident_replay.case_ids.length;
  const revenueRiskScore = Math.min(100, Math.round(
    gate.risk_score
    + (workflow.waiver_policy.required ? 8 : 0)
    + (incidentCaseCount > 0 ? Math.min(12, incidentCaseCount * 3) : 0)
    + (mediaReadiness.signed_url_unconfirmed_types.length > 0 ? 4 : 0)
    + (officialMirror.future_count > 0 ? 2 : 0)
  ));
  const decision = gate.decision === "approve_release"
    ? "ship_ready"
    : gate.decision === "needs_review"
      ? "review_required"
      : "no_go";
  const urgency = decision === "no_go"
    ? "stop_the_line"
    : decision === "review_required"
      ? "same_day_review"
      : "monitor_after_merge";
  const lanes = [
    warRoomLane(
      "Release Control",
      "Release owner",
      gate.pr_gate.blocks_merge ? "blocked" : gate.pr_gate.warning_only ? "review" : "ready",
      `${gate.decision_label}; risk score ${gate.risk_score}; ${gate.failed_check_count} failed gate check(s).`,
      gate.pr_gate.blocks_merge ? "Do not merge until exception approval and audit evidence are attached." : "Attach gate report to release record."
    ),
    warRoomLane(
      "Failure Triage",
      "A3 triage owner",
      gate.top_risk_cases.length ? "active" : "ready",
      `${gate.top_risk_cases.length} top-risk case(s) queued.`,
      gate.top_risk_cases.length ? "Assign owners for every top-risk case before sign-off." : "No high-risk failure queue for this run."
    ),
    warRoomLane(
      "Incident Replay",
      "Evidence owner",
      workflow.incident_replay.enabled ? "active" : "ready",
      `${incidentCaseCount} failed case(s) packaged for replay-first review.`,
      workflow.incident_replay.enabled ? "Replay highest-risk cases before approving release." : "Keep replay pack attached for audit continuity."
    ),
    warRoomLane(
      "Reviewer Workflow",
      workflow.reviewer_workflow.review_lanes.join(", ") || "Release owner",
      workflow.reviewer_workflow.state,
      `${workflow.reviewer_workflow.required_approvers.length} required approver(s); waiver required ${workflow.waiver_policy.required ? "yes" : "no"}.`,
      workflow.reviewer_workflow.next_actions[0] || "No reviewer action required."
    ),
    warRoomLane(
      "Evidence & Audit",
      "Audit owner",
      workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length ? "required" : "optional",
      `${workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length} required artifact(s); redaction policy active.`,
      "Export JSON, Markdown, print/PDF, and bundle evidence before external review."
    ),
    warRoomLane(
      "Official Product Parity",
      "Product owner",
      officialMirror.available ? "mapped" : "missing",
      officialMirror.available
        ? `${officialMirror.page_count} official page(s), ${officialMirror.api_method_count} API method(s) mapped.`
        : "No official frontend mirror summary loaded.",
      officialMirror.available ? "Keep copying review/evidence logic, not secret, billing, or team mutation flows." : "Load clean-room official frontend summary."
    )
  ];

  return {
    schema_version: "a3.release_war_room.v1",
    available: summary.totalCases > 0,
    decision,
    decision_label: decision === "ship_ready" ? "Ship ready" : decision === "review_required" ? "Review required" : "No-go",
    urgency,
    run_id: summary.lastRunId || "unknown-run",
    release_version: workflow.release_version,
    environment: workflow.environment,
    revenue_risk_score: revenueRiskScore,
    blocks_merge: gate.pr_gate.blocks_merge,
    waiver_required: workflow.waiver_policy.required,
    incident_replay_case_count: incidentCaseCount,
    required_artifact_count: workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length,
    required_approvers: workflow.reviewer_workflow.required_approvers,
    top_risk_cases: gate.top_risk_cases,
    lanes,
    executive_brief: buildWarRoomExecutiveBrief({ summary, gate, workflow, revenueRiskScore, requestProvenance, usageQuota, mediaReadiness, officialMirror }),
    customer_value: "Gives release owners one screen for no-go decisions, incident replay, reviewer sign-off, and audit evidence before an agent reaches customers.",
    enterprise_readiness: {
      local_read_only: true,
      secret_free_exports: true,
      external_mutations_enabled: false,
      self_host_ready_contract: true,
      audit_bundle_required: true
    }
  };
}

function gateCheck(id, passed, observed, detail) {
  return { id, passed, observed, detail };
}

function normalizeReleaseGateThresholds(value = {}) {
  return {
    pass_rate_min: numberOrDefault(value.pass_rate_min, 95),
    trace_completeness_min: numberOrDefault(value.trace_completeness_min, 90),
    hard_block_pass_rate_min: numberOrDefault(value.hard_block_pass_rate_min, 80),
    hard_block_trace_completeness_min: numberOrDefault(value.hard_block_trace_completeness_min, 70)
  };
}

function numberOrDefault(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildReleasePrCommentMarkdown(gate, summary, options = {}) {
  const lines = [
    "## Ashr++ Release Gate",
    "",
    `Decision: **${gate.decision_label}**`,
    `Risk score: **${gate.risk_score}**`,
    `Release: \`${options.release_version || "candidate"}\``,
    `Environment: \`${options.environment || "staging"}\``,
    `Owner: ${options.owner || "Release owner"}`,
    "",
    "| Signal | Value |",
    "|---|---|",
    `| Run | \`${summary.lastRunId || "unknown-run"}\` |`,
    `| Pass rate | ${summary.passRate}% |`,
    `| Average score | ${summary.avgScore} |`,
    `| Trace completeness | ${summary.traceCompleteness}% |`,
    `| Failed checks | ${gate.failed_checks.join(", ") || "none"} |`,
    "",
    "### Required Reviewers",
    "",
    ...(gate.required_approvers.length ? gate.required_approvers.map((item) => `- ${item}`) : ["- none"]),
    "",
    "### Top Risk Cases",
    "",
    ...(gate.top_risk_cases.length
      ? gate.top_risk_cases.map((item) => `- \`${item.case_id}\`: ${item.primary_failure_class} / ${item.severity} / ${item.score} - ${item.summary}`)
      : ["- none"]),
    ""
  ];
  return `${lines.join("\n")}\n`;
}

function buildReleaseNextActions(gate) {
  if (gate.decision === "approve_release") {
    return [
      "Attach JSON and Markdown audit artifacts to the release record.",
      "Keep the print/PDF report for sign-off evidence.",
      "Monitor the next production replay batch."
    ];
  }
  const actions = [
    "Review failed gate checks before merge.",
    "Replay the top risk cases from the incident replay pack.",
    "Attach waiver evidence only if the required approvers accept the risk."
  ];
  if (gate.failed_checks.includes("pass_rate")) {
    actions.push("Raise pass rate above the commercial threshold or narrow the release scope.");
  }
  if (gate.failed_checks.includes("required_tool_coverage")) {
    actions.push("Fix missing required tool coverage before customer-facing release.");
  }
  if (gate.failed_checks.includes("policy_failures")) {
    actions.push("Route unsafe or forbidden-tool cases to safety review.");
  }
  return actions;
}

function warRoomLane(lane, owner, status, evidence, nextAction) {
  return {
    lane,
    owner,
    status,
    evidence,
    next_action: nextAction
  };
}

function buildWarRoomExecutiveBrief({
  summary,
  gate,
  workflow,
  revenueRiskScore,
  requestProvenance,
  usageQuota,
  mediaReadiness,
  officialMirror
} = {}) {
  return [
    `${gate.decision_label} for run ${summary.lastRunId || "unknown-run"} with ${summary.passRate}% pass rate and ${summary.failed} failed case(s).`,
    `Revenue risk score is ${revenueRiskScore}; PR gate ${workflow.github_check.blocks_merge ? "blocks merge" : workflow.github_check.conclusion}.`,
    workflow.incident_replay.enabled
      ? `${workflow.incident_replay.case_ids.length} case(s) are packaged for replay-first incident review.`
      : "No failed case replay pack is required for the current evidence package.",
    `${workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length} required audit artifact(s) must travel with the release record.`,
    requestProvenance.available
      ? `Request provenance is available for ${requestProvenance.total_requests} request sample(s).`
      : "Request provenance is not available for this source.",
    usageQuota.available
      ? `Usage/quota calibration is present; direct API-key access ${usageQuota.direct_api_accessible ? "works" : "is limited or OAuth-gated"}.`
      : "Usage/quota calibration is not loaded.",
    mediaReadiness.available
      ? `Media evidence is present with live rendering ${mediaReadiness.live_rendering_allowed ? "allowed" : "blocked by safety"}.`
      : "No media evidence is loaded.",
    officialMirror.available
      ? `Official frontend mirror maps ${officialMirror.page_count} page(s) and ${officialMirror.api_method_count} API method name(s).`
      : "Official frontend mirror map is not loaded."
  ];
}

function auditArtifact(id, path, required, purpose) {
  return { id, path, required, purpose };
}

function releaseGateCaseWeight(item) {
  const severityWeight = {
    critical: 5,
    blocker: 5,
    high: 4,
    major: 3,
    medium: 2,
    minor: 1,
    low: 1,
    none: 0
  };
  const failureWeight = {
    unsafe_or_policy_violation: 5,
    forbidden_tool_call: 4,
    missing_required_tool: 3,
    wrong_tool: 3,
    wrong_arguments: 2
  };
  return (severityWeight[item.severity] || 0) * 1000
    + (failureWeight[item.primary_failure_class] || 0) * 100
    + (100 - Number(item.score || 0));
}

function unique(values = []) {
  return [...new Set(values.filter(Boolean))];
}

function gapItem(area, confirmed, note) {
  return {
    area,
    confirmed: Boolean(confirmed),
    note
  };
}

function officialPage(page, path, a3Status, mvpDecision) {
  return {
    page,
    path,
    a3_status: a3Status,
    mvp_decision: mvpDecision
  };
}

function classifyOfficialMirrorDecision(decision = "") {
  const text = String(decision).toLowerCase();
  if (!text.trim()) {
    return "unknown";
  }
  if (text.includes("future")) {
    return "future";
  }
  if (text.includes("highest priority") || text.includes("copy dataset/run/case")) {
    return "copy";
  }
  if (text.includes("copy audit") || text.includes("copy report") || text.includes("copy pass-rate")) {
    return "partial";
  }
  if (
    text.includes("do not copy")
    || text.includes("skip")
    || text.includes("out of scope")
    || text.includes("low priority")
  ) {
    return "out_of_scope";
  }
  if (
    text.includes("copy")
    || text.includes("show")
    || text.includes("read-only")
    || text.includes("use ")
  ) {
    return "partial";
  }
  return "unknown";
}

function countOfficialMirrorStatuses(items = []) {
  const counts = {
    copy: 0,
    partial: 0,
    future: 0,
    out_of_scope: 0,
    unknown: 0
  };
  for (const item of items) {
    const status = item.a3_status;
    if (status in counts) {
      counts[status] += 1;
    } else {
      counts.unknown += 1;
    }
  }
  return counts;
}

function usageQuotaChannelsFromText(value = "") {
  const text = String(value).toLowerCase();
  return [
    text.includes("image") ? "images" : "",
    text.includes("audio") ? "audio" : "",
    text.includes("file") ? "files" : "",
    text.includes("video") ? "video" : ""
  ].filter(Boolean);
}

function buildMediaChannelMatrix({
  channels = [],
  usageChannels = [],
  mediaCases = [],
  outputPathTypes = [],
  confirmedSignedUrlTypes = [],
  unconfirmedSignedUrlTypes = [],
  renderLiveLinks = false
} = {}) {
  return channels.map((channel) => {
    const caseEvidenceCount = mediaCases.filter((item) => caseHasMediaChannel(item, channel)).length;
    const signedUrlConfirmed = confirmedSignedUrlTypes.includes(channel);
    const signedUrlUnconfirmed = unconfirmedSignedUrlTypes.includes(channel);
    const outputPathConfirmed = outputPathTypes.includes(channel);
    const usageObserved = usageChannels.includes(channel);
    const livePreviewAllowed = renderLiveLinks && signedUrlConfirmed && !signedUrlUnconfirmed;
    const previewPolicy = livePreviewAllowed
      ? "live_preview_allowed"
      : signedUrlConfirmed
        ? "redacted_signed_url_metadata_only"
        : channel === "vm_stream"
          ? "vm_stream_summary_only"
          : "metadata_only";

    return {
      channel,
      usage_observed: usageObserved,
      case_evidence_count: caseEvidenceCount,
      output_path_confirmed: outputPathConfirmed,
      signed_url_confirmed: signedUrlConfirmed,
      signed_url_unconfirmed: signedUrlUnconfirmed,
      live_preview_allowed: livePreviewAllowed,
      preview_policy: previewPolicy,
      decision: mediaChannelDecision(channel, {
        caseEvidenceCount,
        outputPathConfirmed,
        signedUrlConfirmed,
        signedUrlUnconfirmed,
        livePreviewAllowed
      })
    };
  });
}

function buildMediaEvidenceQueue(mediaCases = [], {
  confirmedSignedUrlTypes = [],
  unconfirmedSignedUrlTypes = [],
  renderLiveLinks = false
} = {}) {
  return mediaCases
    .map((item) => {
      const evidence = item.media_evidence || {};
      const evidenceItems = Array.isArray(evidence.evidence_items) ? evidence.evidence_items : [];
      const vmStreams = Array.isArray(evidence.vm_streams) ? evidence.vm_streams : [];
      const mediaTypes = sortMediaChannels([
        evidence.primary_media_type,
        ...(Array.isArray(evidence.media_types) ? evidence.media_types : []),
        ...evidenceItems.map((entry) => entry.type),
        ...vmStreams.map((entry) => entry.type || "vm_stream")
      ].map(canonicalMediaChannel).filter(Boolean));
      const primaryMediaType = canonicalMediaChannel(evidence.primary_media_type)
        || mediaTypes[0]
        || (vmStreams.length ? "vm_stream" : "files");
      const hasConfirmedSignedUrl = mediaTypes.some((type) => confirmedSignedUrlTypes.includes(type));
      const hasUnconfirmedSignedUrl = mediaTypes.some((type) => unconfirmedSignedUrlTypes.includes(type));
      const safeToRender = renderLiveLinks && hasConfirmedSignedUrl && !hasUnconfirmedSignedUrl;
      const signedUrlStatus = hasConfirmedSignedUrl
        ? "confirmed_redacted_metadata"
        : hasUnconfirmedSignedUrl
          ? "unconfirmed"
          : "not_observed";
      const previewPolicy = safeToRender
        ? "live_preview_allowed"
        : hasConfirmedSignedUrl
          ? "redacted_signed_url_metadata_only"
          : primaryMediaType === "vm_stream"
            ? "vm_stream_summary_only"
            : "metadata_only";
      const knownGaps = uniqueSorted([
        ...(Array.isArray(evidence.known_gaps) ? evidence.known_gaps : []),
        hasUnconfirmedSignedUrl ? `${primaryMediaType} signed URL behavior is unconfirmed.` : "",
        safeToRender ? "" : "Live preview is disabled until signed URL safety is confirmed."
      ]);

      return {
        case_id: item.case_id || "unknown_case",
        scenario_id: item.scenario_id || "unknown_scenario",
        title: item.title || "Untitled media case",
        status: item.passed ? "passed" : "failed",
        score: normalizeScore(item.score),
        severity: item.severity || "none",
        primary_failure_class: item.primary_failure_class || "none",
        primary_media_type: primaryMediaType,
        media_types: mediaTypes,
        evidence_count: evidenceItems.length,
        vm_stream_count: vmStreams.length,
        signed_url_status: signedUrlStatus,
        preview_policy: previewPolicy,
        safe_to_render: safeToRender,
        next_action: safeToRender
          ? "Render live preview only from fresh runtime URLs."
          : hasUnconfirmedSignedUrl
            ? "Collect a redacted signed URL shape for this channel before live rendering."
            : "Review metadata, output paths, VM stream summaries, and expected vs actual evidence.",
        known_gaps: knownGaps
      };
    })
    .sort((left, right) => (
      Number(left.status === "passed") - Number(right.status === "passed")
      || right.evidence_count - left.evidence_count
      || right.vm_stream_count - left.vm_stream_count
      || left.case_id.localeCompare(right.case_id)
    ))
    .slice(0, 8);
}

function parityAction(area, action, confirmed, note) {
  return {
    area,
    action,
    confirmed: Boolean(confirmed),
    note
  };
}

function caseHasMediaChannel(item = {}, channel = "") {
  const evidence = item.media_evidence || {};
  if (channel === "vm_stream") {
    return (evidence.vm_streams || []).length > 0
      || (evidence.evidence_items || []).some((entry) => canonicalMediaChannel(entry.type) === "vm_stream");
  }
  const evidenceChannels = [
    evidence.primary_media_type,
    ...(evidence.media_types || []),
    ...(evidence.evidence_items || []).map((entry) => entry.type)
  ].map(canonicalMediaChannel);
  return evidenceChannels.includes(channel);
}

function mediaChannelDecision(channel, signals = {}) {
  if (signals.livePreviewAllowed) {
    return "Safe to render live preview from current evidence.";
  }
  if (signals.signedUrlConfirmed) {
    return "Signed URL shape is confirmed, but A3 keeps values redacted and does not render live links.";
  }
  if (signals.signedUrlUnconfirmed) {
    return "Observed as a product channel, but signed URL behavior is still unconfirmed.";
  }
  if (channel === "vm_stream" && signals.caseEvidenceCount > 0) {
    return "Show VM stream summary only.";
  }
  if (signals.outputPathConfirmed || signals.caseEvidenceCount > 0) {
    return "Show output path and evidence metadata only.";
  }
  return "Keep as observed product capability until concrete case evidence exists.";
}

function buildCloudActionGuardrails({
  authOk = false,
  frontendSessionValid = false,
  requestProvenance = {},
  usageQuota = {},
  observedPageCount = 0
} = {}) {
  return [
    cloudAction("Switch local fixture", "Local dashboard", true, "Safe local UI action; no external request is made."),
    cloudAction("Export JSON / CSV / Markdown", "Local report", true, "Safe local export from redacted fixtures."),
    cloudAction("Print / PDF report", "Local report", true, "Safe browser print flow; no upload or public publishing."),
    cloudAction("Observe auth status", "Auth session", authOk || frontendSessionValid, "Read-only status from redacted auth/frontend evidence."),
    cloudAction("View workspace shell", "Workspace / tenant", authOk, "Only redacted workspace existence is shown; account values stay hidden."),
    cloudAction("View request provenance", "Datasets / runs", requestProvenance.available === true, "Read-only request/dataset/run provenance from redacted samples."),
    cloudAction("View usage quota", "Usage / billing", usageQuota.available === true, usageQuota.guidance || "Read-only usage shell."),
    cloudAction("Sign in with OAuth", "Auth session", false, "Do not implement real OAuth/login in A3; manual browser login remains external."),
    cloudAction("Create hosted dataset", "Datasets", false, "Would create or mutate real Ashr cloud data; disabled for MVP."),
    cloudAction("Generate / revoke API key", "API keys", false, "Would expose or mutate secrets; disabled."),
    cloudAction("Invite teammate", "Team", false, "Would change account access; disabled."),
    cloudAction("Upgrade billing plan", "Usage / billing", false, "Would affect payment/plan state; disabled."),
    cloudAction("Publish Trust certificate", "Trust", false, "Would create public-facing hosted output; replaced by local report export."),
    cloudAction("Delete cloud object", "Cloud mutations", false, "Destructive hosted operation; disabled."),
    cloudAction("Deep-link official run detail", "Official frontend", false, "Requires one UI-visible populated hosted run before A3 should copy the detail workflow.")
  ];
}

function cloudAction(action, surface, enabled, reason) {
  return {
    action,
    surface,
    enabled: Boolean(enabled),
    mode: enabled ? "local/read-only" : "disabled",
    reason
  };
}

function canonicalMediaChannel(value = "") {
  const text = String(value).toLowerCase();
  if (text.includes("audio")) {
    return "audio";
  }
  if (text.includes("image")) {
    return "images";
  }
  if (text.includes("video")) {
    return "video";
  }
  if (text.includes("file")) {
    return "files";
  }
  if (text.includes("vm")) {
    return "vm_stream";
  }
  return "";
}

function sortMediaChannels(values = []) {
  const unique = [...new Set(values.filter(Boolean))];
  return unique.sort((left, right) => {
    const leftIndex = MEDIA_CHANNEL_ORDER.indexOf(left);
    const rightIndex = MEDIA_CHANNEL_ORDER.indexOf(right);
    if (leftIndex === -1 && rightIndex === -1) {
      return left.localeCompare(right);
    }
    if (leftIndex === -1) {
      return 1;
    }
    if (rightIndex === -1) {
      return -1;
    }
    return leftIndex - rightIndex;
  });
}

function countObjectValues(value = {}) {
  return Object.values(objectOr(value)).reduce((sum, item) => sum + (Number(item) || 0), 0);
}

function uniqueSorted(values = []) {
  return [...new Set(values.filter(Boolean))].sort();
}

function extractRequestObjects(input = {}) {
  if (Array.isArray(input)) {
    return input.filter(isObject);
  }
  if (input.response && input.response !== input) {
    const responseRequests = extractRequestObjects(input.response);
    if (responseRequests.length) {
      return responseRequests;
    }
  }
  if (Array.isArray(input.requests)) {
    return input.requests.filter(isObject);
  }
  if (Array.isArray(input.list_requests?.requests)) {
    return input.list_requests.requests.filter(isObject);
  }
  if (Array.isArray(input.calls?.list_requests?.sample?.requests)) {
    return input.calls.list_requests.sample.requests.filter(isObject);
  }
  if (isObject(input.sample) && looksLikeRequest(input.sample)) {
    return [input.sample];
  }
  if (isObject(input.calls?.get_request?.sample)) {
    return [input.calls.get_request.sample];
  }
  if (isObject(input.get_request?.sample)) {
    return [input.get_request.sample];
  }
  const generatedDatasetSummary = generatedDatasetSummaryAsRequest(input);
  if (generatedDatasetSummary) {
    return [generatedDatasetSummary];
  }
  return looksLikeRequest(input) ? [input] : [];
}

function generatedDatasetSummaryAsRequest(input = {}) {
  const frontend = objectOr(input.frontend_result);
  if (!frontend.dataset_id_decimal && !frontend.dataset_name) {
    return null;
  }

  const generatedCases = Array.isArray(input.generated_test_cases) ? input.generated_test_cases : [];
  const acceptedInputs = uniqueSorted(generatedCases.flatMap((item) => (
    Array.isArray(item.media_or_input_types) ? item.media_or_input_types : []
  )));

  return {
    id: `dataset-${firstText(frontend.dataset_id_decimal, "unknown")}-generate-test-suite`,
    request_name: firstText(frontend.dataset_name, "Generated dataset"),
    request_status: frontend.dataset_visible ? "dataset_generated" : "unknown",
    created_at: firstText(input.captured_at, frontend.created_date_visible, ""),
    completed_at: firstText(input.captured_at, ""),
    actual_duration_s: null,
    estimated_duration_s: null,
    request: {
      metadata: {
        dataset_name: firstText(frontend.dataset_name, "Generated dataset"),
        source: "frontend_generate_test_suite_summary"
      },
      agent: {
        accepted_inputs: Object.fromEntries(acceptedInputs.map((inputType) => [inputType, true])),
        tools: []
      },
      generation_options: {
        generated_dataset: frontend.dataset_visible === true
      },
      test_config: {
        strategy: "official_generate_test_suite",
        num_variations: generatedCases.length || numberOrNull(frontend.total_tests_visible),
        coverage: {
          media_channels: acceptedInputs
        }
      },
      context: {
        domain: "e-commerce"
      }
    }
  };
}

function looksLikeRequest(value = {}) {
  return isObject(value) && (
    "request_status" in value
    || "request_name" in value
    || "estimated_duration_s" in value
    || "actual_duration_s" in value
    || isObject(value.request)
  );
}

function objectOr(value) {
  return isObject(value) ? value : {};
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function truthyKeys(value = {}) {
  return Object.entries(objectOr(value))
    .filter(([, flag]) => flag === true || isRedactedPlaceholder(flag))
    .map(([key]) => key)
    .sort();
}

function numberOrNull(value) {
  return typeof value === "number" && !Number.isNaN(value) ? value : null;
}

function isRedactedPlaceholder(value) {
  return typeof value === "string" && value.startsWith("[REDACTED");
}

function formatCoverageCaseRefs(refs = []) {
  if (!Array.isArray(refs) || refs.length === 0) {
    return "none";
  }
  return refs
    .map((item) => `${item.case_id || "unknown_case"}/${item.scenario_id || "unknown_scenario"}`)
    .join(", ");
}

function coverageEvidenceLines(coverage = {}) {
  const goldenClasses = Object.keys(coverage.golden_failure_class_cases || {});
  const executableClasses = Object.keys(coverage.executable_failure_class_cases || {});
  return [...new Set([...goldenClasses, ...executableClasses])]
    .sort()
    .map((failureClass) => (
      `- ${failureClass}: golden ${formatCoverageCaseRefs(coverage.golden_failure_class_cases[failureClass])}; `
      + `executable ${formatCoverageCaseRefs(coverage.executable_failure_class_cases[failureClass])}`
    ));
}

export function clusterFailures(runFixture = {}, gradeFixture = {}) {
  const failedCases = normalizeCases(runFixture, gradeFixture)
    .filter((item) => !item.passed && item.primary_failure_class !== "none");
  const clusters = new Map();

  for (const item of failedCases) {
    const key = item.primary_failure_class || "wrong_intent";
    if (!clusters.has(key)) {
      clusters.set(key, {
        failureClass: key,
        count: 0,
        severity: item.severity || "major",
        cases: [],
        summaries: new Set()
      });
    }

    const cluster = clusters.get(key);
    cluster.count += 1;
    cluster.cases.push({
      case_id: item.case_id,
      scenario_id: item.scenario_id,
      title: item.title,
      score: item.score,
      summary: item.failure_summary
    });
    if (item.failure_summary) {
      cluster.summaries.add(item.failure_summary);
    }
  }

  return [...clusters.values()].map((cluster) => ({
    ...cluster,
    summaries: [...cluster.summaries]
  })).sort((left, right) => right.count - left.count || left.failureClass.localeCompare(right.failureClass));
}

export function buildToolCallDiffs(caseResult = {}) {
  const expected = normalizeToolCalls(caseResult.expected?.tool_calls);
  const actual = normalizeToolCalls(caseResult.actual?.tool_calls);
  const pairs = pairToolCalls(expected, actual);

  return pairs.map((pair, index) => {
    const { expectedCall, actualCall, expectedIndex, actualIndex, matchStrategy } = pair;
    const status = toolDiffStatus(expectedCall, actualCall, pair);
    const traceEventLinks = buildTraceEventLinks(caseResult, {
      index,
      expectedIndex,
      actualIndex,
      expectedCall,
      actualCall
    });
    return {
      index,
      expected_index: expectedIndex,
      actual_index: actualIndex,
      match_strategy: matchStrategy,
      order_changed: Number.isInteger(expectedIndex)
        && Number.isInteger(actualIndex)
        && expectedIndex !== actualIndex,
      status,
      expected: expectedCall,
      actual: actualCall,
      summary: toolDiffSummary(status, expectedCall, actualCall),
      argument_diffs: expectedCall && actualCall
        ? buildArgumentDiffs(expectedCall.arguments, actualCall.arguments)
        : [],
      trace_event_links: traceEventLinks,
      judge_evidence: buildToolDiffJudgeEvidence(caseResult, {
        index,
        expectedIndex,
        actualIndex,
        status,
        expectedCall,
        actualCall,
        traceEventLinks
      })
    };
  });
}

function buildTraceEventLinks(caseResult = {}, diff = {}) {
  const events = Array.isArray(caseResult.trace_events) ? caseResult.trace_events : [];
  const toolNames = new Set([diff.expectedCall?.name, diff.actualCall?.name].filter(Boolean));
  const toolIds = new Set([diff.expectedCall?.id, diff.actualCall?.id].filter(Boolean));
  const seen = new Set();

  return events.flatMap((event, eventIndex) => {
    if (!isToolTraceEvent(event)) {
      return [];
    }
    const data = event.observation?.data || event.data || {};
    const names = traceToolNames(event);
    const ids = traceToolIds(event);
    const nameMatches = names.some((name) => toolNames.has(name));
    const idMatches = ids.some((id) => toolIds.has(id));
    if (!nameMatches && !idMatches) {
      return [];
    }

    const eventId = firstText(event.event_id, event.id, `${caseResult.case_id || "case"}:trace:${event.seq ?? eventIndex}`);
    if (seen.has(eventId)) {
      return [];
    }
    seen.add(eventId);
    return [{
      event_id: eventId,
      seq: event.seq ?? eventIndex,
      event_type: event.event_type || event.type || "tool.tool_call",
      phase: event.phase || "tool",
      tool_name: names[0] || data.name || "tool"
    }];
  });
}

function isToolTraceEvent(event = {}) {
  const eventType = String(event.event_type || event.type || "");
  const phase = String(event.phase || "");
  const kind = String(event.observation?.kind || "");
  return eventType.includes("tool")
    || phase === "tool"
    || kind.includes("tool");
}

function traceToolNames(event = {}) {
  const data = event.observation?.data || event.data || {};
  return uniqueValues([
    data.name,
    data.tool_name,
    data.tool,
    data.actual?.tool_name,
    data.actual?.name,
    data.actual?.tool,
    data.expected?.tool_name,
    data.expected?.name,
    data.expected?.tool
  ].filter(Boolean).map(String));
}

function traceToolIds(event = {}) {
  const data = event.observation?.data || event.data || {};
  return uniqueValues([
    data.id,
    data.tool_call_id,
    data.actual?.id,
    data.actual?.tool_call_id,
    data.expected?.id,
    data.expected?.tool_call_id
  ].filter(Boolean).map(String));
}

function uniqueValues(values) {
  return [...new Set(values)];
}

function firstText(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return String(value);
    }
  }
  return "";
}

function buildToolDiffJudgeEvidence(caseResult = {}, diff = {}) {
  const judgeResults = Array.isArray(caseResult.judge_results) ? caseResult.judge_results : [];
  const toolNames = new Set([diff.expectedCall?.name, diff.actualCall?.name].filter(Boolean));
  const toolIds = new Set([diff.expectedCall?.id, diff.actualCall?.id].filter(Boolean));
  const positions = [diff.index, diff.expectedIndex, diff.actualIndex]
    .filter((position) => Number.isInteger(position))
    .map((position) => `#${position + 1}`);

  return judgeResults.flatMap((judge) => {
    const analysis = judge.failure_analysis || {};
    const evidence = judge.evidence || {};
    const failureClasses = Array.isArray(analysis.failure_classes) ? analysis.failure_classes : [];
    const toolCallIds = Array.isArray(evidence.tool_call_ids) ? evidence.tool_call_ids : [];
    const relevantFailure = judge.passed === false && (
      failureMatchesDiff(analysis.primary_failure_class, diff.status)
      || failureClasses.some((failureClass) => failureMatchesDiff(failureClass, diff.status))
      || failureMatchesDiff(analysis.primary_failure_class, caseResult.primary_failure_class)
    );
    const relevantTool = toolCallIds.some((toolCallId) => (
      positions.some((position) => toolCallId === position || toolCallId.endsWith(position))
      || [...toolIds].some((toolId) => toolCallId === toolId)
      || [...toolNames].some((toolName) => toolCallId.includes(toolName))
    ));

    if (!relevantFailure && !relevantTool) {
      return [];
    }

    return [{
      judge_mode: judge.judge_mode || "judge",
      score: judge.score ?? null,
      primary_failure_class: analysis.primary_failure_class || "none",
      severity: analysis.severity || "none",
      summary: analysis.summary || "No judge summary.",
      details: Array.isArray(analysis.details) ? analysis.details : [],
      remediation: Array.isArray(analysis.remediation) ? analysis.remediation : [],
      evidence: {
        tool_call_ids: toolCallIds,
        trace_event_ids: (diff.traceEventLinks || []).map((event) => event.event_id),
        final_response_excerpt: evidence.final_response_excerpt || null
      }
    }];
  });
}

function failureMatchesDiff(failureClass, status) {
  if (!failureClass || !status) {
    return false;
  }
  if (failureClass === status) {
    return true;
  }
  return canonicalPrimaryFailureClass(failureClass, false) === canonicalPrimaryFailureClass(status, false);
}

export function buildArgumentDiffs(expectedArgs = {}, actualArgs = {}) {
  const expectedLeaves = flattenArgumentLeaves(expectedArgs);
  const actualLeaves = flattenArgumentLeaves(actualArgs);
  const paths = [...new Set([...expectedLeaves.keys(), ...actualLeaves.keys()])].sort();

  return paths.flatMap((path) => {
    const hasExpected = expectedLeaves.has(path);
    const hasActual = actualLeaves.has(path);
    const expected = hasExpected ? expectedLeaves.get(path) : null;
    const actual = hasActual ? actualLeaves.get(path) : null;

    if (!hasExpected && hasActual) {
      return [{ path, status: "unexpected_argument", expected, actual }];
    }
    if (hasExpected && !hasActual) {
      return [{ path, status: "missing_argument", expected, actual }];
    }
    if (stableJson(expected) !== stableJson(actual)) {
      return [{ path, status: "changed_argument", expected, actual }];
    }
    return [];
  });
}

export function buildMarkdownReport(runFixture = {}, gradeFixture = {}, coverageFixture = {}, evidenceReadinessFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}, mediaSignedUrlFixture = {}, authFixture = {}, frontendFixture = {}, frontendMirrorFixture = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const evidenceReadiness = summarizeEvidenceReadiness(evidenceReadinessFixture);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const mediaReadiness = summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, mediaSignedUrlFixture);
  const cloudConsoleShell = summarizeCloudConsoleShell(authFixture, frontendFixture, requestFixture, usageFixture, usageApiProbe);
  const officialGap = summarizeOfficialAshrGap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe);
  const officialFrontendMirror = summarizeOfficialFrontendMirror(frontendMirrorFixture);
  const officialParityRoadmap = summarizeOfficialParityRoadmap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe, mediaSignedUrlFixture, frontendMirrorFixture);
  const releaseGate = summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture);
  const releaseWorkflow = summarizeReleaseWorkflow(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture);
  const releaseWarRoom = summarizeReleaseWarRoom(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, requestFixture, usageFixture, usageApiProbe, frontendMirrorFixture);
  const clusters = clusterFailures(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const lines = [
    "# A3 Dashboard Triage Report",
    "",
    `- Runs: ${summary.totalRuns}`,
    `- Cases: ${summary.totalCases}`,
    `- Pass rate: ${summary.passRate}%`,
    `- Average score: ${summary.avgScore}`,
    `- Trace completeness: ${summary.traceCompleteness}%`,
    ""
  ];

  if (releaseGate.available) {
    lines.push(
      "## Release Gate",
      "",
      `- Decision: ${releaseGate.decision_label}`,
      `- Risk score: ${releaseGate.risk_score}`,
      `- Failed checks: ${releaseGate.failed_check_count}`,
      `- Required approvers: ${releaseGate.required_approvers.join(", ") || "none"}`,
      `- PR gate: ${releaseGate.pr_gate.blocks_merge ? "blocks merge" : releaseGate.pr_gate.warning_only ? "warning only" : "pass"}`,
      `- Commercial value: ${releaseGate.commercial_value}`,
      ""
    );
    for (const check of releaseGate.checks) {
      lines.push(`- ${check.id}: ${check.passed ? "pass" : "fail"} - ${check.observed}. ${check.detail}`);
    }
    lines.push("");
  }

  if (releaseWorkflow.available) {
    lines.push(
      "## PR Gate / Review Workflow",
      "",
      `- GitHub check: ${releaseWorkflow.github_check.name}`,
      `- Check conclusion: ${releaseWorkflow.github_check.conclusion}`,
      `- Waiver required: ${releaseWorkflow.waiver_policy.required ? "yes" : "no"}`,
      `- Waiver allowed: ${releaseWorkflow.waiver_policy.allowed ? "yes" : "no"}`,
      `- Review state: ${releaseWorkflow.reviewer_workflow.state}`,
      `- Review lanes: ${releaseWorkflow.reviewer_workflow.review_lanes.join(", ") || "none"}`,
      `- Audit bundle artifacts: ${releaseWorkflow.audit_bundle.artifacts.map((item) => item.id).join(", ")}`,
      `- Incident replay cases: ${releaseWorkflow.incident_replay.case_ids.join(", ") || "none"}`,
      `- Commercial value: ${releaseWorkflow.commercial_value}`,
      ""
    );
    lines.push("### PR Comment Template", "", releaseWorkflow.pr_comment_markdown.trim(), "");
  }

  if (releaseWarRoom.available) {
    lines.push(
      "## Release War Room",
      "",
      `- Decision: ${releaseWarRoom.decision_label}`,
      `- Urgency: ${releaseWarRoom.urgency}`,
      `- Revenue risk score: ${releaseWarRoom.revenue_risk_score}`,
      `- Blocks merge: ${releaseWarRoom.blocks_merge ? "yes" : "no"}`,
      `- Waiver required: ${releaseWarRoom.waiver_required ? "yes" : "no"}`,
      `- Incident replay cases: ${releaseWarRoom.incident_replay_case_count}`,
      `- Required audit artifacts: ${releaseWarRoom.required_artifact_count}`,
      `- Customer value: ${releaseWarRoom.customer_value}`,
      ""
    );
    lines.push("### Executive Brief", "", ...releaseWarRoom.executive_brief.map((item) => `- ${item}`), "");
    lines.push("### War Room Lanes", "");
    for (const lane of releaseWarRoom.lanes) {
      lines.push(`- ${lane.lane}: ${lane.status} / ${lane.owner} - ${lane.next_action}`);
    }
    lines.push("");
  }

  if (coverage.available) {
    const evidenceLines = coverageEvidenceLines(coverage);
    lines.push(
      "## Coverage",
      "",
      `- Assignment minimums met: ${coverage.meets_assignment_minimums ? "yes" : "no"}`,
      `- Scenarios: ${coverage.scenario_count}`,
      `- Scenario dimensions met: ${Object.values(coverage.scenario_dimension_checks).filter(Boolean).length}/${Object.keys(coverage.scenario_dimension_checks).length}`,
      `- Scenario quality warnings: ${coverage.scenario_quality_warning_count}`,
      `- Rubric classes: ${coverage.rubric_class_count}`,
      `- Judge modes: ${coverage.judge_mode_count}`,
      `- Golden cases: ${coverage.golden_case_count}`,
      `- Executable run cases: ${coverage.executable_run_case_count}`,
      `- Media executable cases: ${coverage.executable_media_case_count}`,
      `- Tool-output grounding executable cases: ${coverage.executable_tool_output_grounding_case_count}`,
      `- Missing executable failure classes: ${coverage.executable_failure_classes_missing.join(", ") || "none"}`,
      `- Coverage warnings: ${coverage.coverage_warning_count}`,
      ""
    );
    if (coverage.scenario_quality_warnings.length > 0) {
      lines.push(
        "### Scenario Quality Warnings",
        "",
        ...coverage.scenario_quality_warnings.map((warning) => `- ${warning}`),
        ""
      );
    }
    if (evidenceLines.length > 0) {
      lines.push(
        "### Failure Class Evidence",
        "",
        ...evidenceLines,
        ""
      );
    }
  }

  if (evidenceReadiness.available) {
    lines.push(
      "## Evidence Readiness",
      "",
      `- Status: ${evidenceReadiness.status}`,
      `- Ready for external collection: ${evidenceReadiness.ready_for_external_collection ? "yes" : "no"}`,
      `- Calibration cases: ${evidenceReadiness.calibration_case_count}`,
      `- Ashr grading missing: ${evidenceReadiness.ashr_current_missing}/${evidenceReadiness.ashr_expected_observation_count}`,
      `- Semantic judge offline-only: ${evidenceReadiness.semantic_offline_reference_only ? "yes" : "no"}`,
      `- SDK languages covered: ${evidenceReadiness.covered_sdk_languages.join(", ") || "none"}`,
      `- Private evidence path: ${evidenceReadiness.private_raw_path || "none"}`,
      ""
    );
  }

  if (requestProvenance.available) {
    const latest = requestProvenance.latest_request;
    lines.push(
      "## Request Provenance",
      "",
      `- Requests observed: ${requestProvenance.total_requests}`,
      `- Latest request: ${latest.request_name}`,
      `- Status: ${latest.request_status}`,
      `- Duration: ${latest.actual_duration_s ?? "unknown"}s actual / ${latest.estimated_duration_s ?? "unknown"}s estimated`,
      `- Accepted inputs: ${latest.accepted_input_types.join(", ") || "none"}`,
      `- Generation outputs: ${latest.generation_outputs.join(", ") || "none"}`,
      `- Tools declared: ${latest.tool_count}`,
      ""
    );
  }

  if (usageQuota.available) {
    lines.push(
      "## Usage / Quota",
      "",
      `- Frontend modules: ${usageQuota.frontend_modules.join(", ") || "none"}`,
      `- Media channels: ${usageQuota.channels.join(", ") || "unknown"}`,
      `- Frontend source functions: ${usageQuota.frontend_source_functions.join(", ") || "unknown"}`,
      `- Direct API-key access: ${usageQuota.direct_api_accessible ? "yes" : "no"}`,
      `- OAuth-gated functions: ${usageQuota.oauth_only_functions.join(", ") || "none"}`,
      `- Guidance: ${usageQuota.guidance}`,
      ""
    );
  }

  if (mediaReadiness.available) {
    lines.push(
      "## Media Readiness",
      "",
      `- Media cases: ${mediaReadiness.media_case_count}`,
      `- Evidence items: ${mediaReadiness.evidence_item_count}`,
      `- VM streams: ${mediaReadiness.vm_stream_count}`,
      `- Channels: ${mediaReadiness.channels.join(", ") || "unknown"}`,
      `- Signed URL keys: ${mediaReadiness.signed_url_key_count}`,
      `- Signed URL confirmed types: ${mediaReadiness.signed_url_confirmed_types.join(", ") || "none"}`,
      `- Live rendering allowed: ${mediaReadiness.live_rendering_allowed ? "yes" : "no"}`,
      `- Guidance: ${mediaReadiness.guidance}`,
      ""
    );
    for (const channel of mediaReadiness.channel_matrix) {
      lines.push(`- ${channel.channel}: ${channel.preview_policy} - ${channel.decision}`);
    }
    lines.push("");
  }

  if (cloudConsoleShell.available) {
    lines.push(
      "## Cloud Console Shell",
      "",
      `- Auth observed: ${cloudConsoleShell.auth_observed ? "yes" : "no"}`,
      `- Frontend session observed: ${cloudConsoleShell.frontend_session_observed ? "yes" : "no"}`,
      `- Observed pages: ${cloudConsoleShell.observed_pages.join(", ") || "none"}`,
      `- Real mutations enabled: ${cloudConsoleShell.real_mutations_enabled ? "yes" : "no"}`,
      `- Secret values allowed: ${cloudConsoleShell.secret_values_allowed ? "yes" : "no"}`,
      `- Recommendation: ${cloudConsoleShell.recommendation}`,
      ""
    );
    for (const section of cloudConsoleShell.sections) {
      lines.push(`- ${section.area}: ${section.status} - ${section.detail}`);
    }
    lines.push("", "### Cloud Action Guardrails", "");
    for (const action of cloudConsoleShell.actions) {
      lines.push(`- ${action.action}: ${action.mode} - ${action.reason}`);
    }
    lines.push("");
  }

  lines.push(
    "## Official Ashr Gap",
    "",
    `- Copied areas: ${officialGap.copied_count}`,
    `- Partial areas: ${officialGap.partial_count}`,
    `- Blocked areas: ${officialGap.blocked_count}`,
    `- Out-of-scope areas: ${officialGap.out_of_scope_count}`,
    `- Recommendation: ${officialGap.recommendation}`,
    ""
  );
  for (const page of officialGap.official_pages) {
    lines.push(`- ${page.page} (${page.path}): ${page.a3_status} - ${page.mvp_decision}`);
  }
  lines.push("");

  if (officialFrontendMirror.available) {
    lines.push(
      "## Official Frontend Mirror",
      "",
      `- Source archive: ${officialFrontendMirror.source_archive}`,
      `- Clean-room boundary: ${officialFrontendMirror.clean_room_boundary}`,
      `- Pages observed: ${officialFrontendMirror.page_count}`,
      `- Lab chunks observed: ${officialFrontendMirror.lab_chunk_count}`,
      `- API method groups observed: ${officialFrontendMirror.api_group_count}`,
      `- API methods observed: ${officialFrontendMirror.api_method_count}`,
      `- Labels confirmed: ${officialFrontendMirror.confirmed_labels.join(", ") || "none"}`,
      `- Official source committed: ${officialFrontendMirror.safety.official_source_committed ? "yes" : "no"}`,
      `- Secrets/tokens/cookies allowed: ${officialFrontendMirror.safety.secret_values_allowed || officialFrontendMirror.safety.raw_tokens_allowed || officialFrontendMirror.safety.raw_cookies_allowed ? "yes" : "no"}`,
      `- Recommendation: ${officialFrontendMirror.recommendation}`,
      ""
    );
    for (const page of officialFrontendMirror.pages) {
      lines.push(`- Page ${page.label} (${page.tab_id}): ${page.a3_status} - ${page.a3_decision}`);
    }
    lines.push("");
    for (const group of officialFrontendMirror.api_method_groups) {
      lines.push(`- API ${group.group}: ${group.a3_status}, ${group.method_count} method(s) - ${group.a3_decision}`);
    }
    lines.push("");
  }

  if (officialParityRoadmap.available) {
    lines.push(
      "## Official Parity Roadmap",
      "",
      `- Official pages observed: ${officialParityRoadmap.official_pages_observed}`,
      `- Copied pages: ${officialParityRoadmap.copied_page_count}`,
      `- Partial pages: ${officialParityRoadmap.partial_page_count}`,
      `- Future pages: ${officialParityRoadmap.future_page_count}`,
      `- Out-of-scope pages: ${officialParityRoadmap.out_of_scope_page_count}`,
      `- Official blocked gaps: ${officialParityRoadmap.official_gap_blocked_count}`,
      `- Recommendation: ${officialParityRoadmap.recommendation}`,
      ""
    );
    lines.push("### Build Priorities", "");
    for (const item of officialParityRoadmap.priorities) {
      lines.push(`- ${item.area}: ${item.action} / ${item.confirmed ? "confirmed" : "unconfirmed"} - ${item.note}`);
    }
    lines.push("", "### Media Actions", "");
    for (const item of officialParityRoadmap.media_actions) {
      lines.push(`- ${item.area}: ${item.action} - ${item.note}`);
    }
    lines.push("", "### Cloud/Admin Boundaries", "");
    for (const boundary of officialParityRoadmap.cloud_admin_boundaries) {
      lines.push(`- ${boundary}`);
    }
    lines.push("", "### Next Build Order", "");
    for (const step of officialParityRoadmap.next_build_order) {
      lines.push(`- ${step}`);
    }
    lines.push("");
  }

  lines.push(
    "## Failure Clusters",
    ""
  );

  if (clusters.length === 0) {
    lines.push("- No failures.");
  } else {
    for (const cluster of clusters) {
      lines.push(`- ${cluster.failureClass}: ${cluster.count} case(s), severity ${cluster.severity}`);
    }
  }

  lines.push("", "## Cases", "");
  for (const item of cases) {
    lines.push(`- ${item.case_id} / ${item.scenario_id}: ${item.passed ? "PASS" : "FAIL"} (${item.score}) - ${item.failure_summary}`);
  }

  return `${lines.join("\n")}\n`;
}

export function buildCsvReport(runFixture = {}, gradeFixture = {}) {
  const header = [
    "run_id",
    "case_id",
    "scenario_id",
    "title",
    "status",
    "score",
    "severity",
    "primary_failure_class",
    "failure_summary",
    "media_types",
    "media_evidence_count",
    "vm_stream_count"
  ];
  const rows = normalizeCases(runFixture, gradeFixture).map((item) => [
    item.run_id,
    item.case_id,
    item.scenario_id,
    item.title,
    item.passed ? "passed" : "failed",
    item.score,
    item.severity,
    item.primary_failure_class,
    item.failure_summary,
    (item.media_evidence?.media_types || []).join("|"),
    item.media_evidence?.evidence_items?.length || 0,
    item.media_evidence?.vm_streams?.length || 0
  ]);
  return [header, ...rows]
    .map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))
    .join("\n");
}

export function buildJsonReport(runFixture = {}, gradeFixture = {}, coverageFixture = {}, evidenceReadinessFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}, mediaSignedUrlFixture = {}, authFixture = {}, frontendFixture = {}, frontendMirrorFixture = {}) {
  return {
    schema_version: "a3.export_report.v1",
    summary: buildDashboardSummary(runFixture, gradeFixture),
    coverage: summarizeCoverage(coverageFixture),
    evidence_readiness: summarizeEvidenceReadiness(evidenceReadinessFixture),
    request_provenance: summarizeRequestProvenance(requestFixture),
    usage_quota: summarizeUsageQuota(usageFixture, usageApiProbe),
    media_readiness: summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, mediaSignedUrlFixture),
    cloud_console_shell: summarizeCloudConsoleShell(authFixture, frontendFixture, requestFixture, usageFixture, usageApiProbe),
    official_ashr_gap: summarizeOfficialAshrGap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe),
    official_frontend_mirror: summarizeOfficialFrontendMirror(frontendMirrorFixture),
    official_parity_roadmap: summarizeOfficialParityRoadmap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe, mediaSignedUrlFixture, frontendMirrorFixture),
    release_gate: summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture),
    release_workflow: summarizeReleaseWorkflow(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture),
    release_war_room: summarizeReleaseWarRoom(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, requestFixture, usageFixture, usageApiProbe, frontendMirrorFixture),
    failure_clusters: clusterFailures(runFixture, gradeFixture),
    cases: normalizeCases(runFixture, gradeFixture).map((item) => ({
      run_id: item.run_id,
      case_id: item.case_id,
      scenario_id: item.scenario_id,
      title: item.title,
      status: item.passed ? "passed" : "failed",
      score: item.score,
      score_source: item.metadata?.score_source || item.grade?.metadata?.score_source || "unknown",
      severity: item.severity,
      score_band: item.score_band,
      judge_modes: item.judge_modes,
      primary_failure_class: item.primary_failure_class,
      failure_summary: item.failure_summary,
      expected: item.expected,
      actual: item.actual,
      tool_call_diffs: buildToolCallDiffs(item),
      media_evidence: item.media_evidence || null
    }))
  };
}

function hasMediaEvidence(item = {}) {
  const mediaEvidence = item.media_evidence || {};
  return (mediaEvidence.media_types || []).length > 0
    || (mediaEvidence.evidence_items || []).length > 0
    || (mediaEvidence.vm_streams || []).length > 0;
}

function normalizeToolCalls(toolCalls) {
  if (!Array.isArray(toolCalls)) {
    return [];
  }

  return toolCalls.map((call, index) => ({
    id: call.id || call.tool_call_id || null,
    name: call.tool_name || call.name || call.tool || "unknown_tool",
    arguments: call.arguments || call.args || call.parameters || {},
    original_index: index,
    raw: call
  }));
}

function pairToolCalls(expected = [], actual = []) {
  const usedActual = new Set();
  const pairs = expected.map((expectedCall, expectedIndex) => {
    const match = selectBestActualMatch(expectedCall, expectedIndex, actual, usedActual);
    if (!match) {
      return {
        expectedCall,
        actualCall: null,
        expectedIndex,
        actualIndex: null,
        matchStrategy: "unmatched_expected"
      };
    }

    usedActual.add(match.actualIndex);
    return {
      expectedCall,
      actualCall: actual[match.actualIndex],
      expectedIndex,
      actualIndex: match.actualIndex,
      matchStrategy: match.matchStrategy
    };
  });

  for (let actualIndex = 0; actualIndex < actual.length; actualIndex += 1) {
    if (!usedActual.has(actualIndex)) {
      pairs.push({
        expectedCall: null,
        actualCall: actual[actualIndex],
        expectedIndex: null,
        actualIndex,
        matchStrategy: "unmatched_actual"
      });
    }
  }

  return pairs;
}

function selectBestActualMatch(expectedCall, expectedIndex, actual = [], usedActual = new Set()) {
  const candidates = actual.flatMap((actualCall, actualIndex) => {
    if (usedActual.has(actualIndex)) {
      return [];
    }
    const score = toolMatchScore(expectedCall, actualCall, expectedIndex, actualIndex);
    if (score <= 0) {
      return [];
    }
    return [{
      actualIndex,
      score,
      matchStrategy: toolMatchStrategy(expectedCall, actualCall, expectedIndex, actualIndex),
      distance: Math.abs(expectedIndex - actualIndex)
    }];
  });

  candidates.sort((left, right) => (
    right.score - left.score
    || left.distance - right.distance
    || left.actualIndex - right.actualIndex
  ));
  return candidates[0] || null;
}

function toolMatchScore(expectedCall, actualCall, expectedIndex, actualIndex) {
  const sameName = expectedCall.name === actualCall.name;
  const sameArguments = stableJson(expectedCall.arguments) === stableJson(actualCall.arguments);
  if (sameName && sameArguments) {
    return 100;
  }
  if (sameName) {
    return 80 - Math.min(buildArgumentDiffs(expectedCall.arguments, actualCall.arguments).length, 20);
  }
  if (expectedIndex === actualIndex) {
    return 40;
  }
  return 0;
}

function toolMatchStrategy(expectedCall, actualCall, expectedIndex, actualIndex) {
  const sameName = expectedCall.name === actualCall.name;
  const sameArguments = stableJson(expectedCall.arguments) === stableJson(actualCall.arguments);
  if (sameName && sameArguments && expectedIndex === actualIndex) {
    return "index_exact";
  }
  if (sameName && sameArguments) {
    return "semantic_exact_reordered";
  }
  if (sameName && expectedIndex === actualIndex) {
    return "index_name";
  }
  if (sameName) {
    return "semantic_name";
  }
  return "index";
}

function toolDiffStatus(expectedCall, actualCall, pair = {}) {
  if (expectedCall && !actualCall) {
    return "missing_required_tool";
  }
  if (!expectedCall && actualCall) {
    return "unexpected_tool_call";
  }
  if (!expectedCall && !actualCall) {
    return "none";
  }
  if (expectedCall.name !== actualCall.name) {
    return "wrong_tool";
  }
  if (stableJson(expectedCall.arguments) !== stableJson(actualCall.arguments)) {
    return "wrong_arguments";
  }
  if (Number.isInteger(pair.expectedIndex) && Number.isInteger(pair.actualIndex) && pair.expectedIndex !== pair.actualIndex) {
    return "wrong_tool_order";
  }
  return "match";
}

function toolDiffSummary(status, expectedCall, actualCall) {
  if (status === "match") {
    return `Matched ${expectedCall.name}.`;
  }
  if (status === "missing_required_tool") {
    return `Expected ${expectedCall.name}, but no actual tool call was present at this position.`;
  }
  if (status === "unexpected_tool_call") {
    return `Unexpected actual tool call ${actualCall.name}.`;
  }
  if (status === "wrong_tool") {
    return `Expected ${expectedCall.name}, but actual tool was ${actualCall.name}.`;
  }
  if (status === "wrong_arguments") {
    return `Tool ${expectedCall.name} was called with different arguments.`;
  }
  if (status === "wrong_tool_order") {
    return `Tool ${expectedCall.name} matched, but appeared in a different order.`;
  }
  return "No tool call expected or observed.";
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function flattenArgumentLeaves(value, prefix = "") {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return new Map();
    }
    return value.reduce((leaves, item, index) => (
      mergeMaps(leaves, flattenArgumentLeaves(item, `${prefix}[${index}]`))
    ), new Map());
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return new Map();
    }
    return entries.reduce((leaves, [key, item]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return mergeMaps(leaves, flattenArgumentLeaves(item, path));
    }, new Map());
  }

  return new Map([[prefix || "(root)", value]]);
}

function mergeMaps(left, right) {
  for (const [key, value] of right) {
    left.set(key, value);
  }
  return left;
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
