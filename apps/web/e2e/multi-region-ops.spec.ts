import { expect, test } from "@playwright/test";
import { installOperatorState, mockOperatorApi } from "@/e2e/operator/helpers";

test.beforeEach(async ({ page }) => {
  await installOperatorState(page);
  await mockOperatorApi(page);
});

test("operator superadmin can rehearse failover, toggle maintenance, and inspect capacity", async ({
  page,
}) => {
  await page.goto("/operator?panel=regions");

  await expect(page.getByRole("heading", { name: "Regions", exact: true })).toBeVisible();
  await expect(page.getByText("postgres")).toBeVisible();
  await page.getByRole("button", { name: "Plans" }).click();
  await expect(page.getByText("primary-to-dr")).toBeVisible();
  await page.getByRole("button", { name: "Runs" }).click();
  await expect(page.getByText("primary-to-dr run history")).toBeVisible();
  await page.getByRole("button", { name: "Trigger rehearsal" }).click();
  await expect(page.getByText("run-2")).not.toBeVisible();
  await expect(page.getByText("Operator verification").first()).toBeVisible();

  await page.goto("/operator?panel=maintenance");
  await expect(page.getByRole("heading", { name: "Maintenance", exact: true })).toBeVisible();
  await expect(page.getByText("Writes open")).toBeVisible();
  await page.getByLabel("Starts at").fill("2099-01-01T01:00");
  await page.getByLabel("Ends at").fill("2099-01-01T02:00");
  await page.getByLabel("Reason").fill("database maintenance");
  await page.getByLabel("Announcement").fill("Writes are paused for maintenance");
  await page.getByRole("button", { name: "Schedule" }).click();
  await page.getByRole("button", { name: "Enable" }).click();
  await expect(page.getByText("Maintenance active until")).toBeVisible();
  await expect(page.getByText("Writes are paused for maintenance").first()).toBeVisible();

  const maintenanceResponse = await page.evaluate(async () => {
    const response = await fetch("http://localhost:8000/api/v1/admin/regions", {
      method: "POST",
      body: JSON.stringify({ region_code: "test", region_role: "secondary" }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(maintenanceResponse.status).toBe(503);
  expect(maintenanceResponse.body.announcement).toBe("Writes are paused for maintenance");
  await page.getByRole("button", { name: "Disable" }).click();
  await expect(page.getByText("Writes open")).toBeVisible();

  await page.goto("/operator?panel=capacity");
  await expect(page.getByRole("heading", { name: "Capacity", exact: true })).toBeVisible();
  await expect(page.getByText("Compute capacity is projected")).toBeVisible();
  await expect(page.getByRole("link", { name: "Costs" })).toBeVisible();
});
