import { expect, test } from "@playwright/test";
import {
  installTrustWorkbenchState,
  mockTrustWorkbenchApi,
} from "@/e2e/trust-workbench/helpers";

test.beforeEach(async ({ page }) => {
  await installTrustWorkbenchState(page);
  await mockTrustWorkbenchApi(page);
});

test("browse the certification queue, filter it, and navigate to detail", async ({
  page,
}) => {
  await page.goto("/trust-workbench");

  await expect(
    page.getByRole("heading", { name: /Trust Workbench/i }),
  ).toBeVisible();
  await expect(page.getByText("Fraud Monitor")).toBeVisible();
  await expect(page.getByText("KYC Review")).toBeVisible();

  await page.getByLabel("Search certifications").fill("fraud");
  await expect(page.getByText("Fraud Monitor")).toBeVisible();
  await expect(page.getByText("KYC Review")).not.toBeVisible();

  await page.goto("/trust-workbench");
  await page.getByRole("button", { name: "Pending", exact: true }).click();
  await expect(
    page.getByText(/pending, expiring, and revoked certifications stay in a single triage surface/i),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Revoked Agent/i })).toBeVisible();

  await page.getByLabel("Sort certifications").selectOption("created");
  await expect(page).toHaveURL(/sort_by=created/);

  await page.getByRole("link", { name: /Fraud Monitor/i }).click();
  await expect(page).toHaveURL("/trust-workbench/cert-1");
});
