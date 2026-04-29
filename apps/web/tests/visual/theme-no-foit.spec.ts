import { expect, test } from "@playwright/test";

const themes = ["dark", "high_contrast", "system"] as const;

for (const theme of themes) {
  test(`first paint honors ${theme} theme preference`, async ({ page }) => {
    await page.addInitScript((themeName) => {
      window.localStorage.setItem("musematic-theme", themeName);
      document.cookie = `musematic-theme=${themeName}; Path=/; SameSite=Lax`;
    }, theme);
    await page.goto("/marketplace");
    if (theme !== "system") {
      await expect(page.locator("html")).toHaveClass(new RegExp(theme));
    }
  });
}
