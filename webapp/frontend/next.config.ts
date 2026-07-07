import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      { source: "/asistente", destination: "/fondeo/liquidity-sweep", permanent: false },
      { source: "/live", destination: "/fondeo/liquidity-sweep", permanent: false },
    ];
  },
};

export default nextConfig;
