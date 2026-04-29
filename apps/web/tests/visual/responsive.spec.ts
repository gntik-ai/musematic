import { expect, test } from "@playwright/test";

const routes = ["/marketplace", "/operator/incidents", "/marketplace/finance-ops/kyc-verifier"] as const;
const viewports = [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1280, height: 900 },
] as const;

for (const route of routes) {
  for (const viewport of viewports) {
    test(`${route} has no horizontal scroll at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(route);
      const hasHorizontalScroll = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth,
      );
      expect(hasHorizontalScroll).toBe(false);
    });
  }
}
