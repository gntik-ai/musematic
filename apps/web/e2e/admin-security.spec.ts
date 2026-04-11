import { expect, test } from "@playwright/test";
import { mockAdminApi } from "./admin/helpers";
import { mockAuthApi, signIn } from "./auth/helpers";

test("platform admin can validate and save security settings", async ({ page }) => {
  await mockAuthApi(page, {
    roles: ["platform_admin"],
    userEmail: "pat.admin@musematic.dev",
    userId: "admin-1",
    userName: "Pat Admin",
  });
  await mockAdminApi(page);

  await page.goto("/login");
  await signIn(page, { email: "pat.admin@musematic.dev" });
  await page.goto("/admin/settings?tab=security");

  const minLength = page.getByLabel("Minimum password length");
  await minLength.fill("7");
  await expect(page.getByText("Minimum 8 characters")).toBeVisible();

  await minLength.fill("16");
  const sessionDuration = page.getByLabel("Session duration (minutes)");
  await sessionDuration.fill("60");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: /Saved ✓/i })).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Minimum password length")).toHaveValue("16");
  await expect(page.getByLabel("Session duration (minutes)")).toHaveValue("60");
});
