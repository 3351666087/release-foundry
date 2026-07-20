# A3 Growth Auditor Round 13: Release Delivery Golden Path

- Date: 2026-07-12
- Review mode: separate fail-closed auditor pass
- Scope: GitHub workflow, deployment acceptance, release artifacts, versioning, and new-run Audit Bundle

## Verdict

The round materially improves enterprise delivery evidence, but the candidate remains correctly blocked. Local packaging is now strong; live deployment and tenant GitHub authority are not yet proven.

## Growth Points

| # | Growth point | Severity | Current state | Required proof |
|---:|---|---|---|---|
| 1 | A2 Trusted Spine blocks release | blocker | correctly blocked | new A2 allow Decision Ledger record |
| 2 | Tenant GitHub App is absent | blocker | not proven | installation id alias, repo binding, permission receipt |
| 3 | `main` has no branch protection | blocker | GitHub returned 404 | required-check readback with strict mode |
| 4 | No deployed A1 identity verifier | blocker | contract only | hosted identity/session verifier receipt |
| 5 | No PostgreSQL/RLS runtime proof | blocker | contract only | migration id, RLS probes, tenant isolation test |
| 6 | No durable queue worker proof | blocker | contract only | queue health, retry, dedupe, dead-letter receipt |
| 7 | No immutable object-storage readback | blocker | local files only | object version, retention, hash readback |
| 8 | No staging/VPC health receipt | blocker | no target URL | versioned health and dependency probes |
| 9 | Upgrade/rollback not rehearsed | blocker | no receipt | install, upgrade, rollback timestamps and checks |
| 10 | Backup/restore not rehearsed | blocker | no receipt | backup id and restore verification |
| 11 | Current archive signer is self-signed | high | cryptographically valid | KMS/HSM/SSO-bound signer identity |
| 12 | GitHub Actions artifact expires in 14 days | high | configured | durable release registry/object storage copy |
| 13 | GitHub Actions Check is not a tenant custom App | high | explicit boundary | A1 trusted App worker evidence |
| 14 | Operator PR comment is calibration only | high | explicit boundary | app-authored comment and readback |
| 15 | Required-check mutation has no approval workflow | high | plan only | maintainer approval plus mutation/readback receipt |
| 16 | Deployment probe is manually assembled | medium | schema exists | automated probe collector with signed receipt |
| 17 | Release manifest is not published to registry | medium | local/CI artifact | registry id, immutable digest, download receipt |
| 18 | Candidate SHA must be resealed after real readback | medium | pending | exact head SHA across Check/comment/bundle/manifest |
| 19 | UI has no download link for CI artifact | medium | status only | trusted artifact URL or hosted report link |
| 20 | UI does not trigger deployment probes | medium | read-only by design | authenticated worker-trigger endpoint with audit |
| 21 | Media case has no real media tool execution | medium | A2 correctly failed | A1 media.fetch/image.view/classify trace |
| 22 | New run has only three cases | medium | calibration slice | full Golden/Regression candidate run |
| 23 | No customer VPC install profile | medium | strategy only | versioned Helm/Terraform/Compose profile |
| 24 | No SBOM/provenance attestation | medium | absent | CycloneDX/SPDX plus signed build provenance |
| 25 | No vulnerability scan receipt in release manifest | medium | npm audit separate | linked SCA/container scan receipt |
| 26 | No SLO/alert acceptance | medium | absent | latency/error SLO and alert firing test |
| 27 | No data-retention deletion test | medium | policy only | purge/legal-hold execution receipt |
| 28 | No multi-region or disaster recovery proof | low for MVP | absent | recovery-point/recovery-time rehearsal |
| 29 | No GitHub webhook replay/idempotency proof | medium | outbox contract only | signed webhook delivery and replay tests |
| 30 | No automatic release-note checksum index | low | docs listed | docs hashes included in release artifact set |

## What passed this audit

- Fresh A1 and A2 evidence is joined by matching case ids.
- A3 does not recompute A2 score or release authority.
- Bundle, custody chain, archive root, archive signature, and release manifest are independently verifiable.
- Contract-only GitHub receipts are rejected as production proof.
- Deployment Acceptance exposes blockers instead of hiding them.
- CI can upload a blocked packet without turning it into a passing release.
- No secret-bearing environment value is written to the packet.

## Commercial recommendation

Do not expand the dashboard with more decorative panels in the next round. Prioritize a deployed staging receipt, a tenant GitHub App installation, and required branch protection. Those three items convert existing product shape into evidence a buyer or maintainer can trust.
