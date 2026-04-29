import { expect, test } from "@playwright/test";

test("PWA manifest is reachable and installable metadata is present", async ({ page }) => {
  const response = await page.goto("/manifest.webmanifest");
  expect(response?.ok()).toBe(true);
  const manifest = JSON.parse(await page.locator("body").innerText()) as {
    name?: string;
    short_name?: string;
    display?: string;
    icons?: unknown[];
  };
  expect(manifest.name).toBe("musematic");
  expect(manifest.short_name).toBe("musematic");
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons?.length).toBeGreaterThanOrEqual(3);
});
