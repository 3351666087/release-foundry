export function isA3ApiSource(source) {
  return String(source || "").startsWith("api-");
}

export function apiSourceTarget(source) {
  return isA3ApiSource(source) ? String(source).replace(/^api-/, "") : source;
}

export async function fetchA3DashboardSnapshot(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/dashboard?source=${encodeURIComponent(source)}`);
  if (!response.ok) {
    throw new Error(`A3 API dashboard load failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchA3AdminConsole(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/admin/console?source=${encodeURIComponent(source)}`);
  if (!response.ok) {
    throw new Error(`A3 API admin console load failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchA3EnterpriseReadiness(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/enterprise/readiness?source=${encodeURIComponent(source)}`);
  if (!response.ok) {
    throw new Error(`A3 API enterprise readiness load failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchA3ReportCenter(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/reports/center?source=${encodeURIComponent(source)}`);
  if (!response.ok) {
    throw new Error(`A3 API report center load failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchA3ProductConsole(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/product/console?source=${encodeURIComponent(source)}`);
  if (!response.ok) {
    throw new Error(`A3 API product console load failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchA3ArtifactRegistry(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/artifacts/registry?source=${encodeURIComponent(source)}`);
  if (!response.ok) {
    throw new Error(`A3 API artifact registry load failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchA3ReviewWorkflow(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/review/workflow?source=${encodeURIComponent(source)}`);
  if (!response.ok) {
    throw new Error(`A3 API review workflow load failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchA3SchemaDriftRadar(options = {}) {
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/a1-a2/schema-drift`, {
    headers: {
      "x-a3-role": options.role || "auditor"
    }
  });
  if (!response.ok) {
    throw new Error(`A3 API schema drift radar load failed: ${response.status}`);
  }
  return response.json();
}

export async function planA3AdminAction(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/admin/actions/plan?source=${encodeURIComponent(source)}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-a3-role": options.role || "owner"
    },
    body: JSON.stringify({
      source,
      action: options.action
    })
  });
  if (!response.ok) {
    throw new Error(`A3 API admin action plan failed: ${response.status}`);
  }
  return response.json();
}

export async function createShareableA3Report(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/reports/share?source=${encodeURIComponent(source)}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-a3-role": options.role || "reviewer"
    },
    body: JSON.stringify({
      source,
      title: options.title || "A3 Release Intelligence Report",
      visibility: options.visibility || "private_link",
      created_by: options.createdBy || "a3-dashboard"
    })
  });
  if (!response.ok) {
    throw new Error(`A3 API share report failed: ${response.status}`);
  }
  return response.json();
}

export async function submitA3AdminAction(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/admin/actions/submit?source=${encodeURIComponent(source)}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-a3-role": options.role || "owner"
    },
    body: JSON.stringify({
      source,
      action: options.action,
      reason: options.reason || "dashboard_admin_request",
      actor_hash: options.actorHash || "dashboard_[REDACTED_HASH]",
      target: options.target || {}
    })
  });
  if (!response.ok) {
    throw new Error(`A3 API admin action submit failed: ${response.status}`);
  }
  return response.json();
}

export async function revokeShareableA3Report(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const reportId = options.reportId;
  if (!reportId) {
    throw new Error("A3 API revoke report requires reportId");
  }
  const response = await fetch(`${baseUrl}/api/a3/reports/${encodeURIComponent(reportId)}/revoke?source=${encodeURIComponent(source)}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-a3-role": options.role || "owner"
    },
    body: JSON.stringify({
      reason: options.reason || "dashboard_revoke",
      revoked_by: options.revokedBy || "a3-dashboard"
    })
  });
  if (!response.ok) {
    throw new Error(`A3 API revoke report failed: ${response.status}`);
  }
  return response.json();
}

function normalizeBaseUrl(baseUrl) {
  const value = baseUrl || "";
  return value.endsWith("/") ? value.slice(0, -1) : value;
}
