import { expect, test } from "@playwright/test";

test("tenant branding renders for enterprise and default tenants", async ({ page }) => {
  await page.route("**/api/v1/me/tenant", async (route) => {
    const host = new URL(route.request().url()).host;
    const isAcme = host.startsWith("acme.");
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: isAcme
          ? "11111111-1111-1111-1111-111111111111"
          : "00000000-0000-0000-0000-000000000001",
        slug: isAcme ? "acme" : "default",
        kind: isAcme ? "enterprise" : "default",
        status: "active",
        display_name: isAcme ? "Acme Corp" : "Musematic",
        branding: isAcme ? { accent_color_hex: "#123456" } : {},
      }),
    });
  });

  await page.goto("/login");
  await expect(page.getByText("Musematic").first()).toBeVisible();

  await page.goto("http://acme.localtest.me:3000/login");
  await expect(page.getByText("Acme Corp").first()).toBeVisible();
});
