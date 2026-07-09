import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const workspaceRoot = resolve(process.cwd());
const fallbackRoot = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const root = workspaceRoot.endsWith("ashr-codex-factory") ? workspaceRoot : fallbackRoot;
const port = parsePort(process.argv, process.env.A3_DASHBOARD_E2E_PORT || "4173");

const contentTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".md", "text/markdown; charset=utf-8"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".svg", "image/svg+xml"]
]);

const server = createServer((request, response) => {
  try {
    const requestUrl = new URL(request.url || "/", `http://${request.headers.host || "127.0.0.1"}`);
    if (requestUrl.pathname === "/__health") {
      sendText(response, 200, "ok");
      return;
    }

    const resolved = resolveRequestPath(requestUrl.pathname);
    if (!resolved.startsWith(`${root}${sep}`) && resolved !== root) {
      sendText(response, 403, "Forbidden");
      return;
    }

    const stats = statSync(resolved);
    if (stats.isDirectory()) {
      sendFile(response, join(resolved, "index.html"));
      return;
    }
    sendFile(response, resolved);
  } catch (error) {
    sendText(response, error.code === "ENOENT" ? 404 : 500, error.code === "ENOENT" ? "Not found" : "Server error");
  }
});

server.on("clientError", (error, socket) => {
  if (socket.writable) {
    socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
  }
  console.warn(`A3 dashboard E2E client error: ${error.code || error.message}`);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`A3 dashboard E2E server listening at http://127.0.0.1:${port}`);
  console.log(`Serving ${root}`);
});

function parsePort(args, fallback) {
  const index = args.indexOf("--port");
  const value = index >= 0 ? args[index + 1] : fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0 || parsed > 65535) {
    throw new Error(`Invalid port: ${value}`);
  }
  return parsed;
}

function resolveRequestPath(pathname) {
  const decoded = decodeURIComponent(pathname);
  const withoutLeadingSlash = decoded.replace(/^\/+/, "");
  return resolve(root, normalize(withoutLeadingSlash || "apps/dashboard/index.html"));
}

function sendFile(response, filePath) {
  response.writeHead(200, {
    "content-type": contentTypes.get(extname(filePath).toLowerCase()) || "application/octet-stream",
    "cache-control": "no-store"
  });
  const stream = createReadStream(filePath);
  stream.on("error", (error) => {
    if (!response.headersSent) {
      sendText(response, 500, "Server error");
      return;
    }
    response.destroy(error);
  });
  response.on("error", () => {
    stream.destroy();
  });
  stream.pipe(response);
}

function sendText(response, status, body) {
  response.writeHead(status, {
    "content-type": "text/plain; charset=utf-8",
    "cache-control": "no-store"
  });
  response.end(body);
}
