import { expect, test } from "@playwright/test";
import { mockAuthApi, signIn } from "./helpers";

test("credential login redirects to the home dashboard", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");

  await signIn(page);

  await expect(page).toHaveURL(/home/);
  await expect(page.getByRole("heading", { name: /current workspace overview/i })).toBeVisible();
});

test("redirectTo is preserved after a successful login", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/settings");

  await expect(page).toHaveURL(/login\?redirectTo=/);
  await signIn(page);

  await expect(page).toHaveURL(/settings/);
});

test("invalid credentials show a generic error", async ({ page }) => {
  await mockAuthApi(page, { loginMode: "invalid" });
  await page.goto("/login");

  await signIn(page, { email: "invalid@musematic.dev" });

  await expect(page.getByText("Invalid email or password")).toBeVisible();
});

test("MFA-enrolled users see the MFA challenge step", async ({ page }) => {
  await mockAuthApi(page, { loginMode: "mfa" });
  await page.goto("/login");

  await signIn(page, { email: "mfa@musematic.dev" });

  await expect(page.getByText(/verify your sign-in/i)).toBeVisible();
  await page.getByLabel(/authenticator code/i).fill("123456");
  await expect(page).toHaveURL(/home/);
});

test("lockout responses show the countdown state", async ({ page }) => {
  await mockAuthApi(page, { loginMode: "locked" });
  await page.goto("/login");

  await signIn(page, { email: "locked@musematic.dev" });

  await expect(page.getByText(/too many failed attempts/i)).toBeVisible();
  await expect(page.getByText(/account temporarily locked/i)).toBeVisible();
  await expect(page.getByText("1:00")).toBeVisible();
});
