import { expect, test } from "@playwright/test";
import { installFleetState, mockFleetApi } from "@/e2e/fleet/helpers";

test.beforeEach(async ({ page }) => {
  await installFleetState(page);
  await mockFleetApi(page);
});

test("pause and resume the fleet, then run and cancel a stress test", async ({ page }) => {
  await page.goto("/fleet/fleet-1?tab=controls");

  await page.getByLabel("Pause fleet").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Pause fleet" }).click();
  await expect(page.getByLabel("Resume fleet")).toBeVisible();

  await page.getByLabel("Resume fleet").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Resume fleet" }).click();
  await expect(page.getByLabel("Pause fleet")).toBeVisible();

  await page.getByLabel("Stress test fleet").click();
  await page.getByRole("button", { name: "Start test" }).click();
  await expect(page.getByText(/Executions: 32/i)).toBeVisible();

  await page.getByRole("button", { name: "Cancel test" }).click();
  await expect(page.getByText(/Status: cancelled/i)).toBeVisible();
});
