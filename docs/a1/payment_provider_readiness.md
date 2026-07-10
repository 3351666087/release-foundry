# A1 Payment Provider Readiness

This packet defines the public-safe A1 payment-provider readiness contract for
China-first hosted WeChat Pay, hosted Alipay, domestic bank-card acquiring by
opaque provider reference, and retained Stripe compatibility. It is evidence
for integration readiness, not evidence of live money movement. The repository
may build provider plans and hash-only webhook envelopes, but it must not call
payment APIs, create live checkout sessions, submit wallet payments, accept
real cards, or store payment credentials.

Machine-readable evidence lives in `docs/a1/evidence/payment_provider_readiness_public.json` and is validated by `tests/a1/test_payment_provider_readiness_docs.py` against `docs/a1/schemas/payment_provider_readiness.schema.json`.

## Safety Boundary

- Public A1 evidence is contract-only: provider modes, hosted surfaces, object references, secret references, hash envelopes, and object evidence paths.
- Test and live provider secrets are references only, using prefixes such as `env:`, `vault:`, `kms:`, `provider-ref:`, or `dashboard-ref:`.
- Every provider rail requires `secret_ref` indirection in test and live. Verified webhook evidence requires `webhook_secret_ref` indirection and provider-specific signature/header shape validation.
- Raw provider secrets, private keys, webhook signing secrets, raw webhook payloads, card PAN, CVC, OTPs, identity documents, and buyer wallet credentials are forbidden in public docs and tests.
- CI and automated tests must not make real provider calls. The billing code must continue to emit `provider_called: false`, `checkout_or_portal_called: false`, and `real_charge_possible: false` for generated plans.
- Any real provider capture belongs under `docs/evidence/private_refs`, and public docs may point to that path shape without committing the private object.
- Domestic bank-card support is `plan_only`. The only admissible values are
  acquirer-hosted session references, opaque acquirer tokens, and opaque
  provider references bound to tenant, project, merchant application,
  acquirer account, and mode.
- PAN, primary account number, expiry, CVC/CVV, PIN, OTP, track data,
  cryptograms, cardholder data, bank credentials, and KYC documents are not
  A1 payloads. They are rejected rather than redacted and must never enter API
  bodies, queues, databases, traces, logs, fixtures, evidence, or prompts.

## Provider Readiness Matrix

| Provider | Modes | Hosted surface | Allowed methods | Required webhook headers | Public evidence status |
| --- | --- | --- | --- | --- | --- |
| Stripe | `test`, `live` | Stripe-hosted Checkout and Billing Portal plans | `card`, `alipay`, `wechat_pay` | `stripe-signature` | Ready as plan-only evidence |
| WeChat Pay | `test`, `live` | Hosted/NATIVE QR provider handoff contract | `wechat_pay` | `wechatpay-signature`, `wechatpay-timestamp`, `wechatpay-nonce`, `wechatpay-serial` | Ready as plan-only evidence |
| Alipay | `test`, `live` | Hosted trade page/provider handoff contract | `alipay` | `sign`, `sign_type`, `app_id`, `trade_no` | Ready as plan-only evidence |
| Domestic bank-card acquirer | `test`, `live` | Acquirer-hosted/token/reference-only contract | `domestic_bank_card` | Acquirer-specific; no generic verification claim | Disabled plan-only scaffold; acquirer and merchant activation required |

All rows currently retain `real_provider_calls=false`,
`real_card_acceptance=false`, `merchant_application_started=false`,
`kyc_started=false`, and `live_money_activation=false`.

## China-First Domestic Card Boundary

A1 does not become a card-data environment. A future domestic-card rail must
select a licensed acquirer and keep the payment UI, card collection, challenge,
and credential handling entirely on that acquirer's hosted surface. A1 may
receive only a bounded opaque reference after the acquirer has completed its
own security controls.

An opaque reference is actionable only when its trusted provenance binds:

`tenant + project + merchant_application + provider + acquirer_account + mode + issuer + created_at + expires_at + revocation_state`

The current implementation is disabled integration infrastructure. It has no
merchant application, KYC approval, production certificate, trusted
provider-specific callback verifier, live acquiring evidence, or real-card
acceptance path. Public reconciliation routes remain receive/list/get only;
verification and money-state transitions are worker-internal and must consume a
future process-internal cryptographic verification artifact.

## Provider Rail Contracts

The public readiness packet includes a `provider_mode_matrix` for Stripe, WeChat Pay, and Alipay. Each entry records supported modes, hosted surface, allowed payment methods, `secret_ref` policy, `webhook_secret_ref` policy, required webhook header names, `requires_live_mode_ack: true`, `test_live_boundary_enforced: true`, `raw_secret_values_allowed: false`, and `raw_card_data_allowed: false`.

Provider configs must use approved reference prefixes for `secret_ref`, `webhook_secret_ref`, and account references. The billing contract rejects raw provider keys, unsupported payment methods, missing secret references, live-mode plans without `live_mode_ack`, and test/live webhook boundary crossings.

Round 45 adds independent adapter contracts in `services/api/payment_providers.py`. These adapters do not import provider SDKs and cannot perform network I/O. They emit deterministic hosted-payment request shapes, require caller-supplied idempotency keys, bind each key to a request fingerprint, and expose `HostedPaymentExecutor` only as an external integration interface. Secret resolution is deferred to that external boundary.

Live Stripe, WeChat Pay, and Alipay plans require both an explicit `live_mode_ack` and a `live_execution_gate_ref` pointing to an approved operational gate. Possessing those fields still does not execute a payment: every adapter result keeps `adapter_can_execute: false`, `provider_called: false`, `checkout_or_portal_called: false`, `real_charge_possible: false`, and `network_io_performed: false`.

## Stripe Test And Live

Stripe test readiness is covered by hosted Checkout and Billing Portal plan contracts. The public plan may include price lookup keys, amount/currency, redirect URLs, customer references, idempotency keys, allowed payment method names, provider mode boundary fields, and usage rollups. It must not include raw API keys, client secrets, card numbers, or raw provider responses.

Stripe live readiness is limited to a control boundary: `live_mode_ack` must be explicit in the provider config, secrets must be referenced indirectly, redirect URLs must be HTTPS, and execution must be a human-controlled operational run outside CI. Public evidence may record dashboard object references and hash envelopes, but not raw live payloads or card details.

The Stripe adapter requires a stable idempotency key for every Checkout or Billing Portal creation plan. It records a SHA-256 request fingerprint so a future executor can reject reuse of a key with changed parameters. Stripe webhook integration passes the exact raw request bytes, signature header values, mode expectation, and webhook verification-key reference to an injected `PaymentSignatureVerifier`; the returned public envelope retains only the payload digest, header names, provider event references, mode result, and reason codes.

## Commercial Auth And Payment Safety Increment

The local control plane now models non-live commercial auth/payment safety records for GitHub OAuth, Google OAuth, payment provider configuration, and payment mode-boundary envelopes. These records are configuration and evidence only: they do not call GitHub, Google, Stripe, WeChat Pay, Alipay, or Ashr hosted APIs.

OAuth provider records store `client_id_ref`, `client_secret_ref`, redirect URIs, scopes, and provider names for `github` and `google`. OAuth session records store provider subject references and optional token references only. Payment provider records store `secret_ref`, `webhook_secret_ref`, `account_ref`, mode, `live_mode_ack`, and `live_mode_enabled: false`. Boundary records reuse the hash-only webhook envelope contract and preserve `provider_called: false`, `checkout_or_portal_called: false`, and `real_charge_possible: false`.

API-key lifecycle safety is linked to these records through scoped keys and per-operation rate-limit buckets for configuration writes. Public snapshots expose key IDs and rate-limit counters, but never raw API keys, OAuth tokens, client secrets, provider secrets, card data, or raw webhook payloads.

`services/api/oauth_providers.py` supplies static Google and GitHub provider metadata plus pure PKCE/state/token-reference helpers. Authorization plans require S256 PKCE, store only a state digest and state reference, and defer client-ID/state resolution to an external redirect executor. Callback validation compares state in constant time and drops the authorization-code reference on mismatch. Token exchange plans and session records contain only client, code-verifier, authorization-code, subject, access-token, refresh-token, and ID-token references; they contain no token values and perform no provider calls.

Google endpoint metadata is paired with its OpenID Connect discovery-document URI so a future executor can refresh and cache metadata according to provider policy. GitHub metadata records its authorization, token, and user API endpoints and requires S256 PKCE plus state matching. The adapter metadata is an integration default, not evidence that discovery or authorization was performed.

## Hosted WeChat Pay And Alipay

WeChat Pay and Alipay readiness is scoped to hosted provider handoff contracts. A1 may document provider mode, merchant/application reference, hosted payment method, amount/currency, event type mapping, required webhook header names, and hash-only webhook envelope shape. It must not store merchant private keys, API keys, certificates, access tokens, buyer identity data, wallet credentials, or raw provider notification bodies.

The Round 45 wallet adapter accepts only CNY minor-unit amounts and HTTPS return/notification URLs. WeChat Pay plans target a NATIVE QR handoff; Alipay plans target a hosted trade-page handoff. Notification verification is delegated to the same `PaymentSignatureVerifier` protocol with provider-specific required header names. The verifier may receive raw bytes transiently, but neither the plan nor the result envelope serializes raw bodies, header values, or key material.

## Real-Card Human-Controlled Testing

Real-card testing is allowed only as a manually operated release-readiness activity outside CI. Automation must stop before a card, wallet, OTP, identity, or other payment credential is entered. A live real-card check requires pre-approval, the smallest practical amount, immediate void/refund handling where available, and private evidence storage.

Public evidence from a real-card check may include operator initials or reviewer handle, provider dashboard object reference, mode label, public price amount/currency, coarse timestamp, hash envelope path, and refund or void object reference. Public evidence must not include card PAN, CVC, raw receipt payloads, screenshots with card details, payer identity documents, or provider secrets.

## Webhook Hash Envelopes

Webhook readiness evidence uses envelopes rather than raw payloads. Each envelope records provider, mode, event type, event object reference, payload SHA-256, signature-header presence, expected/provided header names, missing-header list, webhook secret reference, test/live boundary flags, verification result, object evidence ref, and object evidence path. Raw payloads, raw header values, and secret values are marked absent.

Expected private path shape:

```text
docs/evidence/private_refs/payments/{provider}/{mode}/{object}.hash-envelope.json
docs/evidence/private_refs/payments/{provider}/{mode}/{object}.operator-note.md
```

The public packet includes only this path shape and sample object references. It does not create private payment evidence files.

## Validation

Run the docs/evidence validation test after modifying this packet:

```powershell
python -B -m pytest tests/a1/test_payment_provider_readiness_docs.py -q -p no:cacheprovider
python -B -m pytest tests/a1/test_round45_provider_adapters.py -q -p no:cacheprovider
```

The tests validate the JSON schema, provider coverage, public object paths, forbidden secret/payment markers, explicit live gates, idempotency fingerprints, raw-body verifier hooks, hosted wallet plans, OAuth metadata, S256 PKCE, state mismatch handling, and token-reference-only envelopes.
