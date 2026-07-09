export const A3_TENANT_SCOPE_SCHEMA_VERSION = "a3.tenant_scope.v1";

export function buildA3TenantScope(primary = {}, fallback = {}) {
  const source = primary.tenant_scope || primary.tenantScope || primary;
  const fallbackSource = fallback.tenant_scope || fallback.tenantScope || fallback;
  return {
    schema_version: A3_TENANT_SCOPE_SCHEMA_VERSION,
    organization_id: firstPresent(
      primary.organizationId,
      source.organization_id,
      source.organizationId,
      fallback.organizationId,
      fallbackSource.organization_id,
      fallbackSource.organizationId,
      "org-local"
    ),
    tenant_id: firstPresent(
      primary.tenantId,
      source.tenant_id,
      source.tenantId,
      fallback.tenantId,
      fallbackSource.tenant_id,
      fallbackSource.tenantId,
      "tenant-local"
    ),
    workspace_id: firstPresent(
      primary.workspaceId,
      source.workspace_id,
      source.workspaceId,
      fallback.workspaceId,
      fallbackSource.workspace_id,
      fallbackSource.workspaceId,
      "workspace-local"
    ),
    project_id: firstPresent(
      primary.projectId,
      source.project_id,
      source.projectId,
      fallback.projectId,
      fallbackSource.project_id,
      fallbackSource.projectId,
      "project-local"
    ),
    environment_id: firstPresent(
      primary.environmentId,
      source.environment_id,
      source.environmentId,
      fallback.environmentId,
      fallbackSource.environment_id,
      fallbackSource.environmentId,
      "staging"
    ),
    source_precedence: [
      "request_options",
      "payload.tenant_scope",
      "payload.root_fields",
      "snapshot_defaults",
      "local_dev_defaults"
    ]
  };
}

export function tenantScopeToSnapshotFields(scope = {}) {
  const normalized = buildA3TenantScope(scope);
  return {
    organizationId: normalized.organization_id,
    tenantId: normalized.tenant_id,
    workspaceId: normalized.workspace_id,
    projectId: normalized.project_id,
    environmentId: normalized.environment_id
  };
}

export function tenantScopeMatches(resource = {}, requested = {}) {
  const resourceScope = buildA3TenantScope(resource);
  const requestScope = buildA3TenantScope(requested, resourceScope);
  return ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"]
    .every((field) => {
      const explicit = explicitScopeValue(requested, field);
      return explicit === undefined || String(resourceScope[field]) === String(requestScope[field]);
    });
}

export function validateA3TenantScope(scope = {}) {
  const normalized = buildA3TenantScope(scope);
  const errors = [];
  for (const field of ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"]) {
    if (!normalized[field]) {
      errors.push(`${field} is required`);
    }
    if (/[^\w:./-]/.test(String(normalized[field]))) {
      errors.push(`${field} contains unsupported characters`);
    }
  }
  return {
    valid: errors.length === 0,
    errors,
    scope: normalized
  };
}

function explicitScopeValue(value = {}, field) {
  const camel = field.replace(/_([a-z])/g, (_, char) => char.toUpperCase());
  const source = value.tenant_scope || value.tenantScope || value;
  return value[camel] ?? source[field] ?? source[camel];
}

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}
