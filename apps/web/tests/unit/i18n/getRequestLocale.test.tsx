import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider, useTranslations } from "next-intl";
import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, LOCALES } from "@/i18n.config";
import { getRequestLocale } from "@/lib/i18n/getRequestLocale";
import { mergeMessages } from "@/lib/i18n/messages";

function Greeting() {
  const t = useTranslations("common");
  return <p>{t("hello")}</p>;
}

describe("getRequestLocale", () => {
  it("resolves locale precedence as url, preference, browser, default", () => {
    expect(
      getRequestLocale({
        urlHint: "fr",
        cookieLocale: "es",
        acceptLanguage: "de-DE,de;q=0.9",
      }),
    ).toBe("fr");
    expect(
      getRequestLocale({
        urlHint: "pt-BR",
        cookieLocale: "es",
        acceptLanguage: "de-DE,de;q=0.9",
      }),
    ).toBe("es");
    expect(getRequestLocale({ acceptLanguage: "ja-JP,ja;q=0.8" })).toBe("ja");
    expect(getRequestLocale({ acceptLanguage: "pt-BR,pt;q=0.8" })).toBe(DEFAULT_LOCALE);
  });

  it("keeps the frontend locale set aligned with the supported launch locales", () => {
    expect(LOCALES).toEqual(["en", "es", "fr", "de", "it", "ja", "zh-CN"]);
  });
});

describe("i18n messages", () => {
  it("falls back to English message values without exposing raw keys", () => {
    const messages = mergeMessages(
      { common: { hello: "Hello", submit: "Save" } },
      { common: { submit: "Guardar" } },
    );

    render(
      <NextIntlClientProvider locale="es" messages={messages}>
        <Greeting />
      </NextIntlClientProvider>,
    );

    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.queryByText("common.hello")).not.toBeInTheDocument();
  });

  it("uses Intl locale formatting for the supported launch locales", () => {
    const date = new Date(Date.UTC(2026, 3, 29, 12, 0, 0));
    const formatted = new Intl.DateTimeFormat("de", { dateStyle: "long" }).format(date);
    const currency = new Intl.NumberFormat("ja", {
      style: "currency",
      currency: "JPY",
      maximumFractionDigits: 0,
    }).format(123456);

    expect(formatted).toContain("2026");
    expect(currency).toContain("123,456");
  });
});
