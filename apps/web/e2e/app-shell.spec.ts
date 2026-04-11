import { expect, test } from "@playwright/test";

test("app shell renders and command palette navigates", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /continue with mock workspace/i }).click();
  await expect(page.getByRole("navigation", { name: /main navigation/i })).toBeVisible();
  await page.getByTestId("sidebar-toggle").click();
  await page.keyboard.press("Control+K");
  await page.getByTestId("command-input").fill("settings");
  await page.getByText("Settings").click();
  await expect(page).toHaveURL(/settings/);
});
