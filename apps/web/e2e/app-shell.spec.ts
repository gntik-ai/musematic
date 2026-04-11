import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./auth/helpers";

test("app shell renders and command palette navigates", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL(/dashboard/);
  await expect(page.getByRole("navigation", { name: /main navigation/i })).toBeVisible();
  await page.getByTestId("sidebar-toggle").click();
  await page.keyboard.press("Control+K");
  await page.getByTestId("command-input").fill("settings");
  await page.getByText("Settings").click();
  await expect(page).toHaveURL(/settings/);
});
