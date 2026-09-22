import type { NextConfig } from "next";

const API_BASE_URL = process.env.API_BASE_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_BASE_URL}/api/v1/:path*`,
      },
      {
        // Prefer `/api/:path*` for endpoints that collide with frontend pages
        // (e.g. `/api/notifications` → backend `/notifications`).
        source: "/api/:path*",
        destination: `${API_BASE_URL}/:path*`,
      },
      {
        source: "/dashboard",
        destination: `${API_BASE_URL}/dashboard`,
      },
      {
        source: "/dashboard/:path*",
        destination: `${API_BASE_URL}/dashboard/:path*`,
      },
      {
        source: "/candidates",
        destination: `${API_BASE_URL}/candidates`,
      },
      {
        source: "/candidates/:path*",
        destination: `${API_BASE_URL}/candidates/:path*`,
      },
      {
        source: "/jobs",
        destination: `${API_BASE_URL}/jobs`,
      },
      {
        source: "/jobs/:path*",
        destination: `${API_BASE_URL}/jobs/:path*`,
      },
      {
        source: "/users",
        destination: `${API_BASE_URL}/users`,
      },
      {
        source: "/users/:path*",
        destination: `${API_BASE_URL}/users/:path*`,
      },
      {
        source: "/notifications",
        destination: `${API_BASE_URL}/notifications`,
      },
      {
        source: "/notifications/:path*",
        destination: `${API_BASE_URL}/notifications/:path*`,
      },
      {
        source: "/candidate/:path*",
        destination: `${API_BASE_URL}/candidate/:path*`,
      },
      {
        source: "/jobs/:path*",
        destination: `${API_BASE_URL}/jobs/:path*`,
      },
      {
        source: "/public/:path*",
        destination: `${API_BASE_URL}/public/:path*`,
      },
      {
        source: "/applications/:path*",
        destination: `${API_BASE_URL}/applications/:path*`,
      },
      {
        source: "/interviews",
        destination: `${API_BASE_URL}/interviews`,
      },
      {
        source: "/interviews/:path*",
        destination: `${API_BASE_URL}/interviews/:path*`,
      },
      {
        source: "/companies/:path*",
        destination: `${API_BASE_URL}/companies/:path*`,
      },
      {
        source: "/auth/:path*",
        destination: `${API_BASE_URL}/auth/:path*`,
      },
      {
        source: "/users/:path*",
        destination: `${API_BASE_URL}/users/:path*`,
      },
      {
        source: "/offers/:path*",
        destination: `${API_BASE_URL}/offers/:path*`,
      },
      {
        source: "/search/:path*",
        destination: `${API_BASE_URL}/search/:path*`,
      },
    ];
  },
};

export default nextConfig;