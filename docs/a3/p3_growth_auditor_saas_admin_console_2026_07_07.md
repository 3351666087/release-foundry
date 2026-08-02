# P3 Growth-Auditor: SaaS Admin Console - 2026-07-07

## Commercial Verdict

This round pushes A3 beyond a release dashboard toward an enterprise SaaS console. Login, Team, API Keys, Usage, and Trust are not cosmetic: they are the surfaces that let a company adopt the product, manage access, meter usage, and hand evidence to reviewers or auditors.

## Newly Sellable Capabilities

- Login state model with explicit mock/OAuth boundary.
- Team roster and role model for owner, developer, reviewer, auditor, and billing admin.
- API-key metadata model that never exposes real secret values.
- Usage panel connected to current run/case evidence and P3 usage calibration.
- Trust report preview model connected to release gate status.
- Cloud action planner that marks risky operations as plan-only until hosted auth/RBAC exists.
- A1/A2 compatibility status inside the admin surface.

## What Is Still Toy-Like

- There is no real hosted auth callback.
- There is no server-side RBAC middleware.
- API keys are metadata-only and cannot yet be created or revoked.
- Team invites are not real email workflows.
- Trust publishing is not a real public hosted page.
- Usage/billing is partly fixture-derived and OAuth-gated.

## Why This Increases Willingness To Pay

- Enterprise buyers expect team roles, API-key management, usage visibility, and trust reports before procurement takes a tool seriously.
- Release reviewers need visible ownership and sign-off boundaries.
- Security reviewers need assurance that API-key secrets and account data are not leaked into reports.
- Managers need usage and Trust surfaces to justify ongoing spend.

## Next 20 Growth Points

1. Add hosted auth callback.
2. Add local auth mock middleware for E2E tests.
3. Add RBAC matrix for owner/admin/developer/reviewer/auditor/billing admin.
4. Add `team_members` SQL migration.
5. Add `api_keys` SQL migration with hash-only secret storage.
6. Add one-time API-key reveal flow.
7. Add key rotation audit events.
8. Add key revoke audit events.
9. Add invite preview endpoint.
10. Add invite accept state machine.
11. Add Trust hosted report route.
12. Add Trust publish approval gate.
13. Add usage ledger adapter.
14. Add usage overage warning state.
15. Add billing plan read-only page.
16. Add project switcher connected to API source.
17. Add audit log page for SaaS admin actions.
18. Add API action plan export into hosted report.
19. Add Playwright smoke for SaaS Admin panel.
20. Add secret scan over API-key metadata and Trust report output.

## Highest-Money Direction

The highest-money direction is API-key management plus Trust/release approval. Those two surfaces put ReleaseFoundry directly into a customer's deployment gate and security review process, which supports higher enterprise pricing than dashboard-only triage.
