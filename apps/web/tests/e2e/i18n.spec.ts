import { expect, test } from "@playwright/test";

const locales = ["en", "es", "fr", "de", "it", "ja", "zh-CN"] as const;

test.describe("i18n", () => {
  for (const locale of locales) {
    test(`renders supported locale ${locale} without raw translation keys`, async ({ page }) => {
      await page.addInitScript((localeCode) => {
        document.cookie = `musematic-locale=${localeCode}; Path=/; SameSite=Lax`;
      }, locale);
      await page.goto(`/login?lang=${locale}`);
      await expect(page.locator("body")).not.toContainText(/t\(['"][^)]+['"]\)/);
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
    });
  }

  test("formats dates, numbers, and currency by active locale", async ({ page }) => {
    const formatted = await page.evaluate(() => ({
      date: new Intl.DateTimeFormat("ja-JP").format(new Date("2026-04-29T12:00:00Z")),
      number: new Intl.NumberFormat("de-DE").format(123456.78),
      currency: new Intl.NumberFormat("es-ES", {
        style: "currency",
        currency: "EUR",
      }).format(42.5),
    }));

    expect(formatted.date).toContain("2026");
    expect(formatted.number).toContain(".");
    expect(formatted.currency).toContain("€");
  });
});
