-- Durable registration/login proof receipts. The public receipt is never
-- stored; receipt_digest is a server-keyed HMAC and proof payloads are sealed
-- by the Go runtime before insertion.
BEGIN;

CREATE TABLE IF NOT EXISTS identity_lifecycle_receipts (
  receipt_digest TEXT PRIMARY KEY CHECK (a1_identity_digest_valid(receipt_digest)),
  operation TEXT NOT NULL CHECK (operation IN ('registration', 'login')),
  provider TEXT NOT NULL CHECK (provider IN ('local', 'github', 'google', 'wechat', 'qq', 'alipay')),
  tenant_scope TEXT NOT NULL DEFAULT '',
  project_scope TEXT NOT NULL DEFAULT '',
  proof_nonce BYTEA NOT NULL CHECK (octet_length(proof_nonce) >= 12),
  proof_key_version TEXT NOT NULL CHECK (
    proof_key_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
  ),
  proof_ciphertext BYTEA NOT NULL CHECK (octet_length(proof_ciphertext) >= 32),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  consume_outcome TEXT CHECK (consume_outcome IS NULL OR consume_outcome IN ('success')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT identity_lifecycle_receipt_consumption_check CHECK (
    (consumed_at IS NULL AND consume_outcome IS NULL)
    OR (consumed_at IS NOT NULL AND consume_outcome = 'success')
  )
);

-- Keep upgrades from pre-keyring development builds safe. PostgreSQL does not
-- add columns from a repeated CREATE TABLE IF NOT EXISTS statement.
ALTER TABLE identity_lifecycle_receipts
  ADD COLUMN IF NOT EXISTS proof_key_version TEXT;

UPDATE identity_lifecycle_receipts
SET proof_key_version = 'v1'
WHERE proof_key_version IS NULL;

ALTER TABLE identity_lifecycle_receipts
  ALTER COLUMN proof_key_version SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'identity_lifecycle_receipts'::regclass
      AND conname = 'identity_lifecycle_receipts_proof_key_version_check'
  ) THEN
    ALTER TABLE identity_lifecycle_receipts
      ADD CONSTRAINT identity_lifecycle_receipts_proof_key_version_check
      CHECK (proof_key_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$');
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS identity_lifecycle_receipts_expiry_idx
  ON identity_lifecycle_receipts(expires_at) WHERE consumed_at IS NULL;
CREATE INDEX IF NOT EXISTS identity_lifecycle_receipts_scope_idx
  ON identity_lifecycle_receipts(operation, provider, tenant_scope, project_scope);
CREATE INDEX IF NOT EXISTS identity_lifecycle_receipts_key_version_idx
  ON identity_lifecycle_receipts(proof_key_version, expires_at)
  WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS identity_lifecycle_receipt_audit (
  audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  receipt_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(receipt_digest)),
  operation TEXT NOT NULL CHECK (operation IN ('registration', 'login')),
  provider TEXT NOT NULL,
  tenant_scope TEXT NOT NULL DEFAULT '',
  project_scope TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL CHECK (outcome IN ('consumed', 'expired', 'replayed', 'scope_mismatch', 'not_found')),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE identity_lifecycle_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_lifecycle_receipts FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_lifecycle_receipt_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_lifecycle_receipt_audit FORCE ROW LEVEL SECURITY;

REVOKE ALL ON identity_lifecycle_receipts, identity_lifecycle_receipt_audit FROM PUBLIC;
REVOKE ALL ON SEQUENCE identity_lifecycle_receipt_audit_audit_id_seq FROM PUBLIC;

CREATE OR REPLACE FUNCTION a1_issue_identity_lifecycle_receipt(
  p_receipt_digest TEXT, p_operation TEXT, p_provider TEXT,
  p_tenant_scope TEXT, p_project_scope TEXT, p_proof_nonce BYTEA,
  p_proof_key_version TEXT, p_proof_ciphertext BYTEA,
  p_expires_at TIMESTAMPTZ
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  INSERT INTO identity_lifecycle_receipts(
    receipt_digest, operation, provider, tenant_scope, project_scope,
    proof_nonce, proof_key_version, proof_ciphertext, expires_at
  ) VALUES (
    p_receipt_digest, p_operation, p_provider,
    COALESCE(p_tenant_scope, ''), COALESCE(p_project_scope, ''),
    p_proof_nonce, p_proof_key_version, p_proof_ciphertext, p_expires_at
  );
END
$$;

CREATE OR REPLACE FUNCTION a1_lock_identity_lifecycle_receipt(
  p_receipt_digests TEXT[]
) RETURNS TABLE (
  receipt_digest TEXT, operation TEXT, provider TEXT, tenant_scope TEXT,
  project_scope TEXT, expires_at TIMESTAMPTZ, consumed_at TIMESTAMPTZ,
  proof_nonce BYTEA, proof_key_version TEXT, proof_ciphertext BYTEA
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT
    r.receipt_digest, r.operation, r.provider, r.tenant_scope,
    r.project_scope, r.expires_at, r.consumed_at, r.proof_nonce,
    r.proof_key_version, r.proof_ciphertext
  FROM identity_lifecycle_receipts AS r
  WHERE r.receipt_digest = ANY(p_receipt_digests)
  ORDER BY array_position(p_receipt_digests, r.receipt_digest)
  LIMIT 1
  FOR UPDATE
$$;

CREATE OR REPLACE FUNCTION a1_consume_identity_lifecycle_receipt(
  p_receipt_digest TEXT, p_operation TEXT, p_provider TEXT,
  p_tenant_scope TEXT, p_project_scope TEXT, p_consumed_at TIMESTAMPTZ
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  UPDATE identity_lifecycle_receipts
  SET consumed_at = p_consumed_at, consume_outcome = 'success'
  WHERE receipt_digest = p_receipt_digest AND consumed_at IS NULL;
  IF NOT FOUND THEN
    RETURN FALSE;
  END IF;
  INSERT INTO identity_lifecycle_receipt_audit(
    receipt_digest, operation, provider, tenant_scope, project_scope,
    outcome, occurred_at
  ) VALUES (
    p_receipt_digest, p_operation, p_provider,
    COALESCE(p_tenant_scope, ''), COALESCE(p_project_scope, ''),
    'consumed', p_consumed_at
  );
  RETURN TRUE;
END
$$;

CREATE OR REPLACE FUNCTION a1_register_identity_lifecycle_credential(
  p_provider TEXT,
  p_credential_kind TEXT,
  p_subject_digests TEXT[],
  p_display_label TEXT,
  p_email_digest TEXT,
  p_email_source TEXT,
  p_request_digest TEXT,
  p_now TIMESTAMPTZ
) RETURNS TABLE (registered_principal_id UUID, registered_credential_id UUID)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_principal_id UUID;
  v_credential_id UUID;
  v_link_status TEXT;
  v_conflict_id UUID;
BEGIN
  IF p_provider NOT IN ('email','github','google','wechat','qq','alipay')
     OR p_credential_kind NOT IN ('email_otp','phone_otp','federated')
     OR cardinality(p_subject_digests) < 1
     OR NOT a1_identity_digest_valid(p_subject_digests[1])
     OR NOT a1_identity_digest_valid(p_request_digest) THEN
    RAISE EXCEPTION 'invalid_registration_material' USING ERRCODE = '22023';
  END IF;
  IF EXISTS (
    SELECT 1 FROM identity_credentials
    WHERE provider = p_provider AND provider_environment = 'production'
      AND subject_digest = ANY(p_subject_digests)
  ) THEN
    RAISE EXCEPTION 'credential_already_registered' USING ERRCODE = '23505';
  END IF;
  INSERT INTO identity_principals(status, display_label, metadata)
  VALUES (
    'active', NULLIF(btrim(p_display_label),''),
    jsonb_build_object('registration_provider',p_provider)
  ) RETURNING id INTO v_principal_id;
  SELECT linked.credential_id, linked.link_status, linked.conflict_id
  INTO v_credential_id, v_link_status, v_conflict_id
  FROM a1_link_identity_credential(
    v_principal_id, p_provider, 'production', p_credential_kind,
    p_subject_digests[1], NULL, NULL, v_principal_id, p_request_digest,
    '{}'::jsonb
  ) AS linked;
  IF v_link_status <> 'linked' OR v_conflict_id IS NOT NULL THEN
    RAISE EXCEPTION 'credential_already_registered' USING ERRCODE = '23505';
  END IF;
  IF p_email_digest IS NOT NULL THEN
    IF NOT a1_identity_digest_valid(p_email_digest)
       OR p_email_source NOT IN ('email','github','google') THEN
      RAISE EXCEPTION 'invalid_verified_email_material' USING ERRCODE = '22023';
    END IF;
    IF p_email_source = 'email' THEN
      INSERT INTO identity_account_emails(
        principal_id, normalized_email_digest, source_provider, verified_at
      ) VALUES (v_principal_id, p_email_digest, 'email', p_now);
      INSERT INTO identity_account_security(principal_id)
      VALUES (v_principal_id) ON CONFLICT (principal_id) DO NOTHING;
    ELSE
      PERFORM a1_sync_verified_oauth_email(
        v_principal_id, p_email_source, p_email_digest,
        v_principal_id, p_now, TRUE
      );
    END IF;
  END IF;
  RETURN QUERY SELECT v_principal_id, v_credential_id;
END
$$;

CREATE OR REPLACE FUNCTION a1_authenticate_identity_lifecycle_credential(
  p_provider TEXT,
  p_subject_digests TEXT[],
  p_now TIMESTAMPTZ
) RETURNS TABLE (authenticated_principal_id UUID, authenticated_credential_id UUID)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  RETURN QUERY
  WITH selected AS (
    SELECT p.id AS principal_id, c.id AS credential_id
    FROM identity_credentials AS c
    JOIN identity_principals AS p ON p.id = c.principal_id
    WHERE c.provider = p_provider
      AND c.provider_environment = 'production'
      AND c.subject_digest = ANY(p_subject_digests)
      AND c.status = 'active' AND c.login_enabled
      AND p.status = 'active'
    ORDER BY array_position(p_subject_digests, c.subject_digest)
    LIMIT 1
    FOR UPDATE OF c, p
  ), touched AS (
    UPDATE identity_credentials AS c
    SET last_authenticated_at = p_now, updated_at = p_now
    FROM selected
    WHERE c.id = selected.credential_id
    RETURNING selected.principal_id, c.id AS credential_id
  )
  SELECT touched.principal_id, touched.credential_id FROM touched;
END
$$;

CREATE OR REPLACE FUNCTION a1_project_identity_lifecycle_account(
  p_principal_id UUID
) RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT jsonb_build_object(
    'principal_id', p.id::text,
    'display_name', COALESCE(p.display_label,''),
    'status', p.status,
    'created_at', p.created_at,
    'updated_at', p.updated_at,
    'primary_email', CASE WHEN e.principal_id IS NULL THEN NULL ELSE
      jsonb_build_object(
        'present', TRUE, 'verified', TRUE, 'source_provider', e.source_provider
      ) END,
    'password_status', CASE WHEN s.password_secret_ref IS NULL THEN 'absent' ELSE 'set' END,
    'two_factor_status', COALESCE(s.two_factor_status,'disabled'),
    'two_factor_recommended', COALESCE(s.two_factor_recommended,TRUE),
    'credentials', COALESCE((
      SELECT jsonb_agg(jsonb_build_object(
        'credential_id', c.id::text, 'provider', c.provider,
        'credential_kind', c.credential_kind,
        'verified', c.verified_at IS NOT NULL,
        'can_login', c.login_enabled, 'linked_at', c.created_at,
        'last_used_at', c.last_authenticated_at
      ) ORDER BY c.created_at, c.id)
      FROM identity_credentials AS c
      WHERE c.principal_id = p.id AND c.status = 'active'
    ), '[]'::jsonb),
    'memberships', COALESCE((
      SELECT jsonb_agg(m.item ORDER BY m.tenant_id, m.project_id, m.membership_id)
      FROM (
        SELECT om.organization_id::text AS tenant_id, ''::text AS project_id,
          om.id::text AS membership_id,
          jsonb_build_object(
            'membership_id',om.id::text,'tenant_id',om.organization_id::text,
            'project_id','','role',om.role,'created_at',om.created_at,
            'updated_at',om.updated_at
          ) AS item
        FROM identity_organization_memberships AS om
        WHERE om.principal_id=p.id AND om.status='active'
        UNION ALL
        SELECT pm.organization_id::text, pm.project_id::text, pm.id::text,
          jsonb_build_object(
            'membership_id',pm.id::text,'tenant_id',pm.organization_id::text,
            'project_id',pm.project_id::text,'role',pm.role,
            'created_at',pm.created_at,'updated_at',pm.updated_at
          )
        FROM identity_project_memberships AS pm
        WHERE pm.principal_id=p.id AND pm.status='active'
      ) AS m
    ), '[]'::jsonb)
  )
  FROM identity_principals AS p
  LEFT JOIN identity_account_emails AS e ON e.principal_id=p.id
  LEFT JOIN identity_account_security AS s ON s.principal_id=p.id
  WHERE p.id=p_principal_id
$$;

REVOKE ALL ON FUNCTION a1_issue_identity_lifecycle_receipt(
  TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,BYTEA,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_lock_identity_lifecycle_receipt(TEXT[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_consume_identity_lifecycle_receipt(
  TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_register_identity_lifecycle_credential(
  TEXT,TEXT,TEXT[],TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_authenticate_identity_lifecycle_credential(
  TEXT,TEXT[],TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_project_identity_lifecycle_account(UUID) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    REVOKE ALL ON identity_lifecycle_receipts, identity_lifecycle_receipt_audit
      FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_issue_identity_lifecycle_receipt(
      TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,BYTEA,TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_lock_identity_lifecycle_receipt(TEXT[])
      TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_consume_identity_lifecycle_receipt(
      TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_register_identity_lifecycle_credential(
      TEXT,TEXT,TEXT[],TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_authenticate_identity_lifecycle_credential(
      TEXT,TEXT[],TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_project_identity_lifecycle_account(UUID)
      TO a1_runtime;
  END IF;
END
$$;

COMMIT;
