import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const ROOT = new URL("../../", import.meta.url);
const COMPOSE_PATH = new URL("../../infra/docker/docker-compose.self-host.yml", import.meta.url);
const DOCKERFILE_PATH = new URL("../../infra/docker/Dockerfile.python-runtime", import.meta.url);
const TERRAFORM_FILES = [
  "../../infra/terraform/self-host/versions.tf",
  "../../infra/terraform/self-host/variables.tf",
  "../../infra/terraform/self-host/main.tf",
  "../../infra/terraform/self-host/outputs.tf"
].map((path) => new URL(path, import.meta.url));
const RUST_MANIFEST_PATH = new URL("../../packages/rust/ashr-runtime-verify/Cargo.toml", import.meta.url);
const RUST_MAIN_PATH = new URL("../../packages/rust/ashr-runtime-verify/src/main.rs", import.meta.url);
const DOC_PATH = new URL("../../docs/a1/self_host_runtime_scaffold.md", import.meta.url);

test("self-host compose wires api worker and local backing services", async () => {
  const compose = await readFile(COMPOSE_PATH, "utf8");
  const dockerfile = await readFile(DOCKERFILE_PATH, "utf8");

  for (const service of ["api", "worker", "postgres", "redis", "object-store"]) {
    assert.match(compose, new RegExp(`\\n  ${escapeRegExp(service)}:\\n`), `missing compose service: ${service}`);
  }

  for (const term of [
    "infra/docker/Dockerfile.python-runtime",
    "ASHR_DATABASE_URL",
    "ASHR_REDIS_URL",
    "ASHR_OBJECT_STORE_URL",
    "services.api.control_plane",
    "services.api.cli",
    "replay-queued",
    "--state-input",
    "--state-output",
    "--agent",
    "examples.agents.mock_agent:RespondingMockAgent",
    "--max-runs",
    "--queue-workers",
    "service_healthy",
    "ashr-object-store"
  ]) {
    assert.ok(compose.includes(term), `compose missing ${term}`);
  }
  assert.ok(!compose.includes("--help"), "worker command must execute a bounded replay path, not help output");

  assert.ok(dockerfile.includes("python:3.12-slim"), "Dockerfile should use a slim Python runtime");
  assert.ok(dockerfile.includes("serve_control_plane_http"), "Dockerfile should default to the stdlib control plane");
  assert.ok(dockerfile.includes("HEALTHCHECK"), "Dockerfile should include a local healthcheck");
});

test("terraform self-host skeleton is provider-neutral and secret-free", async () => {
  const terraform = (await Promise.all(TERRAFORM_FILES.map((path) => readFile(path, "utf8")))).join("\n");

  for (const term of [
    "required_version",
    "hashicorp/null",
    "deployment_contract",
    "ashr.a1.self_host.runtime.v1",
    "api_image",
    "worker_image",
    "postgres_storage_gb",
    "object_store_bucket",
    "enable_public_ingress",
    "runtime_environment",
    "postgres_connection_from_secret_manager",
    "redis_connection_from_secret_manager"
  ]) {
    assert.ok(terraform.includes(term), `terraform missing ${term}`);
  }

  assert.doesNotMatch(terraform, /provider\s+"(aws|azurerm|google|kubernetes)"/);
  assertNoProductionSecret(terraform, "terraform self-host skeleton");
});

test("rust runtime verifier crate exposes verify and replay-plan commands", async () => {
  const manifest = await readFile(RUST_MANIFEST_PATH, "utf8");
  const source = await readFile(RUST_MAIN_PATH, "utf8");

  assert.ok(manifest.includes('name = "ashr-runtime-verify"'));
  assert.ok(manifest.includes('edition = "2021"'));
  assert.ok(manifest.includes("publish = false"));
  assert.doesNotMatch(manifest, /^\[dependencies\]/m, "crate should stay dependency-free for locked-down hosts");

  for (const term of [
    "MAX_INPUT_BYTES",
    "SECRET_MARKERS",
    "RUNTIME_MARKERS",
    '"verify"',
    '"replay-plan"',
    "ashr.runtime.replay_plan.v1",
    "brackets_are_balanced",
    "count_status"
  ]) {
    assert.ok(source.includes(term), `rust source missing ${term}`);
  }

  assertNoProductionSecret(source, "rust verifier source");
});

test("A1 deploy note documents compose terraform rust and static validation", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  for (const term of [
    "Docker Compose",
    "Terraform",
    "Rust Utility",
    "Static Validation",
    "infra/docker/docker-compose.self-host.yml",
    "infra/terraform/self-host/",
    "packages/rust/ashr-runtime-verify",
    "node --test tests/integration/deploy_runtime_scaffold.test.mjs"
  ]) {
    assert.ok(doc.includes(term), `doc missing ${term}`);
  }
});

test("deploy scaffold files do not contain obvious credential material", async () => {
  const paths = [COMPOSE_PATH, DOCKERFILE_PATH, RUST_MANIFEST_PATH, RUST_MAIN_PATH, DOC_PATH, ...TERRAFORM_FILES];
  for (const path of paths) {
    const text = await readFile(path, "utf8");
    assertNoProductionSecret(text, path.pathname.replace(ROOT.pathname, ""));
  }
});

function assertNoProductionSecret(text, label) {
  const allowedDevOnly = text.replaceAll("ashr_dev_only", "").replaceAll("ASHR_API_KEY" + "=", "").replaceAll("ASHR_LABS_API_KEY" + "=", "");
  assert.doesNotMatch(allowedDevOnly, /sk-[A-Za-z0-9_-]{8,}/, `${label} contains sk-style token`);
  assert.doesNotMatch(allowedDevOnly, /Bearer\s+[A-Za-z0-9._-]{8,}/, `${label} contains bearer token`);
  assert.doesNotMatch(allowedDevOnly, /password\s*=\s*"(?!ashr_dev_only)[^"]+"/i, `${label} contains password assignment`);
  assert.doesNotMatch(allowedDevOnly, /secret\s*=\s*"[^"]+"/i, `${label} contains secret assignment`);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
