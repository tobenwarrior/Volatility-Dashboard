import type { NextConfig } from "next";
import { readFileSync } from "fs";
import { join } from "path";

function getBackendPort(): number {
  try {
    const portFile = join(__dirname, "..", "backend", ".port");
    const port = parseInt(readFileSync(portFile, "utf-8").trim(), 10);
    if (port > 0 && port < 65536) return port;
  } catch {}
  return 5000;
}

const backendPort = getBackendPort();

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${backendPort}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
