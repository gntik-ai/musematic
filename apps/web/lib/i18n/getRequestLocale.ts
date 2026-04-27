import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  type Locale,
  normalizeLocale,
  resolveLocale,
} from "@/i18n.config";

interface RequestLocaleInput {
  urlHint?: string | null | undefined;
  cookieLocale?: string | null | undefined;
  acceptLanguage?: string | null | undefined;
}

export function getRequestLocale(input: RequestLocaleInput): Locale {
  return resolveLocale({
    urlHint: input.urlHint,
    userPreference: input.cookieLocale,
    acceptLanguage: input.acceptLanguage,
  });
}

export function getLocaleFromCookie(value: string | null | undefined): Locale {
  return normalizeLocale(value) ?? DEFAULT_LOCALE;
}

export { DEFAULT_LOCALE, LOCALE_COOKIE };
