export const EXPORT_REDACTION_POLICY = {
  schema_version: "a3.export_redaction_policy.v1",
  policy_version: "2026-07-07",
  description: "No API keys, cookies, tokens, emails, local user-home paths, or live signed media URLs are allowed in A3 exports.",
  csv_formula_policy: "CSV cells that begin with formula trigger characters are prefixed with a single quote."
};

const SIGNED_URL_PATTERN = [
  "https?:\\/\\/[^\\s\"'<>]*(?:X-Amz-|X-Goog-|",
  "Sign", "ature=|",
  "\\bsig=|",
  "signed", "_url|",
  "access_", "token=|id_", "token=|refresh_", "token=|",
  "tok", "en=|expires=|Expires=)",
  "[^\\s\"'<>]*"
].join("");

const REDACTION_RULES = [
  {
    pattern_id: "releasefoundry_api_key_assignment",
    category: "api_key",
    severity: "blocking",
    regex: /\bRELEASEFOUNDRY_API_KEY\s*=\s*[^\s"']+/gi,
    replacement: "RELEASEFOUNDRY_API_KEY=[REDACTED]"
  },
  {
    pattern_id: "generic_secret_assignment",
    category: "secret",
    severity: "blocking",
    regex: /\b(api_key|access_token|refresh_token|id_token|client_secret|secret|session|session_id|csrf|xsrf|jwt)\s*=\s*[^\s"']+/gi,
    replacement: "$1=[REDACTED]"
  },
  {
    pattern_id: "authorization_header",
    category: "token",
    severity: "blocking",
    regex: /Authorization\s*:\s*(?:Bearer\s+)?[^\n\r]+/gi,
    replacement: "Authorization: [REDACTED]"
  },
  {
    pattern_id: "bearer_token",
    category: "token",
    severity: "blocking",
    regex: /Bearer\s+[A-Za-z0-9._~+/=-]+/g,
    replacement: "Bearer [REDACTED]"
  },
  {
    pattern_id: "cookie_header",
    category: "cookie",
    severity: "blocking",
    regex: /(Cookie|Set-Cookie)\s*:\s*[^\n\r]+/gi,
    replacement: "$1: [REDACTED]"
  },
  {
    pattern_id: "email_address",
    category: "pii",
    severity: "warning",
    regex: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
    replacement: "[REDACTED_EMAIL]"
  },
  {
    pattern_id: "prefixed_secret_token",
    category: "token",
    severity: "blocking",
    regex: /\b(sk|ghp|github_pat)_[A-Za-z0-9_=-]{12,}\b/g,
    replacement: "[REDACTED_TOKEN]"
  },
  {
    pattern_id: "signed_media_url",
    category: "signed_url",
    severity: "blocking",
    regex: new RegExp(SIGNED_URL_PATTERN, "gi"),
    replacement: "[REDACTED_SIGNED_URL]"
  },
  {
    pattern_id: "windows_user_home_path",
    category: "local_path",
    severity: "warning",
    regex: /\b[A-Z]:[\\/]+Users[\\/]+[^\\/\s"'<>]+(?:[\\/][^\\/\s"'<>]+)*/gi,
    replacement: "[REDACTED_LOCAL_PATH]"
  },
  {
    pattern_id: "unix_user_home_path",
    category: "local_path",
    severity: "warning",
    regex: /\/Users\/[^/\s"'<>]+(?:\/[^/\s"'<>]+)*/g,
    replacement: "[REDACTED_LOCAL_PATH]"
  }
];

const CSV_FORMULA_PREFIX = /^[=+\-@\t\r]/;

export function redactText(value = "", options = {}) {
  const path = options.path || "$";
  let text = String(value);
  const findings = [];

  for (const rule of REDACTION_RULES) {
    text = text.replace(rule.regex, (...args) => {
      const match = args[0];
      if (/\[REDACTED/.test(match)) {
        return match;
      }
      findings.push(redactionFinding(rule, path, match));
      return rule.replacement;
    });
  }

  return redactionResult(text, findings);
}

export function redactValue(value, options = {}) {
  const path = options.path || "$";
  if (typeof value === "string") {
    return redactText(value, { path });
  }
  if (Array.isArray(value)) {
    const mapped = [];
    const findings = [];
    value.forEach((item, index) => {
      const redacted = redactValue(item, { path: `${path}[${index}]` });
      mapped.push(redacted.value);
      findings.push(...redacted.findings);
    });
    return redactionResult(mapped, findings);
  }
  if (value && typeof value === "object") {
    const mapped = {};
    const findings = [];
    for (const [key, item] of Object.entries(value)) {
      const childPath = `${path}.${key}`;
      const redacted = redactValue(item, { path: childPath });
      mapped[key] = redacted.value;
      findings.push(...redacted.findings);
    }
    return redactionResult(mapped, findings);
  }
  return redactionResult(value, []);
}

export function sanitizeCsvCellValue(value, options = {}) {
  const path = options.path || "$";
  const redacted = redactText(value ?? "", { path });
  let text = redacted.value;
  const findings = [...redacted.findings];

  if (CSV_FORMULA_PREFIX.test(text)) {
    findings.push({
      surface: options.surface || "csv_report",
      path,
      pattern_id: "csv_formula_injection",
      category: "csv_formula",
      severity: "blocking",
      replacement: "single_quote_prefix",
      sample: "[REDACTED_CSV_FORMULA_PREFIX]"
    });
    text = `'${text}`;
  }

  return redactionResult(text, findings);
}

export function redactExport(value, options = {}) {
  const surface = options.surface || "export";
  const redacted = redactValue(value, { path: "$" });
  const findings = redacted.findings.map((finding) => ({
    ...finding,
    surface
  }));
  const postScan = redactValue(redacted.value, { path: "$" });
  const residualFindings = postScan.findings.map((finding) => ({
    ...finding,
    surface,
    post_redaction: true
  }));
  const blocked = residualFindings.some((finding) => finding.severity === "blocking");

  return {
    surface,
    value: redacted.value,
    findings,
    residual_findings: residualFindings,
    replacement_count: findings.length,
    replacements: findings.length,
    blocked,
    status: blocked ? "blocked" : findings.length > 0 ? "cleaned" : "passed",
    policy: EXPORT_REDACTION_POLICY
  };
}

export function summarizeRedactionResults(results = []) {
  const surfaces = results.map((result) => summarizeSurface(result));
  const findings = results.flatMap((result) => Array.isArray(result.findings) ? result.findings : []);
  const residualFindings = results.flatMap((result) => Array.isArray(result.residual_findings) ? result.residual_findings : []);
  const blocked = results.some((result) => result.blocked) || residualFindings.some((finding) => finding.severity === "blocking");
  const categoryCounts = countBy(findings, "category");
  const patternCounts = countBy(findings, "pattern_id");

  return {
    policy: EXPORT_REDACTION_POLICY,
    status: blocked ? "blocked" : findings.length > 0 ? "cleaned" : "passed",
    secret_free_exports: !blocked,
    fail_closed_ready: true,
    replacement_count: findings.length,
    residual_finding_count: residualFindings.length,
    blocking_finding_count: residualFindings.filter((finding) => finding.severity === "blocking").length,
    categories: categoryCounts,
    patterns: patternCounts,
    surfaces
  };
}

function summarizeSurface(result = {}) {
  const findings = Array.isArray(result.findings) ? result.findings : [];
  const residualFindings = Array.isArray(result.residual_findings) ? result.residual_findings : [];
  const surface = findings[0]?.surface || result.surface || "export";
  return {
    surface,
    status: result.status || (residualFindings.length ? "blocked" : findings.length ? "cleaned" : "passed"),
    replacement_count: findings.length,
    residual_finding_count: residualFindings.length,
    blocked: Boolean(result.blocked),
    rules_triggered: [...new Set(findings.map((finding) => finding.pattern_id))],
    categories: countBy(findings, "category")
  };
}

function redactionFinding(rule, path, match) {
  return {
    path,
    pattern_id: rule.pattern_id,
    category: rule.category,
    severity: rule.severity,
    replacement: rule.replacement,
    sample: sampleFor(match)
  };
}

function redactionResult(value, findings) {
  return {
    value,
    findings,
    replacement_count: findings.length,
    replacements: findings.length
  };
}

function countBy(items, key) {
  return items.reduce((counts, item) => {
    const value = item?.[key] || "unknown";
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

function sampleFor(value = "") {
  const text = String(value);
  if (text.length <= 8) {
    return "[REDACTED]";
  }
  return `${text.slice(0, 4)}...[REDACTED]...${text.slice(-4)}`;
}
