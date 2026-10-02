import { defineConfig } from "@playwright/test";

// Explicitly invoked gate: real HTTPS proxy, two browsers and private engines.
// No Vite server, request mocks, model fallback, skips or automatic retries.
export default defineConfig({
  testDir: "./e2e-hosted",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 480_000,
  expect: { timeout: 30_000 },
  reporter: [["list"]],
});
