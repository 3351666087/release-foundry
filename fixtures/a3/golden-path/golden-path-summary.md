# ReleaseFoundry Release Delivery Golden Path

- Status: blocked_by_a2
- Production ready: no
- Release version: 0.2.0-rc.1
- Progress: 7/11 (63.6%)
- Deployment acceptance: blocked
- A2 decision: block

## Stages

- [x] A1 captures a new run - passed (A1)
- [x] A2 grades every case - passed (A2)
- [ ] A2 Decision Ledger authorizes release - blocked (A2)
  Reason: a2_decision_blocks_release
- [x] A3 seals and verifies the Audit Bundle - passed (A3)
- [x] A3 verifies the signed archive - passed (A3)
- [x] Versioned release artifact is verifiable - passed (A3)
- [ ] Deployment acceptance passes - blocked (A1/A3)
  Reason: Deployment acceptance is blocked.
- [ ] Tenant GitHub App is trusted - blocked (A1/A3)
  Reason: A tenant-bound GitHub App installation is not proven.
- [x] GitHub Check is published and read back - passed (A3)
- [x] PR comment is published and read back - passed (A3)
- [ ] main enforces the release check - blocked (Repository maintainer)
  Reason: Branch protection does not enforce the release check.

## Safety

A3 consumes A1 runtime evidence and A2 decisions. It does not recompute A2 score, pass/fail, or release authority.
