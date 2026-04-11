import { expect, test } from "@playwright/test";
import { mockAdminApi } from "./admin/helpers";
import { mockAuthApi, signIn } from "./auth/helpers";

test("platform admin can approve a pending user and cannot suspend self", async ({ page }) => {
  await mockAuthApi(page, {
    roles: ["platform_admin"],
    userEmail: "pat.admin@musematic.dev",
    userId: "admin-1",
    userName: "Pat Admin",
  });
  await mockAdminApi(page);

  await page.goto("/login");
  await signIn(page, { email: "pat.admin@musematic.dev" });
  await page.goto("/admin/settings?tab=users");

  await expect(page.getByText("John Example")).toBeVisible();
  await expect(page.getByText("Pat Admin")).toBeVisible();

  await page.getByRole("button", { name: "Open actions for John Example" }).click();
  await page.getByRole("button", { name: "Approve John Example" }).click();
  await page.getByRole("button", { name: "Approve user" }).click();

  const johnRow = page.locator("tr", { hasText: "John Example" });
  await expect(johnRow.getByLabel("status active")).toBeVisible();

  await page.getByRole("button", { name: "Open actions for Pat Admin" }).click();
  await expect(
    page.getByRole("button", { name: "Suspend Pat Admin" }),
  ).toBeDisabled();
});
