"use client";

import { Languages } from "lucide-react";
import { useLocale } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { DEFAULT_LOCALE, LOCALE_COOKIE, LOCALES, type Locale, normalizeLocale } from "@/i18n.config";
import { useUpdatePreferences, useUserPreferences } from "@/lib/api/preferences";
import { Select } from "@/components/ui/select";

const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  es: "Español",
  fr: "Français",
  de: "Deutsch",
  it: "Italiano",
  ja: "日本語",
  "zh-CN": "简体中文",
};

export function LocaleSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const runtimeLocale = normalizeLocale(useLocale()) ?? DEFAULT_LOCALE;
  const preferences = useUserPreferences();
  const updatePreferences = useUpdatePreferences();
  const activeLocale = normalizeLocale(preferences.data?.language) ?? runtimeLocale;

  function updateUrl(locale: Locale) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("lang", locale);
    router.replace(`${pathname}?${params.toString()}`);
    router.refresh();
  }

  function persistCookie(locale: Locale) {
    document.cookie = `${LOCALE_COOKIE}=${locale}; Path=/; SameSite=Lax`;
  }

  function handleLocaleChange(value: string) {
    const locale = normalizeLocale(value) ?? DEFAULT_LOCALE;
    persistCookie(locale);
    updateUrl(locale);
    updatePreferences.mutate({ language: locale });
  }

  return (
    <div className="flex items-center gap-2 px-2 py-1.5">
      <Languages className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      <Select
        aria-label="Language"
        className="h-8 min-w-40"
        disabled={updatePreferences.isPending}
        value={activeLocale}
        onChange={(event) => handleLocaleChange(event.target.value)}
      >
        {LOCALES.map((locale) => (
          <option key={locale} value={locale}>
            {LOCALE_LABELS[locale]}
          </option>
        ))}
      </Select>
    </div>
  );
}
