#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { A3_SENSITIVE_ROUTE_PATTERNS } from "./a3_route_access_control.mjs";

const VERIFIED_PRINCIPAL_SECURITY = [
  { A1VerifiedSession: [] },
  { A1ServiceAccount: [] }
];

const TENANT_SCOPE_CONTRACT = {
  required: [
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id"
  ],
  source: "server_verified_a1_principal",
  client_declared_scope_authoritative: false,
  scope_match_required: true,
  cross_tenant_default: "sanitized_403_or_404"
};

const AUTH_CONTRACT = {
  required_for_hosted_saas: true,
  current_local_state: "contract_only_fail_closed",
  backend_owner: "A1",
  enforcement_owner: "A3 hosted API or same-origin BFF",
  principal_authority: "A1 server-side verifier",
  principal_source: "server_verified_a1_principal",
  accepted_principal_kinds: ["browser_session", "service_account"],
  client_declared_identity_authoritative: false,
  client_declared_role_authoritative: false,
  hosted_contract_only_not_production_proof: true
};

export function synchronizeA3OpenApiRuntimeParity(spec = {}) {
  const next = structuredClone(spec);
  next.paths ||= {};
  next.components ||= {};
  next.components.parameters ||= {};
  next.components.parameters.ApiKeyId ||= identifierParameter("api_key_id", "A1 API-key handle; never raw key material.");

  const operationIndex = openApiOperationIndex(next);
  for (const route of A3_SENSITIVE_ROUTE_PATTERNS) {
    const normalizedKey = routeKey(route.method, route.path_pattern);
    const existingOperation = operationIndex.get(normalizedKey);
    if (existingOperation) {
      existingOperation["x-rbac"] ||= {};
      existingOperation["x-rbac"].operation_id = route.operation_id;
      existingOperation["x-rbac"].permission = route.required_permission;
      continue;
    }

    const path = runtimePathToOpenApi(route.path_pattern);
    const method = route.method.toLowerCase();
    next.paths[path] ||= {};
    next.paths[path][method] = buildParityOperation(route, path);
    operationIndex.set(normalizedKey, next.paths[path][method]);
  }
  return next;
}

export function inspectA3OpenApiRuntimeParity(spec = {}) {
  const operations = openApiOperationIndex(spec);
  const missing = A3_SENSITIVE_ROUTE_PATTERNS.filter((route) => (
    !operations.has(routeKey(route.method, route.path_pattern))
  ));
  return {
    schema_version: "a3.openapi_runtime_parity.v1",
    runtime_operation_count: A3_SENSITIVE_ROUTE_PATTERNS.length,
    documented_runtime_operation_count: A3_SENSITIVE_ROUTE_PATTERNS.length - missing.length,
    missing: missing.map((route) => ({
      operation_id: route.operation_id,
      method: route.method,
      path: route.path_pattern,
      required_permission: route.required_permission
    })),
    complete: missing.length === 0
  };
}

export function runtimePathToOpenApi(path = "") {
  return String(path).replace(/:([A-Za-z0-9_]+)/g, "{$1}");
}

export function normalizeContractPath(path = "") {
  return String(path)
    .replace(/:([A-Za-z0-9_]+)/g, "{}")
    .replace(/\{[^}]+\}/g, "{}");
}

function buildParityOperation(route, path) {
  const readOnly = route.method === "GET";
  const operation = {
    operationId: `a3${pascalCase(route.operation_id)}`,
    summary: `A3 protected operation: ${route.operation_id}.`,
    tags: tagsFor(route.operation_id),
    "x-schema-version": "a3.openapi_runtime_parity.v1",
    "x-tenant-scope": structuredClone(TENANT_SCOPE_CONTRACT),
    "x-auth": structuredClone(AUTH_CONTRACT),
    "x-rbac": {
      operation_id: route.operation_id,
      permission: route.required_permission,
      denied_state_required: true,
      evaluation: "server_side_against_verified_principal",
      client_declared_role_authoritative: false
    },
    "x-usage": {
      meters: ["api_requests"],
      source_of_truth: "A1 usage ledger; A3 only emits a metering intent."
    },
    "x-audit": {
      events: [`${route.operation_id}.requested`],
      payload_policy: "ids_hashes_refs_status_counts_only"
    },
    "x-a1-a2-contract": {
      a1: ["verified principal", "tenant scope", "usage and audit execution"],
      a2: ["GradeResult and release decision authority remain unchanged"],
      a3_rule: "A3 orchestrates product workflow and must not reinterpret A1 runtime facts or A2 decision semantics."
    },
    security: structuredClone(VERIFIED_PRINCIPAL_SECURITY),
    "x-access-class": readOnly ? "tenant_sensitive_read" : "tenant_sensitive_write",
    responses: {
      [readOnly ? "200" : "202"]: successResponse(path, readOnly),
      "401": { $ref: "#/components/responses/Unauthorized" },
      "403": { $ref: "#/components/responses/Forbidden" },
      "404": { $ref: "#/components/responses/NotFound" }
    }
  };

  const parameters = pathParameters(path);
  if (parameters.length) operation.parameters = parameters;
  if (!readOnly) {
    operation.requestBody = {
      required: true,
      "x-secret-policy": "raw_secret_values_forbidden",
      content: {
        "application/json": {
          schema: {
            type: "object",
            description: "Operation-specific typed payload. Tenant scope and identity are always resolved server-side.",
            additionalProperties: true
          }
        }
      }
    };
  }
  return operation;
}

function successResponse(path, readOnly) {
  const contentType = path.startsWith("/reports/") && readOnly ? "text/html" : "application/json";
  return {
    description: readOnly ? "Sanitized tenant-scoped response." : "Mutation accepted for trusted execution or returned as a fail-closed plan.",
    content: {
      [contentType]: {
        schema: contentType === "text/html"
          ? { type: "string" }
          : { type: "object", additionalProperties: true }
      }
    }
  };
}

function pathParameters(path) {
  return [...String(path).matchAll(/\{([^}]+)\}/g)].map((match) => {
    const name = match[1];
    const component = {
      releaseId: "ReleaseId",
      reportId: "ReportId",
      runId: "RunId",
      caseId: "CaseId",
      api_key_id: "ApiKeyId"
    }[name];
    return component
      ? { $ref: `#/components/parameters/${component}` }
      : identifierParameter(name, `${name} path identifier.`);
  });
}

function identifierParameter(name, description) {
  return {
    name,
    in: "path",
    required: true,
    description,
    schema: {
      type: "string",
      minLength: 1,
      maxLength: 160
    }
  };
}

function openApiOperationIndex(spec = {}) {
  const operations = new Map();
  for (const [path, pathItem] of Object.entries(spec.paths || {})) {
    for (const method of ["get", "post", "put", "patch", "delete"]) {
      if (pathItem?.[method]) operations.set(routeKey(method, path), pathItem[method]);
    }
  }
  return operations;
}

function routeKey(method, path) {
  return `${String(method).toUpperCase()} ${normalizeContractPath(path)}`;
}

function pascalCase(value) {
  return String(value).split("_").map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`).join("");
}

function tagsFor(operationId) {
  if (/report/.test(operationId)) return ["Reports"];
  if (/billing/.test(operationId)) return ["Billing"];
  if (/github|release|review/.test(operationId)) return ["Release Gate", "Review"];
  if (/admin|api_key|teammate/.test(operationId)) return ["Admin"];
  if (/trust/.test(operationId)) return ["Trust"];
  return ["Operations"];
}

async function run(argv = process.argv.slice(2)) {
  const outputPath = resolve(argv[0] || "docs/a3/openapi/a3_commercial_api.openapi.json");
  const spec = JSON.parse(await readFile(outputPath, "utf8"));
  const synchronized = synchronizeA3OpenApiRuntimeParity(spec);
  await writeFile(outputPath, `${JSON.stringify(synchronized, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(inspectA3OpenApiRuntimeParity(synchronized))}\n`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  run().catch((error) => {
    process.stderr.write(`${error.name}: ${error.message}\n`);
    process.exitCode = 1;
  });
}
