# Round47 China Payment Worker Runtime

Date: 2026-07-10

## Scope

This round adds self-host runtime wiring for WeChat Pay and Alipay payment
webhook ingestion, domestic bank acquirer events, and daily bill
reconciliation. It does not contain provider credentials, card data, OTP or
challenge data, call provider APIs, or enable Stripe by default.

## Runtime contract

- `china-payment-webhook-worker` leases only
  `china_payment_webhook_ingestion` jobs.
- `china-payment-reconciliation-worker` leases only
  `china_payment_bill_reconciliation` jobs.
- `china-bank-acquirer-worker` leases only `china_bank_acquirer_events` jobs.
  Its runtime mode is `hosted-token-reference-only`; the lane accepts merchant,
  hosted-origin, session-token, and signing-key references only.
- `stripe-payment-worker` is retained in the separate `stripe-payments`
  profile. Its configuration and worker branch remain available, but
  `ASHR_STRIPE_ENABLED=false` is the explicit default. In that state the
  entrypoint reports `disabled`, emits heartbeats, and does not execute the
  worker binary or consume Stripe jobs.
- Each lane has an explicit retry sequence, maximum attempt count, and named
  dead-letter queue. The durable worker repository remains responsible for the
  terminal `dead_lettered` state when the attempt budget is exhausted.
- Worker readiness validates Postgres mode, env-reference-only provider
  configuration, provider family and queue identity, disabled provider egress,
  the explicit Stripe disabled state, and the object-store hash evidence path.
- Worker heartbeat and readiness files are separate per lane.
- `china-payment-reconciliation-scheduler` enqueues the previous UTC billing
  date after `02:15` UTC. The job ID is deterministic, and
  `ON CONFLICT ... DO NOTHING` makes repeated scheduler ticks idempotent.
- Reconciliation evidence is configured under
  `evidence/a1/self-host/china-payments/sha256`; tracked runtime configuration
  carries hashes and reference names, not raw webhook bodies, bills, keys, or
  certificates.

## Provider boundaries

The tracked environment includes reference names for:

- WeChat Pay merchant ID, API v3 key, merchant private key, and platform
  certificate.
- Alipay app ID, app private key, and Alipay public key.
- Domestic acquirer merchant ID, hosted origin, session token, and signing key.
- Optional Stripe secret and webhook references for compatibility.

Compose contract tests treat profiles as extensible capability sets: the API
must retain the `api` and `commercial` baseline while also advertising the
isolated `china-payments` and `stripe-payments` entrypoints. The generic worker
retains `worker`, `daemon`, and `commercial`; it is deliberately not enrolled
in either payment profile because the dedicated payment workers own those
queues.

The literal provider environment names may appear only as the target of
`ASHR_STRIPE_SECRET_KEY_REF` and `ASHR_STRIPE_WEBHOOK_SECRET_REF`. Tests reject
direct `ASHR_STRIPE_SECRET_KEY` or `ASHR_STRIPE_WEBHOOK_SECRET` Compose keys and
reject assignments in the tracked env example. This keeps Stripe compatibility
without creating a tracked credential injection path.

The domestic acquirer lane does not define PAN, card number, cardholder,
expiry, CVV/CVC, OTP, one-time-password, or SMS challenge fields. Hosted
collection and token/reference handoff are the boundary.

`ASHR_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED=false` is enforced for the China
wallet and domestic acquirer families. The Stripe branch requires the hosted
checkout reference mode and treats every value other than explicit `true` as
the disabled path; that path also asserts the resolved default is `false`. The
generic Go worker handles durable jobs without provider HTTP calls.

## Verification commands

```powershell
$tests = Get-ChildItem tests/a1/test_china_payment_runtime*.py | ForEach-Object { $_.FullName }
python -m pytest @tests -q
docker compose -f infra/docker/docker-compose.self-host.yml --profile china-payments config --quiet
docker compose -f infra/docker/docker-compose.self-host.yml --profile stripe-payments config --quiet
wsl -d Ubuntu-24.04-Ashr --exec /bin/sh -n /mnt/c/Users/33516/Documents/Ashr_a1_clean_rebase/services/runner/china-payment-worker-entrypoint.sh
wsl -d Ubuntu-24.04-Ashr --exec /bin/sh -n /mnt/c/Users/33516/Documents/Ashr_a1_clean_rebase/services/runner/china-payment-worker-healthcheck.sh
```

Observed on 2026-07-10:

- Focused runtime and self-host Compose suite: `18 passed in 7.13s`.
- Worker entrypoint shell syntax: passed.
- Worker healthcheck shell syntax: passed.
- China payment Compose profile static render: passed.
- Stripe payment Compose profile static render: passed.
- Commercial Compose profile static render: passed.

No live provider command is part of this evidence round. Retry-delay and named
dead-letter values are lane policy metadata; producers must enqueue the
configured `max_attempts`, while the durable worker repository owns terminal
dead-letter state transitions.
