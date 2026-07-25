import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import * as root from "../dist/index.js";
import {
  TENANCY_ROUTES,
  TENANCY_SCHEMA_VERSION,
  TenancyClient,
  TenancyEnvironment,
  TenancyError,
  TenancyOrganization,
  TenancyProject,
  TenancyProjectMembership,
  tenancyEnvironmentCreateRoute,
  tenancyEnvironmentDisableRoute,
  tenancyEnvironmentEnableRoute,
  tenancyEnvironmentListRoute,
  tenancyOrganizationCreateRoute,
  tenancyOrganizationListRoute,
  tenancyProjectArchiveRoute,
  tenancyProjectCreateRoute,
  tenancyProjectListRoute,
  tenancyProjectMembershipListRoute,
  tenancyProjectMembershipRevokeRoute,
  tenancyProjectMembershipSetRoute,
  tenancyProjectRestoreRoute,
  tenancyProjectUpdateRoute,
} from "../dist/tenancy.js";

const ORGANIZATION_ID = "33333333-3333-4333-8333-333333333333";
const PROJECT_ID = "44444444-4444-4444-8444-444444444444";
const ENVIRONMENT_ID = "55555555-5555-4555-8555-555555555555";
const ACCOUNT_ID = "66666666-6666-4666-8666-666666666666";
const NOW = "2026-07-25T01:02:03Z";
const packageRoot = fileURLToPath(new URL("../", import.meta.url));

function organization(overrides = {}) {
  return {
    schema_version: TENANCY_SCHEMA_VERSION,
    organization_id: ORGANIZATION_ID,
    slug: "acme-org",
    display_name: "Acme",
    status: "active",
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function project(status = "active", overrides = {}) {
  return {
    schema_version: TENANCY_SCHEMA_VERSION,
    organization_id: ORGANIZATION_ID,
    project_id: PROJECT_ID,
    slug: "core-api",
    display_name: "Core API",
    status,
    created_at: NOW,
    updated_at: NOW,
    archived_at: status === "archived" ? NOW : null,
    ...overrides,
  };
}

function environment(status = "active", overrides = {}) {
  return {
    schema_version: TENANCY_SCHEMA_VERSION,
    organization_id: ORGANIZATION_ID,
    project_id: PROJECT_ID,
    environment_id: ENVIRONMENT_ID,
    name: "prod-cn",
    kind: "production",
    status,
    created_at: NOW,
    updated_at: NOW,
    disabled_at: status === "disabled" ? NOW : null,
    ...overrides,
  };
}

function membership(status = "active", overrides = {}) {
  return {
    schema_version: TENANCY_SCHEMA_VERSION,
    organization_id: ORGANIZATION_ID,
    project_id: PROJECT_ID,
    account_id: ACCOUNT_ID,
    role: "developer",
    status,
    created_at: NOW,
    updated_at: NOW,
    activated_at: NOW,
    revoked_at: status === "revoked" ? NOW : null,
    ...overrides,
  };
}

function mutation(result, idempotentReplay = false) {
  return {
    schema_version: TENANCY_SCHEMA_VERSION,
    result,
    request_id: "request_test_001",
    idempotent_replay: idempotentReplay,
  };
}

function response(status, payload, headers = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      ...headers,
    },
  });
}

function scriptedFetch(...responses) {
  const calls = [];
  let index = 0;
  const fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    const current = responses[index++];
    assert.ok(current, `unexpected fetch call ${index}`);
    return typeof current === "function" ? current(url, init) : current;
  };
  return { fetch, calls };
}

test("fourteen exact route helpers match the Go tenancy HTTP surface", () => {
  assert.equal(Object.isFrozen(TENANCY_ROUTES), true);
  assert.equal(TENANCY_ROUTES.length, 14);
  assert.deepEqual(
    TENANCY_ROUTES,
    [
      { operation: "organization.create", method: "POST", path: "/v1/organizations" },
      { operation: "organization.list", method: "GET", path: "/v1/organizations" },
      {
        operation: "project.create",
        method: "POST",
        path: "/v1/organizations/{organization_id}/projects",
      },
      {
        operation: "project.list",
        method: "GET",
        path: "/v1/organizations/{organization_id}/projects",
      },
      {
        operation: "project.update",
        method: "PATCH",
        path: "/v1/organizations/{organization_id}/projects/{project_id}",
      },
      {
        operation: "project.archive",
        method: "POST",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/archive",
      },
      {
        operation: "project.restore",
        method: "POST",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/restore",
      },
      {
        operation: "environment.create",
        method: "POST",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/environments",
      },
      {
        operation: "environment.list",
        method: "GET",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/environments",
      },
      {
        operation: "environment.disable",
        method: "POST",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/disable",
      },
      {
        operation: "environment.enable",
        method: "POST",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/enable",
      },
      {
        operation: "project_membership.list",
        method: "GET",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/memberships",
      },
      {
        operation: "project_membership.set",
        method: "PUT",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}",
      },
      {
        operation: "project_membership.revoke",
        method: "DELETE",
        path: "/v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}",
      },
    ],
  );
  assert.equal(TENANCY_ROUTES.every((entry) => Object.isFrozen(entry)), true);
  assert.equal(tenancyOrganizationCreateRoute(), "/v1/organizations");
  assert.equal(tenancyOrganizationListRoute(), "/v1/organizations");
  const projects = `/v1/organizations/${ORGANIZATION_ID}/projects`;
  assert.equal(tenancyProjectListRoute(ORGANIZATION_ID), projects);
  assert.equal(tenancyProjectCreateRoute(ORGANIZATION_ID), projects);
  const selected = `${projects}/${PROJECT_ID}`;
  assert.equal(tenancyProjectUpdateRoute(ORGANIZATION_ID, PROJECT_ID), selected);
  assert.equal(tenancyProjectArchiveRoute(ORGANIZATION_ID, PROJECT_ID), `${selected}/archive`);
  assert.equal(tenancyProjectRestoreRoute(ORGANIZATION_ID, PROJECT_ID), `${selected}/restore`);
  const environments = `${selected}/environments`;
  assert.equal(tenancyEnvironmentListRoute(ORGANIZATION_ID, PROJECT_ID), environments);
  assert.equal(tenancyEnvironmentCreateRoute(ORGANIZATION_ID, PROJECT_ID), environments);
  assert.equal(
    tenancyEnvironmentDisableRoute(ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID),
    `${environments}/${ENVIRONMENT_ID}/disable`,
  );
  assert.equal(
    tenancyEnvironmentEnableRoute(ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID),
    `${environments}/${ENVIRONMENT_ID}/enable`,
  );
  const memberships = `${selected}/memberships`;
  assert.equal(tenancyProjectMembershipListRoute(ORGANIZATION_ID, PROJECT_ID), memberships);
  assert.equal(
    tenancyProjectMembershipSetRoute(ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID),
    `${memberships}/${ACCOUNT_ID}`,
  );
  assert.equal(
    tenancyProjectMembershipRevokeRoute(ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID),
    `${memberships}/${ACCOUNT_ID}`,
  );
});

test("all fourteen client operations preserve methods, scopes, and header-only idempotency", async () => {
  const scripted = scriptedFetch(
    response(201, mutation(organization())),
    response(200, { schema_version: TENANCY_SCHEMA_VERSION, items: [organization()], count: 1 }),
    response(200, { schema_version: TENANCY_SCHEMA_VERSION, items: [project()], count: 1 }),
    response(201, mutation(project())),
    response(200, mutation(project())),
    response(200, mutation(project("archived"))),
    response(200, mutation(project())),
    response(200, { schema_version: TENANCY_SCHEMA_VERSION, items: [environment()], count: 1 }),
    response(201, mutation(environment())),
    response(200, mutation(environment("disabled"))),
    response(200, mutation(environment())),
    response(200, { schema_version: TENANCY_SCHEMA_VERSION, items: [membership()], count: 1 }),
    response(200, mutation(membership())),
    response(200, mutation(membership("revoked"))),
  );
  const client = new TenancyClient({
    baseUrl: "https://api.example.test",
    fetch: scripted.fetch,
  });
  const options = { idempotencyKey: "idem-typescript-0001" };

  await client.createOrganization(" ACME-ORG ", " Acme ", options);
  await client.listOrganizations();
  await client.listProjects(ORGANIZATION_ID);
  await client.createProject(ORGANIZATION_ID, "core-api", "Core API", options);
  await client.updateProject(ORGANIZATION_ID, PROJECT_ID, { ...options, displayName: "Core API" });
  await client.archiveProject(ORGANIZATION_ID, PROJECT_ID, options);
  await client.restoreProject(ORGANIZATION_ID, PROJECT_ID, options);
  await client.listEnvironments(ORGANIZATION_ID, PROJECT_ID);
  await client.createEnvironment(ORGANIZATION_ID, PROJECT_ID, "prod-cn", "production", options);
  await client.disableEnvironment(ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID, options);
  await client.enableEnvironment(ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID, options);
  await client.listProjectMemberships(ORGANIZATION_ID, PROJECT_ID);
  await client.setProjectMembership(ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID, "developer", options);
  await client.revokeProjectMembership(ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID, options);

  assert.deepEqual(
    scripted.calls.map(({ init }) => init.method),
    ["POST", "GET", "GET", "POST", "PATCH", "POST", "POST", "GET", "POST", "POST", "POST", "GET", "PUT", "DELETE"],
  );
  for (const { url, init } of scripted.calls) {
    assert.equal(init.credentials, "same-origin");
    assert.equal(init.redirect, "error");
    assert.equal(init.cache, "no-store");
    assert.equal(init.headers.has("cookie"), false);
    assert.equal(init.headers.has("authorization"), false);
    assert.equal(url.includes("?"), false);
    if (init.method === "GET") {
      assert.equal(init.body, undefined);
      assert.equal(init.headers.has("idempotency-key"), false);
    } else {
      const body = JSON.parse(init.body);
      assert.equal(init.headers.get("idempotency-key"), options.idempotencyKey);
      assert.equal(Object.hasOwn(body, "idempotency_key"), false);
      for (const forbidden of ["actor_id", "actor_principal_id", "principal_id", "session_id", "account_id"]) {
        assert.equal(Object.hasOwn(body, forbidden), false);
      }
    }
  }
  assert.deepEqual(JSON.parse(scripted.calls.at(-2).init.body), { role: "developer" });
  assert.deepEqual(JSON.parse(scripted.calls.at(-1).init.body), {});
  assert.match(scripted.calls.at(-2).url, new RegExp(`${ACCOUNT_ID}$`, "u"));
  assert.match(scripted.calls.at(-1).url, new RegExp(`${ACCOUNT_ID}$`, "u"));
});

test("browser authentication stays browser-managed and never becomes a public client input", async () => {
  const scripted = scriptedFetch(response(201, mutation(organization())));
  const client = new TenancyClient({
    baseUrl: "https://api.example.test",
    fetch: scripted.fetch,
  });
  const result = await client.createOrganization("acme-org", "Acme", {
    idempotencyKey: "idem-typescript-0002",
  });
  const [{ init }] = scripted.calls;
  assert.equal(init.credentials, "same-origin");
  assert.equal(init.headers.has("cookie"), false);
  assert.equal(init.headers.has("authorization"), false);
  assert.equal(JSON.stringify(result).includes("idem-typescript-0002"), false);
  assert.equal(Object.keys(client).some((key) => /cookie|token|credential/iu.test(key)), false);
});

test("DTOs are frozen and exact response parsing rejects private or cross-scope fields", async () => {
  const dto = TenancyOrganization.fromPublicResponse(organization());
  assert.equal(Object.isFrozen(dto), true);
  assert.throws(() => {
    dto.slug = "changed";
  }, TypeError);
  assert.equal(Object.isFrozen(TenancyProject.fromPublicResponse(project())), true);
  assert.equal(Object.isFrozen(TenancyEnvironment.fromPublicResponse(environment())), true);
  assert.equal(Object.isFrozen(TenancyProjectMembership.fromPublicResponse(membership())), true);

  for (const privateField of [
    "actor_id",
    "session_token",
    "oauth_state",
    "pkce",
    "secret_ref",
    "vault_ref",
    "request_digest",
    "raw_policy",
    "database_role",
    "provider_subject",
  ]) {
    const unsafe = organization({ [privateField]: { nested: "not-public" } });
    const scripted = scriptedFetch(response(200, {
      schema_version: TENANCY_SCHEMA_VERSION,
      items: [unsafe],
      count: 1,
    }));
    await assert.rejects(
      new TenancyClient({ baseUrl: "https://api.example.test", fetch: scripted.fetch }).listOrganizations(),
      (error) => error instanceof TenancyError
        && error.code === "tenancy_unavailable"
        && Object.keys(error.toJSON()).join(",") === "schema_version,code,message,request_id",
    );
  }

  const crossScope = scriptedFetch(response(200, {
    schema_version: TENANCY_SCHEMA_VERSION,
    items: [project("active", { organization_id: ACCOUNT_ID })],
    count: 1,
  }));
  await assert.rejects(
    new TenancyClient({ baseUrl: "https://api.example.test", fetch: crossScope.fetch }).listProjects(ORGANIZATION_ID),
    (error) => error instanceof TenancyError && error.code === "tenancy_unavailable",
  );
});

test("collection count, lifecycle timestamps, and malformed identifiers fail closed", async () => {
  const responses = [
    response(200, { schema_version: TENANCY_SCHEMA_VERSION, items: [], count: 1 }),
    response(200, {
      schema_version: TENANCY_SCHEMA_VERSION,
      items: [organization({ organization_id: "not-a-uuid" })],
      count: 1,
    }),
    response(200, {
      schema_version: TENANCY_SCHEMA_VERSION,
      items: [project("archived", { archived_at: null })],
      count: 1,
    }),
    response(200, {
      schema_version: TENANCY_SCHEMA_VERSION,
      items: [environment("disabled", { disabled_at: null })],
      count: 1,
    }),
    response(200, {
      schema_version: TENANCY_SCHEMA_VERSION,
      items: [membership("active", { activated_at: null })],
      count: 1,
    }),
  ];
  const client = new TenancyClient({
    baseUrl: "https://api.example.test",
    fetch: scriptedFetch(...responses).fetch,
  });
  for (const operation of [
    () => client.listOrganizations(),
    () => client.listOrganizations(),
    () => client.listProjects(ORGANIZATION_ID),
    () => client.listEnvironments(ORGANIZATION_ID, PROJECT_ID),
    () => client.listProjectMemberships(ORGANIZATION_ID, PROJECT_ID),
  ]) {
    await assert.rejects(operation(), (error) => error.code === "tenancy_unavailable");
  }
});

test("public errors accept only the exact canonical four-field envelope", async () => {
  const valid = scriptedFetch(response(409, {
    schema_version: TENANCY_SCHEMA_VERSION,
    code: "tenancy_last_owner",
    message: "project must retain an active owner",
    request_id: "request_test_002",
  }));
  await assert.rejects(
    new TenancyClient({ baseUrl: "https://api.example.test", fetch: valid.fetch })
      .revokeProjectMembership(
        ORGANIZATION_ID,
        PROJECT_ID,
        ACCOUNT_ID,
        { idempotencyKey: "idem-typescript-0003" },
      ),
    (error) => {
      assert.deepEqual(error.toJSON(), {
        schema_version: TENANCY_SCHEMA_VERSION,
        code: "tenancy_last_owner",
        message: "project must retain an active owner",
        request_id: "request_test_002",
      });
      return true;
    },
  );

  const malformed = scriptedFetch(response(409, {
    schema_version: TENANCY_SCHEMA_VERSION,
    code: "tenancy_last_owner",
    message: "private server detail",
    request_id: "request_test_003",
    sql: "not-public",
  }));
  await assert.rejects(
    new TenancyClient({ baseUrl: "https://api.example.test", fetch: malformed.fetch })
      .revokeProjectMembership(
        ORGANIZATION_ID,
        PROJECT_ID,
        ACCOUNT_ID,
        { idempotencyKey: "idem-typescript-0004" },
      ),
    (error) => error.code === "tenancy_unavailable"
      && !error.message.includes("private server detail")
      && !JSON.stringify(error).includes("not-public"),
  );
});

test("HTTPS is required and controlled localhost HTTP needs explicit opt-in", () => {
  assert.throws(
    () => new TenancyClient({ baseUrl: "http://localhost:8787" }),
    (error) => error.code === "tenancy_invalid_request",
  );
  assert.equal(
    new TenancyClient({
      baseUrl: "http://localhost:8787",
      allowInsecureLocalhost: true,
      fetch: async () => response(200, { schema_version: TENANCY_SCHEMA_VERSION, items: [], count: 0 }),
    }).origin,
    "http://localhost:8787",
  );
  assert.throws(
    () => new TenancyClient({ baseUrl: "http://example.test", allowInsecureLocalhost: true }),
    (error) => error.code === "tenancy_invalid_request",
  );
});

test("idempotency, update shape, and security response headers are enforced", async () => {
  const client = new TenancyClient({
    baseUrl: "https://api.example.test",
    fetch: async () => response(201, mutation(organization())),
  });
  await assert.rejects(
    client.createOrganization("acme-org", "Acme", { idempotencyKey: "short" }),
    (error) => error.code === "tenancy_invalid_idempotency_key",
  );
  assert.throws(
    () => client.updateProject(ORGANIZATION_ID, PROJECT_ID, { idempotencyKey: "idem-typescript-0005" }),
    (error) => error.code === "tenancy_invalid_request",
  );

  const missingHeaders = scriptedFetch(new Response(JSON.stringify({
    schema_version: TENANCY_SCHEMA_VERSION,
    items: [],
    count: 0,
  }), {
    status: 200,
    headers: { "content-type": "application/json" },
  }));
  await assert.rejects(
    new TenancyClient({ baseUrl: "https://api.example.test", fetch: missingHeaders.fetch }).listOrganizations(),
    (error) => error.code === "tenancy_unavailable",
  );
});

test("root and package subpath exports publish the complete tenancy client", () => {
  assert.equal(root.TenancyClient, TenancyClient);
  assert.equal(root.TENANCY_SCHEMA_VERSION, TENANCY_SCHEMA_VERSION);
  assert.equal(root.tenancy_project_membership_set_route, tenancyProjectMembershipSetRoute);
  const packageJson = JSON.parse(readFileSync(`${packageRoot}/package.json`, "utf8"));
  assert.deepEqual(packageJson.exports["./tenancy"], {
    types: "./dist/tenancy.d.ts",
    import: "./dist/tenancy.js",
  });
});
