import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = dirname(fileURLToPath(import.meta.url));

const nextConfig = {
  output: "export",
  trailingSlash: true,
  basePath: "/apps/webapp/out",
  assetPrefix: "/apps/webapp/out",
  turbopack: {
    root: appRoot
  },
  images: {
    unoptimized: true
  }
};

export default nextConfig;
