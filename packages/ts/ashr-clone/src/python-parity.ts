import { createHash } from "node:crypto";

import {
  ACCOUNT_CONNECTION_EXACT_SCOPES,
  GOOGLE_ACCOUNT_CONNECTION_ISSUERS,
  type PublicAccountConnection,
  type PublicAccountConnectionDisconnect,
  type PublicAccountConnectionStart,
} from "./account-connections.js";
import type { LocalGradeResult, LocalObservation } from "./runner.js";
import {
  IDENTITY_VERIFICATION_PROVIDERS,
  IDENTITY_VERIFICATION_PURPOSES,
} from "./unified-identity.js";

export type AccountConnection = PublicAccountConnection;
export type AccountConnectionDisconnect = PublicAccountConnectionDisconnect;
export type AccountConnectionStart = PublicAccountConnectionStart;
export type GradeResult = LocalGradeResult;
export type Observation = LocalObservation;

export interface ToolCall extends Record<string, unknown> {
  name: string;
  arguments: Record<string, unknown>;
  arguments_json?: string | null;
  call_id?: string | null;
  output?: unknown;
  latency_ms?: number | null;
  error?: string | null;
}

export const GOOGLE_ACCOUNT_CONNECTION_SCOPES = ACCOUNT_CONNECTION_EXACT_SCOPES.google;
export const GOOGLE_OIDC_ISSUERS = GOOGLE_ACCOUNT_CONNECTION_ISSUERS;

export {
  AccountConnectionError as AccountConnectionContractError,
  accountConnectionContractManifest as account_connection_contract_manifest,
  normalizeAccountConnectionProvider as normalize_account_connection_provider,
  validateGoogleOidcPublicContract as validate_google_oidc_public_contract,
} from "./account-connections.js";

export {
  assertCapabilityMatrixSafe as assert_capability_matrix_safe,
  buildCapabilityMatrix as build_capability_matrix,
  validateCapabilityMatrix as validate_capability_matrix,
  writeCapabilityMatrix as write_capability_matrix,
} from "./capability-matrix.js";

export {
  apiRecordToCases as api_record_to_cases,
  caseFromSourceRun as case_from_source_run,
  casesFromDatasetSource as cases_from_dataset_source,
  datasetSourceToCases as dataset_source_to_cases,
  extractDatasetSource as extract_dataset_source,
  loadCasesFromApiRecord as load_cases_from_api_record,
  replayFixtureFromSourceRun as replay_fixture_from_source_run,
  writeCases as write_cases,
} from "./dataset-adapter.js";

export {
  buildPrivateEvidenceIndex as build_private_evidence_index,
  buildPrivateEvidenceIndexFromDir as build_private_evidence_index_from_dir,
  buildResponseFieldMap as build_response_field_map,
  mergeEvidenceIndices as merge_evidence_indices,
  renderResponseFieldMapMarkdown as render_response_field_map_markdown,
  summarizeQuotaError as summarize_quota_error,
  validatePublicEvidenceIndex as validate_public_evidence_index,
  writePrivateEvidenceIndex as write_private_evidence_index,
  writeResponseFieldMapMarkdown as write_response_field_map_markdown,
} from "./evidence.js";

export {
  buildTraceRunFixture as build_run_fixture,
  buildVmStream as build_vm_stream,
  loadRunFixture as load_run_fixture,
  traceEventsFromVmStream as trace_events_from_vm_stream,
  validateRunFixture as validate_run_fixture,
  writeRunFixture as write_run_fixture,
} from "./trace.js";

export {
  assertPublicObjectManifestSafe as assert_public_object_manifest_safe,
  buildObjectManifest as build_object_manifest,
  scopedObjectKey as scoped_object_key,
  sha256Bytes as sha256_bytes,
  verifyObjectBytes as verify_object_bytes,
  verifyObjectManifestSignature as verify_object_manifest_signature,
} from "./storage.js";

export {
  enforceCreateRequestPreflight as enforce_create_request_preflight,
  summarizeGenerationRequest as summarize_generation_request,
} from "./api-client.js";

export {
  consumeOfficialApiMutatingCalibrationIndex as consume_official_api_mutating_calibration_index,
} from "./saas.js";

export {
  assertPublicSessionPayload as assert_public_session_payload,
  browserSessionRefreshRoute as browser_session_refresh_route,
  sessionAuthenticateRoute as session_authenticate_route,
  sessionCollectionRoute as session_collection_route,
  sessionLifecycleContractManifest as session_lifecycle_contract_manifest,
  sessionRecentAuthRoute as session_recent_auth_route,
  sessionRecoveryInvalidationRoute as session_recovery_invalidation_route,
  sessionRefreshRoute as session_refresh_route,
  sessionRevokeAllRoute as session_revoke_all_route,
  sessionRevokeRoute as session_revoke_route,
  sessionRoute as session_route,
} from "./session-lifecycle.js";

export {
  UnifiedIdentityHttpClient as UnifiedIdentityClient,
  identityAccountRoute as identity_account_route,
  identityCredentialsRoute as identity_credentials_route,
  identityPasswordBeginRoute as identity_password_begin_route,
  identityPasswordRoute as identity_password_route,
  identityLinkRoute as identity_link_route,
  identityMembershipsRoute as identity_memberships_route,
  identityMergeRoute as identity_merge_route,
  identityRecoveryCompleteRoute as identity_recovery_complete_route,
  identityRecoveryStartRoute as identity_recovery_start_route,
  identitySecurityRoute as identity_security_route,
  identityTwoFactorEnrollBeginRoute as identity_two_factor_enroll_begin_route,
  identityTwoFactorEnrollConfirmRoute as identity_two_factor_enroll_confirm_route,
  identityTwoFactorDisableRoute as identity_two_factor_disable_route,
  identityTwoFactorRecoveryConsumeRoute as identity_two_factor_recovery_consume_route,
  identityTwoFactorRecoveryRotateRoute as identity_two_factor_recovery_rotate_route,
  identityTwoFactorRoute as identity_two_factor_route,
  identityUnlinkRoute as identity_unlink_route,
  identityVerificationChallengeRoute as identity_verification_challenge_route,
  identityVerificationChallengesRoute as identity_verification_challenges_route,
  identityVerificationResendRoute as identity_verification_resend_route,
  identityVerificationVerifyRoute as identity_verification_verify_route,
  normalizeUnifiedIdentityProvider as normalize_identity_provider,
  unifiedIdentityContractManifest as unified_identity_contract_manifest,
} from "./unified-identity.js";

export function normalize_verification_provider(value: string): (typeof IDENTITY_VERIFICATION_PROVIDERS)[number] {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!IDENTITY_VERIFICATION_PROVIDERS.includes(normalized as (typeof IDENTITY_VERIFICATION_PROVIDERS)[number])) {
    throw new Error(`verification provider must be one of: ${IDENTITY_VERIFICATION_PROVIDERS.join(", ")}`);
  }
  return normalized as (typeof IDENTITY_VERIFICATION_PROVIDERS)[number];
}

export function normalize_verification_purpose(value: string): (typeof IDENTITY_VERIFICATION_PURPOSES)[number] {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!IDENTITY_VERIFICATION_PURPOSES.includes(normalized as (typeof IDENTITY_VERIFICATION_PURPOSES)[number])) {
    throw new Error(`verification purpose must be one of: ${IDENTITY_VERIFICATION_PURPOSES.join(", ")}`);
  }
  return normalized as (typeof IDENTITY_VERIFICATION_PURPOSES)[number];
}

export function stable_id(prefix: string, ...parts: unknown[]): string {
  let size = 16;
  const last = parts.at(-1);
  if (isRecord(last) && typeof last.size === "number") {
    const options = parts.pop() as Record<string, unknown>;
    size = Math.trunc(Number(options.size));
  }
  if (!Number.isInteger(size) || size < 1 || size > 64) throw new Error("stable_id size must be between 1 and 64");
  const payload = JSON.stringify(canonicalize(parts));
  return `${prefix}_${createHash("sha256").update(payload, "utf8").digest("hex").slice(0, size)}`;
}

export function replay_observations(events: Iterable<Record<string, unknown>>): Record<string, unknown>[] {
  return [...events]
    .sort((left, right) => Number(left.seq ?? 0) - Number(right.seq ?? 0))
    .map((event) => {
      if (!isRecord(event.observation)) throw new Error("trace event observation must be an object");
      return canonicalize(event.observation) as Record<string, unknown>;
    });
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (isRecord(value)) return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
