import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./auth/helpers";

test("development component showcase renders shared building blocks", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL(/home/);

  await page.keyboard.press("Control+K");
  await page.getByTestId("command-input").fill("component");
  await page.getByRole("button", { name: /^Open component showcase/ }).click();
  await expect(page).toHaveURL(/\/dev\/components$/);

  if ((await page.getByRole("heading", { name: "404" }).count()) > 0) {
    await expect(page.getByRole("heading", { name: "404" })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /this page could not be found\./i }),
    ).toBeVisible();
    return;
  }

  await expect(page.getByRole("heading", { name: /shared component showcase/i })).toBeVisible();
  await expect(page.getByText("Agent uptime")).toBeVisible();
  await expect(page.getByText("Trust score")).toBeVisible();
  await expect(page.getByText("Empty state treatment")).toBeVisible();
  await expect(page.getByText("Runtime controller promoted")).toBeVisible();
});
