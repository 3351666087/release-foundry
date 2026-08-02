import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const repoUrl = new URL("../../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, repoUrl), "utf8");
}

test("local HTTPS delivery serves only the exported webapp tree", async () => {
  const [caddy, compose] = await Promise.all([
    source("infra/docker/Caddyfile.local-auth"),
    source("infra/docker/docker-compose.local-auth.yml")
  ]);

  assert.match(caddy, /handle_path \/apps\/webapp\/out\/\*/);
  assert.match(caddy, /root \* \/srv\/apps\/webapp\/out/);
  assert.match(caddy, /redir \* \/apps\/webapp\/out\/overview\/ 302/);
  assert.match(caddy, /redir \* \/apps\/webapp\/out\/login\/ 302/);
  assert.match(caddy, /respond "not found" 404/);
  assert.doesNotMatch(caddy, /root \* \/srv(?:\s|$)/m);
  assert.match(compose, /\.\.\/\.\.\/apps\/webapp\/out:\/srv\/apps\/webapp\/out:ro/);
  assert.doesNotMatch(compose, /- \.\.\/\.\.:\/srv:ro/);
});
