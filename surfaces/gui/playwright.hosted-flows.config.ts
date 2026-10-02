import { defineConfig } from "@playwright/test";

// Real HTTPS, built SPA, private engines and an external CLI joiner.
export default defineConfig({
  testDir: "./e2e-hosted",
  testMatch: "flows.spec.ts",
  outputDir: "./test-results-hosted-flows",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 600_000,
  expect: { timeout: 30_000 },
  reporter: [["list"]],
});
