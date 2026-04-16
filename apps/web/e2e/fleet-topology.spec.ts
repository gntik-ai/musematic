import { expect, test } from "@playwright/test";
import { installFleetState, mockFleetApi } from "@/e2e/fleet/helpers";

test.beforeEach(async ({ page }) => {
  await installFleetState(page);
  await mockFleetApi(page);
});

test("render topology, open member detail, and persist tab routing", async ({ page }) => {
  await page.goto("/fleet/fleet-1?tab=topology");

  await expect(page.getByRole("heading", { name: "Topology view" })).toBeVisible();
  await expect(page.getByTestId("rf__node-member-1")).toBeVisible();

  await page.getByTestId("rf__node-member-1").click();
  await expect(page.getByText("Fleet member")).toBeVisible();
  await expect(page.getByRole("dialog").getByText("risk:triage-lead")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();

  await page.getByRole("button", { name: "Members" }).click();
  await expect(page).toHaveURL("/fleet/fleet-1?tab=members");
  await expect(page.getByRole("heading", { name: "Members" })).toBeVisible();

  await page.getByRole("button", { name: "Topology" }).click();
  await expect(page).toHaveURL(/\/fleet\/fleet-1\?tab=topology/);

  await page.reload();
  await expect(page).toHaveURL(/\/fleet\/fleet-1\?tab=topology/);
  await expect(page.getByRole("heading", { name: "Topology view" })).toBeVisible();
});
