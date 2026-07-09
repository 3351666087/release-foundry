# A1 Payment Provider Readiness

This packet defines the public-safe A1 payment-provider readiness contract for Stripe, hosted WeChat Pay, and hosted Alipay. It is evidence for integration readiness, not evidence of live money movement. The repository may build provider plans and hash-only webhook envelopes, but it must not call payment APIs, create live checkout sessions, submit wallet payments, or store payment credentials.

Machine-readable evidence lives in `docs/a1/evidence/payment_provider_readiness_public.json` and is validated by `tests/a1/test_payment_provider_readiness_docs.py` against `docs/a1/schemas/payment_provider_readiness.schema.json`.

## Safety Boundary

- Public A1 evidence is contract-only: provider modes, hosted surfaces, object references, secret references, hash envelopes, and object evidence paths.
- Test and live provider secrets are references only, using prefixes such as `env:`, `vault:`, `kms:`, `provider-ref:`, or `dashboard-ref:`.
- Raw provider secrets, private keys, webhook signing secrets, raw webhook payloads, card PAN, CVC, OTPs, identity documents, and buyer wallet credentials are forbidden in public docs and tests.
- CI and automated tests must not make real provider calls. The billing code must continue to emit `provider_called: false`, `checkout_or_portal_called: false`, and `real_charge_possible: false` for generated plans.
- Any real provider capture belongs under `docs/evidence/private_refs`, and public docs may point to that path shape without committing the private object.

## Provider Readiness Matrix

| Provider | Modes | Hosted surface | Public secret references | Webhook evidence | Public evidence status |
| --- | --- | --- | --- | --- | --- |
| Stripe | `test`, `live` | Stripe-hosted Checkout and Billing Portal plans | `env:STRIPE_TEST_REF`, `env:STRIPE_LIVE_REF`, webhook refs by mode | SHA-256 envelope with signature-header presence and `webhook_secret_ref` | Ready as plan-only evidence |
| WeChat Pay | `test`, `live` | Hosted/NATIVE QR provider handoff contract | `vault:wechat/...` merchant and webhook refs | SHA-256 envelope for transaction-success class events | Ready as plan-only evidence |
| Alipay | `test`, `live` | Hosted trade page/provider handoff contract | `vault:alipay/...` app and webhook refs | SHA-256 envelope for trade-success class events | Ready as plan-only evidence |

## Stripe Test And Live

Stripe test readiness is covered by hosted Checkout and Billing Portal plan contracts. The public plan may include price lookup keys, amount/currency, redirect URLs, customer references, idempotency keys, payment method names, and usage rollups. It must not include raw API keys, client secrets, card numbers, or raw provider responses.

Stripe live readiness is limited to a control boundary: `live_mode_ack` must be explicit in the provider config, secrets must be referenced indirectly, redirect URLs must be HTTPS, and execution must be a human-controlled operational run outside CI. Public evidence may record dashboard object references and hash envelopes, but not raw live payloads or card details.

## Hosted WeChat Pay And Alipay

WeChat Pay and Alipay readiness is scoped to hosted provider handoff contracts. A1 may document provider mode, merchant/application reference, hosted payment method, amount/currency, event type mapping, and hash-only webhook envelope shape. It must not store merchant private keys, API keys, certificates, access tokens, buyer identity data, wallet credentials, or raw provider notification bodies.

## Real-Card Human-Controlled Testing

Real-card testing is allowed only as a manually operated release-readiness activity outside CI. Automation must stop before a card, wallet, OTP, identity, or other payment credential is entered. A live real-card check requires pre-approval, the smallest practical amount, immediate void/refund handling where available, and private evidence storage.

Public evidence from a real-card check may include operator initials or reviewer handle, provider dashboard object reference, mode label, public price amount/currency, coarse timestamp, hash envelope path, and refund or void object reference. Public evidence must not include card PAN, CVC, raw receipt payloads, screenshots with card details, payer identity documents, or provider secrets.

## Webhook Hash Envelopes

Webhook readiness evidence uses envelopes rather than raw payloads. Each envelope records provider, mode, event type, event object reference, payload SHA-256, signature-header presence, webhook secret reference, verification result, and an object evidence path. Raw payloads and secret values are marked absent.

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
