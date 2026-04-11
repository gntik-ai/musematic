import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./helpers";

test("users without MFA enrolled complete enrollment from the dashboard dialog", async ({
  page,
}) => {
  await mockAuthApi(page, { mfaEnrolled: false });
  await page.goto("/login");

  await signIn(page);

  await expect(page.getByText(/set up authenticator/i)).toBeVisible();
  await expect(page.locator("svg")).toBeVisible();
  await page.getByRole("button", { name: /next/i }).click();
  await page.getByLabel(/authenticator verification code/i).fill("123456");
  await expect(page.getByText(/save your recovery codes/i)).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByText(/save your recovery codes/i)).toBeVisible();

  await page
    .getByLabel(/i have saved my recovery codes in a safe place/i)
    .check();
  await page.getByRole("button", { name: /complete setup/i }).click();

  await expect(page.getByText(/save your recovery codes/i)).not.toBeVisible();
  await expect(page.getByText(/mission control dashboard/i)).toBeVisible();
});
