# A1 Payment Provider Readiness

This packet defines the public-safe A1 payment-provider readiness contract for Stripe, hosted WeChat Pay, and hosted Alipay. It is evidence for integration readiness, not evidence of live money movement. The repository may build provider plans and hash-only webhook envelopes, but it must not call payment APIs, create live checkout sessions, submit wallet payments, or store payment credentials.

Machine-readable evidence lives in `docs/a1/evidence/payment_provider_readiness_public.json` and is validated by `tests/a1/test_payment_provider_readiness_docs.py` against `docs/a1/schemas/payment_provider_readiness.schema.json`.

## Safety Boundary

- Public A1 evidence is contract-only: provider modes, hosted surfaces, object references, secret references, hash envelopes, and object evidence paths.
- Test and live provider secrets are references only, using prefixes such as `env:`, `vault:`, `kms:`, `provider-ref:`, or `dashboard-ref:`.
- Every provider rail requires `secret_ref` indirection in test and live. Verified webhook evidence requires `webhook_secret_ref` indirection and provider-specific signature/header shape validation.
- Raw provider secrets, private keys, webhook signing secrets, raw webhook payloads, card PAN, CVC, OTPs, identity documents, and buyer wallet credentials are forbidden in public docs and tests.
- CI and automated tests must not make real provider calls. The billing code must continue to emit `provider_called: false`, `checkout_or_portal_called: false`, and `real_charge_possible: false` for generated plans.
- Any real provider capture belongs under `docs/evidence/private_refs`, and public docs may point to that path shape without committing the private object.

## Provider Readiness Matrix

| Provider | Modes | Hosted surface | Allowed methods | Required webhook headers | Public evidence status |
| --- | --- | --- | --- | --- | --- |
| Stripe | `test`, `live` | Stripe-hosted Checkout and Billing Portal plans | `card`, `alipay`, `wechat_pay` | `stripe-signature` | Ready as plan-only evidence |
| WeChat Pay | `test`, `live` | Hosted/NATIVE QR provider handoff contract | `wechat_pay` | `wechatpay-signature`, `wechatpay-timestamp`, `wechatpay-nonce`, `wechatpay-serial` | Ready as plan-only evidence |
| Alipay | `test`, `live` | Hosted trade page/provider handoff contract | `alipay` | `sign`, `sign_type`, `app_id`, `trade_no` | Ready as plan-only evidence |

## Provider Rail Contracts

The public readiness packet includes a `provider_mode_matrix` for Stripe, WeChat Pay, and Alipay. Each entry records supported modes, hosted surface, allowed payment methods, `secret_ref` policy, `webhook_secret_ref` policy, required webhook header names, `requires_live_mode_ack: true`, `test_live_boundary_enforced: true`, `raw_secret_values_allowed: false`, and `raw_card_data_allowed: false`.

Provider configs must use approved reference prefixes for `secret_ref`, `webhook_secret_ref`, and account references. The billing contract rejects raw provider keys, unsupported payment methods, missing secret references, live-mode plans without `live_mode_ack`, and test/live webhook boundary crossings.

## Stripe Test And Live

Stripe test readiness is covered by hosted Checkout and Billing Portal plan contracts. The public plan may include price lookup keys, amount/currency, redirect URLs, customer references, idempotency keys, allowed payment method names, provider mode boundary fields, and usage rollups. It must not include raw API keys, client secrets, card numbers, or raw provider responses.

Stripe live readiness is limited to a control boundary: `live_mode_ack` must be explicit in the provider config, secrets must be referenced indirectly, redirect URLs must be HTTPS, and execution must be a human-controlled operational run outside CI. Public evidence may record dashboard object references and hash envelopes, but not raw live payloads or card details.

## Commercial Auth And Payment Safety Increment

The local control plane now models non-live commercial auth/payment safety records for GitHub OAuth, Google OAuth, payment provider configuration, and payment mode-boundary envelopes. These records are configuration and evidence only: they do not call GitHub, Google, Stripe, WeChat Pay, Alipay, or Ashr hosted APIs.

OAuth provider records store `client_id_ref`, `client_secret_ref`, redirect URIs, scopes, and provider names for `github` and `google`. OAuth session records store provider subject references and optional token references only. Payment provider records store `secret_ref`, `webhook_secret_ref`, `account_ref`, mode, `live_mode_ack`, and `live_mode_enabled: false`. Boundary records reuse the hash-only webhook envelope contract and preserve `provider_called: false`, `checkout_or_portal_called: false`, and `real_charge_possible: false`.

API-key lifecycle safety is linked to these records through scoped keys and per-operation rate-limit buckets for configuration writes. Public snapshots expose key IDs and rate-limit counters, but never raw API keys, OAuth tokens, client secrets, provider secrets, card data, or raw webhook payloads.

## Hosted WeChat Pay And Alipay

WeChat Pay and Alipay readiness is scoped to hosted provider handoff contracts. A1 may document provider mode, merchant/application reference, hosted payment method, amount/currency, event type mapping, required webhook header names, and hash-only webhook envelope shape. It must not store merchant private keys, API keys, certificates, access tokens, buyer identity data, wallet credentials, or raw provider notification bodies.

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
```

The test validates the JSON schema, checks provider coverage, checks that public object paths remain under the allowed public A1 locations, and scans the public docs/evidence/schema files for forbidden secret, card, and real-payment markers.
