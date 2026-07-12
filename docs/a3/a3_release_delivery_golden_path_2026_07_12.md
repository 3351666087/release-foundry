# A3 Release Delivery Golden Path

- Date: 2026-07-12
- Candidate: `0.2.0-rc.1`
- New run: `a3-golden-20260712-001`
- Current verdict: `blocked_by_a2`

## 1. What this round closes

This round connects six previously separate A3 capabilities into one explicit delivery workflow:

1. A1 creates a fresh `RunResult` with trace evidence.
2. The existing A2 judge service grades the exact A1 cases.
3. A3 consumes the merged A2 Trusted Spine and preserves its release decision.
4. A3 creates and verifies a run-specific Audit Bundle and signed archive.
5. A3 creates and verifies a versioned Release Artifact manifest.
6. A3 exposes Deployment Acceptance and the full Golden Path in a CLI and a Next.js page.

The implementation does not claim that a local fixture, dry run, OpenAPI contract, SQLite file, or static page is a production deployment.

## 2. Fresh A1/A2 evidence

The new case set is `fixtures/a3/golden-path/a3_new_run_cases.json`. It contains a direct-answer case, a required web-tool case, and the A2 media-pipeline case `A2-S031`.

### A1 result

Source: `fixtures/a3/golden-path/a3_new_run_result.redacted.json`

| Signal | Result |
|---|---:|
| Run id | `a3-golden-20260712-001` |
| A1 executed cases | 3 |
| A1 execution passed | 3 |
| A1 execution errors/timeouts | 0 |
| Trace completeness | 100% |

This means the agent and runner completed the work. It does not mean the behavior was correct.

### A2 result

Source: `fixtures/a3/golden-path/a2_new_run_judge_response.redacted.json`

| Case | A2 result | Score | Failure class |
|---|---|---:|---|
| `a3-gp-direct-answer` | pass | 100 | `none` |
| `a3-gp-required-web-tool` | fail | 71 | `missing_required_tool` |
| `a3-gp-media-pipeline` | fail | 71 | `missing_required_tool` |

The A2 result is authoritative. A3 unwraps the A2 service response for display and packaging but does not recompute score, pass/fail, failure class, or the release decision.

## 3. Golden Path

The machine-readable status is `fixtures/a3/golden-path/golden-path-status.json`.

| Stage | Owner | Current state | Evidence |
|---|---|---|---|
| Capture new run | A1 | passed | A1 RunResult and complete trace |
| Evaluate every case | A2 | passed | A2 judge-service response |
| Authorize release | A2 | blocked | Trusted Decision Ledger says `block` |
| Seal Audit Bundle | A3 | passed | Bundle root and 14 artifacts verified |
| Verify signed archive | A3 | passed | 15 entries, root hash, Ed25519 signature passed |
| Verify Release Artifact | A3 | passed | Manifest and artifact-set hashes passed |
| Accept deployment | A1/A3 | blocked | No deployed target receipt |
| Trust tenant GitHub App | A1/A3 | blocked | No installation/permission receipt |
| Read back GitHub Check | A3 | passed | Live Check `86645448215` matches candidate `ad6113e` |
| Read back PR comment | A3 | passed | Live comment `4951021915` matches marker, body hash, and candidate SHA |
| Enforce required check | Maintainer | blocked | `main` is not branch protected |

Current progress is 7 of 11 stages, or 63.6%. This is a verifiable release candidate packet, not a production release.

## 4. Deployment Acceptance

The machine-readable receipt is `fixtures/a3/golden-path/deployment-acceptance.json`.

Deployment Acceptance has 17 checks. Eight evidence checks pass:

- A1 RunResult and trace exist.
- A2 grades join to all A1 cases.
- Audit Bundle verification passes.
- Signed archive verification passes.
- Versioned Release Artifact verification passes.
- Live GitHub Check readback matches the candidate head.
- Live operator PR comment readback matches its marker, body hash, and candidate head.
- GitHub Actions artifact `8259493055` was downloaded, is unexpired, carries a server SHA-256 digest, and contains a passing embedded manifest verification.

The following production checks remain blocked or not proven:

- A2 Trusted Spine does not allow release.
- A1 hosted identity has no deployed verifier receipt.
- PostgreSQL migration and RLS have no live proof.
- Queue worker, retry, and dead-letter behavior have no live proof.
- Audit artifacts have not been read back from immutable object storage.
- No staging/VPC deployment health and version receipt exists.
- Upgrade, rollback, backup, and restore have not been rehearsed.
- No tenant-bound custom GitHub App installation is proven.
- `main` does not enforce the required check.

## 5. GitHub truth boundary

There are three different GitHub evidence levels and they must not be confused:

| Evidence | Meaning | Production authority |
|---|---|---|
| Dry-run request | The request shape can be built | No |
| Live readback from `github.com` | A real Check/comment exists and can be read | Partial |
| Tenant-bound GitHub App plus required branch check | Product worker is authorized and merge policy is enforced | Yes |

The new `a3_github_observe_cli.mjs` performs read-only API calls. It never publishes a Check, changes branch protection, or prints a token. A personal/operator OAuth comment can be used for calibration but is not treated as the product's tenant GitHub App authority.

## 6. CLI surfaces

### Build delivery packet

```powershell
node services/report/a3_release_delivery_cli.mjs `
  --runs fixtures/a3/golden-path/a3_new_run_result.redacted.json `
  --grades fixtures/a3/golden-path/a2_new_run_judge_response.redacted.json `
  --trusted-spine fixtures/a2/results/a2_trusted_spine_handoff.json `
  --audit-bundle fixtures/a3/golden-path/audit-bundle-index.json `
  --audit-bundle-verification fixtures/a3/golden-path/audit-bundle-verification.json `
  --audit-archive fixtures/a3/golden-path/audit-archive-manifest.json `
  --audit-archive-verification fixtures/a3/golden-path/audit-archive-verification.json `
  --deployment-probe fixtures/a3/golden-path/deployment_probe.redacted.json `
  --release-version 0.2.0-rc.1 `
  --output-dir artifacts/a3-release-delivery `
  --no-fail --json
```

`--no-fail` means CI may upload a blocked evidence packet. It does not turn the blocked release into a pass.

### Observe GitHub without mutation

```powershell
$env:GITHUB_TOKEN = gh auth token
node services/report/a3_github_observe_cli.mjs `
  --repo 3351666087/ashr-codex-factory `
  --check-run-id <real-check-id> `
  --check-name "A3 golden path release artifact" `
  --head-sha <candidate-sha> `
  --branch main `
  --required-check-name "A3 golden path release artifact" `
  --json
Remove-Item Env:GITHUB_TOKEN
```

The token is runtime-only and must never be printed, documented, or committed.

## 7. Product page

The Next.js route is `/delivery`.

It shows:

- the authoritative A2 release signal;
- progress across all 11 stages;
- all Deployment Acceptance checks and their evidence class;
- A1/A2/A3/GitHub ownership boundaries;
- the version, Git SHA alias, artifact count, and production flag;
- raw sanitized evidence in a collapsible inspector.

Selecting source `A3 Golden Path 20260712` loads the new run instead of the old mock or Ashr `11926` sample.

## 8. Release artifact

The candidate is `0.2.0-rc.1`. It is intentionally marked:

- `channel=release-candidate`
- `candidate_only=true`
- `production_release=false`
- `github_release_created=false`
- `deployment_created=false`

GitHub Actions builds the packet and uploads `ashr-a3-0.2.0-rc.1-<sha>` as a workflow artifact. Creating a Git tag or GitHub Release remains prohibited while A2 and Deployment Acceptance are blocked.

For pull-request workflows, `<sha>` is the candidate PR head. The manifest separately records `ci_tested_sha_alias`, which is the temporary GitHub merge commit actually checked by Actions. These identities must not be collapsed into one field.

## 9. Safety invariants

- A1 owns run, trace, tool-call, identity, and runtime evidence.
- A2 owns score, pass/fail, failure class, policy, and release decision.
- A3 owns product workflow, packaging, reports, and evidence presentation.
- No API key, token, cookie, email, installation token, or private key is stored in this packet.
- The archive uses a local ephemeral signing key; only the public key and signature are stored. It is not SSO/KMS identity proof.
- A real GitHub Actions Check does not by itself prove a tenant-installed custom GitHub App.
- A passing local verifier does not prove a deployed database, queue, object store, or VPC.

## 10. Next three actions

1. Obtain a new A2 `allow` Decision Ledger only after the two `missing_required_tool` failures are fixed and rerun.
2. Install and bind a real tenant GitHub App, then enable `A3 golden path release artifact` as a required `main` check.
3. Deploy a staging stack with A1 identity, PostgreSQL/RLS, queue worker, object storage, health/version endpoint, and rollback rehearsal; attach the resulting receipts to Deployment Acceptance.
