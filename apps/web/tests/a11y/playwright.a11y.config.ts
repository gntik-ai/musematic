import { defineConfig, devices } from "@playwright/test";

const themes = ["light", "dark", "system", "high_contrast"] as const;
const locales = ["en", "es", "fr", "de", "ja", "zh-CN"] as const;

export default defineConfig({
  testDir: ".",
  fullyParallel: true,
  retries: 0,
  timeout: 60_000,
  reporter: [
    ["json", { outputFile: "test-results/a11y-results.json" }],
    ["html", { outputFolder: "playwright-report/a11y", open: "never" }],
  ],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: themes.flatMap((theme) =>
    locales.map((locale) => ({
      name: `a11y-${theme}-${locale}`,
      use: {
        ...devices["Desktop Chrome"],
        locale,
        colorScheme: theme === "dark" ? "dark" : "light",
      },
    })),
  ),
  ...(process.env.CI ? { workers: 6 } : {}),
});
