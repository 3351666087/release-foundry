import { CloudApiService } from "releasefoundry";
import { AccountConnectionHttpClient } from "releasefoundry/account-connections";
import { build_receipt_template } from "releasefoundry/account-readiness";
import { ReleaseFoundryApiClient } from "releasefoundry/api-client";
import { BillingLedger } from "releasefoundry/billing";
import {
  BrowserHTTPResponse,
  BrowserSessionClient,
  type BrowserHTTPResponseBody,
  type BrowserHTTPResponseHeaders,
} from "releasefoundry/browser-session";
import { runCalibration } from "releasefoundry/calibrate";
import { buildA1CandidateBinding } from "releasefoundry/candidate-binding";
import { buildCapabilityMatrix } from "releasefoundry/capability-matrix";
import { buildCnyTradePlan } from "releasefoundry/china-payments";
import { CloudQueueWorker } from "releasefoundry/cloud-queue";
import { buildCommercialControlPlaneKit } from "releasefoundry/commercial";
import { datasetSourceToCases } from "releasefoundry/dataset-adapter";
import { identityDeliveryProtocolContractManifest } from "releasefoundry/delivery-protocol";
import { buildPrivateEvidenceIndex } from "releasefoundry/evidence";
import { GitHubOAuthHttpClient } from "releasefoundry/github-oauth";
import { IdentityClient } from "releasefoundry/identity-client";
import { buildAuthorizationEnvelope } from "releasefoundry/oauth";
import { ProviderDispatchClient } from "releasefoundry/provider-dispatch";
import { stable_id } from "releasefoundry/python-parity";
import { AgentAdapter } from "releasefoundry/runner";
import { SaaSIngestionClient } from "releasefoundry/saas";
import { SessionLifecycleClient } from "releasefoundry/session-lifecycle";
import { LocalFilesystemObjectStorage } from "releasefoundry/storage";
import { StripeTestHostedExecutor } from "releasefoundry/stripe-executor";
import { TraceRecorder } from "releasefoundry/trace";
import { UnifiedIdentityHttpClient } from "releasefoundry/unified-identity";

export const typedDistributionImports: readonly unknown[] = [
  CloudApiService,
  AccountConnectionHttpClient,
  build_receipt_template,
  ReleaseFoundryApiClient,
  BillingLedger,
  BrowserSessionClient,
  BrowserHTTPResponse,
  runCalibration,
  buildA1CandidateBinding,
  buildCapabilityMatrix,
  buildCnyTradePlan,
  CloudQueueWorker,
  buildCommercialControlPlaneKit,
  datasetSourceToCases,
  identityDeliveryProtocolContractManifest,
  buildPrivateEvidenceIndex,
  GitHubOAuthHttpClient,
  IdentityClient,
  buildAuthorizationEnvelope,
  ProviderDispatchClient,
  stable_id,
  AgentAdapter,
  SaaSIngestionClient,
  SessionLifecycleClient,
  LocalFilesystemObjectStorage,
  StripeTestHostedExecutor,
  TraceRecorder,
  UnifiedIdentityHttpClient,
];

const browserResponseBody: BrowserHTTPResponseBody = { status: "ok" };
const browserResponseHeaders: BrowserHTTPResponseHeaders = {
  "x-request-id": "request_types",
  "set-cookie": ["a=one", "b=two"],
};
const browserResponse = BrowserHTTPResponse.create(200, {
  headers: browserResponseHeaders,
  body: browserResponseBody,
});
browserResponse.headerValues("x-request-id");
