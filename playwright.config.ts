import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the production build served by `vite preview`.
// They use an installed browser (Edge or Chrome) via PW_CHANNEL, so no
// browser download is required: `npx playwright install chromium` is optional.
const channel = process.env.PW_CHANNEL ?? "msedge";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:4173",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    channel: channel === "bundled" ? undefined : channel,
    viewport: { width: 1360, height: 900 },
  },
  webServer: {
    command: "npm run build && npx vite preview --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { VITE_CONFIG_NATIVE_IGNORE_WARNING: "true" },
  },
});
