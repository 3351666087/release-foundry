# A3 rc.1 vs rc.2 Release Comparison

- Date: 2026-07-12
- Product route: `/delivery?source=a3-golden-path-rc2`
- API field: `release_comparison`
- Schema: `a3.release_comparison.v1`
- Version posture: post-seal rc.2 product increment; no production Release created

## Problem

rc.1 and rc.2 previously had separate evidence sources, but an operator had to switch sources and manually remember the differences. That made it too easy to confuse three independent facts:

1. A1 successfully executed a case.
2. A2 judged the case as passing or failing.
3. A2 Decision Ledger authorized or blocked a Release.

The comparison surface keeps those facts separate and explains why a better run does not automatically become release-ready.

## Authoritative Comparison

| Fact | rc.1 | rc.2 | Authority |
|---|---:|---:|---|
| A1 executed cases | 3/3 | 3/3 | A1 RunResult |
| A1 Trace completeness | 100% | 100% | A1 RunResult |
| A1 Tool Calls | 0 | 4 | A1 RunResult |
| A2 passed cases | 1/3 | 3/3 | A2 GradeResults |
| `missing_required_tool` | 2 | 0 | A2 failure class |
| Release Artifact entries | 12 | 16 | A3 manifest |
| Golden Path | 7/11 | 7/11 | A3 delivery evidence |
| Deployment Acceptance | 8/17 | 8/17 | A1/A3 deployment evidence |
| A2 release decision | `block` | `block` | A2 Decision Ledger |
| Production ready | false | false | A2 authority + delivery evidence |

The key correction is wording: A1 execution did not move from 1/3 to 3/3. A1 executed all three cases in both runs. A2 evaluation moved from 1/3 to 3/3 after the required `web.search` and media tool chain were added.

## Data Path

```text
rc.1 A1 RunResult + A2 GradeResults + Golden Path + Deployment + Artifact
rc.2 A1 RunResult + A2 GradeResults + Golden Path + Deployment + Artifact
  -> services/report/a3_release_comparison.mjs
  -> A3 Store snapshot
  -> GET /api/a3/dashboard
  -> release_comparison
  -> Next.js Delivery page
```

`changes`, `resolved_failure_classes`, and `quality` are display-only differences. Scores, pass/fail, failure classes, release decision, and release-ready state are copied from upstream evidence and are not recomputed by A3.

## Product Surface

The Delivery page now includes:

- a high-priority Chinese-first explanation of what improved;
- a prominent `BLOCK -> BLOCK` authority panel;
- four before/after facts for A2 grades, failure class, A1 Tool Calls, and A3 artifacts;
- a two-layer explanation separating case quality from release delivery;
- an expandable raw comparison contract for audit and debugging;
- full English switching without changing the selected evidence source.

## Contract And Safety

- OpenAPI exposes `ReleaseComparison` through `DashboardSnapshot.release_comparison`.
- Empty or missing evidence fails closed to zero/unknown/false.
- The contract records `a2_scores_recomputed=false`.
- The contract records `a2_pass_fail_recomputed=false`.
- The contract records `a2_failure_class_recomputed=false`.
- The contract records `a2_release_decision_recomputed=false`.
- No token, key, cookie, email, local path, or customer data is included.

## Verification

- Full A3 Node contracts passed `419/419`.
- Current-main A2 authority contracts passed `186/186` plus `1050` subtests.
- Focused release-comparison, Golden Agent, API/OpenAPI, and Webapp contracts passed.
- Next.js TypeScript and production build passed with 15 pages.
- Full Playwright passed `37/37`, including the rc.2 delivery flow on desktop and 390 x 844 mobile.
- CL hygiene passed with 0 findings; Commercial CL passed with 0 blockers and 0 advisories.
- The sealed rc.2 Release Artifact manifest reverified with manifest hash `8f84c5e3d4f064ae5d042b0f8ef72f2a3fb4d7ae06eb0a7d4dea01dc113d5a2f`.
- Visual inspection confirmed readable hierarchy, long-token wrapping, and no horizontal overflow.

Visual evidence:

- `docs/screenshots/a3-webapp-release-comparison-rc1-rc2-desktop.png`
- `docs/screenshots/a3-webapp-release-comparison-rc1-rc2-mobile-390x844.png`

## Release Boundary

This increment intentionally does not edit the sealed rc.2 manifest, hashed strategy, Golden Agent record, rc.2 release note, or Round 14 audit. It also does not mint a tag, GitHub Release, or production deployment. Those actions would be dishonest while A2 still says `block` and production infrastructure evidence is missing.

Remaining external prerequisites are a run-bound A2 `allow` ledger record, a tenant GitHub App, maintainer-approved required branch policy, and real staging/VPC deployment receipts for identity, PostgreSQL/RLS, queue, object storage, rollback, backup, and restore.

The 2026-07-13 peer-branch audit also observed new A1 provider execution receipts and new A2 multimodal/provider-receipt verification work. Those changes remain open-draft evidence and are not treated as merged-main authority by this increment.
