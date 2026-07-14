-- Atomically complete an existing-account credential link from a sealed
-- lifecycle proof. Raw provider subjects and verified email values remain in
-- the Go transaction coordinator; PostgreSQL receives only keyed digests.
BEGIN;

ALTER TABLE identity_lifecycle_receipts
  DROP CONSTRAINT IF EXISTS identity_lifecycle_receipts_operation_check;
ALTER TABLE identity_lifecycle_receipts
  ADD CONSTRAINT identity_lifecycle_receipts_operation_check
  CHECK (operation IN ('registration','login','credential_link'));

ALTER TABLE identity_lifecycle_receipt_audit
  DROP CONSTRAINT IF EXISTS identity_lifecycle_receipt_audit_operation_check;
ALTER TABLE identity_lifecycle_receipt_audit
  ADD CONSTRAINT identity_lifecycle_receipt_audit_operation_check
  CHECK (operation IN ('registration','login','credential_link'));

ALTER TABLE identity_lifecycle_receipts
  ADD COLUMN IF NOT EXISTS link_idempotency_digest TEXT,
  ADD COLUMN IF NOT EXISTS link_request_digest TEXT,
  ADD COLUMN IF NOT EXISTS link_result_id UUID
    REFERENCES identity_credentials(id) ON DELETE RESTRICT;

ALTER TABLE identity_lifecycle_receipts
  DROP CONSTRAINT IF EXISTS identity_lifecycle_receipts_link_replay_check;
ALTER TABLE identity_lifecycle_receipts
  ADD CONSTRAINT identity_lifecycle_receipts_link_replay_check CHECK (
    (link_idempotency_digest IS NULL AND link_request_digest IS NULL
      AND link_result_id IS NULL)
    OR
    (operation='credential_link'
      AND a1_identity_digest_valid(link_idempotency_digest)
      AND a1_identity_digest_valid(link_request_digest)
      AND link_result_id IS NOT NULL)
  );

CREATE OR REPLACE FUNCTION a1_lock_identity_credential_link_receipt(
  p_receipt_digests TEXT[]
) RETURNS TABLE (
  receipt_digest TEXT,
  operation TEXT,
  provider TEXT,
  tenant_scope TEXT,
  project_scope TEXT,
  expires_at TIMESTAMPTZ,
  consumed_at TIMESTAMPTZ,
  proof_nonce BYTEA,
  proof_key_version TEXT,
  proof_ciphertext BYTEA
)
LANGUAGE sql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
  SELECT
    r.receipt_digest,
    r.operation,
    r.provider,
    r.tenant_scope,
    r.project_scope,
    r.expires_at,
    r.consumed_at,
    r.proof_nonce,
    r.proof_key_version,
    r.proof_ciphertext
  FROM identity_lifecycle_receipts AS r
  WHERE r.receipt_digest=ANY(p_receipt_digests)
  ORDER BY array_position(p_receipt_digests,r.receipt_digest)
  LIMIT 1
  FOR UPDATE
$$;

CREATE OR REPLACE FUNCTION a1_complete_identity_credential_link(
  p_organization_id UUID,
  p_project_id UUID,
  p_lifecycle_receipt_digest TEXT,
  p_principal_id UUID,
  p_provider TEXT,
  p_credential_kind TEXT,
  p_subject_digest TEXT,
  p_email_digest TEXT,
  p_session_digest TEXT,
  p_mutation_ticket_digest TEXT,
  p_step_up_receipt_digest TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
) RETURNS TABLE (
  linked_credential_id UUID,
  credential_added BOOLEAN,
  linked_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_receipt identity_lifecycle_receipts%ROWTYPE;
  v_ticket identity_security_mutation_tickets%ROWTYPE;
  v_existing_email identity_account_emails%ROWTYPE;
  v_credential_id UUID;
  v_link_status TEXT;
  v_conflict_id UUID;
  v_credential_existed BOOLEAN;
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_identity_session_assert_scope(
    p_organization_id,p_project_id,p_principal_id
  );
  IF p_provider NOT IN ('email','github','google','wechat','qq','alipay')
     OR p_credential_kind NOT IN ('email_otp','phone_otp','federated')
     OR NOT a1_identity_digest_valid(p_lifecycle_receipt_digest)
     OR NOT a1_identity_digest_valid(p_subject_digest)
     OR (p_email_digest IS NOT NULL
       AND NOT a1_identity_digest_valid(p_email_digest))
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_mutation_ticket_digest)
     OR NOT a1_identity_digest_valid(p_step_up_receipt_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity_credential_link_invalid' USING ERRCODE='22023';
  END IF;

  SELECT * INTO v_receipt FROM identity_lifecycle_receipts
   WHERE receipt_digest=p_lifecycle_receipt_digest FOR UPDATE;
  IF NOT FOUND
     OR v_receipt.operation<>'credential_link'
     OR v_receipt.provider <> (
       CASE WHEN p_provider='email' THEN 'local' ELSE p_provider END
     )
     OR v_receipt.tenant_scope<>p_organization_id::text
     OR v_receipt.project_scope<>p_project_id::text THEN
    RAISE EXCEPTION 'identity_credential_link_proof_rejected' USING ERRCODE='42501';
  END IF;
  IF v_receipt.consumed_at IS NOT NULL THEN
    IF v_receipt.link_idempotency_digest=p_idempotency_digest
       AND v_receipt.link_request_digest=p_request_digest
       AND v_receipt.link_result_id IS NOT NULL THEN
      RETURN QUERY
      SELECT c.id,FALSE,c.created_at
        FROM identity_credentials c
       WHERE c.id=v_receipt.link_result_id
         AND c.principal_id=p_principal_id
         AND c.provider=p_provider;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'identity_credential_link_replay_invalid'
          USING ERRCODE='42501';
      END IF;
      RETURN;
    END IF;
    RAISE EXCEPTION 'identity_credential_link_idempotency_conflict'
      USING ERRCODE='23505';
  END IF;
  IF v_receipt.expires_at<=v_now THEN
    RAISE EXCEPTION 'identity_credential_link_proof_expired' USING ERRCODE='42501';
  END IF;

  SELECT * INTO v_ticket FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_mutation_ticket_digest FOR UPDATE;
  IF NOT FOUND OR v_ticket.operation<>'credential_bind'
     OR v_ticket.principal_id<>p_principal_id
     OR v_ticket.actor_principal_id<>p_principal_id
     OR v_ticket.step_up_receipt_digest<>p_step_up_receipt_digest
     OR v_ticket.context_digest<>p_request_digest
     OR v_ticket.consumed_at IS NOT NULL
     OR v_ticket.expires_at<=v_now THEN
    RAISE EXCEPTION 'identity_credential_link_authorization_rejected'
      USING ERRCODE='42501';
  END IF;

  PERFORM a1_assert_recent_identity_authentication(
    p_organization_id,p_project_id,p_principal_id,p_session_digest,600,'aal1'
  );
  IF NOT a1_consume_identity_security_receipt(
    p_step_up_receipt_digest,p_principal_id,'credential_bind',
    p_request_digest,v_now
  ) THEN
    RAISE EXCEPTION 'identity_credential_link_step_up_unavailable'
      USING ERRCODE='42501';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM identity_credentials
    WHERE provider=p_provider
      AND provider_environment='production'
      AND subject_digest=p_subject_digest
      AND principal_id=p_principal_id
  ) INTO v_credential_existed;

  SELECT linked.credential_id,linked.link_status,linked.conflict_id
    INTO v_credential_id,v_link_status,v_conflict_id
    FROM a1_link_identity_credential(
      p_principal_id,p_provider,'production',p_credential_kind,
      p_subject_digest,NULL,NULL,p_principal_id,p_request_digest,p_metadata
    ) AS linked;
  IF v_link_status<>'linked' OR v_conflict_id IS NOT NULL
     OR v_credential_id IS NULL THEN
    RAISE EXCEPTION 'identity_credential_link_conflict' USING ERRCODE='23505';
  END IF;

  IF p_email_digest IS NOT NULL THEN
    SELECT * INTO v_existing_email FROM identity_account_emails
     WHERE principal_id=p_principal_id
        OR normalized_email_digest=p_email_digest
     ORDER BY (principal_id=p_principal_id) DESC
     LIMIT 1 FOR UPDATE;
    IF FOUND AND (
      v_existing_email.principal_id<>p_principal_id
      OR v_existing_email.normalized_email_digest<>p_email_digest
    ) THEN
      RAISE EXCEPTION 'canonical_email_conflict' USING ERRCODE='23505';
    END IF;
    IF p_provider='email' THEN
      INSERT INTO identity_account_emails(
        principal_id,normalized_email_digest,source_provider,verified_at
      ) VALUES (p_principal_id,p_email_digest,'email',v_now)
      ON CONFLICT (principal_id) DO UPDATE SET
        verified_at=EXCLUDED.verified_at,updated_at=v_now
      WHERE identity_account_emails.normalized_email_digest=p_email_digest;
      INSERT INTO identity_account_security(principal_id)
      VALUES(p_principal_id) ON CONFLICT(principal_id) DO NOTHING;
    ELSIF p_provider IN ('github','google') THEN
      PERFORM a1_sync_verified_oauth_email(
        p_principal_id,p_provider,p_email_digest,p_principal_id,v_now,TRUE
      );
    END IF;
  END IF;

  UPDATE identity_security_mutation_tickets SET consumed_at=v_now
   WHERE ticket_digest=p_mutation_ticket_digest AND consumed_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity_credential_link_ticket_unavailable'
      USING ERRCODE='42501';
  END IF;

  UPDATE identity_lifecycle_receipts SET
    consumed_at=v_now,consume_outcome='success',
    link_idempotency_digest=p_idempotency_digest,
    link_request_digest=p_request_digest,link_result_id=v_credential_id
   WHERE receipt_digest=p_lifecycle_receipt_digest AND consumed_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity_credential_link_proof_unavailable'
      USING ERRCODE='42501';
  END IF;
  INSERT INTO identity_lifecycle_receipt_audit(
    receipt_digest,operation,provider,tenant_scope,project_scope,outcome,occurred_at
  ) VALUES (
    p_lifecycle_receipt_digest,'credential_link',
    CASE WHEN p_provider='email' THEN 'local' ELSE p_provider END,
    p_organization_id::text,p_project_id::text,'consumed',v_now
  );
  PERFORM a1_identity_write_event(
    p_principal_id,p_organization_id,p_project_id,p_principal_id,
    'identity.credential.link.completed','identity_credential',
    v_credential_id,p_request_digest,
    p_metadata || jsonb_build_object('event_digest',p_event_digest)
  );
  RETURN QUERY SELECT v_credential_id,NOT v_credential_existed,v_now;
END
$$;

REVOKE ALL ON FUNCTION a1_lock_identity_credential_link_receipt(TEXT[])
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_complete_identity_credential_link(
  UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
    GRANT EXECUTE ON FUNCTION a1_lock_identity_credential_link_receipt(TEXT[])
      TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_complete_identity_credential_link(
      UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB
    ) TO a1_runtime;
  END IF;
END
$$;

COMMIT;
