-- Bound completed credential-link replay retention and expose a narrow,
-- idempotent purge authority. Purge audit rows retain only safe aggregate
-- metadata; receipt/proof/credential material is never copied into the audit.
BEGIN;

ALTER TABLE identity_lifecycle_receipts
  ADD COLUMN IF NOT EXISTS replay_retain_until TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION a1_set_credential_link_replay_retention()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp
AS $$
BEGIN
  IF NEW.operation='credential_link'
     AND NEW.consumed_at IS NOT NULL
     AND NEW.consume_outcome='success'
     AND NEW.link_idempotency_digest IS NOT NULL
     AND NEW.link_request_digest IS NOT NULL
     AND NEW.link_result_id IS NOT NULL THEN
    IF TG_OP='INSERT' OR OLD.replay_retain_until IS NULL THEN
      NEW.replay_retain_until :=
        NEW.consumed_at + INTERVAL '30 days';
    ELSIF NEW.replay_retain_until IS DISTINCT FROM OLD.replay_retain_until THEN
      RAISE EXCEPTION 'credential_link_replay_retention_immutable'
        USING ERRCODE='22023';
    END IF;
  ELSIF NEW.replay_retain_until IS NOT NULL THEN
    RAISE EXCEPTION 'credential_link_replay_retention_invalid'
      USING ERRCODE='22023';
  END IF;
  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS identity_lifecycle_receipts_replay_retention
  ON identity_lifecycle_receipts;
CREATE TRIGGER identity_lifecycle_receipts_replay_retention
BEFORE INSERT OR UPDATE ON identity_lifecycle_receipts
FOR EACH ROW
EXECUTE FUNCTION a1_set_credential_link_replay_retention();

UPDATE identity_lifecycle_receipts
SET replay_retain_until=consumed_at + INTERVAL '30 days'
WHERE operation='credential_link'
  AND consumed_at IS NOT NULL
  AND consume_outcome='success'
  AND link_idempotency_digest IS NOT NULL
  AND link_request_digest IS NOT NULL
  AND link_result_id IS NOT NULL
  AND replay_retain_until IS NULL;

ALTER TABLE identity_lifecycle_receipts
  DROP CONSTRAINT IF EXISTS identity_lifecycle_receipts_replay_retention_check;
ALTER TABLE identity_lifecycle_receipts
  ADD CONSTRAINT identity_lifecycle_receipts_replay_retention_check CHECK (
    (
      operation='credential_link'
      AND consumed_at IS NOT NULL
      AND consume_outcome='success'
      AND link_idempotency_digest IS NOT NULL
      AND link_request_digest IS NOT NULL
      AND link_result_id IS NOT NULL
      AND replay_retain_until=consumed_at + INTERVAL '30 days'
    )
    OR
    (
      replay_retain_until IS NULL
      AND NOT (
        operation='credential_link'
        AND consumed_at IS NOT NULL
        AND consume_outcome='success'
        AND link_idempotency_digest IS NOT NULL
        AND link_request_digest IS NOT NULL
        AND link_result_id IS NOT NULL
      )
    )
  );

CREATE INDEX IF NOT EXISTS identity_lifecycle_receipts_replay_retention_idx
  ON identity_lifecycle_receipts(replay_retain_until,lookup_key_version)
  WHERE operation='credential_link'
    AND replay_retain_until IS NOT NULL;

CREATE TABLE IF NOT EXISTS identity_credential_link_replay_purge_audit (
  purge_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  idempotency_digest TEXT NOT NULL UNIQUE
    CHECK (a1_identity_digest_valid(idempotency_digest)),
  request_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(request_digest)),
  actor_label TEXT NOT NULL CHECK (
    char_length(btrim(actor_label)) BETWEEN 1 AND 128
    AND actor_label !~ '[[:cntrl:]]'
  ),
  reason TEXT NOT NULL CHECK (
    char_length(btrim(reason)) BETWEEN 1 AND 512
    AND reason !~ '[[:cntrl:]]'
  ),
  requested_cutoff TIMESTAMPTZ NOT NULL,
  max_rows INTEGER NOT NULL CHECK (max_rows BETWEEN 1 AND 1000),
  purged_rows INTEGER NOT NULL CHECK (
    purged_rows BETWEEN 0 AND max_rows
  ),
  lookup_version_counts JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
    jsonb_typeof(lookup_version_counts)='object'
  ),
  completed_at TIMESTAMPTZ NOT NULL,
  schema_version TEXT NOT NULL DEFAULT
    'a1.identity.credential-link.replay-purge.v1'
    CHECK (
      schema_version='a1.identity.credential-link.replay-purge.v1'
    )
);

ALTER TABLE identity_credential_link_replay_purge_audit
  ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_credential_link_replay_purge_audit
  FORCE ROW LEVEL SECURITY;

REVOKE ALL ON identity_credential_link_replay_purge_audit FROM PUBLIC;
REVOKE ALL ON SEQUENCE
  identity_credential_link_replay_purge_audit_purge_id_seq FROM PUBLIC;

-- The authority serializes each idempotency namespace, deletes only completed
-- and expired replay rows whose fixed retention deadline passed, and returns
-- aggregate version counts. legacy-unversioned rows require separate explicit
-- administrative remediation and are intentionally never selected here.
CREATE OR REPLACE FUNCTION a1_purge_identity_credential_link_replays(
  p_cutoff TIMESTAMPTZ,
  p_limit INTEGER,
  p_actor TEXT,
  p_reason TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_clock TIMESTAMPTZ := clock_timestamp();
  v_existing identity_credential_link_replay_purge_audit%ROWTYPE;
  v_purge_id BIGINT;
  v_purged_rows INTEGER;
  v_lookup_version_counts JSONB;
BEGIN
  IF p_cutoff IS NULL OR p_now IS NULL
     OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000
     OR p_cutoff>p_now
     OR p_now>v_clock + INTERVAL '5 minutes'
     OR p_now<v_clock - INTERVAL '5 minutes'
     OR p_actor IS NULL
     OR char_length(btrim(p_actor)) NOT BETWEEN 1 AND 128
     OR p_actor ~ '[[:cntrl:]]'
     OR p_reason IS NULL
     OR char_length(btrim(p_reason)) NOT BETWEEN 1 AND 512
     OR p_reason ~ '[[:cntrl:]]'
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest) THEN
    RAISE EXCEPTION 'invalid_credential_link_replay_purge'
      USING ERRCODE='22023';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(p_idempotency_digest,0)
  );

  SELECT * INTO v_existing
  FROM identity_credential_link_replay_purge_audit
  WHERE idempotency_digest=p_idempotency_digest;
  IF FOUND THEN
    IF v_existing.request_digest<>p_request_digest THEN
      RAISE EXCEPTION 'credential_link_replay_purge_idempotency_conflict'
        USING ERRCODE='23505';
    END IF;
    RETURN jsonb_build_object(
      'schema_version',v_existing.schema_version,
      'purge_id',v_existing.purge_id::TEXT,
      'cutoff',v_existing.requested_cutoff,
      'max_rows',v_existing.max_rows,
      'purged_rows',v_existing.purged_rows,
      'lookup_version_counts',v_existing.lookup_version_counts,
      'completed_at',v_existing.completed_at
    );
  END IF;

  WITH eligible AS (
    SELECT receipt_digest,lookup_key_version
    FROM identity_lifecycle_receipts
    WHERE operation='credential_link'
      AND consumed_at IS NOT NULL
      AND consume_outcome='success'
      AND link_idempotency_digest IS NOT NULL
      AND link_request_digest IS NOT NULL
      AND link_result_id IS NOT NULL
      AND replay_retain_until IS NOT NULL
      AND replay_retain_until<=p_cutoff
      AND expires_at<=p_cutoff
      AND lookup_key_version<>'legacy-unversioned'
    ORDER BY replay_retain_until,receipt_digest
    LIMIT p_limit
    FOR UPDATE SKIP LOCKED
  ), deleted AS (
    DELETE FROM identity_lifecycle_receipts AS receipts
    USING eligible
    WHERE receipts.receipt_digest=eligible.receipt_digest
    RETURNING eligible.lookup_key_version
  ), counts AS (
    SELECT lookup_key_version,count(*)::BIGINT AS row_count
    FROM deleted
    GROUP BY lookup_key_version
  )
  SELECT
    COALESCE(sum(row_count),0)::INTEGER,
    COALESCE(
      jsonb_object_agg(lookup_key_version,row_count),
      '{}'::JSONB
    )
  INTO v_purged_rows,v_lookup_version_counts
  FROM counts;

  INSERT INTO identity_credential_link_replay_purge_audit(
    idempotency_digest,request_digest,actor_label,reason,
    requested_cutoff,max_rows,purged_rows,lookup_version_counts,
    completed_at
  ) VALUES (
    p_idempotency_digest,p_request_digest,btrim(p_actor),btrim(p_reason),
    p_cutoff,p_limit,v_purged_rows,v_lookup_version_counts,p_now
  )
  RETURNING purge_id INTO v_purge_id;

  RETURN jsonb_build_object(
    'schema_version','a1.identity.credential-link.replay-purge.v1',
    'purge_id',v_purge_id::TEXT,
    'cutoff',p_cutoff,
    'max_rows',p_limit,
    'purged_rows',v_purged_rows,
    'lookup_version_counts',v_lookup_version_counts,
    'completed_at',p_now
  );
END
$$;

REVOKE ALL ON FUNCTION a1_set_credential_link_replay_retention()
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_purge_identity_credential_link_replays(
  TIMESTAMPTZ,INTEGER,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
    REVOKE ALL ON identity_lifecycle_receipts,
      identity_credential_link_replay_purge_audit FROM a1_runtime;
    REVOKE ALL ON SEQUENCE
      identity_credential_link_replay_purge_audit_purge_id_seq
      FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_purge_identity_credential_link_replays(
      TIMESTAMPTZ,INTEGER,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ
    ) TO a1_runtime;
  END IF;
END
$$;

COMMIT;
