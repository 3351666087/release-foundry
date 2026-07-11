# Round 47 Built-In Browser Public Calibration

Date: 2026-07-10

## Scope

The in-app Browser was used for read-only calibration after the external Chrome
snapshot path proved incompatible. No form was submitted, no credential was
entered, no account setting was changed, and no provider or Ashr API call was
made through the page.

## Observed public state

- URL: `https://ashr.io/`
- Page title: `Ashr`
- Public `Read the Docs` link targets `/docs/python-sdk/overview/`.
- Public `Get Started` link is visible.
- A public blog entry is visible from the home page.

The Browser visible-DOM channel was usable. The richer incremental ARIA snapshot
channel remained incompatible in this environment, so this round intentionally
used the supported visible-DOM path instead of repeatedly retrying the broken
channel.

## Truthful status

```text
built_in_browser_available=true
public_home_opened=true
public_docs_entry_observed=true
logged_in_dashboard_verified=false
sandbox_only=true
merchant_application_started=false
kyc_started=false
live_money_activation=false
real_provider_calls=false
real_card_acceptance=false
plan_only=true
```

This evidence confirms public navigation only. It is not evidence of an Ashr
dashboard session, quota, usage, paid mutation, merchant onboarding, or payment
provider readiness.
