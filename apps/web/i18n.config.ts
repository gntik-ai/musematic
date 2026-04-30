import { match } from "@formatjs/intl-localematcher";

export const LOCALES = ["en", "es", "fr", "de", "ja", "zh-CN"] as const;

export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

export const LOCALE_COOKIE = "musematic-locale";
export const THEME_COOKIE = "musematic-theme";

export const NAMESPACES = [
  "marketplace",
  "auth",
  "errors",
  "commands",
  "preferences",
  "incidents",
  "regions",
  "costs",
  "tagging",
  "policies",
  "workflows",
  "fleets",
  "agents",
  "evaluation",
  "platformStatus",
  "simulations",
  "discovery",
  "trust",
  "dashboard",
  "home",
  "admin",
  "workspaces",
  "common",
  "forms",
  "time",
  "numbers",
] as const;

export type Namespace = (typeof NAMESPACES)[number];

const LOCALE_BY_LOWERCASE = new Map<string, Locale>(
  LOCALES.map((locale) => [locale.toLowerCase(), locale]),
);

export function normalizeLocale(value: string | null | undefined): Locale | null {
  const raw = value?.trim().replace("_", "-");
  if (!raw) {
    return null;
  }

  const exact = LOCALE_BY_LOWERCASE.get(raw.toLowerCase());
  if (exact) {
    return exact;
  }

  const primaryLanguage = raw.split("-", 1)[0]?.toLowerCase();
  return LOCALES.find((locale) => locale.toLowerCase().split("-", 1)[0] === primaryLanguage) ?? null;
}

export function parseAcceptLanguage(value: string | null | undefined): string[] {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((part, index) => {
      const [locale, ...options] = part.split(";").map((section) => section.trim());
      const qOption = options.find((option) => option.startsWith("q="));
      const quality = qOption ? Number(qOption.slice(2)) : 1;
      return {
        locale: locale ?? "",
        index,
        quality: Number.isFinite(quality) ? quality : 0,
      };
    })
    .filter(({ locale, quality }) => locale && locale !== "*" && quality > 0)
    .sort((left, right) => right.quality - left.quality || left.index - right.index)
    .map(({ locale }) => locale);
}

export function resolveLocale({
  urlHint,
  userPreference,
  acceptLanguage,
}: {
  urlHint?: string | null | undefined;
  userPreference?: string | null | undefined;
  acceptLanguage?: string | null | undefined;
}): Locale {
  for (const candidate of [urlHint, userPreference]) {
    const locale = normalizeLocale(candidate);
    if (locale) {
      return locale;
    }
  }

  for (const candidate of parseAcceptLanguage(acceptLanguage)) {
    const locale = normalizeLocale(candidate);
    if (locale) {
      return locale;
    }
  }

  const matchedBrowserLocale = match(
    parseAcceptLanguage(acceptLanguage),
    [...LOCALES],
    DEFAULT_LOCALE,
  );
  const normalizedBrowserLocale = normalizeLocale(matchedBrowserLocale);
  if (normalizedBrowserLocale) {
    return normalizedBrowserLocale;
  }

  return DEFAULT_LOCALE;
}
