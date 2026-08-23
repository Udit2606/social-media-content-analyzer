import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Next generates AGENTS.md / CLAUDE.md by default; this project does not use them.
  agentRules: false,
  poweredByHeader: false,
};

export default nextConfig;
