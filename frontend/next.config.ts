import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
      // Proxy top-level backend routes (dashboard, candidates, jobs, etc.)
      {
        source: "/dashboard/:path*",
        destination: "http://localhost:8000/dashboard/:path*",
      },
      {
        source: "/candidates/:path*",
        destination: "http://localhost:8000/candidates/:path*",
      },
      {
        source: "/jobs/:path*",
        destination: "http://localhost:8000/jobs/:path*",
      },
      {
        source: "/auth/:path*",
        destination: "http://localhost:8000/auth/:path*",
      },
      {
        source: "/users/:path*",
        destination: "http://localhost:8000/users/:path*",
      },
      {
        source: "/offers/:path*",
        destination: "http://localhost:8000/offers/:path*",
      },
      {
        source: "/search/:path*",
        destination: "http://localhost:8000/search/:path*",
      },
    ];
  },
};

export default nextConfig;
