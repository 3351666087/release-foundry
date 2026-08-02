# A3 GitHub Readback Product Surface

- Date: 2026-07-12
- Source: `a3-golden-path-rc2`
- UI route: `/delivery?source=a3-golden-path-rc2`
- Status: implemented and tested against committed redacted live readbacks
- Release authority: still blocked by A2 Decision Ledger

## What changed

The Delivery page now presents four GitHub readback records as first-class product evidence instead of leaving them only inside raw JSON:

1. GitHub Actions Check Run: provider, conclusion, Check ID, head SHA, and trusted GitHub URL.
2. Operator PR comment: authority class, comment ID, marker match, body-hash match, and trusted GitHub URL.
3. GitHub Actions artifact: artifact ID, file count, size, downloaded digest, and workflow URL.
4. Main required-check policy: branch, HTTP status, readback status, and enforced state.

## Data path

```text
redacted rc.1 / rc.2 readback fixtures
-> A3 source configuration
-> normalized Store snapshot
-> /api/a3/dashboard
-> typed Webapp raw evidence boundary
-> Delivery GitHub readback cards
```

The UI does not fetch GitHub directly and never receives a token. Links render only when the URL is HTTPS on `github.com`; arbitrary fixture URLs are rejected.

## Honest authority

- Check success means the GitHub Actions App verified the packet. It is not A2 release approval.
- The PR comment was published through operator OAuth. It is not a tenant-bound custom GitHub App.
- The downloaded artifact digest and 19 uploaded files were verified.
- Main branch protection returned HTTP 404, so required-check enforcement remains false.
- A3 does not recalculate A2 score, pass/fail, failure class, or release authority.

## Visual evidence


This is a post-seal product visibility increment. It consumes the sealed rc.2 readback receipts without rewriting the already signed rc.2 release manifest.
