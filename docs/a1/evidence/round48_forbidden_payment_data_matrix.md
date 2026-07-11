# Round 48 Forbidden Payment Data Matrix

Date: 2026-07-10

Scope:

- `services/api/china_payments.py`
- `packages/ts/ashr-clone/src/china-payments.ts`
- Python and TypeScript China-payment tests

This is a public-safe contract record. It contains field aliases and synthetic
placeholders only. It contains no payment credentials, card numbers, security
codes, authentication codes, track data, cryptograms, or identity documents.

## Cross-layer rule

Python and TypeScript canonicalize camelCase, snake_case, kebab-case, and
space-separated keys before evaluating the same forbidden categories. Objects
and arrays are traversed recursively. A forbidden key at any depth rejects the
whole payment envelope before provider execution.

| Category | Representative aliases covered | Python | TypeScript |
| --- | --- | --- | --- |
| Account number | `pan`, `primaryAccountNumber`, `card-number`, `card no`, `account_number` | reject | reject |
| Expiration | `expiry`, `expirationDate`, `expMonth`, `expiry-year`, `valid thru` | reject | reject |
| Security code | `cvv`, `cvc`, `cvn`, `cid`, `security code`, `cardSecurityCode` | reject | reject |
| PIN | `pin`, `pin-block` | reject | reject |
| Out-of-band code | `otp`, `oneTimePassword`, `one-time-code`, `sms code`, `smsOtp` | reject | reject |
| Magnetic track | `track1`, `track-2`, `track data` | reject | reject |
| Cryptogram | `cryptogram`, `paymentCryptogram` | reject | reject |
| Cardholder data | `cardholder`, `cardHolderName`, `raw-cardholder-data` | reject | reject |
| KYC document/data | `kyc`, `kycDocs`, `raw kyc document` | reject | reject |

## Allowed handoff fields

The SDK may carry reference-only or redirect-only integration material:

- HTTPS hosted payment URL
- provider token reference
- opaque payment reference
- nested public status and sequence metadata

These values do not authorize either SDK to collect or persist raw cardholder
or KYC material. Provider execution remains outside this plan-only contract.

## Test shape

Each forbidden alias is tested at:

1. the metadata root;
2. a nested object;
3. an object inside an array.

Tests use `synthetic-sensitive-placeholder` as the value. No real payment data
is needed to prove key-based rejection.
