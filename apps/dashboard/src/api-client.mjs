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

export async function createShareableA3Report(options = {}) {
  const source = apiSourceTarget(options.source || "mock");
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const response = await fetch(`${baseUrl}/api/a3/reports/share?source=${encodeURIComponent(source)}`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
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

function normalizeBaseUrl(baseUrl) {
  const value = baseUrl || "";
  return value.endsWith("/") ? value.slice(0, -1) : value;
}
