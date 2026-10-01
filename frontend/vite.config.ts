import { defineConfig } from "vitest/config";

export default defineConfig({
  build: {
    outDir: "dist",
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [{ name: "telemetry-vendor", test: /node_modules[\\/]posthog-js/ }],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        // The Django dev server closes idle keep-alive sockets without notice;
        // reusing one leaves the proxied request hanging forever. Fresh socket
        // per request + bounded socket timeouts eliminate that stall class.
        timeout: 30_000,
        proxyTimeout: 30_000,
        headers: { connection: "close" },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "tests/contracts/**/*.test.ts"],
    passWithNoTests: false,
    setupFiles: ["src/test/setup.ts"],
  },
});
