# GitHub Dual Release Runbook

ReleaseFoundry publishes two independent GitHub Releases from one tested source commit:

| Release | Canonical ID | Git tag |
| --- | --- | --- |
| Product RC | `releasefoundry-product@1.0.0-rc.1` | `releasefoundry-product-v1.0.0-rc.1` |
| Customer Agent evidence RC | `agent-release:demo/a3-golden-agent@0.2.0-rc.3` | `customer-agent-demo-a3-golden-agent-v0.2.0-rc.3` |

These tags may point to the same clean packaging commit, but their manifests, assets, verification decisions, notes, and checksums are separate. Customer evidence also preserves distinct A1 candidate, A2 authority and A3 implementation commits. Both are GitHub prereleases until their own verifier reports `GO`.

## Build Preconditions

1. Start from a clean, tested `main` commit.
2. Do not copy `.env.local`, API keys, OAuth credentials, cookies, signed URLs, private media, or account data into the build workspace.
3. Build the TypeScript SDK and Next.js static Web output:

   ```powershell
   npm.cmd ci --prefix packages/ts/releasefoundry
   npm.cmd run build --prefix packages/ts/releasefoundry
   npm.cmd ci --prefix apps/webapp
   npm.cmd run build --prefix apps/webapp
   ```

4. Run the release contracts and complete CL Gate before publishing.

## Build

```powershell
python scripts/build_dual_release_candidates.py `
  --product-version 1.0.0-rc.1 `
  --agent-version 0.2.0-rc.3 `
  --agent-org demo `
  --agent-name a3-golden-agent
```

Output is written to `dist/releases/` and is intentionally ignored by Git. The command creates:

- two self-contained ZIP files;
- independent Product and Customer manifests;
- independent verification outputs and release notes;
- Product SBOM and provenance;
- separate `SHA256SUMS` files;
- `dual-release-index.json` and its integrity verification.

Verify the generated index again before upload:

```powershell
python scripts/build_dual_release_candidates.py `
  --verify-index dist/releases/dual-release-index.json
```

## Decision Rules

- A successful build means the files are complete and hash-consistent. It does not mean either release is `GO`.
- Product `GO` requires every live receipt, immutable image digest, signature, and production Web gate required by `releasefoundry_product_release_policy.v1.json`.
- Customer Agent `GO` requires an approved Product Release binding, a passing A1 run, an A2 `allow` Decision Ledger, an A3 ready delivery, and an auditable human approval.
- A1, A2, A3 delivery, audit bundle, tested Git SHA, run ID, and evidence release version must all identify the same candidate. Historical evidence is retained but cannot authorize a newer candidate.
- Customer Agent verification reads the A2 decision and provenance hash. It never recomputes A2 semantics.
- If either verification is `NO-GO`, publish only as a prerelease and place `NO-GO` at the top of the GitHub Release notes.

## Publish

Use the exact tested source commit as `--target`. Upload only the assets listed in the matching index section.

```powershell
gh release create releasefoundry-product-v1.0.0-rc.1 `
  --repo 3351666087/release-foundry `
  --target <tested-main-sha> `
  --prerelease `
  --title "ReleaseFoundry Product 1.0.0-rc.1 (NO-GO Candidate)" `
  --notes-file dist/releases/releasefoundry-product-1.0.0-rc.1.release-notes.md `
  <product-assets>

gh release create customer-agent-demo-a3-golden-agent-v0.2.0-rc.3 `
  --repo 3351666087/release-foundry `
  --target <tested-main-sha> `
  --prerelease `
  --title "Customer Agent a3-golden-agent 0.2.0-rc.3 (NO-GO Evidence Release)" `
  --notes-file dist/releases/agent-release-demo-a3-golden-agent-0.2.0-rc.3.release-notes.md `
  <customer-assets>
```

## Post-Publish Readback

1. Query each GitHub Release by tag.
2. Confirm `isPrerelease=true`, target commit, asset count, asset names, byte sizes, and download URLs.
3. Download every asset to a new temporary directory.
4. Verify SHA256SUMS, ZIP integrity, both manifests, both verification files, and the product binding in the Customer manifest.
5. Record the GitHub Release URLs and readback result without storing credentials.

Do not mark either Release as latest or production-ready merely because GitHub accepted the upload.
