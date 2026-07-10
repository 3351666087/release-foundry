import assert from "node:assert/strict";
import test from "node:test";

import {
  OAuthProviderContractError,
  OAuthReplayLedger,
  buildAuthorizationEnvelope,
  derivePkceS256,
  hashOAuthNonce,
  hashOAuthState,
  oauthProviderContractManifest,
  verifyCallbackIdentity,
  verifyCallbackState,
} from "../dist/oauth.js";

const issuer = {
  github: "https://github.com",
  google: "https://accounts.google.com",
  wechat: "https://open.weixin.qq.com",
  alipay: "https://openauth.alipay.com",
};

function config(provider, options = {}) {
  const environment = options.environment ?? "sandbox";
  return {
    provider,
    clientIdRef: `env:${provider.toUpperCase()}_${environment.toUpperCase()}_CLIENT_ID_REF`,
    clientSecretRef: `vault:oauth/${environment}/${provider}/client-secret`,
    redirectUri: `https://auth.ashr-clone.invalid/${environment}/${provider}/callback`,
    redirectAllowlist: [`https://auth.ashr-clone.invalid/${environment}/${provider}/callback`],
    scopes: provider === "google" ? ["openid", "email"] : ["account_identity"],
    environment,
    enabled: options.enabled ?? false,
    issuerAllowlist: [issuer[provider]],
    audienceAllowlist: provider === "github" ? [] : [`${provider}-application-id`],
  };
}

test("TS OAuth registry matches Python four-provider account-ready controls", () => {
  const manifest = oauthProviderContractManifest();
  assert.deepEqual(Object.keys(manifest.providers), ["alipay", "github", "google", "wechat"]);
  assert.deepEqual(manifest.environments, ["sandbox", "live"]);
  assert.equal(manifest.required_controls.pkce_method, "S256");
  assert.equal(manifest.required_controls.nonce_hash_only, true);
  assert.equal(manifest.required_controls.redirect_exact_allowlist, true);
  assert.equal(manifest.required_controls.sandbox_live_separation, true);
  assert.equal(manifest.required_controls.callback_replay_protection, true);
  assert.equal(manifest.required_controls.disabled_by_default, true);
});

for (const provider of ["github", "google", "wechat", "alipay"]) {
  test(`TS ${provider} authorization envelope is PKCE/state/redirect/environment bound`, () => {
    const verifier = "V".repeat(64);
    const state = `state-${provider}-account-ready-20260710`;
    const nonce = `nonce-${provider}-account-ready-20260710`;
    const nonceOptions = provider === "google" ? {
      nonceRef: "vault:oauth/sandbox/google/nonce/attempt-1",
      nonceSha256: hashOAuthNonce(nonce).nonce_sha256,
    } : {};
    const envelope = buildAuthorizationEnvelope({
      config: config(provider),
      stateRef: `vault:oauth/sandbox/${provider}/state/attempt-1`,
      stateSha256: hashOAuthState(state).state_sha256,
      pkceCodeChallenge: derivePkceS256(verifier).code_challenge,
      ...nonceOptions,
    });
    const serialized = JSON.stringify(envelope);
    assert.equal(envelope.provider, provider);
    assert.equal(envelope.environment, "sandbox");
    assert.equal(envelope.enabled, false);
    assert.equal(envelope.ready, false);
    assert.equal(envelope.parameters.code_challenge_method, "S256");
    assert.equal(envelope.executor_contract.network_io_performed, false);
    assert.equal(serialized.includes(state), false);
    assert.equal(serialized.includes(nonce), false);
    assert.equal(serialized.includes(verifier), false);
  });
}

test("TS callback identity validates issuer audience nonce subject and account binding", () => {
  const nonce = "nonce-google-account-binding-20260710";
  const base = {
    issuer: issuer.google,
    audience: "google-application-id",
    subject: "google-subject-123",
    accountBindingRef: "provider-ref:google/account/123",
    expectedAccountBindingRef: "provider-ref:google/account/123",
    receivedNonce: nonce,
    expectedNonceSha256: hashOAuthNonce(nonce).nonce_sha256,
  };
  const disabled = verifyCallbackIdentity({ config: config("google"), ...base });
  const accepted = verifyCallbackIdentity({ config: config("google", { enabled: true }), ...base });
  const rejected = verifyCallbackIdentity({
    config: config("google", { enabled: true }),
    ...base,
    issuer: "https://issuer.invalid",
    audience: "wrong-audience",
    accountBindingRef: "provider-ref:google/account/attacker",
    receivedNonce: "wrong-nonce-account-binding",
  });
  assert.deepEqual(disabled.failure_reasons, ["provider_disabled"]);
  assert.equal(accepted.accepted, true);
  assert.equal(accepted.raw_subject_present, false);
  assert.equal(accepted.raw_nonce_present, false);
  assert.deepEqual(rejected.failure_reasons, [
    "issuer_mismatch", "audience_mismatch", "nonce_mismatch", "account_binding_mismatch",
  ]);
  assert.equal(rejected.issuer, null);
  assert.equal(rejected.account_binding_ref, null);
});

test("TS callback replay ledger scopes one-time keys by provider and environment", () => {
  const ledger = new OAuthReplayLedger();
  const state = "state-callback-replay-account-ready";
  const base = {
    receivedState: state,
    expectedStateSha256: hashOAuthState(state).state_sha256,
    authorizationCodeRef: "vault:oauth/codes/attempt-1",
    replayKey: "callback-event-account-ready-0001",
    replayLedger: ledger,
    provider: "wechat",
  };
  const first = verifyCallbackState({ ...base, environment: "sandbox" });
  const replay = verifyCallbackState({ ...base, environment: "sandbox" });
  const live = verifyCallbackState({ ...base, environment: "live" });
  assert.equal(first.accepted, true);
  assert.equal(replay.accepted, false);
  assert.deepEqual(replay.failure_reasons, ["callback_replay"]);
  assert.equal(replay.authorization_code_ref, null);
  assert.equal(live.accepted, true);
  assert.deepEqual(ledger.publicSnapshot(), {
    consumed_digest_count: 2, raw_replay_keys_present: false,
  });
});

test("TS OAuth config rejects cross-environment redirects insecure localhost and raw secrets", () => {
  assert.throws(() => buildAuthorizationEnvelope({
    config: {
      ...config("alipay"),
      redirectAllowlist: ["https://auth.ashr-clone.invalid/live/alipay/callback"],
    },
    stateRef: "vault:oauth/state/attempt-1",
    stateSha256: "a".repeat(64),
    pkceCodeChallenge: "b".repeat(43),
  }), OAuthProviderContractError);
  assert.throws(() => buildAuthorizationEnvelope({
    config: {
      ...config("github"), redirectUri: "http://localhost/oauth/callback",
      redirectAllowlist: ["http://localhost/oauth/callback"],
    },
    stateRef: "vault:oauth/state/attempt-1",
    stateSha256: "a".repeat(64),
    pkceCodeChallenge: "b".repeat(43),
  }), OAuthProviderContractError);
  assert.throws(() => buildAuthorizationEnvelope({
    config: { ...config("wechat"), clientSecretRef: "raw-secret-value" },
    stateRef: "vault:oauth/state/attempt-1",
    stateSha256: "a".repeat(64),
    pkceCodeChallenge: "b".repeat(43),
  }), OAuthProviderContractError);
});
