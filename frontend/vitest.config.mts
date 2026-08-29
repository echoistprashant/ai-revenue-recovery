import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Unit tests cover the pure rules only — role ranking, the proxy allowlist, the
 * session codec, and the display formatters. Those are the modules where a mistake is
 * silent: a formatter that renders a missing score as `0.0000` or an allowlist that
 * accidentally admits `/auth/token` would look fine on screen.
 *
 * Nothing here imports `server-only`, so no test needs a React or Next runtime.
 */
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
