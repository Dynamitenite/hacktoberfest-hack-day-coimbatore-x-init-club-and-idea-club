import type { NextConfig } from "next";

// The browser only ever talks to this Next.js server. API calls are proxied to
// the FastAPI backend, so no API key and no backend URL reach browser code.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default config;
