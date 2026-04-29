import { expect, test } from "@playwright/test";

const desktopFirstRoutes = ["/workflow-editor-monitor/new", "/fleet/fleet-1", "/admin/settings"] as const;

for (const route of desktopFirstRoutes) {
  test(`${route} shows desktop hint on mobile`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(route);
    await expect(page.getByTestId("desktop-best-hint")).toBeVisible();
  });
}
