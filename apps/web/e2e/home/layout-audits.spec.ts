import { expect, test, type Locator, type Page } from "@playwright/test";
import { mockAuthApi, signIn } from "../auth/helpers";

async function expectNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth > root.clientWidth + 1;
  });

  expect(hasOverflow).toBeFalsy();
}

async function countRows(locator: Locator) {
  const tops = await locator.evaluateAll((nodes) =>
    nodes.map((node) => Math.round(node.getBoundingClientRect().top)),
  );

  const rows: number[] = [];
  for (const top of tops) {
    if (!rows.some((value) => Math.abs(value - top) <= 8)) {
      rows.push(top);
    }
  }

  return rows.length;
}

test("@a11y home dashboard stays responsive and readable in dark mode", async ({ page }) => {
  await mockAuthApi(page);
  await page.goto("/login");
  await signIn(page);

  await expect(page).toHaveURL(/home/);
  await page.evaluate(() => {
    document.documentElement.classList.add("dark");
  });

  await expect(page.locator("html")).toHaveClass(/dark/);

  const summaryCards = page.locator('[role="group"][aria-label]');
  const recentActivity = page.getByRole("heading", { name: "Recent activity" });
  const pendingActions = page.getByRole("heading", { name: "Pending actions" });

  await expect(summaryCards).toHaveCount(4);

  await page.setViewportSize({ width: 320, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expect(await countRows(summaryCards)).toBe(4);

  await page.setViewportSize({ width: 640, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expect(await countRows(summaryCards)).toBe(2);

  await page.setViewportSize({ width: 768, height: 900 });
  await expectNoHorizontalOverflow(page);
  {
    const recentBox = await recentActivity.boundingBox();
    const pendingBox = await pendingActions.boundingBox();
    expect(recentBox?.y).toBeDefined();
    expect(pendingBox?.y).toBeDefined();
    expect(Math.abs((recentBox?.y ?? 0) - (pendingBox?.y ?? 0))).toBeGreaterThan(40);
  }

  await page.setViewportSize({ width: 1024, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expect(await countRows(summaryCards)).toBe(1);
  {
    const recentBox = await recentActivity.boundingBox();
    const pendingBox = await pendingActions.boundingBox();
    expect(recentBox?.y).toBeDefined();
    expect(pendingBox?.y).toBeDefined();
    expect(Math.abs((recentBox?.y ?? 0) - (pendingBox?.y ?? 0))).toBeLessThan(20);
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expect(page.getByRole("link", { name: "New Conversation" })).toBeVisible();
});
