const READ_PATHS = [
  /^\/api\/a3\/health$/,
  /^\/api\/a3\/dashboard(?:\?source=[a-z0-9-]+)?$/,
  /^\/api\/a3\/releases\/[^/?#]+\/evidence-summary(?:\?version=2)?$/,
  /^\/api\/a3\/releases\/[^/?#]+\/evidence-health$/,
  /^\/api\/a3\/releases\/[^/?#]+\/readbacks$/,
  /^\/api\/a3\/review\/workflow(?:\?releaseId=[^&#]+)?$/,
  /^\/api\/a3\/reports\/center$/
];
const WRITE_PATHS = [/^\/api\/a3\/ui-actions\/preflight$/];
const FORBIDDEN_KEY = /^(?:token|cookie|authorization|api[_-]?key|raw[_-]?key|password|secret|signed[_-]?url)$/i;
const FORBIDDEN_VALUE = [
  /Bearer\s+[A-Za-z0-9._~+/=-]+/i,
  /(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+/i,
  /\bsk-[A-Za-z0-9_-]{12,}\b/i,
  /postgres(?:ql)?:\/\/[^\s]+/i
];

class ReleaseCenterApiError extends Error {
  constructor(code, status = 0) {
    super(code);
    this.name = "ReleaseCenterApiError";
    this.code = code;
    this.status = status;
  }
}

function normalizeApiBaseUrl(value) {
  const candidate = String(value || "").trim().replace(/\/+$/, "");
  if (!candidate || candidate.includes("@") || /[?#\\\s]/.test(candidate)) return "";
  const match = candidate.match(/^https:\/\/([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?::([0-9]{2,5}))?(\/[a-z0-9._~!$&'()*+,;=:@%/-]*)?$/i);
  if (!match || match[1].includes("..")) return "";
  const port = Number(match[2] || 443);
  if (!Number.isInteger(port) || port < 1 || port > 65535) return "";
  return candidate;
}

function buildRequestDescriptor(baseUrl, path, options = {}) {
  const normalizedBaseUrl = normalizeApiBaseUrl(baseUrl);
  const method = String(options.method || "GET").toUpperCase();
  if (!normalizedBaseUrl) throw new ReleaseCenterApiError("api_base_unavailable");
  if (!isAllowedPath(path, method)) throw new ReleaseCenterApiError("api_route_not_allowed");
  if (containsSensitiveMaterial(options.data || {})) throw new ReleaseCenterApiError("request_contains_sensitive_material");
  return {
    url: `${normalizedBaseUrl}${path}`,
    method,
    timeout: 10000,
    data: options.data,
    header: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Client-Surface": "release-center-miniprogram"
    }
  };
}

function requestJson(path, options = {}) {
  const config = options.config || runtimeConfig();
  const descriptor = buildRequestDescriptor(config.apiBaseUrl, path, options);
  const wxRuntime = options.wxRuntime || (typeof wx !== "undefined" ? wx : null);
  if (!wxRuntime || typeof wxRuntime.request !== "function") {
    return Promise.reject(new ReleaseCenterApiError("wechat_runtime_unavailable"));
  }
  return new Promise((resolve, reject) => {
    wxRuntime.request({
      ...descriptor,
      success(response) {
        const status = Number(response.statusCode || 0);
        if (status < 200 || status >= 300) {
          reject(new ReleaseCenterApiError(status === 401 ? "authentication_required" : status === 403 ? "permission_denied" : "api_request_failed", status));
          return;
        }
        if (containsSensitiveMaterial(response.data)) {
          reject(new ReleaseCenterApiError("response_contains_sensitive_material", status));
          return;
        }
        resolve(response.data);
      },
      fail() {
        reject(new ReleaseCenterApiError("network_unavailable"));
      }
    });
  });
}

function isAllowedPath(path, method) {
  const value = String(path || "");
  if (!value.startsWith("/") || value.startsWith("//") || /[\\\r\n]/.test(value)) return false;
  const rules = method === "GET" ? READ_PATHS : method === "POST" ? WRITE_PATHS : [];
  return rules.some((rule) => rule.test(value));
}

function containsSensitiveMaterial(value) {
  if (Array.isArray(value)) return value.some(containsSensitiveMaterial);
  if (value && typeof value === "object") {
    return Object.entries(value).some(([key, item]) => {
      if (FORBIDDEN_KEY.test(key) && ![false, null, "", "[REDACTED]"].includes(item)) return true;
      return containsSensitiveMaterial(item);
    });
  }
  if (typeof value !== "string") return false;
  return FORBIDDEN_VALUE.some((pattern) => pattern.test(value));
}

function runtimeConfig() {
  try {
    const app = typeof getApp === "function" ? getApp() : null;
    return app ? app.globalData : {};
  } catch {
    return {};
  }
}

module.exports = {
  ReleaseCenterApiError,
  buildRequestDescriptor,
  containsSensitiveMaterial,
  isAllowedPath,
  normalizeApiBaseUrl,
  requestJson
};
