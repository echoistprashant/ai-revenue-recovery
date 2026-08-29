# Next.js control centre.
#
# Three stages so the runtime image carries the server and its traced dependencies
# rather than the whole toolchain: `output: "standalone"` in next.config.ts is what
# makes that possible.
#
# No secret is baked in. `REVENUE_RECOVERY_API_URL`, `FRONTEND_COOKIE_SECURE`,
# `BACKEND_TIMEOUT_MS`, and `RAZORPAY_WEBHOOK_SECRET` are read at runtime, so one image
# serves development over plain HTTP and production behind TLS.

FROM node:22-alpine AS deps
WORKDIR /app
# Only the manifests, so a source-only change does not reinstall the dependency tree.
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Typecheck and unit tests run here too: an image that cannot pass them should not be
# built at all, which keeps `docker compose up` honest about the same rules CI enforces.
RUN npm run typecheck && npm run test && npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# An unprivileged user: the server needs no write access to its own bundle.
RUN addgroup -S nodejs -g 1001 && adduser -S nextjs -u 1001
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
