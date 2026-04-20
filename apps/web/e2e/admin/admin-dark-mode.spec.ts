import { expect, test, type Page } from "@playwright/test";
import { mockAdminApi } from "./helpers";
import { mockAuthApi, signIn } from "../auth/helpers";

async function expectNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth > root.clientWidth + 1;
  });

  expect(hasOverflow).toBeFalsy();
}

test("admin settings tabs render in dark mode without layout regressions", async ({ page }) => {
  await mockAuthApi(page, {
    roles: ["platform_admin"],
    userEmail: "pat.admin@musematic.dev",
    userId: "admin-1",
    userName: "Pat Admin",
  });
  await mockAdminApi(page);

  await page.goto("/login");
  await signIn(page, { email: "pat.admin@musematic.dev" });
  await expect(page).toHaveURL(/\/home/);
  await page.goto("/admin/settings");
  await expect(page).toHaveURL(/\/admin\/settings/);

  await page.evaluate(() => {
    document.documentElement.classList.add("dark");
  });

  await expect(page.locator("html")).toHaveClass(/dark/);

  const tabs = [
    {
      label: "Users",
      content: page.getByText("John Example"),
    },
    {
      label: "Signup",
      content: page.getByText("Signup mode", { exact: true }),
    },
    {
      label: "Quotas",
      content: page.getByRole("heading", { name: "Default quotas" }),
    },
    {
      label: "Connectors",
      content: page.getByRole("heading", { name: "Slack" }),
    },
    {
      label: "Email",
      content: page.getByRole("heading", { name: "Email delivery" }),
    },
    {
      label: "Security",
      content: page.getByRole("heading", { name: "Security policy" }),
    },
  ] as const;

  for (const tab of tabs) {
    await page.getByRole("button", { name: tab.label }).click();
    await expect(tab.content).toBeVisible();
    await expectNoHorizontalOverflow(page);
  }
});
