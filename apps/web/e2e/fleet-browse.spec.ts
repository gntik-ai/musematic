import { expect, test } from "@playwright/test";
import { installFleetState, mockFleetApi } from "@/e2e/fleet/helpers";

test.beforeEach(async ({ page }) => {
  await installFleetState(page);
  await mockFleetApi(page);
});

test("browse fleets, filter the list, and navigate to fleet detail", async ({ page }) => {
  await page.goto("/fleet");

  await expect(page.getByRole("heading", { name: /Operational fleet overview/i })).toBeVisible();
  await expect(page.getByText("Fraud mesh")).toBeVisible();
  await expect(page.getByText("KYC review")).toBeVisible();

  await page.getByLabel("Search fleets").fill("fraud");
  await expect(page.getByText("Fraud mesh")).toBeVisible();
  await expect(page.getByText("KYC review")).not.toBeVisible();

  await page.getByLabel("Search fleets").fill("");
  await page.getByLabel("Status").selectOption(["degraded"]);
  await expect(page.getByText("Fraud mesh")).toBeVisible();
  await expect(page.getByText("KYC review")).not.toBeVisible();

  await page.goto("/fleet");
  await page.getByRole("link", { name: "Fraud mesh" }).click();
  await expect(page).toHaveURL("/fleet/fleet-1");
  await expect(page.getByRole("heading", { name: "Fraud mesh" })).toBeVisible();
});
