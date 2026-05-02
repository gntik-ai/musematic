import { defineConfig, devices } from "@playwright/test";

const chromiumExecutablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const firefoxExecutablePath = process.env.PLAYWRIGHT_FIREFOX_EXECUTABLE_PATH;
const webRootPattern = process
  .cwd()
  .replace(/\\/g, "/")
  .replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export default defineConfig({
  testDir: ".",
  testMatch: [
    new RegExp(`^${webRootPattern}/e2e/.*\\.spec\\.ts$`),
    new RegExp(`^${webRootPattern}/tests/e2e/creator-uis-pages\\.spec\\.ts$`),
    new RegExp(`^${webRootPattern}/tests/e2e/self-service-pages\\.spec\\.ts$`),
    new RegExp(`^${webRootPattern}/tests/e2e/tenant-branding\\.spec\\.ts$`),
    new RegExp(`^${webRootPattern}/tests/e2e/tenant-switcher\\.spec\\.ts$`),
    new RegExp(
      `^${webRootPattern}/tests/e2e/workspace-owner-pages\\.spec\\.ts$`,
    ),
  ],
  fullyParallel: true,
  retries: 0,
  reporter: "html",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(chromiumExecutablePath
          ? {
              launchOptions: {
                executablePath: chromiumExecutablePath,
              },
            }
          : {}),
      },
    },
    {
      name: "firefox",
      use: {
        ...devices["Desktop Firefox"],
        ...(firefoxExecutablePath
          ? {
              launchOptions: {
                executablePath: firefoxExecutablePath,
              },
            }
          : {}),
      },
    },
  ],
});
