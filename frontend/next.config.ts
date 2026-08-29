import type { NextConfig } from "next";

/**
 * The browser never talks to FastAPI directly, so there is no rewrite to the API
 * here and no CORS surface to open. Requests go to this app's own route handlers,
 * which attach the access token server-side — see `lib/backend.ts`.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // A standalone build is what the container copies; it keeps the image to the
  // server plus the traced dependencies rather than all of node_modules.
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            // No inline scripts are used, but Next injects inline bootstrap styles,
            // so style-src keeps 'unsafe-inline' while script-src does not.
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data:",
              "connect-src 'self'",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
