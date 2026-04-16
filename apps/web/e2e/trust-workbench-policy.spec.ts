import { expect, test } from "@playwright/test";
import {
  installTrustWorkbenchState,
  mockTrustWorkbenchApi,
} from "@/e2e/trust-workbench/helpers";

test.beforeEach(async ({ page }) => {
  await installTrustWorkbenchState(page);
  await mockTrustWorkbenchApi(page);
});

test("attach and remove a direct policy while showing inherited bindings", async ({
  page,
}) => {
  await page.goto("/trust-workbench/cert-1?tab=policies");
  const effectiveBindings = page.locator('[class*="border-dashed"]');

  await expect(page.getByText("Policy catalog")).toBeVisible();
  await expect(page.getByText("Effective bindings")).toBeVisible();
  await expect(page.getByText("fleet: Fraud Detection Fleet")).toBeVisible();

  const dataTransfer = await page.evaluateHandle(() => new DataTransfer());
  await page
    .getByText("Fraud triage policy")
    .locator("..")
    .dispatchEvent("dragstart", { dataTransfer });
  await page
    .getByText("Effective bindings")
    .locator("..")
    .dispatchEvent("dragover", { dataTransfer });
  await page
    .getByText("Effective bindings")
    .locator("..")
    .dispatchEvent("drop", { dataTransfer });

  await expect(page.getByText("Fraud triage policy")).toBeVisible();
  await expect(page.getByText(/^direct$/).last()).toBeVisible();

  await page
    .locator('[class*="space-y-3"] > *', {
      has: page.getByText("Direct review guardrail"),
    })
    .getByRole("button", { name: "Remove" })
    .click();
  await page.getByRole("button", { name: "Remove policy" }).click();
  await expect(
    effectiveBindings.getByText("Direct review guardrail"),
  ).not.toBeVisible();
});
