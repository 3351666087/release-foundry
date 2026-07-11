import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  SaaSControlPlaneRouter,
  SaaSControlPlaneService,
  SaaSIngestionClient,
  exportSaaSOpenApiSpec,
} from "../dist/saas.js";

const tenantId = "tenant_round45_ts";
const projectId = "project_round45_ts";
const redirectUri = "https://app.ashr-clone.invalid/oauth/callback";
const verifier = "round45_ts_pkce_verifier_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const oauthState = "round45_ts_oauth_state_0123456789";

function bootstrap(service = new SaaSControlPlaneService()) {
  service.bootstrapProject({
    tenantName: "Round 45 TS",
    projectName: "Parity",
    tenantId,
    projectId,
  });
  return service;
}

function configureOauth(service) {
  return service.configureOauthProvider(tenantId, projectId, {
    provider: "github",
    clientIdRef: "env:GITHUB_CLIENT_ID",
    clientSecretRef: "vault:oauth/github/client-secret",
    redirectUris: [redirectUri],
    scopes: ["read:user", "user:email"],
    configId: "oauthcfg_round45_ts",
  });
}

test("round45_ts OAuth authorization enforces PKCE/state and persists only safe evidence", () => {
  const service = bootstrap();
  const config = configureOauth(service);
  assert.equal(config.provider, "github");
  assert.equal(config.secret_value_present, false);

  const begun = service.beginOauthAuthorization(tenantId, projectId, {
    providerConfigId: config.config_id,
    redirectUri,
    codeVerifier: verifier,
    state: oauthState,
  });
  const expectedChallenge = createHash("sha256").update(verifier, "ascii").digest("base64url");
  assert.equal(begun.code_challenge, expectedChallenge);
  assert.equal(begun.code_challenge_method, "S256");
  assert.equal(begun.state, oauthState);
  assert.equal(begun.state_hash_present, true);
  assert.equal(begun.raw_state_present, false);

  const snapshotText = JSON.stringify(service.snapshotState());
  assert.equal(snapshotText.includes(oauthState), false);
  assert.equal(snapshotText.includes(verifier), false);

  const completed = service.completeOauthAuthorization(tenantId, projectId, {
    flowId: begun.flow_id,
    state: oauthState,
    codeVerifier: verifier,
    redirectUri,
    subjectRef: "github:user:round45",
    providerCodeRef: "provider-ref:github/code/round45",
    accessTokenRef: "vault:oauth/github/access/round45",
    refreshTokenRef: "kms:oauth/github/refresh/round45",
    sessionId: "oauthsess_round45_ts",
  });
  assert.equal(completed.accepted, true);
  assert.equal(completed.status, "completed");
  assert.equal(completed.provider_code_ref_present, true);
  assert.equal(completed.session.session_id, "oauthsess_round45_ts");
  assert.equal(completed.session.access_token_ref_present, true);
  assert.equal(completed.session.refresh_token_ref_present, true);

  const replay = service.completeOauthAuthorization(tenantId, projectId, {
    flowId: begun.flow_id,
    state: oauthState,
    codeVerifier: verifier,
    redirectUri,
    subjectRef: "github:user:round45",
  });
  assert.equal(replay.accepted, false);
  assert.deepEqual(replay.failure_reasons, ["oauth_state_replay"]);

  assert.throws(
    () => service.configureOauthProvider(tenantId, projectId, {
      provider: "github",
      clientIdRef: "raw-client-id",
      clientSecretRef: "raw-client-secret",
      redirectUris: [redirectUri],
      scopes: ["read:user"],
    }),
    /secret reference prefix/,
  );
});

test("round45_ts router and OpenAPI expose executable OAuth authorization contracts", () => {
  const service = bootstrap();
  const router = new SaaSControlPlaneRouter(service);
  const configured = router.handle(
    "POST",
    `/v1/projects/${projectId}/commercial-auth-payment/oauth-providers/configure`,
    {
      tenant_id: tenantId,
      provider: "google",
      client_id_ref: "env:GOOGLE_CLIENT_ID",
      client_secret_ref: "env:GOOGLE_CLIENT_SECRET",
      redirect_uris: [redirectUri],
      scopes: ["openid", "email"],
      config_id: "oauthcfg_router_round45_ts",
    },
  );
  assert.equal(configured.status_code, 201);

  const begun = router.handle(
    "POST",
    `/v1/projects/${projectId}/commercial-auth-payment/oauth-authorizations/begin`,
    {
      tenant_id: tenantId,
      provider_config_id: configured.body.config_id,
      redirect_uri: redirectUri,
      code_verifier: verifier,
      state: oauthState,
    },
  );
  assert.equal(begun.status_code, 201);

  const completed = router.handle(
    "POST",
    `/v1/projects/${projectId}/commercial-auth-payment/oauth-authorizations/${begun.body.flow_id}/complete`,
    {
      tenant_id: tenantId,
      state: oauthState,
      code_verifier: verifier,
      redirect_uri: redirectUri,
      subject_ref: "google:user:round45",
      provider_code_ref: "provider-ref:google/code/round45",
    },
  );
  assert.equal(completed.status_code, 200);
  assert.equal(completed.body.accepted, true);

  const paths = exportSaaSOpenApiSpec().paths;
  assert.ok(paths["/v1/projects/{project_id}/commercial-auth-payment/oauth-providers/configure"]);
  assert.ok(paths["/v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/begin"]);
  assert.ok(paths["/v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/{flow_id}/complete"]);
});

test("round45_ts HTTP typed clients send exact snake_case billing and OAuth bodies", async () => {
  const calls = [];
  const transport = {
    async requestJson(method, requestPath, body) {
      calls.push({ method, path: requestPath, body });
      if (requestPath.endsWith("/oauth-providers/configure")) {
        return {
          tenant_id: tenantId,
          project_id: projectId,
          config_id: "oauthcfg_http_round45_ts",
          provider: "github",
          client_id_ref: body.client_id_ref,
          client_secret_ref: body.client_secret_ref,
          redirect_uris: body.redirect_uris,
          scopes: body.scopes,
          enabled: true,
          secret_value_present: false,
        };
      }
      if (requestPath.endsWith("/oauth-authorizations/begin")) {
        return {
          tenant_id: tenantId,
          project_id: projectId,
          flow_id: "oauthflow_http_round45_ts",
          provider: "github",
          provider_config_id: body.provider_config_id,
          redirect_uri: body.redirect_uri,
          state_hash_present: true,
          code_challenge: "challenge",
          code_challenge_method: "S256",
          status: "pending",
          session_id: null,
          provider_code_ref_present: false,
          failure_reasons: [],
          secret_value_present: false,
          raw_code_present: false,
          raw_state_present: false,
          state: body.state,
        };
      }
      if (requestPath.endsWith("/complete")) {
        return {
          tenant_id: tenantId,
          project_id: projectId,
          flow_id: "oauthflow_http_round45_ts",
          provider: "github",
          provider_config_id: "oauthcfg_http_round45_ts",
          redirect_uri: body.redirect_uri,
          state_hash_present: true,
          code_challenge: "challenge",
          code_challenge_method: "S256",
          status: "completed",
          session_id: "oauthsess_http_round45_ts",
          provider_code_ref_present: true,
          failure_reasons: [],
          secret_value_present: false,
          raw_code_present: false,
          raw_state_present: false,
          accepted: true,
        };
      }
      if (requestPath.endsWith("/checkout-plan")) return { plan_type: "checkout_session", plan_id: "checkout_http_round45_ts" };
      if (requestPath.endsWith("/portal-plan")) return { plan_type: "billing_portal", plan_id: "portal_http_round45_ts" };
      return {
        provider_event_key: "stripe:test:evt_http_round45_ts",
        provider: "stripe",
        mode: "test",
        tenant_id: tenantId,
        project_id: projectId,
        event_id: "evt_http_round45_ts",
        event_type: "invoice.paid",
        payload_sha256: "a".repeat(64),
        ingest_status: "accepted",
        ledger_mutation_count: 1,
        raw_payload_included: false,
        secret_value_present: false,
      };
    },
  };
  const client = new SaaSIngestionClient({ transport });

  const configured = await client.configureOauthProviderHttp(tenantId, projectId, {
    provider: "github",
    clientIdRef: "env:GITHUB_CLIENT_ID",
    clientSecretRef: "env:GITHUB_CLIENT_SECRET",
    redirectUris: [redirectUri],
    scopes: ["read:user"],
    configId: "oauthcfg_http_round45_ts",
    authKeyId: "key_http_round45_ts",
  });
  const begun = await client.beginOauthAuthorizationHttp(tenantId, projectId, {
    providerConfigId: configured.result.config_id,
    redirectUri,
    codeVerifier: verifier,
    state: oauthState,
    authKeyId: "key_http_round45_ts",
  });
  const completed = await client.completeOauthAuthorizationHttp(tenantId, projectId, {
    flowId: begun.result.flow_id,
    state: oauthState,
    codeVerifier: verifier,
    redirectUri,
    subjectRef: "github:user:round45",
    providerCodeRef: "provider-ref:github/code/round45",
    authKeyId: "key_http_round45_ts",
  });
  const checkout = await client.billingCheckoutPlanHttp(tenantId, projectId, {
    customerRef: "cus_round45_ts",
    price: { lookup_key: "team", unit_amount_minor: 4500, currency: "usd" },
    successUrl: "https://app.ashr-clone.invalid/success",
    cancelUrl: "https://app.ashr-clone.invalid/cancel",
    providerConfig: { provider: "stripe", mode: "test", secret_ref: "env:STRIPE_TEST_REF" },
    usageRollup: { units: 45 },
    metadata: { round: 45 },
    idempotencyKey: "checkout_round45_ts",
    authKeyId: "key_http_round45_ts",
  });
  const portal = await client.billingPortalPlanHttp(tenantId, projectId, {
    customerRef: "cus_round45_ts",
    returnUrl: "https://app.ashr-clone.invalid/billing",
    providerConfig: { provider: "stripe", mode: "test", secret_ref: "env:STRIPE_TEST_REF" },
    idempotencyKey: "portal_round45_ts",
    authKeyId: "key_http_round45_ts",
  });
  const webhook = await client.billingWebhookIngestHttp(tenantId, projectId, {
    provider: "stripe",
    mode: "test",
    eventType: "invoice.paid",
    eventId: "evt_http_round45_ts",
    payloadSha256: "a".repeat(64),
    signatureHeaderPresent: true,
    webhookSecretRef: "env:STRIPE_WEBHOOK_REF_TEST",
    customerRef: "cus_round45_ts",
    amountMinor: 4500,
    currency: "usd",
    invoiceRef: "in_round45_ts",
    usageUnits: 45,
    metadata: { round: 45 },
    authKeyId: "key_http_round45_ts",
  });

  assert.equal(configured.operation, "configure_oauth_provider");
  assert.equal(begun.operation, "oauth_authorization_begin");
  assert.equal(completed.operation, "oauth_authorization_complete");
  assert.equal(checkout.operation, "billing_checkout_plan");
  assert.equal(portal.operation, "billing_portal_plan");
  assert.equal(webhook.operation, "billing_webhook_ingest");

  for (const call of calls) {
    const keys = Object.keys(call.body);
    assert.deepEqual(keys.filter((key) => /[A-Z]/u.test(key)), [], `${call.path} leaked camelCase keys`);
  }
  assert.deepEqual(calls[0].body.redirect_uris, [redirectUri]);
  assert.equal(calls[1].body.code_verifier, verifier);
  assert.equal(calls[2].body.provider_code_ref, "provider-ref:github/code/round45");
  assert.equal(calls[3].body.customer_ref, "cus_round45_ts");
  assert.equal(calls[3].body.success_url, "https://app.ashr-clone.invalid/success");
  assert.equal(calls[4].body.return_url, "https://app.ashr-clone.invalid/billing");
  assert.equal(calls[5].body.signature_header_present, true);
  assert.equal(calls[5].body.payload_sha256, "a".repeat(64));
});

test("round45_ts typed API key, quota, trace, artifact, and webhook clients preserve real behavior", () => {
  const service = bootstrap();
  service.cloud.createDataset(tenantId, projectId, {
    datasetId: "dataset_round45_ts",
    name: "Round 45",
    cases: [{ id: "case-round45-ts", prompt: "typed parity" }],
  });
  const client = new SaaSIngestionClient({ service });
  const created = client.createApiKey(tenantId, projectId, {
    name: "Round 45 writer",
    scopes: ["sdk:submit", "trace:ingest", "artifact:upload", "evidence:read", "usage:read"],
    keyId: "key_round45_ts",
    revealSecret: true,
  });
  assert.equal(created.operation, "create_api_key");
  assert.equal(created.result.key_id, "key_round45_ts");
  assert.equal(created.result.one_time_secret_displayed, true);

  const listed = client.listApiKeys(tenantId, projectId);
  assert.equal(listed.operation, "list_api_keys");
  assert.equal(listed.result.api_keys[0].secret_value_present, false);
  const verified = client.verifyApiKeySecret(tenantId, projectId, {
    keyId: "key_round45_ts",
    secret: created.result.one_time_secret,
    scope: "sdk:submit",
  });
  assert.equal(verified.operation, "verify_api_key_secret");
  assert.equal(verified.result.authenticated, true);

  const submitted = client.sdkSubmit(tenantId, projectId, {
    datasetId: "dataset_round45_ts",
    agentRef: "round45-ts-agent",
    runId: "run_round45_ts",
    apiKeyId: "key_round45_ts",
  });
  assert.equal(submitted.result.run.run_id, "run_round45_ts");
  const trace = client.ingestTrace(
    tenantId,
    projectId,
    "run_round45_ts",
    [{ observation_id: "obs_round45_ts", type: "agent_message" }],
    { batchId: "trace_round45_ts", apiKeyId: "key_round45_ts" },
  );
  assert.equal(trace.operation, "ingest_trace");
  assert.deepEqual(trace.result.observation_ids, ["obs_round45_ts"]);

  const artifact = client.createArtifactManifest(
    tenantId,
    projectId,
    "run_round45_ts",
    { schema_version: "ashr.clone.artifact_manifest.v1", files: [{ name: "trace.json", sha256: "b".repeat(64) }] },
    { artifactId: "artifact_round45_ts", apiKeyId: "key_round45_ts" },
  );
  assert.equal(artifact.operation, "artifact_manifest");
  assert.equal(artifact.result.artifact_id, "artifact_round45_ts");
  assert.equal(artifact.result.raw_manifest_included, false);
  const artifacts = client.listArtifactManifests(tenantId, projectId, "run_round45_ts", { authKeyId: "key_round45_ts" });
  assert.equal(artifacts.operation, "artifact_manifests");
  assert.equal(artifacts.result.artifact_manifests.length, 1);

  const quota = client.quotaSnapshot(tenantId, projectId, { authKeyId: "key_round45_ts" });
  assert.equal(quota.operation, "quota_snapshot");
  assert.equal(quota.result.totals["trace.ingest"], 1);
  assert.equal(quota.result.quota.used["artifact.manifest"], 1);

  const webhookBase = {
    provider: "stripe",
    mode: "test",
    eventType: "invoice.paid",
    eventId: "evt_round45_ts",
    signatureHeaderPresent: true,
    webhookSecretRef: "env:STRIPE_WEBHOOK_REF_TEST",
    customerRef: "cus_round45_ts",
    amountMinor: 4500,
    currency: "usd",
  };
  const accepted = client.billingWebhookIngest(tenantId, projectId, { ...webhookBase, payloadSha256: "c".repeat(64) });
  const duplicate = client.billingWebhookIngest(tenantId, projectId, { ...webhookBase, payloadSha256: "c".repeat(64) });
  const conflict = client.billingWebhookIngest(tenantId, projectId, { ...webhookBase, payloadSha256: "d".repeat(64) });
  assert.equal(accepted.result.ingest_status, "accepted");
  assert.equal(accepted.result.ledger_mutation_count, 1);
  assert.equal(duplicate.result.ingest_status, "duplicate");
  assert.equal(duplicate.result.ledger_mutation_count, 0);
  assert.equal(conflict.result.ingest_status, "conflict");
  assert.equal(conflict.result.ledger_mutation_count, 0);
});

test("round45_ts CLI completes OAuth provider, begin, and complete workflow", async () => {
  const tempDir = await mkdtemp(path.join(tmpdir(), "ashr-round45-ts-cli-"));
  const statePath = path.join(tempDir, "state.json");
  const cli = (...args) => {
    const child = spawnSync(process.execPath, ["dist/saas.js", ...args], {
      cwd: path.resolve("."),
      encoding: "utf8",
    });
    assert.equal(child.status, 0, child.stderr);
    return JSON.parse(child.stdout);
  };

  cli(
    "--state-output", statePath,
    "bootstrap",
    "--tenant-name", "Round 45 TS",
    "--project-name", "Parity",
    "--tenant-id", tenantId,
    "--project-id", projectId,
  );
  const configured = cli(
    "--state-input", statePath,
    "--state-output", statePath,
    "oauth-provider-configure",
    "--tenant-id", tenantId,
    "--project-id", projectId,
    "--provider", "github",
    "--client-id-ref", "env:GITHUB_CLIENT_ID",
    "--client-secret-ref", "env:GITHUB_CLIENT_SECRET",
    "--redirect-uri", redirectUri,
    "--scope", "read:user",
    "--config-id", "oauthcfg_cli_round45_ts",
  );
  const begun = cli(
    "--state-input", statePath,
    "--state-output", statePath,
    "oauth-authorization-begin",
    "--tenant-id", tenantId,
    "--project-id", projectId,
    "--provider-config-id", configured.result.config_id,
    "--redirect-uri", redirectUri,
    "--code-verifier", verifier,
    "--state", oauthState,
  );
  const completed = cli(
    "--state-input", statePath,
    "--state-output", statePath,
    "oauth-authorization-complete",
    "--tenant-id", tenantId,
    "--project-id", projectId,
    "--flow-id", begun.result.flow_id,
    "--redirect-uri", redirectUri,
    "--code-verifier", verifier,
    "--state", oauthState,
    "--subject-ref", "github:user:round45",
    "--provider-code-ref", "provider-ref:github/code/round45",
  );

  assert.equal(configured.operation, "configure_oauth_provider");
  assert.equal(begun.operation, "oauth_authorization_begin");
  assert.equal(completed.operation, "oauth_authorization_complete");
  assert.equal(completed.result.accepted, true);
});
