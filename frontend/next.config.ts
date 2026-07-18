import type { NextConfig } from "next";

const configuredBackendHost = process.env.BACKEND_HOST || "127.0.0.1";
const backendHost = configuredBackendHost === "localhost" || configuredBackendHost === "0.0.0.0"
  ? "127.0.0.1"
  : configuredBackendHost;
const backendPort = process.env.BACKEND_PORT || "9999";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://${backendHost}:${backendPort}/:path*`,
      },
    ];
  },
};

export default nextConfig;
