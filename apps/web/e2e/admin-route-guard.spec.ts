import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./auth/helpers";

test("non-admin users are redirected away from admin settings", async ({ page }) => {
  await mockAuthApi(page, {
    roles: ["workspace_owner"],
    userEmail: "owner@musematic.dev",
    userId: "owner-1",
    userName: "Workspace Owner",
  });

  await page.goto("/login");
  await signIn(page, { email: "owner@musematic.dev" });
  await page.goto("/admin/settings");

  await expect(page).toHaveURL(/\/home/);
  await expect(
    page.getByText("You do not have permission to access admin settings"),
  ).toBeVisible();
});
