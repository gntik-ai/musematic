import { expect, test } from "@playwright/test";

test.describe("cost governance", () => {
  test("workspace admin budget path renders", async ({ page }) => {
    await page.goto("/costs/budgets");

    await expect(page.getByRole("heading", { name: "Cost Budgets" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Budget" })).toBeVisible();
  });
});
