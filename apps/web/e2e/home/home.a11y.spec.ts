import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "../auth/helpers";

test("@a11y home dashboard exposes accessible landmarks and summary cards", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");
  await signIn(page);

  await expect(page).toHaveURL(/home/);
  await expect(page.getByRole("main")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /current workspace overview/i }),
  ).toBeVisible();
  await expect(page.getByRole("group", { name: /active agents:/i })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "New Conversation" }),
  ).toBeVisible();
});
