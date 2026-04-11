import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./auth/helpers";

test("theme toggle applies dark mode without leaving the shell", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");
  await signIn(page);
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
