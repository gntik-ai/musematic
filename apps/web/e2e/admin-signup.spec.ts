import { expect, test } from "@playwright/test";
import { mockAdminApi } from "./admin/helpers";
import { mockAuthApi, signIn } from "./auth/helpers";

test("platform admin can change signup mode and the value persists", async ({ page }) => {
  await mockAuthApi(page, {
    roles: ["platform_admin"],
    userEmail: "pat.admin@musematic.dev",
    userId: "admin-1",
    userName: "Pat Admin",
  });
  await mockAdminApi(page);

  await page.goto("/login");
  await signIn(page, { email: "pat.admin@musematic.dev" });
  await page.goto("/admin/settings?tab=signup");

  await page.getByLabel("Invite only").check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: /Saved ✓/i })).toBeVisible();

  await page.reload();

  await expect(page.getByLabel("Invite only")).toBeChecked();
});
