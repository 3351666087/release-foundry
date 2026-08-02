-- Version lifecycle receipt lookup digests and expose an aggregate-only
-- retirement preflight. Existing digests cannot be re-keyed because the
-- public opaque receipt is intentionally never stored.
BEGIN;

ALTER TABLE identity_lifecycle_receipts
  ADD COLUMN IF NOT EXISTS lookup_key_version TEXT;

UPDATE identity_lifecycle_receipts
SET lookup_key_version='legacy-unversioned'
WHERE lookup_key_version IS NULL;

ALTER TABLE identity_lifecycle_receipts
  ALTER COLUMN lookup_key_version SET NOT NULL;

ALTER TABLE identity_lifecycle_receipts
  DROP CONSTRAINT IF EXISTS identity_lifecycle_receipts_lookup_key_version_check;
ALTER TABLE identity_lifecycle_receipts
  ADD CONSTRAINT identity_lifecycle_receipts_lookup_key_version_check
  CHECK (lookup_key_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$');

CREATE INDEX IF NOT EXISTS identity_lifecycle_receipts_lookup_version_idx
  ON identity_lifecycle_receipts(lookup_key_version,expires_at,consumed_at);

CREATE OR REPLACE FUNCTION a1_issue_identity_lifecycle_receipt(
  p_receipt_digest TEXT, p_operation TEXT, p_provider TEXT,
  p_tenant_scope TEXT, p_project_scope TEXT, p_proof_nonce BYTEA,
  p_proof_key_version TEXT, p_lookup_key_version TEXT,
  p_proof_ciphertext BYTEA, p_expires_at TIMESTAMPTZ
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
BEGIN
  IF p_lookup_key_version IS NULL
     OR p_lookup_key_version !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
     OR p_lookup_key_version='legacy-unversioned' THEN
    RAISE EXCEPTION 'invalid_lifecycle_lookup_key_version'
      USING ERRCODE='22023';
  END IF;
  INSERT INTO identity_lifecycle_receipts(
    receipt_digest,operation,provider,tenant_scope,project_scope,
    proof_nonce,proof_key_version,lookup_key_version,proof_ciphertext,expires_at
  ) VALUES (
    p_receipt_digest,p_operation,p_provider,
    COALESCE(p_tenant_scope,''),COALESCE(p_project_scope,''),
    p_proof_nonce,p_proof_key_version,p_lookup_key_version,
    p_proof_ciphertext,p_expires_at
  );
END
$$;

-- This authority returns only version labels, counts, and a deadline. It never
-- returns receipt digests, proof material, ciphertext, nonce, or key bytes.
CREATE OR REPLACE FUNCTION a1_identity_lifecycle_lookup_retirement_readiness(
  p_retiring_version TEXT,
  p_retained_versions TEXT[],
  p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_legacy_live BIGINT;
  v_legacy_replay BIGINT;
  v_retiring_live BIGINT;
  v_retiring_replay BIGINT;
  v_unreachable_live BIGINT;
  v_unreachable_replay BIGINT;
  v_required_until TIMESTAMPTZ;
BEGIN
  IF p_retiring_version IS NULL
     OR p_retiring_version !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
     OR p_retiring_version='legacy-unversioned'
     OR p_retained_versions IS NULL
     OR EXISTS (
       SELECT 1
       FROM unnest(p_retained_versions) AS version
       WHERE version IS NULL
          OR version !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
          OR version='legacy-unversioned'
     )
     OR cardinality(p_retained_versions) <> (
       SELECT count(DISTINCT version) FROM unnest(p_retained_versions) AS version
     ) THEN
    RAISE EXCEPTION 'invalid_lifecycle_lookup_retirement_preflight'
      USING ERRCODE='22023';
  END IF;

  SELECT
    count(*) FILTER (
      WHERE lookup_key_version='legacy-unversioned'
        AND consumed_at IS NULL AND expires_at>p_now
    ),
    count(*) FILTER (
      WHERE lookup_key_version='legacy-unversioned'
        AND link_result_id IS NOT NULL
    ),
    count(*) FILTER (
      WHERE lookup_key_version=p_retiring_version
        AND consumed_at IS NULL AND expires_at>p_now
    ),
    count(*) FILTER (
      WHERE lookup_key_version=p_retiring_version
        AND link_result_id IS NOT NULL
    ),
    count(*) FILTER (
      WHERE consumed_at IS NULL AND expires_at>p_now
        AND (
          lookup_key_version='legacy-unversioned'
          OR NOT (lookup_key_version=ANY(p_retained_versions))
        )
    ),
    count(*) FILTER (
      WHERE link_result_id IS NOT NULL
        AND (
          lookup_key_version='legacy-unversioned'
          OR NOT (lookup_key_version=ANY(p_retained_versions))
        )
    ),
    max(expires_at) FILTER (
      WHERE consumed_at IS NULL AND expires_at>p_now
        AND (
          lookup_key_version='legacy-unversioned'
          OR NOT (lookup_key_version=ANY(p_retained_versions))
        )
    )
  INTO
    v_legacy_live,v_legacy_replay,
    v_retiring_live,v_retiring_replay,
    v_unreachable_live,v_unreachable_replay,v_required_until
  FROM identity_lifecycle_receipts;

  RETURN jsonb_build_object(
    'schema_version','a1.identity.lifecycle.lookup-readiness.v1',
    'retiring_version',p_retiring_version,
    'ready',(v_unreachable_live=0 AND v_unreachable_replay=0),
    'legacy_unversioned_live_receipts',v_legacy_live,
    'legacy_unversioned_replay_records',v_legacy_replay,
    'retiring_live_receipts',v_retiring_live,
    'retiring_replay_records',v_retiring_replay,
    'unreachable_live_receipts',v_unreachable_live,
    'unreachable_replay_records',v_unreachable_replay,
    'live_receipts_required_until',v_required_until,
    'replay_retention_required',(v_unreachable_replay>0)
  );
END
$$;

REVOKE ALL ON FUNCTION a1_issue_identity_lifecycle_receipt(
  TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,BYTEA,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_identity_lifecycle_receipt(
  TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,TEXT,BYTEA,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_identity_lifecycle_lookup_retirement_readiness(
  TEXT,TEXT[],TIMESTAMPTZ
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
    REVOKE ALL ON FUNCTION a1_issue_identity_lifecycle_receipt(
      TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,BYTEA,TIMESTAMPTZ
    ) FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_issue_identity_lifecycle_receipt(
      TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,TEXT,BYTEA,TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_identity_lifecycle_lookup_retirement_readiness(
      TEXT,TEXT[],TIMESTAMPTZ
    ) TO a1_runtime;
  END IF;
END
$$;

COMMIT;
