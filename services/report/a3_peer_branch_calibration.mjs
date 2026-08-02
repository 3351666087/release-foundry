export const A3_PEER_BRANCH_CALIBRATION_SCHEMA_VERSION = "a3.peer_branch_calibration.v1";

const SECRET_PATTERNS = [
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/,
  /\bghp_[A-Za-z0-9]{20,}\b/,
  /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i,
  /Cookie:\s*(?!\[REDACTED\])/i,
  /RELEASEFOUNDRY_API_KEY\s*=\s*(?!\[REDACTED\])/i,
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /C:\\Users\\/i
];

export function summarizeA3PeerBranchCalibration(fixture = {}) {
  const deltas = normalizeDeltas(fixture.peer_deltas || fixture.top_deltas || fixture.deltas || []);
  const growthPoints = normalizeGrowthPoints(fixture.growth_points || []);
  const branchCounts = countBy(deltas, "source_branch");
  const laneCounts = countBy(deltas, "owner_lane");
  const surfaceCounts = countBy(deltas, "a3_surface");
  const riskCounts = countBy(deltas, "risk_level");
  const blockingDeltas = deltas.filter((item) => item.a3_blocker === true || item.risk_level === "high");
  const readyDeltas = deltas.filter((item) => item.a3_status === "ready_to_consume");
  const actionItems = normalizeActionItems(fixture.action_items || buildActionItems(deltas, growthPoints));
  const leaks = findPeerBranchCalibrationLeaks(fixture);
  const peerDeltaCount = numberOr(fixture.peer_delta_count, deltas.length);
  const growthPointCount = numberOr(fixture.growth_point_count, growthPoints.length);
  const blockingDeltaCount = numberOr(fixture.blocking_delta_count, blockingDeltas.length);
  const readyDeltaCount = numberOr(fixture.ready_delta_count, readyDeltas.length);
  const peerBranchCount = numberOr(
    fixture.peer_branch_count,
    Object.keys(fixture.branch_counts || branchCounts).length
  );

  return {
    schema_version: A3_PEER_BRANCH_CALIBRATION_SCHEMA_VERSION,
    available: Boolean(fixture.available) || peerDeltaCount > 0 || growthPointCount > 0,
    source: fixture.source || "peer_remote_branches",
    observed_at: fixture.observed_at || null,
    status: fixture.status && !leaks.length
      ? fixture.status
      : leaks.length
      ? "unsafe"
      : blockingDeltaCount
        ? "needs_a3_action"
        : readyDeltaCount
          ? "ready_to_consume"
          : "watching",
    peer_branch_count: peerBranchCount,
    peer_delta_count: peerDeltaCount,
    growth_point_count: growthPointCount,
    ready_delta_count: readyDeltaCount,
    blocking_delta_count: blockingDeltaCount,
    branch_counts: fixture.branch_counts || branchCounts,
    owner_lane_counts: fixture.owner_lane_counts || laneCounts,
    surface_counts: fixture.surface_counts || surfaceCounts,
    risk_counts: fixture.risk_counts || riskCounts,
    top_deltas: deltas.slice(0, 8),
    action_items: actionItems,
    growth_points: growthPoints.slice(0, 20),
    safety: {
      contains_secret_values: leaks.length > 0,
      raw_tokens_allowed: false,
      raw_cookies_allowed: false,
      raw_emails_allowed: false,
      raw_signed_urls_allowed: false,
      leak_count: leaks.length
    },
    a1_a2_boundary: fixture.a1_a2_boundary || "A3 reads peer-branch contracts as downstream calibration evidence only; it does not modify A1 runtime/auth/billing semantics or A2 judge/release-policy semantics.",
    commercial_value: fixture.commercial_value || "Keeps A3 ahead of A1/A2 PR drift so enterprise release gates, billing readiness, audit exports, and security review screens do not break when peer branches merge.",
    recommendation: actionItems[0]?.action || "Keep watching A1/A2 peer branches and convert every new contract into A3 UI/report/API evidence before merge."
  };
}

export function validateA3PeerBranchCalibration(fixture = {}) {
  const errors = [];
  const summary = summarizeA3PeerBranchCalibration(fixture);
  if (fixture.schema_version && fixture.schema_version !== A3_PEER_BRANCH_CALIBRATION_SCHEMA_VERSION) {
    errors.push("schema_version must be a3.peer_branch_calibration.v1");
  }
  if (!summary.available) {
    errors.push("peer branch calibration must include peer_deltas or growth_points");
  }
  for (const delta of summary.top_deltas) {
    for (const field of ["delta_id", "source_branch", "source_file", "owner_lane", "a3_surface", "contract"]) {
      if (!delta[field]) {
        errors.push(`${delta.delta_id || "delta"} missing ${field}`);
      }
    }
  }
  for (const leak of findPeerBranchCalibrationLeaks(fixture)) {
    errors.push(`potential secret leak: ${leak.pattern}`);
  }
  return { valid: errors.length === 0, errors };
}

export function findPeerBranchCalibrationLeaks(value) {
  const serialized = JSON.stringify(value || {});
  return SECRET_PATTERNS
    .filter((pattern) => pattern.test(serialized))
    .map((pattern) => ({ pattern: pattern.source }));
}

function normalizeDeltas(deltas = []) {
  return (Array.isArray(deltas) ? deltas : [])
    .map((item, index) => ({
      delta_id: item.delta_id || `peer-delta-${index + 1}`,
      source_branch: item.source_branch || "unknown",
      source_file: item.source_file || "unknown",
      owner_lane: item.owner_lane || "A1/A2",
      a3_surface: item.a3_surface || "product_console",
      contract: item.contract || item.field || "unknown_contract",
      risk_level: normalizeRisk(item.risk_level),
      a3_status: item.a3_status || "watch",
      a3_blocker: item.a3_blocker === true,
      dashboard_impact: item.dashboard_impact || "Add read-only visibility before claiming commercial readiness.",
      report_impact: item.report_impact || "Include redacted summary in A3 report exports.",
      api_contract_impact: item.api_contract_impact || "Declare API surface before hosted SaaS rollout.",
      db_event_artifact_impact: item.db_event_artifact_impact || "Track DB/event/artifact refs without raw private payloads.",
      suggested_fixture_field: item.suggested_fixture_field || item.contract || `peer_delta_${index + 1}`,
      next_action: item.next_action || "Map into dashboard, report, tests, and acceptance evidence."
    }));
}

function normalizeGrowthPoints(points = []) {
  return (Array.isArray(points) ? points : [])
    .map((item, index) => ({
      id: item.id || `PBC-${String(index + 1).padStart(2, "0")}`,
      title: item.title || "Unnamed growth point",
      owner_lane: item.owner_lane || "A3",
      surface: item.surface || "product_console",
      expected_artifact: item.expected_artifact || "dashboard/report/test evidence",
      money_grade_reason: item.money_grade_reason || "Moves A3 closer to paid release intelligence.",
      parallelizable: item.parallelizable !== false
    }));
}

function buildActionItems(deltas, growthPoints) {
  const blockerActions = deltas
    .filter((item) => item.a3_blocker || item.risk_level === "high")
    .map((item) => ({
      action_id: `act-${item.delta_id}`,
      priority: "P0",
      lane: item.owner_lane,
      surface: item.a3_surface,
      action: item.next_action,
      evidence_ref: item.source_file
    }));
  const growthActions = growthPoints
    .filter((item) => item.parallelizable)
    .slice(0, Math.max(0, 8 - blockerActions.length))
    .map((item) => ({
      action_id: `act-${item.id}`,
      priority: "P1",
      lane: item.owner_lane,
      surface: item.surface,
      action: item.title,
      evidence_ref: item.expected_artifact
    }));
  return [...blockerActions, ...growthActions].slice(0, 8);
}

function normalizeActionItems(items = []) {
  return (Array.isArray(items) ? items : [])
    .map((item, index) => ({
      action_id: item.action_id || `act-peer-${index + 1}`,
      priority: item.priority || "P1",
      lane: item.lane || item.owner_lane || "A3",
      surface: item.surface || item.a3_surface || "product_console",
      action: item.action || item.next_action || item.title || "Review peer branch delta.",
      evidence_ref: item.evidence_ref || item.source_file || item.expected_artifact || "peer branch fixture"
    }))
    .slice(0, 8);
}

function normalizeRisk(value) {
  return ["high", "medium", "low"].includes(value) ? value : "medium";
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function countBy(items, field) {
  const counts = {};
  for (const item of items) {
    const value = item[field] || "unknown";
    counts[value] = (counts[value] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}
