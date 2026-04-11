import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./auth/helpers";

test("login, shell navigation, breadcrumbs, and dark mode work together", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL(/dashboard/);
  await page.keyboard.press("Control+K");
  await page.getByTestId("command-input").fill("create agent");
  await page.getByText("Agents").click();
  await page.goto("/agents/create");
  await expect(page.getByText("Create Agent")).toBeVisible();
  await expect(page.getByText("Agents")).toBeVisible();
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
