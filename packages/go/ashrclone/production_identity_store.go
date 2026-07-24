package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode"

	"github.com/lib/pq"
)

const (
	IdentityRuntimePostgres = "postgres"
	IdentityRuntimeMemory   = "memory"
)

const (
	defaultIdentitySessionKeyVersion  = "v1"
	identitySessionBearerPrefix       = "ashr_session"
	identityRefreshBearerPrefix       = "ashr_refresh"
	identitySessionNonceBytes         = 32
	defaultIdentitySessionSQLTimeout  = 5 * time.Second
	defaultIdentitySessionLockTimeout = 2 * time.Second
	maxIdentitySessionSQLTimeout      = 30 * time.Second
)

const productionIdentityReadinessQuery = `
SELECT to_regclass('public.identity_principals') IS NOT NULL
   AND to_regclass('public.identity_credentials') IS NOT NULL
   AND to_regclass('public.identity_sessions') IS NOT NULL
   AND to_regclass('public.oauth_runtime_transactions') IS NOT NULL
   AND to_regclass('public.oauth_account_connections') IS NOT NULL
   AND to_regclass('public.oauth_revocation_outbox') IS NOT NULL
   AND to_regclass('public.identity_verification_challenges') IS NOT NULL
   AND to_regclass('public.identity_verification_receipts') IS NOT NULL
   AND to_regclass('public.identity_verification_delivery_outbox') IS NOT NULL
   AND to_regclass('public.identity_verification_abuse_budgets') IS NOT NULL
   AND to_regclass('public.identity_verification_audit_events') IS NOT NULL
   AND to_regclass('public.identity_session_lifecycle_operations') IS NOT NULL
   AND to_regclass('public.identity_verification_delivery_redrive_audit') IS NOT NULL
   AND to_regclass('public.identity_lifecycle_receipts') IS NOT NULL
   AND to_regclass('public.identity_lifecycle_receipt_audit') IS NOT NULL
   AND to_regclass(
     'public.identity_credential_link_replay_purge_audit'
   ) IS NOT NULL
   AND EXISTS (
     SELECT 1
     FROM pg_catalog.pg_attribute
     WHERE attrelid='public.identity_lifecycle_receipts'::regclass
       AND attname='lookup_key_version'
       AND attnotnull
       AND NOT attisdropped
   )
   AND EXISTS (
     SELECT 1
     FROM pg_catalog.pg_attribute
     WHERE attrelid='public.identity_lifecycle_receipts'::regclass
       AND attname='replay_retain_until'
       AND NOT attisdropped
   )
   AND to_regclass('public.identity_account_security') IS NOT NULL
   AND to_regclass('public.identity_security_receipts') IS NOT NULL
   AND to_regclass('public.identity_security_mutation_tickets') IS NOT NULL
   AND to_regclass('public.identity_security_mutation_idempotency') IS NOT NULL
   AND to_regclass('public.oauth_first_login_operations') IS NOT NULL
   AND to_regprocedure(
     'public.a1_complete_oauth_identity_callback(uuid,uuid,uuid,text,text,text,text,text,text,text,text,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_disconnect_oauth_identity_credential(uuid,uuid,uuid,uuid,uuid,text,text,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_authenticate_identity_session_digest(text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_issue_identity_verification_challenge_with_delivery(uuid,uuid,uuid,text,text,text,text,text,text,timestamp with time zone,integer,integer,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_verify_identity_verification_attempt(uuid,uuid,text,text,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_bind_verified_identity_credential(uuid,uuid,text,uuid,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_bind_verified_identity_credential_authorized(uuid,uuid,text,uuid,text,text,text,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_assert_recent_identity_authentication(uuid,uuid,uuid,text,integer,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_issue_identity_session_with_refresh(uuid,uuid,uuid,uuid,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_rotate_identity_session_refresh(uuid,uuid,uuid,text,bigint,text,text,timestamp with time zone,timestamp with time zone,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_rotate_identity_session_refresh_from_digest(uuid,uuid,text,text,text,timestamp with time zone,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_revoke_identity_session(uuid,uuid,uuid,text,uuid,bigint,integer,text,text,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_revoke_all_identity_sessions(uuid,uuid,uuid,text,boolean,integer,text,text,text)'
   ) IS NOT NULL
    AND to_regprocedure(
      'public.a1_register_with_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,text,jsonb)'
    ) IS NOT NULL
    AND to_regprocedure(
      'public.a1_login_with_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
    ) IS NOT NULL
    AND to_regprocedure(
      'public.a1_recover_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_complete_oauth_first_login_with_refresh(uuid,uuid,text,text[],text[],text,text,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_claim_identity_delivery_outbox(uuid,uuid,text,integer,bigint,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_heartbeat_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,bigint,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_complete_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_retry_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_dead_letter_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_redrive_identity_delivery_outbox(uuid,uuid,uuid,bigint,text,text,text,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_project_identity_lifecycle_account(uuid)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_issue_identity_lifecycle_receipt(text,text,text,text,text,bytea,text,text,bytea,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_identity_lifecycle_lookup_retirement_readiness(text,text[],timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_purge_identity_credential_link_replays(timestamp with time zone,integer,text,text,text,text,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_mutate_account_password(uuid,text,text,text,text,text,uuid,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_begin_totp_enrollment(uuid,text,text,text,text,uuid,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_confirm_totp_enrollment(uuid,text,text,text,integer,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_project_account_security(uuid)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamp with time zone)'
   ) IS NOT NULL
    AND to_regprocedure(
      'public.a1_resolve_identity_security_mutation_ticket(text,text,text,timestamp with time zone)'
    ) IS NOT NULL
    AND to_regprocedure(
      'public.a1_execute_identity_security_mutation(text,text,text)'
    ) IS NOT NULL
    AND to_regprocedure(
      'public.a1_resolve_identity_security_mutation_ticket(text,text,text,uuid,timestamp with time zone)'
    ) IS NOT NULL
    AND to_regprocedure(
      'public.a1_execute_identity_security_mutation(text,text,text,uuid)'
    ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamp with time zone,timestamp with time zone)'
   ) IS NULL
   AND to_regprocedure(
     'public.a1_execute_identity_security_mutation(text,text,text,timestamp with time zone)'
   ) IS NULL
   AND has_schema_privilege(current_user, 'public', 'USAGE')
   AND NOT has_schema_privilege(current_user, 'public', 'CREATE')
   AND NOT has_schema_privilege('public', 'public', 'CREATE')
   AND (
     SELECT NOT r.rolsuper AND NOT r.rolbypassrls
       FROM pg_catalog.pg_roles r
      WHERE r.rolname = current_user
   )
   AND NOT has_function_privilege(
     current_user,
     'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamp with time zone)',
     'EXECUTE'
   )
    AND NOT has_function_privilege(
      current_user,
      'public.a1_resolve_identity_security_mutation_ticket(text,text,text,timestamp with time zone)',
      'EXECUTE'
    )
    AND NOT has_function_privilege(
      current_user,
      'public.a1_execute_identity_security_mutation(text,text,text)',
      'EXECUTE'
    )
    AND has_function_privilege(
      current_user,
      'public.a1_resolve_identity_security_mutation_ticket(text,text,text,uuid,timestamp with time zone)',
      'EXECUTE'
    )
    AND has_function_privilege(
      current_user,
      'public.a1_execute_identity_security_mutation(text,text,text,uuid)',
      'EXECUTE'
    )
   AND has_function_privilege(
     current_user,
     'public.a1_project_account_security(uuid)',
     'EXECUTE'
   )
   AND has_function_privilege(
     current_user,
     'public.a1_bind_verified_identity_credential_authorized(uuid,uuid,text,uuid,text,text,text,text,text,text,jsonb)',
     'EXECUTE'
    )
    AND has_function_privilege(
      current_user,
      'public.a1_register_with_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,text,jsonb)',
      'EXECUTE'
    )
    AND has_function_privilege(
      current_user,
      'public.a1_login_with_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)',
      'EXECUTE'
    )
    AND has_function_privilege(
      current_user,
      'public.a1_recover_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)',
      'EXECUTE'
    )
    AND has_function_privilege(
      current_user,
      'public.a1_complete_oauth_first_login_with_refresh(uuid,uuid,text,text[],text[],text,text,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)',
      'EXECUTE'
    )
    AND NOT has_function_privilege(
      'public',
      'public.a1_complete_oauth_first_login_with_refresh(uuid,uuid,text,text[],text[],text,text,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)',
      'EXECUTE'
    )
    AND NOT has_function_privilege(
      'public',
      'public.a1_complete_oauth_first_login_with_refresh(uuid,uuid,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)',
      'EXECUTE'
    )
    AND NOT has_function_privilege(
      current_user,
      'public.a1_login_with_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)',
      'EXECUTE'
    )
    AND NOT has_function_privilege(
      current_user,
      'public.a1_recover_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)',
      'EXECUTE'
    )
   AND NOT has_function_privilege(
     current_user,
     'public.a1_bind_verified_identity_credential(uuid,uuid,text,uuid,text,text,text,jsonb)',
     'EXECUTE'
   )
   AND NOT has_function_privilege(
     current_user,
     'public.a1_consume_identity_security_receipt(text,uuid,text,text,timestamp with time zone)',
     'EXECUTE'
   )
   AND NOT has_function_privilege(
     current_user,
     'public.a1_mutate_account_password(uuid,text,text,text,text,text,uuid,timestamp with time zone)',
     'EXECUTE'
   )
   AND NOT has_function_privilege(
     current_user,
     'public.a1_begin_totp_enrollment(uuid,text,text,text,text,uuid,timestamp with time zone)',
     'EXECUTE'
   )
   AND NOT has_function_privilege(
     current_user,
     'public.a1_confirm_totp_enrollment(uuid,text,text,text,integer,timestamp with time zone)',
     'EXECUTE'
   )
   AND NOT has_function_privilege(
     current_user,
     'public.a1_set_account_two_factor(uuid,boolean,uuid,timestamp with time zone,boolean)',
     'EXECUTE'
   )
   AND has_function_privilege(
     current_user,
     'public.a1_purge_identity_credential_link_replays(timestamp with time zone,integer,text,text,text,text,timestamp with time zone)',
     'EXECUTE'
   )
    AND NOT has_table_privilege(
      current_user,
      'public.identity_lifecycle_receipts',
      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
    )
    AND NOT EXISTS (
      SELECT 1
        FROM unnest(ARRAY[
          'public.identity_verification_cooldowns'::regclass,
          'public.identity_verification_challenges'::regclass,
          'public.identity_verification_receipts'::regclass,
          'public.identity_verification_delivery_outbox'::regclass,
          'public.identity_verification_abuse_budgets'::regclass,
          'public.identity_verification_audit_events'::regclass
        ]) AS verification_table(table_oid)
       WHERE has_table_privilege(
               current_user,
               verification_table.table_oid,
               'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
             )
          OR has_table_privilege(
               'public',
               verification_table.table_oid,
               'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
             )
          OR has_any_column_privilege(
               current_user,
               verification_table.table_oid,
               'SELECT,INSERT,UPDATE,REFERENCES'
             )
          OR has_any_column_privilege(
               'public',
               verification_table.table_oid,
               'SELECT,INSERT,UPDATE,REFERENCES'
             )
    )
   AND NOT has_table_privilege(
     current_user,
     'public.identity_credential_link_replay_purge_audit',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_any_column_privilege(
     current_user,
     'public.identity_credential_link_replay_purge_audit',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_table_privilege(
     'public',
     'public.identity_credential_link_replay_purge_audit',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_any_column_privilege(
     'public',
     'public.identity_credential_link_replay_purge_audit',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND (
     SELECT c.relrowsecurity AND c.relforcerowsecurity
     FROM pg_catalog.pg_class c
     WHERE c.oid=
       'public.identity_credential_link_replay_purge_audit'::regclass
   )
   AND (
     SELECT p.prosecdef
       AND pg_catalog.pg_get_userbyid(p.proowner) <> current_user
       AND NOT pg_catalog.pg_has_role(current_user,p.proowner,'MEMBER')
       AND EXISTS (
         SELECT 1
         FROM unnest(COALESCE(p.proconfig,ARRAY[]::TEXT[])) setting
         WHERE regexp_replace(setting,'\s','','g')=
           'search_path=pg_catalog,public,pg_temp'
       )
     FROM pg_catalog.pg_proc p
     WHERE p.oid=to_regprocedure(
       'public.a1_purge_identity_credential_link_replays(timestamp with time zone,integer,text,text,text,text,timestamp with time zone)'
     )
   )
   AND NOT has_table_privilege(
     current_user,
     'public.identity_account_security',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_table_privilege(
     current_user,
     'public.identity_security_receipts',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_table_privilege(
     current_user,
     'public.identity_security_mutation_tickets',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_table_privilege(
     current_user,
     'public.identity_security_mutation_idempotency',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_any_column_privilege(
     current_user,
     'public.identity_account_security',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_any_column_privilege(
     current_user,
     'public.identity_security_receipts',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_any_column_privilege(
     current_user,
     'public.identity_security_mutation_tickets',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_any_column_privilege(
     current_user,
     'public.identity_security_mutation_idempotency',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_table_privilege(
     'public',
     'public.identity_account_security',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_table_privilege(
     'public',
     'public.identity_security_receipts',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_table_privilege(
     'public',
     'public.identity_security_mutation_tickets',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_table_privilege(
     'public',
     'public.identity_security_mutation_idempotency',
     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
   )
   AND NOT has_any_column_privilege(
     'public',
     'public.identity_account_security',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_any_column_privilege(
     'public',
     'public.identity_security_receipts',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_any_column_privilege(
     'public',
     'public.identity_security_mutation_tickets',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT has_any_column_privilege(
     'public',
     'public.identity_security_mutation_idempotency',
     'SELECT,INSERT,UPDATE,REFERENCES'
   )
   AND NOT EXISTS (
     SELECT 1
       FROM unnest(ARRAY[
         to_regprocedure(
           'public.a1_consume_identity_security_receipt(text,uuid,text,text,timestamp with time zone)'
         ),
         to_regprocedure(
           'public.a1_mutate_account_password(uuid,text,text,text,text,text,uuid,timestamp with time zone)'
         ),
         to_regprocedure(
           'public.a1_begin_totp_enrollment(uuid,text,text,text,text,uuid,timestamp with time zone)'
         ),
         to_regprocedure(
           'public.a1_confirm_totp_enrollment(uuid,text,text,text,integer,timestamp with time zone)'
         ),
         to_regprocedure(
           'public.a1_set_account_two_factor(uuid,boolean,uuid,timestamp with time zone,boolean)'
         ),
         to_regprocedure(
           'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamp with time zone)'
         ),
         to_regprocedure(
           'public.a1_resolve_identity_security_mutation_ticket(text,text,text,timestamp with time zone)'
         ),
          to_regprocedure(
            'public.a1_execute_identity_security_mutation(text,text,text)'
          ),
          to_regprocedure(
            'public.a1_resolve_identity_security_mutation_ticket(text,text,text,uuid,timestamp with time zone)'
          ),
          to_regprocedure(
            'public.a1_execute_identity_security_mutation(text,text,text,uuid)'
          ),
         to_regprocedure('public.a1_project_account_security(uuid)'),
         to_regprocedure(
           'public.a1_bind_verified_identity_credential_authorized(uuid,uuid,text,uuid,text,text,text,text,text,text,jsonb)'
         ),
         to_regprocedure(
           'public.a1_bind_verified_identity_credential(uuid,uuid,text,uuid,text,text,text,jsonb)'
         )
       ]) function_oid
      WHERE function_oid IS NULL
         OR has_function_privilege('public', function_oid, 'EXECUTE')
   )
   AND (
     SELECT count(*) = 3
       FROM pg_catalog.pg_class c
       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname IN (
          'identity_security_receipts',
          'identity_security_mutation_tickets',
          'identity_security_mutation_idempotency'
        )
        AND c.relrowsecurity
        AND c.relforcerowsecurity
   )
   AND (
     SELECT count(*) = 3
        AND count(*) FILTER (
          WHERE p.policyname = p.tablename || '_self'
            AND p.permissive = 'PERMISSIVE'
            AND p.roles = ARRAY['public'::name]
        ) = 3
       FROM pg_catalog.pg_policies p
      WHERE p.schemaname = 'public'
        AND p.tablename IN (
          'identity_security_receipts',
          'identity_security_mutation_tickets',
          'identity_security_mutation_idempotency'
        )
   )
    AND (
      SELECT count(*) = 5
       FROM pg_catalog.pg_proc p
      WHERE p.oid IN (
        to_regprocedure(
          'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamp with time zone)'
        ),
          to_regprocedure(
            'public.a1_resolve_identity_security_mutation_ticket(text,text,text,uuid,timestamp with time zone)'
          ),
          to_regprocedure(
            'public.a1_execute_identity_security_mutation(text,text,text,uuid)'
        ),
        to_regprocedure('public.a1_project_account_security(uuid)'),
        to_regprocedure(
          'public.a1_bind_verified_identity_credential_authorized(uuid,uuid,text,uuid,text,text,text,text,text,text,jsonb)'
        )
        )
        AND p.prosecdef
        AND pg_catalog.pg_get_userbyid(p.proowner) <> current_user
        AND NOT pg_catalog.pg_has_role(current_user, p.proowner, 'MEMBER')
        AND EXISTS (
          SELECT 1
            FROM unnest(COALESCE(p.proconfig, ARRAY[]::text[])) setting
           WHERE regexp_replace(setting, '\s', '', 'g') =
             'search_path=pg_catalog,public,pg_temp'
        )
    )
    AND (
      SELECT count(*) = 3
        FROM pg_catalog.pg_proc p
       WHERE p.oid IN (
         to_regprocedure(
           'public.a1_register_with_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,text,jsonb)'
         ),
         to_regprocedure(
           'public.a1_login_with_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
         ),
         to_regprocedure(
           'public.a1_recover_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
         )
       )
         AND p.prosecdef
         AND pg_catalog.pg_get_userbyid(p.proowner) <> current_user
         AND NOT pg_catalog.pg_has_role(current_user, p.proowner, 'MEMBER')
         AND EXISTS (
           SELECT 1
             FROM unnest(COALESCE(p.proconfig, ARRAY[]::text[])) setting
            WHERE regexp_replace(setting, '\s', '', 'g') =
              'search_path=pg_catalog,public,pg_temp'
         )
    )
    AND NOT has_table_privilege(
      current_user,
      'public.oauth_first_login_operations',
      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
    )
    AND NOT has_any_column_privilege(
      current_user,
      'public.oauth_first_login_operations',
      'SELECT,INSERT,UPDATE,REFERENCES'
    )
    AND NOT has_table_privilege(
      'public',
      'public.oauth_first_login_operations',
      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
    )
    AND NOT has_any_column_privilege(
      'public',
      'public.oauth_first_login_operations',
      'SELECT,INSERT,UPDATE,REFERENCES'
    )
    AND (
      SELECT c.relrowsecurity AND c.relforcerowsecurity
        FROM pg_catalog.pg_class c
       WHERE c.oid = to_regclass('public.oauth_first_login_operations')
    )
    AND (
      SELECT p.prosecdef
        AND pg_catalog.pg_get_userbyid(p.proowner) <> current_user
        AND NOT pg_catalog.pg_has_role(current_user, p.proowner, 'MEMBER')
        AND EXISTS (
          SELECT 1
            FROM unnest(COALESCE(p.proconfig, ARRAY[]::TEXT[])) setting
           WHERE regexp_replace(setting, '\s', '', 'g') =
             'search_path=pg_catalog,public,pg_temp'
        )
        FROM pg_catalog.pg_proc p
       WHERE p.oid = to_regprocedure(
         'public.a1_complete_oauth_first_login_with_refresh(uuid,uuid,text,text[],text[],text,text,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
       )
    )
`

type ProductionIdentityStore struct {
	db               *sql.DB
	sessionTokens    *identitySessionTokenCodec
	now              func() time.Time
	sqlTimeout       time.Duration
	statementTimeout time.Duration
	lockTimeout      time.Duration
	lifecycleKeys    *identityLifecycleKeyring
}

type IdentitySessionHMACKey struct {
	Version  string
	Key      []byte
	RetireAt time.Time
}

type ProductionIdentityStoreOptions struct {
	DB                                 *sql.DB
	SessionKey                         []byte
	SessionKeyVersion                  string
	PreviousSessionKeys                []IdentitySessionHMACKey
	LegacySessionKeyVersion            string
	Random                             io.Reader
	Now                                func() time.Time
	RequirePreviousKeyRetention        bool
	RefreshTokenLifetime               time.Duration
	PreviousKeyRetentionMargin         time.Duration
	SQLTimeout                         time.Duration
	StatementTimeout                   time.Duration
	LockTimeout                        time.Duration
	LifecycleReceiptKey                []byte
	LifecycleReceiptKeyVersion         string
	PreviousLifecycleReceiptKeys       []IdentityLifecycleEncryptionKey
	LifecycleReceiptLookupKey          []byte
	LifecycleReceiptLookupKeyVersion   string
	PreviousLifecycleReceiptLookupKeys []IdentityLifecycleLookupKey
}

type IdentityLifecycleEncryptionKey struct {
	Version string
	Key     []byte
}

// IdentityLifecycleLookupKey retains only the keyed receipt-lookup namespace.
// Keeping lookup keys independent from proof-encryption keys allows completed
// idempotent replays to remain locatable after an old encryption key retires.
type IdentityLifecycleLookupKey struct {
	Version string
	Key     []byte
}

type IdentityLifecycleLookupRetirementReadiness struct {
	SchemaVersion                  string     `json:"schema_version"`
	ActiveVersion                  string     `json:"active_version"`
	RetiringVersion                string     `json:"retiring_version"`
	Ready                          bool       `json:"ready"`
	LegacyUnversionedLiveReceipts  int64      `json:"legacy_unversioned_live_receipts"`
	LegacyUnversionedReplayRecords int64      `json:"legacy_unversioned_replay_records"`
	RetiringLiveReceipts           int64      `json:"retiring_live_receipts"`
	RetiringReplayRecords          int64      `json:"retiring_replay_records"`
	UnreachableLiveReceipts        int64      `json:"unreachable_live_receipts"`
	UnreachableReplayRecords       int64      `json:"unreachable_replay_records"`
	LiveReceiptsRequiredUntil      *time.Time `json:"live_receipts_required_until"`
	ReplayRetentionRequired        bool       `json:"replay_retention_required"`
}

// IdentityCredentialLinkReplayPurgeRequest is the A3-safe maintenance
// contract for deleting completed credential-link replay rows after their
// fixed retention deadline. The idempotency key is keyed before PostgreSQL.
type IdentityCredentialLinkReplayPurgeRequest struct {
	Cutoff         time.Time
	MaxRows        int
	Actor          string
	Reason         string
	IdempotencyKey string
}

// IdentityCredentialLinkReplayPurgeReceipt exposes only aggregate maintenance
// evidence. It intentionally contains no receipt, proof, subject, credential,
// session, ticket, email, or key material.
type IdentityCredentialLinkReplayPurgeReceipt struct {
	SchemaVersion       string           `json:"schema_version"`
	PurgeID             string           `json:"purge_id"`
	Cutoff              time.Time        `json:"cutoff"`
	MaxRows             int              `json:"max_rows"`
	PurgedRows          int64            `json:"purged_rows"`
	LookupVersionCounts map[string]int64 `json:"lookup_version_counts"`
	CompletedAt         time.Time        `json:"completed_at"`
}

type IdentitySessionKeyRetirement struct {
	Version          string    `json:"version"`
	RetireAt         time.Time `json:"retire_at"`
	RequiredUntil    time.Time `json:"required_until"`
	RetentionReady   bool      `json:"retention_ready"`
	RemainingSeconds int64     `json:"remaining_seconds"`
}

type IdentitySessionKeyringReadiness struct {
	ActiveVersion string                         `json:"active_version"`
	LegacyVersion string                         `json:"legacy_version"`
	Ready         bool                           `json:"ready"`
	PreviousKeys  []IdentitySessionKeyRetirement `json:"previous_keys"`
}

// GetIdentityAccount projects the canonical PostgreSQL identity account.
// Authentication and URL ownership checks happen at the HTTP boundary; this
// method never falls back to process-local identity state.
func (store *ProductionIdentityStore) GetIdentityAccount(
	ctx context.Context,
	accountID string,
) (IdentityAccountDTO, error) {
	if store == nil || store.db == nil {
		return IdentityAccountDTO{}, ErrIdentityStoreUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	if !validPostgresIdentityVerificationUUID(accountID) {
		return IdentityAccountDTO{}, ErrIdentityAccountNotFound
	}
	queryCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(queryCtx, &sql.TxOptions{
		Isolation: sql.LevelReadCommitted,
		ReadOnly:  true,
	})
	if err != nil {
		return IdentityAccountDTO{}, fmt.Errorf("begin identity account projection: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if _, err = tx.ExecContext(queryCtx, `
SELECT set_config('statement_timeout', $1, true),
       set_config('lock_timeout', $2, true)
`, fmt.Sprintf("%dms", store.statementTimeout.Milliseconds()),
		fmt.Sprintf("%dms", store.lockTimeout.Milliseconds())); err != nil {
		return IdentityAccountDTO{}, fmt.Errorf("configure identity account projection: %w", err)
	}
	var raw sql.NullString
	if err = tx.QueryRowContext(queryCtx, `
SELECT a1_project_identity_lifecycle_account($1::uuid)
`, accountID).Scan(&raw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return IdentityAccountDTO{}, ErrIdentityAccountNotFound
		}
		return IdentityAccountDTO{}, fmt.Errorf("project identity account: %w", err)
	}
	if !raw.Valid || strings.TrimSpace(raw.String) == "" {
		return IdentityAccountDTO{}, ErrIdentityAccountNotFound
	}
	var projection identityLifecycleAccountProjection
	if err = json.Unmarshal([]byte(raw.String), &projection); err != nil {
		return IdentityAccountDTO{}, fmt.Errorf("decode identity account projection: %w", err)
	}
	account := projection.toDTO()
	if strings.TrimSpace(account.AccountID) == "" {
		return IdentityAccountDTO{}, ErrIdentityAccountNotFound
	}
	if err = tx.Commit(); err != nil {
		return IdentityAccountDTO{}, fmt.Errorf("commit identity account projection: %w", err)
	}
	committed = true
	account.CredentialCount = len(account.Credentials)
	account.MembershipCount = len(account.Memberships)
	return account, nil
}

type identitySessionTokenMaterial struct {
	bearer     string
	digest     string
	keyVersion string
}

type identitySessionTokenCodec struct {
	mu            sync.RWMutex
	activeVersion string
	legacyVersion string
	keys          map[string][]byte
	random        io.Reader
	retireAt      map[string]time.Time
	requiredUntil time.Time
}

func newIdentitySessionTokenCodec(options ProductionIdentityStoreOptions) (*identitySessionTokenCodec, error) {
	activeVersion := strings.TrimSpace(options.SessionKeyVersion)
	if activeVersion == "" {
		activeVersion = defaultIdentitySessionKeyVersion
	}
	if !validIdentitySessionKeyVersion(activeVersion) {
		return nil, fmt.Errorf("production identity active session key version is invalid")
	}
	if len(options.SessionKey) < 32 {
		return nil, fmt.Errorf("production identity session HMAC key must contain at least 32 bytes")
	}
	keys := map[string][]byte{
		activeVersion: append([]byte(nil), options.SessionKey...),
	}
	retireAt := make(map[string]time.Time, len(options.PreviousSessionKeys))
	now := time.Now
	if options.Now != nil {
		now = options.Now
	}
	refreshLifetime := options.RefreshTokenLifetime
	if refreshLifetime == 0 {
		refreshLifetime = defaultIdentityRefreshSessionTTL
	}
	if refreshLifetime < time.Minute || refreshLifetime > 366*24*time.Hour {
		return nil, fmt.Errorf("production identity refresh token lifetime is invalid")
	}
	retentionMargin := options.PreviousKeyRetentionMargin
	if retentionMargin < 0 || retentionMargin > 30*24*time.Hour {
		return nil, fmt.Errorf("production identity previous session key retention margin is invalid")
	}
	requiredUntil := now().UTC().Add(refreshLifetime + retentionMargin)
	keepKeys := false
	defer func() {
		if !keepKeys {
			zeroIdentitySessionHMACKeys(keys)
		}
	}()
	for _, previous := range options.PreviousSessionKeys {
		version := strings.TrimSpace(previous.Version)
		if !validIdentitySessionKeyVersion(version) {
			return nil, fmt.Errorf("production identity previous session key version is invalid")
		}
		if len(previous.Key) < 32 {
			return nil, fmt.Errorf("production identity previous session HMAC key must contain at least 32 bytes")
		}
		if _, duplicate := keys[version]; duplicate {
			return nil, fmt.Errorf("production identity session key version %q is duplicated", version)
		}
		if options.RequirePreviousKeyRetention {
			if previous.RetireAt.IsZero() {
				return nil, fmt.Errorf("production identity previous session key version %q is missing retirement metadata", version)
			}
			if previous.RetireAt.UTC().Before(requiredUntil) {
				return nil, fmt.Errorf("production identity previous session key version %q retires before live refresh tokens expire", version)
			}
		}
		keys[version] = append([]byte(nil), previous.Key...)
		retireAt[version] = previous.RetireAt.UTC()
	}
	legacyVersion := strings.TrimSpace(options.LegacySessionKeyVersion)
	if legacyVersion == "" {
		legacyVersion = activeVersion
	}
	if _, ok := keys[legacyVersion]; !ok {
		return nil, fmt.Errorf("production identity legacy session key version is not configured")
	}
	if options.RequirePreviousKeyRetention && legacyVersion != activeVersion &&
		retireAt[legacyVersion].Before(requiredUntil) {
		return nil, fmt.Errorf("production identity legacy session key version is not safely retained")
	}
	random := options.Random
	if random == nil {
		random = rand.Reader
	}
	keepKeys = true
	return &identitySessionTokenCodec{
		activeVersion: activeVersion,
		legacyVersion: legacyVersion,
		keys:          keys,
		random:        random,
		retireAt:      retireAt,
		requiredUntil: requiredUntil,
	}, nil
}

func (codec *identitySessionTokenCodec) readiness(now time.Time) IdentitySessionKeyringReadiness {
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	result := IdentitySessionKeyringReadiness{
		ActiveVersion: codec.activeVersion,
		LegacyVersion: codec.legacyVersion,
		Ready:         true,
		PreviousKeys:  make([]IdentitySessionKeyRetirement, 0, len(codec.retireAt)),
	}
	for version, retireAt := range codec.retireAt {
		remaining := retireAt.Sub(now.UTC())
		ready := retireAt.IsZero() || !retireAt.Before(codec.requiredUntil)
		if !ready {
			result.Ready = false
		}
		result.PreviousKeys = append(result.PreviousKeys, IdentitySessionKeyRetirement{
			Version: version, RetireAt: retireAt, RequiredUntil: codec.requiredUntil,
			RetentionReady: ready, RemainingSeconds: max(0, int64(remaining/time.Second)),
		})
	}
	sort.Slice(result.PreviousKeys, func(i, j int) bool {
		return result.PreviousKeys[i].Version < result.PreviousKeys[j].Version
	})
	return result
}

func (codec *identitySessionTokenCodec) issue() (identitySessionTokenMaterial, error) {
	return codec.issueWithPrefix(identitySessionBearerPrefix)
}

func (codec *identitySessionTokenCodec) issueRefresh() (identitySessionTokenMaterial, error) {
	return codec.issueWithPrefix(identityRefreshBearerPrefix)
}

func (codec *identitySessionTokenCodec) issueWithPrefix(
	prefix string,
) (identitySessionTokenMaterial, error) {
	if codec == nil {
		return identitySessionTokenMaterial{}, fmt.Errorf("identity session token codec is unavailable")
	}
	if prefix != identitySessionBearerPrefix && prefix != identityRefreshBearerPrefix {
		return identitySessionTokenMaterial{}, fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.Lock()
	defer codec.mu.Unlock()
	key := codec.keys[codec.activeVersion]
	if len(key) < 32 || codec.random == nil {
		return identitySessionTokenMaterial{}, fmt.Errorf("identity session token codec is unavailable")
	}
	nonce := make([]byte, identitySessionNonceBytes)
	if _, err := io.ReadFull(codec.random, nonce); err != nil {
		return identitySessionTokenMaterial{}, fmt.Errorf("generate identity session bearer: %w", err)
	}
	bearer := prefix + "." + codec.activeVersion + "." +
		base64.RawURLEncoding.EncodeToString(nonce)
	return identitySessionTokenMaterial{
		bearer:     bearer,
		digest:     identitySessionHMAC(key, bearer),
		keyVersion: codec.activeVersion,
	}, nil
}

func (codec *identitySessionTokenCodec) digest(bearer string) (string, string, error) {
	if codec == nil {
		return "", "", fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	version, err := codec.keyVersionForBearer(bearer)
	if err != nil {
		return "", "", err
	}
	key := codec.keys[version]
	if len(key) < 32 {
		return "", "", fmt.Errorf("identity session bearer key version is unavailable")
	}
	return identitySessionHMAC(key, bearer), version, nil
}

func (codec *identitySessionTokenCodec) digestRefresh(
	bearer string,
) (string, string, error) {
	if codec == nil {
		return "", "", fmt.Errorf("identity refresh token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	version, err := codec.keyVersionForPrefixedBearer(
		bearer,
		identityRefreshBearerPrefix,
	)
	if err != nil {
		return "", "", err
	}
	key := codec.keys[version]
	if len(key) < 32 {
		return "", "", fmt.Errorf("identity refresh bearer key version is unavailable")
	}
	return identitySessionHMAC(key, bearer), version, nil
}

func (codec *identitySessionTokenCodec) digestActive(parts ...string) (string, error) {
	if codec == nil {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	key := codec.keys[codec.activeVersion]
	if len(key) < 32 {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	return identitySessionHMAC(key, strings.Join(parts, "\x00")), nil
}

func (codec *identitySessionTokenCodec) digestWithVersion(
	version string,
	parts ...string,
) (string, error) {
	if codec == nil || !validIdentitySessionKeyVersion(version) {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	key := codec.keys[version]
	if len(key) < 32 {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	return identitySessionHMAC(key, strings.Join(parts, "\x00")), nil
}

func (codec *identitySessionTokenCodec) deriveRefreshRotation(
	refreshBearer string,
	idempotencyKey string,
) (identitySessionTokenMaterial, identitySessionTokenMaterial, error) {
	if codec == nil {
		return identitySessionTokenMaterial{}, identitySessionTokenMaterial{},
			fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	refreshKeyVersion, err := codec.keyVersionForPrefixedBearer(
		refreshBearer, identityRefreshBearerPrefix,
	)
	if err != nil {
		return identitySessionTokenMaterial{}, identitySessionTokenMaterial{}, err
	}
	key := codec.keys[refreshKeyVersion]
	if len(key) < 32 || !validIdentitySessionIdempotencyKey(idempotencyKey) {
		return identitySessionTokenMaterial{}, identitySessionTokenMaterial{},
			fmt.Errorf("identity session token codec is unavailable")
	}
	derive := func(label string, prefix string) identitySessionTokenMaterial {
		nonce := identitySessionHMACBytes(
			key,
			strings.Join([]string{
				"identity-refresh-rotation",
				label,
				refreshBearer,
				idempotencyKey,
			}, "\x00"),
		)
		bearer := prefix + "." + refreshKeyVersion + "." +
			base64.RawURLEncoding.EncodeToString(nonce)
		return identitySessionTokenMaterial{
			bearer:     bearer,
			digest:     identitySessionHMAC(key, bearer),
			keyVersion: refreshKeyVersion,
		}
	}
	return derive("access", identitySessionBearerPrefix),
		derive("refresh", identityRefreshBearerPrefix), nil
}

func (codec *identitySessionTokenCodec) keyVersionForBearer(bearer string) (string, error) {
	if strings.HasPrefix(bearer, identityRefreshBearerPrefix+".") {
		return "", fmt.Errorf("identity session bearer is malformed")
	}
	prefix := identitySessionBearerPrefix + "."
	if !strings.HasPrefix(bearer, prefix) {
		return codec.legacyVersion, nil
	}
	return codec.keyVersionForPrefixedBearer(bearer, identitySessionBearerPrefix)
}

func (codec *identitySessionTokenCodec) keyVersionForPrefixedBearer(
	bearer string,
	prefix string,
) (string, error) {
	parts := strings.Split(bearer, ".")
	if len(parts) != 3 || parts[0] != prefix ||
		!validIdentitySessionKeyVersion(parts[1]) {
		return "", fmt.Errorf("identity session bearer is malformed")
	}
	nonce, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || len(nonce) != identitySessionNonceBytes {
		return "", fmt.Errorf("identity session bearer is malformed")
	}
	if _, ok := codec.keys[parts[1]]; !ok {
		return "", fmt.Errorf("identity session bearer key version is unavailable")
	}
	return parts[1], nil
}

func (codec *identitySessionTokenCodec) close() {
	if codec == nil {
		return
	}
	codec.mu.Lock()
	defer codec.mu.Unlock()
	zeroIdentitySessionHMACKeys(codec.keys)
}

func zeroIdentitySessionHMACKeys(keys map[string][]byte) {
	for version, key := range keys {
		for index := range key {
			key[index] = 0
		}
		delete(keys, version)
	}
}

func identitySessionHMAC(key []byte, bearer string) string {
	return hex.EncodeToString(identitySessionHMACBytes(key, bearer))
}

func identitySessionHMACBytes(key []byte, bearer string) []byte {
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(bearer))
	return mac.Sum(nil)
}

func validIdentitySessionKeyVersion(version string) bool {
	if len(version) < 1 || len(version) > 32 {
		return false
	}
	for _, character := range version {
		if (character < 'a' || character > 'z') &&
			(character < 'A' || character > 'Z') &&
			(character < '0' || character > '9') &&
			character != '_' && character != '-' {
			return false
		}
	}
	return true
}

func NewProductionIdentityStore(options ProductionIdentityStoreOptions) (*ProductionIdentityStore, error) {
	if options.DB == nil {
		return nil, fmt.Errorf("production identity postgres db is required")
	}
	sessionTokens, err := newIdentitySessionTokenCodec(options)
	if err != nil {
		return nil, err
	}
	now := options.Now
	if now == nil {
		now = time.Now
	}
	sqlTimeout, err := validatedIdentitySessionTimeout(
		options.SQLTimeout, defaultIdentitySessionSQLTimeout, "SQL operation",
	)
	if err != nil {
		sessionTokens.close()
		return nil, err
	}
	statementTimeout, err := validatedIdentitySessionTimeout(
		options.StatementTimeout, sqlTimeout, "SQL statement",
	)
	if err != nil {
		sessionTokens.close()
		return nil, err
	}
	lockTimeout, err := validatedIdentitySessionTimeout(
		options.LockTimeout, defaultIdentitySessionLockTimeout, "SQL lock",
	)
	if err != nil || statementTimeout > sqlTimeout || lockTimeout > statementTimeout {
		sessionTokens.close()
		if err != nil {
			return nil, err
		}
		return nil, fmt.Errorf("production identity SQL timeouts must satisfy lock <= statement <= operation")
	}
	lifecycleKeys, err := newIdentityLifecycleKeyringWithLookup(
		options.LifecycleReceiptKeyVersion,
		options.LifecycleReceiptKey,
		options.PreviousLifecycleReceiptKeys,
		options.LifecycleReceiptLookupKeyVersion,
		options.LifecycleReceiptLookupKey,
		options.PreviousLifecycleReceiptLookupKeys,
	)
	if err != nil {
		sessionTokens.close()
		return nil, err
	}
	return &ProductionIdentityStore{
		db:               options.DB,
		sessionTokens:    sessionTokens,
		now:              now,
		sqlTimeout:       sqlTimeout,
		statementTimeout: statementTimeout,
		lockTimeout:      lockTimeout,
		lifecycleKeys:    lifecycleKeys,
	}, nil
}

func (store *ProductionIdentityStore) NewIdentityLifecycleReceiptStore() (IdentityLifecycleReceiptStore, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("production identity store is unavailable")
	}
	if store.lifecycleKeys == nil {
		return nil, fmt.Errorf("production identity lifecycle receipt key must be at least 32 bytes")
	}
	return &postgresIdentityLifecycleReceiptStore{
		db: store.db, keys: store.lifecycleKeys.clone(),
		sqlTimeout: store.sqlTimeout, statementTimeout: store.statementTimeout, lockTimeout: store.lockTimeout,
	}, nil
}

func validatedIdentitySessionTimeout(value, fallback time.Duration, name string) (time.Duration, error) {
	if value == 0 {
		value = fallback
	}
	if value < time.Millisecond || value > maxIdentitySessionSQLTimeout {
		return 0, fmt.Errorf("production identity %s timeout must be between 1ms and 30s", name)
	}
	return value, nil
}

func (store *ProductionIdentityStore) SessionKeyringReadiness() IdentitySessionKeyringReadiness {
	if store == nil || store.sessionTokens == nil || store.now == nil {
		return IdentitySessionKeyringReadiness{}
	}
	return store.sessionTokens.readiness(store.now())
}

// LifecycleReceiptLookupRetirementReadiness performs a database-backed,
// aggregate-only preflight before a previous receipt lookup key is removed.
// It never exposes receipt digests, proof material, ciphertext, or key bytes.
func (store *ProductionIdentityStore) LifecycleReceiptLookupRetirementReadiness(
	ctx context.Context,
	retiringVersion string,
) (IdentityLifecycleLookupRetirementReadiness, error) {
	if store == nil || store.db == nil || store.lifecycleKeys == nil {
		return IdentityLifecycleLookupRetirementReadiness{},
			fmt.Errorf("production identity lifecycle lookup keyring is unavailable")
	}
	retiringVersion = strings.TrimSpace(retiringVersion)
	if !validIdentitySessionKeyVersion(retiringVersion) {
		return IdentityLifecycleLookupRetirementReadiness{},
			fmt.Errorf("lifecycle receipt lookup key version is invalid")
	}
	retained, err := store.lifecycleKeys.lookupVersionsExcept(retiringVersion)
	if err != nil {
		return IdentityLifecycleLookupRetirementReadiness{}, err
	}
	queryCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	var raw []byte
	err = store.db.QueryRowContext(queryCtx, `
SELECT a1_identity_lifecycle_lookup_retirement_readiness($1,$2,$3)
`, retiringVersion, pq.Array(retained), store.now().UTC()).Scan(&raw)
	if err != nil {
		return IdentityLifecycleLookupRetirementReadiness{},
			fmt.Errorf("check lifecycle receipt lookup key retirement: %w", err)
	}
	var readiness IdentityLifecycleLookupRetirementReadiness
	if err = json.Unmarshal(raw, &readiness); err != nil {
		return IdentityLifecycleLookupRetirementReadiness{},
			fmt.Errorf("decode lifecycle receipt lookup key retirement readiness: %w", err)
	}
	readiness.ActiveVersion = store.lifecycleKeys.lookupActive
	if readiness.SchemaVersion != "a1.identity.lifecycle.lookup-readiness.v1" ||
		readiness.RetiringVersion != retiringVersion {
		return IdentityLifecycleLookupRetirementReadiness{},
			fmt.Errorf("lifecycle receipt lookup key retirement readiness is invalid")
	}
	return readiness, nil
}

// PurgeExpiredCredentialLinkReplays invokes the audited PostgreSQL purge
// authority after validating and keying every caller-controlled identifier.
// The returned receipt is aggregate-only and safe to pass across the A3
// boundary.
func (store *ProductionIdentityStore) PurgeExpiredCredentialLinkReplays(
	ctx context.Context,
	request IdentityCredentialLinkReplayPurgeRequest,
) (IdentityCredentialLinkReplayPurgeReceipt, error) {
	if store == nil || store.db == nil || store.lifecycleKeys == nil ||
		store.now == nil {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("production identity lifecycle lookup keyring is unavailable")
	}
	now := store.now().UTC().Truncate(time.Microsecond)
	cutoff := request.Cutoff.UTC().Truncate(time.Microsecond)
	actor := strings.TrimSpace(request.Actor)
	reason := strings.TrimSpace(request.Reason)
	idempotencyKey := strings.TrimSpace(request.IdempotencyKey)
	if request.Cutoff.IsZero() || cutoff.After(now) {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("credential-link replay purge cutoff must not be in the future")
	}
	if request.MaxRows < 1 || request.MaxRows > 1000 {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("credential-link replay purge max rows must be between 1 and 1000")
	}
	if !validIdentityMaintenanceLabel(actor, 128) {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("credential-link replay purge actor is invalid")
	}
	if !validIdentityMaintenanceLabel(reason, 512) {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("credential-link replay purge reason is invalid")
	}
	if !validIdentityMaintenanceLabel(idempotencyKey, 256) {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("credential-link replay purge idempotency key is invalid")
	}

	idempotencyDigest := store.lifecycleKeys.receiptDigest(
		"maintenance:credential-link-replay-purge:idempotency:" +
			idempotencyKey,
	)
	requestDigest := store.lifecycleKeys.receiptDigest(strings.Join([]string{
		"maintenance:credential-link-replay-purge:v1",
		cutoff.Format(time.RFC3339Nano),
		strconv.Itoa(request.MaxRows),
		actor,
		reason,
	}, "\x00"))
	queryCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	var raw []byte
	err := store.db.QueryRowContext(queryCtx, `
SELECT a1_purge_identity_credential_link_replays($1,$2,$3,$4,$5,$6,$7)
`, cutoff, request.MaxRows, actor, reason, idempotencyDigest,
		requestDigest, now).Scan(&raw)
	if err != nil {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("purge expired credential-link replays: %w", err)
	}
	var receipt IdentityCredentialLinkReplayPurgeReceipt
	if err = json.Unmarshal(raw, &receipt); err != nil {
		return IdentityCredentialLinkReplayPurgeReceipt{},
			fmt.Errorf("decode credential-link replay purge receipt: %w", err)
	}
	if err = validateIdentityCredentialLinkReplayPurgeReceipt(
		receipt, cutoff, request.MaxRows, now,
	); err != nil {
		return IdentityCredentialLinkReplayPurgeReceipt{}, err
	}
	return receipt, nil
}

func validIdentityMaintenanceLabel(value string, maxLength int) bool {
	if value == "" || len([]rune(value)) > maxLength {
		return false
	}
	for _, item := range value {
		if unicode.IsControl(item) {
			return false
		}
	}
	return true
}

func validateIdentityCredentialLinkReplayPurgeReceipt(
	receipt IdentityCredentialLinkReplayPurgeReceipt,
	cutoff time.Time,
	maxRows int,
	now time.Time,
) error {
	if receipt.SchemaVersion !=
		"a1.identity.credential-link.replay-purge.v1" ||
		receipt.PurgeID == "" ||
		!receipt.Cutoff.Equal(cutoff) ||
		receipt.MaxRows != maxRows ||
		receipt.PurgedRows < 0 ||
		receipt.PurgedRows > int64(maxRows) ||
		receipt.CompletedAt.IsZero() ||
		receipt.CompletedAt.After(now.Add(5*time.Minute)) ||
		receipt.LookupVersionCounts == nil {
		return fmt.Errorf("credential-link replay purge receipt is invalid")
	}
	purgeID, err := strconv.ParseInt(receipt.PurgeID, 10, 64)
	if err != nil || purgeID < 1 {
		return fmt.Errorf("credential-link replay purge receipt is invalid")
	}
	var total int64
	for version, count := range receipt.LookupVersionCounts {
		if !validIdentitySessionKeyVersion(version) ||
			version == "legacy-unversioned" || count < 1 ||
			total > receipt.PurgedRows ||
			count > receipt.PurgedRows-total {
			return fmt.Errorf("credential-link replay purge receipt is invalid")
		}
		total += count
	}
	if total != receipt.PurgedRows {
		return fmt.Errorf("credential-link replay purge receipt is invalid")
	}
	return nil
}

func OpenProductionIdentityStore(dsn string, sessionKey []byte) (*ProductionIdentityStore, error) {
	dsn = strings.TrimSpace(dsn)
	if dsn == "" {
		return nil, fmt.Errorf("production identity requires ASHR_POSTGRES_DSN or DATABASE_URL")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("open production identity postgres: %w", err)
	}
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{DB: db, SessionKey: sessionKey})
	if err != nil {
		_ = db.Close()
		return nil, err
	}
	return store, nil
}

func (store *ProductionIdentityStore) Close() error {
	if store == nil {
		return nil
	}
	store.sessionTokens.close()
	if store.lifecycleKeys != nil {
		store.lifecycleKeys.close()
	}
	if store.db == nil {
		return nil
	}
	return store.db.Close()
}

func (store *ProductionIdentityStore) Ready(ctx context.Context) error {
	if store == nil || store.db == nil {
		return fmt.Errorf("production identity store is not configured")
	}
	if err := store.db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping production identity postgres: %w", err)
	}
	var ready bool
	err := store.db.QueryRowContext(ctx, productionIdentityReadinessQuery).Scan(&ready)
	if err != nil {
		return fmt.Errorf("verify production identity schema: %w", err)
	}
	if !ready {
		return fmt.Errorf("production identity PostgreSQL schema is incomplete; migrations through 025 email registration session handoff are required")
	}
	return nil
}

func (store *ProductionIdentityStore) NewOAuthStore(vault OAuthOpaqueVault) (*PostgresOAuthStore, error) {
	if store == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	return NewPostgresOAuthStore(store.db, vault)
}

func (store *ProductionIdentityStore) NewGitHubOAuthStore(vault GitHubOAuthOpaqueVault) (*PostgresGitHubOAuthStore, error) {
	if store == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	return NewPostgresGitHubOAuthStore(store.db, vault)
}

func (store *ProductionIdentityStore) NewOAuthRevocationOutboxStore() (*PostgresOAuthRevocationOutboxStore, error) {
	if store == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	return NewPostgresOAuthRevocationOutboxStore(store.db)
}

func (store *ProductionIdentityStore) NewIdentityVerificationStore(
	options PostgresIdentityVerificationStoreOptions,
) (*PostgresIdentityVerificationStore, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	options.DB = store.db
	options.sessionTokens = store.sessionTokens
	return NewPostgresIdentityVerificationStoreWithOptions(options)
}

func (store *ProductionIdentityStore) NewIdentityVerificationTransactionCoordinator(
	verificationStore *PostgresIdentityVerificationStore,
) (*PostgresIdentityVerificationTransactionCoordinator, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	if verificationStore == nil || verificationStore.db != store.db {
		return nil, fmt.Errorf("production identity verification store must belong to the production identity database")
	}
	return NewPostgresIdentityVerificationTransactionCoordinator(verificationStore)
}

type postgresIdentitySession struct {
	AccountID     string
	ActorID       string
	SessionID     string
	SessionDigest string
	TenantID      string
	ProjectID     string
	UserID        string
	Revoked       bool
}

func (store *ProductionIdentityStore) resolveSession(ctx context.Context, request *http.Request) (postgresIdentitySession, error) {
	if store == nil || store.db == nil {
		return postgresIdentitySession{}, fmt.Errorf("production identity session store is unavailable")
	}
	token, err := bearerToken(request)
	if err != nil {
		return postgresIdentitySession{}, err
	}
	digest, _, err := store.sessionTokens.digest(token)
	if err != nil {
		return postgresIdentitySession{}, fmt.Errorf("identity session is invalid")
	}
	var session postgresIdentitySession
	err = store.db.QueryRowContext(ctx, `
SELECT authenticated.principal_id::text,
       authenticated.principal_id::text,
       authenticated.session_id::text,
       COALESCE(authenticated.organization_id::text, ''),
       COALESCE(authenticated.project_id::text, ''),
       authenticated.principal_id::text
  FROM a1_authenticate_identity_session_digest($1) AS authenticated
`, digest).Scan(
		&session.AccountID,
		&session.ActorID,
		&session.SessionID,
		&session.TenantID,
		&session.ProjectID,
		&session.UserID,
	)
	if err == sql.ErrNoRows {
		return postgresIdentitySession{}, fmt.Errorf("identity session is invalid")
	}
	if err != nil {
		return postgresIdentitySession{}, fmt.Errorf("resolve identity session: %w", err)
	}
	session.SessionDigest = digest
	return session, nil
}

func (store *ProductionIdentityStore) sessionDigest(token string) string {
	if store == nil {
		return ""
	}
	digest, _, err := store.sessionTokens.digest(token)
	if err != nil {
		return ""
	}
	return digest
}

func (store *ProductionIdentityStore) RefreshIdentityHTTPSession(
	ctx context.Context,
	request *http.Request,
	projectID string,
	accountID string,
	idempotencyKey string,
) (IdentitySessionIssuanceReceipt, error) {
	if store == nil || store.db == nil || store.sessionTokens == nil || store.now == nil {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	projectID = strings.TrimSpace(projectID)
	accountID = strings.TrimSpace(accountID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if !validPostgresIdentityVerificationUUID(projectID) ||
		!validPostgresIdentityVerificationUUID(accountID) ||
		!validIdentitySessionIdempotencyKey(idempotencyKey) {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	refreshBearer, err := identityRefreshBearerToken(request)
	if err != nil {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	refreshDigest, refreshKeyVersion, err := store.sessionTokens.digestRefresh(refreshBearer)
	if err != nil {
		refreshBearer = ""
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	accessToken, refreshToken, err := store.sessionTokens.deriveRefreshRotation(
		refreshBearer, idempotencyKey,
	)
	refreshBearer = ""
	if err != nil {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	clearBearers := func() {
		accessToken.bearer = ""
		refreshToken.bearer = ""
	}
	if accessToken.keyVersion != refreshKeyVersion ||
		refreshToken.keyVersion != refreshKeyVersion {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	now := store.now().UTC()
	requestedAccessExpiresAt := now.Add(defaultIdentityAccessSessionTTL)
	idempotencyDigest, err := store.sessionTokens.digestWithVersion(
		refreshKeyVersion,
		"identity-refresh-idempotency",
		projectID,
		accountID,
		idempotencyKey,
	)
	if err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	// Access expiry is server policy and may advance between retries. It is not
	// part of the caller's idempotent intent.
	requestDigest, err := store.sessionTokens.digestWithVersion(
		refreshKeyVersion,
		"identity-refresh-request",
		projectID,
		accountID,
		refreshDigest,
		accessToken.digest,
		refreshToken.digest,
	)
	if err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	var sessionID sql.NullString
	var organizationID, returnedProjectID, principalID string
	var rotationGeneration int64
	var outcomeCode string
	var affectedCount int
	var accessExpiresAt, refreshExpiresAt time.Time
	operationCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(operationCtx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if _, err = tx.ExecContext(operationCtx, `
SELECT set_config('statement_timeout', $1, true),
       set_config('lock_timeout', $2, true)
`, fmt.Sprintf("%dms", store.statementTimeout.Milliseconds()),
		fmt.Sprintf("%dms", store.lockTimeout.Milliseconds())); err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	err = tx.QueryRowContext(operationCtx, `
SELECT session_id::text,
       organization_id::text,
       project_id::text,
       principal_id::text,
       rotation_generation,
       outcome_code,
       affected_count,
       access_expires_at,
       refresh_expires_at
  FROM a1_rotate_identity_session_refresh_from_digest(
    $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9::jsonb
  )
`,
		projectID,
		accountID,
		refreshDigest,
		accessToken.digest,
		refreshToken.digest,
		requestedAccessExpiresAt,
		idempotencyDigest,
		requestDigest,
		`{"source":"go_identity_session_refresh_http"}`,
	).Scan(
		&sessionID,
		&organizationID,
		&returnedProjectID,
		&principalID,
		&rotationGeneration,
		&outcomeCode,
		&affectedCount,
		&accessExpiresAt,
		&refreshExpiresAt,
	)
	if err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	if outcomeCode == "refresh_reuse_detected" {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshReused
	}
	if outcomeCode != "rotated" || !sessionID.Valid ||
		!validPostgresIdentityVerificationUUID(sessionID.String) ||
		!validPostgresIdentityVerificationUUID(organizationID) ||
		returnedProjectID != projectID || principalID != accountID ||
		rotationGeneration < 1 || affectedCount != 1 ||
		!accessExpiresAt.After(now) ||
		!refreshExpiresAt.After(accessExpiresAt) {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	if err := tx.Commit(); err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	committed = true
	receipt := newIdentitySessionIssuanceReceiptWithRefresh(
		sessionID.String,
		accessToken.keyVersion,
		refreshToken.keyVersion,
		accessExpiresAt.UTC(),
		refreshExpiresAt.UTC(),
		accessToken.bearer,
		refreshToken.bearer,
	)
	clearBearers()
	return receipt, nil
}

func validIdentitySessionIdempotencyKey(value string) bool {
	if len(value) < 8 || len(value) > 256 {
		return false
	}
	for index, character := range value {
		if (character >= 'a' && character <= 'z') ||
			(character >= 'A' && character <= 'Z') ||
			(character >= '0' && character <= '9') ||
			(index > 0 && (character == '.' || character == '_' ||
				character == ':' || character == '-')) {
			continue
		}
		return false
	}
	return true
}

func bearerToken(request *http.Request) (string, error) {
	if request == nil {
		return "", fmt.Errorf("identity session request is required")
	}
	headerValues := request.Header.Values("Authorization")
	if len(headerValues) > 1 {
		return "", fmt.Errorf("identity session credentials are ambiguous")
	}
	headerToken := ""
	if len(headerValues) == 1 {
		authorization := strings.TrimSpace(headerValues[0])
		scheme, token, found := strings.Cut(authorization, " ")
		token = strings.TrimSpace(token)
		if !found || !strings.EqualFold(scheme, "Bearer") ||
			!validIdentitySessionBearerValue(token) {
			return "", fmt.Errorf("Bearer identity session is malformed")
		}
		headerToken = token
	}
	cookieToken, cookiePresent, err := identitySessionCookieBearer(request, IdentitySessionCookieName)
	if err != nil {
		return "", err
	}
	if headerToken == "" && !cookiePresent {
		return "", fmt.Errorf("Bearer identity session is required")
	}
	if headerToken != "" && cookiePresent && headerToken != cookieToken {
		return "", fmt.Errorf("identity session credentials conflict")
	}
	if headerToken != "" {
		return headerToken, nil
	}
	return cookieToken, nil
}

func identityRefreshBearerToken(request *http.Request) (string, error) {
	if request == nil {
		return "", fmt.Errorf("identity refresh request is required")
	}
	if len(request.Header.Values("Authorization")) != 0 {
		return "", fmt.Errorf("identity refresh credentials are ambiguous")
	}
	token, present, err := identitySessionCookieBearer(request, IdentityRefreshCookieName)
	if err != nil {
		return "", err
	}
	if !present {
		return "", fmt.Errorf("identity refresh credential is required")
	}
	return token, nil
}

func identitySessionCookieBearer(
	request *http.Request,
	name string,
) (string, bool, error) {
	var value string
	count := 0
	for _, cookie := range request.Cookies() {
		if cookie.Name != name {
			continue
		}
		count++
		value = cookie.Value
	}
	if count == 0 {
		return "", false, nil
	}
	if count != 1 || !validIdentitySessionBearerValue(value) {
		return "", false, fmt.Errorf("identity session cookie is malformed")
	}
	return value, true, nil
}

func validIdentitySessionBearerValue(value string) bool {
	return value != "" && value == strings.TrimSpace(value) && len(value) <= 4096 &&
		!strings.ContainsAny(value, " \t\r\n,;")
}

func (store *ProductionIdentityStore) ResolveIdentityHTTPSession(
	ctx context.Context,
	request *http.Request,
) (IdentityHTTPSession, error) {
	session, err := store.resolveSession(ctx, request)
	if err != nil {
		return IdentityHTTPSession{}, err
	}
	return IdentityHTTPSession{
		AccountID:     session.AccountID,
		ActorID:       session.ActorID,
		SessionID:     session.SessionID,
		SessionDigest: session.SessionDigest,
		Revoked:       session.Revoked,
	}, nil
}

func (store *ProductionIdentityStore) ResolveOAuthSession(
	ctx context.Context,
	request *http.Request,
) (OAuthSession, error) {
	session, err := store.resolveSession(ctx, request)
	if err != nil {
		return OAuthSession{}, err
	}
	return OAuthSession{
		TenantID:  session.TenantID,
		UserID:    session.UserID,
		SessionID: session.SessionID,
		AccountID: session.AccountID,
		Revoked:   session.Revoked,
	}, nil
}

func (store *ProductionIdentityStore) ResolveGitHubOAuthSession(
	ctx context.Context,
	request *http.Request,
) (GitHubOAuthSession, error) {
	session, err := store.resolveSession(ctx, request)
	if err != nil {
		return GitHubOAuthSession{}, err
	}
	return GitHubOAuthSession{
		TenantID:  session.TenantID,
		UserID:    session.UserID,
		SessionID: session.SessionID,
		AccountID: session.AccountID,
		Revoked:   session.Revoked,
	}, nil
}

var (
	_ UnifiedIdentityHTTPStore     = (*ProductionIdentityStore)(nil)
	_ IdentityHTTPSessionResolver  = (*ProductionIdentityStore)(nil)
	_ IdentityHTTPSessionRefresher = (*ProductionIdentityStore)(nil)
	_ OAuthSessionResolver         = (*ProductionIdentityStore)(nil)
	_ GitHubOAuthSessionResolver   = (*ProductionIdentityStore)(nil)
)
