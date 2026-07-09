# A2 A1 Billing And Payment Context - 2026-07-09

## Scope

- Lane: A2 Evaluation / Policy / Security.
- Service boundary: `services/judge/evidence_readiness.py`.
- Contract: `docs/a2/schemas/evidence_readiness.schema.json`.
- Generated artifact: `fixtures/a2/results/a2_evidence_readiness_report.json`.

## Upstream Signal

- `origin/codex/a1-local-sdk-runner` advanced to billing ledger migration work:
  - `91213fc A1: add durable billing ledger migration`
  - `11ac03e A1: add billing ledger live migration smoke`
  - `5c4bc83 A1: add billing route contract parity`
- New public manifest: `docs/a1/schemas/a1_billing_ledger_migration_manifest.json`.
- New public payment provider readiness packet on A1: `docs/a1/evidence/payment_provider_readiness_public.json`.
- `origin/codex/a3-commercial-growth-round4` added peer branch/live workflow readiness and then `afd8efe Add A3 live ops control plane`, which names billing state and A2 evidence contracts as downstream product inputs.

## A2 Behavior

- A2 now optionally consumes the A1 billing ledger migration manifest when it appears on the active branch.
- The summary records table names, tenant RLS readiness, required constraint/index counts, provider/mode/currency support, required SQL function names, and public-safety flags.
- The context is ready only when tenant-scoped RLS exists for all billing tables, provider coverage includes Stripe/WeChat Pay/Alipay, modes include test/live, currencies include USD/CNY, and no raw provider payload/secret/card data is stored.
- A2 also optionally consumes A1 payment provider readiness as payment policy context.
- The payment summary records provider/mode/payment-method coverage, hosted-surface count, CI/provider-call safety flags, raw secret/card/webhook boundaries, public/private evidence path counts, and human real-card automation boundaries.
- Payment context is ready only when public-safe references and webhook hashes are present, CI provider calls are disallowed, raw secret/provider/card data is absent, and live payment testing is explicitly human-controlled.
- `c3_grading_ready` remains false; SQL billing migration evidence does not satisfy reviewed Ashr grading rows.
- `c3_grading_ready` also remains false for payment provider readiness; payment provider evidence is policy/security context, not reviewed Ashr grading evidence.

## Verification Plan

- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- `git diff --check`
- staged secret scan before commit.

## Notes

- No live Ashr API call was needed for this change.
- No private evidence path was read or committed.
