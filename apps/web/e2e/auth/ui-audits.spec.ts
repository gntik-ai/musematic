import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi } from "./helpers";

async function expectNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth > root.clientWidth + 1;
  });

  expect(hasOverflow).toBeFalsy();
}

test("auth flow keeps keyboard order and moves focus into MFA input", async ({ page }) => {
  await mockAuthApi(page, { loginMode: "mfa" });
  await page.goto("/login");

  const email = page.getByLabel("Email");
  const password = page.getByLabel("Password");
  const submit = page.getByRole("button", { name: /^sign in$/i });
  const forgotPassword = page.getByRole("link", { name: /forgot password/i });

  await email.fill("mfa@musematic.dev");
  await password.fill("SecretPass1!");

  await email.focus();
  await page.keyboard.press("Tab");
  await expect(password).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(submit).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(forgotPassword).toBeFocused();

  await page.keyboard.press("Shift+Tab");
  await expect(submit).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(page.getByLabel(/authenticator code/i)).toBeFocused();
});

test("auth pages and MFA enrollment dialog stay responsive in dark mode", async ({ page }) => {
  const authRoutes = [
    { route: "/login", heading: /sign in to musematic/i },
    { route: "/forgot-password", heading: /forgot your password/i },
    { route: "/reset-password/demo-token", heading: /set new password/i },
  ] as const;
  const widths = [320, 768, 1440, 2560];

  await page.addInitScript(() => {
    window.localStorage.setItem("theme", "dark");
  });
  await page.emulateMedia({ colorScheme: "dark" });

  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });

    for (const authRoute of authRoutes) {
      await page.goto(authRoute.route, { waitUntil: "domcontentloaded" });

      await expect(page.locator("html")).toHaveClass(/dark/);
      await expect(
        page.getByRole("heading", { name: authRoute.heading }),
      ).toBeVisible();
      await expectNoHorizontalOverflow(page);
    }

    await mockAuthApi(page, { mfaEnrolled: false });
    await page.goto("/login");
    await page.getByLabel("Email").fill("alex@musematic.dev");
    await page.getByLabel("Password").fill("SecretPass1!");
    await page.getByRole("button", { name: /^sign in$/i }).click();

    await expect(page.getByText(/set up authenticator/i)).toBeVisible();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expectNoHorizontalOverflow(page);
  }
});
