export const TENANCY_SCHEMA_VERSION = "releasefoundry.tenancy.v1";

export const TENANCY_ERROR_CODES = [
  "tenancy_authentication_required",
  "tenancy_invalid_idempotency_key",
  "tenancy_invalid_request",
  "tenancy_idempotency_conflict",
  "tenancy_forbidden",
  "tenancy_not_found",
  "tenancy_state_conflict",
  "tenancy_last_owner",
  "tenancy_unavailable",
] as const;

export const TENANCY_PROJECT_ROLES = [
  "owner",
  "admin",
  "developer",
  "reviewer",
  "auditor",
  "read_only_viewer",
  "service_account",
] as const;

export const TENANCY_ENVIRONMENT_KINDS = [
  "development",
  "staging",
  "production",
  "sandbox",
] as const;

export interface TenancyRoute {
  readonly operation: string;
  readonly method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  readonly path: string;
}

export const TENANCY_ROUTES: readonly TenancyRoute[] = Object.freeze([
  Object.freeze({ operation: "organization.create", method: "POST", path: "/v1/organizations" }),
  Object.freeze({ operation: "organization.list", method: "GET", path: "/v1/organizations" }),
  Object.freeze({
    operation: "project.create",
    method: "POST",
    path: "/v1/organizations/{organization_id}/projects",
  }),
  Object.freeze({
    operation: "project.list",
    method: "GET",
    path: "/v1/organizations/{organization_id}/projects",
  }),
  Object.freeze({
    operation: "project.update",
    method: "PATCH",
    path: "/v1/organizations/{organization_id}/projects/{project_id}",
  }),
  Object.freeze({
    operation: "project.archive",
    method: "POST",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/archive",
  }),
  Object.freeze({
    operation: "project.restore",
    method: "POST",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/restore",
  }),
  Object.freeze({
    operation: "environment.create",
    method: "POST",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/environments",
  }),
  Object.freeze({
    operation: "environment.list",
    method: "GET",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/environments",
  }),
  Object.freeze({
    operation: "environment.disable",
    method: "POST",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/disable",
  }),
  Object.freeze({
    operation: "environment.enable",
    method: "POST",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/enable",
  }),
  Object.freeze({
    operation: "project_membership.list",
    method: "GET",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/memberships",
  }),
  Object.freeze({
    operation: "project_membership.set",
    method: "PUT",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}",
  }),
  Object.freeze({
    operation: "project_membership.revoke",
    method: "DELETE",
    path: "/v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}",
  }),
]);

export type TenancyErrorCode = typeof TENANCY_ERROR_CODES[number];
export type TenancyProjectRole = typeof TENANCY_PROJECT_ROLES[number];
export type TenancyEnvironmentKind = typeof TENANCY_ENVIRONMENT_KINDS[number];
export type TenancyProjectStatus = "active" | "archived";
export type TenancyEnvironmentStatus = "active" | "disabled";
export type TenancyMembershipStatus = "invited" | "active" | "suspended" | "revoked";

interface TenancyErrorDetail {
  readonly status: number;
  readonly message: string;
}

const ERROR_DETAILS: Readonly<Record<TenancyErrorCode, TenancyErrorDetail>> = Object.freeze({
  tenancy_authentication_required: {
    status: 401,
    message: "authentication is required",
  },
  tenancy_invalid_idempotency_key: {
    status: 400,
    message: "Idempotency-Key is invalid",
  },
  tenancy_invalid_request: {
    status: 400,
    message: "tenancy request is invalid",
  },
  tenancy_idempotency_conflict: {
    status: 409,
    message: "Idempotency-Key was already used for a different request",
  },
  tenancy_forbidden: {
    status: 403,
    message: "tenancy operation is forbidden",
  },
  tenancy_not_found: {
    status: 404,
    message: "tenancy resource was not found",
  },
  tenancy_state_conflict: {
    status: 409,
    message: "tenancy lifecycle state conflicts with the operation",
  },
  tenancy_last_owner: {
    status: 409,
    message: "project must retain an active owner",
  },
  tenancy_unavailable: {
    status: 503,
    message: "tenancy service is temporarily unavailable",
  },
});

const READABLE_PROJECT_ROLES = [
  ...TENANCY_PROJECT_ROLES,
  "operator",
  "viewer",
  "member",
] as const;
const PROJECT_STATUSES = ["active", "archived"] as const;
const ENVIRONMENT_STATUSES = ["active", "disabled"] as const;
const MEMBERSHIP_STATUSES = ["invited", "active", "suspended", "revoked"] as const;
const IDEMPOTENCY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/u;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;
const SLUG_PATTERN = /^[a-z](?:[a-z0-9-]{1,62}[a-z0-9])$/u;
const ENVIRONMENT_NAME_PATTERN = /^[a-z](?:[a-z0-9_-]{1,62}[a-z0-9])$/u;
const CORRELATION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/u;
const TIMEZONE_SUFFIX = /(?:Z|[+-]\d{2}:\d{2})$/u;
const MAX_RESPONSE_BYTES = 1_048_576;
const FORBIDDEN_CANONICAL_KEYS = new Set([
  "actor",
  "actorid",
  "actorprincipalid",
  "principal",
  "principalid",
  "session",
  "sessionid",
  "sessiontoken",
  "sessiondigest",
  "token",
  "cookie",
  "credential",
  "oauth",
  "state",
  "nonce",
  "pkce",
  "proof",
  "ticket",
  "challenge",
  "secretref",
  "privateref",
  "vaultref",
  "kms",
  "ciphertext",
  "requestdigest",
  "payloaddigest",
  "subjectdigest",
  "eventdigest",
  "rawpolicy",
  "rls",
  "acl",
  "sql",
  "databaserole",
  "email",
  "phone",
  "providersubject",
]);
const FORBIDDEN_CANONICAL_SUFFIXES = [
  "token",
  "cookie",
  "credential",
  "secretref",
  "privateref",
  "vaultref",
  "ciphertext",
  "digest",
  "ticket",
  "challenge",
  "proof",
] as const;

export interface TenancyPublicError {
  readonly schema_version: typeof TENANCY_SCHEMA_VERSION;
  readonly code: TenancyErrorCode;
  readonly message: string;
  readonly request_id: string;
}

export class TenancyError extends Error {
  readonly schema_version = TENANCY_SCHEMA_VERSION;
  readonly code: TenancyErrorCode;
  readonly request_id: string;
  readonly status: number;

  constructor(
    code: string,
    options: {
      readonly requestId?: string;
      readonly status?: number;
    } = {},
  ) {
    const normalized = isErrorCode(code) ? code : "tenancy_unavailable";
    const detail = ERROR_DETAILS[normalized];
    super(detail.message);
    this.name = "TenancyError";
    this.code = normalized;
    this.request_id = correlationId(options.requestId ?? "request_unavailable", "request_unavailable");
    this.status = options.status ?? detail.status;
    Object.freeze(this);
  }

  toJSON(): TenancyPublicError {
    return {
      schema_version: this.schema_version,
      code: this.code,
      message: this.message,
      request_id: this.request_id,
    };
  }
}

export interface TenancyOrganizationDTO {
  readonly schema_version: typeof TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly slug: string;
  readonly display_name: string;
  readonly status: "active";
  readonly created_at: string;
  readonly updated_at: string;
}

export class TenancyOrganization implements TenancyOrganizationDTO {
  readonly schema_version = TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly slug: string;
  readonly display_name: string;
  readonly status: "active";
  readonly created_at: string;
  readonly updated_at: string;

  private constructor(value: Omit<TenancyOrganizationDTO, "schema_version">) {
    this.organization_id = value.organization_id;
    this.slug = value.slug;
    this.display_name = value.display_name;
    this.status = value.status;
    this.created_at = value.created_at;
    this.updated_at = value.updated_at;
    Object.freeze(this);
  }

  static fromPublicResponse(payload: unknown): TenancyOrganization {
    const value = exactObject(payload, [
      "schema_version",
      "organization_id",
      "slug",
      "display_name",
      "status",
      "created_at",
      "updated_at",
    ]);
    schemaVersion(value);
    const result = new TenancyOrganization({
      organization_id: responseUuid(value.organization_id),
      slug: responseSlug(value.slug),
      display_name: responseDisplayName(value.display_name),
      status: responseEnum(value.status, ["active"] as const),
      created_at: timestamp(value.created_at),
      updated_at: timestamp(value.updated_at),
    });
    orderedTimestamps(result.created_at, result.updated_at);
    return result;
  }

  static from_public_response(payload: unknown): TenancyOrganization {
    return TenancyOrganization.fromPublicResponse(payload);
  }

  toJSON(): TenancyOrganizationDTO {
    return {
      schema_version: this.schema_version,
      organization_id: this.organization_id,
      slug: this.slug,
      display_name: this.display_name,
      status: this.status,
      created_at: this.created_at,
      updated_at: this.updated_at,
    };
  }
}

export interface TenancyProjectDTO {
  readonly schema_version: typeof TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly project_id: string;
  readonly slug: string;
  readonly display_name: string;
  readonly status: TenancyProjectStatus;
  readonly created_at: string;
  readonly updated_at: string;
  readonly archived_at: string | null;
}

export interface TenancyProjectExpectedScope {
  readonly organizationId?: string;
  readonly projectId?: string;
}

export class TenancyProject implements TenancyProjectDTO {
  readonly schema_version = TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly project_id: string;
  readonly slug: string;
  readonly display_name: string;
  readonly status: TenancyProjectStatus;
  readonly created_at: string;
  readonly updated_at: string;
  readonly archived_at: string | null;

  private constructor(value: Omit<TenancyProjectDTO, "schema_version">) {
    this.organization_id = value.organization_id;
    this.project_id = value.project_id;
    this.slug = value.slug;
    this.display_name = value.display_name;
    this.status = value.status;
    this.created_at = value.created_at;
    this.updated_at = value.updated_at;
    this.archived_at = value.archived_at;
    Object.freeze(this);
  }

  static fromPublicResponse(
    payload: unknown,
    expected: TenancyProjectExpectedScope = {},
  ): TenancyProject {
    const value = exactObject(payload, [
      "schema_version",
      "organization_id",
      "project_id",
      "slug",
      "display_name",
      "status",
      "created_at",
      "updated_at",
      "archived_at",
    ]);
    schemaVersion(value);
    const result = new TenancyProject({
      organization_id: responseUuid(value.organization_id),
      project_id: responseUuid(value.project_id),
      slug: responseSlug(value.slug),
      display_name: responseDisplayName(value.display_name),
      status: responseEnum(value.status, PROJECT_STATUSES),
      created_at: timestamp(value.created_at),
      updated_at: timestamp(value.updated_at),
      archived_at: optionalTimestamp(value.archived_at),
    });
    orderedTimestamps(result.created_at, result.updated_at);
    if ((result.status === "archived") !== (result.archived_at !== null)) throw invalidResponse();
    expectedScope(result.organization_id, expected.organizationId);
    expectedScope(result.project_id, expected.projectId);
    return result;
  }

  static from_public_response(
    payload: unknown,
    expected: TenancyProjectExpectedScope = {},
  ): TenancyProject {
    return TenancyProject.fromPublicResponse(payload, expected);
  }

  toJSON(): TenancyProjectDTO {
    return {
      schema_version: this.schema_version,
      organization_id: this.organization_id,
      project_id: this.project_id,
      slug: this.slug,
      display_name: this.display_name,
      status: this.status,
      created_at: this.created_at,
      updated_at: this.updated_at,
      archived_at: this.archived_at,
    };
  }
}

export interface TenancyEnvironmentDTO {
  readonly schema_version: typeof TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly project_id: string;
  readonly environment_id: string;
  readonly name: string;
  readonly kind: TenancyEnvironmentKind;
  readonly status: TenancyEnvironmentStatus;
  readonly created_at: string;
  readonly updated_at: string;
  readonly disabled_at: string | null;
}

export interface TenancyEnvironmentExpectedScope extends TenancyProjectExpectedScope {
  readonly environmentId?: string;
}

export class TenancyEnvironment implements TenancyEnvironmentDTO {
  readonly schema_version = TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly project_id: string;
  readonly environment_id: string;
  readonly name: string;
  readonly kind: TenancyEnvironmentKind;
  readonly status: TenancyEnvironmentStatus;
  readonly created_at: string;
  readonly updated_at: string;
  readonly disabled_at: string | null;

  private constructor(value: Omit<TenancyEnvironmentDTO, "schema_version">) {
    this.organization_id = value.organization_id;
    this.project_id = value.project_id;
    this.environment_id = value.environment_id;
    this.name = value.name;
    this.kind = value.kind;
    this.status = value.status;
    this.created_at = value.created_at;
    this.updated_at = value.updated_at;
    this.disabled_at = value.disabled_at;
    Object.freeze(this);
  }

  static fromPublicResponse(
    payload: unknown,
    expected: TenancyEnvironmentExpectedScope = {},
  ): TenancyEnvironment {
    const value = exactObject(payload, [
      "schema_version",
      "organization_id",
      "project_id",
      "environment_id",
      "name",
      "kind",
      "status",
      "created_at",
      "updated_at",
      "disabled_at",
    ]);
    schemaVersion(value);
    const result = new TenancyEnvironment({
      organization_id: responseUuid(value.organization_id),
      project_id: responseUuid(value.project_id),
      environment_id: responseUuid(value.environment_id),
      name: responseEnvironmentName(value.name),
      kind: responseEnum(value.kind, TENANCY_ENVIRONMENT_KINDS),
      status: responseEnum(value.status, ENVIRONMENT_STATUSES),
      created_at: timestamp(value.created_at),
      updated_at: timestamp(value.updated_at),
      disabled_at: optionalTimestamp(value.disabled_at),
    });
    orderedTimestamps(result.created_at, result.updated_at);
    if ((result.status === "disabled") !== (result.disabled_at !== null)) throw invalidResponse();
    expectedScope(result.organization_id, expected.organizationId);
    expectedScope(result.project_id, expected.projectId);
    expectedScope(result.environment_id, expected.environmentId);
    return result;
  }

  static from_public_response(
    payload: unknown,
    expected: TenancyEnvironmentExpectedScope = {},
  ): TenancyEnvironment {
    return TenancyEnvironment.fromPublicResponse(payload, expected);
  }

  toJSON(): TenancyEnvironmentDTO {
    return {
      schema_version: this.schema_version,
      organization_id: this.organization_id,
      project_id: this.project_id,
      environment_id: this.environment_id,
      name: this.name,
      kind: this.kind,
      status: this.status,
      created_at: this.created_at,
      updated_at: this.updated_at,
      disabled_at: this.disabled_at,
    };
  }
}

export interface TenancyProjectMembershipDTO {
  readonly schema_version: typeof TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly project_id: string;
  readonly account_id: string;
  readonly role: typeof READABLE_PROJECT_ROLES[number];
  readonly status: TenancyMembershipStatus;
  readonly created_at: string;
  readonly updated_at: string;
  readonly activated_at: string | null;
  readonly revoked_at: string | null;
}

export interface TenancyProjectMembershipExpectedScope extends TenancyProjectExpectedScope {
  readonly accountId?: string;
}

export class TenancyProjectMembership implements TenancyProjectMembershipDTO {
  readonly schema_version = TENANCY_SCHEMA_VERSION;
  readonly organization_id: string;
  readonly project_id: string;
  readonly account_id: string;
  readonly role: typeof READABLE_PROJECT_ROLES[number];
  readonly status: TenancyMembershipStatus;
  readonly created_at: string;
  readonly updated_at: string;
  readonly activated_at: string | null;
  readonly revoked_at: string | null;

  private constructor(value: Omit<TenancyProjectMembershipDTO, "schema_version">) {
    this.organization_id = value.organization_id;
    this.project_id = value.project_id;
    this.account_id = value.account_id;
    this.role = value.role;
    this.status = value.status;
    this.created_at = value.created_at;
    this.updated_at = value.updated_at;
    this.activated_at = value.activated_at;
    this.revoked_at = value.revoked_at;
    Object.freeze(this);
  }

  static fromPublicResponse(
    payload: unknown,
    expected: TenancyProjectMembershipExpectedScope = {},
  ): TenancyProjectMembership {
    const value = exactObject(payload, [
      "schema_version",
      "organization_id",
      "project_id",
      "account_id",
      "role",
      "status",
      "created_at",
      "updated_at",
      "activated_at",
      "revoked_at",
    ]);
    schemaVersion(value);
    const result = new TenancyProjectMembership({
      organization_id: responseUuid(value.organization_id),
      project_id: responseUuid(value.project_id),
      account_id: responseUuid(value.account_id),
      role: responseEnum(value.role, READABLE_PROJECT_ROLES),
      status: responseEnum(value.status, MEMBERSHIP_STATUSES),
      created_at: timestamp(value.created_at),
      updated_at: timestamp(value.updated_at),
      activated_at: optionalTimestamp(value.activated_at),
      revoked_at: optionalTimestamp(value.revoked_at),
    });
    orderedTimestamps(result.created_at, result.updated_at);
    if (result.status === "active" && result.activated_at === null) throw invalidResponse();
    if ((result.status === "revoked") !== (result.revoked_at !== null)) throw invalidResponse();
    expectedScope(result.organization_id, expected.organizationId);
    expectedScope(result.project_id, expected.projectId);
    expectedScope(result.account_id, expected.accountId);
    return result;
  }

  static from_public_response(
    payload: unknown,
    expected: TenancyProjectMembershipExpectedScope = {},
  ): TenancyProjectMembership {
    return TenancyProjectMembership.fromPublicResponse(payload, expected);
  }

  toJSON(): TenancyProjectMembershipDTO {
    return {
      schema_version: this.schema_version,
      organization_id: this.organization_id,
      project_id: this.project_id,
      account_id: this.account_id,
      role: this.role,
      status: this.status,
      created_at: this.created_at,
      updated_at: this.updated_at,
      activated_at: this.activated_at,
      revoked_at: this.revoked_at,
    };
  }
}

export type TenancyResource =
  | TenancyOrganization
  | TenancyProject
  | TenancyEnvironment
  | TenancyProjectMembership;

export interface TenancyCollectionDTO<T extends TenancyResource> {
  readonly schema_version: typeof TENANCY_SCHEMA_VERSION;
  readonly items: readonly ReturnType<T["toJSON"]>[];
  readonly count: number;
}

export class TenancyCollection<T extends TenancyResource> {
  readonly schema_version = TENANCY_SCHEMA_VERSION;
  readonly items: readonly T[];
  readonly count: number;

  constructor(items: readonly T[], count: number) {
    this.items = Object.freeze([...items]);
    this.count = count;
    Object.freeze(this);
  }

  toJSON(): TenancyCollectionDTO<T> {
    return {
      schema_version: this.schema_version,
      items: this.items.map((item) => item.toJSON()) as unknown as TenancyCollectionDTO<T>["items"],
      count: this.count,
    };
  }
}

export interface TenancyMutationEnvelopeDTO<T extends TenancyResource> {
  readonly schema_version: typeof TENANCY_SCHEMA_VERSION;
  readonly result: ReturnType<T["toJSON"]>;
  readonly request_id: string;
  readonly idempotent_replay: boolean;
}

export class TenancyMutationEnvelope<T extends TenancyResource> {
  readonly schema_version = TENANCY_SCHEMA_VERSION;
  readonly result: T;
  readonly request_id: string;
  readonly idempotent_replay: boolean;

  constructor(result: T, requestId: string, idempotentReplay: boolean) {
    this.result = result;
    this.request_id = requestId;
    this.idempotent_replay = idempotentReplay;
    Object.freeze(this);
  }

  toJSON(): TenancyMutationEnvelopeDTO<T> {
    return {
      schema_version: this.schema_version,
      result: this.result.toJSON() as TenancyMutationEnvelopeDTO<T>["result"],
      request_id: this.request_id,
      idempotent_replay: this.idempotent_replay,
    };
  }
}

export function tenancyOrganizationCreateRoute(): string {
  return "/v1/organizations";
}

export function tenancyOrganizationListRoute(): string {
  return "/v1/organizations";
}

export function tenancyProjectListRoute(organizationId: string): string {
  return `/v1/organizations/${uuidValue(organizationId)}/projects`;
}

export function tenancyProjectCreateRoute(organizationId: string): string {
  return tenancyProjectListRoute(organizationId);
}

export function tenancyProjectUpdateRoute(organizationId: string, projectId: string): string {
  return `${tenancyProjectListRoute(organizationId)}/${uuidValue(projectId)}`;
}

export function tenancyProjectArchiveRoute(organizationId: string, projectId: string): string {
  return `${tenancyProjectUpdateRoute(organizationId, projectId)}/archive`;
}

export function tenancyProjectRestoreRoute(organizationId: string, projectId: string): string {
  return `${tenancyProjectUpdateRoute(organizationId, projectId)}/restore`;
}

export function tenancyEnvironmentListRoute(organizationId: string, projectId: string): string {
  return `${tenancyProjectUpdateRoute(organizationId, projectId)}/environments`;
}

export function tenancyEnvironmentCreateRoute(organizationId: string, projectId: string): string {
  return tenancyEnvironmentListRoute(organizationId, projectId);
}

export function tenancyEnvironmentDisableRoute(
  organizationId: string,
  projectId: string,
  environmentId: string,
): string {
  return `${tenancyEnvironmentListRoute(organizationId, projectId)}/${uuidValue(environmentId)}/disable`;
}

export function tenancyEnvironmentEnableRoute(
  organizationId: string,
  projectId: string,
  environmentId: string,
): string {
  return `${tenancyEnvironmentListRoute(organizationId, projectId)}/${uuidValue(environmentId)}/enable`;
}

export function tenancyProjectMembershipListRoute(organizationId: string, projectId: string): string {
  return `${tenancyProjectUpdateRoute(organizationId, projectId)}/memberships`;
}

export function tenancyProjectMembershipSetRoute(
  organizationId: string,
  projectId: string,
  accountId: string,
): string {
  return `${tenancyProjectMembershipListRoute(organizationId, projectId)}/${uuidValue(accountId)}`;
}

export function tenancyProjectMembershipRevokeRoute(
  organizationId: string,
  projectId: string,
  accountId: string,
): string {
  return tenancyProjectMembershipSetRoute(organizationId, projectId, accountId);
}

export const tenancy_organization_create_route = tenancyOrganizationCreateRoute;
export const tenancy_organization_list_route = tenancyOrganizationListRoute;
export const tenancy_project_list_route = tenancyProjectListRoute;
export const tenancy_project_create_route = tenancyProjectCreateRoute;
export const tenancy_project_update_route = tenancyProjectUpdateRoute;
export const tenancy_project_archive_route = tenancyProjectArchiveRoute;
export const tenancy_project_restore_route = tenancyProjectRestoreRoute;
export const tenancy_environment_list_route = tenancyEnvironmentListRoute;
export const tenancy_environment_create_route = tenancyEnvironmentCreateRoute;
export const tenancy_environment_disable_route = tenancyEnvironmentDisableRoute;
export const tenancy_environment_enable_route = tenancyEnvironmentEnableRoute;
export const tenancy_project_membership_list_route = tenancyProjectMembershipListRoute;
export const tenancy_project_membership_set_route = tenancyProjectMembershipSetRoute;
export const tenancy_project_membership_revoke_route = tenancyProjectMembershipRevokeRoute;

export interface TenancyClientOptions {
  readonly baseUrl: string;
  readonly fetch?: typeof fetch;
  readonly timeoutMs?: number;
  readonly signal?: AbortSignal;
  readonly allowInsecureLocalhost?: boolean;
}

export interface TenancyIdempotentOptions {
  readonly idempotencyKey: string;
}

export interface TenancyProjectUpdateOptions extends TenancyIdempotentOptions {
  readonly slug?: string;
  readonly displayName?: string;
}

type TenancyParser<T extends TenancyResource> = (payload: unknown) => T;
type TenancyMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export class TenancyClient {
  readonly #origin: string;
  readonly #fetch: typeof fetch;
  readonly #timeoutMs: number;
  readonly #signal: AbortSignal | undefined;

  constructor(options: TenancyClientOptions) {
    this.#origin = normalizeOrigin(options.baseUrl, options.allowInsecureLocalhost === true);
    this.#fetch = options.fetch ?? globalThis.fetch;
    if (typeof this.#fetch !== "function") throw failure("tenancy_invalid_request");
    this.#timeoutMs = boundedInteger(options.timeoutMs ?? 30_000, 1, 300_000);
    this.#signal = options.signal;
  }

  get origin(): string {
    return this.#origin;
  }

  createOrganization(
    slug: string,
    displayName: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyOrganization>> {
    return this.#mutate(
      "POST",
      tenancyOrganizationCreateRoute(),
      {
        slug: slugValue(slug),
        display_name: displayNameValue(displayName),
      },
      options.idempotencyKey,
      201,
      TenancyOrganization.fromPublicResponse,
    );
  }

  listOrganizations(): Promise<TenancyCollection<TenancyOrganization>> {
    return this.#list(tenancyOrganizationListRoute(), TenancyOrganization.fromPublicResponse);
  }

  listProjects(organizationId: string): Promise<TenancyCollection<TenancyProject>> {
    const organization = uuidValue(organizationId);
    return this.#list(
      tenancyProjectListRoute(organization),
      (payload) => TenancyProject.fromPublicResponse(payload, { organizationId: organization }),
    );
  }

  createProject(
    organizationId: string,
    slug: string,
    displayName: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    const organization = uuidValue(organizationId);
    return this.#mutate(
      "POST",
      tenancyProjectCreateRoute(organization),
      {
        slug: slugValue(slug),
        display_name: displayNameValue(displayName),
      },
      options.idempotencyKey,
      201,
      (payload) => TenancyProject.fromPublicResponse(payload, { organizationId: organization }),
    );
  }

  updateProject(
    organizationId: string,
    projectId: string,
    options: TenancyProjectUpdateOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    const payload: Record<string, unknown> = {};
    if (options.slug !== undefined) payload.slug = slugValue(options.slug);
    if (options.displayName !== undefined) payload.display_name = displayNameValue(options.displayName);
    if (Object.keys(payload).length === 0) throw failure("tenancy_invalid_request");
    return this.#mutate(
      "PATCH",
      tenancyProjectUpdateRoute(organization, project),
      payload,
      options.idempotencyKey,
      200,
      (value) => TenancyProject.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
      }),
    );
  }

  archiveProject(
    organizationId: string,
    projectId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    return this.#projectStateMutation(organizationId, projectId, "archive", options.idempotencyKey);
  }

  restoreProject(
    organizationId: string,
    projectId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    return this.#projectStateMutation(organizationId, projectId, "restore", options.idempotencyKey);
  }

  listEnvironments(
    organizationId: string,
    projectId: string,
  ): Promise<TenancyCollection<TenancyEnvironment>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    return this.#list(
      tenancyEnvironmentListRoute(organization, project),
      (value) => TenancyEnvironment.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
      }),
    );
  }

  createEnvironment(
    organizationId: string,
    projectId: string,
    name: string,
    kind: TenancyEnvironmentKind | string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyEnvironment>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    return this.#mutate(
      "POST",
      tenancyEnvironmentCreateRoute(organization, project),
      {
        name: environmentNameValue(name),
        kind: enumValue(kind, TENANCY_ENVIRONMENT_KINDS),
      },
      options.idempotencyKey,
      201,
      (value) => TenancyEnvironment.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
      }),
    );
  }

  disableEnvironment(
    organizationId: string,
    projectId: string,
    environmentId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyEnvironment>> {
    return this.#environmentStateMutation(
      organizationId,
      projectId,
      environmentId,
      "disable",
      options.idempotencyKey,
    );
  }

  enableEnvironment(
    organizationId: string,
    projectId: string,
    environmentId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyEnvironment>> {
    return this.#environmentStateMutation(
      organizationId,
      projectId,
      environmentId,
      "enable",
      options.idempotencyKey,
    );
  }

  listProjectMemberships(
    organizationId: string,
    projectId: string,
  ): Promise<TenancyCollection<TenancyProjectMembership>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    return this.#list(
      tenancyProjectMembershipListRoute(organization, project),
      (value) => TenancyProjectMembership.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
      }),
    );
  }

  setProjectMembership(
    organizationId: string,
    projectId: string,
    accountId: string,
    role: TenancyProjectRole | string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProjectMembership>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    const account = uuidValue(accountId);
    return this.#mutate(
      "PUT",
      tenancyProjectMembershipSetRoute(organization, project, account),
      { role: enumValue(role, TENANCY_PROJECT_ROLES) },
      options.idempotencyKey,
      200,
      (value) => TenancyProjectMembership.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
        accountId: account,
      }),
    );
  }

  revokeProjectMembership(
    organizationId: string,
    projectId: string,
    accountId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProjectMembership>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    const account = uuidValue(accountId);
    return this.#mutate(
      "DELETE",
      tenancyProjectMembershipRevokeRoute(organization, project, account),
      {},
      options.idempotencyKey,
      200,
      (value) => TenancyProjectMembership.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
        accountId: account,
      }),
    );
  }

  create_organization(
    slug: string,
    displayName: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyOrganization>> {
    return this.createOrganization(slug, displayName, options);
  }

  list_organizations(): Promise<TenancyCollection<TenancyOrganization>> {
    return this.listOrganizations();
  }

  list_projects(organizationId: string): Promise<TenancyCollection<TenancyProject>> {
    return this.listProjects(organizationId);
  }

  create_project(
    organizationId: string,
    slug: string,
    displayName: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    return this.createProject(organizationId, slug, displayName, options);
  }

  update_project(
    organizationId: string,
    projectId: string,
    options: TenancyProjectUpdateOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    return this.updateProject(organizationId, projectId, options);
  }

  archive_project(
    organizationId: string,
    projectId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    return this.archiveProject(organizationId, projectId, options);
  }

  restore_project(
    organizationId: string,
    projectId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    return this.restoreProject(organizationId, projectId, options);
  }

  list_environments(
    organizationId: string,
    projectId: string,
  ): Promise<TenancyCollection<TenancyEnvironment>> {
    return this.listEnvironments(organizationId, projectId);
  }

  create_environment(
    organizationId: string,
    projectId: string,
    name: string,
    kind: TenancyEnvironmentKind | string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyEnvironment>> {
    return this.createEnvironment(organizationId, projectId, name, kind, options);
  }

  disable_environment(
    organizationId: string,
    projectId: string,
    environmentId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyEnvironment>> {
    return this.disableEnvironment(organizationId, projectId, environmentId, options);
  }

  enable_environment(
    organizationId: string,
    projectId: string,
    environmentId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyEnvironment>> {
    return this.enableEnvironment(organizationId, projectId, environmentId, options);
  }

  list_project_memberships(
    organizationId: string,
    projectId: string,
  ): Promise<TenancyCollection<TenancyProjectMembership>> {
    return this.listProjectMemberships(organizationId, projectId);
  }

  set_project_membership(
    organizationId: string,
    projectId: string,
    accountId: string,
    role: TenancyProjectRole | string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProjectMembership>> {
    return this.setProjectMembership(organizationId, projectId, accountId, role, options);
  }

  revoke_project_membership(
    organizationId: string,
    projectId: string,
    accountId: string,
    options: TenancyIdempotentOptions,
  ): Promise<TenancyMutationEnvelope<TenancyProjectMembership>> {
    return this.revokeProjectMembership(organizationId, projectId, accountId, options);
  }

  #projectStateMutation(
    organizationId: string,
    projectId: string,
    operation: "archive" | "restore",
    idempotencyKeyValue: string,
  ): Promise<TenancyMutationEnvelope<TenancyProject>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    const route = operation === "archive"
      ? tenancyProjectArchiveRoute(organization, project)
      : tenancyProjectRestoreRoute(organization, project);
    return this.#mutate(
      "POST",
      route,
      {},
      idempotencyKeyValue,
      200,
      (value) => TenancyProject.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
      }),
    );
  }

  #environmentStateMutation(
    organizationId: string,
    projectId: string,
    environmentId: string,
    operation: "disable" | "enable",
    idempotencyKeyValue: string,
  ): Promise<TenancyMutationEnvelope<TenancyEnvironment>> {
    const organization = uuidValue(organizationId);
    const project = uuidValue(projectId);
    const environment = uuidValue(environmentId);
    const route = operation === "disable"
      ? tenancyEnvironmentDisableRoute(organization, project, environment)
      : tenancyEnvironmentEnableRoute(organization, project, environment);
    return this.#mutate(
      "POST",
      route,
      {},
      idempotencyKeyValue,
      200,
      (value) => TenancyEnvironment.fromPublicResponse(value, {
        organizationId: organization,
        projectId: project,
        environmentId: environment,
      }),
    );
  }

  async #list<T extends TenancyResource>(
    path: string,
    parser: TenancyParser<T>,
  ): Promise<TenancyCollection<T>> {
    const response = await this.#request("GET", path, undefined, undefined, 200);
    const envelope = exactObject(await decodeResponse(response), [
      "schema_version",
      "items",
      "count",
    ]);
    schemaVersion(envelope);
    if (!Array.isArray(envelope.items)
      || !Number.isSafeInteger(envelope.count)
      || Number(envelope.count) < 0
      || Number(envelope.count) !== envelope.items.length) {
      throw invalidResponse();
    }
    return new TenancyCollection(envelope.items.map((item) => parser(item)), Number(envelope.count));
  }

  async #mutate<T extends TenancyResource>(
    method: Exclude<TenancyMethod, "GET">,
    path: string,
    payload: Readonly<Record<string, unknown>>,
    rawIdempotencyKey: string,
    successStatus: number,
    parser: TenancyParser<T>,
  ): Promise<TenancyMutationEnvelope<T>> {
    assertPublicSafe(payload);
    const response = await this.#request(
      method,
      path,
      payload,
      idempotencyKey(rawIdempotencyKey),
      successStatus,
    );
    const envelope = exactObject(await decodeResponse(response), [
      "schema_version",
      "result",
      "request_id",
      "idempotent_replay",
    ]);
    schemaVersion(envelope);
    if (typeof envelope.idempotent_replay !== "boolean") throw invalidResponse();
    return new TenancyMutationEnvelope(
      parser(envelope.result),
      correlationId(envelope.request_id),
      envelope.idempotent_replay,
    );
  }

  async #request(
    method: TenancyMethod,
    path: string,
    payload: Readonly<Record<string, unknown>> | undefined,
    idempotencyKeyValue: string | undefined,
    successStatus: number,
  ): Promise<Response> {
    const headers = new Headers({
      accept: "application/json",
      "cache-control": "no-store",
      pragma: "no-cache",
    });
    let body: string | undefined;
    if (payload !== undefined) {
      headers.set("content-type", "application/json");
      body = JSON.stringify(payload);
    }
    if (idempotencyKeyValue !== undefined) headers.set("idempotency-key", idempotencyKeyValue);
    if (headers.has("cookie") || headers.has("authorization")) throw failure("tenancy_invalid_request");

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.#timeoutMs);
    const abortFromCaller = () => controller.abort();
    this.#signal?.addEventListener("abort", abortFromCaller, { once: true });
    try {
      if (this.#signal?.aborted) controller.abort();
      const response = await this.#fetch(`${this.#origin}${path}`, {
        method,
        headers,
        body,
        credentials: "same-origin",
        redirect: "error",
        cache: "no-store",
        signal: controller.signal,
      });
      if (!(response instanceof Response)) throw invalidResponse();
      if (response.status !== successStatus) throw await errorFromResponse(response);
      validateResponseHeaders(response);
      return response;
    } catch (error) {
      if (error instanceof TenancyError) throw error;
      if (timedOut || controller.signal.aborted) throw failure("tenancy_unavailable");
      throw failure("tenancy_unavailable");
    } finally {
      clearTimeout(timer);
      this.#signal?.removeEventListener("abort", abortFromCaller);
    }
  }
}

function failure(
  code: TenancyErrorCode,
  options: {
    readonly requestId?: string;
    readonly status?: number;
  } = {},
): TenancyError {
  return new TenancyError(code, options);
}

function invalidResponse(): TenancyError {
  return failure("tenancy_unavailable");
}

function isErrorCode(value: string): value is TenancyErrorCode {
  return (TENANCY_ERROR_CODES as readonly string[]).includes(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactObject(payload: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!isRecord(payload)) throw invalidResponse();
  assertPublicSafe(payload);
  const actual = Object.keys(payload);
  if (actual.length !== keys.length || keys.some((key) => !Object.hasOwn(payload, key))) {
    throw invalidResponse();
  }
  return payload;
}

function schemaVersion(value: Readonly<Record<string, unknown>>): typeof TENANCY_SCHEMA_VERSION {
  if (value.schema_version !== TENANCY_SCHEMA_VERSION) throw invalidResponse();
  return TENANCY_SCHEMA_VERSION;
}

function uuidValue(value: unknown): string {
  if (typeof value !== "string" || value !== value.trim() || !UUID_PATTERN.test(value)) {
    throw failure("tenancy_invalid_request");
  }
  return value;
}

function responseUuid(value: unknown): string {
  try {
    return uuidValue(value);
  } catch {
    throw invalidResponse();
  }
}

function slugValue(value: unknown): string {
  if (typeof value !== "string") throw failure("tenancy_invalid_request");
  const normalized = value.trim().toLowerCase();
  if (!SLUG_PATTERN.test(normalized)) throw failure("tenancy_invalid_request");
  return normalized;
}

function responseSlug(value: unknown): string {
  try {
    return slugValue(value);
  } catch {
    throw invalidResponse();
  }
}

function environmentNameValue(value: unknown): string {
  if (typeof value !== "string") throw failure("tenancy_invalid_request");
  const normalized = value.trim().toLowerCase();
  if (!ENVIRONMENT_NAME_PATTERN.test(normalized)) throw failure("tenancy_invalid_request");
  return normalized;
}

function responseEnvironmentName(value: unknown): string {
  try {
    return environmentNameValue(value);
  } catch {
    throw invalidResponse();
  }
}

function displayNameValue(value: unknown): string {
  if (typeof value !== "string") throw failure("tenancy_invalid_request");
  const normalized = value.trim();
  if (normalized.length < 1 || normalized.length > 120 || normalized.includes("\0")) {
    throw failure("tenancy_invalid_request");
  }
  return normalized;
}

function responseDisplayName(value: unknown): string {
  try {
    return displayNameValue(value);
  } catch {
    throw invalidResponse();
  }
}

function enumValue<const T extends readonly string[]>(value: unknown, allowed: T): T[number] {
  if (typeof value !== "string") throw failure("tenancy_invalid_request");
  const normalized = value.trim().toLowerCase();
  if (!(allowed as readonly string[]).includes(normalized)) throw failure("tenancy_invalid_request");
  return normalized as T[number];
}

function responseEnum<const T extends readonly string[]>(value: unknown, allowed: T): T[number] {
  try {
    return enumValue(value, allowed);
  } catch {
    throw invalidResponse();
  }
}

function idempotencyKey(value: unknown): string {
  if (typeof value !== "string" || !IDEMPOTENCY_PATTERN.test(value)) {
    throw failure("tenancy_invalid_idempotency_key");
  }
  return value;
}

function correlationId(value: unknown, fallback?: string): string {
  if (typeof value === "string" && CORRELATION_PATTERN.test(value)) return value;
  if (fallback !== undefined) return fallback;
  throw invalidResponse();
}

function timestamp(value: unknown): string {
  if (typeof value !== "string"
    || value.length < 1
    || value.length > 64
    || value !== value.trim()
    || !TIMEZONE_SUFFIX.test(value)
    || !Number.isFinite(Date.parse(value))) {
    throw invalidResponse();
  }
  return value;
}

function optionalTimestamp(value: unknown): string | null {
  return value === null ? null : timestamp(value);
}

function orderedTimestamps(createdAt: string, updatedAt: string): void {
  if (Date.parse(updatedAt) < Date.parse(createdAt)) throw invalidResponse();
}

function expectedScope(actual: string, expected: string | undefined): void {
  if (expected !== undefined && actual !== expected) throw invalidResponse();
}

function assertPublicSafe(value: unknown): void {
  if (Array.isArray(value)) {
    for (const item of value) assertPublicSafe(item);
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, nested] of Object.entries(value)) {
    const normalized = key.trim().toLowerCase().replaceAll(/[^a-z0-9]/gu, "");
    if (FORBIDDEN_CANONICAL_KEYS.has(normalized)
      || FORBIDDEN_CANONICAL_SUFFIXES.some((suffix) => normalized.endsWith(suffix))) {
      throw invalidResponse();
    }
    assertPublicSafe(nested);
  }
}

function normalizeOrigin(value: string, allowInsecureLocalhost: boolean): string {
  let url: URL;
  try {
    url = new URL(String(value).trim());
  } catch {
    throw failure("tenancy_invalid_request");
  }
  const local = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(url.hostname);
  if (url.username
    || url.password
    || url.search
    || url.hash
    || (url.pathname !== "/" && url.pathname !== "")) {
    throw failure("tenancy_invalid_request");
  }
  if (url.protocol !== "https:" && !(url.protocol === "http:" && local && allowInsecureLocalhost)) {
    throw failure("tenancy_invalid_request");
  }
  return url.origin.toLowerCase();
}

function boundedInteger(value: number, minimum: number, maximum: number): number {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw failure("tenancy_invalid_request");
  }
  return value;
}

function validateResponseHeaders(response: Response): void {
  const contentType = response.headers.get("content-type");
  const cacheControl = response.headers.get("cache-control");
  const nosniff = response.headers.get("x-content-type-options");
  if (contentType === null
    || contentType.split(";", 1)[0]?.trim().toLowerCase() !== "application/json"
    || cacheControl?.trim().toLowerCase() !== "no-store"
    || nosniff?.trim().toLowerCase() !== "nosniff") {
    throw invalidResponse();
  }
}

async function decodeResponse(response: Response): Promise<Record<string, unknown>> {
  validateResponseHeaders(response);
  const declaredLength = response.headers.get("content-length");
  if (declaredLength !== null) {
    const parsed = Number(declaredLength);
    if (!Number.isSafeInteger(parsed) || parsed < 0 || parsed > MAX_RESPONSE_BYTES) throw invalidResponse();
  }
  let text: string;
  try {
    text = await response.text();
  } catch {
    throw invalidResponse();
  }
  if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) throw invalidResponse();
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw invalidResponse();
  }
  if (!isRecord(value)) throw invalidResponse();
  assertPublicSafe(value);
  return value;
}

async function errorFromResponse(response: Response): Promise<TenancyError> {
  try {
    const value = exactObject(await decodeResponse(response), [
      "schema_version",
      "code",
      "message",
      "request_id",
    ]);
    schemaVersion(value);
    if (typeof value.code !== "string" || !isErrorCode(value.code)) throw invalidResponse();
    const detail = ERROR_DETAILS[value.code];
    if (value.message !== detail.message || response.status !== detail.status) throw invalidResponse();
    return failure(value.code, {
      requestId: correlationId(value.request_id),
      status: response.status,
    });
  } catch (error) {
    if (error instanceof TenancyError
      && error.code === "tenancy_unavailable"
      && error.request_id === "request_unavailable") {
      return error;
    }
    return invalidResponse();
  }
}
