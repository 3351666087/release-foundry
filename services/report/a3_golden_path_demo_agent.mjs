import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PRICE_FIXTURE = "fixtures/a2/web/acme_minidock_official.json";
const MEDIA_FIXTURE = "fixtures/a2/media/dashboard_alert_analysis.json";
const MEDIA_ASSET = "fixtures/a2/images/dashboard-alert.png";

export class A3GoldenPathDemoAgent {
  constructor(options = {}) {
    this.rootDir = resolve(options.rootDir || DEFAULT_ROOT);
  }

  reset() {
    return true;
  }

  async respond(message) {
    const text = typeof message === "string" ? message : String(message?.text || "");
    if (/rewrite this sentence/i.test(text)) {
      return this.directAnswer();
    }
    if (/current official price|current listed price|official product page/i.test(text)) {
      return this.currentPrice();
    }
    if (/dashboard media asset|red critical service/i.test(text)) {
      return this.inspectDashboardMedia();
    }
    throw new Error("A3 Golden Agent refuses prompts outside its versioned case set");
  }

  directAnswer() {
    return response(
      "We would be happy to review your request once the missing information is complete.",
      []
    );
  }

  async currentPrice() {
    const args = {
      query: "Acme MiniDock official product price",
      official_domain: "acme.example",
    };
    const record = await this.readJson(PRICE_FIXTURE);
    if (!record.url || !record.price || !String(record.url).startsWith("https://acme.example/")) {
      throw new Error("official price fixture failed provenance validation");
    }
    const output = {
      title: String(record.title || ""),
      price: String(record.price),
      source_url: String(record.url),
      source_kind: "official_product_page",
      fixture_updated: String(record.updated || ""),
    };
    return response(
      `The Acme MiniDock is currently listed at ${output.price} on the official product page: ${output.source_url}.`,
      [toolCall("web.search", args, output, "tool-web-search-001")]
    );
  }

  async inspectDashboardMedia() {
    const analysis = await this.readJson(MEDIA_FIXTURE);
    const fetchArgs = { asset_id: "dashboard-alert-001" };
    if (analysis.asset_id !== fetchArgs.asset_id || analysis.source_path !== MEDIA_ASSET) {
      throw new Error("media fixture failed asset provenance validation");
    }

    const bytes = await readFile(resolve(this.rootDir, MEDIA_ASSET));
    const digest = sha256(bytes);
    const fetchOutput = {
      asset_id: analysis.asset_id,
      modality: analysis.modality,
      path: analysis.source_path,
      content_hash_sha256: digest,
      raw_media_embedded: false,
    };

    const viewArgs = { path: MEDIA_ASSET };
    const image = inspectPng(bytes);
    const viewOutput = {
      path: MEDIA_ASSET,
      format: "png",
      width: image.width,
      height: image.height,
      content_hash_sha256: digest,
      inspected: true,
    };

    const classifyArgs = {
      classifier: "dashboard_alert_service",
      asset_id: analysis.asset_id,
    };
    const classification = analysis.analysis || {};
    if (!classification.service || !classification.severity || !classification.alert_color) {
      throw new Error("media classifier fixture is incomplete");
    }
    const classifyOutput = {
      classifier: classifyArgs.classifier,
      service: String(classification.service),
      severity: String(classification.severity),
      alert_color: String(classification.alert_color),
      confidence: Number(classification.confidence),
      evidence_hash_sha256: digest,
      grounded_facts: [
        String(classification.service),
        String(classification.severity),
        String(classification.alert_color),
      ],
    };

    return response(
      `The media evidence identifies Billing as the critical service shown in red (classifier confidence ${classifyOutput.confidence}).`,
      [
        toolCall("media.fetch", fetchArgs, fetchOutput, "tool-media-fetch-001"),
        toolCall("image.view", viewArgs, viewOutput, "tool-image-view-001"),
        toolCall("media.classify", classifyArgs, classifyOutput, "tool-media-classify-001"),
      ]
    );
  }

  async readJson(relativePath) {
    const payload = JSON.parse(await readFile(resolve(this.rootDir, relativePath), "utf8"));
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error(`fixture ${relativePath} must contain a JSON object`);
    }
    return payload;
  }
}

export default A3GoldenPathDemoAgent;

function response(text, toolCalls) {
  return {
    text,
    tool_calls: toolCalls,
    status: "ok",
    metadata: {
      implementation: "services/report/a3_golden_path_demo_agent.mjs",
      local_only: true,
      fixture_grounded: true,
      network_used: false,
      read_only: true,
    },
  };
}

function toolCall(name, args, output, callId) {
  return {
    name,
    arguments: args,
    output,
    call_id: callId,
  };
}

function inspectPng(bytes) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(signature) || bytes.toString("ascii", 12, 16) !== "IHDR") {
    throw new Error("dashboard media asset is not a valid PNG header");
  }
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  if (width < 1 || height < 1) {
    throw new Error("dashboard media asset has invalid dimensions");
  }
  return { width, height };
}

function sha256(value) {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}
