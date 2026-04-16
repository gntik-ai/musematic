import { expect, test } from "@playwright/test";
import {
  installTrustWorkbenchState,
  mockTrustWorkbenchApi,
} from "@/e2e/trust-workbench/helpers";

test.beforeEach(async ({ page }) => {
  await installTrustWorkbenchState(page);
  await mockTrustWorkbenchApi(page);
});

test("review evidence, approve a certification, and reject another after validation", async ({
  page,
}) => {
  await page.goto("/trust-workbench/cert-1");

  await expect(page.getByText("Package validation")).toBeVisible();
  await page.getByRole("button", { name: /Package validation/i }).click();
  await expect(page.getByText("Supporting data")).toBeVisible();

  await page.locator("label", { hasText: "Approve" }).click();
  await page.getByLabel("Review notes").fill(
    "Approve after validating package and behavioral evidence.",
  );
  await page.getByRole("button", { name: "Approve certification" }).click();
  await expect(page.getByLabel("Certification status Active")).toBeVisible();

  await page.goto("/trust-workbench/cert-2");
  await page.getByRole("button", { name: "Submit review" }).click();
  await expect(page.getByText("Select a decision.")).toBeVisible();
  await expect(page.getByText("Review notes are required.")).toBeVisible();

  await page.locator("label", { hasText: "Reject" }).click();
  await page.getByLabel("Review notes").fill(
    "Reject until privacy remediation is completed.",
  );
  await page.getByRole("button", { name: "Reject certification" }).click();
  await expect(page.getByLabel("Certification status Revoked")).toBeVisible();
});
