import { CloudApiService } from "@ashr-clone/sdk";
import { AccountConnectionHttpClient } from "@ashr-clone/sdk/account-connections";
import { build_receipt_template } from "@ashr-clone/sdk/account-readiness";
import { AshrApiClient } from "@ashr-clone/sdk/api-client";
import { BillingLedger } from "@ashr-clone/sdk/billing";
import {
  BrowserHTTPResponse,
  BrowserSessionClient,
  type BrowserHTTPResponseBody,
  type BrowserHTTPResponseHeaders,
} from "@ashr-clone/sdk/browser-session";
import { runCalibration } from "@ashr-clone/sdk/calibrate";
import { buildCapabilityMatrix } from "@ashr-clone/sdk/capability-matrix";
import { buildCnyTradePlan } from "@ashr-clone/sdk/china-payments";
import { CloudQueueWorker } from "@ashr-clone/sdk/cloud-queue";
import { buildCommercialControlPlaneKit } from "@ashr-clone/sdk/commercial";
import { datasetSourceToCases } from "@ashr-clone/sdk/dataset-adapter";
import { identityDeliveryProtocolContractManifest } from "@ashr-clone/sdk/delivery-protocol";
import { buildPrivateEvidenceIndex } from "@ashr-clone/sdk/evidence";
import { GitHubOAuthHttpClient } from "@ashr-clone/sdk/github-oauth";
import { buildAuthorizationEnvelope } from "@ashr-clone/sdk/oauth";
import { ProviderDispatchClient } from "@ashr-clone/sdk/provider-dispatch";
import { stable_id } from "@ashr-clone/sdk/python-parity";
import { AgentAdapter } from "@ashr-clone/sdk/runner";
import { SaaSIngestionClient } from "@ashr-clone/sdk/saas";
import { SessionLifecycleClient } from "@ashr-clone/sdk/session-lifecycle";
import { LocalFilesystemObjectStorage } from "@ashr-clone/sdk/storage";
import { StripeTestHostedExecutor } from "@ashr-clone/sdk/stripe-executor";
import { TraceRecorder } from "@ashr-clone/sdk/trace";
import { UnifiedIdentityHttpClient } from "@ashr-clone/sdk/unified-identity";

export const typedDistributionImports: readonly unknown[] = [
  CloudApiService,
  AccountConnectionHttpClient,
  build_receipt_template,
  AshrApiClient,
  BillingLedger,
  BrowserSessionClient,
  BrowserHTTPResponse,
  runCalibration,
  buildCapabilityMatrix,
  buildCnyTradePlan,
  CloudQueueWorker,
  buildCommercialControlPlaneKit,
  datasetSourceToCases,
  identityDeliveryProtocolContractManifest,
  buildPrivateEvidenceIndex,
  GitHubOAuthHttpClient,
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
