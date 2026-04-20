import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./auth/helpers";

test("login, shell navigation, breadcrumbs, and dark mode work together", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL(/home/);
  await page.getByTestId("command-palette-toggle").click();
  await page.getByTestId("command-input").fill("agents");
  await page.getByRole("button", { name: /^Agents/ }).click();
  await page.goto("/agents/create");
  await expect(page.getByRole("heading", { name: "Create Agent", exact: true })).toBeVisible();
  const breadcrumb = page.getByLabel("Breadcrumb").first();
  await expect(breadcrumb.getByRole("link", { name: "Agents" })).toBeVisible();
  await expect(breadcrumb.getByText("Create")).toBeVisible();
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
