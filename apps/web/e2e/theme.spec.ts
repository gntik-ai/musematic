import { expect, test } from "@playwright/test";

test("theme toggle applies dark mode without leaving the shell", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /continue with mock workspace/i }).click();
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
