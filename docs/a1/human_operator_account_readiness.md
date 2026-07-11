# A1 Human Operator Account Readiness Board

Status: account onboarding plan and non-sensitive receipt contract only. This
board does not claim that any provider is activated, certified, or ready to
move money.

## Human Operator Rules

The user is the Human Operator for provider-owned account actions. Complete
identity checks, agreements, account logins, captchas, OTPs, key generation,
and credential storage only in the provider portal or an approved local secret
manager.

Report back only:

- provider and sandbox/production environment;
- application, merchant, or account identifier suffix (4-16 characters), or a
  locally computed `sha256:` fingerprint;
- exact registered redirect URIs;
- status and timezone-qualified timestamps;
- a non-sensitive provider receipt/reference ID and short status note.

Never report or commit client secrets, API keys, access/refresh tokens,
authorization codes, private keys, certificates containing private keys,
passwords, OTPs, PINs, PAN/card numbers, CVV/CVC, track data, cryptograms,
cardholder data, identity-document numbers, KYC files, business-license scans,
or screenshots containing those values.

## Task Board

### GitHub OAuth Login

- Official entry: <https://github.com/settings/developers> and GitHub's
  "Creating an OAuth app" documentation.
- Subject/materials: a GitHub personal account, or organization administrator
  access when the organization should own the app; public application name,
  homepage URL, optional public description.
- Domain/callback: register the full authorization callback URL. GitHub's
  official OAuth App documentation says an OAuth App has one callback URL;
  use separate apps where separate environment callbacks are required.
- Product/scopes: start with identity-only minimums such as `read:user` and
  request `user:email` only when verified email is required. GitHub recommends
  considering a GitHub App when fine-grained repository permissions or
  app-independent actions are needed.
- Boundary: development and production apps must have separate identifiers and
  secret storage. Do not put an internal or secret URL in public app metadata.
- Human receipt: app ID/client ID suffix or SHA-256 fingerprint, callback URI,
  owner type (`personal` or `organization`) in the note, status, timestamp.
- Next code step: store the client secret directly in the local secret manager,
  configure only its secret reference in A1, then run PKCE/state callback tests.

### Google OAuth Login

- Official entry: <https://console.cloud.google.com/auth/clients>; official web
  server OAuth guide:
  <https://developers.google.com/identity/protocols/oauth2/web-server>.
- Subject/materials: Google Cloud project, configured Google Auth Platform
  branding/audience, support contact, authorized domains, and test users when
  the app is not published.
- Domain/callback: authorized redirect URIs must exactly match, including
  scheme, case, path, and trailing slash. Google requires HTTPS except local
  test callbacks such as `http://localhost`.
- Product/scopes: begin with OIDC `openid email profile`. Additional sensitive
  or restricted API scopes can trigger verification and must not be requested
  until the product requires them.
- Boundary: keep testing audience/test users separate from production
  publishing and verification. Store downloaded credentials outside the repo.
- Human receipt: OAuth client ID suffix/fingerprint, exact redirect URIs,
  audience/publishing status in the note, environment, timestamp.
- Next code step: configure client ID reference and secret reference, then
  exercise exact-redirect, state, nonce, PKCE, revoke, and linking-conflict
  paths.

### WeChat Open Platform Login

- Official entry: <https://open.weixin.qq.com/>. The public page exposes
  registration, login, management center, account center, and resource center.
- Subject/materials: account registration and provider-side developer
  qualification are required. The exact current entity types, verification
  materials, review fee, and review SLA were not visible on the logged-out
  public page and must be confirmed by the Human Operator in the current
  console. Do not guess from historical requirements.
- Domain/callback: register only the production-owned website application
  authorization callback domain/URI shown by the current console. Confirm
  whether the selected product accepts a domain or a full URI before coding.
- Product/scopes: request the website/app WeChat Login product and only the
  identity scope displayed for that approved application.
- Boundary: no public sandbox capability was confirmed. Treat unapproved and
  approved applications as separate readiness states; never simulate approval.
- Human receipt: application ID suffix/fingerprint, application type, approved
  callback value, review status, timestamp, non-sensitive application receipt.
- Next code step: map the approved product's exact callback and scope into the
  provider adapter, then add state/code single-use and account-linking tests.

### Alipay Login

- Official entry: <https://open.alipay.com/>. Use the console's application
  creation and product-binding flow; public documentation and product names can
  change.
- Subject/materials: the exact entity qualification, application category,
  required agreements, and review materials depend on the selected application
  and product. The public logged-out page did not expose a stable complete
  checklist; the Human Operator must record the console's current requirement
  names without uploading the materials.
- Domain/callback: record the exact authorization callback URI configured for
  the application. Production callbacks must use an owned HTTPS domain.
- Product/scopes: select the current Alipay member authorization/login product
  in the console and report only the approved public scope names.
- Boundary: Alipay publishes sandbox notices, but sandbox availability and
  parity are product-specific. A sandbox approval is not production approval.
- Human receipt: app ID suffix/fingerprint, exact redirect URI, approved product
  and scopes in a non-sensitive note, environment/status/timestamp.
- Next code step: bind the approved scope names, RSA2 verification-key
  reference, state, replay, and account-link conflict tests.

### WeChat Pay Merchant

- Official entries: <https://pay.weixin.qq.com/> and the public merchant
  onboarding guide at
  <https://pay.weixin.qq.com/static/applyment_guide/applyment_index.shtml>.
  The public site currently exposes merchant onboarding and integration
  documentation.
- Subject/materials: choose the actual merchant entity and industry in the
  current onboarding guide. Legal representative/operator identity, settlement
  account, business qualification, store/site/app proof, and agreements may be
  requested based on that selection. Never send those materials to chat/repo.
- Domain/callback: after merchant approval, bind the approved AppID/product and
  register owned HTTPS notification URLs. Record only the URL and merchant/AppID
  suffixes.
- Products: request only channels required by the product, for example Native,
  JSAPI, H5, App, or Mini Program. Product availability depends on entity and
  business scenario.
- Boundary: account/application approval and API v3 credential configuration
  are production controls. Local fake-signature tests are not merchant sandbox
  certification.
- Human receipt: merchant ID suffix/fingerprint, bound AppID suffix/fingerprint,
  enabled channel names, notification URI, status/timestamp.
- Next code step: configure key/certificate references in secret storage, then
  run API v3 signature, platform-certificate rotation, replay, idempotency, and
  reconciliation tests before any payment.

### Alipay Merchant

- Official entries: <https://b.alipay.com/page/portal/home> and its public
  merchant onboarding guide:
  <https://b.alipay.com/page/portal/enter-guide/business-type>.
- Subject/materials: register/select the legal merchant entity and follow the
  current business-type guide. Exact licenses, settlement account, operator,
  industry, site/app, and agreement requirements are selection-dependent and
  must be confirmed in the authenticated portal.
- Domain/callback: configure owned HTTPS return and asynchronous notification
  URLs for the approved application/product; report URLs only.
- Products: request only required merchant payment products and channels. Do
  not infer approval from an application existing in the open platform.
- Boundary: sandbox notices exist, but sandbox objects, keys, gateways, and
  production merchant approval remain separate.
- Human receipt: merchant/app suffix or fingerprint, enabled product/channel
  names, callback URIs, environment/status/timestamp.
- Next code step: store RSA2 private material only in the secret manager,
  configure public-key references, and test signature, notification replay,
  order/refund idempotency, and reconciliation.

### Domestic Bank-Card Acquiring

- Official starting points: China UnionPay Open Platform
  <https://open.unionpay.com/> and its merchant onboarding platform
  <https://pcs.unionpay.com/mcmweb/login>. A bank or licensed acquirer's own
  onboarding portal may be the actual contracting path.
- Subject/materials: acquirer, acquiring model, merchant category, legal
  entity, licenses, settlement account, website/app/store proof, risk review,
  and certification requirements are institution-specific. No universal
  checklist or generic certification result is claimed here.
- Domain/callback: prefer acquirer-hosted/tokenized checkout and owned HTTPS
  callbacks. A1 must never receive raw PAN, CVV/CVC, PIN, track data, or
  cryptograms.
- Products: select hosted or token-reference acquiring and required
  refund/query/reconciliation products. Native raw-card acceptance is out of
  scope.
- Boundary: portal registration, test/certification environment, production
  merchant onboarding, and live settlement are separate gates.
- Human receipt: acquirer name, merchant/account suffix or SHA-256 fingerprint,
  certification case/status reference, callback URIs, environment/timestamp.
- Next code step: implement the chosen acquirer's certification interface using
  opaque references, then add forbidden-data, signature, replay, settlement,
  refund, and exception-queue tests.

## Receipt CLI

Create a safe template:

```powershell
python -m packages.sdk.ashr_clone.account_readiness template `
  --provider github_oauth `
  --environment sandbox
```

Validate a receipt:

```powershell
python -m packages.sdk.ashr_clone.account_readiness validate `
  --file .\human-operator-receipt.json
```

Supported providers are `github_oauth`, `google_oauth`,
`wechat_open_login`, `alipay_login`, `wechat_pay`, `alipay_merchant`, and
`domestic_bank_card`. Validation is fail-closed: unknown fields, unsafe
redirects, malformed timestamps/fingerprints, secrets, payment-card data, and
KYC fields are rejected. The CLI never prints the rejected raw value.

## Known Gaps

- WeChat Open Platform and Alipay product qualification/material requirements
  were not fully available on their logged-out public pages on July 10, 2026.
- Sandbox availability and production parity for WeChat login, Alipay login,
  WeChat Pay, Alipay merchant products, and each domestic acquirer must be
  confirmed inside the authenticated product-specific console.
- Fees, review SLAs, industry exclusions, settlement timing, reserve policy,
  and card-acquirer certification cases are intentionally not guessed.
- No provider secret, KYC document, payment credential, live payment, or
  production activation was handled in this task.
