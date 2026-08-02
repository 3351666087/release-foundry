# A1 Worker SDK CLI OpenAPI Billing/Usage Parity Evidence

Generated: 2026-07-09

## Scope

- Python SDK/CLI exposes commercial billing commands for checkout planning, portal planning, webhook ingest, and ledger readback.
- TypeScript SDK/CLI exposes the same billing commands and keeps OpenAPI route parity for the shared commercial routes.
- Existing quota/readiness CLI surface remains available through `quota`, `usage`, release gate, audit chain verify, and release evidence commands.
- Shared operation contract fixture: `tests/a1/fixtures/billing_sdk_parity_contract.json`.

## Public Safety

- Billing checkout and portal commands build provider request plans only; they do not contact a payment provider.
- Webhook ingest accepts event metadata and `payload_sha256`; it does not accept or persist raw webhook payloads.
- Tests assert public outputs do not include forbidden fragments from the shared fixture: `sk_test`, `sk_live`, `whsec`, `4242 4242`, `api_key_secret`, or `bearer_api_key`.
- Local CLI state now persists only public-safe billing ledger records: ledger events, provider event summaries, billing accounts, and explicit `raw_payload_included=false` / `secret_value_present=false` flags.

## Focused Verification

```text
cd packages/ts/releasefoundry
npm run build
node --test test/billing-sdk-parity.test.mjs

Result: pass, 3 tests.
```

```text
python -m pytest -q tests/a1/test_saas_sdk_client.py

Result: pass, 15 tests.
```

```text
python -m pytest -q tests/a1/test_saas_control_plane_http.py

Result: pass, 5 tests.
```

Note: `pytest` was not available as a direct shell command in this environment, so `python -m pytest` was used.

## Covered Operations

| Operation | CLI command | Route |
| --- | --- | --- |
| `billing_checkout_plan` | `billing-checkout-plan` | `POST /v1/projects/{project_id}/billing/checkout-plan` |
| `billing_portal_plan` | `billing-portal-plan` | `POST /v1/projects/{project_id}/billing/portal-plan` |
| `billing_webhook_ingest` | `billing-webhook-ingest` | `POST /v1/projects/{project_id}/billing/webhooks/ingest` |
| `billing_ledger` | `billing-ledger` | `GET /v1/projects/{project_id}/billing/ledger` |

## Gaps

- No hosted payment-provider calls were made or added.
- No real secrets, raw payment data, or raw webhook payloads were used.
- Verification was focused on SDK/CLI/OpenAPI parity surfaces, not the full repository test suite.
